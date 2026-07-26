"""Unit tests for the Burr-mode refuel graph.

Exercises the substrate-side state machine end-to-end with stub
agents — no real airframe runtime, no xoscar pool, no bd CLI.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

from maverick.burr import BurrWorkflowDriver
from maverick.events import (
    AgentCompleted,
    AgentStarted,
    ProgressEvent,
    StepCompleted,
    StepStarted,
)
from maverick.library.actions.types import BeadCreationResult, DependencyWiringResult
from maverick.payloads import (
    AcceptanceCriterionPayload,
    FileScopePayload,
    SubmitContrarianBriefPayload,
    SubmitDetailsPayload,
    SubmitFixPayload,
    SubmitNavigatorBriefPayload,
    SubmitOutlinePayload,
    SubmitReconBriefPayload,
    SubmitStructuralistBriefPayload,
    WorkUnitDetailPayload,
    WorkUnitOutlinePayload,
)
from maverick.squadron.tiers import DEFAULT_TIER
from maverick.workflows.refuel_maverick.actions import CACHE_SCHEMA_VERSION
from maverick.workflows.refuel_maverick.burr_graph import (
    REFUEL_TERMINAL_ACTIONS,
    build_refuel_application,
)
from tests.unit.agents.airframe_stubs import StubBriefingAgent, StubDecomposerAgent


def _empty_codebase_context() -> Any:
    """Build a minimal :class:`CodebaseContext` with no files."""
    from maverick.library.actions.decompose import CodebaseContext

    return CodebaseContext(files=(), missing_files=(), total_size=0)


# ---------------------------------------------------------------------------
# Stub squadron — keeps the Burr graph 100% offline
# ---------------------------------------------------------------------------


def _make_outline(unit_ids: tuple[str, ...] = ("u-1", "u-2")) -> SubmitOutlinePayload:
    return SubmitOutlinePayload(
        work_units=tuple(
            WorkUnitOutlinePayload(
                id=uid,
                task=f"task for {uid}",
                sequence=i + 1,
                depends_on=(),
                file_scope=FileScopePayload(),
                complexity="simple",
            )
            for i, uid in enumerate(unit_ids)
        ),
    )


def _make_details(unit_ids: tuple[str, ...]) -> SubmitDetailsPayload:
    return SubmitDetailsPayload(
        details=tuple(
            WorkUnitDetailPayload(
                id=uid,
                instructions=f"instructions for {uid}",
                acceptance_criteria=(AcceptanceCriterionPayload(text=f"ac-{uid}"),),
                verification=("pytest -k stub",),
                test_specification="",
            )
            for uid in unit_ids
        )
    )


_BRIEF_PAYLOADS: dict[str, Any] = {
    "navigator": SubmitNavigatorBriefPayload(
        architecture_decisions=(),
        module_structure="stub mods",
        summary="navigator stub",
    ),
    "structuralist": SubmitStructuralistBriefPayload(
        entities=(),
        summary="structuralist stub",
    ),
    "recon": SubmitReconBriefPayload(
        risks=(),
        summary="recon stub",
    ),
    "contrarian": SubmitContrarianBriefPayload(
        challenges=(),
        summary="contrarian stub",
    ),
}


class _StubDecomposerPool:
    """Mimics :class:`DecomposerAgentPool` for offline tests.

    Always hands out the same :class:`StubDecomposerAgent`. Tracks
    acquire/release call counts so tests can assert on them.
    """

    def __init__(self, agent: StubDecomposerAgent) -> None:
        self._agent = agent
        self.acquire_calls: list[str] = []
        self.release_calls: list[str] = []

    async def acquire(self, tier: str) -> StubDecomposerAgent:
        self.acquire_calls.append(tier)
        return self._agent

    async def release(self, agent: StubDecomposerAgent, tier: str) -> None:
        self.release_calls.append(tier)

    async def set_context(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def teardown(self) -> None:
        return None


class StubRefuelSquadron:
    """Mimics :class:`RefuelSquadron` for Burr-mode tests."""

    def __init__(
        self,
        *,
        outline_payload: SubmitOutlinePayload | None = None,
        detail_payloads: list[SubmitDetailsPayload] | None = None,
        fix_payloads: list[SubmitFixPayload] | None = None,
        briefing_payloads: dict[str, Any] | None = None,
        escalation_ladder: tuple[str, ...] | None = None,
    ) -> None:
        # ``None`` mirrors an unconfigured squadron: the base binding is
        # the only rung, so there is nothing to escalate to.
        self._escalation_ladder = escalation_ladder or (DEFAULT_TIER,)
        outline = outline_payload or _make_outline()
        # Each per-unit detail call returns details for *one* unit;
        # the fan-out makes one decomposer call per unit by default.
        # If the caller doesn't pre-stage detail payloads, derive them
        # from the outline so each unit gets its own.
        if detail_payloads is None:
            detail_payloads = [_make_details((u.id,)) for u in outline.work_units]
        self._decomposer = StubDecomposerAgent(
            outline_payloads=[outline],
            detail_payloads=detail_payloads,
            fix_payloads=fix_payloads or [],
        )
        self.decomposer_pool = _StubDecomposerPool(self._decomposer)
        self._briefing_payloads = dict(briefing_payloads or _BRIEF_PAYLOADS)
        self.built_briefings: list[StubBriefingAgent] = []

    def decomposer_escalation_ladder(self) -> tuple[str, ...]:
        return self._escalation_ladder

    def build_briefing_agent(self, *, agent_name: str, result_model: Any) -> StubBriefingAgent:
        payload = self._briefing_payloads.get(agent_name)
        if payload is None:
            raise AssertionError(f"no stub briefing payload for agent {agent_name!r}")
        stub = StubBriefingAgent(
            agent_name=agent_name,
            result_model=result_model,
            brief_payloads=[payload],
        )
        self.built_briefings.append(stub)
        return stub


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _collect(driver: BurrWorkflowDriver) -> list[ProgressEvent]:
    events: list[ProgressEvent] = []
    async for evt in driver.events():
        events.append(evt)
    return events


def _by_action(events: list[ProgressEvent]) -> list[str]:
    return [e.step_name for e in events if isinstance(e, StepStarted)]


def _make_bead_result() -> BeadCreationResult:
    return BeadCreationResult(
        epic={"bd_id": "epic-1", "title": "stub-plan"},
        work_beads=(
            {"bd_id": "bead-1", "title": "task for u-1"},
            {"bd_id": "bead-2", "title": "task for u-2"},
        ),
        created_map={
            "task for u-1": "bead-1",
            "task for u-2": "bead-2",
        },
        errors=(),
    )


def _raise_budget(message: str) -> None:
    """Raise airframe's budget error with its required metadata."""
    from airframe.errors import RuntimeBudgetExceededError

    raise RuntimeBudgetExceededError(message, cap=10.0, current=10.5, kind="usd")


def _dump(payload: Any) -> dict[str, Any]:
    """Serialize a payload the way the cache writer does."""
    from maverick.payloads import dump_supervisor_payload

    return dump_supervisor_payload(payload)


def _make_wire_result() -> DependencyWiringResult:
    return DependencyWiringResult(
        dependencies=({"from": "bead-2", "to": "bead-1"},),
        errors=(),
        success=True,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRefuelBurrGraphHappyPath:
    async def test_full_pipeline_executes_all_actions(self, tmp_path: Path) -> None:
        """Briefing → outline → detail → validate (pass) → create_beads → done."""
        queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
        squadron = StubRefuelSquadron()

        with (
            patch(
                "maverick.workflows.refuel_maverick.actions.SUPERVISOR_TOOL_PAYLOAD_MODELS",
                {
                    "submit_navigator_brief": SubmitNavigatorBriefPayload,
                    "submit_structuralist_brief": SubmitStructuralistBriefPayload,
                    "submit_recon_brief": SubmitReconBriefPayload,
                    "submit_contrarian_brief": SubmitContrarianBriefPayload,
                },
            ),
            patch(
                "maverick.library.actions.beads.create_beads",
                new=AsyncMock(return_value=_make_bead_result()),
            ),
            patch(
                "maverick.library.actions.beads.wire_dependencies",
                new=AsyncMock(return_value=_make_wire_result()),
            ),
        ):
            app = build_refuel_application(
                squadron=squadron,
                event_queue=queue,
                raw_content="# stub PRD",
                briefing_prompt="brief me",
                codebase_context=_empty_codebase_context(),
                open_bead_context=None,
                runway_context_text=None,
                plan_name="stub-plan",
                plan_objective="ship stub",
                cwd=str(tmp_path),
                skip_briefing=False,
                provider_labels={},
                max_briefing_agents=3,
                decomposer_pool_size=2,
                success_criteria_count=0,
                expected_sc_refs=(),
            )
            driver = BurrWorkflowDriver(app, halt_after=REFUEL_TERMINAL_ACTIONS, event_queue=queue)
            events = await _collect(driver)

        action_sequence = _by_action(events)
        assert action_sequence == [
            "init_state",
            "parallel_briefings",
            "contrarian_briefing",
            "synthesize_briefing",
            "outline",
            "detail_fan_out",
            "validate",
            "check_validation",
            "create_beads",
            "done",
        ]

        for name in action_sequence:
            completed = [e for e in events if isinstance(e, StepCompleted) and e.step_name == name]
            assert len(completed) == 1, f"missing StepCompleted for {name!r}"
            assert completed[0].success is True, f"{name!r} not successful"

        _, _, state = driver.result
        assert state["epic_id"] == "epic-1"
        assert len(state["work_beads"]) == 2
        assert state["fix_rounds"] == 0
        assert state["validation_passed"] is True
        # 4 briefing agents built (3 parallel + contrarian)
        assert len(squadron.built_briefings) == 4

    async def test_emits_agent_events_per_briefing(self, tmp_path: Path) -> None:
        queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
        squadron = StubRefuelSquadron()
        with (
            patch(
                "maverick.library.actions.beads.create_beads",
                new=AsyncMock(return_value=_make_bead_result()),
            ),
            patch(
                "maverick.library.actions.beads.wire_dependencies",
                new=AsyncMock(return_value=_make_wire_result()),
            ),
        ):
            app = build_refuel_application(
                squadron=squadron,
                event_queue=queue,
                raw_content="x",
                briefing_prompt="x",
                codebase_context=_empty_codebase_context(),
                open_bead_context=None,
                runway_context_text=None,
                plan_name="p",
                plan_objective="o",
                cwd=str(tmp_path),
                skip_briefing=False,
            )
            driver = BurrWorkflowDriver(app, halt_after=REFUEL_TERMINAL_ACTIONS, event_queue=queue)
            events = await _collect(driver)

        # 4 briefings + 1 outline + 2 details (per unit) = 7 AgentStarted
        # events. We don't assert the exact count to keep this test
        # robust against new agent events being added, but verify the
        # briefing labels are present.
        started_names = {e.agent_name for e in events if isinstance(e, AgentStarted)}
        for label in ("Navigator", "Structuralist", "Recon", "Contrarian"):
            assert label in started_names, f"missing AgentStarted for {label}"

        completed_names = {e.agent_name for e in events if isinstance(e, AgentCompleted)}
        for label in ("Navigator", "Structuralist", "Recon", "Contrarian"):
            assert label in completed_names, f"missing AgentCompleted for {label}"

    async def test_skip_briefing_routes_around_briefing_actions(self, tmp_path: Path) -> None:
        queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
        squadron = StubRefuelSquadron()
        with (
            patch(
                "maverick.library.actions.beads.create_beads",
                new=AsyncMock(return_value=_make_bead_result()),
            ),
            patch(
                "maverick.library.actions.beads.wire_dependencies",
                new=AsyncMock(return_value=_make_wire_result()),
            ),
        ):
            app = build_refuel_application(
                squadron=squadron,
                event_queue=queue,
                raw_content="x",
                briefing_prompt="x",
                codebase_context=_empty_codebase_context(),
                open_bead_context=None,
                runway_context_text=None,
                plan_name="p",
                plan_objective="o",
                cwd=str(tmp_path),
                skip_briefing=True,
            )
            driver = BurrWorkflowDriver(app, halt_after=REFUEL_TERMINAL_ACTIONS, event_queue=queue)
            events = await _collect(driver)

        action_sequence = _by_action(events)
        assert action_sequence == [
            "init_state",
            "outline",
            "detail_fan_out",
            "validate",
            "check_validation",
            "create_beads",
            "done",
        ]
        assert squadron.built_briefings == []


class TestRefuelBurrDetailEscalation:
    async def test_transient_retries_on_same_tier_when_no_tiers_configured(
        self, tmp_path: Path
    ) -> None:
        """Transient → same-binding retry inside the budget → unit succeeds.

        With no ``tiers:`` config there is no second binding to escalate
        to, so resilience against a transient blip has to come from the
        same-tier retry budget rather than from walking a ladder of
        aliases for one model (#135).
        """
        from airframe.errors import RuntimeTransientError

        outline = _make_outline(unit_ids=("u-1",))
        # The first ``detail()`` call raises transient; the retry
        # succeeds. ``outline()`` must still work.
        squadron = StubRefuelSquadron(
            outline_payload=outline,
            detail_payloads=[_make_details(("u-1",))],
        )
        original_detail = squadron._decomposer.detail
        detail_calls = {"n": 0}

        async def _first_detail_raises(**kwargs: Any) -> SubmitDetailsPayload:
            detail_calls["n"] += 1
            if detail_calls["n"] == 1:
                raise RuntimeTransientError("rate limited")
            return await original_detail(**kwargs)

        squadron._decomposer.detail = _first_detail_raises  # type: ignore[assignment]

        queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
        with (
            patch(
                "maverick.library.actions.beads.create_beads",
                new=AsyncMock(return_value=_make_bead_result()),
            ),
            patch(
                "maverick.library.actions.beads.wire_dependencies",
                new=AsyncMock(return_value=_make_wire_result()),
            ),
        ):
            app = build_refuel_application(
                squadron=squadron,
                event_queue=queue,
                raw_content="x",
                briefing_prompt="x",
                codebase_context=_empty_codebase_context(),
                open_bead_context=None,
                runway_context_text=None,
                plan_name="p",
                plan_objective="o",
                cwd=str(tmp_path),
                skip_briefing=True,
            )
            driver = BurrWorkflowDriver(app, halt_after=REFUEL_TERMINAL_ACTIONS, event_queue=queue)
            await _collect(driver)

        _, _, state = driver.result
        # Detail eventually landed and the unit was not abandoned.
        assert state["abandoned_unit_ids"] == []
        assert any(d.get("id") == "u-1" for d in state["accumulated_details"])
        # One acquire for the outline + one for the detail unit. The
        # retry happens *within* that acquire, so no second checkout.
        acquired = squadron.decomposer_pool.acquire_calls
        assert acquired == [DEFAULT_TIER, DEFAULT_TIER]
        assert squadron.decomposer_pool.release_calls == acquired
        # The retry actually re-ran ``detail``.
        assert detail_calls["n"] == 2

    async def test_transient_escalates_through_configured_tiers(self, tmp_path: Path) -> None:
        """A configured ladder is walked in order, one acquire per rung.

        This is the behaviour that was missing: before per-tier bindings
        existed, every rung resolved to the same model, so "escalation"
        bought nothing.
        """
        from airframe.errors import RuntimeTransientError

        outline = _make_outline(unit_ids=("u-1",))
        squadron = StubRefuelSquadron(
            outline_payload=outline,
            detail_payloads=[_make_details(("u-1",))],
            escalation_ladder=(DEFAULT_TIER, "moderate", "complex"),
        )
        original_detail = squadron._decomposer.detail
        detail_calls = {"n": 0}

        # Fail every attempt on the first two rungs (the retry budget
        # gives 2 attempts per rung), then succeed on "complex".
        async def _fail_until_complex(**kwargs: Any) -> SubmitDetailsPayload:
            detail_calls["n"] += 1
            if detail_calls["n"] <= 4:
                raise RuntimeTransientError("rate limited")
            return await original_detail(**kwargs)

        squadron._decomposer.detail = _fail_until_complex  # type: ignore[assignment]

        queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
        with (
            patch(
                "maverick.library.actions.beads.create_beads",
                new=AsyncMock(return_value=_make_bead_result()),
            ),
            patch(
                "maverick.library.actions.beads.wire_dependencies",
                new=AsyncMock(return_value=_make_wire_result()),
            ),
        ):
            app = build_refuel_application(
                squadron=squadron,
                event_queue=queue,
                raw_content="x",
                briefing_prompt="x",
                codebase_context=_empty_codebase_context(),
                open_bead_context=None,
                runway_context_text=None,
                plan_name="p",
                plan_objective="o",
                cwd=str(tmp_path),
                skip_briefing=True,
            )
            driver = BurrWorkflowDriver(app, halt_after=REFUEL_TERMINAL_ACTIONS, event_queue=queue)
            await _collect(driver)

        _, _, state = driver.result
        assert state["abandoned_unit_ids"] == []
        assert any(d.get("id") == "u-1" for d in state["accumulated_details"])
        # Outline on the base tier, then one acquire per ladder rung —
        # and critically, the *configured* rungs, not a fixed list.
        assert squadron.decomposer_pool.acquire_calls == [
            DEFAULT_TIER,
            DEFAULT_TIER,
            "moderate",
            "complex",
        ]

    async def test_transient_exhausts_ladder_abandons_unit(self, tmp_path: Path) -> None:
        """Every tier raises transient → unit is abandoned, no detail recorded."""
        from airframe.errors import RuntimeTransientError

        outline = _make_outline(unit_ids=("u-1",))

        class _AlwaysRaisingDecomposer:
            def __init__(self) -> None:
                self.detail_calls = 0

            async def outline(self, **_kw: Any) -> SubmitOutlinePayload:
                return outline

            async def detail(self, **_kw: Any) -> SubmitDetailsPayload:
                self.detail_calls += 1
                raise RuntimeTransientError(f"upstream fault #{self.detail_calls}")

            async def fix(self, **_kw: Any) -> Any:
                raise AssertionError("fix should not be called when all details fail")

        always_raising = _AlwaysRaisingDecomposer()
        squadron = StubRefuelSquadron(
            outline_payload=outline,
            escalation_ladder=(DEFAULT_TIER, "moderate", "complex"),
        )
        # Outline still uses the stub agent; only swap the agent the
        # pool hands out *after* the outline action has run. Easiest:
        # leave outline alone and route subsequent acquires to the
        # raising stub.
        original_acquire = squadron.decomposer_pool.acquire

        async def _acquire_route(tier: str) -> Any:
            await original_acquire(tier)  # records the call
            if (
                always_raising.detail_calls == 0
                and tier == DEFAULT_TIER
                and (outline_acquired["n"] == 0)
            ):
                outline_acquired["n"] = 1
                return squadron._decomposer  # outline uses original
            return always_raising

        outline_acquired = {"n": 0}
        squadron.decomposer_pool.acquire = _acquire_route  # type: ignore[assignment]

        queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
        with (
            patch(
                "maverick.library.actions.beads.create_beads",
                new=AsyncMock(return_value=_make_bead_result()),
            ),
            patch(
                "maverick.library.actions.beads.wire_dependencies",
                new=AsyncMock(return_value=_make_wire_result()),
            ),
        ):
            app = build_refuel_application(
                squadron=squadron,
                event_queue=queue,
                raw_content="x",
                briefing_prompt="x",
                codebase_context=_empty_codebase_context(),
                open_bead_context=None,
                runway_context_text=None,
                plan_name="p",
                plan_objective="o",
                cwd=str(tmp_path),
                skip_briefing=True,
            )
            driver = BurrWorkflowDriver(app, halt_after=REFUEL_TERMINAL_ACTIONS, event_queue=queue)
            await _collect(driver)

        _, _, state = driver.result
        # 3 rungs x 2 attempts each (the same-tier retry budget) — the
        # ladder is exhausted only after every rung has spent its budget.
        assert always_raising.detail_calls == 6
        assert "u-1" in state["abandoned_unit_ids"]
        assert all(d.get("id") != "u-1" for d in state["accumulated_details"])
        # Outline acquired once + one acquire per rung = 4 total.
        assert len(squadron.decomposer_pool.acquire_calls) == 4
        assert len(squadron.decomposer_pool.release_calls) == 4
        # The detail-side calls walked the configured ladder in order.
        detail_tiers = squadron.decomposer_pool.acquire_calls[1:]
        assert detail_tiers == [DEFAULT_TIER, "moderate", "complex"]


class TestRefuelBurrCacheWriteBack:
    async def test_outline_and_details_written_to_cache_dir(self, tmp_path: Path) -> None:
        """Outline + per-unit details land at the expected cache paths."""
        outline = _make_outline(unit_ids=("u-1", "u-2"))
        squadron = StubRefuelSquadron(outline_payload=outline)
        cache_dir = tmp_path / "refuel-cache"

        queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
        with (
            patch(
                "maverick.library.actions.beads.create_beads",
                new=AsyncMock(return_value=_make_bead_result()),
            ),
            patch(
                "maverick.library.actions.beads.wire_dependencies",
                new=AsyncMock(return_value=_make_wire_result()),
            ),
        ):
            app = build_refuel_application(
                squadron=squadron,
                event_queue=queue,
                raw_content="x",
                briefing_prompt="x",
                codebase_context=_empty_codebase_context(),
                open_bead_context=None,
                runway_context_text=None,
                plan_name="my-plan",
                plan_objective="o",
                cwd=str(tmp_path),
                skip_briefing=True,
                cache_dir=str(cache_dir),
            )
            driver = BurrWorkflowDriver(app, halt_after=REFUEL_TERMINAL_ACTIONS, event_queue=queue)
            await _collect(driver)

        import json as _json

        outline_path = cache_dir / "outline.json"
        u1_path = cache_dir / "details" / "u-1.json"
        u2_path = cache_dir / "details" / "u-2.json"
        assert outline_path.exists()
        assert u1_path.exists()
        assert u2_path.exists()

        outline_doc = _json.loads(outline_path.read_text())
        # Versioned envelope — a drifted or mis-filed cache must be
        # rejectable on read without parsing the payload.
        assert outline_doc["schema_version"] == CACHE_SCHEMA_VERSION
        assert outline_doc["kind"] == "outline"
        outline_doc = outline_doc["payload"]
        unit_ids = {u["id"] for u in outline_doc.get("work_units") or ()}
        assert unit_ids == {"u-1", "u-2"}

        u1_doc = _json.loads(u1_path.read_text())
        assert u1_doc["schema_version"] == CACHE_SCHEMA_VERSION
        assert u1_doc["kind"] == "detail"
        assert u1_doc["payload"].get("id") == "u-1"

    async def test_briefings_written_to_cache_dir(self, tmp_path: Path) -> None:
        """``briefings.json`` lands alongside the outline/details files."""
        squadron = StubRefuelSquadron()
        cache_dir = tmp_path / "refuel-cache"

        queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
        with (
            patch(
                "maverick.workflows.refuel_maverick.actions.SUPERVISOR_TOOL_PAYLOAD_MODELS",
                {
                    "submit_navigator_brief": SubmitNavigatorBriefPayload,
                    "submit_structuralist_brief": SubmitStructuralistBriefPayload,
                    "submit_recon_brief": SubmitReconBriefPayload,
                    "submit_contrarian_brief": SubmitContrarianBriefPayload,
                },
            ),
            patch(
                "maverick.library.actions.beads.create_beads",
                new=AsyncMock(return_value=_make_bead_result()),
            ),
            patch(
                "maverick.library.actions.beads.wire_dependencies",
                new=AsyncMock(return_value=_make_wire_result()),
            ),
        ):
            app = build_refuel_application(
                squadron=squadron,
                event_queue=queue,
                raw_content="x",
                briefing_prompt="x",
                codebase_context=_empty_codebase_context(),
                open_bead_context=None,
                runway_context_text=None,
                plan_name="my-plan",
                plan_objective="o",
                cwd=str(tmp_path),
                skip_briefing=False,
                cache_dir=str(cache_dir),
            )
            driver = BurrWorkflowDriver(app, halt_after=REFUEL_TERMINAL_ACTIONS, event_queue=queue)
            await _collect(driver)

        import json as _json

        briefings_path = cache_dir / "briefings.json"
        assert briefings_path.exists()
        doc = _json.loads(briefings_path.read_text())
        assert doc["schema_version"] == CACHE_SCHEMA_VERSION
        assert doc["kind"] == "briefings"
        doc = doc["payload"]
        assert set(doc.keys()) == {
            "navigator",
            "structuralist",
            "recon",
            "contrarian",
        }

    async def test_empty_cache_dir_is_a_noop(self, tmp_path: Path) -> None:
        """Default ``cache_dir=''`` writes nothing — preserves prior behaviour."""
        squadron = StubRefuelSquadron()
        cache_dir = tmp_path / "refuel-cache"

        queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
        with (
            patch(
                "maverick.library.actions.beads.create_beads",
                new=AsyncMock(return_value=_make_bead_result()),
            ),
            patch(
                "maverick.library.actions.beads.wire_dependencies",
                new=AsyncMock(return_value=_make_wire_result()),
            ),
        ):
            app = build_refuel_application(
                squadron=squadron,
                event_queue=queue,
                raw_content="x",
                briefing_prompt="x",
                codebase_context=_empty_codebase_context(),
                open_bead_context=None,
                runway_context_text=None,
                plan_name="p",
                plan_objective="o",
                cwd=str(tmp_path),
                skip_briefing=True,
            )
            driver = BurrWorkflowDriver(app, halt_after=REFUEL_TERMINAL_ACTIONS, event_queue=queue)
            await _collect(driver)

        assert not cache_dir.exists()


class TestRefuelBurrCacheReadBack:
    """A populated ``refuel-cache/`` short-circuits regeneration (#135).

    The write side landed first and nothing consumed it, so every re-run
    paid full agent cost for evidence already sitting on disk.
    """

    @staticmethod
    def _write(path: Path, kind: str, payload: Any, *, version: int | None = None) -> None:
        import json as _json

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            _json.dumps(
                {
                    "schema_version": CACHE_SCHEMA_VERSION if version is None else version,
                    "kind": kind,
                    "payload": payload,
                }
            )
        )

    async def _run(
        self, squadron: StubRefuelSquadron, tmp_path: Path, cache_dir: Path, **kwargs: Any
    ) -> Any:
        queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
        with (
            patch(
                "maverick.library.actions.beads.create_beads",
                new=AsyncMock(return_value=_make_bead_result()),
            ),
            patch(
                "maverick.library.actions.beads.wire_dependencies",
                new=AsyncMock(return_value=_make_wire_result()),
            ),
        ):
            app = build_refuel_application(
                squadron=squadron,
                event_queue=queue,
                raw_content="x",
                briefing_prompt="x",
                codebase_context=_empty_codebase_context(),
                open_bead_context=None,
                runway_context_text=None,
                plan_name="p",
                plan_objective="o",
                cwd=str(tmp_path),
                cache_dir=str(cache_dir),
                **kwargs,
            )
            driver = BurrWorkflowDriver(app, halt_after=REFUEL_TERMINAL_ACTIONS, event_queue=queue)
            await _collect(driver)
        return driver.result[2]

    async def test_cached_outline_and_details_skip_the_decomposer(self, tmp_path: Path) -> None:
        outline = _make_outline(unit_ids=("u-1", "u-2"))
        cache_dir = tmp_path / "refuel-cache"
        self._write(
            cache_dir / "outline.json",
            "outline",
            _dump(outline),
        )
        for uid in ("u-1", "u-2"):
            self._write(
                cache_dir / "details" / f"{uid}.json",
                "detail",
                {"id": uid, "instructions": f"cached {uid}", "acceptance_criteria": []},
            )

        squadron = StubRefuelSquadron(outline_payload=outline)
        state = await self._run(squadron, tmp_path, cache_dir, skip_briefing=True)

        # Zero decomposer checkouts: neither the outline nor any detail
        # needed an agent.
        assert squadron.decomposer_pool.acquire_calls == []
        assert state["abandoned_unit_ids"] == []
        assert {d["id"] for d in state["accumulated_details"]} == {"u-1", "u-2"}
        assert any("cached u-1" in d.get("instructions", "") for d in state["accumulated_details"])

    async def test_partial_detail_cache_regenerates_only_the_gap(self, tmp_path: Path) -> None:
        """A run that abandoned half its units re-requests only those."""
        outline = _make_outline(unit_ids=("u-1", "u-2"))
        cache_dir = tmp_path / "refuel-cache"
        self._write(cache_dir / "outline.json", "outline", _dump(outline))
        self._write(
            cache_dir / "details" / "u-1.json",
            "detail",
            {"id": "u-1", "instructions": "cached u-1", "acceptance_criteria": []},
        )

        squadron = StubRefuelSquadron(
            outline_payload=outline,
            detail_payloads=[_make_details(("u-2",))],
        )
        state = await self._run(squadron, tmp_path, cache_dir, skip_briefing=True)

        # Exactly one detail checkout — for the uncached unit.
        assert squadron.decomposer_pool.acquire_calls == [DEFAULT_TIER]
        assert {d["id"] for d in state["accumulated_details"]} == {"u-1", "u-2"}

    async def test_cached_briefs_skip_all_four_briefing_agents(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "refuel-cache"
        self._write(
            cache_dir / "briefings.json",
            "briefings",
            {role: {"summary": f"cached {role}"} for role in _BRIEF_PAYLOADS},
        )

        squadron = StubRefuelSquadron()
        state = await self._run(squadron, tmp_path, cache_dir, skip_briefing=False)

        # No briefing agent was ever built, let alone called.
        assert squadron.built_briefings == []
        assert set(state["briefs"]) == set(_BRIEF_PAYLOADS)
        # The markdown is still rendered — it's a pure function of briefs.
        assert state["briefing_markdown"]

    async def test_stale_schema_version_fails_closed(self, tmp_path: Path) -> None:
        """A cache from a different schema is discarded, not adapted.

        Regenerating costs budget; reusing a drifted outline silently
        produces beads that don't match the plan.
        """
        outline = _make_outline(unit_ids=("u-1",))
        cache_dir = tmp_path / "refuel-cache"
        self._write(
            cache_dir / "outline.json",
            "outline",
            _dump(outline),
            version=CACHE_SCHEMA_VERSION + 1,
        )

        squadron = StubRefuelSquadron(outline_payload=outline)
        await self._run(squadron, tmp_path, cache_dir, skip_briefing=True)

        # Two checkouts — one to regenerate the outline, one for the
        # single unit's detail. A cache hit would have made it one.
        assert squadron.decomposer_pool.acquire_calls == [DEFAULT_TIER, DEFAULT_TIER]

    async def test_wrong_kind_fails_closed(self, tmp_path: Path) -> None:
        """A detail file sitting in the outline slot must not be parsed
        as an outline."""
        outline = _make_outline(unit_ids=("u-1",))
        cache_dir = tmp_path / "refuel-cache"
        self._write(cache_dir / "outline.json", "detail", _dump(outline))

        squadron = StubRefuelSquadron(outline_payload=outline)
        await self._run(squadron, tmp_path, cache_dir, skip_briefing=True)

        # Outline regenerated (2 checkouts, not 1) — see the
        # stale-schema case for the same reasoning.
        assert squadron.decomposer_pool.acquire_calls == [DEFAULT_TIER, DEFAULT_TIER]

    async def test_corrupt_json_fails_closed(self, tmp_path: Path) -> None:
        outline = _make_outline(unit_ids=("u-1",))
        cache_dir = tmp_path / "refuel-cache"
        (cache_dir).mkdir(parents=True, exist_ok=True)
        (cache_dir / "outline.json").write_text("{not json")

        squadron = StubRefuelSquadron(outline_payload=outline)
        await self._run(squadron, tmp_path, cache_dir, skip_briefing=True)

        # Outline regenerated (2 checkouts, not 1) — see the
        # stale-schema case for the same reasoning.
        assert squadron.decomposer_pool.acquire_calls == [DEFAULT_TIER, DEFAULT_TIER]

    async def test_detail_for_a_dropped_unit_is_not_merged(self, tmp_path: Path) -> None:
        """A regenerated outline may drop a unit; its stale cached detail
        must not leak into the merge."""
        outline = _make_outline(unit_ids=("u-1",))
        cache_dir = tmp_path / "refuel-cache"
        self._write(cache_dir / "outline.json", "outline", _dump(outline))
        for uid in ("u-1", "u-obsolete"):
            self._write(
                cache_dir / "details" / f"{uid}.json",
                "detail",
                {"id": uid, "instructions": f"cached {uid}", "acceptance_criteria": []},
            )

        squadron = StubRefuelSquadron(outline_payload=outline)
        state = await self._run(squadron, tmp_path, cache_dir, skip_briefing=True)

        assert {d["id"] for d in state["accumulated_details"]} == {"u-1"}


class TestRefuelBurrQuotaHandling:
    """Provider quota aborts the run; it does not walk the tier ladder (#135).

    Quota exhaustion is account-wide and time-bound: no other model,
    tier, or retry makes it go away before the limit resets. Treating it
    like an ordinary failure meant every remaining unit paid a full
    round-trip to be told the same thing, and then beads were created
    from a truncated fan-out.
    """

    @staticmethod
    async def _run_expecting_quota(
        squadron: StubRefuelSquadron, tmp_path: Path, **kwargs: Any
    ) -> BaseException | None:
        queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
        with (
            patch(
                "maverick.library.actions.beads.create_beads",
                new=AsyncMock(return_value=_make_bead_result()),
            ),
            patch(
                "maverick.library.actions.beads.wire_dependencies",
                new=AsyncMock(return_value=_make_wire_result()),
            ),
        ):
            app = build_refuel_application(
                squadron=squadron,
                event_queue=queue,
                raw_content="x",
                briefing_prompt="x",
                codebase_context=_empty_codebase_context(),
                open_bead_context=None,
                runway_context_text=None,
                plan_name="p",
                plan_objective="o",
                cwd=str(tmp_path),
                skip_briefing=True,
                **kwargs,
            )
            driver = BurrWorkflowDriver(app, halt_after=REFUEL_TERMINAL_ACTIONS, event_queue=queue)
            await _collect(driver)
            # The driver defers an action's exception to ``.result`` so
            # the event stream always drains cleanly first.
            try:
                _ = driver.result
            except BaseException as exc:  # noqa: BLE001 — the assertion subject
                return exc
        return None

    async def test_budget_exceeded_aborts_without_climbing_the_ladder(
        self, tmp_path: Path
    ) -> None:

        from maverick.exceptions.quota import ProviderQuotaError

        outline = _make_outline(unit_ids=("u-1",))
        squadron = StubRefuelSquadron(
            outline_payload=outline,
            escalation_ladder=(DEFAULT_TIER, "moderate", "complex"),
        )
        calls = {"n": 0}

        async def _quota(**_kw: Any) -> SubmitDetailsPayload:
            calls["n"] += 1
            _raise_budget("monthly usage limit exceeded")

        squadron._decomposer.detail = _quota  # type: ignore[assignment]

        exc = await self._run_expecting_quota(squadron, tmp_path)

        assert isinstance(exc, ProviderQuotaError)
        # One attempt total: no same-tier retry, no escalation to
        # "moderate" or "complex".
        assert calls["n"] == 1
        assert squadron.decomposer_pool.acquire_calls == [DEFAULT_TIER, DEFAULT_TIER]

    async def test_quota_reported_as_transient_is_not_retried(self, tmp_path: Path) -> None:
        """Some providers dress a hard limit up as a 429/5xx.

        Classifying by message keeps those off the retry-and-escalate
        path that a genuine transient belongs on.
        """
        from airframe.errors import RuntimeTransientError

        from maverick.exceptions.quota import ProviderQuotaError

        outline = _make_outline(unit_ids=("u-1",))
        squadron = StubRefuelSquadron(
            outline_payload=outline,
            escalation_ladder=(DEFAULT_TIER, "complex"),
        )
        calls = {"n": 0}

        async def _quota_as_transient(**_kw: Any) -> SubmitDetailsPayload:
            calls["n"] += 1
            raise RuntimeTransientError("429: usage limit reached, resets 6am UTC")

        squadron._decomposer.detail = _quota_as_transient  # type: ignore[assignment]

        exc = await self._run_expecting_quota(squadron, tmp_path)

        assert isinstance(exc, ProviderQuotaError)
        assert calls["n"] == 1
        # The reset hint is parsed off the message for the operator.
        assert exc.reset_time is not None
        assert "6am" in exc.reset_time

    async def test_genuine_transient_still_retries_and_escalates(self, tmp_path: Path) -> None:
        """Guard the other side: the quota check must not swallow real
        transients, which *do* deserve the ladder."""
        from airframe.errors import RuntimeTransientError

        outline = _make_outline(unit_ids=("u-1",))
        squadron = StubRefuelSquadron(
            outline_payload=outline,
            detail_payloads=[_make_details(("u-1",))],
            escalation_ladder=(DEFAULT_TIER, "complex"),
        )
        original_detail = squadron._decomposer.detail
        calls = {"n": 0}

        async def _transient_then_ok(**kwargs: Any) -> SubmitDetailsPayload:
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeTransientError("503 service unavailable")
            return await original_detail(**kwargs)

        squadron._decomposer.detail = _transient_then_ok  # type: ignore[assignment]

        exc = await self._run_expecting_quota(squadron, tmp_path)

        assert exc is None
        assert calls["n"] == 2

    async def test_completed_units_are_cached_before_the_abort(self, tmp_path: Path) -> None:
        """The abort is only tolerable because progress survives it.

        Units that finished before the limit hit are on disk, so the
        re-run after reset resumes instead of starting over.
        """

        outline = _make_outline(unit_ids=("u-1", "u-2"))
        cache_dir = tmp_path / "refuel-cache"
        squadron = StubRefuelSquadron(outline_payload=outline)
        original_detail = squadron._decomposer.detail
        seen: list[str] = []

        async def _one_then_quota(**kwargs: Any) -> SubmitDetailsPayload:
            unit_ids = kwargs.get("unit_ids") or ()
            seen.extend(unit_ids)
            if len(seen) > 1:
                _raise_budget("you have no quota left")
            return await original_detail(**kwargs)

        squadron._decomposer.detail = _one_then_quota  # type: ignore[assignment]

        from maverick.exceptions.quota import ProviderQuotaError

        # pool_size=1 so the two units are strictly ordered.
        exc = await self._run_expecting_quota(
            squadron, tmp_path, cache_dir=str(cache_dir), decomposer_pool_size=1
        )

        # The run aborted rather than creating beads from a fan-out that
        # only covered half the plan...
        assert isinstance(exc, ProviderQuotaError)
        # ...and the half that did complete survived the abort.
        cached = sorted(p.name for p in (cache_dir / "details").glob("*.json"))
        assert cached == ["u-1.json"]


class TestRefuelBurrGraphValidationLoop:
    async def test_fix_loop_runs_when_validation_fails_then_passes(self, tmp_path: Path) -> None:
        """First validate produces gaps → request_fix → validate (passes).

        Driven by an *overloaded* work unit rather than untraced success
        criteria. Untraced criteria are advisory now — they are routinely
        cross-cutting constraints no work unit can carry — so they no
        longer reach the fix loop. Overload still does, and it is the one
        the fixer can actually act on: split the unit.
        """
        outline = _make_outline(unit_ids=("u-1",))
        # First detail call: one unit claiming 13 SC refs — over the
        # hard limit of 12, so validation fails.
        empty_details = SubmitDetailsPayload(
            details=(
                WorkUnitDetailPayload(
                    id="u-1",
                    instructions="todo",
                    acceptance_criteria=tuple(
                        AcceptanceCriterionPayload(text=f"ac-{i}", trace_ref=f"SC-{i:03d}")
                        for i in range(1, 14)
                    ),
                    verification=("pytest -k todo",),
                    test_specification="",
                ),
            )
        )
        # Fix delivers a slimmed-down unit that is back under the limit.
        fix_payload = SubmitFixPayload(
            work_units=(),
            details=(
                WorkUnitDetailPayload(
                    id="u-1",
                    instructions="done",
                    acceptance_criteria=(
                        AcceptanceCriterionPayload(text="ac-1", trace_ref="SC-001"),
                    ),
                    verification=("pytest",),
                    test_specification="",
                ),
            ),
        )

        squadron = StubRefuelSquadron(
            outline_payload=outline,
            detail_payloads=[empty_details],
            fix_payloads=[fix_payload],
        )

        queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
        with (
            patch(
                "maverick.library.actions.beads.create_beads",
                new=AsyncMock(return_value=_make_bead_result()),
            ),
            patch(
                "maverick.library.actions.beads.wire_dependencies",
                new=AsyncMock(return_value=_make_wire_result()),
            ),
        ):
            app = build_refuel_application(
                squadron=squadron,
                event_queue=queue,
                raw_content="x",
                briefing_prompt="x",
                codebase_context=_empty_codebase_context(),
                open_bead_context=None,
                runway_context_text=None,
                plan_name="p",
                plan_objective="o",
                cwd=str(tmp_path),
                skip_briefing=True,
                # sc_count drives the overload check's ref accounting;
                # the trigger is the 13-ref unit, not coverage.
                success_criteria_count=1,
                expected_sc_refs=("SC-001",),
            )
            driver = BurrWorkflowDriver(app, halt_after=REFUEL_TERMINAL_ACTIONS, event_queue=queue)
            events = await _collect(driver)

        action_sequence = _by_action(events)
        # We expect at least: init → outline → detail → validate (fail)
        # → check_validation → request_fix → validate (pass) →
        # check_validation → create_beads → done.
        assert "request_fix" in action_sequence
        assert action_sequence.count("validate") >= 2
        _, _, state = driver.result
        assert state["fix_rounds"] >= 1

    async def test_fix_round_merges_new_work_units_into_outline(self, tmp_path: Path) -> None:
        """``SubmitFixPayload.work_units`` deltas are merged into the outline.

        Models the "fixer splits an overloaded unit" path: the outline
        starts with one unit, the fix returns a second unit + a
        replacement detail for both. After ``request_fix``, the outline
        should contain both units so downstream actions see the split.
        """
        outline = _make_outline(unit_ids=("u-1",))
        # Overloaded unit (13 SC refs > the hard limit of 12) — the one
        # coverage failure the fixer can genuinely act on, and the
        # scenario this test is named for.
        empty_details = SubmitDetailsPayload(
            details=(
                WorkUnitDetailPayload(
                    id="u-1",
                    instructions="todo",
                    acceptance_criteria=tuple(
                        AcceptanceCriterionPayload(text=f"ac-{i}", trace_ref=f"SC-{i:03d}")
                        for i in range(1, 14)
                    ),
                    verification=("pytest -k todo",),
                    test_specification="",
                ),
            )
        )
        # Fix splits u-1 → u-1-a + u-1-b (new work_units appear).
        new_unit_a = WorkUnitOutlinePayload(
            id="u-1-a",
            task="half a",
            sequence=2,
            depends_on=(),
            file_scope=FileScopePayload(),
            complexity="simple",
        )
        new_unit_b = WorkUnitOutlinePayload(
            id="u-1-b",
            task="half b",
            sequence=3,
            depends_on=(),
            file_scope=FileScopePayload(),
            complexity="simple",
        )
        fix_payload = SubmitFixPayload(
            work_units=(new_unit_a, new_unit_b),
            details=(
                # The split also slims the original unit; without this
                # u-1 would still carry 13 refs and fail again.
                WorkUnitDetailPayload(
                    id="u-1",
                    instructions="slimmed",
                    acceptance_criteria=(
                        AcceptanceCriterionPayload(text="ac-1", trace_ref="SC-001"),
                    ),
                    verification=("pytest",),
                    test_specification="",
                ),
                WorkUnitDetailPayload(
                    id="u-1-a",
                    instructions="done a",
                    acceptance_criteria=(
                        AcceptanceCriterionPayload(text="ac-a", trace_ref="SC-001"),
                    ),
                    verification=("pytest",),
                    test_specification="",
                ),
                WorkUnitDetailPayload(
                    id="u-1-b",
                    instructions="done b",
                    acceptance_criteria=(
                        AcceptanceCriterionPayload(text="ac-b", trace_ref="SC-001"),
                    ),
                    verification=("pytest",),
                    test_specification="",
                ),
            ),
        )

        squadron = StubRefuelSquadron(
            outline_payload=outline,
            detail_payloads=[empty_details],
            fix_payloads=[fix_payload],
        )

        queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
        with (
            patch(
                "maverick.library.actions.beads.create_beads",
                new=AsyncMock(return_value=_make_bead_result()),
            ),
            patch(
                "maverick.library.actions.beads.wire_dependencies",
                new=AsyncMock(return_value=_make_wire_result()),
            ),
        ):
            app = build_refuel_application(
                squadron=squadron,
                event_queue=queue,
                raw_content="x",
                briefing_prompt="x",
                codebase_context=_empty_codebase_context(),
                open_bead_context=None,
                runway_context_text=None,
                plan_name="p",
                plan_objective="o",
                cwd=str(tmp_path),
                skip_briefing=True,
                success_criteria_count=1,
                expected_sc_refs=("SC-001",),
            )
            driver = BurrWorkflowDriver(app, halt_after=REFUEL_TERMINAL_ACTIONS, event_queue=queue)
            await _collect(driver)

        _, _, state = driver.result
        outline_ids = sorted(u["id"] for u in state["outline"]["work_units"])
        assert outline_ids == ["u-1", "u-1-a", "u-1-b"], (
            f"fix-round work_units not merged into outline: {outline_ids}"
        )
