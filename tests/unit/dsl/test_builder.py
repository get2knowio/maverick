"""Unit tests for step() builder function and StepBuilder class.

This module tests the fluent builder API for creating workflow steps.

TDD Note: These tests are written FIRST and will FAIL until implementation
is complete. They define the expected behavior of the builder.
"""

from __future__ import annotations

import pytest

from maverick.dsl import PythonStep, StepType, step


class TestStepBuilderFunction:
    """Test the step() builder function."""

    def test_step_returns_step_builder_with_correct_name(self) -> None:
        """Test that step(name) returns a StepBuilder instance with correct name."""
        builder = step("test-step")

        # Builder should be a StepBuilder instance
        assert builder is not None
        assert hasattr(builder, "python")  # Has python() method

        # When we build a step, it should have the correct name
        python_step = builder.python(action=lambda: None)
        assert python_step.name == "test-step"

    def test_step_raises_value_error_for_empty_name(self) -> None:
        """Test that step("") raises ValueError for empty name."""
        with pytest.raises(ValueError, match="name.*empty"):
            step("")

    def test_step_raises_value_error_for_whitespace_only_name(self) -> None:
        """Test that step with only whitespace raises ValueError."""
        with pytest.raises(ValueError, match="name.*empty"):
            step("   ")


class TestStepBuilderPythonMethod:
    """Test StepBuilder.python() method."""

    def test_python_returns_python_step_with_correct_name(self) -> None:
        """Test that python() returns PythonStep with correct name."""

        def dummy_action() -> str:
            return "result"

        python_step = step("my-step").python(action=dummy_action)

        assert isinstance(python_step, PythonStep)
        assert python_step.name == "my-step"

    def test_python_returns_python_step_with_correct_action(self) -> None:
        """Test that python() stores the action callable."""

        def dummy_action() -> str:
            return "result"

        python_step = step("my-step").python(action=dummy_action)

        assert python_step.action is dummy_action

    def test_python_returns_python_step_with_default_args(self) -> None:
        """Test that python() defaults to empty args tuple."""

        def dummy_action() -> str:
            return "result"

        python_step = step("my-step").python(action=dummy_action)

        assert python_step.args == ()

    def test_python_returns_python_step_with_default_kwargs(self) -> None:
        """Test that python() defaults to empty kwargs dict."""

        def dummy_action() -> str:
            return "result"

        python_step = step("my-step").python(action=dummy_action)

        assert python_step.kwargs == {}

    def test_python_returns_python_step_with_provided_args(self) -> None:
        """Test that python() accepts args parameter."""

        def dummy_action(a: int, b: str) -> str:
            return f"{a}-{b}"

        python_step = step("my-step").python(
            action=dummy_action,
            args=(42, "hello"),
        )

        assert python_step.args == (42, "hello")

    def test_python_returns_python_step_with_provided_kwargs(self) -> None:
        """Test that python() accepts kwargs parameter."""

        def dummy_action(x: int = 0, y: str = "") -> str:
            return f"{x}-{y}"

        python_step = step("my-step").python(
            action=dummy_action,
            kwargs={"x": 10, "y": "world"},
        )

        assert python_step.kwargs == {"x": 10, "y": "world"}

    def test_python_accepts_none_kwargs_and_converts_to_empty_dict(self) -> None:
        """Test that python(kwargs=None) is converted to empty dict."""

        def dummy_action() -> str:
            return "result"

        python_step = step("my-step").python(action=dummy_action, kwargs=None)

        assert python_step.kwargs == {}

    def test_python_step_has_correct_step_type(self) -> None:
        """Test that PythonStep has step_type = StepType.PYTHON."""

        def dummy_action() -> str:
            return "result"

        python_step = step("my-step").python(action=dummy_action)

        assert python_step.step_type == StepType.PYTHON

    def test_python_accepts_sync_callable(self) -> None:
        """Test that python() accepts synchronous callables."""

        def sync_action() -> str:
            return "sync"

        python_step = step("my-step").python(action=sync_action)

        assert python_step.action is sync_action

    def test_python_accepts_async_callable(self) -> None:
        """Test that python() accepts asynchronous callables."""

        async def async_action() -> str:
            return "async"

        python_step = step("my-step").python(action=async_action)

        assert python_step.action is async_action

    def test_python_accepts_lambda(self) -> None:
        """Test that python() accepts lambda functions."""

        def lambda_action(x):
            return x * 2

        python_step = step("my-step").python(action=lambda_action, args=(5,))

        assert python_step.action is lambda_action

    def test_python_accepts_class_method(self) -> None:
        """Test that python() accepts bound methods."""

        class MyClass:
            def my_method(self) -> str:
                return "method"

        obj = MyClass()
        bound_method = obj.my_method
        python_step = step("my-step").python(action=bound_method)

        # Bound methods may not be identical but should be equal
        assert python_step.action == bound_method

    def test_python_builder_is_immutable(self) -> None:
        """Test that calling python() doesn't mutate the builder."""
        builder = step("my-step")

        # Create two steps from same builder
        step1 = builder.python(action=lambda: 1)
        step2 = builder.python(action=lambda: 2)

        # They should be different instances
        assert step1 is not step2
        assert step1.action is not step2.action


class TestStepBuilderChaining:
    """Test that StepBuilder provides fluent API (though python() is terminal)."""

    def test_step_builder_returns_correct_step_type(self) -> None:
        """Test that each builder method returns the appropriate step type."""

        def dummy_action() -> str:
            return "result"

        # python() should return PythonStep
        python_step = step("step-name").python(action=dummy_action)
        assert isinstance(python_step, PythonStep)

    def test_multiple_steps_from_same_name(self) -> None:
        """Test creating multiple different step types with same name
        (builder pattern)."""

        def dummy_action() -> str:
            return "result"

        # Even though we use same name, we get different step instances
        # (In practice, duplicate names would be caught by engine)
        step1 = step("duplicate").python(action=dummy_action)
        step2 = step("duplicate").python(action=lambda: "different")

        assert step1 is not step2
        assert step1.name == step2.name == "duplicate"
