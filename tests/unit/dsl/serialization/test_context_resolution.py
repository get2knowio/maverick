"""Tests for context builder resolution utility.

This module tests the resolve_context_builder function that is shared between
agent and generate step handlers.
"""

from __future__ import annotations

import pytest

from maverick.dsl.context import WorkflowContext
from maverick.dsl.errors import ReferenceResolutionError
from maverick.dsl.results import StepResult
from maverick.dsl.serialization.executor.context_resolution import (
    resolve_context_builder,
)
from maverick.dsl.serialization.registry import ComponentRegistry
from maverick.dsl.types import StepType

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def registry():
    """Create a basic registry with context builders."""
    reg = ComponentRegistry()

    # Sync context builder
    def sync_builder(inputs: dict, step_results: dict) -> dict:
        """Synchronous context builder."""
        return {
            "sync": True,
            "inputs": inputs,
            "step_results": step_results,
            "computed": "sync_value",
        }

    # Async context builder
    async def async_builder(inputs: dict, step_results: dict) -> dict:
        """Asynchronous context builder."""
        return {
            "async": True,
            "inputs": inputs,
            "step_results": step_results,
            "computed": "async_value",
        }

    reg.context_builders.register("sync_builder", sync_builder)
    reg.context_builders.register("async_builder", async_builder)
    return reg


@pytest.fixture
def context_data():
    """Create sample workflow context data as a WorkflowContext."""
    return WorkflowContext(
        inputs={"task_file": "tasks.md", "branch_name": "feature/test"},
        results={
            "init": StepResult(
                name="init",
                step_type=StepType.PYTHON,
                success=True,
                output="initialized",
                duration_ms=0,
            ),
            "validate": StepResult(
                name="validate",
                step_type=StepType.PYTHON,
                success=True,
                output="passed",
                duration_ms=0,
            ),
        },
    )


# =============================================================================
# Tests for resolve_context_builder
# =============================================================================


class TestResolveContextBuilder:
    """Tests for resolve_context_builder function."""

    @pytest.mark.asyncio
    async def test_resolve_with_sync_context_builder(
        self, registry: ComponentRegistry, context_data: WorkflowContext
    ):
        """Test resolution with a synchronous context builder."""
        resolved_inputs = {"_context_builder": "sync_builder"}

        result = await resolve_context_builder(
            resolved_inputs=resolved_inputs,
            context=context_data,
            registry=registry,
            step_type="agent",
            step_name="test_agent",
        )

        assert result["sync"] is True
        assert result["computed"] == "sync_value"
        assert result["inputs"] == context_data.inputs
        # step_results is transformed to {"step_name": {"output": ...}}
        assert result["step_results"] == {
            "init": {"output": "initialized"},
            "validate": {"output": "passed"},
        }

    @pytest.mark.asyncio
    async def test_resolve_with_async_context_builder(
        self, registry: ComponentRegistry, context_data: WorkflowContext
    ):
        """Test resolution with an asynchronous context builder."""
        resolved_inputs = {"_context_builder": "async_builder"}

        result = await resolve_context_builder(
            resolved_inputs=resolved_inputs,
            context=context_data,
            registry=registry,
            step_type="generate",
            step_name="test_generator",
        )

        assert result["async"] is True
        assert result["computed"] == "async_value"
        assert result["inputs"] == context_data.inputs
        # step_results is transformed to {"step_name": {"output": ...}}
        assert result["step_results"] == {
            "init": {"output": "initialized"},
            "validate": {"output": "passed"},
        }

    @pytest.mark.asyncio
    async def test_resolve_with_missing_context_builder(
        self, registry: ComponentRegistry, context_data: WorkflowContext
    ):
        """Test resolution with a non-existent context builder raises error."""
        resolved_inputs = {"_context_builder": "nonexistent_builder"}

        with pytest.raises(ReferenceResolutionError) as exc_info:
            await resolve_context_builder(
                resolved_inputs=resolved_inputs,
                context=context_data,
                registry=registry,
                step_type="agent",
                step_name="test_agent",
            )

        error = exc_info.value
        assert error.reference_type == "context_builder"
        assert error.reference_name == "nonexistent_builder"
        assert "sync_builder" in error.available_names
        assert "async_builder" in error.available_names

    @pytest.mark.asyncio
    async def test_resolve_without_context_builder_with_inputs(
        self, registry: ComponentRegistry, context_data: WorkflowContext
    ):
        """Test resolution without context builder returns resolved_inputs."""
        resolved_inputs = {"file": "test.py", "mode": "review"}

        result = await resolve_context_builder(
            resolved_inputs=resolved_inputs,
            context=context_data,
            registry=registry,
            step_type="agent",
            step_name="test_agent",
        )

        # Should return resolved_inputs directly when no context builder
        assert result == {"file": "test.py", "mode": "review"}

    @pytest.mark.asyncio
    async def test_resolve_without_context_builder_empty_inputs(
        self, registry: ComponentRegistry, context_data: WorkflowContext
    ):
        """Test resolution without builder and empty inputs returns empty dict."""
        resolved_inputs = {}

        result = await resolve_context_builder(
            resolved_inputs=resolved_inputs,
            context=context_data,
            registry=registry,
            step_type="agent",
            step_name="test_agent",
        )

        # Should return empty dict when no context builder and no inputs
        assert result == {}

    @pytest.mark.asyncio
    async def test_resolve_with_failing_context_builder(
        self, registry: ComponentRegistry, context_data: WorkflowContext
    ):
        """Test resolution with a context builder that raises an exception."""

        def failing_builder(inputs: dict, step_results: dict) -> dict:
            """Context builder that raises an exception."""
            raise ValueError("Intentional failure in builder")

        registry.context_builders.register("failing_builder", failing_builder)
        resolved_inputs = {"_context_builder": "failing_builder"}

        with pytest.raises(ValueError) as exc_info:
            await resolve_context_builder(
                resolved_inputs=resolved_inputs,
                context=context_data,
                registry=registry,
                step_type="agent",
                step_name="test_agent",
            )

        assert "Intentional failure in builder" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_context_builder_receives_correct_arguments(
        self, registry: ComponentRegistry, context_data: WorkflowContext
    ):
        """Test context builder receives inputs and step_results args."""
        received_args = {}

        def capturing_builder(inputs: dict, step_results: dict) -> dict:
            """Context builder that captures its arguments."""
            received_args["inputs"] = inputs
            received_args["step_results"] = step_results
            return {"captured": True}

        registry.context_builders.register("capturing_builder", capturing_builder)
        resolved_inputs = {"_context_builder": "capturing_builder"}

        await resolve_context_builder(
            resolved_inputs=resolved_inputs,
            context=context_data,
            registry=registry,
            step_type="agent",
            step_name="test_agent",
        )

        # Verify the builder received the correct arguments
        assert received_args["inputs"] == context_data.inputs
        # step_results is transformed to {"step_name": {"output": ...}}
        assert received_args["step_results"] == {
            "init": {"output": "initialized"},
            "validate": {"output": "passed"},
        }

    @pytest.mark.asyncio
    async def test_resolve_with_empty_results_in_context(
        self, registry: ComponentRegistry
    ):
        """Test resolution when context has empty results."""
        context_data = WorkflowContext(
            inputs={"task_file": "tasks.md"},
            results={},
        )

        def builder(inputs: dict, step_results: dict) -> dict:
            return {"inputs_was": inputs, "steps_was": step_results}

        registry.context_builders.register("builder", builder)
        resolved_inputs = {"_context_builder": "builder"}

        result = await resolve_context_builder(
            resolved_inputs=resolved_inputs,
            context=context_data,
            registry=registry,
            step_type="agent",
            step_name="test_agent",
        )

        # Should pass inputs and empty dict for step_results
        assert result["inputs_was"] == {"task_file": "tasks.md"}
        assert result["steps_was"] == {}

    @pytest.mark.asyncio
    async def test_resolve_with_empty_inputs_in_context(
        self, registry: ComponentRegistry
    ):
        """Test resolution when context has empty inputs."""
        context_data = WorkflowContext(
            inputs={},
            results={
                "init": StepResult(
                    name="init",
                    step_type=StepType.PYTHON,
                    success=True,
                    output="done",
                    duration_ms=0,
                ),
            },
        )

        def builder(inputs: dict, step_results: dict) -> dict:
            return {"inputs_was": inputs, "steps_was": step_results}

        registry.context_builders.register("builder", builder)
        resolved_inputs = {"_context_builder": "builder"}

        result = await resolve_context_builder(
            resolved_inputs=resolved_inputs,
            context=context_data,
            registry=registry,
            step_type="agent",
            step_name="test_agent",
        )

        # Should pass empty dict for inputs
        assert result["inputs_was"] == {}
        assert result["steps_was"] == {"init": {"output": "done"}}

    @pytest.mark.asyncio
    async def test_error_raised_for_missing_context_builder(
        self, registry: ComponentRegistry, context_data: WorkflowContext
    ):
        """Test that ReferenceResolutionError is raised for missing context builder."""
        resolved_inputs = {"_context_builder": "nonexistent"}

        # Test with agent step
        with pytest.raises(ReferenceResolutionError) as exc_info:
            await resolve_context_builder(
                resolved_inputs=resolved_inputs,
                context=context_data,
                registry=registry,
                step_type="agent",
                step_name="my_agent",
            )

        # Verify error contains context builder information
        error = exc_info.value
        assert error.reference_type == "context_builder"
        assert error.reference_name == "nonexistent"

        # Test with generate step
        with pytest.raises(ReferenceResolutionError) as exc_info:
            await resolve_context_builder(
                resolved_inputs=resolved_inputs,
                context=context_data,
                registry=registry,
                step_type="generate",
                step_name="my_generator",
            )

        # Verify error contains context builder information
        error = exc_info.value
        assert error.reference_type == "context_builder"
        assert error.reference_name == "nonexistent"
