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
    ) -> None:
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


class TestRefuelBurrGraphValidationLoop:
    async def test_fix_loop_runs_when_validation_fails_then_passes(self, tmp_path: Path) -> None:
        """First validate produces gaps → request_fix → validate (passes)."""
        # Outline has one unit with no AC, first detail leaves AC empty,
        # fix delivers a corrected detail.
        outline = _make_outline(unit_ids=("u-1",))
        # First detail call: AC without trace_ref → coverage gap.
        empty_details = SubmitDetailsPayload(
            details=(
                WorkUnitDetailPayload(
                    id="u-1",
                    instructions="todo",
                    acceptance_criteria=(AcceptanceCriterionPayload(text="todo ac"),),
                    verification=("pytest -k todo",),
                    test_specification="",
                ),
            )
        )
        # Fix delivers AC with the expected trace_ref so coverage closes.
        fix_payload = SubmitFixPayload(
            work_units=(),
            details=(
                WorkUnitDetailPayload(
                    id="u-1",
                    instructions="done",
                    acceptance_criteria=(
                        AcceptanceCriterionPayload(text="ac-1", trace_ref="SC-1"),
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
                # Pass non-zero sc_count so the validator notices the
                # missing acceptance criteria in the first detail pass.
                success_criteria_count=1,
                expected_sc_refs=("SC-1",),
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
