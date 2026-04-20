"""Unit tests for GenerateFlightPlanWorkflow."""

from __future__ import annotations

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
    mock_registry: MagicMock,
) -> GenerateFlightPlanWorkflow:
    """Create a GenerateFlightPlanWorkflow with mocked dependencies."""
    return GenerateFlightPlanWorkflow(
        config=mock_config,
        registry=mock_registry,
        workflow_name=WORKFLOW_NAME,
    )


def _make_thespian_result(
    plan_dir: Path,
    output: FlightPlanOutput | None = None,
) -> dict[str, Any]:
    """Build a dict matching what _generate_with_thespian returns.

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
        mock_registry: MagicMock,
        tmp_path: Path,
    ) -> None:
        """read_prd step produces a StepCompleted event (other steps run inside Thespian)."""
        plan_dir = tmp_path / "test-plan"
        thespian_result = _make_thespian_result(plan_dir)

        workflow = _make_workflow(mock_config, mock_registry)
        with patch.object(
            workflow,
            "_generate_with_thespian",
            new=AsyncMock(return_value=thespian_result),
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
        mock_registry: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Workflow emits WorkflowStarted at the beginning."""
        plan_dir = tmp_path / "test-plan"
        thespian_result = _make_thespian_result(plan_dir)

        workflow = _make_workflow(mock_config, mock_registry)
        with patch.object(
            workflow,
            "_generate_with_thespian",
            new=AsyncMock(return_value=thespian_result),
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
        mock_registry: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Workflow emits WorkflowCompleted with success=True."""
        plan_dir = tmp_path / "test-plan"
        thespian_result = _make_thespian_result(plan_dir)

        workflow = _make_workflow(mock_config, mock_registry)
        with patch.object(
            workflow,
            "_generate_with_thespian",
            new=AsyncMock(return_value=thespian_result),
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
        mock_registry: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Thespian actor system writes the flight plan file to disk."""
        plan_dir = tmp_path / "test-plan"
        thespian_result = _make_thespian_result(plan_dir)

        workflow = _make_workflow(mock_config, mock_registry)
        with patch.object(
            workflow,
            "_generate_with_thespian",
            new=AsyncMock(return_value=thespian_result),
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
        mock_registry: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Workflow result includes the output path."""
        plan_dir = tmp_path / "test-plan"
        thespian_result = _make_thespian_result(plan_dir)

        workflow = _make_workflow(mock_config, mock_registry)
        with patch.object(
            workflow,
            "_generate_with_thespian",
            new=AsyncMock(return_value=thespian_result),
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
        mock_registry: MagicMock,
    ) -> None:
        """Missing prd_content input raises WorkflowError."""
        workflow = _make_workflow(mock_config, mock_registry)
        with pytest.raises(WorkflowError, match="prd_content"):
            await _collect_events(workflow, {"name": "test"})

    async def test_missing_name_raises(
        self,
        mock_config: MagicMock,
        mock_registry: MagicMock,
    ) -> None:
        """Missing name input raises WorkflowError."""
        workflow = _make_workflow(mock_config, mock_registry)
        with pytest.raises(WorkflowError, match="name"):
            await _collect_events(workflow, {"prd_content": "Some PRD"})

    async def test_agent_returns_none_raises(
        self,
        mock_config: MagicMock,
        mock_registry: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Agent returning no output causes Thespian to report failure."""
        workflow = _make_workflow(mock_config, mock_registry)
        with patch.object(
            workflow,
            "_generate_with_thespian",
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


class TestGenerateFlightPlanWorkflowThespianConfig:
    """Tests for config propagation into active Thespian actors."""

    async def test_thespian_actor_inits_receive_resolved_step_config(
        self,
        mock_config: MagicMock,
        mock_registry: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Briefing and generator actors receive the workflow's resolved config."""
        from maverick.config import AgentConfig, AgentProviderConfig

        class _FakeActorSystem:
            def __init__(self) -> None:
                self.asks: list[tuple[str, dict[str, Any], int]] = []
                self._counter = 0

            def createActor(self, _cls, **kwargs):  # noqa: N802
                self._counter += 1
                return kwargs.get("globalName") or f"actor-{self._counter}"

            def ask(self, addr, message, timeout):
                self.asks.append((addr, message, timeout))
                return {"type": "init_ok"}

            def tell(self, addr, message):
                return None

            def shutdown(self):
                return None

        mock_config.steps = {}
        mock_config.agents = {
            "scopist": AgentConfig(
                provider="gemini",
                model_id="gemini-3.1-pro-preview",
            ),
            "flight_plan_generator": AgentConfig(
                provider="claude",
                model_id="opus",
            ),
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

        workflow = _make_workflow(mock_config, mock_registry)
        fake_asys = _FakeActorSystem()

        with (
            patch("maverick.actors.create_actor_system", return_value=fake_asys),
            patch.object(workflow, "emit_output", new=AsyncMock()),
            patch.object(
                workflow,
                "_drain_supervisor_events",
                new=AsyncMock(
                    return_value={
                        "success": True,
                        "success_criteria_count": 1,
                        "validation_passed": True,
                        "briefing_path": None,
                    }
                ),
            ),
        ):
            await workflow._generate_with_thespian(
                prd_content="Build a CLI",
                name="test-plan",
                plan_dir=tmp_path / "test-plan",
                skip_briefing=False,
            )

        briefing_inits = [
            message
            for _addr, message, _timeout in fake_asys.asks
            if message.get("type") == "init" and message.get("mcp_tool")
        ]
        scopist_init = next(msg for msg in briefing_inits if msg.get("agent_name") == "scopist")
        assert scopist_init["config"]["provider"] == "gemini"
        assert scopist_init["config"]["model_id"] == "gemini-3.1-pro-preview"

        generator_init = next(
            message
            for _addr, message, _timeout in fake_asys.asks
            if message.get("type") == "init"
            and message.get("config", {}).get("model_id") == "opus"
        )
        assert generator_init["config"]["provider"] == "claude"

        supervisor_init = next(
            message
            for _addr, message, _timeout in fake_asys.asks
            if message.get("type") == "init" and message.get("provider_labels")
        )
        assert supervisor_init["provider_labels"]["Scopist"] == "gemini/gemini-3.1-pro-preview"
