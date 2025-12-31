"""Agent step handler for executing agent-based steps.

This module handles execution of AgentStepRecord steps.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

from maverick.dsl.context import WorkflowContext
from maverick.dsl.errors import ReferenceResolutionError
from maverick.dsl.serialization.executor import context as context_module
from maverick.dsl.serialization.executor.context_resolution import (
    resolve_context_builder,
)
from maverick.dsl.serialization.registry import ComponentRegistry
from maverick.dsl.serialization.schema import AgentStepRecord
from maverick.logging import get_logger
from maverick.models.implementation import ImplementerContext

logger = get_logger(__name__)


async def execute_agent_step(
    step: AgentStepRecord,
    resolved_inputs: dict[str, Any],
    context: WorkflowContext,
    registry: ComponentRegistry,
    config: Any = None,
) -> Any:
    """Execute an agent step.

    Args:
        step: AgentStepRecord containing agent reference and context.
        resolved_inputs: Resolved context values.
        context: WorkflowContext with inputs and step results.
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

    # Build context using shared resolution utility
    agent_context: Any = await resolve_context_builder(
        resolved_inputs=resolved_inputs,
        context=context,
        registry=registry,
        step_type="agent",
        step_name=step.agent,
    )

    # Convert dict to ImplementerContext for implementer agent
    if step.agent == "implementer" and isinstance(agent_context, dict):
        task_file_str = agent_context.get("task_file")
        # Handle case where expression evaluates to False instead of None
        if isinstance(task_file_str, bool):
            task_file_str = None
        task_file = Path(task_file_str) if task_file_str else None
        branch = agent_context.get("branch", "")
        phase_name = agent_context.get("phase_name")
        cwd_str = agent_context.get("cwd")
        cwd = Path(cwd_str) if cwd_str else Path.cwd()

        agent_context = ImplementerContext(
            task_file=task_file,
            phase_name=phase_name,
            branch=branch,
            cwd=cwd,
            skip_validation=agent_context.get("skip_validation", False),
            dry_run=agent_context.get("dry_run", False),
        )

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

    # Register rollback if specified
    if step.rollback:
        if not registry.actions.has(step.rollback):
            logger.warning(
                f"Rollback action '{step.rollback}' not found in registry "
                f"for agent step '{step.name}'. Skipping rollback registration."
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
