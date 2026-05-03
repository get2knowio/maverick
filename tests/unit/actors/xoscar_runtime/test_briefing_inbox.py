"""Tests for BriefingActor under the OpenCode runtime.

Confirms:

* ``send_briefing`` runs a structured prompt and forwards the typed
  payload to the supervisor's named ``forward_method``.
* The result schema is looked up by ``mcp_tool`` (legacy tool name) at
  construction time.
* OpenCode runtime errors route through ``prompt_error``.
* Constructor validates required ``cwd`` / ``mcp_tool`` /
  ``forward_method``.
"""

from __future__ import annotations

from typing import Any

import pytest
import xoscar as xo

from maverick.actors.xoscar.briefing import BriefingActor
from maverick.actors.xoscar.messages import BriefingRequest, PromptError
from maverick.payloads import SubmitNavigatorBriefPayload
from maverick.runtime.opencode import (
    OpenCodeAuthError,
    SendResult,
)


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


class _StubBriefing(BriefingActor):
    """BriefingActor with the OpenCode client replaced by a scripted stub."""

    provider_tier = None  # type: ignore[assignment]

    def __init__(
        self,
        supervisor_ref: xo.ActorRef,
        *,
        agent_name: str,
        mcp_tool: str,
        forward_method: str,
        cwd: str = "/tmp",
        scripted_payload: dict | None = None,
        scripted_error: BaseException | None = None,
    ) -> None:
        super().__init__(
            supervisor_ref,
            agent_name=agent_name,
            mcp_tool=mcp_tool,
            forward_method=forward_method,
            cwd=cwd,
        )
        self._scripted_payload = scripted_payload
        self._scripted_error = scripted_error

    async def _build_client(self) -> Any:  # type: ignore[override]
        scripted_payload = self._scripted_payload
        scripted_error = self._scripted_error

        class _Client:
            base_url = "http://stub"

            async def list_providers(self) -> dict[str, Any]:
                return {"all": [], "connected": []}

            async def create_session(self, *, title: str | None = None, **_: Any) -> str:
                return "ses_brief"

            async def delete_session(self, session_id: str) -> bool:
                return True

            async def send_with_event_watch(self, *args: Any, **kwargs: Any) -> SendResult:
                if scripted_error is not None:
                    raise scripted_error
                payload = scripted_payload
                return SendResult(
                    message={"info": {"structured": payload}, "parts": []},
                    text="",
                    structured=payload,
                    valid=True,
                    info={},
                )

            async def aclose(self) -> None:
                return None

        return _Client()


@pytest.mark.asyncio
async def test_briefing_forwards_to_named_supervisor_method(pool_address: str) -> None:
    sup = await xo.create_actor(_BriefingRecorder, address=pool_address, uid="brief-sup")
    payload = {
        "architecture_decisions": [
            {"title": "use x", "decision": "use x", "rationale": "it works"}
        ],
        "module_structure": "module a -> module b",
        "integration_points": ["mcp", "acp"],
        "summary": "do x then y",
    }
    briefing = await xo.create_actor(
        _StubBriefing,
        sup,
        agent_name="navigator",
        mcp_tool="submit_navigator_brief",
        forward_method="navigator_brief_ready",
        cwd="/tmp",
        scripted_payload=payload,
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
    finally:
        await xo.destroy_actor(briefing)
        await xo.destroy_actor(sup)


@pytest.mark.asyncio
async def test_briefing_routes_send_error_to_prompt_error(pool_address: str) -> None:
    sup = await xo.create_actor(_BriefingRecorder, address=pool_address, uid="brief-sup-err")
    briefing = await xo.create_actor(
        _StubBriefing,
        sup,
        agent_name="navigator",
        mcp_tool="submit_navigator_brief",
        forward_method="navigator_brief_ready",
        cwd="/tmp",
        scripted_error=OpenCodeAuthError("bad key"),
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


@pytest.mark.asyncio
async def test_briefing_constructor_validates_required_fields(pool_address: str) -> None:
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
