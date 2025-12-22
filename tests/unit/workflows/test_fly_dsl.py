"""Unit tests for FlyWorkflow DSL integration.

Tests the FlyWorkflow class with DSL execution enabled:
- DSL workflow execution path
- Event translation from DSL events to FlyProgressEvent
- Result construction from WorkflowResult
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.dsl.events import (
    StepCompleted as DslStepCompleted,
    StepStarted as DslStepStarted,
    WorkflowCompleted as DslWorkflowCompleted,
    WorkflowStarted as DslWorkflowStarted,
)
from maverick.dsl.results import StepResult, WorkflowResult
from maverick.dsl.types import StepType
from maverick.workflows.fly import (
    FlyConfig,
    FlyInputs,
    FlyResult,
    FlyStageCompleted,
    FlyStageStarted,
    FlyWorkflow,
    FlyWorkflowCompleted,
    FlyWorkflowFailed,
    FlyWorkflowStarted,
    WorkflowStage,
)


class TestFlyWorkflowDSLExecution:
    """Tests for FlyWorkflow with DSL execution enabled."""

    @pytest.mark.asyncio
    async def test_enable_dsl_execution_sets_flag(self) -> None:
        """Test enable_dsl_execution sets internal flag."""
        workflow = FlyWorkflow()

        assert workflow._use_dsl is False

        workflow.enable_dsl_execution()

        assert workflow._use_dsl is True

    @pytest.mark.asyncio
    async def test_executes_dsl_workflow_when_enabled(self, tmp_path: Path) -> None:
        """Test executes DSL workflow instead of legacy when DSL enabled."""
        workflow = FlyWorkflow()
        workflow.enable_dsl_execution()

        inputs = FlyInputs(branch_name="test-branch")

        # Mock the workflow file loading
        mock_workflow_file = MagicMock()
        mock_workflow_file.name = "fly"

        # Mock the executor
        mock_executor = MagicMock()

        # Create mock DSL events
        async def mock_execute(wf, inputs):
            # Yield DSL events
            yield DslWorkflowStarted(
                workflow_name="fly",
                inputs={"branch_name": "test-branch"},
                timestamp=1234567890.0,
            )
            yield DslWorkflowCompleted(
                workflow_name="fly",
                success=True,
                total_duration_ms=1000,
                timestamp=1234567891.0,
            )

        mock_executor.execute = mock_execute
        mock_executor.get_result.return_value = WorkflowResult(
            workflow_name="fly",
            success=True,
            step_results=(),
            total_duration_ms=1000,
            final_output=None,
        )

        with (
            patch.object(workflow, "_load_workflow", return_value=mock_workflow_file),
            patch(
                "maverick.workflows.fly.WorkflowFileExecutor",
                return_value=mock_executor,
            ),
        ):
            events = []
            async for event in workflow.execute(inputs):
                events.append(event)

            # Should have received FlyWorkflowStarted and FlyWorkflowCompleted
            assert len(events) >= 2
            assert isinstance(events[0], FlyWorkflowStarted)
            assert isinstance(events[-1], FlyWorkflowCompleted)

    @pytest.mark.asyncio
    async def test_handles_workflow_file_not_found(self) -> None:
        """Test handles workflow file not found error."""
        workflow = FlyWorkflow()

        # Since we now use the builtin library, it raises KeyError for unknown workflows
        with pytest.raises(KeyError, match="Unknown built-in workflow"):
            workflow._load_workflow("nonexistent")


class TestEventTranslation:
    """Tests for DSL event translation to FlyProgressEvent."""

    def test_translates_dsl_workflow_started(self) -> None:
        """Test translates DslWorkflowStarted to FlyWorkflowStarted."""
        workflow = FlyWorkflow()

        dsl_event = DslWorkflowStarted(
            workflow_name="fly",
            inputs={
                "branch_name": "feature/test",
                "task_file": "tasks.md",
                "skip_review": False,
                "skip_pr": False,
                "draft_pr": True,
                "base_branch": "develop",
                "dry_run": False,
            },
            timestamp=1234567890.0,
        )

        fly_event = workflow._translate_event(dsl_event)

        assert isinstance(fly_event, FlyWorkflowStarted)
        assert fly_event.inputs.branch_name == "feature/test"
        assert fly_event.inputs.task_file == Path("tasks.md")
        assert fly_event.inputs.skip_review is False
        assert fly_event.inputs.skip_pr is False
        assert fly_event.inputs.draft_pr is True
        assert fly_event.inputs.base_branch == "develop"
        assert fly_event.inputs.dry_run is False
        assert fly_event.timestamp == 1234567890.0

    def test_translates_dsl_step_started_to_stage_started(self) -> None:
        """Test translates DslStepStarted to FlyStageStarted."""
        workflow = FlyWorkflow()

        dsl_event = DslStepStarted(
            step_name="init",
            step_type=StepType.PYTHON,
            timestamp=1234567890.0,
        )

        fly_event = workflow._translate_event(dsl_event)

        assert isinstance(fly_event, FlyStageStarted)
        assert fly_event.stage == WorkflowStage.INIT
        assert fly_event.timestamp == 1234567890.0

    def test_translates_dsl_step_completed_to_stage_completed(self) -> None:
        """Test translates DslStepCompleted to FlyStageCompleted."""
        workflow = FlyWorkflow()

        dsl_event = DslStepCompleted(
            step_name="implement",
            step_type=StepType.AGENT,
            success=True,
            duration_ms=5000,
            timestamp=1234567890.0,
        )

        fly_event = workflow._translate_event(dsl_event)

        assert isinstance(fly_event, FlyStageCompleted)
        assert fly_event.stage == WorkflowStage.IMPLEMENTATION
        assert fly_event.result["success"] is True
        assert fly_event.result["duration_ms"] == 5000
        assert fly_event.timestamp == 1234567890.0

    def test_maps_all_step_names_to_stages(self) -> None:
        """Test maps all recognized step names to workflow stages."""
        workflow = FlyWorkflow()

        step_to_stage = {
            "init": WorkflowStage.INIT,
            "init_dry_run": WorkflowStage.INIT,
            "implement": WorkflowStage.IMPLEMENTATION,
            "validate_and_fix": WorkflowStage.VALIDATION,
            "commit_and_push": WorkflowStage.PR_CREATION,
            "review": WorkflowStage.CODE_REVIEW,
            "create_pr": WorkflowStage.PR_CREATION,
        }

        for step_name, expected_stage in step_to_stage.items():
            dsl_event = DslStepStarted(
                step_name=step_name,
                step_type=StepType.PYTHON,
                timestamp=1234567890.0,
            )

            fly_event = workflow._translate_event(dsl_event)

            assert isinstance(fly_event, FlyStageStarted)
            assert fly_event.stage == expected_stage

    def test_returns_none_for_unmapped_step_names(self) -> None:
        """Test returns None for step names that don't map to stages."""
        workflow = FlyWorkflow()

        dsl_event = DslStepStarted(
            step_name="unknown_step",
            step_type=StepType.PYTHON,
            timestamp=1234567890.0,
        )

        fly_event = workflow._translate_event(dsl_event)

        assert fly_event is None

    def test_returns_none_for_unmapped_event_types(self) -> None:
        """Test returns None for DSL events that don't map to Fly events."""
        workflow = FlyWorkflow()

        # Create a generic event that's not specifically mapped
        # (WorkflowCompleted is handled separately in execute())
        dsl_event = DslWorkflowCompleted(
            workflow_name="fly",
            success=True,
            total_duration_ms=5000,
            timestamp=1234567890.0,
        )

        fly_event = workflow._translate_event(dsl_event)

        # WorkflowCompleted should return None (handled in execute)
        assert fly_event is None


class TestResultConstruction:
    """Tests for building FlyResult from WorkflowResult."""

    def test_builds_fly_result_from_successful_workflow(self) -> None:
        """Test builds FlyResult from successful WorkflowResult."""
        workflow = FlyWorkflow()

        # Initialize state
        workflow._state = MagicMock()
        workflow._state.branch = "feature/test"
        workflow._state.task_file = Path("tasks.md")
        workflow._state.started_at = MagicMock()
        workflow._state.implementation_result = None
        workflow._state.validation_result = None
        workflow._state.review_results = []
        workflow._state.pr_url = "https://github.com/org/repo/pull/123"
        workflow._state.errors = []

        workflow_result = WorkflowResult(
            workflow_name="fly",
            success=True,
            step_results=(),
            total_duration_ms=10000,
            final_output={"pr_url": "https://github.com/org/repo/pull/123"},
        )

        fly_result = workflow._build_fly_result(workflow_result)

        assert isinstance(fly_result, FlyResult)
        assert fly_result.success is True
        assert fly_result.state.stage == WorkflowStage.COMPLETE
        assert "completed successfully" in fly_result.summary.lower()

    def test_builds_fly_result_from_failed_workflow(self) -> None:
        """Test builds FlyResult from failed WorkflowResult."""
        workflow = FlyWorkflow()

        # Initialize state
        workflow._state = MagicMock()
        workflow._state.branch = "feature/test"
        workflow._state.task_file = None
        workflow._state.started_at = MagicMock()
        workflow._state.implementation_result = None
        workflow._state.validation_result = None
        workflow._state.review_results = []
        workflow._state.pr_url = None
        workflow._state.errors = []

        failed_step = StepResult(
            name="validate_and_fix",
            step_type=StepType.PYTHON,
            success=False,
            output=None,
            error="Validation failed",
            duration_ms=3000,
        )

        workflow_result = WorkflowResult(
            workflow_name="fly",
            success=False,
            step_results=(failed_step,),
            total_duration_ms=5000,
            final_output=None,
        )

        fly_result = workflow._build_fly_result(workflow_result)

        assert isinstance(fly_result, FlyResult)
        assert fly_result.success is False
        assert fly_result.state.stage == WorkflowStage.FAILED
        assert "failed" in fly_result.summary.lower()
        assert "validate_and_fix" in fly_result.summary

    def test_includes_pr_url_in_success_summary(self) -> None:
        """Test includes PR URL in success summary when available."""
        workflow = FlyWorkflow()

        workflow._state = MagicMock()
        workflow._state.branch = "feature/test"
        workflow._state.task_file = None
        workflow._state.started_at = MagicMock()
        workflow._state.implementation_result = None
        workflow._state.validation_result = None
        workflow._state.review_results = []
        workflow._state.pr_url = "https://github.com/org/repo/pull/456"
        workflow._state.errors = []

        workflow_result = WorkflowResult(
            workflow_name="fly",
            success=True,
            step_results=(),
            total_duration_ms=8000,
            final_output={"pr_url": "https://github.com/org/repo/pull/456"},
        )

        fly_result = workflow._build_fly_result(workflow_result)

        assert "https://github.com/org/repo/pull/456" in fly_result.summary

    def test_extracts_error_from_failed_step(self) -> None:
        """Test extracts error message from failed step."""
        workflow = FlyWorkflow()

        workflow._state = MagicMock()
        workflow._state.branch = "feature/test"
        workflow._state.task_file = None
        workflow._state.started_at = MagicMock()
        workflow._state.implementation_result = None
        workflow._state.validation_result = None
        workflow._state.review_results = []
        workflow._state.pr_url = None
        workflow._state.errors = []

        failed_step = StepResult(
            name="implement",
            step_type=StepType.AGENT,
            success=False,
            output=None,
            error="Implementation error: file not found",
            duration_ms=1000,
        )

        workflow_result = WorkflowResult(
            workflow_name="fly",
            success=False,
            step_results=(failed_step,),
            total_duration_ms=2000,
            final_output=None,
        )

        fly_result = workflow._build_fly_result(workflow_result)

        # Error should be added to state.errors
        assert len(fly_result.state.errors) > 0
        assert "implement" in fly_result.state.errors[0]
        assert "Implementation error: file not found" in fly_result.state.errors[0]

    def test_aggregates_token_usage(self) -> None:
        """Test aggregates token usage in result."""
        workflow = FlyWorkflow()

        # Add usage records
        from maverick.agents.result import AgentUsage

        workflow._usage_records = [
            AgentUsage(
                input_tokens=100, output_tokens=50, total_cost_usd=0.01, duration_ms=500
            ),
            AgentUsage(
                input_tokens=200,
                output_tokens=100,
                total_cost_usd=0.02,
                duration_ms=800,
            ),
        ]

        workflow._state = MagicMock()
        workflow._state.branch = "feature/test"
        workflow._state.task_file = None
        workflow._state.started_at = MagicMock()
        workflow._state.implementation_result = None
        workflow._state.validation_result = None
        workflow._state.review_results = []
        workflow._state.pr_url = None
        workflow._state.errors = []

        workflow_result = WorkflowResult(
            workflow_name="fly",
            success=True,
            step_results=(),
            total_duration_ms=5000,
            final_output=None,
        )

        fly_result = workflow._build_fly_result(workflow_result)

        assert fly_result.token_usage.input_tokens == 300
        assert fly_result.token_usage.output_tokens == 150
        assert fly_result.total_cost_usd == 0.03


class TestDSLExecutionErrorHandling:
    """Tests for error handling during DSL execution."""

    @pytest.mark.asyncio
    async def test_handles_workflow_parse_error(self) -> None:
        """Test handles workflow file parse error."""
        workflow = FlyWorkflow()
        workflow.enable_dsl_execution()

        inputs = FlyInputs(branch_name="test-branch")

        with patch.object(
            workflow,
            "_load_workflow",
            side_effect=Exception("Parse error: invalid YAML"),
        ):
            events = []
            async for event in workflow.execute(inputs):
                events.append(event)

            # Should emit FlyWorkflowFailed event
            assert len(events) > 0
            assert isinstance(events[-1], FlyWorkflowFailed)
            assert (
                "Parse error" in events[-1].error
                or "DSL workflow execution failed" in events[-1].error
            )

    @pytest.mark.asyncio
    async def test_handles_executor_error(self, tmp_path: Path) -> None:
        """Test handles executor runtime error."""
        workflow = FlyWorkflow()
        workflow.enable_dsl_execution()

        inputs = FlyInputs(branch_name="test-branch")

        mock_workflow_file = MagicMock()
        mock_executor = MagicMock()

        async def failing_execute(wf, inputs):
            raise Exception("Executor runtime error")
            yield  # Make it a generator (unreachable)

        mock_executor.execute = failing_execute

        with (
            patch.object(workflow, "_load_workflow", return_value=mock_workflow_file),
            patch(
                "maverick.workflows.fly.WorkflowFileExecutor",
                return_value=mock_executor,
            ),
        ):
            events = []
            async for event in workflow.execute(inputs):
                events.append(event)

            # Should emit FlyWorkflowFailed event
            assert len(events) > 0
            assert isinstance(events[-1], FlyWorkflowFailed)
            assert "failed" in events[-1].error.lower()

    @pytest.mark.asyncio
    async def test_state_updated_on_failure(self) -> None:
        """Test state is properly updated when workflow fails."""
        workflow = FlyWorkflow()
        workflow.enable_dsl_execution()

        inputs = FlyInputs(branch_name="test-branch")

        with patch.object(
            workflow,
            "_load_workflow",
            side_effect=Exception("Test failure"),
        ):
            events = []
            async for event in workflow.execute(inputs):
                events.append(event)

            # State should be set to FAILED
            assert workflow._state is not None
            assert workflow._state.stage == WorkflowStage.FAILED
            assert workflow._state.completed_at is not None
            assert len(workflow._state.errors) > 0
