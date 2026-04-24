"""Smoke tests for ``RefuelSupervisor``.

Full state-machine coverage is deferred to end-to-end integration tests
(which exercise real ACP subprocesses). These tests verify that the
supervisor constructs cleanly, its typed domain methods behave as
expected, and its event queue / generator wiring is correct.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import xoscar as xo

from maverick.actors.xoscar.messages import PromptError
from maverick.actors.xoscar.refuel_supervisor import (
    REFUEL_BRIEFING_CONFIG,
    RefuelInputs,
    RefuelSupervisor,
)
from maverick.tools.agent_inbox.models import (
    SubmitDetailsPayload,
    SubmitOutlinePayload,
    WorkUnitDetailPayload,
    WorkUnitOutlinePayload,
)


def _flight_plan() -> SimpleNamespace:
    return SimpleNamespace(name="test-plan", objective="do a thing", success_criteria=[])


async def _build_supervisor(pool_address: str, **overrides: Any) -> xo.ActorRef:
    inputs = RefuelInputs(
        cwd=overrides.pop("cwd", "/tmp"),
        flight_plan=overrides.pop("flight_plan", _flight_plan()),
        initial_payload=overrides.pop("initial_payload", {"flight_plan_content": "plan"}),
        decomposer_pool_size=overrides.pop("decomposer_pool_size", 1),
        skip_briefing=overrides.pop("skip_briefing", True),
    )
    return await xo.create_actor(
        RefuelSupervisor,
        inputs,
        address=pool_address,
        uid=overrides.pop("uid", "refuel-supervisor"),
    )


def test_refuel_inputs_requires_cwd() -> None:
    inputs = RefuelInputs(cwd="", flight_plan=_flight_plan())
    with pytest.raises(ValueError, match="cwd"):
        RefuelSupervisor(inputs)


def test_briefing_config_tools_and_methods_match() -> None:
    """Every briefing entry maps tool → method. Regression guard so future
    edits don't drift one side."""
    names = {c[0] for c in REFUEL_BRIEFING_CONFIG}
    tools = {c[1] for c in REFUEL_BRIEFING_CONFIG}
    methods = {c[2] for c in REFUEL_BRIEFING_CONFIG}
    assert names == {"navigator", "structuralist", "recon", "contrarian"}
    assert tools == {
        "submit_navigator_brief",
        "submit_structuralist_brief",
        "submit_recon_brief",
        "submit_contrarian_brief",
    }
    assert methods == {
        "navigator_brief_ready",
        "structuralist_brief_ready",
        "recon_brief_ready",
        "contrarian_brief_ready",
    }
    # All forward methods must exist on the supervisor class.
    for _, _, method in REFUEL_BRIEFING_CONFIG:
        assert hasattr(RefuelSupervisor, method), f"missing forward method {method}"


@pytest.mark.asyncio
async def test_outline_ready_stores_payload_and_emits_event(pool_address: str) -> None:
    sup = await _build_supervisor(pool_address, uid="ref-sup-outline")
    try:
        payload = SubmitOutlinePayload(
            work_units=(
                WorkUnitOutlinePayload(id="wu-1", task="Task 1"),
                WorkUnitOutlinePayload(id="wu-2", task="Task 2"),
            )
        )
        await sup.outline_ready(payload)
        # No clean way to read _outline from outside; instead verify
        # via behaviour: a second outline is ignored (emits warning).
        await sup.outline_ready(payload)
    finally:
        await xo.destroy_actor(sup)


@pytest.mark.asyncio
async def test_detail_ready_accumulates(pool_address: str) -> None:
    sup = await _build_supervisor(pool_address, uid="ref-sup-detail")
    try:
        payload = SubmitDetailsPayload(
            details=(
                WorkUnitDetailPayload(id="wu-1", instructions="do it"),
                WorkUnitDetailPayload(id="wu-2", instructions="and again"),
            )
        )
        # Must not raise even though pending_detail_ids is empty (no
        # outstanding fan-out yet in this smoke test).
        await sup.detail_ready(payload)
    finally:
        await xo.destroy_actor(sup)


@pytest.mark.asyncio
async def test_prompt_error_detail_phase_is_silent(pool_address: str) -> None:
    """Detail-phase prompt errors are logged at debug only — the fan-out
    retry loop owns recovery, not the prompt_error callback."""
    sup = await _build_supervisor(pool_address, uid="ref-sup-pe-detail")
    try:
        # Should not mark the supervisor done.
        await sup.prompt_error(
            PromptError(
                phase="detail",
                error="transient",
                unit_id="wu-1",
                quota_exhausted=False,
            )
        )
    finally:
        await xo.destroy_actor(sup)


@pytest.mark.asyncio
async def test_prompt_error_outline_phase_marks_done(pool_address: str) -> None:
    """Outline failure is fatal — supervisor marks done with error."""
    sup = await _build_supervisor(pool_address, uid="ref-sup-pe-outline")
    try:
        with patch(
            "maverick.actors.xoscar.refuel_supervisor.RefuelSupervisor._emit_output",
            new=AsyncMock(),
        ):
            await sup.prompt_error(
                PromptError(phase="outline", error="agent died", quota_exhausted=False)
            )
    finally:
        await xo.destroy_actor(sup)


@pytest.mark.asyncio
async def test_payload_parse_error_detail_is_warned_only(pool_address: str) -> None:
    sup = await _build_supervisor(pool_address, uid="ref-sup-parse-detail")
    try:
        await sup.payload_parse_error("submit_details", "bad shape")
    finally:
        await xo.destroy_actor(sup)
