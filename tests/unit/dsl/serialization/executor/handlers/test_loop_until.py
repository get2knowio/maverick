"""Unit tests for the until loop handler."""

from __future__ import annotations

from typing import Any

import pytest

from maverick.dsl.context import WorkflowContext
from maverick.dsl.errors import LoopStepExecutionError
from maverick.dsl.events import (
    LoopConditionChecked,
    LoopIterationCompleted,
    LoopIterationStarted,
)
from maverick.dsl.serialization.executor.handlers.loop_step import execute_loop_step
from maverick.dsl.serialization.registry import ComponentRegistry
from maverick.dsl.serialization.schema import LoopStepRecord, PythonStepRecord
from maverick.dsl.types import StepType


def _make_python_step(name: str) -> PythonStepRecord:
    """Create a minimal PythonStepRecord for testing."""
    return PythonStepRecord(
        name=name,
        type=StepType.PYTHON,
        action="noop",
    )


def _make_until_loop(
    until: str,
    steps: list[PythonStepRecord] | None = None,
    max_iterations: int = 30,
) -> LoopStepRecord:
    """Create a LoopStepRecord with an until expression."""
    return LoopStepRecord(
        name="test_loop",
        type=StepType.LOOP,
        until=until,
        max_iterations=max_iterations,
        steps=steps or [_make_python_step("body_step")],
    )


def _make_context(results: dict[str, Any] | None = None) -> WorkflowContext:
    """Create a WorkflowContext for testing."""
    ctx = WorkflowContext(
        inputs={},
        results={},
        iteration_context={},
    )
    if results:
        for name, output in results.items():
            ctx.store_step_output(name, output, "python")
    return ctx


class TestExecuteLoopUntil:
    """Tests for _execute_loop_until via execute_loop_step."""

    @pytest.mark.asyncio
    async def test_terminates_when_condition_true(self) -> None:
        """Loop should stop when until condition evaluates to truthy."""
        context = _make_context()
        call_count = 0

        async def mock_execute_step(step: Any, ctx: Any, callback: Any = None) -> Any:
            nonlocal call_count
            call_count += 1
            # Return the check_done result directly — the handler stores it
            if step.name == "check_done":
                done = call_count >= 4
                return {"done": done}
            return {"executed": True}

        loop = _make_until_loop(
            until="${{ steps.check_done.output.done }}",
            steps=[
                _make_python_step("process"),
                _make_python_step("check_done"),
            ],
            max_iterations=10,
        )

        result = await execute_loop_step(
            step=loop,
            resolved_inputs={},
            context=context,
            registry=ComponentRegistry(),
            execute_step_fn=mock_execute_step,
        )

        # Should have run 2 iterations (4 step calls = 2 iterations * 2 steps)
        assert call_count == 4
        assert result.result is not None
        assert len(result.result) == 2

    @pytest.mark.asyncio
    async def test_safety_valve_at_max_iterations(self) -> None:
        """Loop should stop at max_iterations even if condition not met."""
        context = _make_context()
        call_count = 0

        async def mock_execute_step(step: Any, ctx: Any, callback: Any = None) -> Any:
            nonlocal call_count
            call_count += 1
            # Never set done to True — return directly, handler stores it
            return {"done": False}

        loop = _make_until_loop(
            until="${{ steps.check.output.done }}",
            steps=[_make_python_step("check")],
            max_iterations=3,
        )

        result = await execute_loop_step(
            step=loop,
            resolved_inputs={},
            context=context,
            registry=ComponentRegistry(),
            execute_step_fn=mock_execute_step,
        )

        assert call_count == 3
        assert len(result.result) == 3

    @pytest.mark.asyncio
    async def test_body_step_outputs_accessible_to_condition(self) -> None:
        """Until expression should see outputs from body steps."""
        context = _make_context()
        iteration = 0

        async def mock_execute_step(step: Any, ctx: Any, callback: Any = None) -> Any:
            nonlocal iteration
            if step.name == "counter":
                iteration += 1
                value = iteration >= 2
                # Return directly — handler stores the output automatically
                return {"reached": value}
            return {}

        loop = _make_until_loop(
            until="${{ steps.counter.output.reached }}",
            steps=[_make_python_step("counter")],
            max_iterations=10,
        )

        result = await execute_loop_step(
            step=loop,
            resolved_inputs={},
            context=context,
            registry=ComponentRegistry(),
            execute_step_fn=mock_execute_step,
        )

        assert iteration == 2
        assert len(result.result) == 2

    @pytest.mark.asyncio
    async def test_emits_correct_events(self) -> None:
        """Should emit LoopIterationStarted, Completed, and ConditionChecked."""
        context = _make_context()
        events: list[Any] = []

        async def mock_callback(event: Any) -> None:
            events.append(event)

        call_count = 0

        async def mock_execute_step(step: Any, ctx: Any, callback: Any = None) -> Any:
            nonlocal call_count
            call_count += 1
            # Return directly — handler stores the output automatically
            return {"done": call_count >= 1}

        loop = _make_until_loop(
            until="${{ steps.check.output.done }}",
            steps=[_make_python_step("check")],
            max_iterations=5,
        )

        await execute_loop_step(
            step=loop,
            resolved_inputs={},
            context=context,
            registry=ComponentRegistry(),
            execute_step_fn=mock_execute_step,
            event_callback=mock_callback,
        )

        # Filter by event types
        started = [e for e in events if isinstance(e, LoopIterationStarted)]
        completed = [e for e in events if isinstance(e, LoopIterationCompleted)]
        checked = [e for e in events if isinstance(e, LoopConditionChecked)]

        assert len(started) == 1
        assert len(completed) == 1
        assert len(checked) == 1
        assert checked[0].condition_met is True
        assert checked[0].iteration_index == 0

    @pytest.mark.asyncio
    async def test_body_failure_stops_loop(self) -> None:
        """Loop should stop when a body step raises an exception."""
        context = _make_context()

        async def mock_execute_step(step: Any, ctx: Any, callback: Any = None) -> Any:
            raise RuntimeError("body step failed")

        loop = _make_until_loop(
            until="${{ steps.check.output.done }}",
            steps=[_make_python_step("check")],
            max_iterations=5,
        )

        with pytest.raises(LoopStepExecutionError):
            await execute_loop_step(
                step=loop,
                resolved_inputs={},
                context=context,
                registry=ComponentRegistry(),
                execute_step_fn=mock_execute_step,
            )

    @pytest.mark.asyncio
    async def test_requires_execute_step_fn(self) -> None:
        """Should raise ValueError if execute_step_fn is not provided."""
        context = _make_context()
        loop = _make_until_loop(
            until="${{ steps.check.output.done }}",
        )

        with pytest.raises(ValueError, match="execute_step_fn is required"):
            await execute_loop_step(
                step=loop,
                resolved_inputs={},
                context=context,
                registry=ComponentRegistry(),
                execute_step_fn=None,
            )
