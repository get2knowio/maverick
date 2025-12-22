"""Unit tests for the Fly workflow interface.

Tests the public API of the FlyWorkflow class, including initialization,
configuration validation, and workflow execution orchestration.
"""

from __future__ import annotations

import time
from dataclasses import FrozenInstanceError
from datetime import datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from maverick.agents.result import AgentUsage
from maverick.config import MaverickConfig
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
    WorkflowState,
)


class TestWorkflowStage:
    """Tests for WorkflowStage enum."""

    def test_all_stages_exist(self):
        """Test that all 8 expected stages exist."""
        assert hasattr(WorkflowStage, "INIT")
        assert hasattr(WorkflowStage, "IMPLEMENTATION")
        assert hasattr(WorkflowStage, "VALIDATION")
        assert hasattr(WorkflowStage, "CODE_REVIEW")
        assert hasattr(WorkflowStage, "CONVENTION_UPDATE")
        assert hasattr(WorkflowStage, "PR_CREATION")
        assert hasattr(WorkflowStage, "COMPLETE")
        assert hasattr(WorkflowStage, "FAILED")

    def test_string_representation(self):
        """Test that str() returns lowercase string values."""
        assert str(WorkflowStage.INIT) == "init"
        assert str(WorkflowStage.IMPLEMENTATION) == "implementation"
        assert str(WorkflowStage.VALIDATION) == "validation"
        assert str(WorkflowStage.CODE_REVIEW) == "code_review"
        assert str(WorkflowStage.CONVENTION_UPDATE) == "convention_update"
        assert str(WorkflowStage.PR_CREATION) == "pr_creation"
        assert str(WorkflowStage.COMPLETE) == "complete"
        assert str(WorkflowStage.FAILED) == "failed"

    def test_enum_values(self):
        """Test that .value attribute matches expected string."""
        assert WorkflowStage.INIT.value == "init"
        assert WorkflowStage.IMPLEMENTATION.value == "implementation"
        assert WorkflowStage.VALIDATION.value == "validation"
        assert WorkflowStage.CODE_REVIEW.value == "code_review"
        assert WorkflowStage.CONVENTION_UPDATE.value == "convention_update"
        assert WorkflowStage.PR_CREATION.value == "pr_creation"
        assert WorkflowStage.COMPLETE.value == "complete"
        assert WorkflowStage.FAILED.value == "failed"

    def test_all_values_unique(self):
        """Test that all enum values are unique."""
        values = [stage.value for stage in WorkflowStage]
        assert len(values) == len(set(values)), "Enum values must be unique"
        assert len(values) == 8, "Expected exactly 8 stages"


class TestFlyInputs:
    """Tests for FlyInputs data model."""

    def test_validates_branch_name_not_empty(self):
        """Test FlyInputs(branch_name="") should raise ValidationError."""
        with pytest.raises(ValidationError):
            FlyInputs(branch_name="")

    def test_default_values(self):
        """Test FlyInputs default values for optional fields."""
        inputs = FlyInputs(branch_name="test")

        assert inputs.branch_name == "test"
        assert inputs.skip_review is False
        assert inputs.skip_pr is False
        assert inputs.draft_pr is False
        assert inputs.base_branch == "main"
        assert inputs.task_file is None
        assert inputs.dry_run is False

    def test_accepts_all_optional_fields_with_custom_values(self):
        """Test FlyInputs accepts all fields set to custom values."""
        inputs = FlyInputs(
            branch_name="feature-branch",
            skip_review=True,
            skip_pr=True,
            draft_pr=True,
            base_branch="develop",
            task_file="custom-tasks.md",
            dry_run=True,
        )

        assert inputs.branch_name == "feature-branch"
        assert inputs.skip_review is True
        assert inputs.skip_pr is True
        assert inputs.draft_pr is True
        assert inputs.base_branch == "develop"
        assert inputs.task_file == Path("custom-tasks.md")
        assert inputs.dry_run is True


class TestWorkflowState:
    """Tests for WorkflowState mutable state tracking."""

    def test_workflow_state_has_all_required_fields(self):
        """Test WorkflowState has all required fields (T013)."""
        state = WorkflowState(branch="test-branch")

        # Assert all required fields exist
        assert hasattr(state, "stage")
        assert hasattr(state, "branch")
        assert hasattr(state, "task_file")
        assert hasattr(state, "implementation_result")
        assert hasattr(state, "validation_result")
        assert hasattr(state, "review_results")
        assert hasattr(state, "pr_url")
        assert hasattr(state, "errors")
        assert hasattr(state, "started_at")
        assert hasattr(state, "completed_at")

    def test_workflow_state_stage_can_hold_any_workflow_stage_enum_value(self):
        """Test WorkflowState.stage can hold any WorkflowStage enum value (T014)."""
        state = WorkflowState(branch="test-branch", stage=WorkflowStage.INIT)
        assert state.stage == WorkflowStage.INIT

        # Mutate stage to IMPLEMENTATION
        state.stage = WorkflowStage.IMPLEMENTATION
        assert state.stage == WorkflowStage.IMPLEMENTATION

        # Mutate stage to COMPLETE
        state.stage = WorkflowStage.COMPLETE
        assert state.stage == WorkflowStage.COMPLETE

    def test_workflow_state_errors_list_accumulates_strings(self):
        """Test WorkflowState.errors list accumulates strings (T015)."""
        state = WorkflowState(branch="test-branch")

        # Append multiple errors
        state.errors.append("Error 1: Something went wrong")
        state.errors.append("Error 2: Another issue")
        state.errors.append("Error 3: Yet another problem")

        # Assert all errors are present and in order
        assert len(state.errors) == 3
        assert state.errors[0] == "Error 1: Something went wrong"
        assert state.errors[1] == "Error 2: Another issue"
        assert state.errors[2] == "Error 3: Yet another problem"

    def test_workflow_state_default_values(self):
        """Test WorkflowState default values (T016)."""
        state = WorkflowState(branch="test-branch")

        # Assert defaults
        assert state.stage == WorkflowStage.INIT
        assert state.branch == "test-branch"
        assert state.review_results == []
        assert state.errors == []
        assert state.task_file is None
        assert state.implementation_result is None
        assert state.validation_result is None
        assert state.pr_url is None
        assert state.completed_at is None

        # Assert started_at is set (not None)
        assert state.started_at is not None
        assert isinstance(state.started_at, datetime)


class TestFlyConfig:
    """Tests for FlyConfig data model."""

    def test_fly_config_default_values(self):
        """Test FlyConfig default values (T037)."""
        config = FlyConfig()

        # Assert all default values
        assert config.parallel_reviews is True
        assert config.max_validation_attempts == 3
        assert config.coderabbit_enabled is False
        assert config.auto_merge is False
        assert config.notification_on_complete is True

    def test_max_validation_attempts_validates_range_1_to_10(self):
        """Test FlyConfig.max_validation_attempts validates range 1-10 (T038)."""
        # Test invalid values (0 and 11)
        with pytest.raises(ValidationError):
            FlyConfig(max_validation_attempts=0)

        with pytest.raises(ValidationError):
            FlyConfig(max_validation_attempts=11)

        # Test valid boundary values (1 and 10)
        config_min = FlyConfig(max_validation_attempts=1)
        assert config_min.max_validation_attempts == 1

        config_max = FlyConfig(max_validation_attempts=10)
        assert config_max.max_validation_attempts == 10

    def test_fly_config_is_frozen_immutable(self):
        """Test FlyConfig is frozen (immutable) (T039)."""
        config = FlyConfig()

        # Attempt to mutate parallel_reviews should raise ValidationError
        with pytest.raises(ValidationError):
            config.parallel_reviews = False

    def test_maverick_config_fly_field_exists(self):
        """Test MaverickConfig.fly field exists (T043)."""
        config = MaverickConfig()

        # Assert config.fly is a FlyConfig instance
        assert hasattr(config, "fly")
        assert isinstance(config.fly, FlyConfig)

        # Assert config.fly uses default values
        assert config.fly.parallel_reviews is True
        assert config.fly.max_validation_attempts == 3
        assert config.fly.coderabbit_enabled is False
        assert config.fly.auto_merge is False
        assert config.fly.notification_on_complete is True


class TestFlyWorkflow:
    """Tests for FlyWorkflow orchestration."""

    def test_accepts_optional_fly_config_in_constructor(self):
        """Test FlyWorkflow accepts optional FlyConfig in constructor."""
        # Should work with no args
        workflow1 = FlyWorkflow()
        assert workflow1 is not None

        # Should work with explicit config
        config = FlyConfig()
        workflow2 = FlyWorkflow(config=config)
        assert workflow2 is not None


class TestFlyWorkflowExecution:
    """Tests for FlyWorkflow.execute() implementation (User Story 1)."""

    @pytest.mark.asyncio
    async def test_init_stage_creates_branch_without_ai(self, tmp_path):
        """Test INIT stage creates branch via GitRunner without AI (T014)."""
        from unittest.mock import AsyncMock, MagicMock

        from maverick.runners.git import GitResult

        # Setup mocks
        mock_git = MagicMock()
        mock_git.create_branch_with_fallback = AsyncMock(
            return_value=GitResult(
                success=True,
                output="feature-test",
                error=None,
                duration_ms=50,
            )
        )

        # Create task file
        task_file = tmp_path / "tasks.md"
        task_file.write_text("- [ ] T001 Test task")

        # Create workflow with injected runner
        workflow = FlyWorkflow(
            git_runner=mock_git,
            implementer_agent=None,  # Should not be called in INIT
        )
        inputs = FlyInputs(branch_name="feature-test", task_file=task_file)

        # Execute and collect events
        events = []
        async for event in workflow.execute(inputs):
            events.append(event)
            # Stop after INIT stage completes
            if (
                isinstance(event, FlyStageCompleted)
                and event.stage == WorkflowStage.INIT
            ):
                break

        # Verify branch creation was called
        mock_git.create_branch_with_fallback.assert_called_once_with(
            "feature-test", "HEAD"
        )

        # Verify INIT stage events were emitted
        stage_started = [e for e in events if isinstance(e, FlyStageStarted)]
        assert any(e.stage == WorkflowStage.INIT for e in stage_started)

    @pytest.mark.asyncio
    async def test_implementation_stage_invokes_agent(self, tmp_path):
        """Test IMPLEMENTATION stage invokes ImplementerAgent (T015)."""
        from unittest.mock import AsyncMock, MagicMock

        from maverick.agents.result import AgentResult, AgentUsage
        from maverick.runners.git import GitResult

        # Setup mocks
        mock_git = MagicMock()
        mock_git.create_branch_with_fallback = AsyncMock(
            return_value=GitResult(
                success=True, output="test-branch", error=None, duration_ms=50
            )
        )

        mock_agent = MagicMock()
        usage = AgentUsage(
            input_tokens=100, output_tokens=50, total_cost_usd=0.01, duration_ms=1000
        )
        mock_agent.execute = AsyncMock(
            return_value=AgentResult.success_result(
                output="Implementation complete", usage=usage
            )
        )

        # Create task file
        task_file = tmp_path / "tasks.md"
        task_file.write_text("- [ ] T001 Implement feature")

        # Create workflow
        workflow = FlyWorkflow(git_runner=mock_git, implementer_agent=mock_agent)
        inputs = FlyInputs(branch_name="test-branch", task_file=task_file)

        # Execute and collect events
        events = []
        async for event in workflow.execute(inputs):
            events.append(event)
            if (
                isinstance(event, FlyStageCompleted)
                and event.stage == WorkflowStage.IMPLEMENTATION
            ):
                break

        # Verify agent was invoked
        assert mock_agent.execute.call_count >= 1

        # Verify IMPLEMENTATION stage completed
        impl_completed = [
            e
            for e in events
            if isinstance(e, FlyStageCompleted)
            and e.stage == WorkflowStage.IMPLEMENTATION
        ]
        assert len(impl_completed) >= 1

    @pytest.mark.asyncio
    async def test_validation_stage_with_retry(self, tmp_path):
        """Test VALIDATION stage runs ValidationRunner with retry (T016)."""
        from unittest.mock import AsyncMock, MagicMock

        from maverick.agents.result import AgentResult, AgentUsage
        from maverick.models.validation import (
            StageResult,
            StageStatus,
            ValidationWorkflowResult,
        )
        from maverick.runners.git import GitResult

        # Setup mocks
        mock_git = MagicMock()
        mock_git.create_branch_with_fallback = AsyncMock(
            return_value=GitResult(
                success=True, output="test", error=None, duration_ms=50
            )
        )

        mock_agent = MagicMock()
        usage = AgentUsage(
            input_tokens=100, output_tokens=50, total_cost_usd=0.01, duration_ms=1000
        )
        mock_agent.execute = AsyncMock(
            return_value=AgentResult.success_result(output="Done", usage=usage)
        )

        mock_validation = MagicMock()
        # First attempt fails
        mock_validation.run = AsyncMock(
            return_value=iter(
                [
                    ValidationWorkflowResult(
                        success=False,
                        stage_results=[
                            StageResult(
                                stage_name="test",
                                status=StageStatus.FAILED,
                                fix_attempts=0,
                                error_message="Test failed",
                                output="Error",
                                duration_ms=100,
                            )
                        ],
                    )
                ]
            )
        )

        task_file = tmp_path / "tasks.md"
        task_file.write_text("- [ ] T001 Test")

        workflow = FlyWorkflow(
            git_runner=mock_git,
            implementer_agent=mock_agent,
            validation_runner=mock_validation,
        )
        inputs = FlyInputs(branch_name="test", task_file=task_file)

        # Execute workflow
        events = []
        async for event in workflow.execute(inputs):
            events.append(event)
            if (
                isinstance(event, FlyStageCompleted)
                and event.stage == WorkflowStage.VALIDATION
            ):
                break

        # Verify validation was attempted
        assert mock_validation.run.call_count >= 1

    @pytest.mark.asyncio
    async def test_code_review_stage_optional_coderabbit(self, tmp_path):
        """Test CODE_REVIEW stage with optional CodeRabbit (T017)."""
        from unittest.mock import AsyncMock, MagicMock

        from maverick.agents.result import AgentResult, AgentUsage
        from maverick.models.validation import ValidationWorkflowResult
        from maverick.runners.git import GitResult

        # Setup mocks
        mock_git = MagicMock()
        mock_git.create_branch_with_fallback = AsyncMock(
            return_value=GitResult(
                success=True, output="test", error=None, duration_ms=50
            )
        )

        usage = AgentUsage(
            input_tokens=100, output_tokens=50, total_cost_usd=0.01, duration_ms=1000
        )
        mock_agent = MagicMock()
        mock_agent.execute = AsyncMock(
            return_value=AgentResult.success_result(output="Done", usage=usage)
        )

        mock_validation = MagicMock()
        mock_validation.run = AsyncMock(
            return_value=iter(
                [ValidationWorkflowResult(success=True, stage_results=[])]
            )
        )

        mock_reviewer = MagicMock()
        mock_reviewer.execute = AsyncMock(
            return_value=AgentResult.success_result(
                output="Review complete", usage=usage
            )
        )

        task_file = tmp_path / "tasks.md"
        task_file.write_text("- [ ] T001 Test")

        # Test without CodeRabbit
        config = FlyConfig(coderabbit_enabled=False)
        workflow = FlyWorkflow(
            config=config,
            git_runner=mock_git,
            implementer_agent=mock_agent,
            validation_runner=mock_validation,
            code_reviewer_agent=mock_reviewer,
        )
        inputs = FlyInputs(branch_name="test", task_file=task_file)

        events = []
        async for event in workflow.execute(inputs):
            events.append(event)
            if (
                isinstance(event, FlyStageCompleted)
                and event.stage == WorkflowStage.CODE_REVIEW
            ):
                break

        # Verify reviewer was called even without CodeRabbit
        assert mock_reviewer.execute.call_count >= 1

    @pytest.mark.asyncio
    async def test_pr_creation_stage_generates_description(self, tmp_path):
        """Test PR_CREATION stage generates PR body (T018)."""
        from unittest.mock import AsyncMock, MagicMock

        from maverick.agents.result import AgentResult, AgentUsage
        from maverick.models.validation import ValidationWorkflowResult
        from maverick.runners.git import GitResult

        # Setup mocks
        mock_git = MagicMock()
        mock_git.create_branch_with_fallback = AsyncMock(
            return_value=GitResult(
                success=True, output="test", error=None, duration_ms=50
            )
        )
        mock_git.diff = AsyncMock(return_value="test diff")
        mock_git.commit = AsyncMock(
            return_value=GitResult(
                success=True, output="commit created", error=None, duration_ms=50
            )
        )

        usage = AgentUsage(
            input_tokens=100, output_tokens=50, total_cost_usd=0.01, duration_ms=1000
        )

        mock_agent = MagicMock()
        mock_agent.execute = AsyncMock(
            return_value=AgentResult.success_result(output="Done", usage=usage)
        )

        mock_validation = MagicMock()
        mock_validation.run = AsyncMock(
            return_value=iter(
                [ValidationWorkflowResult(success=True, stage_results=[])]
            )
        )

        mock_reviewer = MagicMock()
        mock_reviewer.execute = AsyncMock(
            return_value=AgentResult.success_result(output="Review done", usage=usage)
        )

        mock_commit_gen = MagicMock()
        mock_commit_gen.generate = AsyncMock(return_value="feat: test commit")

        mock_pr_gen = MagicMock()
        mock_pr_gen.generate = AsyncMock(return_value="## Summary\nTest PR")

        mock_github = MagicMock()
        mock_github.create_pr = AsyncMock(return_value="https://github.com/test/pr/1")

        task_file = tmp_path / "tasks.md"
        task_file.write_text("- [ ] T001 Test")

        workflow = FlyWorkflow(
            git_runner=mock_git,
            implementer_agent=mock_agent,
            validation_runner=mock_validation,
            code_reviewer_agent=mock_reviewer,
            commit_generator=mock_commit_gen,
            pr_generator=mock_pr_gen,
            github_runner=mock_github,
        )
        inputs = FlyInputs(branch_name="test", task_file=task_file, skip_pr=False)

        events = []
        async for event in workflow.execute(inputs):
            events.append(event)

        # Verify PR generator was called
        assert mock_pr_gen.generate.call_count >= 1

        # Verify GitHub PR creation was called
        assert mock_github.create_pr.call_count >= 1

    @pytest.mark.asyncio
    async def test_progress_events_emitted_at_each_stage(self, tmp_path):
        """Test progress events are emitted at each stage (T019)."""
        from unittest.mock import AsyncMock, MagicMock

        from maverick.agents.result import AgentResult, AgentUsage
        from maverick.models.validation import ValidationWorkflowResult
        from maverick.runners.git import GitResult

        # Setup minimal mocks
        mock_git = MagicMock()
        mock_git.create_branch_with_fallback = AsyncMock(
            return_value=GitResult(
                success=True, output="test", error=None, duration_ms=50
            )
        )
        mock_git.diff = AsyncMock(return_value="diff")
        mock_git.commit = AsyncMock(
            return_value=GitResult(
                success=True, output="commit", error=None, duration_ms=50
            )
        )

        usage = AgentUsage(
            input_tokens=100, output_tokens=50, total_cost_usd=0.01, duration_ms=1000
        )
        mock_agent = MagicMock()
        mock_agent.execute = AsyncMock(
            return_value=AgentResult.success_result(output="Done", usage=usage)
        )

        mock_validation = MagicMock()
        mock_validation.run = AsyncMock(
            return_value=iter(
                [ValidationWorkflowResult(success=True, stage_results=[])]
            )
        )

        mock_reviewer = MagicMock()
        mock_reviewer.execute = AsyncMock(
            return_value=AgentResult.success_result(output="Review", usage=usage)
        )

        mock_commit_gen = MagicMock()
        mock_commit_gen.generate = AsyncMock(return_value="feat: test")

        mock_pr_gen = MagicMock()
        mock_pr_gen.generate = AsyncMock(return_value="## Summary\nTest")

        mock_github = MagicMock()
        mock_github.create_pr = AsyncMock(return_value="https://github.com/test/pr/1")

        task_file = tmp_path / "tasks.md"
        task_file.write_text("- [ ] T001 Test task")

        workflow = FlyWorkflow(
            git_runner=mock_git,
            implementer_agent=mock_agent,
            validation_runner=mock_validation,
            code_reviewer_agent=mock_reviewer,
            commit_generator=mock_commit_gen,
            pr_generator=mock_pr_gen,
            github_runner=mock_github,
        )
        inputs = FlyInputs(branch_name="test", task_file=task_file)

        events = []
        async for event in workflow.execute(inputs):
            events.append(event)

        # Verify workflow started event
        started_events = [e for e in events if isinstance(e, FlyWorkflowStarted)]
        assert len(started_events) == 1

        # Verify each stage has started and completed events
        stage_started = [e for e in events if isinstance(e, FlyStageStarted)]
        stage_completed = [e for e in events if isinstance(e, FlyStageCompleted)]

        # Should have at least INIT, IMPLEMENTATION, VALIDATION, CODE_REVIEW,
        # PR_CREATION
        assert len(stage_started) >= 5
        assert len(stage_completed) >= 5

        # Verify workflow completed
        completed_events = [e for e in events if isinstance(e, FlyWorkflowCompleted)]
        assert len(completed_events) == 1

    @pytest.mark.asyncio
    async def test_error_handling_stage_failure_continues(self, tmp_path):
        """Test error handling: stage failure continues workflow (T020)."""
        from unittest.mock import AsyncMock, MagicMock

        from maverick.agents.result import AgentResult, AgentUsage
        from maverick.models.validation import (
            StageResult,
            StageStatus,
            ValidationWorkflowResult,
        )
        from maverick.runners.git import GitResult

        # Setup mocks
        mock_git = MagicMock()
        mock_git.create_branch_with_fallback = AsyncMock(
            return_value=GitResult(
                success=True, output="test", error=None, duration_ms=50
            )
        )
        mock_git.diff = AsyncMock(return_value="diff")
        mock_git.commit = AsyncMock(
            return_value=GitResult(
                success=True, output="commit", error=None, duration_ms=50
            )
        )

        usage = AgentUsage(
            input_tokens=100, output_tokens=50, total_cost_usd=0.01, duration_ms=1000
        )
        mock_agent = MagicMock()
        mock_agent.execute = AsyncMock(
            return_value=AgentResult.success_result(output="Done", usage=usage)
        )

        # Validation fails
        mock_validation = MagicMock()
        mock_validation.run = AsyncMock(
            return_value=iter(
                [
                    ValidationWorkflowResult(
                        success=False,
                        stage_results=[
                            StageResult(
                                stage_name="test",
                                status=StageStatus.FAILED,
                                fix_attempts=0,
                                error_message="Failed",
                                output="",
                                duration_ms=100,
                            )
                        ],
                    )
                ]
            )
        )

        mock_reviewer = MagicMock()
        mock_reviewer.execute = AsyncMock(
            return_value=AgentResult.success_result(output="Review", usage=usage)
        )

        mock_commit_gen = MagicMock()
        mock_commit_gen.generate = AsyncMock(return_value="feat: test")

        mock_pr_gen = MagicMock()
        mock_pr_gen.generate = AsyncMock(return_value="## Summary\nTest")

        mock_github = MagicMock()
        mock_github.create_pr = AsyncMock(return_value="https://github.com/test/pr/1")

        task_file = tmp_path / "tasks.md"
        task_file.write_text("- [ ] T001 Test")

        config = FlyConfig(max_validation_attempts=1)
        workflow = FlyWorkflow(
            config=config,
            git_runner=mock_git,
            implementer_agent=mock_agent,
            validation_runner=mock_validation,
            code_reviewer_agent=mock_reviewer,
            commit_generator=mock_commit_gen,
            pr_generator=mock_pr_gen,
            github_runner=mock_github,
        )
        inputs = FlyInputs(branch_name="test", task_file=task_file)

        events = []
        async for event in workflow.execute(inputs):
            events.append(event)

        # Workflow should continue despite validation failure
        # Verify CODE_REVIEW stage was reached
        review_started = [
            e
            for e in events
            if isinstance(e, FlyStageStarted) and e.stage == WorkflowStage.CODE_REVIEW
        ]
        assert len(review_started) >= 1

        # Result should indicate validation failed but workflow completed
        result = workflow.get_result()
        assert result is not None
        # Workflow should have errors but not fail completely
        assert (
            len(result.state.errors) > 0 or not result.state.validation_result.success
        )


# Helper functions for creating test objects
def make_agent_usage() -> AgentUsage:
    """Create a valid AgentUsage for testing."""
    return AgentUsage(
        input_tokens=100,
        output_tokens=50,
        total_cost_usd=0.01,
        duration_ms=1000,
    )


class TestFlyResult:
    """Tests for FlyResult data model."""

    def test_fly_result_has_all_required_fields(self):
        """Test FlyResult has all required fields (T019)."""
        state = WorkflowState(branch="test-branch")
        usage = make_agent_usage()

        result = FlyResult(
            success=True,
            state=state,
            summary="Workflow completed successfully",
            token_usage=usage,
            total_cost_usd=0.05,
        )

        # Assert all required fields exist
        assert hasattr(result, "success")
        assert hasattr(result, "state")
        assert hasattr(result, "summary")
        assert hasattr(result, "token_usage")
        assert hasattr(result, "total_cost_usd")

    def test_fly_result_total_cost_usd_validates_non_negative(self):
        """Test FlyResult.total_cost_usd validates non-negative (T020)."""
        state = WorkflowState(branch="test-branch")
        usage = make_agent_usage()

        # Negative cost should raise ValidationError
        with pytest.raises(ValidationError):
            FlyResult(
                success=True,
                state=state,
                summary="Test",
                token_usage=usage,
                total_cost_usd=-1.0,
            )

        # Zero cost should work
        result_zero = FlyResult(
            success=True,
            state=state,
            summary="Test",
            token_usage=usage,
            total_cost_usd=0.0,
        )
        assert result_zero.total_cost_usd == 0.0

        # Positive cost should work
        result_positive = FlyResult(
            success=True,
            state=state,
            summary="Test",
            token_usage=usage,
            total_cost_usd=100.0,
        )
        assert result_positive.total_cost_usd == 100.0

    def test_fly_result_is_frozen_immutable(self):
        """Test FlyResult is frozen (immutable) (T021)."""
        state = WorkflowState(branch="test-branch")
        usage = make_agent_usage()

        result = FlyResult(
            success=True,
            state=state,
            summary="Test",
            token_usage=usage,
            total_cost_usd=0.05,
        )

        # Attempt to mutate success should raise ValidationError (frozen model)
        with pytest.raises(ValidationError):
            result.success = False

    def test_fly_result_summary_is_human_readable_string(self):
        """Test FlyResult.summary is human-readable string (T022)."""
        state = WorkflowState(branch="test-branch")
        usage = make_agent_usage()
        summary_text = "Workflow completed successfully with 3 tasks implemented"

        result = FlyResult(
            success=True,
            state=state,
            summary=summary_text,
            token_usage=usage,
            total_cost_usd=0.05,
        )

        # Assert summary is the provided string
        assert result.summary == summary_text
        # Assert type(summary) is str
        assert type(result.summary) is str


class TestProgressEvents:
    """Tests for progress event dataclasses."""

    def test_fly_workflow_started_has_inputs_and_timestamp(self):
        """Test FlyWorkflowStarted has inputs and timestamp fields (T025)."""
        inputs = FlyInputs(branch_name="test-branch")

        # Create without explicit timestamp - should default to current time
        before_time = time.time()
        event = FlyWorkflowStarted(inputs=inputs)
        after_time = time.time()

        # Assert inputs field is accessible
        assert event.inputs == inputs

        # Assert timestamp is set and within reasonable range
        assert hasattr(event, "timestamp")
        assert isinstance(event.timestamp, float)
        assert before_time <= event.timestamp <= after_time

    def test_fly_stage_started_has_stage_and_timestamp(self):
        """Test FlyStageStarted has stage and timestamp fields (T026)."""
        # Create with WorkflowStage.IMPLEMENTATION
        event = FlyStageStarted(
            stage=WorkflowStage.IMPLEMENTATION, timestamp=time.time()
        )

        # Verify both fields are accessible
        assert event.stage == WorkflowStage.IMPLEMENTATION
        assert isinstance(event.timestamp, float)

    def test_fly_stage_completed_has_stage_result_and_timestamp(self):
        """Test FlyStageCompleted has stage, result, and timestamp fields (T027)."""
        # result can be any type (string, dict, etc.)
        stage = WorkflowStage.IMPLEMENTATION
        result_str = "Implementation completed"
        result_dict = {"tasks_completed": 5, "errors": 0}

        # Create with string result
        event1 = FlyStageCompleted(
            stage=stage, result=result_str, timestamp=time.time()
        )
        assert event1.stage == stage
        assert event1.result == result_str

        # Create with dict result
        event2 = FlyStageCompleted(
            stage=stage, result=result_dict, timestamp=time.time()
        )
        assert event2.stage == stage
        assert event2.result == result_dict

    def test_fly_workflow_completed_has_result_and_timestamp(self):
        """Test FlyWorkflowCompleted has result and timestamp fields (T028)."""
        # Create FlyResult instance
        state = WorkflowState(branch="test-branch")
        usage = make_agent_usage()
        fly_result = FlyResult(
            success=True,
            state=state,
            summary="Workflow completed",
            token_usage=usage,
            total_cost_usd=0.05,
        )

        # Create event
        event = FlyWorkflowCompleted(result=fly_result, timestamp=time.time())

        # Verify result is accessible
        assert event.result == fly_result
        assert isinstance(event.timestamp, float)

    def test_fly_workflow_failed_has_error_state_and_timestamp(self):
        """Test FlyWorkflowFailed has error, state, and timestamp fields (T029)."""
        # Create WorkflowState instance
        state = WorkflowState(branch="test-branch")
        state.errors.append("Something went wrong")

        error_message = "Workflow failed during validation"

        # Create event
        event = FlyWorkflowFailed(
            error=error_message, state=state, timestamp=time.time()
        )

        # Verify all fields accessible
        assert event.error == error_message
        assert event.state == state
        assert isinstance(event.timestamp, float)

    def test_all_progress_events_are_frozen_dataclasses_with_slots(self):
        """Test all progress events are frozen dataclasses with slots=True (T030)."""
        inputs = FlyInputs(branch_name="test-branch")
        state = WorkflowState(branch="test-branch")
        usage = make_agent_usage()
        fly_result = FlyResult(
            success=True,
            state=state,
            summary="Test",
            token_usage=usage,
            total_cost_usd=0.05,
        )

        # Create instances of all event types
        event1 = FlyWorkflowStarted(inputs=inputs)
        event2 = FlyStageStarted(
            stage=WorkflowStage.IMPLEMENTATION, timestamp=time.time()
        )
        event3 = FlyStageCompleted(
            stage=WorkflowStage.IMPLEMENTATION,
            result="done",
            timestamp=time.time(),
        )
        event4 = FlyWorkflowCompleted(result=fly_result, timestamp=time.time())
        event5 = FlyWorkflowFailed(
            error="test error", state=state, timestamp=time.time()
        )

        events = [event1, event2, event3, event4, event5]
        event_names = [
            "FlyWorkflowStarted",
            "FlyStageStarted",
            "FlyStageCompleted",
            "FlyWorkflowCompleted",
            "FlyWorkflowFailed",
        ]

        for event, name in zip(events, event_names, strict=True):
            # Test immutability (frozen=True)
            with pytest.raises(FrozenInstanceError):
                event.timestamp = time.time()

            # Test slots=True (should have __slots__ attribute)
            assert hasattr(type(event), "__slots__"), f"{name} should have __slots__"


class TestInterfaceIntegration:
    """Integration tests for interface types."""

    def test_all_interface_types_importable(self):
        """Test all interface types importable from maverick.workflows.fly."""
        from enum import Enum

        from pydantic import BaseModel

        from maverick.workflows.fly import (
            FlyConfig,
            FlyInputs,
            FlyProgressEvent,
            FlyResult,
            FlyStageCompleted,
            FlyStageStarted,
            FlyWorkflow,
            FlyWorkflowCompleted,
            FlyWorkflowFailed,
            FlyWorkflowStarted,
            WorkflowStage,
            WorkflowState,
        )

        # Verify they are the correct types
        assert issubclass(WorkflowStage, Enum)
        assert issubclass(FlyConfig, BaseModel)
        assert issubclass(FlyInputs, BaseModel)
        assert issubclass(FlyResult, BaseModel)

        # Verify event dataclasses are classes (not types)
        assert isinstance(FlyWorkflowStarted, type)
        assert isinstance(FlyStageStarted, type)
        assert isinstance(FlyStageCompleted, type)
        assert isinstance(FlyWorkflowCompleted, type)
        assert isinstance(FlyWorkflowFailed, type)

        # Verify union type
        assert FlyProgressEvent is not None

        # Verify workflow class
        assert isinstance(FlyWorkflow, type)

        # Verify state class
        assert isinstance(WorkflowState, type)

    def test_interface_types_integrate_with_existing_types(self):
        """Test interface types integrate with existing types (T047)."""
        from maverick.agents.result import AgentResult, AgentUsage
        from maverick.models.validation import ValidationWorkflowResult

        # Create a WorkflowState with AgentResult for implementation_result
        usage = AgentUsage(
            input_tokens=100, output_tokens=50, total_cost_usd=0.01, duration_ms=1000
        )
        # AgentResult requires either success_result or failure_result factory
        agent_result = AgentResult.success_result(output="test", usage=usage)

        state = WorkflowState(branch="test")
        state.implementation_result = agent_result
        assert state.implementation_result is agent_result

        # Create a WorkflowState with ValidationWorkflowResult
        validation_result = ValidationWorkflowResult(
            success=True,
            stage_results=[],
        )
        state.validation_result = validation_result
        assert state.validation_result is validation_result


class TestProgressEventEmission:
    """Tests for User Story 4: Progress Event Emission."""

    @pytest.mark.asyncio
    async def test_workflow_started_event_emission(self, tmp_path):
        """Test FlyWorkflowStarted event emitted at workflow start (T067)."""
        from unittest.mock import AsyncMock, MagicMock

        from maverick.runners.git import GitResult

        # Setup minimal mocks
        mock_git = MagicMock()
        mock_git.create_branch_with_fallback = AsyncMock(
            return_value=GitResult(
                success=True, output="test-branch", error=None, duration_ms=50
            )
        )

        task_file = tmp_path / "tasks.md"
        task_file.write_text("- [ ] T001 Test task")

        workflow = FlyWorkflow(git_runner=mock_git)
        inputs = FlyInputs(branch_name="test-branch", task_file=task_file)

        # Collect events
        events = []
        async for event in workflow.execute(inputs):
            events.append(event)
            # Stop after INIT completes
            if (
                isinstance(event, FlyStageCompleted)
                and event.stage == WorkflowStage.INIT
            ):
                break

        # Verify FlyWorkflowStarted is first event
        assert len(events) >= 1
        assert isinstance(events[0], FlyWorkflowStarted)

        # Verify it contains the inputs
        started_event = events[0]
        assert started_event.inputs == inputs
        assert started_event.inputs.branch_name == "test-branch"

        # Verify timestamp is set
        assert hasattr(started_event, "timestamp")
        assert isinstance(started_event.timestamp, float)
        assert started_event.timestamp > 0

    @pytest.mark.asyncio
    async def test_stage_started_completed_event_pairs(self, tmp_path):
        """Test FlyStageStarted/Completed event pairs for each stage (T068)."""
        from unittest.mock import AsyncMock, MagicMock

        from maverick.agents.result import AgentResult, AgentUsage
        from maverick.models.validation import ValidationWorkflowResult
        from maverick.runners.git import GitResult

        # Setup mocks
        mock_git = MagicMock()
        mock_git.create_branch_with_fallback = AsyncMock(
            return_value=GitResult(
                success=True, output="test", error=None, duration_ms=50
            )
        )
        mock_git.diff = AsyncMock(return_value="diff")
        mock_git.commit = AsyncMock(
            return_value=GitResult(
                success=True, output="commit", error=None, duration_ms=50
            )
        )

        usage = AgentUsage(
            input_tokens=100, output_tokens=50, total_cost_usd=0.01, duration_ms=1000
        )
        mock_agent = MagicMock()
        mock_agent.execute = AsyncMock(
            return_value=AgentResult.success_result(output="Done", usage=usage)
        )

        mock_validation = MagicMock()
        mock_validation.run = AsyncMock(
            return_value=iter(
                [ValidationWorkflowResult(success=True, stage_results=[])]
            )
        )

        mock_reviewer = MagicMock()
        mock_reviewer.execute = AsyncMock(
            return_value=AgentResult.success_result(output="Review", usage=usage)
        )

        mock_commit_gen = MagicMock()
        mock_commit_gen.generate = AsyncMock(return_value="feat: test")

        mock_pr_gen = MagicMock()
        mock_pr_gen.generate = AsyncMock(return_value="## Summary\nTest")

        mock_github = MagicMock()
        mock_github.create_pr = AsyncMock(return_value="https://github.com/test/pr/1")

        task_file = tmp_path / "tasks.md"
        task_file.write_text("- [ ] T001 Test")

        workflow = FlyWorkflow(
            git_runner=mock_git,
            implementer_agent=mock_agent,
            validation_runner=mock_validation,
            code_reviewer_agent=mock_reviewer,
            commit_generator=mock_commit_gen,
            pr_generator=mock_pr_gen,
            github_runner=mock_github,
        )
        inputs = FlyInputs(branch_name="test", task_file=task_file)

        # Collect events
        events = []
        async for event in workflow.execute(inputs):
            events.append(event)

        # Extract stage started and completed events
        stage_started = [e for e in events if isinstance(e, FlyStageStarted)]
        stage_completed = [e for e in events if isinstance(e, FlyStageCompleted)]

        # Verify we have matching pairs
        assert (
            len(stage_started) >= 5
        )  # INIT, IMPLEMENTATION, VALIDATION, CODE_REVIEW, PR_CREATION
        assert len(stage_completed) >= 5

        # Verify each stage has both started and completed
        stages_with_started = {e.stage for e in stage_started}
        stages_with_completed = {e.stage for e in stage_completed}

        expected_stages = {
            WorkflowStage.INIT,
            WorkflowStage.IMPLEMENTATION,
            WorkflowStage.VALIDATION,
            WorkflowStage.CODE_REVIEW,
            WorkflowStage.PR_CREATION,
        }

        assert expected_stages.issubset(stages_with_started)
        assert expected_stages.issubset(stages_with_completed)

        # Verify order: for each stage, started comes before completed
        for stage in expected_stages:
            started_idx = next(
                i
                for i, e in enumerate(events)
                if isinstance(e, FlyStageStarted) and e.stage == stage
            )
            completed_idx = next(
                i
                for i, e in enumerate(events)
                if isinstance(e, FlyStageCompleted) and e.stage == stage
            )
            assert started_idx < completed_idx, (
                f"Stage {stage} started must come before completed"
            )

    @pytest.mark.asyncio
    async def test_validation_retry_progress_updates(self, tmp_path):
        """Test validation retry progress updates in events (T069)."""
        from unittest.mock import AsyncMock, MagicMock

        from maverick.agents.result import AgentResult, AgentUsage
        from maverick.models.validation import (
            StageResult,
            StageStatus,
        )
        from maverick.runners.git import GitResult

        # Setup mocks
        mock_git = MagicMock()
        mock_git.create_branch_with_fallback = AsyncMock(
            return_value=GitResult(
                success=True, output="test", error=None, duration_ms=50
            )
        )

        usage = AgentUsage(
            input_tokens=100, output_tokens=50, total_cost_usd=0.01, duration_ms=1000
        )
        mock_agent = MagicMock()
        mock_agent.execute = AsyncMock(
            return_value=AgentResult.success_result(output="Done", usage=usage)
        )

        # Validation runner that returns results
        # Create a mock ValidationOutput that has success and stages attributes
        from maverick.runners.models import ValidationOutput

        mock_validation_output = MagicMock(spec=ValidationOutput)
        mock_validation_output.success = False
        mock_validation_output.stages = [
            StageResult(
                stage_name="format",
                status=StageStatus.FAILED,
                fix_attempts=1,
                error_message="Formatting errors detected",
                output="File needs formatting",
                duration_ms=200,
            )
        ]

        mock_validation = MagicMock()
        mock_validation.run = AsyncMock(return_value=mock_validation_output)

        task_file = tmp_path / "tasks.md"
        task_file.write_text("- [ ] T001 Test")

        config = FlyConfig(max_validation_attempts=2)
        workflow = FlyWorkflow(
            config=config,
            git_runner=mock_git,
            implementer_agent=mock_agent,
            validation_runner=mock_validation,
        )
        inputs = FlyInputs(branch_name="test", task_file=task_file)

        # Collect events
        events = []
        async for event in workflow.execute(inputs):
            events.append(event)
            # Stop after validation completes
            if (
                isinstance(event, FlyStageCompleted)
                and event.stage == WorkflowStage.VALIDATION
            ):
                break

        # Verify VALIDATION stage events exist
        validation_started = [
            e
            for e in events
            if isinstance(e, FlyStageStarted) and e.stage == WorkflowStage.VALIDATION
        ]
        validation_completed = [
            e
            for e in events
            if isinstance(e, FlyStageCompleted) and e.stage == WorkflowStage.VALIDATION
        ]

        assert len(validation_started) >= 1
        assert len(validation_completed) >= 1

        # Verify completed event contains validation result
        completed_event = validation_completed[0]
        assert completed_event.result is not None
        # Result should be ValidationWorkflowResult
        assert hasattr(completed_event.result, "success")
        assert completed_event.result.success is False  # Validation failed

        # Verify stage results contain retry information
        if hasattr(completed_event.result, "stage_results"):
            assert len(completed_event.result.stage_results) > 0
