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

    def test_accepts_all_optional_fields_with_custom_values(self):
        """Test FlyInputs accepts all fields set to custom values."""
        inputs = FlyInputs(
            branch_name="feature-branch",
            skip_review=True,
            skip_pr=True,
            draft_pr=True,
            base_branch="develop",
            task_file="custom-tasks.md",
        )

        assert inputs.branch_name == "feature-branch"
        assert inputs.skip_review is True
        assert inputs.skip_pr is True
        assert inputs.draft_pr is True
        assert inputs.base_branch == "develop"
        assert inputs.task_file == Path("custom-tasks.md")


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

    @pytest.mark.asyncio
    async def test_execute_raises_not_implemented_with_spec_26_message(self):
        """Test FlyWorkflow.execute() raises NotImplementedError with Spec 26."""
        workflow = FlyWorkflow()
        inputs = FlyInputs(branch_name="test-branch")

        with pytest.raises(NotImplementedError) as exc_info:
            await workflow.execute(inputs)

        assert "Spec 26" in str(exc_info.value)

    def test_accepts_optional_fly_config_in_constructor(self):
        """Test FlyWorkflow accepts optional FlyConfig in constructor."""
        # Should work with no args
        workflow1 = FlyWorkflow()
        assert workflow1 is not None

        # Should work with explicit config
        config = FlyConfig()
        workflow2 = FlyWorkflow(config=config)
        assert workflow2 is not None


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
            stage=WorkflowStage.IMPLEMENTATION,
            timestamp=time.time()
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
            stage=stage,
            result=result_str,
            timestamp=time.time()
        )
        assert event1.stage == stage
        assert event1.result == result_str

        # Create with dict result
        event2 = FlyStageCompleted(
            stage=stage,
            result=result_dict,
            timestamp=time.time()
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
        event = FlyWorkflowCompleted(
            result=fly_result,
            timestamp=time.time()
        )

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
            error=error_message,
            state=state,
            timestamp=time.time()
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
