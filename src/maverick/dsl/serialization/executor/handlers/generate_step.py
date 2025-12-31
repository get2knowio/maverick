"""Generate step handler for executing text generation steps.

This module handles execution of GenerateStepRecord steps.
"""

from __future__ import annotations

import inspect
from typing import Any

from maverick.dsl.context import WorkflowContext
from maverick.dsl.errors import ReferenceResolutionError
from maverick.dsl.serialization.executor import context as context_module
from maverick.dsl.serialization.executor.context_resolution import (
    resolve_context_builder,
)
from maverick.dsl.serialization.registry import ComponentRegistry
from maverick.dsl.serialization.schema import GenerateStepRecord
from maverick.logging import get_logger

logger = get_logger(__name__)


async def execute_generate_step(
    step: GenerateStepRecord,
    resolved_inputs: dict[str, Any],
    context: WorkflowContext,
    registry: ComponentRegistry,
    config: Any = None,
) -> Any:
    """Execute a text generation step.

    Args:
        step: GenerateStepRecord containing generator reference and context.
        resolved_inputs: Resolved context values.
        context: WorkflowContext with inputs and step results.
        registry: Component registry for resolving generator.
        config: Optional configuration (unused).

    Returns:
        Generated text.

    Raises:
        ReferenceResolutionError: If generator not found in registry.
    """
    # Check if generator exists in registry
    if not registry.generators.has(step.generator):
        raise ReferenceResolutionError(
            reference_type="generator",
            reference_name=step.generator,
            available_names=registry.generators.list_names(),
        )

    # Build context using shared resolution utility
    generator_context: Any = await resolve_context_builder(
        resolved_inputs=resolved_inputs,
        context=context,
        registry=registry,
        step_type="generate",
        step_name=step.generator,
    )

    # Get generator class from registry and instantiate
    # Note: Registry stores generator classes (not instances)
    generator_class = registry.generators.get(step.generator)

    # Runtime validation: ensure it's callable
    if not callable(generator_class):
        raise TypeError(
            f"Generator '{step.generator}' is not callable. "
            f"Expected a class or callable, got {type(generator_class).__name__}"
        )

    try:
        generator_instance = generator_class()  # type: ignore[call-arg]
    except TypeError as e:
        logger.error(
            f"Failed to instantiate generator '{step.generator}': {e}. "
            f"Generator classes must be instantiable without arguments."
        )
        raise

    # Runtime validation: ensure generate method exists
    if not hasattr(generator_instance, "generate"):
        raise AttributeError(
            f"Generator instance '{step.generator}' does not have a 'generate' method"
        )

    # Call generate method (runtime validated above)
    result = generator_instance.generate(generator_context)

    # If result is a coroutine, await it
    if inspect.iscoroutine(result):
        result = await result

    # Register rollback if specified
    if step.rollback:
        if not registry.actions.has(step.rollback):
            logger.warning(
                f"Rollback action '{step.rollback}' not found in registry "
                f"for generate step '{step.name}'. Skipping rollback registration."
            )
        else:
            rollback_action = registry.actions.get(step.rollback)

            # Wrap action to match SerializationRollbackAction signature
            async def rollback_wrapper(
                exec_context: WorkflowContext,
            ) -> None:
                rollback_result = rollback_action(**resolved_inputs)
                if inspect.iscoroutine(rollback_result):
                    await rollback_result

            context_module.register_rollback(context, step.name, rollback_wrapper)

    return result
