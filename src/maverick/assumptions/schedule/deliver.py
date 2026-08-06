"""ntfy delivery for the assumption batch scheduler (``maverick notify``).

**Single canonical wrapper** (Guardrail 5): this module is the only one
that may construct ntfy requests — see
``specs/054-assumption-batch-scheduler/contracts/ntfy-payload.md``.

:class:`NtfyDeliverer` POSTs to ``{server}/{topic}`` via ``httpx.AsyncClient``
with an explicit 10-second timeout, retrying transient failures
(``httpx.TransportError`` and HTTP 5xx) with ``tenacity.AsyncRetrying`` (3
attempts, exponential backoff). HTTP 4xx responses are a configuration
problem retrying cannot fix, so they fail immediately. Exhausted retries and
non-retryable rejections both raise :class:`DeliveryFailedError` — per
FR-012, the triggering decision must never be recorded as delivered, so the
batch stays due for the next evaluation.

Payloads are built from :class:`~maverick.assumptions.schedule.models.BatchSummary`
only (never entry contents — FR-008): counts by severity, owning specs,
oldest-entry age, and a suggested review invocation. :func:`build_payload`
takes the delivery ``kind`` explicitly so the escalation/renotify kinds
wired in by later phases (T021, T028) are pure additions to the priority/
title tables below, not a restructuring.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
from tenacity.wait import WaitBaseT

from maverick.assumptions.models import Severity
from maverick.assumptions.schedule.models import BatchSummary, DecisionKind, format_age_hours
from maverick.exceptions.base import MaverickError
from maverick.logging import get_logger

__all__ = [
    "DeliveryFailedError",
    "NtfyDeliverer",
    "NtfyPayload",
    "build_payload",
]

logger = get_logger(__name__)

#: Explicit request timeout (contracts/ntfy-payload.md, research.md R5).
_REQUEST_TIMEOUT_SECONDS = 10.0

#: Retry budget: 3 attempts total (1 initial + 2 retries), exponential
#: backoff (contracts/ntfy-payload.md, research.md R5).
_MAX_ATTEMPTS = 3
_DEFAULT_WAIT: WaitBaseT = wait_exponential(multiplier=1, min=1, max=8)

#: HTTP status thresholds: >=500 retries, >=400 (and <500) fails immediately.
_RETRYABLE_STATUS_FLOOR = 500
_CLIENT_ERROR_STATUS_FLOOR = 400

_TAGS = "maverick,assumptions"

#: Stand-in for the spec list when no open entry carries an owning spec —
#: without it the body reads "... low open across ." (an empty join).
_NO_SPEC_PLACEHOLDER = "no owning spec"

#: Title per DecisionKind (contracts/ntfy-payload.md). window-batch's
#: ``{count}`` placeholder is filled from the summary's total open-entry
#: count; the other kinds carry no placeholder and pass through unchanged.
_TITLES: dict[DecisionKind, str] = {
    DecisionKind.WINDOW_BATCH: "Assumption review: {count} open entries",
    DecisionKind.INTERRUPT: "High-severity assumption recorded",
    DecisionKind.ESCALATION: "Assumption entries aging past limit",
    DecisionKind.RENOTIFY: "High-severity assumption still unanswered",
}

#: Priority per DecisionKind (contracts/ntfy-payload.md): every kind but
#: window-batch is urgent.
_URGENT_KINDS = frozenset({DecisionKind.INTERRUPT, DecisionKind.ESCALATION, DecisionKind.RENOTIFY})


class DeliveryFailedError(MaverickError):
    """Raised when an ntfy delivery cannot be completed (FR-012).

    Covers both exhausted retries (5xx / transport errors across
    ``_MAX_ATTEMPTS`` attempts) and an immediate 4xx rejection. In either
    case the triggering decision must not be recorded as delivered — the
    caller (the ``notify`` command layer) leaves the batch due.

    Attributes:
        kind: The delivery kind that failed to send.
        status_code: The last HTTP status code observed, or ``None`` when
            every attempt failed at the transport layer without a response.
    """

    def __init__(
        self,
        message: str,
        *,
        kind: DecisionKind,
        status_code: int | None = None,
    ) -> None:
        """Initialize the DeliveryFailedError.

        Args:
            message: Human-readable error message.
            kind: The delivery kind that failed to send.
            status_code: The last HTTP status code observed, if any.
        """
        self.kind = kind
        self.status_code = status_code
        super().__init__(message)


class _RetryableStatusError(Exception):
    """Internal signal: an ntfy response was 5xx and tenacity should retry.

    Never escapes :class:`NtfyDeliverer` — it is either swallowed by a
    successful subsequent attempt or translated into
    :class:`DeliveryFailedError` once retries are exhausted.
    """

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"ntfy responded {status_code}")


@dataclass(frozen=True, slots=True)
class NtfyPayload:
    """The literal ntfy request shape for one delivery.

    Attributes:
        title: The ``Title`` header value.
        priority: The ``Priority`` header value (``"default"`` or
            ``"urgent"``).
        tags: The ``Tags`` header value.
        body: The plain-text request body.
    """

    title: str
    priority: str
    tags: str
    body: str


def build_payload(kind: DecisionKind, summary: BatchSummary) -> NtfyPayload:
    """Build the content-free ntfy payload for one delivery decision.

    The payload is derived exclusively from *summary* — counts, owning
    specs, oldest-entry age, and a review invocation. There are no
    entry-content fields on :class:`BatchSummary` to leak (FR-008); a
    prohibited field would require a type-level change here, not a
    formatting slip.

    Args:
        kind: Which delivery category this payload represents. Selects
            the title template and priority per
            contracts/ntfy-payload.md's table.
        summary: Content-free aggregate of the covered entries.

    Returns:
        The ``Title``/``Priority``/``Tags``/body values to send.
    """
    total = sum(summary.counts.values())
    title = _TITLES[kind].format(count=total)
    priority = "urgent" if kind in _URGENT_KINDS else "default"
    specs = ", ".join(summary.owner_specs) if summary.owner_specs else _NO_SPEC_PLACEHOLDER
    body = (
        f"{summary.counts.get(Severity.HIGH, 0)} high, "
        f"{summary.counts.get(Severity.MEDIUM, 0)} medium, "
        f"{summary.counts.get(Severity.LOW, 0)} low open across "
        f"{specs}.\n"
        f"Oldest: {format_age_hours(summary.oldest_age_hours)}h.\n"
        f"Run: {summary.review_invocation}"
    )
    return NtfyPayload(title=title, priority=priority, tags=_TAGS, body=body)


class NtfyDeliverer:
    """Delivers assumption-scheduler notifications to an ntfy topic.

    The only module permitted to construct ntfy requests (Guardrail 5).
    Owns one ``httpx.AsyncClient`` for its lifetime; callers should use it
    as an async context manager or call :meth:`aclose` explicitly.
    """

    def __init__(
        self,
        server: str,
        topic: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = _REQUEST_TIMEOUT_SECONDS,
        wait: WaitBaseT | None = None,
    ) -> None:
        """Initialize the NtfyDeliverer.

        Args:
            server: ntfy server base URL (``notifications.server``), e.g.
                ``"https://ntfy.sh"``.
            topic: ntfy topic name (``notifications.topic``).
            transport: Optional ``httpx`` transport override — used in
                tests to inject ``httpx.MockTransport``. ``None`` uses
                httpx's default transport.
            timeout: Explicit request timeout in seconds, applied to
                connect/read/write/pool phases uniformly.
            wait: Optional tenacity wait strategy override — used in tests
                to avoid real sleeps. Defaults to exponential backoff
                (multiplier=1s, min=1s, max=8s).
        """
        self._server = server.rstrip("/")
        self._topic = topic
        self._client = httpx.AsyncClient(timeout=timeout, transport=transport)
        self._wait: WaitBaseT = wait if wait is not None else _DEFAULT_WAIT

    async def __aenter__(self) -> NtfyDeliverer:
        """Enter the async context, returning self."""
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        """Exit the async context, closing the underlying HTTP client."""
        await self.aclose()

    async def aclose(self) -> None:
        """Close the underlying ``httpx.AsyncClient``."""
        await self._client.aclose()

    async def deliver(self, kind: DecisionKind, summary: BatchSummary) -> None:
        """Deliver one notification to the configured ntfy topic.

        Args:
            kind: Which delivery category to send — selects title/priority
                per contracts/ntfy-payload.md.
            summary: Content-free aggregate of the covered entries; the
                sole input to payload construction (FR-008).

        Raises:
            DeliveryFailedError: The request was rejected with a 4xx
                status (no retry), or retries were exhausted against 5xx
                responses / transport errors.
        """
        payload = build_payload(kind, summary)
        response = await self._post_with_retry(kind, payload)

        if response.status_code >= _CLIENT_ERROR_STATUS_FLOOR:
            logger.warning(
                "ntfy_delivery_rejected",
                kind=str(kind),
                status_code=response.status_code,
            )
            raise DeliveryFailedError(
                f"ntfy rejected delivery with status {response.status_code}",
                kind=kind,
                status_code=response.status_code,
            )

    async def _post_with_retry(self, kind: DecisionKind, payload: NtfyPayload) -> httpx.Response:
        """POST *payload*, retrying transient failures per the retry policy.

        A 5xx response or ``httpx.TransportError`` triggers a retry (up to
        ``_MAX_ATTEMPTS`` total attempts, exponential backoff). A 2xx or
        4xx response returns immediately — 4xx is a configuration problem
        retrying cannot fix and is left for :meth:`deliver` to translate
        into :class:`DeliveryFailedError`.

        Args:
            kind: The delivery kind being sent, for error attribution.
            payload: The already-built ntfy payload.

        Returns:
            The final ``httpx.Response`` (2xx or 4xx).

        Raises:
            DeliveryFailedError: Retries exhausted against 5xx responses
                or transport errors.
        """
        url = f"{self._server}/{self._topic}"
        headers = {
            "Title": payload.title,
            "Priority": payload.priority,
            "Tags": payload.tags,
        }

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(_MAX_ATTEMPTS),
                wait=self._wait,
                retry=retry_if_exception_type((httpx.TransportError, _RetryableStatusError)),
            ):
                with attempt:
                    response = await self._client.post(
                        url,
                        content=payload.body.encode("utf-8"),
                        headers=headers,
                    )
                    if response.status_code >= _RETRYABLE_STATUS_FLOOR:
                        raise _RetryableStatusError(response.status_code)
                    return response
        except RetryError as exc:
            cause = exc.last_attempt.exception()
            status_code = cause.status_code if isinstance(cause, _RetryableStatusError) else None
            logger.warning(
                "ntfy_delivery_exhausted",
                kind=str(kind),
                status_code=status_code,
                attempts=_MAX_ATTEMPTS,
            )
            detail = f" (last status {status_code})" if status_code is not None else ""
            raise DeliveryFailedError(
                f"ntfy delivery failed after {_MAX_ATTEMPTS} attempts{detail}",
                kind=kind,
                status_code=status_code,
            ) from exc

        # Unreachable: AsyncRetrying either returns via a successful attempt
        # above or raises RetryError, which is handled. Satisfies the type
        # checker (mirrors the house pattern in runners/github.py).
        raise AssertionError("unreachable: AsyncRetrying attempt loop exited without returning")
