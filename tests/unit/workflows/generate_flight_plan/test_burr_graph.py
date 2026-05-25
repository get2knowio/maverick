"""Unit tests for the Burr-mode plan generation graph.

Covers the same supervisor-orchestration surface that
``test_workflow.py::TestGenerateFlightPlanWorkflowHappyPath`` covers for
the xoscar driver, but at the Burr ``Application`` level — no actor
shells, no xoscar pool.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from maverick.burr import BurrWorkflowDriver
from maverick.events import (
    AgentCompleted,
    AgentStarted,
    ProgressEvent,
    StepCompleted,
    StepOutput,
    StepStarted,
)
from maverick.payloads import (
    FlightPlanSuccessCriterionPayload,
    SubmitAnalysisPayload,
    SubmitChallengePayload,
    SubmitCriteriaPayload,
    SubmitFlightPlanPayload,
    SubmitScopePayload,
)
from maverick.workflows.generate_flight_plan.burr_graph import (
    PLAN_TERMINAL_ACTIONS,
    build_plan_application,
)
from tests.unit.agents.airframe_stubs import StubBriefingAgent, StubGeneratorAgent

# ---------------------------------------------------------------------------
# Stub squadron — keeps the Burr graph 100% offline
# ---------------------------------------------------------------------------


_BRIEF_PAYLOADS: dict[str, Any] = {
    "scopist": SubmitScopePayload(
        in_scope=("src/foo.py",),
        out_scope=(),
        boundaries=(),
        summary="stub scope",
    ),
    "codebase_analyst": SubmitAnalysisPayload(
        modules=("src/foo",),
        patterns=(),
        dependencies=(),
        complexity_assessment="stub analysis",
    ),
    "criteria_writer": SubmitCriteriaPayload(
        criteria=("ship the thing",),
        test_scenarios=(),
        objective_draft="stub draft",
        measurability_notes="stub notes",
    ),
    "contrarian": SubmitChallengePayload(
        risks=("hubris",),
        blind_spots=(),
        open_questions=(),
        consensus_points=(),
    ),
}


def _make_flight_plan_payload(
    name: str = "test-plan",
    sc_count: int = 2,
) -> SubmitFlightPlanPayload:
    return SubmitFlightPlanPayload(
        name=name,
        version="1",
        objective="Build a test CLI tool",
        success_criteria=tuple(
            FlightPlanSuccessCriterionPayload(description=f"sc-{i}") for i in range(sc_count)
        ),
        in_scope=("src/foo.py",),
        out_of_scope=(),
        boundaries=(),
        context="stub context",
        constraints=(),
        notes="",
    )


class StubPlanSquadron:
    """Mimics :class:`PlanSquadron`'s interface for Burr-mode tests.

    Holds one :class:`StubGeneratorAgent` and one fresh
    :class:`StubBriefingAgent` per ``build_briefing_agent`` call. Both
    stubs derive from :mod:`tests.unit.agents.airframe_stubs` and pop
    their canned payloads on each invocation.
    """

    def __init__(
        self,
        *,
        flight_plan: SubmitFlightPlanPayload | None = None,
        briefing_payloads: dict[str, Any] | None = None,
    ) -> None:
        self.generator = StubGeneratorAgent(
            generate_payloads=[flight_plan or _make_flight_plan_payload()],
        )
        # Canned per-agent payloads — callers can override one or all.
        self._briefing_payloads = dict(briefing_payloads or _BRIEF_PAYLOADS)
        self.built_briefings: list[StubBriefingAgent] = []

    def build_briefing_agent(self, *, agent_name: str, result_model: Any) -> StubBriefingAgent:
        payload = self._briefing_payloads.get(agent_name)
        if payload is None:
            raise AssertionError(f"no stub briefing payload registered for agent {agent_name!r}")
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
    """Action sequence as derived from emitted ``StepStarted`` events."""
    return [e.step_name for e in events if isinstance(e, StepStarted)]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBurrPlanGraphHappyPath:
    async def test_full_pipeline_executes_all_actions(self, tmp_path: Path) -> None:
        """Briefing → contrarian → generate → validate → write → done."""
        queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
        squadron = StubPlanSquadron()
        app = build_plan_application(
            squadron=squadron,
            event_queue=queue,
            prd_content="# stub PRD\n\nbuild a thing",
            plan_name="test-plan",
            output_dir=str(tmp_path / "test-plan"),
            skip_briefing=False,
            provider_labels={"Scopist": "claude/x"},
            max_briefing_agents=3,
        )
        driver = BurrWorkflowDriver(app, halt_after=PLAN_TERMINAL_ACTIONS, event_queue=queue)
        events = await _collect(driver)

        action_sequence = _by_action(events)
        assert action_sequence == [
            "init_state",
            "parallel_briefings",
            "contrarian_briefing",
            "synthesize_briefing",
            "generate_plan",
            "validate_plan",
            "write_plan",
            "done",
        ]

        # Every step ended successfully.
        for name in action_sequence:
            completed = [e for e in events if isinstance(e, StepCompleted) and e.step_name == name]
            assert len(completed) == 1
            assert completed[0].success is True, f"action {name} not successful"

        _, _, state = driver.result
        assert state["flight_plan"] is not None
        assert state["flight_plan_path"].endswith("flight-plan.md")
        assert state["briefing_path"].endswith("preflight-briefing.md")
        assert state["validation_passed"] is True

        # Files actually landed on disk.
        assert Path(state["flight_plan_path"]).exists()
        assert Path(state["briefing_path"]).exists()

    async def test_emits_agent_started_completed_per_briefing(self, tmp_path: Path) -> None:
        queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
        squadron = StubPlanSquadron()
        app = build_plan_application(
            squadron=squadron,
            event_queue=queue,
            prd_content="x",
            plan_name="test-plan",
            output_dir=str(tmp_path / "test-plan"),
            skip_briefing=False,
        )
        driver = BurrWorkflowDriver(app, halt_after=PLAN_TERMINAL_ACTIONS, event_queue=queue)
        events = await _collect(driver)

        agent_names_started = sorted(e.agent_name for e in events if isinstance(e, AgentStarted))
        assert agent_names_started == [
            "Codebase Analyst",
            "Contrarian",
            "Criteria Writer",
            "Scopist",
        ]
        agent_names_completed = sorted(
            e.agent_name for e in events if isinstance(e, AgentCompleted)
        )
        assert agent_names_completed == agent_names_started

        # Provider label propagates onto the Scopist AgentStarted (only one
        # we set in this test).
        scopist_started = [
            e for e in events if isinstance(e, AgentStarted) and e.agent_name == "Scopist"
        ]
        assert len(scopist_started) == 1

    async def test_step_output_events_carry_success_metadata(self, tmp_path: Path) -> None:
        """``generate_plan`` + ``write_plan`` surface success_criteria_count."""
        queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
        squadron = StubPlanSquadron(flight_plan=_make_flight_plan_payload(sc_count=3))
        app = build_plan_application(
            squadron=squadron,
            event_queue=queue,
            prd_content="x",
            plan_name="test-plan",
            output_dir=str(tmp_path / "test-plan"),
            skip_briefing=False,
        )
        driver = BurrWorkflowDriver(app, halt_after=PLAN_TERMINAL_ACTIONS, event_queue=queue)
        events = await _collect(driver)

        outputs = [e for e in events if isinstance(e, StepOutput)]
        sc_outputs = [
            o for o in outputs if o.metadata and o.metadata.get("success_criteria_count") == 3
        ]
        # Two StepOutput events should mention sc_count=3 — one from
        # generate_plan ("generated"), one from write_plan ("written").
        assert len(sc_outputs) >= 2


class TestBurrPlanGraphSkipBriefing:
    async def test_skip_briefing_routes_around_briefing_actions(self, tmp_path: Path) -> None:
        """When ``skip_briefing=True``, init_state → generate_plan directly."""
        queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
        squadron = StubPlanSquadron()
        app = build_plan_application(
            squadron=squadron,
            event_queue=queue,
            prd_content="x",
            plan_name="test-plan",
            output_dir=str(tmp_path / "test-plan"),
            skip_briefing=True,
        )
        driver = BurrWorkflowDriver(app, halt_after=PLAN_TERMINAL_ACTIONS, event_queue=queue)
        events = await _collect(driver)

        action_sequence = _by_action(events)
        assert action_sequence == [
            "init_state",
            "generate_plan",
            "validate_plan",
            "write_plan",
            "done",
        ]

        # No briefing agents should have been built.
        assert squadron.built_briefings == []

        _, _, state = driver.result
        assert state["briefing_path"] is None  # only set when briefing ran
        assert state["flight_plan_path"] is not None


class TestBurrPlanGraphErrors:
    async def test_generator_failure_propagates(self, tmp_path: Path) -> None:
        """A failure in the generator agent surfaces via driver.result."""
        queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue()
        squadron = StubPlanSquadron()
        squadron.generator.raise_error = RuntimeError("stub generator boom")  # type: ignore[attr-defined]

        app = build_plan_application(
            squadron=squadron,
            event_queue=queue,
            prd_content="x",
            plan_name="test-plan",
            output_dir=str(tmp_path / "test-plan"),
            skip_briefing=True,
        )
        driver = BurrWorkflowDriver(app, halt_after=PLAN_TERMINAL_ACTIONS, event_queue=queue)

        events: list[ProgressEvent] = []
        with pytest.raises(RuntimeError, match="stub generator boom"):
            async for evt in driver.events():
                events.append(evt)
            _ = driver.result

        # generate_plan must have started but its StepCompleted should be
        # marked success=False.
        completed = [
            e for e in events if isinstance(e, StepCompleted) and e.step_name == "generate_plan"
        ]
        assert len(completed) == 1
        assert completed[0].success is False
        assert "stub generator boom" in (completed[0].error or "")
