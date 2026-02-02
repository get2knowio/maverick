"""Tests for WorkflowFileExecutor.

Tests the execution of WorkflowFile instances using the WorkflowFileExecutor class.
"""

from __future__ import annotations

import pytest

from maverick.dsl.events import (
    StepCompleted,
    StepStarted,
    ValidationCompleted,
    ValidationFailed,
    ValidationStarted,
    WorkflowCompleted,
    WorkflowStarted,
)
from maverick.dsl.serialization import (
    ComponentRegistry,
    PythonStepRecord,
    WorkflowFile,
    WorkflowFileExecutor,
)
from maverick.dsl.types import StepType


@pytest.fixture
def registry():
    """Create a component registry with test actions."""
    reg = ComponentRegistry()

    # Register a simple action
    @reg.actions.register("test_action")
    def test_action(x: int, y: int) -> int:
        return x + y

    # Register an async action
    @reg.actions.register("async_action")
    async def async_action(message: str) -> str:
        return f"Processed: {message}"

    return reg


@pytest.mark.asyncio
async def test_executor_simple_workflow(registry):
    """Test executing a simple workflow with one Python step."""
    # Create a simple workflow
    workflow = WorkflowFile(
        version="1.0",
        name="test-workflow",
        description="Test workflow",
        steps=[
            PythonStepRecord(
                name="add_numbers",
                type=StepType.PYTHON,
                action="test_action",
                kwargs={"x": 5, "y": 3},
            )
        ],
    )

    # Execute workflow
    executor = WorkflowFileExecutor(registry=registry)
    events = []

    async for event in executor.execute(workflow):
        events.append(event)

    # Verify events (Validation, Preflight, then workflow events)
    from maverick.dsl.events import PreflightCompleted, PreflightStarted

    assert len(events) == 8
    assert isinstance(events[0], ValidationStarted)
    assert isinstance(events[1], ValidationCompleted)
    assert isinstance(events[2], PreflightStarted)
    assert isinstance(events[3], PreflightCompleted)
    assert isinstance(events[4], WorkflowStarted)
    assert events[4].workflow_name == "test-workflow"

    assert isinstance(events[5], StepStarted)
    assert events[5].step_name == "add_numbers"
    assert events[5].step_type == StepType.PYTHON

    assert isinstance(events[6], StepCompleted)
    assert events[6].step_name == "add_numbers"
    assert events[6].success is True

    assert isinstance(events[7], WorkflowCompleted)
    assert events[7].success is True

    # Verify result
    result = executor.get_result()
    assert result.success is True
    assert result.final_output == 8
    assert len(result.step_results) == 1
    assert result.step_results[0].output == 8


@pytest.mark.asyncio
async def test_executor_async_action(registry):
    """Test executing an async action."""
    workflow = WorkflowFile(
        version="1.0",
        name="async-workflow",
        steps=[
            PythonStepRecord(
                name="process_message",
                type=StepType.PYTHON,
                action="async_action",
                kwargs={"message": "hello"},
            )
        ],
    )

    executor = WorkflowFileExecutor(registry=registry)
    async for _ in executor.execute(workflow):
        pass

    result = executor.get_result()
    assert result.success is True
    assert result.final_output == "Processed: hello"


@pytest.mark.asyncio
async def test_executor_expression_resolution(registry):
    """Test expression resolution in step inputs."""
    workflow = WorkflowFile(
        version="1.0",
        name="expr-workflow",
        steps=[
            PythonStepRecord(
                name="use_input",
                type=StepType.PYTHON,
                action="async_action",
                kwargs={"message": "${{ inputs.text }}"},
            )
        ],
    )

    executor = WorkflowFileExecutor(registry=registry)
    async for _ in executor.execute(workflow, inputs={"text": "world"}):
        pass

    result = executor.get_result()
    assert result.success is True
    assert result.final_output == "Processed: world"


@pytest.mark.asyncio
async def test_executor_conditional_skip(registry):
    """Test conditional step execution (skip when false)."""
    workflow = WorkflowFile(
        version="1.0",
        name="conditional-workflow",
        steps=[
            PythonStepRecord(
                name="skipped_step",
                type=StepType.PYTHON,
                action="test_action",
                kwargs={"x": 1, "y": 2},
                when="${{ inputs.run_step }}",
            ),
            PythonStepRecord(
                name="executed_step",
                type=StepType.PYTHON,
                action="test_action",
                kwargs={"x": 10, "y": 20},
            ),
        ],
    )

    executor = WorkflowFileExecutor(registry=registry)
    events = []

    async for event in executor.execute(workflow, inputs={"run_step": False}):
        events.append(event)

    # Should have ValidationStarted, ValidationCompleted, PreflightStarted,
    # PreflightCompleted, WorkflowStarted, StepStarted (executed_step),
    # StepCompleted, WorkflowCompleted.
    # The skipped_step should not generate events
    assert len(events) == 8

    step_names = [e.step_name for e in events if isinstance(e, StepStarted)]
    assert step_names == ["executed_step"]

    result = executor.get_result()
    assert result.success is True
    assert result.final_output == 30


@pytest.mark.asyncio
async def test_executor_step_output_reference(registry):
    """Test referencing previous step output in expressions."""
    workflow = WorkflowFile(
        version="1.0",
        name="chained-workflow",
        steps=[
            PythonStepRecord(
                name="first_step",
                type=StepType.PYTHON,
                action="test_action",
                kwargs={"x": 5, "y": 10},
            ),
            PythonStepRecord(
                name="second_step",
                type=StepType.PYTHON,
                action="async_action",
                kwargs={"message": "Result was ${{ steps.first_step.output }}"},
            ),
        ],
    )

    executor = WorkflowFileExecutor(registry=registry)
    async for _ in executor.execute(workflow):
        pass

    result = executor.get_result()
    assert result.success is True
    assert result.final_output == "Processed: Result was 15"


@pytest.mark.asyncio
async def test_executor_action_not_found():
    """Test error handling when action is not registered."""
    registry = ComponentRegistry()  # Empty registry

    workflow = WorkflowFile(
        version="1.0",
        name="missing-action-workflow",
        steps=[
            PythonStepRecord(
                name="bad_step",
                type=StepType.PYTHON,
                action="nonexistent_action",
                kwargs={},
            )
        ],
    )

    executor = WorkflowFileExecutor(registry=registry)
    events = []

    async for event in executor.execute(workflow):
        events.append(event)

    # Should fail during validation (action not found is caught early)
    assert len(events) == 3  # ValidationStarted, ValidationFailed, WorkflowCompleted
    assert isinstance(events[0], ValidationStarted)
    assert isinstance(events[1], ValidationFailed)
    assert isinstance(events[2], WorkflowCompleted)
    # Validation should have error about missing action
    assert "nonexistent_action" in events[1].errors[0]

    result = executor.get_result()
    assert result.success is False
    # No steps executed because validation failed
    assert len(result.step_results) == 0


@pytest.mark.asyncio
async def test_executor_step_failure_stops_workflow(registry):
    """Test that workflow stops on first step failure."""

    @registry.actions.register("failing_action")
    def failing_action() -> None:
        raise ValueError("Step failed!")

    workflow = WorkflowFile(
        version="1.0",
        name="failing-workflow",
        steps=[
            PythonStepRecord(
                name="fail_step",
                type=StepType.PYTHON,
                action="failing_action",
                kwargs={},
            ),
            PythonStepRecord(
                name="never_executed",
                type=StepType.PYTHON,
                action="test_action",
                kwargs={"x": 1, "y": 2},
            ),
        ],
    )

    executor = WorkflowFileExecutor(registry=registry)
    events = []

    async for event in executor.execute(workflow):
        events.append(event)

    # Should only execute the first step
    step_started = [e for e in events if isinstance(e, StepStarted)]
    assert len(step_started) == 1
    assert step_started[0].step_name == "fail_step"

    result = executor.get_result()
    assert result.success is False
    assert len(result.step_results) == 1


@pytest.mark.asyncio
async def test_executor_get_result_before_execution():
    """Test that get_result() raises error if called before execution."""
    executor = WorkflowFileExecutor()

    with pytest.raises(RuntimeError, match="has not been executed"):
        executor.get_result()


@pytest.mark.asyncio
async def test_executor_cancellation(registry):
    """Test workflow cancellation."""
    workflow = WorkflowFile(
        version="1.0",
        name="cancel-workflow",
        steps=[
            PythonStepRecord(
                name="step1",
                type=StepType.PYTHON,
                action="test_action",
                kwargs={"x": 1, "y": 1},
            ),
            PythonStepRecord(
                name="step2",
                type=StepType.PYTHON,
                action="test_action",
                kwargs={"x": 2, "y": 2},
            ),
        ],
    )

    executor = WorkflowFileExecutor(registry=registry)

    # Cancel immediately
    executor.cancel()

    events = []
    async for event in executor.execute(workflow):
        events.append(event)

    # Should only get WorkflowStarted and WorkflowCompleted (no steps executed)
    result = executor.get_result()
    assert result.success is False
    assert len(result.step_results) == 0


@pytest.mark.asyncio
async def test_executor_event_timestamps(registry):
    """Test that all events have valid timestamps."""
    workflow = WorkflowFile(
        version="1.0",
        name="timestamp-test",
        steps=[
            PythonStepRecord(
                name="step1",
                type=StepType.PYTHON,
                action="test_action",
                kwargs={"x": 1, "y": 2},
            )
        ],
    )

    executor = WorkflowFileExecutor(registry=registry)
    events = []

    async for event in executor.execute(workflow):
        events.append(event)

    # All events should have timestamps
    for event in events:
        assert hasattr(event, "timestamp")
        assert isinstance(event.timestamp, float)
        assert event.timestamp > 0

    # Timestamps should be sequential
    for i in range(len(events) - 1):
        assert events[i].timestamp <= events[i + 1].timestamp


@pytest.mark.asyncio
async def test_executor_multiple_steps_event_order(registry):
    """Test that events are emitted in correct order for multi-step workflows."""
    workflow = WorkflowFile(
        version="1.0",
        name="event-order-test",
        steps=[
            PythonStepRecord(
                name="step1",
                type=StepType.PYTHON,
                action="test_action",
                kwargs={"x": 1, "y": 1},
            ),
            PythonStepRecord(
                name="step2",
                type=StepType.PYTHON,
                action="test_action",
                kwargs={"x": 2, "y": 2},
            ),
        ],
    )

    executor = WorkflowFileExecutor(registry=registry)
    events = []

    async for event in executor.execute(workflow):
        events.append(event)

    # Expected order:
    # 0. ValidationStarted
    # 1. ValidationCompleted
    # 2. PreflightStarted
    # 3. PreflightCompleted
    # 4. WorkflowStarted
    # 5. StepStarted(step1)
    # 6. StepCompleted(step1)
    # 7. StepStarted(step2)
    # 8. StepCompleted(step2)
    # 9. WorkflowCompleted
    from maverick.dsl.events import PreflightCompleted, PreflightStarted

    assert isinstance(events[0], ValidationStarted)
    assert isinstance(events[1], ValidationCompleted)
    assert isinstance(events[2], PreflightStarted)
    assert isinstance(events[3], PreflightCompleted)
    assert isinstance(events[4], WorkflowStarted)
    assert isinstance(events[5], StepStarted)
    assert events[5].step_name == "step1"
    assert isinstance(events[6], StepCompleted)
    assert events[6].step_name == "step1"
    assert isinstance(events[7], StepStarted)
    assert events[7].step_name == "step2"
    assert isinstance(events[8], StepCompleted)
    assert events[8].step_name == "step2"
    assert isinstance(events[9], WorkflowCompleted)
