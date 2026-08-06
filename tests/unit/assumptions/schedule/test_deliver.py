"""Tests for the ntfy deliverer (contracts/ntfy-payload.md, tasks.md T012).

Covers request shape (URL, headers, body template), the window-batch
priority mapping, the retry-on-5xx/transport-error and no-retry-on-4xx
policies, the typed error raised once retries are exhausted, and the
content-free-payload guarantee (FR-008).
"""

from __future__ import annotations

import httpx
import pytest
from tenacity import wait_none

from maverick.assumptions.models import Severity
from maverick.assumptions.schedule.deliver import (
    DeliveryFailedError,
    NtfyDeliverer,
    build_payload,
)
from maverick.assumptions.schedule.models import BatchSummary, DecisionKind

_SERVER = "https://ntfy.example.com"
_TOPIC = "maverick-assumptions"


def _make_summary(
    *,
    high: int = 1,
    medium: int = 2,
    low: int = 3,
    owner_specs: tuple[str, ...] = ("054-assumption-batch-scheduler",),
    oldest_age_hours: float = 26.5,
    review_invocation: str = "maverick review --list --status open",
) -> BatchSummary:
    return BatchSummary(
        counts={Severity.HIGH: high, Severity.MEDIUM: medium, Severity.LOW: low},
        owner_specs=owner_specs,
        oldest_age_hours=oldest_age_hours,
        review_invocation=review_invocation,
    )


def _deliverer(handler: httpx.MockTransport, *, wait: object = None) -> NtfyDeliverer:
    return NtfyDeliverer(
        _SERVER,
        _TOPIC,
        transport=handler,
        wait=wait_none() if wait is None else wait,
    )


class _CountingHandler:
    """A MockTransport handler that records every request and can be
    scripted to return a fixed sequence of responses/exceptions."""

    def __init__(self, responses: list[httpx.Response | Exception]) -> None:
        self._responses = list(responses)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        outcome = self._responses[len(self.requests) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    @property
    def call_count(self) -> int:
        return len(self.requests)


# --- build_payload -----------------------------------------------------------


class TestBuildPayload:
    def test_window_batch_title_and_priority(self) -> None:
        summary = _make_summary(high=1, medium=2, low=3)

        payload = build_payload(DecisionKind.WINDOW_BATCH, summary)

        assert payload.title == "Assumption review: 6 open entries"
        assert payload.priority == "default"
        assert payload.tags == "maverick,assumptions"

    def test_interrupt_escalation_renotify_are_urgent(self) -> None:
        summary = _make_summary()

        for kind, expected_title in (
            (DecisionKind.INTERRUPT, "High-severity assumption recorded"),
            (DecisionKind.ESCALATION, "Assumption entries aging past limit"),
            (DecisionKind.RENOTIFY, "High-severity assumption still unanswered"),
        ):
            payload = build_payload(kind, summary)
            assert payload.priority == "urgent"
            assert payload.title == expected_title

    def test_body_matches_template(self) -> None:
        summary = _make_summary(
            high=1,
            medium=2,
            low=3,
            owner_specs=("054-assumption-batch-scheduler", "049-assumption-ledger"),
            oldest_age_hours=26.5,
            review_invocation="maverick review --list --status open",
        )

        payload = build_payload(DecisionKind.WINDOW_BATCH, summary)

        assert payload.body == (
            "1 high, 2 medium, 3 low open across "
            "054-assumption-batch-scheduler, 049-assumption-ledger.\n"
            "Oldest: 26.5h.\n"
            "Run: maverick review --list --status open"
        )

    def test_body_contains_no_entry_content_fields(self) -> None:
        """FR-008: the payload must never carry entry-specific content —
        BatchSummary structurally has none to leak, but pin it anyway."""
        summary = _make_summary(
            review_invocation="maverick review --list --spec 054 --status open"
        )

        payload = build_payload(DecisionKind.WINDOW_BATCH, summary)
        full_text = f"{payload.title}\n{payload.body}"

        for forbidden in ("bd-", "question", "answer", "waive", "rationale", "alternative"):
            assert forbidden not in full_text.lower()


# --- NtfyDeliverer: request shape ---------------------------------------------


class TestNtfyDelivererRequestShape:
    @pytest.mark.asyncio
    async def test_posts_to_server_slash_topic(self) -> None:
        handler = _CountingHandler([httpx.Response(200)])
        deliverer = _deliverer(httpx.MockTransport(handler))

        await deliverer.deliver(DecisionKind.WINDOW_BATCH, _make_summary())
        await deliverer.aclose()

        assert handler.call_count == 1
        request = handler.requests[0]
        assert request.method == "POST"
        assert str(request.url) == f"{_SERVER}/{_TOPIC}"

    @pytest.mark.asyncio
    async def test_headers_and_body_sent_on_wire(self) -> None:
        handler = _CountingHandler([httpx.Response(200)])
        deliverer = _deliverer(httpx.MockTransport(handler))
        summary = _make_summary(high=0, medium=1, low=0)

        await deliverer.deliver(DecisionKind.WINDOW_BATCH, summary)
        await deliverer.aclose()

        request = handler.requests[0]
        assert request.headers["Title"] == "Assumption review: 1 open entries"
        assert request.headers["Priority"] == "default"
        assert request.headers["Tags"] == "maverick,assumptions"
        assert (
            request.content.decode("utf-8")
            == build_payload(DecisionKind.WINDOW_BATCH, summary).body
        )

    @pytest.mark.asyncio
    async def test_server_trailing_slash_normalized(self) -> None:
        handler = _CountingHandler([httpx.Response(200)])
        deliverer = NtfyDeliverer(
            f"{_SERVER}/",
            _TOPIC,
            transport=httpx.MockTransport(handler),
            wait=wait_none(),
        )

        await deliverer.deliver(DecisionKind.WINDOW_BATCH, _make_summary())
        await deliverer.aclose()

        assert str(handler.requests[0].url) == f"{_SERVER}/{_TOPIC}"


# --- NtfyDeliverer: retry policy -----------------------------------------------


class TestNtfyDelivererRetryPolicy:
    @pytest.mark.asyncio
    async def test_retries_on_5xx_then_succeeds(self) -> None:
        handler = _CountingHandler([httpx.Response(503), httpx.Response(502), httpx.Response(200)])
        deliverer = _deliverer(httpx.MockTransport(handler))

        await deliverer.deliver(DecisionKind.WINDOW_BATCH, _make_summary())
        await deliverer.aclose()

        assert handler.call_count == 3

    @pytest.mark.asyncio
    async def test_retries_on_transport_error_then_succeeds(self) -> None:
        handler = _CountingHandler(
            [
                httpx.ConnectError("connection refused"),
                httpx.ReadTimeout("timed out"),
                httpx.Response(200),
            ]
        )
        deliverer = _deliverer(httpx.MockTransport(handler))

        await deliverer.deliver(DecisionKind.WINDOW_BATCH, _make_summary())
        await deliverer.aclose()

        assert handler.call_count == 3

    @pytest.mark.asyncio
    async def test_exhausted_5xx_retries_raise_typed_error(self) -> None:
        handler = _CountingHandler([httpx.Response(500), httpx.Response(500), httpx.Response(500)])
        deliverer = _deliverer(httpx.MockTransport(handler))

        with pytest.raises(DeliveryFailedError) as exc_info:
            await deliverer.deliver(DecisionKind.WINDOW_BATCH, _make_summary())
        await deliverer.aclose()

        assert handler.call_count == 3
        assert exc_info.value.kind == DecisionKind.WINDOW_BATCH
        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_exhausted_transport_error_retries_raise_typed_error(self) -> None:
        handler = _CountingHandler(
            [
                httpx.ConnectError("connection refused"),
                httpx.ConnectError("connection refused"),
                httpx.ConnectError("connection refused"),
            ]
        )
        deliverer = _deliverer(httpx.MockTransport(handler))

        with pytest.raises(DeliveryFailedError) as exc_info:
            await deliverer.deliver(DecisionKind.WINDOW_BATCH, _make_summary())
        await deliverer.aclose()

        assert handler.call_count == 3
        assert exc_info.value.status_code is None

    @pytest.mark.asyncio
    async def test_4xx_fails_immediately_without_retry(self) -> None:
        handler = _CountingHandler([httpx.Response(400)])
        deliverer = _deliverer(httpx.MockTransport(handler))

        with pytest.raises(DeliveryFailedError) as exc_info:
            await deliverer.deliver(DecisionKind.WINDOW_BATCH, _make_summary())
        await deliverer.aclose()

        assert handler.call_count == 1
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_404_fails_immediately_without_retry(self) -> None:
        handler = _CountingHandler([httpx.Response(404)])
        deliverer = _deliverer(httpx.MockTransport(handler))

        with pytest.raises(DeliveryFailedError):
            await deliverer.deliver(DecisionKind.WINDOW_BATCH, _make_summary())
        await deliverer.aclose()

        assert handler.call_count == 1


# --- Async context manager -----------------------------------------------------


class TestNtfyDelivererContextManager:
    @pytest.mark.asyncio
    async def test_async_context_manager_closes_client(self) -> None:
        handler = _CountingHandler([httpx.Response(200)])

        async with _deliverer(httpx.MockTransport(handler)) as deliverer:
            await deliverer.deliver(DecisionKind.WINDOW_BATCH, _make_summary())

        assert handler.call_count == 1
