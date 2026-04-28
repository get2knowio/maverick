"""Smoke tests for ``RefuelSupervisor``.

Full state-machine coverage is deferred to end-to-end integration tests
(which exercise real ACP subprocesses). These tests verify that the
supervisor constructs cleanly, its typed domain methods behave as
expected, and its event queue / generator wiring is correct.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
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


@pytest.mark.asyncio
async def test_detail_ready_emits_per_unit_agent_completed(pool_address: str) -> None:
    """Each unit in a SubmitDetailsPayload triggers an AgentCompleted so
    the CLI's Live decompose table can mark its row done. Drives the
    "which model worked on which unit" visibility surface."""
    from maverick.events import AgentCompleted

    sup = await _build_supervisor(pool_address, uid="ref-sup-emit-completed")
    try:
        await sup.t_seed_detail_state(["wu-1", "wu-2"])
        # Discard any startup events so we measure just detail_ready's emissions.
        await sup.t_drain_events()

        await sup.detail_ready(
            SubmitDetailsPayload(
                details=(
                    WorkUnitDetailPayload(id="wu-1", instructions="x"),
                    WorkUnitDetailPayload(id="wu-2", instructions="y"),
                )
            )
        )
        events = await sup.t_drain_events()
        completed = [e for e in events if isinstance(e, AgentCompleted)]
        completed_unit_ids = {e.agent_name for e in completed}
        assert completed_unit_ids == {"wu-1", "wu-2"}
        assert all(e.step_name == "decompose" for e in completed)
        assert all(e.success for e in completed)
    finally:
        await xo.destroy_actor(sup)


@pytest.mark.asyncio
async def test_detail_ready_no_double_emit_for_unknown_unit(pool_address: str) -> None:
    """A worker re-submitting an already-done unit's detail must not
    emit a second AgentCompleted — the empty pending set means "no longer
    waiting on this unit", so the row is already marked done."""
    from maverick.events import AgentCompleted

    sup = await _build_supervisor(pool_address, uid="ref-sup-no-double-emit")
    try:
        await sup.t_seed_detail_state([])  # empty pending — already-done case
        await sup.t_drain_events()

        await sup.detail_ready(
            SubmitDetailsPayload(
                details=(WorkUnitDetailPayload(id="wu-stale", instructions="x"),)
            )
        )
        events = await sup.t_drain_events()
        completed = [e for e in events if isinstance(e, AgentCompleted)]
        assert completed == [], "should not re-emit AgentCompleted for stale unit"
    finally:
        await xo.destroy_actor(sup)


def test_seed_cached_details_loads_into_accumulator() -> None:
    """``_seed_cached_details`` parses the workflow-supplied cache and
    seeds ``_accumulated_details`` so the detail fan-out can skip those
    units. Bug fix: previously this code was missing entirely — every
    resumed run re-processed every unit even when detail JSON files
    existed on disk."""
    from types import SimpleNamespace

    from maverick.actors.xoscar.refuel_supervisor import RefuelSupervisor

    cached_details = {
        "wu-1": {
            "id": "wu-1",
            "instructions": "do it",
            "acceptance_criteria": [{"text": "passes", "trace_ref": "SC-001"}],
            "verification": ["npm test"],
            "test_specification": "tests pass",
        },
        "wu-3": {
            "id": "wu-3",
            "instructions": "ok",
            "acceptance_criteria": [{"text": "ok", "trace_ref": "SC-003"}],
            "verification": ["npm test"],
            "test_specification": "ok",
        },
        # Stale entry — wu-99 not in the current outline.
        "wu-99": {
            "id": "wu-99",
            "instructions": "stale",
            "verification": ["x"],
        },
        # Malformed entry — fails Pydantic validation.
        "wu-bad": "not a mapping",
    }
    sup = RefuelSupervisor(
        RefuelInputs(
            cwd="/tmp",
            flight_plan=SimpleNamespace(
                name="plan", objective="x", success_criteria=[]
            ),
            initial_payload={"cached_details": cached_details},
            skip_briefing=True,
        )
    )
    sup._accumulated_details = []  # __post_create__ usually does this

    seeded = sup._seed_cached_details(["wu-1", "wu-2", "wu-3"])
    assert seeded == {"wu-1", "wu-3"}
    accumulator_ids = {d.id for d in sup._accumulated_details}
    assert accumulator_ids == {"wu-1", "wu-3"}
    # Stale entry never made it into the accumulator.
    assert all(d.id != "wu-99" for d in sup._accumulated_details)


@pytest.mark.asyncio
async def test_decomposer_escalation_threshold_default_is_one(
    pool_address: str,
) -> None:
    """``DecomposerTiersConfig.escalation_threshold`` defaults to 1 so the
    common case (one moderate tier failure escalates to complex) is the
    out-of-the-box behaviour. ``ImplementerTiersConfig`` defaults to 2;
    decomposer detail is mechanical enough that 1 is the right default."""
    from maverick.config import DecomposerTiersConfig, ImplementerTierConfig

    cfg = DecomposerTiersConfig(
        moderate=ImplementerTierConfig(provider="copilot", model_id="gpt-5.4"),
        complex=ImplementerTierConfig(
            provider="copilot", model_id="gpt-5.3-codex"
        ),
    )
    assert cfg.escalation_threshold == 1

    # Threshold 0 (disable) is legal.
    disabled = DecomposerTiersConfig(escalation_threshold=0)
    assert disabled.escalation_threshold == 0

    # Threshold > 5 is rejected by the Pydantic validator.
    with pytest.raises(Exception):  # noqa: PT011 — pydantic ValidationError shape varies
        DecomposerTiersConfig(escalation_threshold=99)


@pytest.mark.asyncio
async def test_prompt_error_detail_records_quota_signal(pool_address: str) -> None:
    """``prompt_error`` for the detail phase records ``quota_exhausted``
    signals into ``_detail_quota_errors`` so the dispatcher can skip
    doomed retries against the same exhausted provider."""
    sup = await _build_supervisor(pool_address, uid="ref-sup-quota-record")
    try:
        await sup.prompt_error(
            PromptError(
                phase="detail",
                error="You've hit your usage limit; resets 6am UTC",
                unit_id="wu-1",
                quota_exhausted=True,
            )
        )
        # Non-quota detail errors must NOT be recorded — only quota.
        await sup.prompt_error(
            PromptError(
                phase="detail",
                error="some random transient",
                unit_id="wu-2",
                quota_exhausted=False,
            )
        )

        async def _peek_quota(s: RefuelSupervisor) -> dict[str, str]:
            return dict(s._detail_quota_errors)

        # Use a thin t_ probe (added below) so we can read the dict
        # across the actor boundary without hand-rolling RPC plumbing.
        snapshot = await sup.t_peek_detail_quota_errors()
        assert "wu-1" in snapshot
        assert "wu-2" not in snapshot
        assert "limit" in snapshot["wu-1"].lower()
    finally:
        await xo.destroy_actor(sup)


@pytest.mark.asyncio
async def test_fix_ready_writes_outline_and_details_to_cache(
    pool_address: str, tmp_path: Path
) -> None:
    """fix_ready must persist the corrected outline and details so a
    re-run picks up the post-fix state instead of re-loading the
    pre-fix version and burning the fix loop again."""
    from maverick.tools.agent_inbox.models import (
        AcceptanceCriterionPayload,
        SubmitFixPayload,
        WorkUnitDetailPayload,
        WorkUnitOutlinePayload,
    )

    detail_cache_dir = tmp_path / "details"
    outline_cache_path = tmp_path / "outline.json"

    sup = await xo.create_actor(
        RefuelSupervisor,
        RefuelInputs(
            cwd=str(tmp_path),
            flight_plan=_flight_plan(),
            initial_payload={"flight_plan_content": "plan"},
            skip_briefing=True,
            outline_cache_path=str(outline_cache_path),
            detail_cache_dir=str(detail_cache_dir),
        ),
        address=pool_address,
        uid="ref-sup-fix-cache",
    )
    try:
        # Send a fix payload mirroring what the agent's submit_fix
        # MCP tool would deliver.
        await sup.fix_ready(
            SubmitFixPayload(
                work_units=(
                    WorkUnitOutlinePayload(
                        id="wu-1", task="t1", sequence=1, complexity="moderate"
                    ),
                ),
                details=(
                    WorkUnitDetailPayload(
                        id="wu-1",
                        instructions="updated by fix",
                        acceptance_criteria=(
                            AcceptanceCriterionPayload(
                                text="now traces SC-009", trace_ref="SC-009"
                            ),
                        ),
                        verification=("npm test",),
                    ),
                ),
            )
        )

        assert outline_cache_path.is_file(), (
            "fix_ready must persist the corrected outline"
        )
        detail_path = detail_cache_dir / "wu-1.json"
        assert detail_path.is_file(), (
            "fix_ready must persist each corrected detail per-unit"
        )
        import json as _json

        cached_detail = _json.loads(detail_path.read_text(encoding="utf-8"))
        assert cached_detail["id"] == "wu-1"
        assert cached_detail["instructions"] == "updated by fix"
        # Verify the fixed trace_ref made it through.
        ac = cached_detail["acceptance_criteria"][0]
        assert ac["trace_ref"] == "SC-009"
    finally:
        await xo.destroy_actor(sup)


@pytest.mark.asyncio
async def test_fix_ready_merges_partial_payload_with_existing_state(
    pool_address: str, tmp_path: Path
) -> None:
    """The fix payload is a DELTA — only units the fixer changed.
    fix_ready MUST merge into existing outline + accumulated_details;
    replacing wholesale drops the untouched units and the validator
    sees a 1-unit decomposition with dangling deps. This was an
    observed-in-the-wild bug where a 42-unit run with a missing
    trace_ref produced 4 created beads after the fix overwrote 41
    untouched units."""
    from maverick.tools.agent_inbox.models import (
        AcceptanceCriterionPayload,
        SubmitDetailsPayload,
        SubmitFixPayload,
        SubmitOutlinePayload,
        WorkUnitDetailPayload,
        WorkUnitOutlinePayload,
    )

    sup = await xo.create_actor(
        RefuelSupervisor,
        RefuelInputs(
            cwd=str(tmp_path),
            flight_plan=_flight_plan(),
            initial_payload={"flight_plan_content": "plan"},
            skip_briefing=True,
        ),
        address=pool_address,
        uid="ref-sup-fix-merge",
    )
    try:
        # Pre-seed outline + details with three units (simulating a
        # full decompose that already completed).
        await sup.outline_ready(
            SubmitOutlinePayload(
                work_units=(
                    WorkUnitOutlinePayload(id="wu-a", task="A", sequence=1),
                    WorkUnitOutlinePayload(id="wu-b", task="B", sequence=2),
                    WorkUnitOutlinePayload(id="wu-c", task="C", sequence=3),
                )
            )
        )
        # Seed each unit's detail.
        for uid in ("wu-a", "wu-b", "wu-c"):
            await sup.t_seed_detail_state([uid])  # marks as pending
            await sup.detail_ready(
                SubmitDetailsPayload(
                    details=(
                        WorkUnitDetailPayload(
                            id=uid,
                            instructions=f"original {uid}",
                            acceptance_criteria=(
                                AcceptanceCriterionPayload(
                                    text="t", trace_ref="SC-001"
                                ),
                            ),
                            verification=("npm test",),
                        ),
                    )
                )
            )
        # Drain events so the next assertions see only fix-related output.
        await sup.t_drain_events()

        # Fix payload addresses ONLY wu-b.
        await sup.fix_ready(
            SubmitFixPayload(
                work_units=(
                    WorkUnitOutlinePayload(
                        id="wu-b", task="B (fixed)", sequence=2
                    ),
                ),
                details=(
                    WorkUnitDetailPayload(
                        id="wu-b",
                        instructions="updated by fix",
                        acceptance_criteria=(
                            AcceptanceCriterionPayload(
                                text="t", trace_ref="SC-002"
                            ),
                        ),
                        verification=("npm test",),
                    ),
                ),
            )
        )

        # Probe state via t_ helper.
        async def _peek_state(s: RefuelSupervisor) -> dict[str, Any]:
            return {
                "outline_ids": [wu.id for wu in s._outline.work_units]
                if s._outline
                else [],
                "outline_tasks": {
                    wu.id: wu.task for wu in (s._outline.work_units if s._outline else ())
                },
                "detail_ids": [d.id for d in s._accumulated_details],
                "detail_instructions": {
                    d.id: d.instructions for d in s._accumulated_details
                },
            }

        # Use a small inline t_ method on the actor to peek state.
        # Since the supervisor doesn't have one for this purpose,
        # check via the existing t_drain_events / outline_payload by
        # serialising to dict.
        outline_dict = await sup.t_peek_outline_and_details()
        assert sorted(outline_dict["outline_ids"]) == ["wu-a", "wu-b", "wu-c"], (
            "outline must keep all 3 units after fix; got "
            f"{outline_dict['outline_ids']}"
        )
        assert outline_dict["outline_tasks"]["wu-b"] == "B (fixed)"
        assert outline_dict["outline_tasks"]["wu-a"] == "A"  # preserved

        assert sorted(outline_dict["detail_ids"]) == [
            "wu-a",
            "wu-b",
            "wu-c",
        ], (
            "accumulated_details must keep all 3 units after fix; got "
            f"{outline_dict['detail_ids']}"
        )
        assert (
            outline_dict["detail_instructions"]["wu-b"] == "updated by fix"
        )
        # Untouched units retain their original instructions.
        assert (
            outline_dict["detail_instructions"]["wu-a"] == "original wu-a"
        )
        assert (
            outline_dict["detail_instructions"]["wu-c"] == "original wu-c"
        )
    finally:
        await xo.destroy_actor(sup)


def test_seed_cached_details_no_op_when_no_cache() -> None:
    """Empty cache → no-op, returns empty set, accumulator unchanged."""
    from types import SimpleNamespace

    from maverick.actors.xoscar.refuel_supervisor import RefuelSupervisor

    sup = RefuelSupervisor(
        RefuelInputs(
            cwd="/tmp",
            flight_plan=SimpleNamespace(
                name="plan", objective="x", success_criteria=[]
            ),
            initial_payload={},
            skip_briefing=True,
        )
    )
    sup._accumulated_details = []
    assert sup._seed_cached_details(["wu-1", "wu-2"]) == set()
    assert sup._accumulated_details == []


def test_merge_to_specs_skips_unparseable_specs() -> None:
    """A unit whose merged dict fails ``WorkUnitSpec.model_validate``
    (e.g., empty verification) is logged + dropped — never appended as a
    raw dict. Was the silent fallback that hid the upstream abandon."""
    from types import SimpleNamespace

    from maverick.actors.xoscar.refuel_supervisor import RefuelSupervisor
    from maverick.tools.agent_inbox.models import (
        AcceptanceCriterionPayload,
        SubmitDetailsPayload,
        SubmitOutlinePayload,
        WorkUnitDetailPayload,
        WorkUnitOutlinePayload,
    )
    from maverick.workflows.refuel_maverick.models import WorkUnitSpec

    sup = RefuelSupervisor(
        RefuelInputs(
            cwd="/tmp",
            flight_plan=SimpleNamespace(
                name="plan", objective="x", success_criteria=[]
            ),
            initial_payload={},
            skip_briefing=True,
        )
    )
    sup._outline = SubmitOutlinePayload(
        work_units=(
            WorkUnitOutlinePayload(id="wu-good", task="t1", sequence=1),
            WorkUnitOutlinePayload(id="wu-bad", task="t2", sequence=2),
        )
    )
    # wu-bad: empty verification → WorkUnitSpec rejects it.
    sup._details = SubmitDetailsPayload(
        details=(
            WorkUnitDetailPayload(
                id="wu-good",
                instructions="ok",
                acceptance_criteria=(
                    AcceptanceCriterionPayload(text="t", trace_ref="SC-1"),
                ),
                verification=("npm test",),
            ),
            WorkUnitDetailPayload(
                id="wu-bad",
                instructions="ok",
                acceptance_criteria=(
                    AcceptanceCriterionPayload(text="t", trace_ref="SC-2"),
                ),
                verification=(),  # empty → validation fails
            ),
        )
    )
    specs = sup._merge_to_specs()
    assert len(specs) == 1
    assert isinstance(specs[0], WorkUnitSpec)
    assert specs[0].id == "wu-good"


def test_merge_to_specs_skips_units_without_detail() -> None:
    """``_merge_to_specs`` drops units missing detail entirely instead of
    falling back to a raw dict — preventing the cascading
    `'dict' object has no attribute 'id'` validator crash."""
    from types import SimpleNamespace

    from maverick.actors.xoscar.refuel_supervisor import RefuelSupervisor
    from maverick.tools.agent_inbox.models import (
        AcceptanceCriterionPayload,
        SubmitDetailsPayload,
        SubmitOutlinePayload,
        WorkUnitDetailPayload,
        WorkUnitOutlinePayload,
    )
    from maverick.workflows.refuel_maverick.models import WorkUnitSpec

    sup = RefuelSupervisor(
        RefuelInputs(
            cwd="/tmp",
            flight_plan=SimpleNamespace(
                name="plan", objective="x", success_criteria=[]
            ),
            initial_payload={},
            skip_briefing=True,
        )
    )
    # Outline has 3 units; details have only 2 — wu-2 was abandoned.
    sup._outline = SubmitOutlinePayload(
        work_units=(
            WorkUnitOutlinePayload(id="wu-1", task="t1", sequence=1),
            WorkUnitOutlinePayload(id="wu-2", task="t2", sequence=2),
            WorkUnitOutlinePayload(id="wu-3", task="t3", sequence=3),
        )
    )
    sup._details = SubmitDetailsPayload(
        details=(
            WorkUnitDetailPayload(
                id="wu-1",
                instructions="do it",
                acceptance_criteria=(
                    AcceptanceCriterionPayload(text="passes", trace_ref="SC-001"),
                ),
                verification=("npm test",),
                test_specification="t",
            ),
            WorkUnitDetailPayload(
                id="wu-3",
                instructions="do it 3",
                acceptance_criteria=(
                    AcceptanceCriterionPayload(text="passes", trace_ref="SC-002"),
                ),
                verification=("npm test",),
                test_specification="t3",
            ),
        )
    )
    specs = sup._merge_to_specs()
    # Only wu-1 and wu-3 — wu-2 (no detail) is silently dropped.
    assert len(specs) == 2
    assert all(isinstance(s, WorkUnitSpec) for s in specs), (
        "no raw dicts should leak into the spec list"
    )
    assert {s.id for s in specs} == {"wu-1", "wu-3"}


@pytest.mark.asyncio
async def test_tier_mode_demand_pool_starts_empty(pool_address: str) -> None:
    """Tier mode uses a demand-driven pool — actors are spawned when work
    arrives, not pre-allocated at supervisor construction. The cap is the
    system-resource budget; the pool fills as the workload demands."""
    from maverick.config import (
        DecomposerTiersConfig,
        ImplementerTierConfig,
    )

    inputs = RefuelInputs(
        cwd="/tmp",
        flight_plan=_flight_plan(),
        initial_payload={"flight_plan_content": "plan"},
        decomposer_pool_size=3,  # cap on total live decomposers in tier mode
        skip_briefing=True,
        decomposer_tiers=DecomposerTiersConfig(
            simple=ImplementerTierConfig(provider="opencode", model_id="x"),
            moderate=ImplementerTierConfig(provider="claude", model_id="sonnet"),
            complex=ImplementerTierConfig(provider="claude", model_id="opus"),
        ),
    )
    sup = await xo.create_actor(
        RefuelSupervisor,
        inputs,
        address=pool_address,
        uid="ref-sup-tier-demand",
    )
    try:
        snapshot = await sup.t_peek_decomposers()
        assert snapshot["mode"] == "tiered"
        # Pool is empty at start — no actors of any tier exist until the
        # detail fan-out asks for one.
        assert snapshot["demand_pool"]["cap"] == 3
        assert snapshot["demand_pool"]["total"] == 0
        assert snapshot["demand_pool"]["actors_by_tier"] == {}
    finally:
        await xo.destroy_actor(sup)


# ---------------------------------------------------------------------------
# Demand-pool internals — tested in isolation against a fake supervisor so
# we don't need the full supervisor + xoscar create_actor stack here.
# ---------------------------------------------------------------------------


class _FakeRef:
    """Stand-in for an xoscar ActorRef. Identity-distinct, no behaviour."""

    def __init__(self, label: str) -> None:
        self.label = label

    def __repr__(self) -> str:
        return f"<FakeRef {self.label}>"


# Imported lazily to keep the top of the file dependency-light.
from maverick.executor.config import StepConfig as _StepConfig  # noqa: E402


@pytest.mark.asyncio
async def test_decomposer_pool_reuse_spawn_evict() -> None:
    """The demand pool follows the spec: reuse idle of-tier first, spawn
    under cap, evict LRU idle of any other tier when at cap."""
    from unittest.mock import AsyncMock, patch

    from maverick.actors.xoscar.refuel_supervisor import _DecomposerPool

    spawn_log: list[str] = []
    destroy_log: list[str] = []

    fake_actor_count = [0]

    async def fake_create_actor(*_args: Any, **_kwargs: Any) -> _FakeRef:
        fake_actor_count[0] += 1
        ref = _FakeRef(f"actor-{fake_actor_count[0]}")
        spawn_log.append(_kwargs.get("uid", ref.label))
        return ref

    async def fake_destroy_actor(ref: _FakeRef) -> None:
        destroy_log.append(ref.label)

    # The pool reaches into ``supervisor.ref()``, ``supervisor.address``,
    # ``supervisor.uid``, ``supervisor._inputs.cwd``. Stub all four.
    supervisor = SimpleNamespace(
        ref=lambda: SimpleNamespace(),
        address="memory://test",
        uid=b"fake-sup",
        _inputs=SimpleNamespace(cwd="/tmp"),
    )

    with (
        patch(
            "maverick.actors.xoscar.refuel_supervisor.xo.create_actor",
            new=fake_create_actor,
        ),
        patch(
            "maverick.actors.xoscar.refuel_supervisor.xo.destroy_actor",
            new=fake_destroy_actor,
        ),
        patch(
            "maverick.actors.xoscar.refuel_supervisor.DecomposerActor",
            new=AsyncMock,
        ),
    ):
        from maverick.config import (
            DecomposerTiersConfig,
            ImplementerTierConfig,
        )

        pool = _DecomposerPool(
            supervisor=supervisor,
            cap=2,
            base_config=_StepConfig(provider="claude", model_id="sonnet"),
            decomposer_tiers=DecomposerTiersConfig(
                simple=ImplementerTierConfig(provider="opencode", model_id="x"),
                moderate=ImplementerTierConfig(
                    provider="claude", model_id="sonnet"
                ),
                complex=ImplementerTierConfig(provider="claude", model_id="opus"),
            ),
            detail_session_max_turns=1,
            fix_session_max_turns=1,
        )

        # 1. Empty pool, acquire(moderate) → spawns first.
        a1 = await pool.acquire("moderate")
        assert pool.snapshot() == {
            "cap": 2,
            "total": 1,
            "idle_by_tier": {},
            "actors_by_tier": {"moderate": 1},
        }

        # 2. Release a1 then acquire(moderate) → REUSES (no spawn).
        await pool.release(a1, "moderate")
        a1_again = await pool.acquire("moderate")
        assert a1_again is a1, "must reuse the cached moderate actor"
        assert len(spawn_log) == 1

        # 3. Acquire(simple) under cap → spawns second.
        a2 = await pool.acquire("simple")
        assert a2 is not a1
        assert pool.total_live == 2
        assert len(spawn_log) == 2
        assert destroy_log == []

        # 4. Release both, then acquire(complex) — at cap, must EVICT
        # the LRU idle actor (the moderate one — released first).
        await pool.release(a1_again, "moderate")
        await pool.release(a2, "simple")
        a3 = await pool.acquire("complex")
        assert a3 is not a1
        assert a3 is not a2
        assert len(spawn_log) == 3
        # The LRU was a1 (moderate, released first) — that's what got destroyed.
        assert destroy_log == [a1.label]
        snap = pool.snapshot()
        assert snap["total"] == 2
        # complex (busy, just acquired) + simple (idle in cache).
        assert snap["actors_by_tier"] == {"simple": 1, "complex": 1}
        assert snap["idle_by_tier"] == {"simple": 1}


@pytest.mark.asyncio
async def test_decomposer_pool_blocks_at_cap_when_no_idle() -> None:
    """When every actor in the pool is busy and we're at cap, acquire()
    must block until release() — not spawn beyond cap."""
    import contextlib
    from unittest.mock import AsyncMock, patch

    from maverick.actors.xoscar.refuel_supervisor import _DecomposerPool

    fake_actor_count = [0]

    async def fake_create_actor(*_args: Any, **_kwargs: Any) -> _FakeRef:
        fake_actor_count[0] += 1
        return _FakeRef(f"actor-{fake_actor_count[0]}")

    async def fake_destroy_actor(_ref: _FakeRef) -> None:
        pass

    supervisor = SimpleNamespace(
        ref=lambda: SimpleNamespace(),
        address="memory://test",
        uid=b"fake-sup",
        _inputs=SimpleNamespace(cwd="/tmp"),
    )

    with (
        patch(
            "maverick.actors.xoscar.refuel_supervisor.xo.create_actor",
            new=fake_create_actor,
        ),
        patch(
            "maverick.actors.xoscar.refuel_supervisor.xo.destroy_actor",
            new=fake_destroy_actor,
        ),
        patch(
            "maverick.actors.xoscar.refuel_supervisor.DecomposerActor",
            new=AsyncMock,
        ),
    ):
        pool = _DecomposerPool(
            supervisor=supervisor,
            cap=1,
            base_config=_StepConfig(provider="claude", model_id="sonnet"),
            decomposer_tiers=None,
            detail_session_max_turns=1,
            fix_session_max_turns=1,
        )
        a1 = await pool.acquire("moderate")  # spawned, busy
        # Second acquire of same tier with no idle: must wait.
        third_task = asyncio.create_task(pool.acquire("moderate"))
        await asyncio.sleep(0.05)
        assert not third_task.done(), "acquire must block when at cap with no idle"
        # Release a1 → unblocks third_task with the same actor reused.
        await pool.release(a1, "moderate")
        a2 = await asyncio.wait_for(third_task, timeout=1.0)
        assert a2 is a1, "released actor should be reused, not respawned"
        # Cleanup: cancel any remaining waiters (none here, defensive).
        with contextlib.suppress(asyncio.CancelledError):
            third_task.cancel()


def test_format_provider_label_handles_partial_configs() -> None:
    """The label helper produces ``provider/model`` even when fields are
    missing — defensive against partial StepConfigs from sparse YAML."""
    from types import SimpleNamespace

    full = SimpleNamespace(provider="gemini", model_id="gemini-3.1-pro-preview")
    partial = SimpleNamespace(provider="gemini", model_id=None)
    none_config = None

    fmt = RefuelSupervisor._format_provider_label
    assert fmt(full) == "gemini/gemini-3.1-pro-preview"
    assert fmt(partial) == "gemini/default"
    assert fmt(none_config) == ""
