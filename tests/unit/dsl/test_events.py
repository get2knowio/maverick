"""Unit tests for DSL progress events.

Tests for StepStarted, StepCompleted, WorkflowStarted, WorkflowCompleted,
LoopIterationStarted, and LoopIterationCompleted events.
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
from maverick.dsl.events import (
    AgentStreamChunk,
    LoopIterationCompleted,
    LoopIterationStarted,
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

    def test_failed_step_with_error(self) -> None:
        """Test that failed steps carry error message."""
        event = StepCompleted(
            step_name="failed_agent",
            step_type=StepType.AGENT,
            success=False,
            duration_ms=500,
            error="API error",
        )
        assert event.success is False
        assert event.error == "API error"


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


class TestLoopIterationStarted:
    """Test suite for LoopIterationStarted event."""

    def test_creation_with_all_fields(self) -> None:
        """Test creating LoopIterationStarted with all fields."""
        timestamp = time.time()
        event = LoopIterationStarted(
            step_name="implement_by_phase",
            iteration_index=0,
            total_iterations=3,
            item_label="Phase 1: Setup",
            timestamp=timestamp,
        )
        assert event.step_name == "implement_by_phase"
        assert event.iteration_index == 0
        assert event.total_iterations == 3
        assert event.item_label == "Phase 1: Setup"
        assert event.parent_step_name is None
        assert event.timestamp == timestamp

    def test_creation_with_nested_parent(self) -> None:
        """Test creating LoopIterationStarted with parent_step_name for nested loops."""
        event = LoopIterationStarted(
            step_name="inner_loop",
            iteration_index=2,
            total_iterations=5,
            item_label="Sub-item 3",
            parent_step_name="outer_loop",
        )
        assert event.step_name == "inner_loop"
        assert event.iteration_index == 2
        assert event.total_iterations == 5
        assert event.item_label == "Sub-item 3"
        assert event.parent_step_name == "outer_loop"

    def test_timestamp_defaults_to_current_time(self) -> None:
        """Test that timestamp defaults to current time if not provided."""
        before = time.time()
        event = LoopIterationStarted(
            step_name="loop_step",
            iteration_index=1,
            total_iterations=10,
            item_label="Item 2",
        )
        after = time.time()

        # Timestamp should be between before and after
        assert before <= event.timestamp <= after

    def test_timestamp_is_float(self) -> None:
        """Test that timestamp is a float."""
        event = LoopIterationStarted(
            step_name="loop_step",
            iteration_index=0,
            total_iterations=1,
            item_label="Only item",
        )
        assert isinstance(event.timestamp, float)

    def test_timestamp_is_positive(self) -> None:
        """Test that default timestamp is positive (greater than zero)."""
        event = LoopIterationStarted(
            step_name="loop_step",
            iteration_index=0,
            total_iterations=1,
            item_label="Test item",
        )
        assert event.timestamp > 0

    def test_all_fields_accessible(self) -> None:
        """Test that all fields can be accessed."""
        event = LoopIterationStarted(
            step_name="my_loop",
            iteration_index=5,
            total_iterations=10,
            item_label="Phase 6: Testing",
            parent_step_name="parent_loop",
        )
        assert event.step_name == "my_loop"
        assert event.iteration_index == 5
        assert event.total_iterations == 10
        assert event.item_label == "Phase 6: Testing"
        assert event.parent_step_name == "parent_loop"
        assert hasattr(event, "timestamp")

    def test_event_is_frozen(self) -> None:
        """Test that LoopIterationStarted is immutable (frozen)."""
        event = LoopIterationStarted(
            step_name="loop_step",
            iteration_index=0,
            total_iterations=3,
            item_label="First",
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            event.step_name = "modified"  # type: ignore[misc]

    def test_zero_index_first_iteration(self) -> None:
        """Test that iteration_index is 0-based for first iteration."""
        event = LoopIterationStarted(
            step_name="loop_step",
            iteration_index=0,
            total_iterations=5,
            item_label="First item",
        )
        assert event.iteration_index == 0

    def test_last_iteration_index(self) -> None:
        """Test iteration_index for last iteration (total - 1)."""
        total = 10
        event = LoopIterationStarted(
            step_name="loop_step",
            iteration_index=total - 1,
            total_iterations=total,
            item_label="Last item",
        )
        assert event.iteration_index == total - 1
        assert event.total_iterations == total


class TestLoopIterationCompleted:
    """Test suite for LoopIterationCompleted event."""

    def test_creation_with_success(self) -> None:
        """Test creating LoopIterationCompleted with success=True."""
        timestamp = time.time()
        event = LoopIterationCompleted(
            step_name="implement_by_phase",
            iteration_index=0,
            success=True,
            duration_ms=1500,
            timestamp=timestamp,
        )
        assert event.step_name == "implement_by_phase"
        assert event.iteration_index == 0
        assert event.success is True
        assert event.duration_ms == 1500
        assert event.error is None
        assert event.timestamp == timestamp

    def test_creation_with_error(self) -> None:
        """Test creating LoopIterationCompleted with error."""
        event = LoopIterationCompleted(
            step_name="implement_by_phase",
            iteration_index=1,
            success=False,
            duration_ms=5000,
            error="Validation failed",
        )
        assert event.step_name == "implement_by_phase"
        assert event.iteration_index == 1
        assert event.success is False
        assert event.duration_ms == 5000
        assert event.error == "Validation failed"

    def test_timestamp_defaults_to_current_time(self) -> None:
        """Test that timestamp defaults to current time if not provided."""
        before = time.time()
        event = LoopIterationCompleted(
            step_name="loop_step",
            iteration_index=2,
            success=True,
            duration_ms=100,
        )
        after = time.time()

        # Timestamp should be between before and after
        assert before <= event.timestamp <= after

    def test_timestamp_is_float(self) -> None:
        """Test that timestamp is a float."""
        event = LoopIterationCompleted(
            step_name="loop_step",
            iteration_index=0,
            success=True,
            duration_ms=50,
        )
        assert isinstance(event.timestamp, float)

    def test_timestamp_is_positive(self) -> None:
        """Test that default timestamp is positive (greater than zero)."""
        event = LoopIterationCompleted(
            step_name="loop_step",
            iteration_index=0,
            success=True,
            duration_ms=100,
        )
        assert event.timestamp > 0

    def test_all_fields_accessible(self) -> None:
        """Test that all fields can be accessed."""
        event = LoopIterationCompleted(
            step_name="my_loop",
            iteration_index=3,
            success=False,
            duration_ms=2500,
            error="Test error",
        )
        assert event.step_name == "my_loop"
        assert event.iteration_index == 3
        assert event.success is False
        assert event.duration_ms == 2500
        assert event.error == "Test error"
        assert hasattr(event, "timestamp")

    def test_event_is_frozen(self) -> None:
        """Test that LoopIterationCompleted is immutable (frozen)."""
        event = LoopIterationCompleted(
            step_name="loop_step",
            iteration_index=0,
            success=True,
            duration_ms=100,
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            event.success = False  # type: ignore[misc]

    def test_zero_duration(self) -> None:
        """Test LoopIterationCompleted with zero duration."""
        event = LoopIterationCompleted(
            step_name="instant_loop",
            iteration_index=0,
            success=True,
            duration_ms=0,
        )
        assert event.duration_ms == 0

    def test_success_without_error(self) -> None:
        """Test that successful iteration has no error."""
        event = LoopIterationCompleted(
            step_name="loop_step",
            iteration_index=0,
            success=True,
            duration_ms=100,
        )
        assert event.success is True
        assert event.error is None

    def test_failure_with_error_message(self) -> None:
        """Test that failed iteration includes error message."""
        event = LoopIterationCompleted(
            step_name="loop_step",
            iteration_index=5,
            success=False,
            duration_ms=3000,
            error="Task failed: syntax error in generated code",
        )
        assert event.success is False
        assert event.error == "Task failed: syntax error in generated code"


class TestLoopEventInteraction:
    """Test suite for loop event interactions."""

    def test_started_and_completed_can_coexist(self) -> None:
        """Test that LoopIterationStarted and LoopIterationCompleted coexist."""
        started = LoopIterationStarted(
            step_name="loop",
            iteration_index=0,
            total_iterations=3,
            item_label="Phase 1",
        )
        completed = LoopIterationCompleted(
            step_name="loop",
            iteration_index=0,
            success=True,
            duration_ms=1000,
        )

        assert started != completed
        assert started.step_name == completed.step_name
        assert started.iteration_index == completed.iteration_index

    def test_completed_timestamp_after_started(self) -> None:
        """Test that completed event timestamp is after started event."""
        started = LoopIterationStarted(
            step_name="loop",
            iteration_index=0,
            total_iterations=1,
            item_label="Test",
        )
        time.sleep(0.001)  # Small delay
        completed = LoopIterationCompleted(
            step_name="loop",
            iteration_index=0,
            success=True,
            duration_ms=1,
        )

        assert completed.timestamp > started.timestamp


class TestAgentStreamChunk:
    """Test suite for AgentStreamChunk event."""

    def test_creation_with_all_fields(self) -> None:
        """Test creating AgentStreamChunk with all fields."""
        timestamp = time.time()
        event = AgentStreamChunk(
            step_name="implement_task",
            agent_name="ImplementerAgent",
            text="Processing file...",
            chunk_type="output",
            timestamp=timestamp,
        )
        assert event.step_name == "implement_task"
        assert event.agent_name == "ImplementerAgent"
        assert event.text == "Processing file..."
        assert event.chunk_type == "output"
        assert event.timestamp == timestamp

    def test_chunk_type_output(self) -> None:
        """Test AgentStreamChunk with chunk_type='output'."""
        event = AgentStreamChunk(
            step_name="review_code",
            agent_name="CodeReviewerAgent",
            text="Found 3 issues in module.py",
            chunk_type="output",
        )
        assert event.chunk_type == "output"
        assert event.text == "Found 3 issues in module.py"

    def test_chunk_type_thinking(self) -> None:
        """Test AgentStreamChunk with chunk_type='thinking'."""
        event = AgentStreamChunk(
            step_name="analyze_pr",
            agent_name="AnalysisAgent",
            text="Considering the implications of this change...",
            chunk_type="thinking",
        )
        assert event.chunk_type == "thinking"
        assert event.text == "Considering the implications of this change..."

    def test_chunk_type_error(self) -> None:
        """Test AgentStreamChunk with chunk_type='error'."""
        event = AgentStreamChunk(
            step_name="generate_code",
            agent_name="GeneratorAgent",
            text="API rate limit exceeded",
            chunk_type="error",
        )
        assert event.chunk_type == "error"
        assert event.text == "API rate limit exceeded"

    def test_timestamp_defaults_to_current_time(self) -> None:
        """Test that timestamp defaults to current time if not provided."""
        before = time.time()
        event = AgentStreamChunk(
            step_name="test_step",
            agent_name="TestAgent",
            text="Test output",
            chunk_type="output",
        )
        after = time.time()

        # Timestamp should be between before and after
        assert before <= event.timestamp <= after

    def test_timestamp_is_float(self) -> None:
        """Test that timestamp is a float."""
        event = AgentStreamChunk(
            step_name="test_step",
            agent_name="TestAgent",
            text="Output",
            chunk_type="output",
        )
        assert isinstance(event.timestamp, float)

    def test_timestamp_is_positive(self) -> None:
        """Test that default timestamp is positive (greater than zero)."""
        event = AgentStreamChunk(
            step_name="test_step",
            agent_name="TestAgent",
            text="Output",
            chunk_type="output",
        )
        assert event.timestamp > 0

    def test_all_fields_accessible(self) -> None:
        """Test that all fields can be accessed."""
        event = AgentStreamChunk(
            step_name="my_step",
            agent_name="MyAgent",
            text="Some text",
            chunk_type="thinking",
        )
        assert event.step_name == "my_step"
        assert event.agent_name == "MyAgent"
        assert event.text == "Some text"
        assert event.chunk_type == "thinking"
        assert hasattr(event, "timestamp")

    def test_event_is_frozen(self) -> None:
        """Test that AgentStreamChunk is immutable (frozen)."""
        event = AgentStreamChunk(
            step_name="test_step",
            agent_name="TestAgent",
            text="Output text",
            chunk_type="output",
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            event.text = "modified"  # type: ignore[misc]

    def test_empty_text(self) -> None:
        """Test AgentStreamChunk with empty text."""
        event = AgentStreamChunk(
            step_name="empty_output_step",
            agent_name="StreamAgent",
            text="",
            chunk_type="output",
        )
        assert event.text == ""

    def test_long_text(self) -> None:
        """Test AgentStreamChunk with long text content."""
        # Simulate a large streaming chunk (e.g., 10KB of text)
        long_text = "x" * 10000
        event = AgentStreamChunk(
            step_name="large_output_step",
            agent_name="VerboseAgent",
            text=long_text,
            chunk_type="output",
        )
        assert event.text == long_text
        assert len(event.text) == 10000

    def test_multiline_text(self) -> None:
        """Test AgentStreamChunk with multiline text content."""
        multiline_text = """Line 1: Starting process
Line 2: Processing data
Line 3: Completed successfully"""
        event = AgentStreamChunk(
            step_name="multiline_step",
            agent_name="ProcessAgent",
            text=multiline_text,
            chunk_type="output",
        )
        assert event.text == multiline_text
        assert "\n" in event.text

    def test_special_characters_in_text(self) -> None:
        """Test AgentStreamChunk with special characters."""
        special_text = "Error: path='/tmp/test' && rm -rf /"
        event = AgentStreamChunk(
            step_name="special_step",
            agent_name="EscapeAgent",
            text=special_text,
            chunk_type="error",
        )
        assert event.text == special_text

    def test_unicode_text(self) -> None:
        """Test AgentStreamChunk with unicode characters."""
        unicode_text = "Processing: \u2714 Success \u274c Failure \U0001f680 Deploy"
        event = AgentStreamChunk(
            step_name="unicode_step",
            agent_name="InternationalAgent",
            text=unicode_text,
            chunk_type="output",
        )
        assert event.text == unicode_text

    def test_different_agent_names(self) -> None:
        """Test AgentStreamChunk with various agent names."""
        agent_names = [
            "ImplementerAgent",
            "CodeReviewerAgent",
            "IssueFixer",
            "ValidationAgent",
            "custom_agent",
        ]
        for agent_name in agent_names:
            event = AgentStreamChunk(
                step_name="test_step",
                agent_name=agent_name,
                text="Output",
                chunk_type="output",
            )
            assert event.agent_name == agent_name


class TestAgentStreamChunkInteraction:
    """Test suite for AgentStreamChunk interactions with other events."""

    def test_multiple_chunks_sequential(self) -> None:
        """Test creating multiple sequential stream chunks."""
        chunks = []
        for i in range(5):
            chunk = AgentStreamChunk(
                step_name="streaming_step",
                agent_name="StreamAgent",
                text=f"Chunk {i}",
                chunk_type="output",
            )
            chunks.append(chunk)
            time.sleep(0.001)  # Small delay between chunks

        # Verify all chunks are distinct
        for i, chunk in enumerate(chunks):
            assert chunk.text == f"Chunk {i}"

        # Verify timestamps are increasing
        for i in range(1, len(chunks)):
            assert chunks[i].timestamp > chunks[i - 1].timestamp

    def test_stream_chunk_with_step_events(self) -> None:
        """Test that AgentStreamChunk can coexist with StepStarted/StepCompleted."""
        step_started = StepStarted(
            step_name="agent_step",
            step_type=StepType.AGENT,
        )

        stream_chunk = AgentStreamChunk(
            step_name="agent_step",
            agent_name="TestAgent",
            text="Processing...",
            chunk_type="output",
        )

        step_completed = StepCompleted(
            step_name="agent_step",
            step_type=StepType.AGENT,
            success=True,
            duration_ms=100,
        )

        # All events should be distinct
        assert step_started != stream_chunk
        assert stream_chunk != step_completed
        assert step_started != step_completed

        # Step names should match
        assert (
            step_started.step_name == stream_chunk.step_name == step_completed.step_name
        )

    def test_mixed_chunk_types_sequence(self) -> None:
        """Test a realistic sequence of different chunk types."""
        events = [
            AgentStreamChunk(
                step_name="complex_step",
                agent_name="ThinkingAgent",
                text="Analyzing requirements...",
                chunk_type="thinking",
            ),
            AgentStreamChunk(
                step_name="complex_step",
                agent_name="ThinkingAgent",
                text="def process_data():",
                chunk_type="output",
            ),
            AgentStreamChunk(
                step_name="complex_step",
                agent_name="ThinkingAgent",
                text="    return transformed",
                chunk_type="output",
            ),
        ]

        assert events[0].chunk_type == "thinking"
        assert events[1].chunk_type == "output"
        assert events[2].chunk_type == "output"

        # All share the same step and agent
        for event in events:
            assert event.step_name == "complex_step"
            assert event.agent_name == "ThinkingAgent"
