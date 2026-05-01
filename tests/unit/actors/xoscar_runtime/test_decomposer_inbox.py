"""Tests for DecomposerActor under the OpenCode runtime.

Covers the three phases (outline / detail / fix) plus the nudge path,
error routing through ``prompt_error``, and session-mode rotation.
"""

from __future__ import annotations

from typing import Any

import xoscar as xo

from maverick.actors.xoscar.decomposer import DecomposerActor
from maverick.actors.xoscar.messages import (
    DetailRequest,
    FixRequest,
    NudgeRequest,
    OutlineRequest,
    PromptError,
)
from maverick.payloads import (
    SubmitDetailsPayload,
    SubmitFixPayload,
    SubmitOutlinePayload,
)
from maverick.runtime.opencode import OpenCodeAuthError, SendResult


class _DecomposerRecorder(xo.Actor):
    async def __post_create__(self) -> None:
        self._calls: list[tuple[str, Any]] = []

    @xo.no_lock
    async def outline_ready(self, payload: SubmitOutlinePayload) -> None:
        self._calls.append(("outline_ready", payload))

    @xo.no_lock
    async def detail_ready(self, payload: SubmitDetailsPayload) -> None:
        self._calls.append(("detail_ready", payload))

    @xo.no_lock
    async def fix_ready(self, payload: SubmitFixPayload) -> None:
        self._calls.append(("fix_ready", payload))

    @xo.no_lock
    async def payload_parse_error(self, tool: str, message: str) -> None:
        self._calls.append(("payload_parse_error", (tool, message)))

    @xo.no_lock
    async def prompt_error(self, error: PromptError) -> None:
        self._calls.append(("prompt_error", error))

    async def calls(self) -> list[tuple[str, Any]]:
        return list(self._calls)


class _StubDecomposer(DecomposerActor):
    """Decomposer with a scripted client. ``send_results`` is consumed FIFO;
    ``send_error`` short-circuits with the named exception."""

    provider_tier = None  # type: ignore[assignment]

    def __init__(
        self,
        supervisor_ref: xo.ActorRef,
        *,
        cwd: str = "/tmp",
        send_results: list[SendResult] | None = None,
        send_error: BaseException | None = None,
        role: str = "primary",
    ) -> None:
        super().__init__(supervisor_ref, cwd=cwd, role=role)
        self._scripted_results = list(send_results or [])
        self._scripted_error = send_error

    async def _build_client(self) -> Any:  # type: ignore[override]
        scripted_results = self._scripted_results
        scripted_error = self._scripted_error

        class _Client:
            base_url = "http://stub"

            async def list_providers(self) -> dict[str, Any]:
                return {"all": [], "connected": []}

            async def create_session(self, *, title: str | None = None, **_: Any) -> str:
                return f"ses_{id(self)}"

            async def delete_session(self, session_id: str) -> bool:
                return True

            async def send_with_event_watch(self, *args: Any, **kwargs: Any) -> SendResult:
                if scripted_error is not None:
                    raise scripted_error
                if not scripted_results:
                    return SendResult(message={}, text="", structured=None, valid=False)
                return scripted_results.pop(0)

            async def aclose(self) -> None:
                return None

        return _Client()


def _structured(payload: dict[str, Any]) -> SendResult:
    return SendResult(
        message={"info": {"structured": payload}, "parts": []},
        text="",
        structured=payload,
        valid=True,
        info={},
    )


# ---------------------------------------------------------------------------
# Outline / detail / fix happy paths
# ---------------------------------------------------------------------------


def _empty_context() -> Any:
    """Build an empty CodebaseContext suitable for prompt-building."""
    from maverick.library.actions.decompose import CodebaseContext

    return CodebaseContext(files=(), missing_files=(), total_size=0)


async def test_outline_forwards_to_supervisor(pool_address: str) -> None:
    sup = await xo.create_actor(_DecomposerRecorder, address=pool_address, uid="dec-sup-1")
    payload = {"work_units": []}
    dec = await xo.create_actor(
        _StubDecomposer,
        sup,
        cwd="/tmp",
        send_results=[_structured(payload)],
        address=pool_address,
        uid="dec-1",
    )
    try:
        await dec.send_outline(
            OutlineRequest(flight_plan_content="plan", codebase_context=_empty_context())
        )
        calls = await sup.calls()
        kinds = [k for k, _ in calls]
        assert kinds == ["outline_ready"]
    finally:
        await xo.destroy_actor(dec)
        await xo.destroy_actor(sup)


async def test_detail_forwards_to_supervisor(pool_address: str) -> None:
    sup = await xo.create_actor(_DecomposerRecorder, address=pool_address, uid="dec-sup-2")
    payload = {
        "details": [
            {
                "id": "wu-1",
                "instructions": "do x",
                "files": [],
            }
        ]
    }
    dec = await xo.create_actor(
        _StubDecomposer,
        sup,
        cwd="/tmp",
        role="pool",
        send_results=[_structured(payload)],
        address=pool_address,
        uid="dec-2",
    )
    try:
        await dec.send_detail(DetailRequest(unit_ids=("wu-1",)))
        calls = await sup.calls()
        assert [k for k, _ in calls] == ["detail_ready"]
    finally:
        await xo.destroy_actor(dec)
        await xo.destroy_actor(sup)


async def test_fix_forwards_to_supervisor(pool_address: str) -> None:
    sup = await xo.create_actor(_DecomposerRecorder, address=pool_address, uid="dec-sup-3")
    payload = {"work_units": [], "details": []}
    dec = await xo.create_actor(
        _StubDecomposer,
        sup,
        cwd="/tmp",
        send_results=[_structured(payload)],
        address=pool_address,
        uid="dec-3",
    )
    try:
        await dec.send_fix(FixRequest())
        calls = await sup.calls()
        assert [k for k, _ in calls] == ["fix_ready"]
    finally:
        await xo.destroy_actor(dec)
        await xo.destroy_actor(sup)


# ---------------------------------------------------------------------------
# Error routing
# ---------------------------------------------------------------------------


async def test_outline_failure_routes_to_prompt_error(pool_address: str) -> None:
    sup = await xo.create_actor(_DecomposerRecorder, address=pool_address, uid="dec-sup-4")
    dec = await xo.create_actor(
        _StubDecomposer,
        sup,
        cwd="/tmp",
        send_error=OpenCodeAuthError("bad key"),
        address=pool_address,
        uid="dec-4",
    )
    try:
        await dec.send_outline(
            OutlineRequest(flight_plan_content="plan", codebase_context=_empty_context())
        )
        calls = await sup.calls()
        kinds = [k for k, _ in calls]
        assert kinds == ["prompt_error"]
        err: PromptError = calls[0][1]
        assert err.phase == "outline"
        assert "bad key" in err.error
    finally:
        await xo.destroy_actor(dec)
        await xo.destroy_actor(sup)


async def test_detail_failure_includes_unit_id(pool_address: str) -> None:
    sup = await xo.create_actor(_DecomposerRecorder, address=pool_address, uid="dec-sup-5")
    dec = await xo.create_actor(
        _StubDecomposer,
        sup,
        cwd="/tmp",
        role="pool",
        send_error=OpenCodeAuthError("auth"),
        address=pool_address,
        uid="dec-5",
    )
    try:
        await dec.send_detail(DetailRequest(unit_ids=("wu-3",)))
        calls = await sup.calls()
        kinds = [k for k, _ in calls]
        assert kinds == ["prompt_error"]
        err: PromptError = calls[0][1]
        assert err.phase == "detail"
        assert err.unit_id == "wu-3"
    finally:
        await xo.destroy_actor(dec)
        await xo.destroy_actor(sup)


# ---------------------------------------------------------------------------
# Nudge
# ---------------------------------------------------------------------------


async def test_nudge_dispatches_by_expected_tool(pool_address: str) -> None:
    sup = await xo.create_actor(_DecomposerRecorder, address=pool_address, uid="dec-sup-6")
    payload = {"details": [{"id": "wu-7", "instructions": "do x", "files": []}]}
    dec = await xo.create_actor(
        _StubDecomposer,
        sup,
        cwd="/tmp",
        send_results=[_structured(payload)],
        address=pool_address,
        uid="dec-6",
    )
    try:
        await dec.send_nudge(
            NudgeRequest(expected_tool="submit_details", unit_id="wu-7", reason="retry")
        )
        calls = await sup.calls()
        assert [k for k, _ in calls] == ["detail_ready"]
    finally:
        await xo.destroy_actor(dec)
        await xo.destroy_actor(sup)
