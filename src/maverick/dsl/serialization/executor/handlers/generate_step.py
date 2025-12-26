"""Generate step handler for executing text generation steps.

This module handles execution of GenerateStepRecord steps.
"""

from __future__ import annotations

import inspect
from typing import Any

from maverick.dsl.serialization.errors import ReferenceResolutionError
from maverick.dsl.serialization.registry import ComponentRegistry
from maverick.dsl.serialization.schema import GenerateStepRecord
from maverick.logging import get_logger

logger = get_logger(__name__)


async def execute_generate_step(
    step: GenerateStepRecord,
    resolved_inputs: dict[str, Any],
    context: dict[str, Any],
    registry: ComponentRegistry,
    config: Any = None,
) -> Any:
    """Execute a text generation step.

    Args:
        step: GenerateStepRecord containing generator reference and context.
        resolved_inputs: Resolved context values.
        context: Execution context.
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

    # Build context
    generator_context: Any = context.copy()

    # If context is a string (context builder name), resolve it
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
            builder_result = context_builder(generator_context)
            # If context builder is async, await it
            if inspect.iscoroutine(builder_result):
                generator_context = await builder_result
            else:
                generator_context = builder_result
        except ReferenceResolutionError as e:
            logger.error(
                f"Context builder '{context_builder_name}' not found "
                f"for generate step '{step.generator}': {e}"
            )
            raise
        except Exception as e:
            logger.error(
                f"Error executing context builder '{context_builder_name}' "
                f"for generate step '{step.generator}': {e}"
            )
            raise
    elif resolved_inputs:
        # Context is a dict, use resolved inputs directly
        generator_context.update(resolved_inputs)

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

    return result
