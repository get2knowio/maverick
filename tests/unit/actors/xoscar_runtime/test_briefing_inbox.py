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
    supervisor = await xo.create_actor(_BriefingRecorder, address=pool_address, uid="brief-sup")
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
    supervisor = await xo.create_actor(_BriefingRecorder, address=pool_address, uid="brief-sup-r")
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
    supervisor = await xo.create_actor(_BriefingRecorder, address=pool_address, uid="brief-sup-v")
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


# ---------------------------------------------------------------------------
# JSON-in-text fallback — recovers when the agent skipped the MCP tool but
# emitted the payload as inline JSON. Mirrors the reviewer/decomposer wiring
# we ship; without this, Copilot- or Gemini-routed briefings fail because
# their ACP bridges silently drop MCP tool calls.
# ---------------------------------------------------------------------------


def test_send_briefing_passes_json_fallback_to_self_nudge() -> None:
    """The briefing actor wires a ``json_fallback`` into the self-nudge.

    Plain unit test: instantiate ``BriefingActor`` outside the pool,
    stub ``_run_with_self_nudge`` to capture its kwargs, and confirm a
    callable lands on ``json_fallback``. Avoids spinning up the actor
    pool for what is purely a wiring assertion.
    """
    import json
    from unittest.mock import MagicMock

    captured: dict[str, Any] = {}

    async def _capture(**kwargs: Any) -> None:
        captured.update(kwargs)

    actor = BriefingActor.__new__(BriefingActor)
    actor._supervisor_ref = MagicMock()
    actor._agent_name = "scopist"
    actor._mcp_tool = "submit_scope"
    actor._forward_method = "scope_ready"
    actor._cwd = "/tmp"
    actor._step_config = None
    actor._actor_tag = "briefing[scopist:test]"
    actor._run_with_self_nudge = _capture  # type: ignore[method-assign]

    import asyncio

    request = MagicMock()
    asyncio.run(actor.send_briefing(request))

    assert captured["expected_tool"] == "submit_scope"
    assert callable(captured.get("json_fallback")), (
        "send_briefing must pass json_fallback so Copilot/Gemini misses can "
        "recover via inline JSON"
    )

    # Sanity-check the fallback closure: a payload-shaped JSON returns True
    # and forwards to the supervisor's named method; non-matching JSON
    # returns False without forwarding.
    fallback = captured["json_fallback"]
    forwarded: list[Any] = []

    async def _scope_ready(payload: Any) -> None:
        forwarded.append(payload)

    actor._supervisor_ref.scope_ready = _scope_ready

    valid = json.dumps(
        {
            "in_scope": ["src/foo.py"],
            "out_scope": [],
            "boundaries": [],
            "summary": "x",
            "scope_rationale": "y",
        }
    )
    assert asyncio.run(fallback(valid)) is True
    assert len(forwarded) == 1

    # Garbage doesn't validate → no forward.
    forwarded.clear()
    assert asyncio.run(fallback("just thinking out loud, no JSON here")) is False
    assert forwarded == []


def test_send_briefing_fallback_unwraps_tool_call_envelope() -> None:
    """``{"name": "<tool>", "arguments": {...}}`` envelope unwraps + forwards.

    The unwrap logic lives in ``_unwrap_tool_call_envelope`` (used by
    ``try_parse_tool_payload_from_text``). This confirms the briefing
    fallback inherits it — important because Copilot-style models tend
    to emit tool calls as JSON envelopes when they think they're calling
    a tool but are actually outputting text.
    """
    import asyncio
    import json
    from unittest.mock import MagicMock

    captured: dict[str, Any] = {}

    async def _capture(**kwargs: Any) -> None:
        captured.update(kwargs)

    actor = BriefingActor.__new__(BriefingActor)
    actor._supervisor_ref = MagicMock()
    actor._agent_name = "scopist"
    actor._mcp_tool = "submit_scope"
    actor._forward_method = "scope_ready"
    actor._cwd = "/tmp"
    actor._step_config = None
    actor._actor_tag = "briefing[scopist:test]"
    actor._run_with_self_nudge = _capture  # type: ignore[method-assign]

    asyncio.run(actor.send_briefing(MagicMock()))
    fallback = captured["json_fallback"]

    forwarded: list[Any] = []

    async def _scope_ready(payload: Any) -> None:
        forwarded.append(payload)

    actor._supervisor_ref.scope_ready = _scope_ready

    enveloped = json.dumps(
        {
            "name": "submit_scope",
            "arguments": {
                "in_scope": ["src/x.py"],
                "out_scope": [],
                "boundaries": [],
                "summary": "x",
                "scope_rationale": "y",
            },
        }
    )
    assert asyncio.run(fallback(enveloped)) is True
    assert len(forwarded) == 1


def test_send_briefing_fallback_returns_false_when_supervisor_method_missing() -> None:
    """Malformed wiring (forward_method names a nonexistent method) is a
    silent False rather than a crash, so the failure path stays clean."""
    import asyncio
    import json
    from unittest.mock import MagicMock

    captured: dict[str, Any] = {}

    async def _capture(**kwargs: Any) -> None:
        captured.update(kwargs)

    actor = BriefingActor.__new__(BriefingActor)
    actor._supervisor_ref = MagicMock(spec=[])  # no attributes at all
    actor._agent_name = "scopist"
    actor._mcp_tool = "submit_scope"
    actor._forward_method = "nonexistent_method"
    actor._cwd = "/tmp"
    actor._step_config = None
    actor._actor_tag = "briefing[scopist:test]"
    actor._run_with_self_nudge = _capture  # type: ignore[method-assign]

    asyncio.run(actor.send_briefing(MagicMock()))
    fallback = captured["json_fallback"]

    valid = json.dumps(
        {
            "in_scope": ["src/x.py"],
            "out_scope": [],
            "boundaries": [],
            "summary": "x",
            "scope_rationale": "y",
        }
    )
    assert asyncio.run(fallback(valid)) is False
