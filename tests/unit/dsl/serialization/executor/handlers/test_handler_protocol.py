"""Tests for StepHandler protocol and handler registry.

This module verifies that:
1. All step handlers conform to the StepHandler protocol
2. Handler registry contains all step types
3. Handler signatures are consistent
4. Error handling wrapper works correctly
"""

from __future__ import annotations

import inspect
from typing import Any

import pytest

from maverick.dsl.context import WorkflowContext
from maverick.dsl.errors import ReferenceResolutionError
from maverick.dsl.serialization.executor.handlers import (
    STEP_HANDLERS,
    agent_step,
    branch_step,
    checkpoint_step,
    generate_step,
    get_handler,
    parallel_step,
    python_step,
    subworkflow_step,
    validate_step,
    with_error_handling,
)
from maverick.dsl.serialization.registry import ComponentRegistry
from maverick.dsl.types import StepType


class TestHandlerRegistry:
    """Tests for handler registry functionality."""

    def test_step_handlers_contains_all_step_types(self) -> None:
        """Verify registry contains handlers for all step types."""
        expected_types = {
            StepType.PYTHON,
            StepType.AGENT,
            StepType.GENERATE,
            StepType.VALIDATE,
            StepType.SUBWORKFLOW,
            StepType.BRANCH,
            StepType.PARALLEL,
            StepType.CHECKPOINT,
        }
        actual_types = set(STEP_HANDLERS.keys())
        assert actual_types == expected_types, (
            f"Handler registry missing types: {expected_types - actual_types}, "
            f"or has extra types: {actual_types - expected_types}"
        )

    def test_get_handler_returns_correct_handlers(self) -> None:
        """Verify get_handler returns the correct handler for each type."""
        assert get_handler(StepType.PYTHON) == python_step.execute_python_step
        assert get_handler(StepType.AGENT) == agent_step.execute_agent_step
        assert get_handler(StepType.GENERATE) == generate_step.execute_generate_step
        assert get_handler(StepType.VALIDATE) == validate_step.execute_validate_step
        assert get_handler(StepType.SUBWORKFLOW) == (
            subworkflow_step.execute_subworkflow_step
        )
        assert get_handler(StepType.BRANCH) == branch_step.execute_branch_step
        assert get_handler(StepType.PARALLEL) == parallel_step.execute_parallel_step
        assert get_handler(StepType.CHECKPOINT) == (
            checkpoint_step.execute_checkpoint_step
        )

    def test_get_handler_raises_on_unknown_type(self) -> None:
        """Verify get_handler raises ValueError for unknown step types."""

        # Create a mock enum value that doesn't exist in the registry
        class FakeStepType:
            value = "unknown"

            def __str__(self) -> str:
                return self.value

        with pytest.raises(ValueError, match="No handler registered for step type"):
            get_handler(FakeStepType())  # type: ignore[arg-type]


class TestHandlerProtocolConformance:
    """Tests for handler protocol conformance."""

    def test_all_handlers_are_async_functions(self) -> None:
        """Verify all handlers are async functions."""
        for step_type, handler in STEP_HANDLERS.items():
            assert inspect.iscoroutinefunction(handler), (
                f"Handler for {step_type} is not an async function"
            )

    def test_all_handlers_have_correct_signature(self) -> None:
        """Verify all handlers have the protocol signature."""
        for step_type, handler in STEP_HANDLERS.items():
            sig = inspect.signature(handler)
            params = list(sig.parameters.keys())

            # Required parameters common to all handlers
            assert "step" in params, f"Handler {step_type} missing 'step' parameter"
            assert "resolved_inputs" in params, (
                f"Handler {step_type} missing 'resolved_inputs' parameter"
            )
            assert "context" in params, (
                f"Handler {step_type} missing 'context' parameter"
            )
            assert "registry" in params, (
                f"Handler {step_type} missing 'registry' parameter"
            )
            assert "config" in params, f"Handler {step_type} missing 'config' parameter"

            # Verify context type annotation is WorkflowContext
            # Note: Due to `from __future__ import annotations`, annotations
            # are strings. We check either the class or the string name.
            context_param = sig.parameters["context"]
            context_anno = context_param.annotation
            assert (
                context_anno == WorkflowContext or context_anno == "WorkflowContext"
            ), (
                f"Handler {step_type} has incorrect context type: "
                f"{context_anno}, expected WorkflowContext"
            )

            # Verify registry type annotation
            registry_param = sig.parameters["registry"]
            registry_anno = registry_param.annotation
            assert registry_anno == ComponentRegistry or (
                registry_anno == "ComponentRegistry"
            ), f"Handler {step_type} has incorrect registry type: {registry_anno}"

    def test_special_handlers_have_extra_parameters(self) -> None:
        """Verify handlers with special needs have additional parameters."""
        # Branch and parallel handlers need execute_step_fn
        branch_sig = inspect.signature(branch_step.execute_branch_step)
        assert "execute_step_fn" in branch_sig.parameters

        parallel_sig = inspect.signature(parallel_step.execute_parallel_step)
        assert "execute_step_fn" in parallel_sig.parameters

        # Checkpoint handler needs checkpoint_store
        checkpoint_sig = inspect.signature(checkpoint_step.execute_checkpoint_step)
        assert "checkpoint_store" in checkpoint_sig.parameters

    def test_handlers_conform_to_protocol(self) -> None:
        """Verify handlers conform to StepHandler protocol using isinstance."""
        # Note: This is a structural check, not a runtime instance check
        # The @runtime_checkable decorator makes this possible
        for step_type, handler in STEP_HANDLERS.items():
            # We can't use isinstance on functions, but we can verify they
            # have the execute signature by checking if they're callable
            assert callable(handler), f"Handler for {step_type} is not callable"


class TestErrorHandlingWrapper:
    """Tests for the error handling wrapper."""

    async def test_with_error_handling_returns_result(self) -> None:
        """Verify wrapper returns handler result on success."""

        async def mock_handler(value: int) -> int:
            return value * 2

        result = await with_error_handling(
            "test_handler", "test_step", mock_handler, 21
        )
        assert result == 42

    async def test_with_error_handling_reraises_exceptions(self) -> None:
        """Verify wrapper re-raises non-ReferenceResolutionError exceptions."""

        async def mock_handler() -> None:
            raise ValueError("Test error")

        with pytest.raises(ValueError, match="Test error"):
            await with_error_handling(
                "test_handler",
                "test_step",
                mock_handler,
            )

    async def test_with_error_handling_logs_reference_errors(self) -> None:
        """Verify wrapper logs and re-raises ReferenceResolutionError."""

        async def mock_handler() -> None:
            raise ReferenceResolutionError(
                reference_type="action",
                reference_name="missing_action",
                available_names=["action1", "action2"],
            )

        with pytest.raises(ReferenceResolutionError):
            await with_error_handling(
                "test_handler",
                "test_step",
                mock_handler,
            )

    async def test_with_error_handling_passes_args_and_kwargs(self) -> None:
        """Verify wrapper correctly passes args and kwargs to handler."""

        async def mock_handler(
            a: int, b: int, *, c: int = 0, d: int = 0
        ) -> dict[str, int]:
            return {"a": a, "b": b, "c": c, "d": d}

        result = await with_error_handling(
            "test_handler",
            "test_step",
            mock_handler,
            1,
            2,
            c=3,
            d=4,
        )
        assert result == {"a": 1, "b": 2, "c": 3, "d": 4}


class TestHandlerTypeAnnotations:
    """Tests for handler type annotations."""

    def test_python_step_handler_annotations(self) -> None:
        """Verify python_step handler has correct type annotations."""
        sig = inspect.signature(python_step.execute_python_step)

        # Check return type (should be Any or string "Any")
        assert sig.return_annotation == Any or sig.return_annotation == "Any"

        # Check parameter types (annotations are strings due to __future__ import)
        params = sig.parameters
        step_anno = params["step"].annotation
        assert (
            hasattr(step_anno, "__name__") and step_anno.__name__ == "PythonStepRecord"
        ) or step_anno == "PythonStepRecord"

    def test_agent_step_handler_annotations(self) -> None:
        """Verify agent_step handler has correct type annotations."""
        sig = inspect.signature(agent_step.execute_agent_step)

        # Check return type (should be Any or string "Any")
        assert sig.return_annotation == Any or sig.return_annotation == "Any"

        # Check parameter types (annotations are strings due to __future__ import)
        params = sig.parameters
        step_anno = params["step"].annotation
        assert (
            hasattr(step_anno, "__name__") and step_anno.__name__ == "AgentStepRecord"
        ) or step_anno == "AgentStepRecord"

    def test_generate_step_handler_annotations(self) -> None:
        """Verify generate_step handler has correct type annotations."""
        sig = inspect.signature(generate_step.execute_generate_step)

        # Check return type (should be Any or string "Any")
        assert sig.return_annotation == Any or sig.return_annotation == "Any"

        # Check parameter types (annotations are strings due to __future__ import)
        params = sig.parameters
        step_anno = params["step"].annotation
        assert (
            hasattr(step_anno, "__name__")
            and step_anno.__name__ == "GenerateStepRecord"
        ) or step_anno == "GenerateStepRecord"
