"""Tests for ``DecomposerActor.on_tool_call`` — the MCP inbox surface.

Validates Design Decision #3: each agent owns its own MCP inbox,
parses only the tools it advertises, and forwards typed results to
the supervisor via in-pool RPC.
"""

from __future__ import annotations

from typing import Any

import pytest
import xoscar as xo

from maverick.actors.xoscar.decomposer import DecomposerActor
from maverick.tools.supervisor_inbox.models import (
    SubmitDetailsPayload,
    SubmitFixPayload,
    SubmitOutlinePayload,
)


class _StubSupervisor(xo.Actor):
    """Records every typed domain call the decomposer forwards."""

    async def __post_create__(self) -> None:
        self._calls: list[tuple[str, Any]] = []

    async def outline_ready(self, payload: SubmitOutlinePayload) -> None:
        self._calls.append(("outline_ready", payload))

    async def detail_ready(self, payload: SubmitDetailsPayload) -> None:
        self._calls.append(("detail_ready", payload))

    async def fix_ready(self, payload: SubmitFixPayload) -> None:
        self._calls.append(("fix_ready", payload))

    async def prompt_error(self, error: Any) -> None:
        self._calls.append(("prompt_error", error))

    async def payload_parse_error(self, tool: str, message: str) -> None:
        self._calls.append(("payload_parse_error", (tool, message)))

    async def calls(self) -> list[tuple[str, Any]]:
        return list(self._calls)


async def _build(pool_address: str, role: str = "primary") -> tuple[xo.ActorRef, xo.ActorRef]:
    supervisor = await xo.create_actor(
        _StubSupervisor, address=pool_address, uid=f"supervisor-{role}"
    )
    decomposer = await xo.create_actor(
        DecomposerActor,
        supervisor,
        cwd="/tmp",
        config=None,
        role=role,
        address=pool_address,
        uid=f"decomposer-{role}",
    )
    return supervisor, decomposer


@pytest.mark.asyncio
async def test_submit_outline_forwards_to_supervisor(pool_address: str) -> None:
    supervisor, decomposer = await _build(pool_address, role="primary")
    try:
        args = {
            "work_units": [
                {"id": "wu-1", "task": "Do a"},
                {"id": "wu-2", "task": "Do b"},
            ],
            "rationale": "split a and b",
        }
        result = await decomposer.on_tool_call("submit_outline", args)
        assert result == "ok"

        calls = await supervisor.calls()
        assert len(calls) == 1
        kind, payload = calls[0]
        assert kind == "outline_ready"
        assert isinstance(payload, SubmitOutlinePayload)
        assert [wu.id for wu in payload.work_units] == ["wu-1", "wu-2"]
    finally:
        await xo.destroy_actor(decomposer)
        await xo.destroy_actor(supervisor)


@pytest.mark.asyncio
async def test_submit_details_forwards_to_supervisor(pool_address: str) -> None:
    supervisor, decomposer = await _build(pool_address, role="pool")
    try:
        args = {
            "details": [
                {
                    "id": "wu-1",
                    "instructions": "Write code",
                    "acceptance_criteria": [{"text": "Works", "trace_ref": "AC-001"}],
                    "verification": ["unit test"],
                }
            ]
        }
        result = await decomposer.on_tool_call("submit_details", args)
        assert result == "ok"

        calls = await supervisor.calls()
        assert len(calls) == 1
        kind, payload = calls[0]
        assert kind == "detail_ready"
        assert isinstance(payload, SubmitDetailsPayload)
        assert [d.id for d in payload.details] == ["wu-1"]
    finally:
        await xo.destroy_actor(decomposer)
        await xo.destroy_actor(supervisor)


@pytest.mark.asyncio
async def test_submit_fix_forwards_to_supervisor(pool_address: str) -> None:
    supervisor, decomposer = await _build(pool_address, role="primary")
    try:
        args = {
            "work_units": [{"id": "wu-1", "task": "Do a"}],
            "details": [
                {
                    "id": "wu-1",
                    "instructions": "Fixed",
                    "acceptance_criteria": [{"text": "OK", "trace_ref": "AC-001"}],
                    "verification": ["unit test"],
                }
            ],
        }
        result = await decomposer.on_tool_call("submit_fix", args)
        assert result == "ok"

        calls = await supervisor.calls()
        assert len(calls) == 1
        kind, payload = calls[0]
        assert kind == "fix_ready"
        assert isinstance(payload, SubmitFixPayload)
    finally:
        await xo.destroy_actor(decomposer)
        await xo.destroy_actor(supervisor)


@pytest.mark.asyncio
async def test_invalid_payload_is_reported(pool_address: str) -> None:
    supervisor, decomposer = await _build(pool_address, role="primary")
    try:
        # Missing required "work_units" field
        result = await decomposer.on_tool_call("submit_outline", {"rationale": "oops"})
        assert result == "error"

        calls = await supervisor.calls()
        assert len(calls) == 1
        kind, detail = calls[0]
        assert kind == "payload_parse_error"
        tool, message = detail
        assert tool == "submit_outline"
        assert message  # non-empty reason string
    finally:
        await xo.destroy_actor(decomposer)
        await xo.destroy_actor(supervisor)


@pytest.mark.asyncio
async def test_unknown_tool_is_reported(pool_address: str) -> None:
    supervisor, decomposer = await _build(pool_address, role="primary")
    try:
        # submit_review is a real tool elsewhere, but the decomposer
        # does not own it — expect an error report to the supervisor.
        result = await decomposer.on_tool_call("submit_review", {"approved": True, "findings": []})
        assert result == "error"

        calls = await supervisor.calls()
        assert len(calls) == 1
        kind, detail = calls[0]
        # The parser raises for a tool-name it doesn't know, which
        # lands in the parse_error branch.
        assert kind == "payload_parse_error"
        tool, _message = detail
        assert tool == "submit_review"
    finally:
        await xo.destroy_actor(decomposer)
        await xo.destroy_actor(supervisor)
