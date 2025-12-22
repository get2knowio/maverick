"""Unit tests for @workflow decorator.

This module tests the @workflow decorator that captures function signature
parameters and creates executable workflows from generator functions.

TDD Note: These tests are written FIRST and will FAIL until implementation
is complete. They define the expected behavior of the decorator.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest

from maverick.dsl import workflow


class TestWorkflowDecorator:
    """Test the @workflow decorator."""

    def test_decorator_captures_function_signature_correctly(self) -> None:
        """Test that decorator captures all function parameters with metadata."""

        @workflow(name="test-workflow", description="Test description")
        def sample_workflow(
            arg1: str,
            arg2: int = 42,
            *args: Any,
            kwonly: str = "default",
            **kwargs: Any,
        ) -> dict[str, Any]:
            """Sample workflow docstring."""
            result = yield None  # Placeholder
            return {"result": result}

        # Access the workflow definition attached to the wrapper
        workflow_def = sample_workflow.__workflow_def__

        # Verify all parameters are captured
        assert len(workflow_def.parameters) == 5

        # Check each parameter's metadata
        params = {p.name: p for p in workflow_def.parameters}

        # arg1: positional-or-keyword with str annotation, no default
        # Note: Due to `from __future__ import annotations`, annotations
        # are stored as strings. kind is stored as a string name
        # (e.g., "POSITIONAL_OR_KEYWORD") instead of inspect enum
        assert params["arg1"].name == "arg1"
        assert params["arg1"].annotation == "str"
        assert params["arg1"].default is None  # Implementation uses None for no default
        assert params["arg1"].kind == "POSITIONAL_OR_KEYWORD"

        # arg2: positional-or-keyword with int annotation, default=42
        assert params["arg2"].name == "arg2"
        assert params["arg2"].annotation == "int"
        assert params["arg2"].default == 42
        assert params["arg2"].kind == "POSITIONAL_OR_KEYWORD"

        # args: VAR_POSITIONAL
        assert params["args"].name == "args"
        assert params["args"].annotation == "Any"
        assert params["args"].kind == "VAR_POSITIONAL"

        # kwonly: KEYWORD_ONLY
        assert params["kwonly"].name == "kwonly"
        assert params["kwonly"].annotation == "str"
        assert params["kwonly"].default == "default"
        assert params["kwonly"].kind == "KEYWORD_ONLY"

        # kwargs: VAR_KEYWORD
        assert params["kwargs"].name == "kwargs"
        assert params["kwargs"].annotation == "Any"
        assert params["kwargs"].kind == "VAR_KEYWORD"

    def test_decorator_validates_name_not_empty(self) -> None:
        """Test that decorator raises ValueError if name is empty."""
        with pytest.raises(ValueError, match="name.*empty"):

            @workflow(name="", description="Test")
            def bad_workflow() -> None:
                yield None

    def test_decorator_validates_function_is_generator(self) -> None:
        """Test that decorator raises TypeError if function is not a generator."""
        with pytest.raises(TypeError, match="generator"):

            @workflow(name="test-workflow")
            def not_a_generator() -> dict[str, Any]:
                return {"result": "value"}

    def test_decorator_attaches_workflow_def_attribute(self) -> None:
        """Test that decorator attaches __workflow_def__ to the wrapper."""

        @workflow(name="test-workflow", description="Test description")
        def sample_workflow() -> None:
            yield None

        # Verify __workflow_def__ is attached
        assert hasattr(sample_workflow, "__workflow_def__")
        assert sample_workflow.__workflow_def__ is not None

    def test_workflow_definition_contains_correct_metadata(self) -> None:
        """Test that WorkflowDefinition has correct name, description, func."""

        def original_func() -> Generator[None, None, None]:
            """Original docstring."""
            yield None

        decorated = workflow(name="my-workflow", description="My description")(
            original_func
        )
        workflow_def = decorated.__workflow_def__

        # Verify WorkflowDefinition fields
        assert workflow_def.name == "my-workflow"
        assert workflow_def.description == "My description"
        assert workflow_def.func == original_func

    def test_wrapper_preserves_function_docstring_and_name(self) -> None:
        """Test that wrapper preserves original function's docstring and __name__."""

        @workflow(name="test-workflow")
        def sample_workflow() -> None:
            """This is the docstring."""
            yield None

        # functools.wraps should preserve these
        assert sample_workflow.__name__ == "sample_workflow"
        assert sample_workflow.__doc__ == "This is the docstring."

    def test_decorator_with_minimal_arguments(self) -> None:
        """Test decorator with only required 'name' argument."""

        @workflow(name="minimal-workflow")
        def minimal() -> None:
            yield None

        workflow_def = minimal.__workflow_def__
        assert workflow_def.name == "minimal-workflow"
        assert workflow_def.description == ""  # Empty description is default

    def test_decorator_captures_no_parameters(self) -> None:
        """Test decorator with function that has no parameters."""

        @workflow(name="no-params")
        def no_params() -> None:
            yield None

        workflow_def = no_params.__workflow_def__
        assert len(workflow_def.parameters) == 0

    def test_decorator_captures_unannotated_parameters(self) -> None:
        """Test that decorator handles parameters without type annotations."""

        @workflow(name="unannotated")
        def unannotated_params(arg1, arg2=10):  # No type annotations
            yield None

        workflow_def = unannotated_params.__workflow_def__
        params = {p.name: p for p in workflow_def.parameters}

        # Parameters without annotations have annotation == None (implementation choice)
        assert params["arg1"].annotation is None
        assert params["arg2"].annotation is None
        assert params["arg2"].default == 10

    def test_decorator_preserves_generator_return_annotation(self) -> None:
        """Test that decorator preserves the return type annotation."""

        @workflow(name="return-annotated")
        def return_annotated() -> dict[str, Any]:
            result = yield None
            return {"result": result}

        # The wrapper should preserve return annotation (though not strictly required)
        # This is more about ensuring functools.wraps works correctly
        assert return_annotated.__workflow_def__.func == return_annotated.__wrapped__


class TestWorkflowDefinitionDataclass:
    """Test WorkflowDefinition dataclass properties."""

    def test_workflow_definition_is_frozen(self) -> None:
        """Test that WorkflowDefinition is immutable (frozen=True)."""

        @workflow(name="test-workflow")
        def sample() -> None:
            yield None

        workflow_def = sample.__workflow_def__

        # Attempt to modify should raise error (frozen dataclass)
        with pytest.raises((AttributeError, TypeError)):
            workflow_def.name = "modified-name"

    def test_workflow_definition_has_slots(self) -> None:
        """Test that WorkflowDefinition uses __slots__ for memory efficiency."""

        @workflow(name="test-workflow")
        def sample() -> None:
            yield None

        workflow_def = sample.__workflow_def__

        # Dataclass with slots=True should not have __dict__
        assert not hasattr(workflow_def, "__dict__")


class TestWorkflowParameterDataclass:
    """Test WorkflowParameter dataclass properties."""

    def test_workflow_parameter_is_frozen(self) -> None:
        """Test that WorkflowParameter is immutable (frozen=True)."""

        @workflow(name="test-workflow")
        def sample(arg1: str) -> None:
            yield None

        param = sample.__workflow_def__.parameters[0]

        # Attempt to modify should raise error (frozen dataclass)
        with pytest.raises((AttributeError, TypeError)):
            param.name = "modified"

    def test_workflow_parameter_has_slots(self) -> None:
        """Test that WorkflowParameter uses __slots__ for memory efficiency."""

        @workflow(name="test-workflow")
        def sample(arg1: str) -> None:
            yield None

        param = sample.__workflow_def__.parameters[0]

        # Dataclass with slots=True should not have __dict__
        assert not hasattr(param, "__dict__")
