"""Unit tests for GenerateFlightPlanWorkflow."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.events import (
    StepCompleted,
    WorkflowCompleted,
    WorkflowStarted,
)
from maverick.exceptions import WorkflowError
from maverick.workflows.generate_flight_plan.constants import (
    READ_PRD,
    WORKFLOW_NAME,
)
from maverick.workflows.generate_flight_plan.models import FlightPlanOutput
from maverick.workflows.generate_flight_plan.workflow import (
    GenerateFlightPlanWorkflow,
    _build_generate_prompt,
    _convert_output_to_flight_plan,
)

_MODULE = "maverick.workflows.generate_flight_plan.workflow"

_REQUIRES_OPENCODE = pytest.mark.skipif(
    shutil.which("opencode") is None,
    reason="opencode binary not on PATH (CI environment)",
)


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


def _make_workflow(
    mock_config: MagicMock,
) -> GenerateFlightPlanWorkflow:
    """Create a GenerateFlightPlanWorkflow with mocked dependencies."""
    return GenerateFlightPlanWorkflow(
        config=mock_config,
        workflow_name=WORKFLOW_NAME,
    )


def _make_supervisor_result(
    plan_dir: Path,
    output: FlightPlanOutput | None = None,
) -> dict[str, Any]:
    """Build a dict matching what _generate_with_xoscar returns.

    Also writes the flight plan file to disk so tests that check file
    existence continue to work.
    """
    fp_output = output or _make_flight_plan_output()
    today = __import__("datetime").date.today()
    plan = _convert_output_to_flight_plan(fp_output, today)

    # Write the flight plan file (thespian actors do this in production)
    from maverick.flight.serializer import serialize_flight_plan

    plan_dir.mkdir(parents=True, exist_ok=True)
    target_file = plan_dir / "flight-plan.md"
    target_file.write_text(serialize_flight_plan(plan), encoding="utf-8")

    return {
        "success": True,
        "flight_plan_path": str(target_file),
        "success_criteria_count": len(fp_output.success_criteria),
        "validation_passed": True,
        "briefing_path": None,
    }


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

        prompt = _build_generate_prompt("Build a hello world CLI", "my-plan", date.today())
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
        tmp_path: Path,
    ) -> None:
        """read_prd step produces a StepCompleted event (other steps run inside Thespian)."""
        plan_dir = tmp_path / "test-plan"
        supervisor_result = _make_supervisor_result(plan_dir)

        workflow = _make_workflow(mock_config)
        with patch.object(
            workflow,
            "_generate_with_xoscar",
            new=AsyncMock(return_value=supervisor_result),
        ):
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
        assert READ_PRD in completed_names

    async def test_workflow_started_event(
        self,
        mock_config: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Workflow emits WorkflowStarted at the beginning."""
        plan_dir = tmp_path / "test-plan"
        supervisor_result = _make_supervisor_result(plan_dir)

        workflow = _make_workflow(mock_config)
        with patch.object(
            workflow,
            "_generate_with_xoscar",
            new=AsyncMock(return_value=supervisor_result),
        ):
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
        tmp_path: Path,
    ) -> None:
        """Workflow emits WorkflowCompleted with success=True."""
        plan_dir = tmp_path / "test-plan"
        supervisor_result = _make_supervisor_result(plan_dir)

        workflow = _make_workflow(mock_config)
        with patch.object(
            workflow,
            "_generate_with_xoscar",
            new=AsyncMock(return_value=supervisor_result),
        ):
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
        tmp_path: Path,
    ) -> None:
        """Thespian actor system writes the flight plan file to disk."""
        plan_dir = tmp_path / "test-plan"
        supervisor_result = _make_supervisor_result(plan_dir)

        workflow = _make_workflow(mock_config)
        with patch.object(
            workflow,
            "_generate_with_xoscar",
            new=AsyncMock(return_value=supervisor_result),
        ):
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
        tmp_path: Path,
    ) -> None:
        """Workflow result includes the output path."""
        plan_dir = tmp_path / "test-plan"
        supervisor_result = _make_supervisor_result(plan_dir)

        workflow = _make_workflow(mock_config)
        with patch.object(
            workflow,
            "_generate_with_xoscar",
            new=AsyncMock(return_value=supervisor_result),
        ):
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
    ) -> None:
        """Missing prd_content input raises WorkflowError."""
        workflow = _make_workflow(mock_config)
        with pytest.raises(WorkflowError, match="prd_content"):
            await _collect_events(workflow, {"name": "test"})

    async def test_missing_name_raises(
        self,
        mock_config: MagicMock,
    ) -> None:
        """Missing name input raises WorkflowError."""
        workflow = _make_workflow(mock_config)
        with pytest.raises(WorkflowError, match="name"):
            await _collect_events(workflow, {"prd_content": "Some PRD"})

    async def test_agent_returns_none_raises(
        self,
        mock_config: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Agent returning no output causes Thespian to report failure."""
        workflow = _make_workflow(mock_config)
        with patch.object(
            workflow,
            "_generate_with_xoscar",
            new=AsyncMock(
                side_effect=WorkflowError("Plan generation failed: no output from agent")
            ),
        ):
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


@_REQUIRES_OPENCODE
class TestGenerateFlightPlanWorkflowXoscarConfig:
    """Tests for config propagation into the xoscar PlanSupervisor."""

    async def test_xoscar_supervisor_receives_typed_inputs(
        self,
        mock_config: MagicMock,
        tmp_path: Path,
    ) -> None:
        """PlanSupervisor gets PlanInputs carrying the generator's StepConfig
        and the resolved provider labels for the briefing Rich Live table."""
        from maverick.config import AgentProviderConfig

        mock_config.actors = {
            "plan": {
                "scopist": {
                    "provider": "gemini",
                    "model_id": "gemini-3.1-pro-preview",
                },
                "flight_plan_generator": {
                    "provider": "claude",
                    "model_id": "opus",
                },
            }
        }
        mock_config.agent_providers = {
            "claude": AgentProviderConfig(
                command=["claude-agent"],
                default=True,
                default_model="sonnet",
            ),
            "gemini": AgentProviderConfig(
                command=["gemini-agent"],
                default_model="gemini-default",
            ),
        }

        workflow = _make_workflow(mock_config)

        captured_inputs: dict[str, Any] = {}

        async def _fake_create_actor(_cls, *args: Any, **kwargs: Any) -> AsyncMock:
            if args and not captured_inputs:
                captured_inputs["value"] = args[0]
            return AsyncMock()

        async def _fake_destroy_actor(_ref: Any) -> None:
            return None

        with (
            patch("xoscar.create_actor", new=_fake_create_actor),
            patch("xoscar.destroy_actor", new=_fake_destroy_actor),
            patch.object(workflow, "emit_output", new=AsyncMock()),
            patch.object(
                workflow,
                "_drain_xoscar_supervisor",
                new=AsyncMock(
                    return_value={
                        "success": True,
                        "success_criteria_count": 1,
                        "validation_passed": True,
                        "briefing_path": None,
                        "flight_plan_path": str(tmp_path / "test-plan" / "flight-plan.md"),
                    }
                ),
            ),
        ):
            await workflow._generate_with_xoscar(
                prd_content="Build a CLI",
                name="test-plan",
                plan_dir=tmp_path / "test-plan",
                skip_briefing=False,
            )

        inputs = captured_inputs.get("value")
        assert inputs is not None, "PlanSupervisor was never created"
        assert inputs.plan_name == "test-plan"
        assert inputs.prd_content == "Build a CLI"
        assert inputs.skip_briefing is False
        assert inputs.config is not None
        assert inputs.config.provider == "claude"
        assert inputs.config.model_id == "opus"
        assert inputs.provider_labels["Scopist"] == "gemini/gemini-3.1-pro-preview"
        # Per-agent briefing config carries scopist's resolved StepConfig.
        assert "scopist" in inputs.briefing_configs
        assert inputs.briefing_configs["scopist"].provider == "gemini"
        assert inputs.briefing_configs["scopist"].model_id == "gemini-3.1-pro-preview"

    async def test_briefing_configs_resolve_per_agent_from_actors_block(
        self,
        mock_config: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Each briefing agent gets its own StepConfig resolved through the
        actors.plan.<agent_name> path — the user's symptom of all briefings
        sharing claude/sonnet was caused by a single shared config."""
        from maverick.config import AgentProviderConfig

        mock_config.actors = {
            "plan": {
                "scopist": {
                    "provider": "gemini",
                    "model_id": "gemini-3.1-pro-preview",
                },
                "codebase_analyst": {
                    "provider": "opencode",
                    "model_id": "opencode/nemotron-3-super-free",
                },
                "criteria_writer": {
                    "provider": "copilot",
                    "model_id": "gpt-5.4",
                },
                "contrarian": {"provider": "claude", "model_id": "opus"},
                "flight_plan_generator": {"provider": "claude", "model_id": "sonnet"},
            }
        }
        mock_config.agent_providers = {
            "claude": AgentProviderConfig(
                command=["claude-agent"], default=True, default_model="sonnet"
            ),
            "copilot": AgentProviderConfig(command=["copilot-agent"], default_model="gpt-5-mini"),
            "gemini": AgentProviderConfig(
                command=["gemini-agent"], default_model="gemini-default"
            ),
            "opencode": AgentProviderConfig(
                command=["opencode-agent"], default_model="opencode/default"
            ),
        }

        workflow = _make_workflow(mock_config)
        captured_inputs: dict[str, Any] = {}

        async def _fake_create_actor(_cls, *args: Any, **kwargs: Any) -> AsyncMock:
            if args and not captured_inputs:
                captured_inputs["value"] = args[0]
            return AsyncMock()

        async def _fake_destroy_actor(_ref: Any) -> None:
            return None

        with (
            patch("xoscar.create_actor", new=_fake_create_actor),
            patch("xoscar.destroy_actor", new=_fake_destroy_actor),
            patch.object(workflow, "emit_output", new=AsyncMock()),
            patch.object(
                workflow,
                "_drain_xoscar_supervisor",
                new=AsyncMock(
                    return_value={
                        "success": True,
                        "success_criteria_count": 1,
                        "validation_passed": True,
                        "briefing_path": None,
                        "flight_plan_path": str(tmp_path / "p" / "flight-plan.md"),
                    }
                ),
            ),
        ):
            await workflow._generate_with_xoscar(
                prd_content="x",
                name="p",
                plan_dir=tmp_path / "p",
                skip_briefing=False,
            )

        inputs = captured_inputs["value"]
        bc = inputs.briefing_configs
        # Each briefing agent has the right provider + model_id —
        # actors.plan.<agent_name> beats the global default.
        assert bc["scopist"].provider == "gemini"
        assert bc["scopist"].model_id == "gemini-3.1-pro-preview"
        assert bc["codebase_analyst"].provider == "opencode"
        assert bc["codebase_analyst"].model_id == "opencode/nemotron-3-super-free"
        assert bc["criteria_writer"].provider == "copilot"
        assert bc["criteria_writer"].model_id == "gpt-5.4"
        assert bc["contrarian"].provider == "claude"
        assert bc["contrarian"].model_id == "opus"
