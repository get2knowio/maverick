"""Tests for the actor-internal self-nudge in :class:`DecomposerActor`.

The actor is the only thing that owns its ACP session and ``on_tool_call``
handler — so when the agent finishes its turn without calling the expected
MCP tool, the actor must self-nudge once before reporting failure. The
supervisor only sees the typed callback (success) or a ``PromptError``
(failure), never has to inspect "did a tool fire" itself.

These tests exercise that contract end-to-end through xoscar:
  * happy path — first prompt fires the tool, no nudge
  * recovery path — first prompt skips the tool, nudge succeeds
  * exhaustion path — both prompts skip the tool, PromptError reported
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
import xoscar as xo

from maverick.actors.xoscar.decomposer import DecomposerActor
from maverick.actors.xoscar.messages import OutlineRequest, PromptError
from maverick.tools.agent_inbox.models import SubmitOutlinePayload

_VALID_OUTLINE_ARGS: dict[str, Any] = {
    "work_units": [
        {"id": "wu-1", "task": "do the thing"},
    ],
    "rationale": "minimal viable outline",
}


class _RecordingSupervisor(xo.Actor):
    """Supervisor double that records both outline_ready and prompt_error."""

    async def __post_create__(self) -> None:
        self._outlines: list[SubmitOutlinePayload] = []
        self._errors: list[PromptError] = []

    async def outline_ready(self, payload: SubmitOutlinePayload) -> None:
        self._outlines.append(payload)

    async def prompt_error(self, error: PromptError) -> None:
        self._errors.append(error)

    # Required by decomposer's on_tool_call when it forwards typed payloads.
    async def detail_ready(self, payload: Any) -> None:  # pragma: no cover
        pass

    async def fix_ready(self, payload: Any) -> None:  # pragma: no cover
        pass

    async def payload_parse_error(self, tool: str, message: str) -> None:  # pragma: no cover
        pass

    async def outlines(self) -> list[SubmitOutlinePayload]:
        return list(self._outlines)

    async def errors(self) -> list[PromptError]:
        return list(self._errors)


async def _make_decomposer(pool_address: str, supervisor: xo.ActorRef, uid: str) -> Any:
    return await xo.create_actor(
        DecomposerActor,
        supervisor,
        cwd="/tmp",
        config=None,
        role="primary",
        address=pool_address,
        uid=uid,
    )


@pytest.mark.asyncio
async def test_send_outline_no_nudge_when_tool_fires(pool_address: str) -> None:
    """Happy path: tool fires during the prompt → no nudge, no extra prompt."""
    supervisor = await xo.create_actor(
        _RecordingSupervisor, address=pool_address, uid="nudge-sup-happy"
    )
    decomposer = await _make_decomposer(pool_address, supervisor, "decomp-nudge-happy")
    nudge_calls: list[Any] = []

    async def _prompt_with_tool_call(self: DecomposerActor, request: Any) -> None:
        # Simulate the agent calling submit_outline during its turn by
        # invoking on_tool_call directly — same path the gateway would use.
        await self.on_tool_call("submit_outline", _VALID_OUTLINE_ARGS)

    async def _record_nudge(self: DecomposerActor, request: Any) -> None:
        nudge_calls.append(request)

    try:
        with (
            patch.object(DecomposerActor, "_send_outline_prompt", new=_prompt_with_tool_call),
            patch.object(DecomposerActor, "_send_nudge_prompt", new=_record_nudge),
            patch.object(DecomposerActor, "_end_turn", new=_noop_end_turn),
        ):
            await decomposer.send_outline(OutlineRequest(flight_plan_content="plan"))

        outlines = await supervisor.outlines()
        errors = await supervisor.errors()
        assert len(outlines) == 1
        assert errors == []
        assert nudge_calls == []
    finally:
        await xo.destroy_actor(decomposer)
        await xo.destroy_actor(supervisor)


@pytest.mark.asyncio
async def test_send_outline_nudges_when_tool_skipped_then_succeeds(
    pool_address: str,
) -> None:
    """Recovery: first prompt is silent → actor nudges → nudge fires the tool."""
    supervisor = await xo.create_actor(
        _RecordingSupervisor, address=pool_address, uid="nudge-sup-recover"
    )
    decomposer = await _make_decomposer(pool_address, supervisor, "decomp-nudge-recover")
    nudge_calls: list[Any] = []

    async def _silent_prompt(self: DecomposerActor, request: Any) -> None:
        # Agent yapped but never called submit_outline.
        return None

    async def _nudge_calls_tool(self: DecomposerActor, request: Any) -> None:
        nudge_calls.append(request)
        await self.on_tool_call("submit_outline", _VALID_OUTLINE_ARGS)

    try:
        with (
            patch.object(DecomposerActor, "_send_outline_prompt", new=_silent_prompt),
            patch.object(DecomposerActor, "_send_nudge_prompt", new=_nudge_calls_tool),
            patch.object(DecomposerActor, "_end_turn", new=_noop_end_turn),
        ):
            await decomposer.send_outline(OutlineRequest(flight_plan_content="plan"))

        outlines = await supervisor.outlines()
        errors = await supervisor.errors()
        assert len(outlines) == 1
        assert errors == []
        assert len(nudge_calls) == 1
        assert nudge_calls[0].expected_tool == "submit_outline"
    finally:
        await xo.destroy_actor(decomposer)
        await xo.destroy_actor(supervisor)


@pytest.mark.asyncio
async def test_send_outline_reports_prompt_error_when_nudge_also_skipped(
    pool_address: str,
) -> None:
    """Exhaustion: both prompts skip the tool → single PromptError, no outline."""
    supervisor = await xo.create_actor(
        _RecordingSupervisor, address=pool_address, uid="nudge-sup-exhaust"
    )
    decomposer = await _make_decomposer(pool_address, supervisor, "decomp-nudge-exhaust")
    nudge_calls: list[Any] = []

    async def _silent_prompt(self: DecomposerActor, request: Any) -> None:
        return None

    async def _silent_nudge(self: DecomposerActor, request: Any) -> None:
        nudge_calls.append(request)

    try:
        with (
            patch.object(DecomposerActor, "_send_outline_prompt", new=_silent_prompt),
            patch.object(DecomposerActor, "_send_nudge_prompt", new=_silent_nudge),
            patch.object(DecomposerActor, "_end_turn", new=_noop_end_turn),
        ):
            await decomposer.send_outline(OutlineRequest(flight_plan_content="plan"))

        outlines = await supervisor.outlines()
        errors = await supervisor.errors()
        assert outlines == []
        assert len(errors) == 1
        assert errors[0].phase == "outline"
        assert "submit_outline" in errors[0].error
        assert "two turns" in errors[0].error
        # Nudge was attempted exactly once, not retried.
        assert len(nudge_calls) == 1
    finally:
        await xo.destroy_actor(decomposer)
        await xo.destroy_actor(supervisor)


async def _noop_end_turn(self: DecomposerActor) -> None:
    """Stand-in for ``_end_turn`` — there's no real ACP session in these tests."""
    return None
