"""Unit tests for GenerateFlightPlanWorkflow."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from maverick.events import (
    StepCompleted,
    WorkflowCompleted,
    WorkflowStarted,
)
from maverick.exceptions import WorkflowError
from maverick.executor.result import ExecutorResult
from maverick.workflows.generate_flight_plan.constants import (
    GENERATE,
    READ_PRD,
    VALIDATE,
    WORKFLOW_NAME,
    WRITE_FLIGHT_PLAN,
)
from maverick.workflows.generate_flight_plan.models import FlightPlanOutput
from maverick.workflows.generate_flight_plan.workflow import (
    GenerateFlightPlanWorkflow,
    _build_generate_prompt,
    _convert_output_to_flight_plan,
)

_ALL_STEPS = [READ_PRD, GENERATE, WRITE_FLIGHT_PLAN, VALIDATE]

_MODULE = "maverick.workflows.generate_flight_plan.workflow"


def _make_flight_plan_output(name: str = "test-plan") -> FlightPlanOutput:
    """Create a valid FlightPlanOutput for testing."""
    return FlightPlanOutput(
        name=name,
        version="1",
        objective="Build a test CLI tool",
        success_criteria=["Unit tests pass", "CLI outputs greeting"],
        in_scope=["src/main.py", "tests/"],
        out_of_scope=["documentation", "CI/CD"],
        boundaries=["Python 3.10+ only"],
        context="This is a test project",
        constraints=["Must use Click framework"],
        notes="No additional notes",
    )


def _make_executor_result(
    output: FlightPlanOutput | None = None,
) -> ExecutorResult:
    """Create an ExecutorResult wrapping a FlightPlanOutput."""
    return ExecutorResult(
        output=output or _make_flight_plan_output(),
        success=True,
        usage=None,
        events=(),
    )


def _make_workflow(
    mock_config: MagicMock,
    mock_registry: MagicMock,
    mock_step_executor: AsyncMock,
) -> GenerateFlightPlanWorkflow:
    """Create a GenerateFlightPlanWorkflow with mocked dependencies."""
    return GenerateFlightPlanWorkflow(
        config=mock_config,
        registry=mock_registry,
        step_executor=mock_step_executor,
        workflow_name=WORKFLOW_NAME,
    )


async def _collect_events(
    workflow: GenerateFlightPlanWorkflow,
    inputs: dict,
) -> list:
    """Collect all events from a workflow execution."""
    events = []
    async for event in workflow.execute(inputs):
        events.append(event)
    return events


# ---------------------------------------------------------------------------
# Prompt building tests
# ---------------------------------------------------------------------------


class TestBuildGeneratePrompt:
    """Tests for the prompt builder function."""

    def test_prompt_contains_prd_content(self) -> None:
        """Prompt includes the raw PRD content."""
        from datetime import date

        prompt = _build_generate_prompt(
            "Build a hello world CLI", "my-plan", date.today()
        )
        assert "Build a hello world CLI" in prompt

    def test_prompt_contains_name(self) -> None:
        """Prompt includes the flight plan name."""
        from datetime import date

        prompt = _build_generate_prompt("Some PRD", "greet-cli", date.today())
        assert "greet-cli" in prompt

    def test_prompt_contains_date(self) -> None:
        """Prompt includes the date."""
        from datetime import date

        today = date(2026, 2, 28)
        prompt = _build_generate_prompt("Some PRD", "test", today)
        assert "2026-02-28" in prompt

    def test_prompt_without_briefing(self) -> None:
        """Prompt without briefing content has no briefing section."""
        from datetime import date

        prompt = _build_generate_prompt("PRD", "test", date.today())
        assert "Pre-Flight Briefing" not in prompt

    def test_prompt_with_briefing(self) -> None:
        """Prompt with briefing content includes the briefing section."""
        from datetime import date

        prompt = _build_generate_prompt(
            "PRD", "test", date.today(), briefing_content="## Scope\n- Item A"
        )
        assert "## Pre-Flight Briefing" in prompt
        assert "## Scope" in prompt
        assert "- Item A" in prompt


# ---------------------------------------------------------------------------
# Output conversion tests
# ---------------------------------------------------------------------------


class TestConvertOutputToFlightPlan:
    """Tests for converting agent output to FlightPlan model."""

    def test_basic_conversion(self) -> None:
        """FlightPlanOutput is correctly converted to FlightPlan."""
        from datetime import date

        output = _make_flight_plan_output()
        plan = _convert_output_to_flight_plan(output, date(2026, 2, 28))

        assert plan.name == "test-plan"
        assert plan.version == "1"
        assert plan.created == date(2026, 2, 28)
        assert plan.objective == "Build a test CLI tool"
        assert len(plan.success_criteria) == 2
        assert all(not sc.checked for sc in plan.success_criteria)
        assert len(plan.scope.in_scope) == 2
        assert len(plan.scope.out_of_scope) == 2
        assert len(plan.scope.boundaries) == 1
        assert plan.context == "This is a test project"
        assert len(plan.constraints) == 1
        assert plan.notes == "No additional notes"

    def test_success_criteria_all_unchecked(self) -> None:
        """All success criteria in the converted plan are unchecked."""
        from datetime import date

        output = _make_flight_plan_output()
        plan = _convert_output_to_flight_plan(output, date.today())
        for sc in plan.success_criteria:
            assert sc.checked is False


# ---------------------------------------------------------------------------
# Workflow execution tests
# ---------------------------------------------------------------------------


class TestGenerateFlightPlanWorkflowHappyPath:
    """Tests for the happy path workflow execution."""

    async def test_all_4_steps_execute(
        self,
        mock_config: MagicMock,
        mock_registry: MagicMock,
        mock_step_executor: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """All 4 steps produce StepCompleted events."""
        output = _make_flight_plan_output()
        mock_step_executor.execute.return_value = _make_executor_result(output)

        workflow = _make_workflow(mock_config, mock_registry, mock_step_executor)
        events = await _collect_events(
            workflow,
            {
                "prd_content": "Build a hello world CLI",
                "name": "test-plan",
                "output_dir": str(tmp_path),
                "skip_briefing": True,
            },
        )

        step_completions = [e for e in events if isinstance(e, StepCompleted)]
        completed_names = [e.step_name for e in step_completions]
        assert completed_names == _ALL_STEPS

    async def test_workflow_started_event(
        self,
        mock_config: MagicMock,
        mock_registry: MagicMock,
        mock_step_executor: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Workflow emits WorkflowStarted at the beginning."""
        mock_step_executor.execute.return_value = _make_executor_result()

        workflow = _make_workflow(mock_config, mock_registry, mock_step_executor)
        events = await _collect_events(
            workflow,
            {
                "prd_content": "Some PRD",
                "name": "test-plan",
                "output_dir": str(tmp_path),
                "skip_briefing": True,
            },
        )

        started = [e for e in events if isinstance(e, WorkflowStarted)]
        assert len(started) == 1

    async def test_workflow_completed_event_success(
        self,
        mock_config: MagicMock,
        mock_registry: MagicMock,
        mock_step_executor: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Workflow emits WorkflowCompleted with success=True."""
        mock_step_executor.execute.return_value = _make_executor_result()

        workflow = _make_workflow(mock_config, mock_registry, mock_step_executor)
        events = await _collect_events(
            workflow,
            {
                "prd_content": "Some PRD",
                "name": "test-plan",
                "output_dir": str(tmp_path),
                "skip_briefing": True,
            },
        )

        completed = [e for e in events if isinstance(e, WorkflowCompleted)]
        assert len(completed) == 1
        assert completed[0].success is True

    async def test_writes_flight_plan_file(
        self,
        mock_config: MagicMock,
        mock_registry: MagicMock,
        mock_step_executor: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Workflow writes the flight plan file to disk."""
        mock_step_executor.execute.return_value = _make_executor_result()

        workflow = _make_workflow(mock_config, mock_registry, mock_step_executor)
        await _collect_events(
            workflow,
            {
                "prd_content": "Some PRD",
                "name": "test-plan",
                "output_dir": str(tmp_path),
                "skip_briefing": True,
            },
        )

        target = tmp_path / "test-plan" / "flight-plan.md"
        assert target.exists()
        content = target.read_text()
        assert "## Objective" in content
        assert "## Success Criteria" in content

    async def test_result_contains_path(
        self,
        mock_config: MagicMock,
        mock_registry: MagicMock,
        mock_step_executor: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Workflow result includes the output path."""
        mock_step_executor.execute.return_value = _make_executor_result()

        workflow = _make_workflow(mock_config, mock_registry, mock_step_executor)
        await _collect_events(
            workflow,
            {
                "prd_content": "Some PRD",
                "name": "test-plan",
                "output_dir": str(tmp_path),
                "skip_briefing": True,
            },
        )

        assert workflow.result is not None
        assert workflow.result.success
        assert "flight-plan.md" in str(workflow.result.final_output)


class TestGenerateFlightPlanWorkflowErrors:
    """Tests for workflow error handling."""

    async def test_missing_prd_content_raises(
        self,
        mock_config: MagicMock,
        mock_registry: MagicMock,
        mock_step_executor: AsyncMock,
    ) -> None:
        """Missing prd_content input raises WorkflowError."""
        workflow = _make_workflow(mock_config, mock_registry, mock_step_executor)
        with pytest.raises(WorkflowError, match="prd_content"):
            await _collect_events(workflow, {"name": "test"})

    async def test_missing_name_raises(
        self,
        mock_config: MagicMock,
        mock_registry: MagicMock,
        mock_step_executor: AsyncMock,
    ) -> None:
        """Missing name input raises WorkflowError."""
        workflow = _make_workflow(mock_config, mock_registry, mock_step_executor)
        with pytest.raises(WorkflowError, match="name"):
            await _collect_events(workflow, {"prd_content": "Some PRD"})

    async def test_no_step_executor_raises(
        self,
        mock_config: MagicMock,
        mock_registry: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Missing step_executor raises WorkflowError during generate step."""
        workflow = GenerateFlightPlanWorkflow(
            config=mock_config,
            registry=mock_registry,
            step_executor=None,
            workflow_name=WORKFLOW_NAME,
        )
        with pytest.raises(WorkflowError, match="step_executor"):
            await _collect_events(
                workflow,
                {
                    "prd_content": "Some PRD",
                    "name": "test-plan",
                    "output_dir": str(tmp_path),
                    "skip_briefing": True,
                },
            )

    async def test_agent_returns_none_raises(
        self,
        mock_config: MagicMock,
        mock_registry: MagicMock,
        mock_step_executor: AsyncMock,
        tmp_path: Path,
    ) -> None:
        """Agent returning None output raises WorkflowError."""
        mock_step_executor.execute.return_value = ExecutorResult(
            output=None, success=True, usage=None, events=()
        )

        workflow = _make_workflow(mock_config, mock_registry, mock_step_executor)
        with pytest.raises(WorkflowError, match="no output"):
            await _collect_events(
                workflow,
                {
                    "prd_content": "Some PRD",
                    "name": "test-plan",
                    "output_dir": str(tmp_path),
                    "skip_briefing": True,
                },
            )
