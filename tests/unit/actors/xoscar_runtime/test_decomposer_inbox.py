"""Tests for DecomposerActor (airframe-stub injection path).

Covers the three phases (outline / detail / fix) plus the nudge path,
error routing through ``prompt_error``. Uses :class:`StubDecomposerAgent`
as the ``agent=`` injection — no real adapter SDK, no HTTP transport.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
import xoscar as xo
from airframe.errors import RuntimeAuthError

from maverick.actors.xoscar.decomposer import DecomposerActor
from maverick.actors.xoscar.messages import (
    DetailRequest,
    FixRequest,
    NudgeRequest,
    OutlineRequest,
    PromptError,
)
from maverick.actors.xoscar.pool import create_pool
from maverick.payloads import (
    SubmitDetailsPayload,
    SubmitFixPayload,
    SubmitOutlinePayload,
)
from tests.unit.agents.airframe_stubs import StubDecomposerAgent


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


@pytest.fixture
async def pool_address() -> AsyncIterator[str]:
    """Torn-down-on-exit xoscar pool; no runtime registration."""
    pool, address = await create_pool()
    try:
        yield address
    finally:
        await pool.stop()


def _empty_context() -> Any:
    """Build an empty CodebaseContext suitable for prompt-building."""
    from maverick.library.actions.decompose import CodebaseContext

    return CodebaseContext(files=(), missing_files=(), total_size=0)


# ---------------------------------------------------------------------------
# Outline / detail / fix happy paths
# ---------------------------------------------------------------------------


async def test_outline_forwards_to_supervisor(pool_address: str) -> None:
    sup = await xo.create_actor(_DecomposerRecorder, address=pool_address, uid="dec-sup-1")
    payload = SubmitOutlinePayload(work_units=())
    decomposer_agent = StubDecomposerAgent(outline_payloads=[payload])
    dec = await xo.create_actor(
        DecomposerActor,
        sup,
        cwd="/tmp",
        agent=decomposer_agent,
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
        # Actor forwarded the kwargs verbatim to the agent.
        agent_call = decomposer_agent.calls[0]
        assert agent_call[0] == "outline"
        assert agent_call[1]["flight_plan_content"] == "plan"
    finally:
        await xo.destroy_actor(dec)
        await xo.destroy_actor(sup)


async def test_detail_forwards_to_supervisor(pool_address: str) -> None:
    sup = await xo.create_actor(_DecomposerRecorder, address=pool_address, uid="dec-sup-2")
    payload = SubmitDetailsPayload(details=())
    decomposer_agent = StubDecomposerAgent(detail_payloads=[payload])
    dec = await xo.create_actor(
        DecomposerActor,
        sup,
        cwd="/tmp",
        role="pool",
        agent=decomposer_agent,
        address=pool_address,
        uid="dec-2",
    )
    try:
        await dec.send_detail(DetailRequest(unit_ids=("wu-1",)))
        calls = await sup.calls()
        assert [k for k, _ in calls] == ["detail_ready"]
        assert decomposer_agent.calls[0][1]["unit_ids"] == ("wu-1",)
    finally:
        await xo.destroy_actor(dec)
        await xo.destroy_actor(sup)


async def test_fix_forwards_to_supervisor(pool_address: str) -> None:
    sup = await xo.create_actor(_DecomposerRecorder, address=pool_address, uid="dec-sup-3")
    payload = SubmitFixPayload(work_units=(), details=())
    decomposer_agent = StubDecomposerAgent(fix_payloads=[payload])
    dec = await xo.create_actor(
        DecomposerActor,
        sup,
        cwd="/tmp",
        agent=decomposer_agent,
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
    decomposer_agent = StubDecomposerAgent()
    decomposer_agent.raise_error = RuntimeAuthError("bad key")
    dec = await xo.create_actor(
        DecomposerActor,
        sup,
        cwd="/tmp",
        agent=decomposer_agent,
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
    decomposer_agent = StubDecomposerAgent()
    decomposer_agent.raise_error = RuntimeAuthError("auth")
    dec = await xo.create_actor(
        DecomposerActor,
        sup,
        cwd="/tmp",
        role="pool",
        agent=decomposer_agent,
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
    """Nudge payload typed as ``SubmitDetailsPayload`` lands on detail_ready."""
    sup = await xo.create_actor(_DecomposerRecorder, address=pool_address, uid="dec-sup-6")
    payload = SubmitDetailsPayload(details=())
    decomposer_agent = StubDecomposerAgent(nudge_payloads=[payload])
    dec = await xo.create_actor(
        DecomposerActor,
        sup,
        cwd="/tmp",
        agent=decomposer_agent,
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
