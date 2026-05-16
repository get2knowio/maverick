"""Tests for BriefingActor (airframe-stub injection path).

Confirms:

* ``send_briefing`` runs through the agent and forwards the typed
  payload to the supervisor's named ``forward_method``.
* The result schema is looked up by ``mcp_tool`` (legacy tool name) at
  construction time.
* Airframe runtime errors route through ``prompt_error``.
* Constructor validates required ``cwd`` / ``mcp_tool`` /
  ``forward_method``.

Uses :class:`StubBriefingAgent` as the ``agent=`` injection — no
OpenCode handle, no SDK adapter, no HTTP transport.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
import xoscar as xo
from airframe.errors import RuntimeAuthError

from maverick.actors.xoscar.briefing import BriefingActor
from maverick.actors.xoscar.messages import BriefingRequest, PromptError
from maverick.actors.xoscar.pool import create_pool
from maverick.payloads import SubmitNavigatorBriefPayload
from tests.unit.agents.airframe_stubs import StubBriefingAgent


class _BriefingRecorder(xo.Actor):
    async def __post_create__(self) -> None:
        self._calls: list[tuple[str, Any]] = []

    @xo.no_lock
    async def navigator_brief_ready(self, payload: SubmitNavigatorBriefPayload) -> None:
        self._calls.append(("navigator_brief_ready", payload))

    @xo.no_lock
    async def payload_parse_error(self, tool: str, message: str) -> None:
        self._calls.append(("payload_parse_error", (tool, message)))

    @xo.no_lock
    async def prompt_error(self, error: PromptError) -> None:
        self._calls.append(
            (
                "prompt_error",
                {"phase": error.phase, "error": error.error, "unit_id": error.unit_id},
            )
        )

    async def calls(self) -> list[tuple[str, Any]]:
        return list(self._calls)


@pytest.fixture
async def pool_address() -> AsyncIterator[str]:
    """Torn-down-on-exit xoscar pool; no OpenCode handle registration."""
    pool, address = await create_pool()
    try:
        yield address
    finally:
        await pool.stop()


def _navigator_payload() -> SubmitNavigatorBriefPayload:
    return SubmitNavigatorBriefPayload(
        architecture_decisions=(
            {"title": "use x", "decision": "use x", "rationale": "it works"},
        ),
        module_structure="module a -> module b",
        integration_points=("mcp", "acp"),
        summary="do x then y",
    )


async def test_briefing_forwards_to_named_supervisor_method(pool_address: str) -> None:
    """Typed payload reaches the supervisor's per-agent forward method."""
    sup = await xo.create_actor(_BriefingRecorder, address=pool_address, uid="brief-sup")
    payload = _navigator_payload()
    briefing_agent = StubBriefingAgent(
        agent_name="navigator",
        result_model=SubmitNavigatorBriefPayload,
        brief_payloads=[payload],
    )
    briefing = await xo.create_actor(
        BriefingActor,
        sup,
        agent_name="navigator",
        mcp_tool="submit_navigator_brief",
        forward_method="navigator_brief_ready",
        cwd="/tmp",
        agent=briefing_agent,
        address=pool_address,
        uid="briefing-navigator",
    )
    try:
        await briefing.send_briefing(BriefingRequest(agent_name="navigator", prompt="brief x"))
        calls = await sup.calls()
        assert len(calls) == 1
        kind, delivered = calls[0]
        assert kind == "navigator_brief_ready"
        assert isinstance(delivered, SubmitNavigatorBriefPayload)
        # The stub saw the prompt verbatim.
        assert briefing_agent.calls == [("brief", {"prompt": "brief x"})]
    finally:
        await xo.destroy_actor(briefing)
        await xo.destroy_actor(sup)


async def test_briefing_routes_send_error_to_prompt_error(pool_address: str) -> None:
    """Airframe RuntimeAuthError surfaces as a classified PromptError."""
    sup = await xo.create_actor(_BriefingRecorder, address=pool_address, uid="brief-sup-err")
    briefing_agent = StubBriefingAgent(
        agent_name="navigator", result_model=SubmitNavigatorBriefPayload
    )
    briefing_agent.raise_error = RuntimeAuthError("bad key")
    briefing = await xo.create_actor(
        BriefingActor,
        sup,
        agent_name="navigator",
        mcp_tool="submit_navigator_brief",
        forward_method="navigator_brief_ready",
        cwd="/tmp",
        agent=briefing_agent,
        address=pool_address,
        uid="briefing-err",
    )
    try:
        await briefing.send_briefing(BriefingRequest(agent_name="navigator", prompt="x"))
        calls = await sup.calls()
        kinds = [k for k, _ in calls]
        assert kinds == ["prompt_error"]
        err = calls[0][1]
        assert err["phase"] == "briefing"
        assert err["unit_id"] == "navigator"
    finally:
        await xo.destroy_actor(briefing)
        await xo.destroy_actor(sup)


async def test_briefing_constructor_validates_required_fields(pool_address: str) -> None:
    """Cwd / mcp_tool / forward_method / known-tool — all validated."""
    sup = await xo.create_actor(_BriefingRecorder, address=pool_address, uid="brief-sup-v")
    try:
        for bad_kwargs in (
            {"cwd": "", "mcp_tool": "submit_navigator_brief", "forward_method": "y"},
            {"cwd": "/tmp", "mcp_tool": "", "forward_method": "y"},
            {"cwd": "/tmp", "mcp_tool": "submit_navigator_brief", "forward_method": ""},
        ):
            with pytest.raises(ValueError):
                await xo.create_actor(
                    BriefingActor,
                    sup,
                    agent_name="navigator",
                    address=pool_address,
                    uid=f"briefing-bad-{hash(tuple(bad_kwargs.items()))}",
                    **bad_kwargs,
                )
        # Unknown tool name → ValueError too.
        with pytest.raises(ValueError, match="unknown payload tool"):
            await xo.create_actor(
                BriefingActor,
                sup,
                agent_name="navigator",
                cwd="/tmp",
                mcp_tool="submit_does_not_exist",
                forward_method="x",
                address=pool_address,
                uid="briefing-unknown-tool",
            )
    finally:
        await xo.destroy_actor(sup)
