"""Tests for rollback/compensation support in the serialization DSL executor.

This module tests the rollback mechanism added to WorkflowFileExecutor,
ensuring that rollback actions are executed in LIFO order when workflows fail
and that rollback failures are logged but don't halt execution.
"""

from __future__ import annotations

import pytest

from maverick.dsl.events import (
    RollbackCompleted,
    RollbackStarted,
    StepCompleted,
    StepStarted,
    ValidationCompleted,
    ValidationStarted,
    WorkflowCompleted,
    WorkflowStarted,
)
from maverick.dsl.results import RollbackError
from maverick.dsl.serialization.executor.executor import WorkflowFileExecutor
from maverick.dsl.serialization.registry import ComponentRegistry
from maverick.dsl.serialization.schema import (
    PythonStepRecord,
    WorkflowFile,
)
from maverick.dsl.types import StepType


# Test fixtures
class RollbackTracker:
    """Helper class to track rollback execution order."""

    def __init__(self) -> None:
        self.executed: list[str] = []
        self.should_fail: set[str] = set()

    def create_action(self, name: str):
        """Create an action that records its execution."""

        async def action(**kwargs) -> str:
            return f"{name}_result"

        return action

    def create_rollback(self, name: str):
        """Create a rollback action that records its execution."""

        async def rollback(**kwargs) -> None:
            if name in self.should_fail:
                raise RuntimeError(f"Rollback {name} failed")
            self.executed.append(name)

        return rollback


@pytest.fixture
def tracker():
    """Provide a fresh RollbackTracker instance."""
    return RollbackTracker()


@pytest.fixture
def registry_with_rollbacks(tracker: RollbackTracker):
    """Provide a ComponentRegistry with rollback-enabled actions."""
    registry = ComponentRegistry()

    # Register forward actions
    registry.actions.register("action_a", tracker.create_action("action_a"))
    registry.actions.register("action_b", tracker.create_action("action_b"))
    registry.actions.register("action_c", tracker.create_action("action_c"))

    # Register rollback actions
    registry.actions.register("rollback_a", tracker.create_rollback("rollback_a"))
    registry.actions.register("rollback_b", tracker.create_rollback("rollback_b"))
    registry.actions.register("rollback_c", tracker.create_rollback("rollback_c"))

    return registry


@pytest.mark.asyncio
async def test_successful_workflow_skips_rollbacks(
    tracker: RollbackTracker,
    registry_with_rollbacks: ComponentRegistry,
):
    """Test that successful workflows don't execute rollbacks."""
    workflow = WorkflowFile(
        version="1.0",
        name="test-success",
        description="Test successful execution",
        steps=[
            PythonStepRecord(
                name="step_a",
                type=StepType.PYTHON,
                action="action_a",
                rollback="rollback_a",
            ),
            PythonStepRecord(
                name="step_b",
                type=StepType.PYTHON,
                action="action_b",
                rollback="rollback_b",
            ),
        ],
    )

    executor = WorkflowFileExecutor(registry=registry_with_rollbacks)

    events = []
    async for event in executor.execute(workflow):
        events.append(event)

    # Verify workflow succeeded
    result = executor.get_result()
    assert result.success
    assert len(result.step_results) == 2

    # Verify no rollbacks were executed
    assert tracker.executed == []

    # Verify event sequence (no rollback events)
    event_types = [type(e).__name__ for e in events]
    assert "RollbackStarted" not in event_types
    assert "RollbackCompleted" not in event_types


@pytest.mark.asyncio
async def test_failed_workflow_executes_rollbacks_in_reverse(
    tracker: RollbackTracker,
    registry_with_rollbacks: ComponentRegistry,
):
    """Test that failed workflows execute rollbacks in LIFO order."""

    # Create a failing action
    async def failing_action(**kwargs) -> str:
        raise RuntimeError("Intentional failure")

    registry_with_rollbacks.actions.register("failing_action", failing_action)

    workflow = WorkflowFile(
        version="1.0",
        name="test-failure",
        description="Test rollback on failure",
        steps=[
            PythonStepRecord(
                name="step_a",
                type=StepType.PYTHON,
                action="action_a",
                rollback="rollback_a",
            ),
            PythonStepRecord(
                name="step_b",
                type=StepType.PYTHON,
                action="action_b",
                rollback="rollback_b",
            ),
            PythonStepRecord(
                name="step_c",
                type=StepType.PYTHON,
                action="action_c",
                rollback="rollback_c",
            ),
            PythonStepRecord(
                name="failing_step",
                type=StepType.PYTHON,
                action="failing_action",
            ),
        ],
    )

    executor = WorkflowFileExecutor(registry=registry_with_rollbacks)

    events = []
    async for event in executor.execute(workflow):
        events.append(event)

    # Verify workflow failed
    result = executor.get_result()
    assert not result.success
    assert len(result.step_results) == 4  # All steps attempted
    assert not result.step_results[-1].success  # Last step failed

    # Verify rollbacks executed in reverse order (LIFO)
    assert tracker.executed == ["rollback_c", "rollback_b", "rollback_a"]

    # Verify rollback events were emitted
    rollback_started = [e for e in events if isinstance(e, RollbackStarted)]
    rollback_completed = [e for e in events if isinstance(e, RollbackCompleted)]

    assert len(rollback_started) == 3
    assert len(rollback_completed) == 3

    # Verify event order matches LIFO
    assert rollback_started[0].step_name == "step_c"
    assert rollback_started[1].step_name == "step_b"
    assert rollback_started[2].step_name == "step_a"


@pytest.mark.asyncio
async def test_rollback_failure_continues_execution(
    tracker: RollbackTracker,
    registry_with_rollbacks: ComponentRegistry,
):
    """Test that rollback failures don't halt other rollbacks."""

    # Mark rollback_b to fail
    tracker.should_fail.add("rollback_b")

    # Create a failing action
    async def failing_action(**kwargs) -> str:
        raise RuntimeError("Intentional failure")

    registry_with_rollbacks.actions.register("failing_action", failing_action)

    workflow = WorkflowFile(
        version="1.0",
        name="test-rollback-failure",
        description="Test rollback failure handling",
        steps=[
            PythonStepRecord(
                name="step_a",
                type=StepType.PYTHON,
                action="action_a",
                rollback="rollback_a",
            ),
            PythonStepRecord(
                name="step_b",
                type=StepType.PYTHON,
                action="action_b",
                rollback="rollback_b",
            ),
            PythonStepRecord(
                name="step_c",
                type=StepType.PYTHON,
                action="action_c",
                rollback="rollback_c",
            ),
            PythonStepRecord(
                name="failing_step",
                type=StepType.PYTHON,
                action="failing_action",
            ),
        ],
    )

    executor = WorkflowFileExecutor(registry=registry_with_rollbacks)

    events = []
    async for event in executor.execute(workflow):
        events.append(event)

    # Verify workflow failed
    result = executor.get_result()
    assert not result.success

    # Verify rollback_a and rollback_c succeeded, rollback_b failed
    assert "rollback_c" in tracker.executed
    assert "rollback_b" not in tracker.executed  # Failed
    assert "rollback_a" in tracker.executed

    # Verify rollback error was captured
    assert len(result.rollback_errors) == 1
    assert result.rollback_errors[0].step_name == "step_b"
    assert "Rollback rollback_b failed" in result.rollback_errors[0].error

    # Verify RollbackError event was emitted
    rollback_errors = [e for e in events if isinstance(e, RollbackError)]
    assert len(rollback_errors) == 1
    assert rollback_errors[0].step_name == "step_b"

    # Verify RollbackCompleted events show failure status
    rollback_completed = [e for e in events if isinstance(e, RollbackCompleted)]
    step_b_completion = [e for e in rollback_completed if e.step_name == "step_b"][0]
    assert not step_b_completion.success
    assert step_b_completion.error is not None


@pytest.mark.asyncio
async def test_missing_rollback_action_logs_warning(
    tracker: RollbackTracker,
    registry_with_rollbacks: ComponentRegistry,
):
    """Test that missing rollback actions are logged but don't fail."""

    # Create a failing action
    async def failing_action(**kwargs) -> str:
        raise RuntimeError("Intentional failure")

    registry_with_rollbacks.actions.register("failing_action", failing_action)

    workflow = WorkflowFile(
        version="1.0",
        name="test-missing-rollback",
        description="Test missing rollback action",
        steps=[
            PythonStepRecord(
                name="step_a",
                type=StepType.PYTHON,
                action="action_a",
                rollback="nonexistent_rollback",  # This doesn't exist
            ),
            PythonStepRecord(
                name="failing_step",
                type=StepType.PYTHON,
                action="failing_action",
            ),
        ],
    )

    executor = WorkflowFileExecutor(registry=registry_with_rollbacks)

    events = []
    async for event in executor.execute(workflow):
        events.append(event)

    # Verify workflow failed
    result = executor.get_result()
    assert not result.success

    # Verify no rollbacks were executed (since rollback action doesn't exist)
    assert tracker.executed == []

    # Verify no rollback events were emitted
    rollback_events = [
        e for e in events if isinstance(e, (RollbackStarted, RollbackCompleted))
    ]
    assert len(rollback_events) == 0


@pytest.mark.asyncio
async def test_steps_without_rollbacks_skipped(
    tracker: RollbackTracker,
    registry_with_rollbacks: ComponentRegistry,
):
    """Test that steps without rollbacks are skipped during rollback."""

    # Create a failing action
    async def failing_action(**kwargs) -> str:
        raise RuntimeError("Intentional failure")

    registry_with_rollbacks.actions.register("failing_action", failing_action)

    workflow = WorkflowFile(
        version="1.0",
        name="test-partial-rollbacks",
        description="Test partial rollback registration",
        steps=[
            PythonStepRecord(
                name="step_a",
                type=StepType.PYTHON,
                action="action_a",
                rollback="rollback_a",
            ),
            PythonStepRecord(
                name="step_b",
                type=StepType.PYTHON,
                action="action_b",
                # No rollback specified
            ),
            PythonStepRecord(
                name="step_c",
                type=StepType.PYTHON,
                action="action_c",
                rollback="rollback_c",
            ),
            PythonStepRecord(
                name="failing_step",
                type=StepType.PYTHON,
                action="failing_action",
            ),
        ],
    )

    executor = WorkflowFileExecutor(registry=registry_with_rollbacks)

    events = []
    async for event in executor.execute(workflow):
        events.append(event)

    # Verify workflow failed
    result = executor.get_result()
    assert not result.success

    # Verify only steps with rollbacks were rolled back
    assert tracker.executed == ["rollback_c", "rollback_a"]

    # Verify only 2 rollback events (for step_a and step_c)
    rollback_started = [e for e in events if isinstance(e, RollbackStarted)]
    assert len(rollback_started) == 2
    assert rollback_started[0].step_name == "step_c"
    assert rollback_started[1].step_name == "step_a"


@pytest.mark.asyncio
async def test_event_sequence_with_rollbacks(
    tracker: RollbackTracker,
    registry_with_rollbacks: ComponentRegistry,
):
    """Test the complete event sequence for a failed workflow with rollbacks."""

    # Create a failing action
    async def failing_action(**kwargs) -> str:
        raise RuntimeError("Intentional failure")

    registry_with_rollbacks.actions.register("failing_action", failing_action)

    workflow = WorkflowFile(
        version="1.0",
        name="test-event-sequence",
        description="Test event sequence",
        steps=[
            PythonStepRecord(
                name="step_a",
                type=StepType.PYTHON,
                action="action_a",
                rollback="rollback_a",
            ),
            PythonStepRecord(
                name="failing_step",
                type=StepType.PYTHON,
                action="failing_action",
            ),
        ],
    )

    executor = WorkflowFileExecutor(registry=registry_with_rollbacks)

    events = []
    async for event in executor.execute(workflow):
        events.append(event)

    # Verify event sequence:
    # 0. ValidationStarted
    # 1. ValidationCompleted
    # 2. PreflightStarted
    # 3. PreflightCompleted
    # 4. WorkflowStarted
    # 5. StepStarted (step_a)
    # 6. StepCompleted (step_a, success)
    # 7. StepStarted (failing_step)
    # 8. StepCompleted (failing_step, failure)
    # 9. RollbackStarted (step_a)
    # 10. RollbackCompleted (step_a)
    # 11. WorkflowCompleted (failure)
    from maverick.dsl.events import PreflightCompleted, PreflightStarted

    assert isinstance(events[0], ValidationStarted)
    assert isinstance(events[1], ValidationCompleted)
    assert isinstance(events[2], PreflightStarted)
    assert isinstance(events[3], PreflightCompleted)
    assert isinstance(events[4], WorkflowStarted)
    assert isinstance(events[5], StepStarted)
    assert events[5].step_name == "step_a"
    assert isinstance(events[6], StepCompleted)
    assert events[6].step_name == "step_a"
    assert events[6].success

    assert isinstance(events[7], StepStarted)
    assert events[7].step_name == "failing_step"
    assert isinstance(events[8], StepCompleted)
    assert events[8].step_name == "failing_step"
    assert not events[8].success

    assert isinstance(events[9], RollbackStarted)
    assert events[9].step_name == "step_a"
    assert isinstance(events[10], RollbackCompleted)
    assert events[10].step_name == "step_a"
    assert events[10].success

    assert isinstance(events[11], WorkflowCompleted)
    assert not events[11].success
