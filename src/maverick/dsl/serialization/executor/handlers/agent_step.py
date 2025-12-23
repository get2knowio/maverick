"""Agent step handler for executing agent-based steps.

This module handles execution of AgentStepRecord steps.
"""

from __future__ import annotations

import inspect
import logging
from typing import Any

from maverick.dsl.serialization.errors import ReferenceResolutionError
from maverick.dsl.serialization.registry import ComponentRegistry
from maverick.dsl.serialization.schema import AgentStepRecord

logger = logging.getLogger(__name__)


async def execute_agent_step(
    step: AgentStepRecord,
    resolved_inputs: dict[str, Any],
    context: dict[str, Any],
    registry: ComponentRegistry,
    config: Any = None,
) -> Any:
    """Execute an agent step.

    Args:
        step: AgentStepRecord containing agent reference and context.
        resolved_inputs: Resolved context values.
        context: Execution context.
        registry: Component registry for resolving agent.
        config: Optional configuration (unused).

    Returns:
        Agent execution result.

    Raises:
        ReferenceResolutionError: If agent not found in registry.
    """
    # Check if agent exists in the agents registry
    if not registry.agents.has(step.agent):
        raise ReferenceResolutionError(
            reference_type="agent",
            reference_name=step.agent,
            available_names=registry.agents.list_names(),
        )

    # Build context
    agent_context: Any = context.copy()

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
            builder_result = context_builder(agent_context)
            # If context builder is async, await it
            if inspect.iscoroutine(builder_result):
                agent_context = await builder_result
            else:
                agent_context = builder_result
        except ReferenceResolutionError as e:
            logger.error(
                f"Context builder '{context_builder_name}' not found "
                f"for agent step '{step.agent}': {e}"
            )
            raise
        except Exception as e:
            logger.error(
                f"Error executing context builder '{context_builder_name}' "
                f"for agent step '{step.agent}': {e}"
            )
            raise
    elif resolved_inputs:
        # Context is a dict, use resolved inputs directly
        agent_context.update(resolved_inputs)

    # Get agent class from registry and instantiate
    # Note: Registry stores agent classes (not instances)
    agent_class = registry.agents.get(step.agent)

    # Runtime validation: ensure it's callable
    if not callable(agent_class):
        raise TypeError(
            f"Agent '{step.agent}' is not callable. "
            f"Expected a class or callable, got {type(agent_class).__name__}"
        )

    try:
        agent_instance = agent_class()  # type: ignore[call-arg]
    except TypeError as e:
        logger.error(
            f"Failed to instantiate agent '{step.agent}': {e}. "
            f"Agent classes must be instantiable without arguments."
        )
        raise

    # Runtime validation: ensure execute method exists
    if not hasattr(agent_instance, "execute"):
        raise AttributeError(
            f"Agent instance '{step.agent}' does not have an 'execute' method"
        )

    # Call execute method (runtime validated above)
    result = agent_instance.execute(agent_context)

    # If result is a coroutine, await it
    if inspect.iscoroutine(result):
        result = await result

    return result
