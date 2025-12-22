"""Unit tests for RefuelWorkflow DSL integration.

Tests the RefuelWorkflow class with DSL execution enabled:
- DSL workflow execution path
- Event translation from DSL events to RefuelProgressEvent
- Result construction from WorkflowResult
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.dsl.events import (
    StepCompleted as DslStepCompleted,
)
from maverick.dsl.events import (
    StepStarted as DslStepStarted,
)
from maverick.dsl.events import (
    WorkflowCompleted as DslWorkflowCompleted,
)
from maverick.dsl.events import (
    WorkflowStarted as DslWorkflowStarted,
)
from maverick.dsl.results import StepResult, WorkflowResult
from maverick.dsl.types import StepType
from maverick.workflows.refuel import (
    RefuelCompleted,
    RefuelConfig,
    RefuelInputs,
    RefuelResult,
    RefuelStarted,
    RefuelWorkflow,
)


class TestRefuelWorkflowDSLExecution:
    """Tests for RefuelWorkflow with DSL execution enabled."""

    @pytest.mark.asyncio
    async def test_enable_dsl_execution_sets_flag(self) -> None:
        """Test enable_dsl_execution sets internal flag."""
        workflow = RefuelWorkflow()

        assert workflow._use_dsl is False

        workflow.enable_dsl_execution()

        assert workflow._use_dsl is True

    @pytest.mark.asyncio
    async def test_executes_dsl_workflow_when_enabled(self) -> None:
        """Test executes DSL workflow instead of legacy when DSL enabled."""
        workflow = RefuelWorkflow()
        workflow.enable_dsl_execution()

        inputs = RefuelInputs(label="tech-debt", limit=3)

        # Mock the workflow file loading
        mock_workflow_file = MagicMock()
        mock_workflow_file.name = "refuel"

        # Mock the executor
        mock_executor = MagicMock()

        # Create mock DSL events
        async def mock_execute(wf, inputs):
            # Yield DSL events
            yield DslWorkflowStarted(
                workflow_name="refuel",
                inputs={
                    "label": "tech-debt",
                    "limit": 3,
                    "parallel": True,
                    "dry_run": False,
                    "auto_assign": True,
                },
                timestamp=1234567890.0,
            )
            yield DslWorkflowCompleted(
                workflow_name="refuel",
                success=True,
                total_duration_ms=5000,
                timestamp=1234567895.0,
            )

        mock_executor.execute = mock_execute
        mock_executor.get_result.return_value = WorkflowResult(
            workflow_name="refuel",
            success=True,
            step_results=(),
            total_duration_ms=5000,
            final_output={
                "issues_found": 3,
                "results": [],
            },
        )

        with (
            patch.object(workflow, "_load_workflow", return_value=mock_workflow_file),
            patch(
                "maverick.workflows.refuel.WorkflowFileExecutor",
                return_value=mock_executor,
            ),
        ):
            events = []
            async for event in workflow.execute(inputs):
                events.append(event)

            # Should have received RefuelStarted and RefuelCompleted
            assert len(events) >= 2
            assert isinstance(events[0], RefuelStarted)
            assert isinstance(events[-1], RefuelCompleted)

    @pytest.mark.asyncio
    async def test_handles_workflow_file_not_found(self) -> None:
        """Test handles workflow file not found error."""
        workflow = RefuelWorkflow()

        # With builtin library, unknown workflows raise KeyError
        with pytest.raises(KeyError, match="Unknown built-in workflow"):
            workflow._load_workflow("nonexistent")

    @pytest.mark.asyncio
    async def test_loads_workflow_from_library(self) -> None:
        """Test loads workflow file from built-in library."""
        workflow = RefuelWorkflow()

        # Mock the builtin library to verify it's being used
        mock_library = MagicMock()
        mock_workflow_file = MagicMock(name="refuel")
        mock_library.get_workflow.return_value = mock_workflow_file

        with patch(
            "maverick.workflows.base.create_builtin_library", return_value=mock_library
        ):
            result = workflow._load_workflow("refuel")

            # Verify builtin library was called
            mock_library.get_workflow.assert_called_once_with("refuel")
            assert result == mock_workflow_file

    @pytest.mark.asyncio
    async def test_uses_legacy_execution_when_dsl_disabled(self) -> None:
        """Test uses legacy execution path when DSL not enabled."""
        workflow = RefuelWorkflow()
        # Do NOT call enable_dsl_execution()

        assert workflow._use_dsl is False

        # Mock the legacy dependencies
        mock_github_runner = AsyncMock()
        mock_github_runner.list_issues.return_value = []
        workflow._github_runner = mock_github_runner

        inputs = RefuelInputs(label="test", limit=1)

        events = []
        async for event in workflow.execute(inputs):
            events.append(event)

        # Should still get RefuelStarted and RefuelCompleted from legacy path
        assert len(events) >= 2
        assert isinstance(events[0], RefuelStarted)
        assert isinstance(events[-1], RefuelCompleted)


class TestEventTranslation:
    """Tests for DSL event translation to RefuelProgressEvent."""

    def test_translates_dsl_workflow_started(self) -> None:
        """Test translates DslWorkflowStarted to RefuelStarted."""
        workflow = RefuelWorkflow()

        dsl_event = DslWorkflowStarted(
            workflow_name="refuel",
            inputs={
                "label": "bug",
                "limit": 10,
                "parallel": False,
                "dry_run": True,
                "auto_assign": False,
            },
            timestamp=1234567890.0,
        )

        refuel_event = workflow._translate_event(dsl_event)

        assert isinstance(refuel_event, RefuelStarted)
        assert refuel_event.inputs.label == "bug"
        assert refuel_event.inputs.limit == 10
        assert refuel_event.inputs.parallel is False
        assert refuel_event.inputs.dry_run is True
        assert refuel_event.inputs.auto_assign is False
        # issues_found is 0 at workflow start, will be updated later
        assert refuel_event.issues_found == 0

    def test_uses_default_values_for_missing_inputs(self) -> None:
        """Test uses default values when inputs are missing."""
        workflow = RefuelWorkflow()

        dsl_event = DslWorkflowStarted(
            workflow_name="refuel",
            inputs={},  # Empty inputs
            timestamp=1234567890.0,
        )

        refuel_event = workflow._translate_event(dsl_event)

        assert isinstance(refuel_event, RefuelStarted)
        assert refuel_event.inputs.label == "tech-debt"  # Default
        assert refuel_event.inputs.limit == 5  # Default
        assert refuel_event.inputs.parallel is True  # Default
        assert refuel_event.inputs.dry_run is False  # Default
        assert refuel_event.inputs.auto_assign is True  # Default

    def test_returns_none_for_step_started(self) -> None:
        """Test returns None for DslStepStarted events."""
        workflow = RefuelWorkflow()

        dsl_event = DslStepStarted(
            step_name="fetch_issues",
            step_type=StepType.PYTHON,
            timestamp=1234567890.0,
        )

        refuel_event = workflow._translate_event(dsl_event)

        # Currently returns None as issue processing tracking would require metadata
        assert refuel_event is None

    def test_returns_none_for_step_completed(self) -> None:
        """Test returns None for DslStepCompleted events."""
        workflow = RefuelWorkflow()

        dsl_event = DslStepCompleted(
            step_name="process_issues",
            step_type=StepType.PYTHON,
            success=True,
            duration_ms=3000,
            timestamp=1234567890.0,
        )

        refuel_event = workflow._translate_event(dsl_event)

        # Currently returns None as issue processing tracking would require metadata
        assert refuel_event is None

    def test_returns_none_for_workflow_completed(self) -> None:
        """Test returns None for DslWorkflowCompleted events."""
        workflow = RefuelWorkflow()

        dsl_event = DslWorkflowCompleted(
            workflow_name="refuel",
            success=True,
            total_duration_ms=10000,
            timestamp=1234567900.0,
        )

        refuel_event = workflow._translate_event(dsl_event)

        # WorkflowCompleted is handled separately in execute()
        assert refuel_event is None


class TestResultConstruction:
    """Tests for building RefuelResult from WorkflowResult."""

    def test_builds_refuel_result_from_successful_workflow(self) -> None:
        """Test builds RefuelResult from successful WorkflowResult."""
        workflow = RefuelWorkflow()

        workflow_result = WorkflowResult(
            workflow_name="refuel",
            success=True,
            step_results=(),
            total_duration_ms=8000,
            final_output=None,
        )

        refuel_result = workflow._build_refuel_result(workflow_result)

        assert isinstance(refuel_result, RefuelResult)
        assert refuel_result.success is True
        assert refuel_result.total_duration_ms == 8000
        assert refuel_result.issues_found == 0
        assert refuel_result.issues_processed == 0
        assert refuel_result.issues_fixed == 0
        assert refuel_result.issues_failed == 0
        assert refuel_result.issues_skipped == 0

    def test_builds_refuel_result_from_failed_workflow(self) -> None:
        """Test builds RefuelResult from failed WorkflowResult."""
        workflow = RefuelWorkflow()

        failed_step = StepResult(
            name="process_issues",
            step_type=StepType.PYTHON,
            success=False,
            output=None,
            error="Processing failed",
            duration_ms=2000,
        )

        workflow_result = WorkflowResult(
            workflow_name="refuel",
            success=False,
            step_results=(failed_step,),
            total_duration_ms=3000,
            final_output=None,
        )

        refuel_result = workflow._build_refuel_result(workflow_result)

        assert isinstance(refuel_result, RefuelResult)
        assert refuel_result.success is False
        assert refuel_result.total_duration_ms == 3000

    def test_extracts_issues_found_from_output(self) -> None:
        """Test extracts issues_found from workflow output."""
        workflow = RefuelWorkflow()

        workflow_result = WorkflowResult(
            workflow_name="refuel",
            success=True,
            step_results=(),
            total_duration_ms=5000,
            final_output={
                "issues_found": 7,
                "results": [],
            },
        )

        refuel_result = workflow._build_refuel_result(workflow_result)

        assert refuel_result.issues_found == 7

    def test_extracts_issue_processing_results(self) -> None:
        """Test extracts and reconstructs issue processing results."""
        workflow = RefuelWorkflow()

        results_data = [
            {
                "issue": {
                    "number": 123,
                    "title": "Fix bug",
                    "body": "Bug description",
                    "labels": ["bug", "priority"],
                    "assignee": "dev1",
                    "url": "https://github.com/org/repo/issues/123",
                },
                "status": "fixed",
                "branch": "fix/issue-123",
                "pr_url": "https://github.com/org/repo/pull/200",
                "error": None,
                "duration_ms": 5000,
                "agent_usage": {
                    "input_tokens": 1000,
                    "output_tokens": 500,
                    "total_cost_usd": 0.05,
                    "duration_ms": 3000,
                },
            },
        ]

        workflow_result = WorkflowResult(
            workflow_name="refuel",
            success=True,
            step_results=(),
            total_duration_ms=10000,
            final_output={
                "issues_found": 1,
                "results": results_data,
            },
        )

        refuel_result = workflow._build_refuel_result(workflow_result)

        assert len(refuel_result.results) == 1
        result = refuel_result.results[0]
        assert result.issue.number == 123
        assert result.issue.title == "Fix bug"
        assert result.status.value == "fixed"
        assert result.branch == "fix/issue-123"
        assert result.pr_url == "https://github.com/org/repo/pull/200"
        assert result.agent_usage.input_tokens == 1000
        assert result.agent_usage.output_tokens == 500

    def test_counts_status_types_correctly(self) -> None:
        """Test correctly counts issues by status."""
        workflow = RefuelWorkflow()

        results_data = [
            {
                "issue": {
                    "number": 1,
                    "title": "Issue 1",
                    "body": None,
                    "labels": [],
                    "assignee": None,
                    "url": "url1",
                },
                "status": "fixed",
                "branch": "branch1",
                "pr_url": "pr1",
                "error": None,
                "duration_ms": 1000,
                "agent_usage": {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_cost_usd": 0.0,
                    "duration_ms": 0,
                },
            },
            {
                "issue": {
                    "number": 2,
                    "title": "Issue 2",
                    "body": None,
                    "labels": [],
                    "assignee": None,
                    "url": "url2",
                },
                "status": "fixed",
                "branch": "branch2",
                "pr_url": "pr2",
                "error": None,
                "duration_ms": 1000,
                "agent_usage": {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_cost_usd": 0.0,
                    "duration_ms": 0,
                },
            },
            {
                "issue": {
                    "number": 3,
                    "title": "Issue 3",
                    "body": None,
                    "labels": [],
                    "assignee": None,
                    "url": "url3",
                },
                "status": "failed",
                "branch": None,
                "pr_url": None,
                "error": "Error message",
                "duration_ms": 1000,
                "agent_usage": {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_cost_usd": 0.0,
                    "duration_ms": 0,
                },
            },
            {
                "issue": {
                    "number": 4,
                    "title": "Issue 4",
                    "body": None,
                    "labels": [],
                    "assignee": None,
                    "url": "url4",
                },
                "status": "skipped",
                "branch": None,
                "pr_url": None,
                "error": None,
                "duration_ms": 0,
                "agent_usage": {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_cost_usd": 0.0,
                    "duration_ms": 0,
                },
            },
        ]

        workflow_result = WorkflowResult(
            workflow_name="refuel",
            success=True,
            step_results=(),
            total_duration_ms=5000,
            final_output={
                "issues_found": 4,
                "results": results_data,
            },
        )

        refuel_result = workflow._build_refuel_result(workflow_result)

        assert refuel_result.issues_fixed == 2
        assert refuel_result.issues_failed == 1
        assert refuel_result.issues_skipped == 1
        assert refuel_result.issues_processed == 3  # fixed + failed

    def test_computes_total_cost(self) -> None:
        """Test computes total cost from all results."""
        workflow = RefuelWorkflow()

        results_data = [
            {
                "issue": {
                    "number": 1,
                    "title": "Issue 1",
                    "body": None,
                    "labels": [],
                    "assignee": None,
                    "url": "url1",
                },
                "status": "fixed",
                "branch": "branch1",
                "pr_url": "pr1",
                "error": None,
                "duration_ms": 1000,
                "agent_usage": {
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "total_cost_usd": 0.10,
                    "duration_ms": 1000,
                },
            },
            {
                "issue": {
                    "number": 2,
                    "title": "Issue 2",
                    "body": None,
                    "labels": [],
                    "assignee": None,
                    "url": "url2",
                },
                "status": "fixed",
                "branch": "branch2",
                "pr_url": "pr2",
                "error": None,
                "duration_ms": 1000,
                "agent_usage": {
                    "input_tokens": 200,
                    "output_tokens": 100,
                    "total_cost_usd": 0.25,
                    "duration_ms": 1000,
                },
            },
        ]

        workflow_result = WorkflowResult(
            workflow_name="refuel",
            success=True,
            step_results=(),
            total_duration_ms=3000,
            final_output={
                "issues_found": 2,
                "results": results_data,
            },
        )

        refuel_result = workflow._build_refuel_result(workflow_result)

        assert refuel_result.total_cost_usd == 0.35

    def test_uses_workflow_duration_when_no_output(self) -> None:
        """Test uses workflow total_duration_ms when not in output."""
        workflow = RefuelWorkflow()

        workflow_result = WorkflowResult(
            workflow_name="refuel",
            success=True,
            step_results=(),
            total_duration_ms=7000,
            final_output={},  # No total_duration_ms in output
        )

        refuel_result = workflow._build_refuel_result(workflow_result)

        assert refuel_result.total_duration_ms == 7000

    def test_prefers_output_duration_over_workflow_duration(self) -> None:
        """Test prefers duration from output over workflow duration."""
        workflow = RefuelWorkflow()

        workflow_result = WorkflowResult(
            workflow_name="refuel",
            success=True,
            step_results=(),
            total_duration_ms=5000,
            final_output={
                "total_duration_ms": 8000,  # Different from workflow duration
                "results": [],
            },
        )

        refuel_result = workflow._build_refuel_result(workflow_result)

        assert refuel_result.total_duration_ms == 8000

    def test_handles_empty_results_gracefully(self) -> None:
        """Test handles empty results list gracefully."""
        workflow = RefuelWorkflow()

        workflow_result = WorkflowResult(
            workflow_name="refuel",
            success=True,
            step_results=(),
            total_duration_ms=1000,
            final_output={
                "issues_found": 0,
                "results": [],
            },
        )

        refuel_result = workflow._build_refuel_result(workflow_result)

        assert len(refuel_result.results) == 0
        assert refuel_result.issues_processed == 0
        assert refuel_result.total_cost_usd == 0.0

    def test_success_false_when_workflow_failed(self) -> None:
        """Test sets success=False when workflow failed."""
        workflow = RefuelWorkflow()

        workflow_result = WorkflowResult(
            workflow_name="refuel",
            success=False,  # Workflow failed
            step_results=(),
            total_duration_ms=2000,
            final_output=None,
        )

        refuel_result = workflow._build_refuel_result(workflow_result)

        assert refuel_result.success is False

    def test_success_false_when_issues_failed(self) -> None:
        """Test sets success=False when any issues failed."""
        workflow = RefuelWorkflow()

        results_data = [
            {
                "issue": {
                    "number": 1,
                    "title": "Issue 1",
                    "body": None,
                    "labels": [],
                    "assignee": None,
                    "url": "url1",
                },
                "status": "failed",
                "branch": None,
                "pr_url": None,
                "error": "Error",
                "duration_ms": 1000,
                "agent_usage": {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_cost_usd": 0.0,
                    "duration_ms": 0,
                },
            },
        ]

        workflow_result = WorkflowResult(
            workflow_name="refuel",
            success=True,  # Workflow succeeded but issue failed
            step_results=(),
            total_duration_ms=2000,
            final_output={
                "issues_found": 1,
                "results": results_data,
            },
        )

        refuel_result = workflow._build_refuel_result(workflow_result)

        assert refuel_result.success is False  # Because issues_failed > 0


class TestDSLExecutionErrorHandling:
    """Tests for error handling during DSL execution."""

    @pytest.mark.asyncio
    async def test_handles_workflow_parse_error(self) -> None:
        """Test handles workflow file parse error."""
        workflow = RefuelWorkflow()
        workflow.enable_dsl_execution()

        inputs = RefuelInputs(label="test")

        with patch.object(
            workflow,
            "_load_workflow",
            side_effect=Exception("Parse error: invalid YAML"),
        ):
            events = []
            async for event in workflow.execute(inputs):
                events.append(event)

            # Should emit RefuelCompleted with failure
            assert len(events) > 0
            assert isinstance(events[-1], RefuelCompleted)
            assert events[-1].result.success is False

    @pytest.mark.asyncio
    async def test_handles_executor_error(self) -> None:
        """Test handles executor runtime error."""
        workflow = RefuelWorkflow()
        workflow.enable_dsl_execution()

        inputs = RefuelInputs(label="test")

        mock_workflow_file = MagicMock()
        mock_executor = MagicMock()

        async def failing_execute(wf, inputs):
            raise Exception("Executor runtime error")
            yield  # Make it a generator (unreachable)

        mock_executor.execute = failing_execute

        with (
            patch.object(workflow, "_load_workflow", return_value=mock_workflow_file),
            patch(
                "maverick.workflows.refuel.WorkflowFileExecutor",
                return_value=mock_executor,
            ),
        ):
            events = []
            async for event in workflow.execute(inputs):
                events.append(event)

            # Should emit RefuelCompleted with failure
            assert len(events) > 0
            assert isinstance(events[-1], RefuelCompleted)
            assert events[-1].result.success is False

    @pytest.mark.asyncio
    async def test_returns_empty_result_on_failure(self) -> None:
        """Test returns empty result when workflow fails."""
        workflow = RefuelWorkflow()
        workflow.enable_dsl_execution()

        inputs = RefuelInputs(label="test")

        with patch.object(
            workflow,
            "_load_workflow",
            side_effect=Exception("Test failure"),
        ):
            events = []
            async for event in workflow.execute(inputs):
                events.append(event)

            result_event = events[-1]
            assert isinstance(result_event, RefuelCompleted)
            assert result_event.result.success is False
            assert result_event.result.issues_found == 0
            assert result_event.result.issues_processed == 0
            assert result_event.result.total_cost_usd == 0.0
            assert len(result_event.result.results) == 0

    @pytest.mark.asyncio
    async def test_passes_config_to_executor(self) -> None:
        """Test passes RefuelConfig to WorkflowFileExecutor."""
        config = RefuelConfig(
            default_label="custom-label",
            branch_prefix="custom/",
            max_parallel=5,
        )
        workflow = RefuelWorkflow(config=config)
        workflow.enable_dsl_execution()

        inputs = RefuelInputs(label="test")

        mock_workflow_file = MagicMock()
        mock_executor = MagicMock()

        async def mock_execute(wf, inputs):
            yield DslWorkflowStarted(
                workflow_name="refuel",
                inputs={},
                timestamp=0.0,
            )
            yield DslWorkflowCompleted(
                workflow_name="refuel",
                success=True,
                total_duration_ms=1000,
                timestamp=1.0,
            )

        mock_executor.execute = mock_execute
        mock_executor.get_result.return_value = WorkflowResult(
            workflow_name="refuel",
            success=True,
            step_results=(),
            total_duration_ms=1000,
            final_output=None,
        )

        with (
            patch.object(workflow, "_load_workflow", return_value=mock_workflow_file),
            patch(
                "maverick.workflows.refuel.WorkflowFileExecutor",
                return_value=mock_executor,
            ) as executor_mock,
        ):
            events = []
            async for event in workflow.execute(inputs):
                events.append(event)

            # Verify WorkflowFileExecutor was created with config
            executor_mock.assert_called_once()
            call_kwargs = executor_mock.call_args[1]
            assert call_kwargs["config"] == config

    @pytest.mark.asyncio
    async def test_converts_inputs_to_dict_for_executor(self) -> None:
        """Test converts RefuelInputs to dict for DSL executor."""
        workflow = RefuelWorkflow()
        workflow.enable_dsl_execution()

        inputs = RefuelInputs(
            label="custom-label",
            limit=10,
            parallel=False,
            dry_run=True,
            auto_assign=False,
        )

        mock_workflow_file = MagicMock()
        mock_executor = MagicMock()

        executed_with_inputs = None

        async def mock_execute(wf, inputs):
            nonlocal executed_with_inputs
            executed_with_inputs = inputs
            yield DslWorkflowStarted(
                workflow_name="refuel",
                inputs=inputs,
                timestamp=0.0,
            )
            yield DslWorkflowCompleted(
                workflow_name="refuel",
                success=True,
                total_duration_ms=1000,
                timestamp=1.0,
            )

        mock_executor.execute = mock_execute
        mock_executor.get_result.return_value = WorkflowResult(
            workflow_name="refuel",
            success=True,
            step_results=(),
            total_duration_ms=1000,
            final_output=None,
        )

        with (
            patch.object(workflow, "_load_workflow", return_value=mock_workflow_file),
            patch(
                "maverick.workflows.refuel.WorkflowFileExecutor",
                return_value=mock_executor,
            ),
        ):
            events = []
            async for event in workflow.execute(inputs):
                events.append(event)

            # Verify inputs were converted to dict
            assert executed_with_inputs == {
                "label": "custom-label",
                "limit": 10,
                "parallel": False,
                "dry_run": True,
                "auto_assign": False,
            }
