"""Tests for the actor-internal self-nudge in :class:`AgenticActorMixin`.

The mixin owns the "did the agent call the tool I asked for?" decision so
every agentic actor (briefing, decomposer, generator, implementer,
reviewer) gets the same behaviour: a missing tool triggers exactly one
nudge before failing to the supervisor's ``prompt_error`` path.

These tests exercise the helpers directly so we don't depend on a real
ACP subprocess, then cross-check that each agent actor wires the helpers
correctly via its on_tool_call.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
import xoscar as xo

from maverick.actors.xoscar._agentic import AgenticActorMixin
from maverick.tools.agent_inbox.models import (
    SupervisorInboxPayload,
)

# ---------------------------------------------------------------------------
# Mixin helpers — pure unit tests, no actor pool needed.
# ---------------------------------------------------------------------------


class _BareMixin(AgenticActorMixin):
    """Minimal subclass to exercise the mixin helpers in isolation."""

    _actor_tag = "test-mixin"


def test_mark_and_was_tool_delivered_round_trip() -> None:
    m = _BareMixin()
    assert m._was_tool_delivered("foo") is False
    m._mark_tool_delivered("foo")
    assert m._was_tool_delivered("foo") is True
    # Other tools remain untouched.
    assert m._was_tool_delivered("bar") is False


def test_reset_tool_tracking_clears_only_named_tool() -> None:
    m = _BareMixin()
    m._mark_tool_delivered("foo")
    m._mark_tool_delivered("bar")
    m._reset_tool_tracking("foo")
    assert m._was_tool_delivered("foo") is False
    assert m._was_tool_delivered("bar") is True


@pytest.mark.asyncio
async def test_run_with_self_nudge_no_nudge_when_tool_fires() -> None:
    m = _BareMixin()
    nudges: list[str] = []
    failures: list[str] = []

    async def _prompt() -> None:
        m._mark_tool_delivered("submit_x")

    async def _nudge() -> None:
        nudges.append("called")

    async def _failure(msg: str) -> None:
        failures.append(msg)

    await m._run_with_self_nudge(
        expected_tool="submit_x",
        run_prompt=_prompt,
        run_nudge=_nudge,
        on_failure=_failure,
        log_prefix="test",
    )
    assert nudges == []
    assert failures == []


@pytest.mark.asyncio
async def test_run_with_self_nudge_nudges_then_succeeds() -> None:
    m = _BareMixin()
    nudges: list[str] = []
    failures: list[str] = []

    async def _silent_prompt() -> None:
        return None

    async def _nudge_succeeds() -> None:
        nudges.append("called")
        m._mark_tool_delivered("submit_x")

    async def _failure(msg: str) -> None:
        failures.append(msg)

    await m._run_with_self_nudge(
        expected_tool="submit_x",
        run_prompt=_silent_prompt,
        run_nudge=_nudge_succeeds,
        on_failure=_failure,
        log_prefix="test",
    )
    assert len(nudges) == 1
    assert failures == []


@pytest.mark.asyncio
async def test_run_with_self_nudge_reports_failure_when_both_silent() -> None:
    m = _BareMixin()
    nudges: list[str] = []
    failures: list[str] = []

    async def _silent_prompt() -> None:
        return None

    async def _silent_nudge() -> None:
        nudges.append("called")

    async def _failure(msg: str) -> None:
        failures.append(msg)

    await m._run_with_self_nudge(
        expected_tool="submit_x",
        run_prompt=_silent_prompt,
        run_nudge=_silent_nudge,
        on_failure=_failure,
        log_prefix="test",
    )
    assert len(nudges) == 1
    assert len(failures) == 1
    assert "submit_x" in failures[0]
    assert "two turns" in failures[0]


@pytest.mark.asyncio
async def test_run_with_self_nudge_routes_prompt_exception_to_failure() -> None:
    m = _BareMixin()
    nudges: list[str] = []
    failures: list[str] = []

    async def _boom() -> None:
        raise RuntimeError("ACP exploded")

    async def _nudge() -> None:
        nudges.append("called")

    async def _failure(msg: str) -> None:
        failures.append(msg)

    await m._run_with_self_nudge(
        expected_tool="submit_x",
        run_prompt=_boom,
        run_nudge=_nudge,
        on_failure=_failure,
        log_prefix="test",
    )
    assert nudges == []  # nudge does not fire on hard prompt error
    assert failures == ["ACP exploded"]


@pytest.mark.asyncio
async def test_run_with_self_nudge_routes_nudge_exception_to_failure() -> None:
    m = _BareMixin()
    failures: list[str] = []

    async def _silent_prompt() -> None:
        return None

    async def _nudge_boom() -> None:
        raise RuntimeError("nudge exploded")

    async def _failure(msg: str) -> None:
        failures.append(msg)

    await m._run_with_self_nudge(
        expected_tool="submit_x",
        run_prompt=_silent_prompt,
        run_nudge=_nudge_boom,
        on_failure=_failure,
        log_prefix="test",
    )
    assert failures == ["nudge exploded"]


# ---------------------------------------------------------------------------
# Transient retry: the prompt-runner retries once on transient errors
# before propagating. Quota and other failures pass through immediately.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transient_retry_recovers_after_blip() -> None:
    """A transient first call followed by success returns cleanly."""
    m = _BareMixin()
    calls: list[int] = []

    async def _flaky() -> None:
        calls.append(1)
        if len(calls) == 1:
            # Real-world capacity-error string from the gemini ACP path.
            raise RuntimeError("ACP prompt failed: No capacity available for model X (code=500)")

    await m._run_prompt_with_transient_retry(
        _flaky,
        log_prefix="test",
        actor_tag="bare",
        backoff_seconds=0,  # don't slow the test
    )
    assert len(calls) == 2  # original + one retry


@pytest.mark.asyncio
async def test_transient_retry_propagates_after_second_failure() -> None:
    """Two transient failures in a row → exception propagates."""
    m = _BareMixin()
    calls: list[int] = []

    async def _always_transient() -> None:
        calls.append(1)
        raise RuntimeError("Service unavailable")

    with pytest.raises(RuntimeError, match="Service unavailable"):
        await m._run_prompt_with_transient_retry(
            _always_transient,
            log_prefix="test",
            actor_tag="bare",
            backoff_seconds=0,
        )
    # Exactly one retry — no infinite loop.
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_non_transient_error_propagates_without_retry() -> None:
    """Non-transient errors are not retried — they fail through immediately."""
    m = _BareMixin()
    calls: list[int] = []

    async def _content_error() -> None:
        calls.append(1)
        raise RuntimeError("Agent not found in registry")

    with pytest.raises(RuntimeError, match="Agent not found"):
        await m._run_prompt_with_transient_retry(
            _content_error,
            log_prefix="test",
            actor_tag="bare",
            backoff_seconds=0,
        )
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_quota_errors_are_not_retried() -> None:
    """Quota errors (which excludes them from is_transient_error) skip retry."""
    m = _BareMixin()
    calls: list[int] = []

    async def _quota_error() -> None:
        calls.append(1)
        raise RuntimeError("You've hit your limit · resets 6am")

    with pytest.raises(RuntimeError, match="hit your limit"):
        await m._run_prompt_with_transient_retry(
            _quota_error,
            log_prefix="test",
            actor_tag="bare",
            backoff_seconds=0,
        )
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_self_nudge_retries_transient_prompt() -> None:
    """End-to-end: ``_run_with_self_nudge`` lets the inner retry recover."""
    m = _BareMixin()
    prompt_calls: list[int] = []
    failures: list[str] = []

    async def _flaky_prompt() -> None:
        prompt_calls.append(1)
        if len(prompt_calls) == 1:
            raise RuntimeError("HTTP 503 server error")
        # Second call succeeds — mark the tool delivered.
        m._mark_tool_delivered("submit_x")

    async def _nudge_unused() -> None:
        raise AssertionError("nudge should not run when retry recovers")

    async def _failure(msg: str) -> None:
        failures.append(msg)

    with patch("asyncio.sleep", new=_no_sleep):
        await m._run_with_self_nudge(
            expected_tool="submit_x",
            run_prompt=_flaky_prompt,
            run_nudge=_nudge_unused,
            on_failure=_failure,
            log_prefix="test",
        )
    assert prompt_calls == [1, 1]  # retry recovered
    assert failures == []  # no failure routed


async def _no_sleep(_seconds: float) -> None:
    """Patch target — skip the retry backoff in tests."""
    return None


# ---------------------------------------------------------------------------
# Per-actor wiring — confirm each actor flips the flag in on_tool_call and
# triggers the nudge path through ``send_*`` when the tool is skipped.
# ---------------------------------------------------------------------------


class _Recorder(xo.Actor):
    """Supervisor double recording typed callbacks + prompt_errors."""

    async def __post_create__(self) -> None:
        self._payloads: list[tuple[str, SupervisorInboxPayload]] = []
        self._errors: list[PromptError] = []

    # Generic forward methods used across actors.
    async def briefing_ready(self, payload: SupervisorInboxPayload) -> None:
        self._payloads.append(("briefing", payload))

    async def flight_plan_ready(self, payload: SubmitFlightPlanPayload) -> None:
        self._payloads.append(("flight_plan", payload))

    async def implementation_ready(self, payload: SubmitImplementationPayload) -> None:
        self._payloads.append(("implementation", payload))

    async def review_ready(self, payload: SubmitReviewPayload) -> None:
        self._payloads.append(("review", payload))

    async def prompt_error(self, error: PromptError) -> None:
        self._errors.append(error)

    async def payload_parse_error(self, tool: str, message: str) -> None:  # pragma: no cover
        pass

    # Test inspection helpers.
    async def payloads(self) -> list[tuple[str, SupervisorInboxPayload]]:
        return list(self._payloads)

    async def errors(self) -> list[PromptError]:
        return list(self._errors)


_VALID_FLIGHT_PLAN: dict[str, Any] = {
    "objective": "build a thing",
    "success_criteria": [],
    "in_scope": [],
    "out_of_scope": [],
    "constraints": [],
    "context": "",
    "tags": [],
}

_VALID_IMPLEMENTATION: dict[str, Any] = {
    "summary": "did the thing",
    "files_changed": [],
}

_VALID_REVIEW: dict[str, Any] = {
    "approved": True,
    "findings": [],
    "summary": "looks good",
}


# NOTE: BriefingActor migrated to OpenCodeAgentMixin (Phase 4.3).
# Coverage of the new pattern lives in
# tests/unit/actors/xoscar_runtime/test_briefing_inbox.py.


# NOTE: GeneratorActor migrated to OpenCodeAgentMixin (Phase 4.2).
# Coverage of the new pattern lives in
# tests/unit/actors/xoscar_runtime/test_plan_actors.py.


# NOTE: ImplementerActor migrated to OpenCodeAgentMixin (Phase 4).
# Coverage of the new pattern lives in
# tests/unit/actors/xoscar_runtime/test_implementer_reviewer_inbox.py.


# NOTE: ReviewerActor migrated to OpenCodeAgentMixin (Phase 4.5).
# Coverage of the new pattern lives in
# tests/unit/actors/xoscar_runtime/test_reviewer_opencode.py and
# tests/unit/actors/xoscar_runtime/test_implementer_reviewer_inbox.py.
