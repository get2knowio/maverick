"""Unit tests for DSL progress events.

Tests for StepStarted, StepCompleted, WorkflowStarted, and WorkflowCompleted events.
"""

from __future__ import annotations

import time

import pytest

from maverick.dsl import (
    StepCompleted,
    StepStarted,
    StepType,
    WorkflowCompleted,
    WorkflowStarted,
)


class TestStepStarted:
    """Test suite for StepStarted event."""

    def test_creation_with_all_fields(self) -> None:
        """Test creating StepStarted with all fields."""
        timestamp = time.time()
        event = StepStarted(
            step_name="test_step",
            step_type=StepType.PYTHON,
            timestamp=timestamp,
        )
        assert event.step_name == "test_step"
        assert event.step_type == StepType.PYTHON
        assert event.timestamp == timestamp

    def test_timestamp_defaults_to_current_time(self) -> None:
        """Test that timestamp defaults to current time if not provided."""
        before = time.time()
        event = StepStarted(
            step_name="test_step",
            step_type=StepType.AGENT,
        )
        after = time.time()

        # Timestamp should be between before and after
        assert before <= event.timestamp <= after

    def test_timestamp_is_float(self) -> None:
        """Test that timestamp is a float."""
        event = StepStarted(
            step_name="test_step",
            step_type=StepType.PYTHON,
        )
        assert isinstance(event.timestamp, float)

    def test_all_fields_accessible(self) -> None:
        """Test that all fields can be accessed."""
        event = StepStarted(
            step_name="my_step",
            step_type=StepType.GENERATE,
        )
        assert event.step_name == "my_step"
        assert event.step_type == StepType.GENERATE
        assert hasattr(event, "timestamp")

    def test_event_is_frozen(self) -> None:
        """Test that StepStarted is immutable (frozen)."""
        event = StepStarted(
            step_name="test_step",
            step_type=StepType.PYTHON,
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            event.step_name = "modified"  # type: ignore[misc]

    def test_different_step_types(self) -> None:
        """Test StepStarted with different step types."""
        for step_type in StepType:
            event = StepStarted(
                step_name=f"{step_type.value}_step",
                step_type=step_type,
            )
            assert event.step_type == step_type


class TestStepCompleted:
    """Test suite for StepCompleted event."""

    def test_creation_with_all_fields(self) -> None:
        """Test creating StepCompleted with all fields."""
        timestamp = time.time()
        event = StepCompleted(
            step_name="test_step",
            step_type=StepType.PYTHON,
            success=True,
            duration_ms=100,
            timestamp=timestamp,
        )
        assert event.step_name == "test_step"
        assert event.step_type == StepType.PYTHON
        assert event.success is True
        assert event.duration_ms == 100
        assert event.timestamp == timestamp

    def test_creation_failed_step(self) -> None:
        """Test creating StepCompleted for a failed step."""
        event = StepCompleted(
            step_name="failed_step",
            step_type=StepType.AGENT,
            success=False,
            duration_ms=50,
        )
        assert event.step_name == "failed_step"
        assert event.step_type == StepType.AGENT
        assert event.success is False
        assert event.duration_ms == 50

    def test_timestamp_defaults_to_current_time(self) -> None:
        """Test that timestamp defaults to current time if not provided."""
        before = time.time()
        event = StepCompleted(
            step_name="test_step",
            step_type=StepType.VALIDATE,
            success=True,
            duration_ms=75,
        )
        after = time.time()

        assert before <= event.timestamp <= after

    def test_timestamp_is_float(self) -> None:
        """Test that timestamp is a float."""
        event = StepCompleted(
            step_name="test_step",
            step_type=StepType.PYTHON,
            success=True,
            duration_ms=10,
        )
        assert isinstance(event.timestamp, float)

    def test_all_fields_accessible(self) -> None:
        """Test that all fields can be accessed."""
        event = StepCompleted(
            step_name="my_step",
            step_type=StepType.SUBWORKFLOW,
            success=True,
            duration_ms=200,
        )
        assert event.step_name == "my_step"
        assert event.step_type == StepType.SUBWORKFLOW
        assert event.success is True
        assert event.duration_ms == 200
        assert hasattr(event, "timestamp")

    def test_event_is_frozen(self) -> None:
        """Test that StepCompleted is immutable (frozen)."""
        event = StepCompleted(
            step_name="test_step",
            step_type=StepType.PYTHON,
            success=True,
            duration_ms=10,
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            event.success = False  # type: ignore[misc]

    def test_zero_duration(self) -> None:
        """Test StepCompleted with zero duration."""
        event = StepCompleted(
            step_name="instant_step",
            step_type=StepType.PYTHON,
            success=True,
            duration_ms=0,
        )
        assert event.duration_ms == 0


class TestWorkflowStarted:
    """Test suite for WorkflowStarted event."""

    def test_creation_with_all_fields(self) -> None:
        """Test creating WorkflowStarted with all fields."""
        timestamp = time.time()
        inputs = {"branch": "main", "issue": 42}
        event = WorkflowStarted(
            workflow_name="test_workflow",
            inputs=inputs,
            timestamp=timestamp,
        )
        assert event.workflow_name == "test_workflow"
        assert event.inputs == inputs
        assert event.timestamp == timestamp

    def test_creation_with_empty_inputs(self) -> None:
        """Test creating WorkflowStarted with empty inputs."""
        event = WorkflowStarted(
            workflow_name="no_input_workflow",
            inputs={},
        )
        assert event.workflow_name == "no_input_workflow"
        assert event.inputs == {}

    def test_timestamp_defaults_to_current_time(self) -> None:
        """Test that timestamp defaults to current time if not provided."""
        before = time.time()
        event = WorkflowStarted(
            workflow_name="test_workflow",
            inputs={"key": "value"},
        )
        after = time.time()

        assert before <= event.timestamp <= after

    def test_timestamp_is_float(self) -> None:
        """Test that timestamp is a float."""
        event = WorkflowStarted(
            workflow_name="test_workflow",
            inputs={},
        )
        assert isinstance(event.timestamp, float)

    def test_all_fields_accessible(self) -> None:
        """Test that all fields can be accessed."""
        inputs = {"param1": "value1", "param2": 123}
        event = WorkflowStarted(
            workflow_name="my_workflow",
            inputs=inputs,
        )
        assert event.workflow_name == "my_workflow"
        assert event.inputs == inputs
        assert hasattr(event, "timestamp")

    def test_event_is_frozen(self) -> None:
        """Test that WorkflowStarted is immutable (frozen)."""
        event = WorkflowStarted(
            workflow_name="test_workflow",
            inputs={},
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            event.workflow_name = "modified"  # type: ignore[misc]

    def test_inputs_dict_not_shared(self) -> None:
        """Test that inputs dict is properly isolated between instances."""
        inputs1 = {"key": "value1"}
        inputs2 = {"key": "value2"}

        event1 = WorkflowStarted(workflow_name="wf1", inputs=inputs1)
        event2 = WorkflowStarted(workflow_name="wf2", inputs=inputs2)

        assert event1.inputs == {"key": "value1"}
        assert event2.inputs == {"key": "value2"}


class TestWorkflowCompleted:
    """Test suite for WorkflowCompleted event."""

    def test_creation_with_all_fields(self) -> None:
        """Test creating WorkflowCompleted with all fields."""
        timestamp = time.time()
        event = WorkflowCompleted(
            workflow_name="test_workflow",
            success=True,
            total_duration_ms=500,
            timestamp=timestamp,
        )
        assert event.workflow_name == "test_workflow"
        assert event.success is True
        assert event.total_duration_ms == 500
        assert event.timestamp == timestamp

    def test_creation_failed_workflow(self) -> None:
        """Test creating WorkflowCompleted for a failed workflow."""
        event = WorkflowCompleted(
            workflow_name="failed_workflow",
            success=False,
            total_duration_ms=250,
        )
        assert event.workflow_name == "failed_workflow"
        assert event.success is False
        assert event.total_duration_ms == 250

    def test_timestamp_defaults_to_current_time(self) -> None:
        """Test that timestamp defaults to current time if not provided."""
        before = time.time()
        event = WorkflowCompleted(
            workflow_name="test_workflow",
            success=True,
            total_duration_ms=1000,
        )
        after = time.time()

        assert before <= event.timestamp <= after

    def test_timestamp_is_float(self) -> None:
        """Test that timestamp is a float."""
        event = WorkflowCompleted(
            workflow_name="test_workflow",
            success=True,
            total_duration_ms=100,
        )
        assert isinstance(event.timestamp, float)

    def test_all_fields_accessible(self) -> None:
        """Test that all fields can be accessed."""
        event = WorkflowCompleted(
            workflow_name="my_workflow",
            success=True,
            total_duration_ms=750,
        )
        assert event.workflow_name == "my_workflow"
        assert event.success is True
        assert event.total_duration_ms == 750
        assert hasattr(event, "timestamp")

    def test_event_is_frozen(self) -> None:
        """Test that WorkflowCompleted is immutable (frozen)."""
        event = WorkflowCompleted(
            workflow_name="test_workflow",
            success=True,
            total_duration_ms=100,
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            event.success = False  # type: ignore[misc]

    def test_zero_duration(self) -> None:
        """Test WorkflowCompleted with zero duration."""
        event = WorkflowCompleted(
            workflow_name="instant_workflow",
            success=True,
            total_duration_ms=0,
        )
        assert event.total_duration_ms == 0


class TestProgressEventTypes:
    """Test suite for ProgressEvent type alias and event relationships."""

    def test_all_event_types_are_independent(self) -> None:
        """Test that different event types can coexist."""
        step_started = StepStarted(
            step_name="step1",
            step_type=StepType.PYTHON,
        )
        step_completed = StepCompleted(
            step_name="step1",
            step_type=StepType.PYTHON,
            success=True,
            duration_ms=50,
        )
        workflow_started = WorkflowStarted(
            workflow_name="workflow1",
            inputs={},
        )
        workflow_completed = WorkflowCompleted(
            workflow_name="workflow1",
            success=True,
            total_duration_ms=100,
        )

        # All events should be distinct
        assert step_started != step_completed
        assert workflow_started != workflow_completed

    def test_events_have_unique_timestamps(self) -> None:
        """Test that events created sequentially have different timestamps."""
        event1 = StepStarted(step_name="s1", step_type=StepType.PYTHON)
        time.sleep(0.001)  # Small delay to ensure different timestamps
        event2 = StepStarted(step_name="s2", step_type=StepType.PYTHON)

        # Timestamps should be different (though very close)
        assert event1.timestamp != event2.timestamp
        assert event2.timestamp > event1.timestamp
