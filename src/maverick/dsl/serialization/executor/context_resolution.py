"""Context builder resolution utility for workflow execution.

This module provides shared utilities for resolving and executing context builders
during workflow step execution. Context builders transform workflow inputs and
step results into the appropriate context format for agents and generators.
"""

from __future__ import annotations

import inspect
from typing import Any

from maverick.dsl.errors import ReferenceResolutionError
from maverick.dsl.serialization.registry import ComponentRegistry
from maverick.logging import get_logger

logger = get_logger(__name__)


async def resolve_context_builder(
    resolved_inputs: dict[str, Any],
    context: Any,  # WorkflowContext but avoiding circular import
    registry: ComponentRegistry,
    step_type: str,
    step_name: str,
) -> Any:
    """Resolve and execute a context builder if specified in inputs.

    This function checks if the resolved_inputs contains a "_context_builder" key.
    If present, it looks up the context builder in the registry, executes it with
    workflow inputs and step results, and returns the result. If not present,
    it returns the context updated with resolved_inputs.

    Context builders are functions that transform workflow state into the appropriate
    context format for a specific agent or generator. They receive two arguments:
    - inputs: The workflow input parameters (from context.inputs)
    - step_results: Dictionary of step outputs (converted from context.results)

    Args:
        resolved_inputs: Step inputs (may contain "_context_builder" key).
        context: WorkflowContext with inputs and step results.
        registry: Component registry containing context builders.
        step_type: Type of step requesting resolution (e.g., "agent", "generate").
        step_name: Name of the step requesting resolution (for error messages).

    Returns:
        Context builder result if "_context_builder" was specified,
        otherwise returns context updated with resolved_inputs.

    Raises:
        ReferenceResolutionError: If context builder name is not found in registry.
        Exception: If context builder execution fails.

    Examples:
        ```python
        # With context builder
        resolved_inputs = {"_context_builder": "implementer_context"}
        result = await resolve_context_builder(
            resolved_inputs, context, registry, "agent", "implementer"
        )
        # Returns: ImplementerContext instance from builder

        # Without context builder
        resolved_inputs = {"file": "test.py", "mode": "review"}
        result = await resolve_context_builder(
            resolved_inputs, context, registry, "agent", "reviewer"
        )
        # Returns: dict with resolved_inputs
        ```
    """
    # If context builder is specified, resolve and execute it
    if "_context_builder" in resolved_inputs:
        context_builder_name = resolved_inputs["_context_builder"]
        try:
            if not registry.context_builders.has(context_builder_name):
                raise ReferenceResolutionError(
                    reference_type="context_builder",
                    reference_name=context_builder_name,
                    available_names=registry.context_builders.list_names(),
                )
            context_builder = registry.context_builders.get(context_builder_name)
            # Context builders expect (inputs, step_results) as separate args
            # Convert WorkflowContext.results to the step_results dict format
            inputs = context.inputs
            step_results = {}
            for step_name_key, step_result in context.results.items():
                step_results[step_name_key] = {"output": step_result.output}

            builder_result = context_builder(inputs, step_results)
            # If context builder is async, await it
            if inspect.iscoroutine(builder_result):
                return await builder_result
            else:
                return builder_result
        except ReferenceResolutionError as e:
            logger.error(
                f"Context builder '{context_builder_name}' not found "
                f"for {step_type} step '{step_name}': {e}"
            )
            raise
        except Exception as e:
            logger.error(
                f"Error executing context builder '{context_builder_name}' "
                f"for {step_type} step '{step_name}': {e}"
            )
            raise
    # If no context builder, return resolved inputs as a dict
    elif resolved_inputs:
        return resolved_inputs
    # No context builder and no resolved inputs - return empty dict
    else:
        return {}
