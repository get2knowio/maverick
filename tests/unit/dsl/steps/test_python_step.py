"""Unit tests for PythonStep class.

This module tests the PythonStep class that executes Python callables
within workflow execution.

TDD Note: These tests are written FIRST and will FAIL until implementation
is complete. They define the expected behavior of PythonStep.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from maverick.dsl import PythonStep, StepResult, StepType, WorkflowContext


class TestPythonStepCreation:
    """Test PythonStep instantiation and properties."""

    def test_creation_with_required_fields(self) -> None:
        """Test creating PythonStep with minimal required fields."""

        def dummy_action() -> str:
            return "result"

        step = PythonStep(
            name="test-step",
            action=dummy_action,
        )

        assert step.name == "test-step"
        assert step.action is dummy_action
        assert step.args == ()
        assert step.kwargs == {}

    def test_creation_with_all_fields(self) -> None:
        """Test creating PythonStep with all fields."""

        def dummy_action(a: int, b: str, x: int = 0) -> str:
            return f"{a}-{b}-{x}"

        step = PythonStep(
            name="test-step",
            action=dummy_action,
            args=(42, "hello"),
            kwargs={"x": 10},
        )

        assert step.name == "test-step"
        assert step.action is dummy_action
        assert step.args == (42, "hello")
        assert step.kwargs == {"x": 10}

    def test_step_type_is_python(self) -> None:
        """Test that step_type is always StepType.PYTHON."""

        def dummy_action() -> str:
            return "result"

        step = PythonStep(name="test-step", action=dummy_action)

        assert step.step_type == StepType.PYTHON

    def test_python_step_is_frozen(self) -> None:
        """Test that PythonStep is immutable (frozen=True)."""

        def dummy_action() -> str:
            return "result"

        step = PythonStep(name="test-step", action=dummy_action)

        # Attempt to modify should raise error
        with pytest.raises((AttributeError, TypeError)):
            step.name = "modified"

    def test_python_step_has_slots(self) -> None:
        """Test that PythonStep declares __slots__ for memory efficiency."""

        def dummy_action() -> str:
            return "result"

        PythonStep(name="test-step", action=dummy_action)

        # Dataclass with slots=True declares __slots__
        # Note: May still have __dict__ if parent class doesn't use slots
        assert hasattr(PythonStep, "__slots__")


class TestPythonStepToDict:
    """Test PythonStep.to_dict() serialization."""

    def test_to_dict_returns_expected_structure(self) -> None:
        """Test that to_dict() returns correct structure."""

        def my_action(a: int, b: str, x: int = 0) -> str:
            return f"{a}-{b}-{x}"

        step = PythonStep(
            name="test-step",
            action=my_action,
            args=(1, 2),
            kwargs={"key1": "value1", "key2": "value2"},
        )

        result = step.to_dict()

        assert result["name"] == "test-step"
        assert result["step_type"] == "python"
        assert result["action"] == "my_action"
        assert result["args_count"] == 2
        assert result["kwargs_keys"] == ["key1", "key2"]

    def test_to_dict_with_lambda(self) -> None:
        """Test to_dict() with lambda function."""
        step = PythonStep(
            name="test-step",
            action=lambda x: x * 2,
            args=(5,),
        )

        result = step.to_dict()

        assert result["action"] == "<lambda>"

    def test_to_dict_with_no_args_or_kwargs(self) -> None:
        """Test to_dict() with empty args and kwargs."""

        def my_action() -> str:
            return "result"

        step = PythonStep(name="test-step", action=my_action)

        result = step.to_dict()

        assert result["args_count"] == 0
        assert result["kwargs_keys"] == []


class TestPythonStepExecuteSync:
    """Test PythonStep.execute() with synchronous callables."""

    @pytest.mark.asyncio
    async def test_execute_with_sync_callable_returns_step_result(self) -> None:
        """Test that execute() with sync callable returns StepResult."""

        def sync_action() -> str:
            return "sync_result"

        step = PythonStep(name="test-step", action=sync_action)
        context = WorkflowContext(inputs={}, results={})

        result = await step.execute(context)

        assert isinstance(result, StepResult)
        assert result.name == "test-step"
        assert result.step_type == StepType.PYTHON
        assert result.success is True
        assert result.output == "sync_result"
        assert result.duration_ms >= 0
        assert result.error is None

    @pytest.mark.asyncio
    async def test_execute_with_sync_callable_and_args(self) -> None:
        """Test execute() passes args to sync callable."""

        def sync_action(a: int, b: str) -> str:
            return f"{a}-{b}"

        step = PythonStep(name="test-step", action=sync_action, args=(42, "hello"))
        context = WorkflowContext(inputs={}, results={})

        result = await step.execute(context)

        assert result.success is True
        assert result.output == "42-hello"

    @pytest.mark.asyncio
    async def test_execute_with_sync_callable_and_kwargs(self) -> None:
        """Test execute() passes kwargs to sync callable."""

        def sync_action(x: int = 0, y: str = "") -> str:
            return f"{x}-{y}"

        step = PythonStep(
            name="test-step",
            action=sync_action,
            kwargs={"x": 10, "y": "world"},
        )
        context = WorkflowContext(inputs={}, results={})

        result = await step.execute(context)

        assert result.success is True
        assert result.output == "10-world"

    @pytest.mark.asyncio
    async def test_execute_with_sync_callable_and_args_and_kwargs(self) -> None:
        """Test execute() with both args and kwargs."""

        def sync_action(a: int, b: str, x: int = 0) -> str:
            return f"{a}-{b}-{x}"

        step = PythonStep(
            name="test-step",
            action=sync_action,
            args=(1, "two"),
            kwargs={"x": 3},
        )
        context = WorkflowContext(inputs={}, results={})

        result = await step.execute(context)

        assert result.success is True
        assert result.output == "1-two-3"


class TestPythonStepExecuteAsync:
    """Test PythonStep.execute() with asynchronous callables."""

    @pytest.mark.asyncio
    async def test_execute_with_async_callable_returns_step_result(self) -> None:
        """Test that execute() with async callable returns StepResult."""

        async def async_action() -> str:
            await asyncio.sleep(0.001)
            return "async_result"

        step = PythonStep(name="test-step", action=async_action)
        context = WorkflowContext(inputs={}, results={})

        result = await step.execute(context)

        assert isinstance(result, StepResult)
        assert result.name == "test-step"
        assert result.step_type == StepType.PYTHON
        assert result.success is True
        assert result.output == "async_result"
        assert result.duration_ms >= 0
        assert result.error is None

    @pytest.mark.asyncio
    async def test_execute_with_async_callable_and_args(self) -> None:
        """Test execute() passes args to async callable."""

        async def async_action(a: int, b: str) -> str:
            await asyncio.sleep(0.001)
            return f"{a}-{b}"

        step = PythonStep(name="test-step", action=async_action, args=(99, "test"))
        context = WorkflowContext(inputs={}, results={})

        result = await step.execute(context)

        assert result.success is True
        assert result.output == "99-test"

    @pytest.mark.asyncio
    async def test_execute_with_async_callable_and_kwargs(self) -> None:
        """Test execute() passes kwargs to async callable."""

        async def async_action(x: int = 0, y: str = "") -> str:
            await asyncio.sleep(0.001)
            return f"{x}+{y}"

        step = PythonStep(
            name="test-step",
            action=async_action,
            kwargs={"x": 5, "y": "async"},
        )
        context = WorkflowContext(inputs={}, results={})

        result = await step.execute(context)

        assert result.success is True
        assert result.output == "5+async"


class TestPythonStepExecuteExceptionHandling:
    """Test PythonStep.execute() exception handling."""

    @pytest.mark.asyncio
    async def test_execute_handles_sync_exception(self) -> None:
        """Test that execute() catches exceptions and returns failed StepResult."""

        def failing_action() -> None:
            raise ValueError("Something went wrong")

        step = PythonStep(name="test-step", action=failing_action)
        context = WorkflowContext(inputs={}, results={})

        result = await step.execute(context)

        assert result.success is False
        assert result.output is None
        assert result.error is not None
        assert "ValueError" in result.error
        assert "Something went wrong" in result.error
        assert result.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_execute_handles_async_exception(self) -> None:
        """Test that execute() catches async exceptions."""

        async def failing_action() -> None:
            await asyncio.sleep(0.001)
            raise RuntimeError("Async failure")

        step = PythonStep(name="test-step", action=failing_action)
        context = WorkflowContext(inputs={}, results={})

        result = await step.execute(context)

        assert result.success is False
        assert result.output is None
        assert result.error is not None
        assert "RuntimeError" in result.error
        assert "Async failure" in result.error

    @pytest.mark.asyncio
    async def test_execute_handles_exception_with_args(self) -> None:
        """Test exception handling when args are involved."""

        def failing_action(a: int, b: str) -> None:
            raise TypeError(f"Failed with {a} and {b}")

        step = PythonStep(name="test-step", action=failing_action, args=(1, "two"))
        context = WorkflowContext(inputs={}, results={})

        result = await step.execute(context)

        assert result.success is False
        assert "TypeError" in result.error
        assert "Failed with 1 and two" in result.error

    @pytest.mark.asyncio
    async def test_execute_with_zero_return_value(self) -> None:
        """Test that execute() correctly handles falsy but valid return values."""

        def zero_action() -> int:
            return 0

        step = PythonStep(name="test-step", action=zero_action)
        context = WorkflowContext(inputs={}, results={})

        result = await step.execute(context)

        assert result.success is True
        assert result.output == 0

    @pytest.mark.asyncio
    async def test_execute_with_none_return_value(self) -> None:
        """Test that execute() correctly handles None return value."""

        def none_action() -> None:
            return None

        step = PythonStep(name="test-step", action=none_action)
        context = WorkflowContext(inputs={}, results={})

        result = await step.execute(context)

        assert result.success is True
        assert result.output is None

    @pytest.mark.asyncio
    async def test_execute_with_complex_return_value(self) -> None:
        """Test execute() with complex return value (dict, list, etc.)."""

        def complex_action() -> dict[str, Any]:
            return {
                "status": "success",
                "data": [1, 2, 3],
                "metadata": {"key": "value"},
            }

        step = PythonStep(name="test-step", action=complex_action)
        context = WorkflowContext(inputs={}, results={})

        result = await step.execute(context)

        assert result.success is True
        assert result.output == {
            "status": "success",
            "data": [1, 2, 3],
            "metadata": {"key": "value"},
        }


class TestPythonStepExecuteDuration:
    """Test that execute() correctly measures duration."""

    @pytest.mark.asyncio
    async def test_execute_measures_duration(self) -> None:
        """Test that execute() records execution duration in milliseconds."""

        async def slow_action() -> str:
            await asyncio.sleep(0.05)  # 50ms
            return "done"

        step = PythonStep(name="test-step", action=slow_action)
        context = WorkflowContext(inputs={}, results={})

        result = await step.execute(context)

        # Should be at least 50ms (accounting for overhead)
        assert result.duration_ms >= 40
        assert result.duration_ms < 200  # Sanity check

    @pytest.mark.asyncio
    async def test_execute_duration_on_failure(self) -> None:
        """Test that execute() records duration even when action fails."""

        async def failing_action() -> None:
            await asyncio.sleep(0.01)
            raise ValueError("fail")

        step = PythonStep(name="test-step", action=failing_action)
        context = WorkflowContext(inputs={}, results={})

        result = await step.execute(context)

        assert result.success is False
        assert result.duration_ms >= 5  # At least some time recorded


class TestPythonStepNonBlocking:
    """Test that PythonStep doesn't block the event loop with sync callables."""

    @pytest.mark.asyncio
    async def test_sync_callable_runs_in_thread_pool(self) -> None:
        """Test that sync callables are offloaded via asyncio.to_thread.

        This ensures blocking operations don't freeze the event loop.
        """
        import threading

        main_thread_id = threading.current_thread().ident
        callable_thread_id = None

        def sync_action() -> str:
            nonlocal callable_thread_id
            callable_thread_id = threading.current_thread().ident
            return "done"

        step = PythonStep(name="test-step", action=sync_action)
        context = WorkflowContext(inputs={}, results={})

        result = await step.execute(context)

        assert result.success is True
        assert callable_thread_id is not None
        # Sync callable should run in a different thread
        assert callable_thread_id != main_thread_id

    @pytest.mark.asyncio
    async def test_async_callable_runs_in_main_thread(self) -> None:
        """Test that async callables run directly on the event loop thread."""
        import threading

        main_thread_id = threading.current_thread().ident
        callable_thread_id = None

        async def async_action() -> str:
            nonlocal callable_thread_id
            callable_thread_id = threading.current_thread().ident
            return "done"

        step = PythonStep(name="test-step", action=async_action)
        context = WorkflowContext(inputs={}, results={})

        result = await step.execute(context)

        assert result.success is True
        assert callable_thread_id is not None
        # Async callable should run in the same (event loop) thread
        assert callable_thread_id == main_thread_id

    @pytest.mark.asyncio
    async def test_sync_callable_exception_preserves_traceback(self) -> None:
        """Test that exceptions from sync callables in thread pool are handled."""

        def failing_sync_action() -> None:
            raise RuntimeError("Error from thread pool")

        step = PythonStep(name="test-step", action=failing_sync_action)
        context = WorkflowContext(inputs={}, results={})

        result = await step.execute(context)

        assert result.success is False
        assert "RuntimeError" in result.error
        assert "Error from thread pool" in result.error
