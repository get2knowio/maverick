"""Tests for WorkflowFileExecutor.

Tests the execution of WorkflowFile instances using the WorkflowFileExecutor class.
"""

from __future__ import annotations

import pytest

from maverick.dsl.events import (
    StepCompleted,
    StepStarted,
    WorkflowCompleted,
    WorkflowStarted,
)
from maverick.dsl.serialization import (
    ComponentRegistry,
    PythonStepRecord,
    WorkflowFile,
    WorkflowFileExecutor,
)
from maverick.dsl.serialization.errors import ReferenceResolutionError
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

    # Verify events
    assert len(events) == 4
    assert isinstance(events[0], WorkflowStarted)
    assert events[0].workflow_name == "test-workflow"

    assert isinstance(events[1], StepStarted)
    assert events[1].step_name == "add_numbers"
    assert events[1].step_type == StepType.PYTHON

    assert isinstance(events[2], StepCompleted)
    assert events[2].step_name == "add_numbers"
    assert events[2].success is True

    assert isinstance(events[3], WorkflowCompleted)
    assert events[3].success is True

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

    # Should have WorkflowStarted, StepStarted (executed_step), StepCompleted, WorkflowCompleted
    # The skipped_step should not generate events
    assert len(events) == 4

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

    # Should complete with failure
    result = executor.get_result()
    assert result.success is False
    assert len(result.step_results) == 1
    assert result.step_results[0].success is False
    assert "nonexistent_action" in result.step_results[0].error


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
