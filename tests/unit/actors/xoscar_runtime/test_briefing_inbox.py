"""Tests for ``BriefingActor`` — generic briefing agent.

Covers both inbox dispatch (refuel navigator brief → supervisor method)
and parameter validation.
"""

from __future__ import annotations

from typing import Any

import pytest
import xoscar as xo

from maverick.actors.xoscar.briefing import BriefingActor
from maverick.tools.agent_inbox.models import SubmitNavigatorBriefPayload


class _BriefingRecorder(xo.Actor):
    async def __post_create__(self) -> None:
        self._calls: list[tuple[str, Any]] = []

    async def navigator_brief_ready(self, payload: SubmitNavigatorBriefPayload) -> None:
        self._calls.append(("navigator_brief_ready", payload))

    async def payload_parse_error(self, tool: str, message: str) -> None:
        self._calls.append(("payload_parse_error", (tool, message)))

    async def prompt_error(self, error: Any) -> None:
        self._calls.append(("prompt_error", error))

    async def calls(self) -> list[tuple[str, Any]]:
        return list(self._calls)


@pytest.mark.asyncio
async def test_briefing_forwards_to_named_supervisor_method(pool_address: str) -> None:
    supervisor = await xo.create_actor(
        _BriefingRecorder, address=pool_address, uid="brief-sup"
    )
    briefing = await xo.create_actor(
        BriefingActor,
        supervisor,
        agent_name="navigator",
        mcp_tool="submit_navigator_brief",
        forward_method="navigator_brief_ready",
        cwd="/tmp",
        address=pool_address,
        uid="briefing-navigator",
    )
    try:
        args = {
            "architecture_decisions": [
                {"title": "use x", "decision": "use x", "rationale": "it works"}
            ],
            "module_structure": "module a -> module b",
            "integration_points": ["mcp", "acp"],
            "summary": "do x then y",
        }
        result = await briefing.on_tool_call("submit_navigator_brief", args)
        assert result == "ok"
        calls = await supervisor.calls()
        assert len(calls) == 1
        kind, payload = calls[0]
        assert kind == "navigator_brief_ready"
        assert isinstance(payload, SubmitNavigatorBriefPayload)
    finally:
        await xo.destroy_actor(briefing)
        await xo.destroy_actor(supervisor)


@pytest.mark.asyncio
async def test_briefing_rejects_unowned_tool(pool_address: str) -> None:
    supervisor = await xo.create_actor(
        _BriefingRecorder, address=pool_address, uid="brief-sup-r"
    )
    briefing = await xo.create_actor(
        BriefingActor,
        supervisor,
        agent_name="navigator",
        mcp_tool="submit_navigator_brief",
        forward_method="navigator_brief_ready",
        cwd="/tmp",
        address=pool_address,
        uid="briefing-navigator-r",
    )
    try:
        result = await briefing.on_tool_call("submit_scope", {"in_scope": ["a"]})
        assert result == "error"
        calls = await supervisor.calls()
        assert len(calls) == 1
        kind, detail = calls[0]
        assert kind == "payload_parse_error"
        tool, message = detail
        assert tool == "submit_scope"
        assert "submit_navigator_brief" in message
    finally:
        await xo.destroy_actor(briefing)
        await xo.destroy_actor(supervisor)


@pytest.mark.asyncio
async def test_briefing_requires_cwd_mcp_tool_and_forward_method(pool_address: str) -> None:
    supervisor = await xo.create_actor(
        _BriefingRecorder, address=pool_address, uid="brief-sup-v"
    )
    try:
        for bad_kwargs in (
            {"cwd": "", "mcp_tool": "x", "forward_method": "y"},
            {"cwd": "/tmp", "mcp_tool": "", "forward_method": "y"},
            {"cwd": "/tmp", "mcp_tool": "x", "forward_method": ""},
        ):
            with pytest.raises(ValueError):
                await xo.create_actor(
                    BriefingActor,
                    supervisor,
                    agent_name="navigator",
                    address=pool_address,
                    uid=f"briefing-bad-{hash(tuple(bad_kwargs.items()))}",
                    **bad_kwargs,
                )
    finally:
        await xo.destroy_actor(supervisor)
