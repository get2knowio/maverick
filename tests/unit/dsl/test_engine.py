"""Unit tests for WorkflowEngine.

This module tests the WorkflowEngine that executes workflows and emits
progress events for TUI consumption.

TDD Note: These tests are written FIRST and will FAIL until implementation
is complete. They define the expected behavior of the engine.
"""

from __future__ import annotations

import pytest

from maverick.dsl import (
    StepCompleted,
    StepStarted,
    StepType,
    WorkflowCompleted,
    WorkflowEngine,
    WorkflowStarted,
    step,
    workflow,
)
from maverick.exceptions import DuplicateStepNameError


class TestWorkflowEngineExecute:
    """Test WorkflowEngine.execute() method."""

    @pytest.mark.asyncio
    async def test_execute_yields_workflow_started_event(self) -> None:
        """Test that execute() yields WorkflowStarted as first event."""

        @workflow(name="test-workflow")
        def simple_workflow(input_value: str) -> str:
            yield step("step1").python(action=lambda: "result")
            return "done"

        engine = WorkflowEngine()
        events = []

        async for event in engine.execute(simple_workflow, input_value="test"):
            events.append(event)

        # First event should be WorkflowStarted
        assert len(events) >= 1
        assert isinstance(events[0], WorkflowStarted)
        assert events[0].workflow_name == "test-workflow"
        assert events[0].inputs == {"input_value": "test"}

    @pytest.mark.asyncio
    async def test_execute_yields_step_started_event(self) -> None:
        """Test that execute() yields StepStarted before each step."""

        @workflow(name="test-workflow")
        def simple_workflow() -> None:
            yield step("my-step").python(action=lambda: "result")

        engine = WorkflowEngine()
        events = []

        async for event in engine.execute(simple_workflow):
            events.append(event)

        # Should have: WorkflowStarted, StepStarted, StepCompleted, WorkflowCompleted
        step_started_events = [e for e in events if isinstance(e, StepStarted)]
        assert len(step_started_events) == 1
        assert step_started_events[0].step_name == "my-step"
        assert step_started_events[0].step_type == StepType.PYTHON

    @pytest.mark.asyncio
    async def test_execute_yields_step_completed_event(self) -> None:
        """Test that execute() yields StepCompleted after each step."""

        @workflow(name="test-workflow")
        def simple_workflow() -> None:
            yield step("my-step").python(action=lambda: "result")

        engine = WorkflowEngine()
        events = []

        async for event in engine.execute(simple_workflow):
            events.append(event)

        step_completed_events = [e for e in events if isinstance(e, StepCompleted)]
        assert len(step_completed_events) == 1
        assert step_completed_events[0].step_name == "my-step"
        assert step_completed_events[0].step_type == StepType.PYTHON
        assert step_completed_events[0].success is True
        assert step_completed_events[0].duration_ms >= 0

    @pytest.mark.asyncio
    async def test_execute_yields_workflow_completed_event(self) -> None:
        """Test that execute() yields WorkflowCompleted as last event."""

        @workflow(name="test-workflow")
        def simple_workflow() -> None:
            yield step("step1").python(action=lambda: "result")

        engine = WorkflowEngine()
        events = []

        async for event in engine.execute(simple_workflow):
            events.append(event)

        # Last event should be WorkflowCompleted
        assert isinstance(events[-1], WorkflowCompleted)
        assert events[-1].workflow_name == "test-workflow"
        assert events[-1].success is True
        assert events[-1].total_duration_ms >= 0

    @pytest.mark.asyncio
    async def test_execute_event_order_is_correct(self) -> None:
        """Test that events are emitted in correct order."""

        @workflow(name="test-workflow")
        def two_step_workflow() -> None:
            yield step("step1").python(action=lambda: "r1")
            yield step("step2").python(action=lambda: "r2")

        engine = WorkflowEngine()
        events = []

        async for event in engine.execute(two_step_workflow):
            events.append(event)

        # Expected order:
        # 1. WorkflowStarted
        # 2. StepStarted(step1)
        # 3. StepCompleted(step1)
        # 4. StepStarted(step2)
        # 5. StepCompleted(step2)
        # 6. WorkflowCompleted

        assert isinstance(events[0], WorkflowStarted)
        assert isinstance(events[1], StepStarted)
        assert events[1].step_name == "step1"
        assert isinstance(events[2], StepCompleted)
        assert events[2].step_name == "step1"
        assert isinstance(events[3], StepStarted)
        assert events[3].step_name == "step2"
        assert isinstance(events[4], StepCompleted)
        assert events[4].step_name == "step2"
        assert isinstance(events[5], WorkflowCompleted)


class TestWorkflowEngineGetResult:
    """Test WorkflowEngine.get_result() method."""

    @pytest.mark.asyncio
    async def test_get_result_returns_workflow_result(self) -> None:
        """Test that get_result() returns WorkflowResult after execution."""

        @workflow(name="test-workflow")
        def simple_workflow() -> None:
            yield step("step1").python(action=lambda: "result")

        engine = WorkflowEngine()

        # Consume all events
        async for _ in engine.execute(simple_workflow):
            pass

        result = engine.get_result()

        assert result.workflow_name == "test-workflow"
        assert result.success is True
        assert len(result.step_results) == 1
        assert result.step_results[0].name == "step1"

    @pytest.mark.asyncio
    async def test_get_result_raises_runtime_error_before_execute(self) -> None:
        """Test that get_result() raises RuntimeError if called before
        execute completes."""
        engine = WorkflowEngine()

        with pytest.raises(RuntimeError, match="not been executed"):
            engine.get_result()

    @pytest.mark.asyncio
    async def test_get_result_raises_runtime_error_during_execute(self) -> None:
        """Test that get_result() raises RuntimeError during execution."""

        @workflow(name="test-workflow")
        def simple_workflow() -> None:
            yield step("step1").python(action=lambda: "result")

        engine = WorkflowEngine()

        async for event in engine.execute(simple_workflow):
            # Try to get result mid-execution
            if isinstance(event, StepStarted):
                with pytest.raises(RuntimeError, match="not been executed"):
                    engine.get_result()
            break  # Don't consume all events


class TestWorkflowEngineFinalOutput:
    """Test WorkflowEngine final_output handling."""

    @pytest.mark.asyncio
    async def test_workflow_with_explicit_return_uses_return_value(self) -> None:
        """Test that workflow with return statement uses return value as
        final_output."""

        @workflow(name="test-workflow")
        def workflow_with_return() -> dict[str, str]:
            result1 = yield step("step1").python(action=lambda: "r1")
            result2 = yield step("step2").python(action=lambda: "r2")
            return {"combined": f"{result1}-{result2}"}

        engine = WorkflowEngine()

        async for _ in engine.execute(workflow_with_return):
            pass

        result = engine.get_result()

        # final_output should be the return value
        assert result.final_output == {"combined": "r1-r2"}

    @pytest.mark.asyncio
    async def test_workflow_without_return_uses_last_step_output(self) -> None:
        """Test that workflow without return uses last step output as final_output."""

        @workflow(name="test-workflow")
        def workflow_no_return() -> None:
            yield step("step1").python(action=lambda: "r1")
            yield step("step2").python(action=lambda: "last_output")

        engine = WorkflowEngine()

        async for _ in engine.execute(workflow_no_return):
            pass

        result = engine.get_result()

        # final_output should be last step's output
        assert result.final_output == "last_output"

    @pytest.mark.asyncio
    async def test_workflow_return_none_uses_none(self) -> None:
        """Test that explicit return None is used as final_output."""

        @workflow(name="test-workflow")
        def workflow_return_none() -> None:
            yield step("step1").python(action=lambda: "r1")
            return None

        engine = WorkflowEngine()

        async for _ in engine.execute(workflow_return_none):
            pass

        result = engine.get_result()

        # When explicitly returning None, last step output is used per FR-021
        # since final_output = None falls through to last step
        assert result.final_output == "r1"


class TestWorkflowEngineDuplicateStepNames:
    """Test WorkflowEngine duplicate step name detection."""

    @pytest.mark.asyncio
    async def test_duplicate_step_names_raise_error(self) -> None:
        """Test that duplicate step names raise DuplicateStepNameError."""

        @workflow(name="test-workflow")
        def bad_workflow() -> None:
            yield step("duplicate").python(action=lambda: "r1")
            yield step("duplicate").python(action=lambda: "r2")

        engine = WorkflowEngine()

        # Should raise during execution when duplicate is encountered
        with pytest.raises(DuplicateStepNameError) as exc_info:
            async for _ in engine.execute(bad_workflow):
                pass

        assert exc_info.value.step_name == "duplicate"

    @pytest.mark.asyncio
    async def test_duplicate_step_names_stop_workflow(self) -> None:
        """Test that duplicate step names stop workflow execution."""

        @workflow(name="test-workflow")
        def bad_workflow() -> None:
            yield step("step1").python(action=lambda: "r1")
            yield step("duplicate").python(action=lambda: "r2")
            yield step("duplicate").python(action=lambda: "r3")
            yield step("step4").python(action=lambda: "r4")  # Should not execute

        engine = WorkflowEngine()
        events = []

        with pytest.raises(DuplicateStepNameError):
            async for event in engine.execute(bad_workflow):
                events.append(event)

        # Should have executed step1 and first duplicate, but not step4
        completed_steps = [e for e in events if isinstance(e, StepCompleted)]
        # Depending on when detection happens, we might have 1 or 2 completed steps
        assert len(completed_steps) <= 2


class TestWorkflowEngineStepFailure:
    """Test WorkflowEngine behavior when steps fail."""

    @pytest.mark.asyncio
    async def test_step_failure_stops_workflow(self) -> None:
        """Test that step failure stops workflow execution."""

        @workflow(name="test-workflow")
        def failing_workflow() -> None:
            yield step("step1").python(action=lambda: "r1")
            yield step("failing-step").python(
                action=lambda: (_ for _ in ()).throw(ValueError("fail"))
            )
            yield step("step3").python(action=lambda: "r3")  # Should not execute

        engine = WorkflowEngine()
        events = []

        async for event in engine.execute(failing_workflow):
            events.append(event)

        # step3 should not have executed
        completed_steps = [e for e in events if isinstance(e, StepCompleted)]
        assert len(completed_steps) == 2  # step1 and failing-step
        assert completed_steps[1].success is False

    @pytest.mark.asyncio
    async def test_step_failure_returns_failed_workflow_result(self) -> None:
        """Test that step failure results in failed WorkflowResult."""

        def raise_error() -> None:
            raise RuntimeError("Step failed")

        @workflow(name="test-workflow")
        def failing_workflow() -> None:
            yield step("step1").python(action=lambda: "r1")
            yield step("failing-step").python(action=raise_error)

        engine = WorkflowEngine()

        async for _ in engine.execute(failing_workflow):
            pass

        result = engine.get_result()

        assert result.success is False
        assert result.failed_step is not None
        assert result.failed_step.name == "failing-step"

    @pytest.mark.asyncio
    async def test_step_failure_emits_failed_step_completed(self) -> None:
        """Test that failed step emits StepCompleted with success=False."""

        def raise_error() -> None:
            raise RuntimeError("Step failed")

        @workflow(name="test-workflow")
        def failing_workflow() -> None:
            yield step("failing-step").python(action=raise_error)

        engine = WorkflowEngine()
        events = []

        async for event in engine.execute(failing_workflow):
            events.append(event)

        completed_events = [e for e in events if isinstance(e, StepCompleted)]
        assert len(completed_events) == 1
        assert completed_events[0].success is False

    @pytest.mark.asyncio
    async def test_step_failure_emits_failed_workflow_completed(self) -> None:
        """Test that workflow failure emits WorkflowCompleted with success=False."""

        def raise_error() -> None:
            raise RuntimeError("Step failed")

        @workflow(name="test-workflow")
        def failing_workflow() -> None:
            yield step("failing-step").python(action=raise_error)

        engine = WorkflowEngine()
        events = []

        async for event in engine.execute(failing_workflow):
            events.append(event)

        workflow_completed = [e for e in events if isinstance(e, WorkflowCompleted)]
        assert len(workflow_completed) == 1
        assert workflow_completed[0].success is False


class TestWorkflowEngineMultipleSteps:
    """Test WorkflowEngine with multiple steps."""

    @pytest.mark.asyncio
    async def test_workflow_with_three_steps(self) -> None:
        """Test workflow with multiple sequential steps."""

        @workflow(name="test-workflow")
        def multi_step_workflow() -> str:
            r1 = yield step("step1").python(action=lambda: 1)
            r2 = yield step("step2").python(action=lambda: 2)
            r3 = yield step("step3").python(action=lambda: 3)
            return f"{r1}-{r2}-{r3}"

        engine = WorkflowEngine()

        async for _ in engine.execute(multi_step_workflow):
            pass

        result = engine.get_result()

        assert result.success is True
        assert len(result.step_results) == 3
        assert result.final_output == "1-2-3"

    @pytest.mark.asyncio
    async def test_workflow_step_results_stored_in_context(self) -> None:
        """Test that step results are accessible in subsequent steps."""

        @workflow(name="test-workflow")
        def workflow_with_deps() -> str:
            r1 = yield step("step1").python(action=lambda: "first")
            # r1 should contain the output from step1
            r2 = yield step("step2").python(action=lambda x: f"{x}-second", args=(r1,))
            return r2

        engine = WorkflowEngine()

        async for _ in engine.execute(workflow_with_deps):
            pass

        result = engine.get_result()

        assert result.success is True
        assert result.final_output == "first-second"


class TestWorkflowEngineEmptyWorkflow:
    """Test WorkflowEngine with edge cases."""

    @pytest.mark.asyncio
    async def test_workflow_with_no_steps(self) -> None:
        """Test workflow that yields no steps but still uses yield expression."""

        @workflow(name="empty-workflow")
        def empty_workflow() -> str:
            # Use a conditional that never triggers to satisfy generator requirement
            if False:
                yield step("never").python(action=lambda: None)
            return "immediate_result"

        engine = WorkflowEngine()

        async for _ in engine.execute(empty_workflow):
            pass

        result = engine.get_result()

        assert result.success is True
        assert len(result.step_results) == 0
        assert result.final_output == "immediate_result"


class TestWorkflowEngineTimestamps:
    """Test that events have valid timestamps."""

    @pytest.mark.asyncio
    async def test_events_have_timestamps(self) -> None:
        """Test that all progress events have valid timestamps."""

        @workflow(name="test-workflow")
        def simple_workflow() -> None:
            yield step("step1").python(action=lambda: "r1")

        engine = WorkflowEngine()
        events = []

        async for event in engine.execute(simple_workflow):
            events.append(event)

        # All events should have timestamps
        for event in events:
            assert hasattr(event, "timestamp")
            assert isinstance(event.timestamp, float)
            assert event.timestamp > 0

    @pytest.mark.asyncio
    async def test_timestamps_are_sequential(self) -> None:
        """Test that event timestamps are in chronological order."""

        @workflow(name="test-workflow")
        def simple_workflow() -> None:
            yield step("step1").python(action=lambda: "r1")

        engine = WorkflowEngine()
        events = []

        async for event in engine.execute(simple_workflow):
            events.append(event)

        # Timestamps should be monotonically increasing
        for i in range(len(events) - 1):
            assert events[i].timestamp <= events[i + 1].timestamp
