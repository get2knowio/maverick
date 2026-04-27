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
from maverick.actors.xoscar.briefing import BriefingActor
from maverick.actors.xoscar.generator import GENERATOR_MCP_TOOL, GeneratorActor
from maverick.actors.xoscar.implementer import ImplementerActor
from maverick.actors.xoscar.messages import (
    BriefingRequest,
    GenerateRequest,
    ImplementRequest,
    PromptError,
    ReviewRequest,
)
from maverick.actors.xoscar.reviewer import REVIEWER_MCP_TOOL, ReviewerActor
from maverick.tools.agent_inbox.models import (
    SubmitFlightPlanPayload,
    SubmitImplementationPayload,
    SubmitReviewPayload,
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


@pytest.mark.asyncio
async def test_briefing_actor_self_nudges(pool_address: str) -> None:
    """BriefingActor: silent first prompt → nudge → tool delivered → success."""
    sup = await xo.create_actor(_Recorder, address=pool_address, uid="b-sup")
    actor = await xo.create_actor(
        BriefingActor,
        sup,
        agent_name="navigator",
        mcp_tool="submit_navigator_brief",
        forward_method="briefing_ready",
        cwd="/tmp",
        config=None,
        address=pool_address,
        uid="b-actor",
    )

    async def _silent(self: BriefingActor, request: Any) -> None:
        return None

    async def _nudge_calls_tool(self: BriefingActor) -> None:
        await self.on_tool_call(
            "submit_navigator_brief",
            {"architecture_decisions": [], "summary": "ok"},
        )

    try:
        with (
            patch.object(BriefingActor, "_send_prompt", new=_silent),
            patch.object(BriefingActor, "_send_nudge_prompt", new=_nudge_calls_tool),
            patch.object(BriefingActor, "_end_turn", new=_noop_end_turn_one_arg),
        ):
            await actor.send_briefing(BriefingRequest(agent_name="navigator", prompt="x"))

        payloads = await sup.payloads()
        errors = await sup.errors()
        assert len(payloads) == 1
        assert payloads[0][0] == "briefing"
        assert errors == []
    finally:
        await xo.destroy_actor(actor)
        await xo.destroy_actor(sup)


@pytest.mark.asyncio
async def test_briefing_actor_reports_after_nudge_silence(pool_address: str) -> None:
    sup = await xo.create_actor(_Recorder, address=pool_address, uid="b-sup-fail")
    actor = await xo.create_actor(
        BriefingActor,
        sup,
        agent_name="navigator",
        mcp_tool="submit_navigator_brief",
        forward_method="briefing_ready",
        cwd="/tmp",
        config=None,
        address=pool_address,
        uid="b-actor-fail",
    )

    async def _silent(self: BriefingActor, *args: Any, **_: Any) -> None:
        return None

    try:
        with (
            patch.object(BriefingActor, "_send_prompt", new=_silent),
            patch.object(BriefingActor, "_send_nudge_prompt", new=_silent),
            patch.object(BriefingActor, "_end_turn", new=_noop_end_turn_one_arg),
        ):
            await actor.send_briefing(BriefingRequest(agent_name="navigator", prompt="x"))

        payloads = await sup.payloads()
        errors = await sup.errors()
        assert payloads == []
        assert len(errors) == 1
        assert errors[0].phase == "briefing"
        assert "submit_navigator_brief" in errors[0].error
    finally:
        await xo.destroy_actor(actor)
        await xo.destroy_actor(sup)


@pytest.mark.asyncio
async def test_generator_actor_self_nudges(pool_address: str) -> None:
    sup = await xo.create_actor(_Recorder, address=pool_address, uid="g-sup")
    actor = await xo.create_actor(
        GeneratorActor,
        sup,
        cwd="/tmp",
        config=None,
        address=pool_address,
        uid="g-actor",
    )

    async def _silent(self: GeneratorActor, *args: Any, **_: Any) -> None:
        return None

    async def _nudge_calls_tool(self: GeneratorActor) -> None:
        await self.on_tool_call(GENERATOR_MCP_TOOL, _VALID_FLIGHT_PLAN)

    try:
        with (
            patch.object(GeneratorActor, "_send_prompt", new=_silent),
            patch.object(GeneratorActor, "_send_nudge_prompt", new=_nudge_calls_tool),
            patch.object(GeneratorActor, "_end_turn", new=_noop_end_turn_one_arg),
        ):
            await actor.send_generate(GenerateRequest(prompt="hi"))

        payloads = await sup.payloads()
        errors = await sup.errors()
        assert [kind for kind, _ in payloads] == ["flight_plan"]
        assert errors == []
    finally:
        await xo.destroy_actor(actor)
        await xo.destroy_actor(sup)


@pytest.mark.asyncio
async def test_implementer_actor_self_nudges(pool_address: str) -> None:
    sup = await xo.create_actor(_Recorder, address=pool_address, uid="i-sup")
    actor = await xo.create_actor(
        ImplementerActor,
        sup,
        cwd="/tmp",
        config=None,
        address=pool_address,
        uid="i-actor",
    )

    async def _silent(self: ImplementerActor, *args: Any, **_: Any) -> None:
        return None

    async def _nudge_calls_tool(self: ImplementerActor, expected_tool: str, *, phase: str) -> None:
        await self.on_tool_call(expected_tool, _VALID_IMPLEMENTATION)

    try:
        with (
            patch.object(ImplementerActor, "_send_prompt", new=_silent),
            patch.object(ImplementerActor, "_send_nudge_prompt", new=_nudge_calls_tool),
            patch.object(ImplementerActor, "_end_turn", new=_noop_end_turn_one_arg),
        ):
            await actor.send_implement(ImplementRequest(prompt="implement", bead_id="bd-1"))

        payloads = await sup.payloads()
        errors = await sup.errors()
        assert [kind for kind, _ in payloads] == ["implementation"]
        assert errors == []
    finally:
        await xo.destroy_actor(actor)
        await xo.destroy_actor(sup)


@pytest.mark.asyncio
async def test_reviewer_actor_self_nudges(pool_address: str) -> None:
    sup = await xo.create_actor(_Recorder, address=pool_address, uid="r-sup")
    actor = await xo.create_actor(
        ReviewerActor,
        sup,
        cwd="/tmp",
        config=None,
        address=pool_address,
        uid="r-actor",
    )

    async def _silent(self: ReviewerActor, *args: Any, **_: Any) -> None:
        return None

    async def _nudge_calls_tool(self: ReviewerActor, *, phase: str) -> None:
        await self.on_tool_call(REVIEWER_MCP_TOOL, _VALID_REVIEW)

    try:
        with (
            patch.object(ReviewerActor, "_send_review_prompt", new=_silent),
            patch.object(ReviewerActor, "_send_nudge_prompt", new=_nudge_calls_tool),
            patch.object(ReviewerActor, "_end_turn", new=_noop_end_turn_one_arg),
        ):
            await actor.send_review(ReviewRequest(bead_id="bd-1"))

        payloads = await sup.payloads()
        errors = await sup.errors()
        assert [kind for kind, _ in payloads] == ["review"]
        assert errors == []
    finally:
        await xo.destroy_actor(actor)
        await xo.destroy_actor(sup)


async def _noop_end_turn_one_arg(self: Any) -> None:
    """No-op _end_turn — there's no real ACP session in these tests."""
    return None
