"""Agent step handler for executing agent-based steps.

This module handles execution of AgentStepRecord steps with streaming events.
Implements T027 (AgentStreamChunk emission) and T028 (thinking indicator).
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

from maverick.dsl.context import WorkflowContext
from maverick.dsl.errors import ReferenceResolutionError
from maverick.dsl.events import AgentStreamChunk
from maverick.dsl.serialization.executor import context as context_module
from maverick.dsl.serialization.executor.context_resolution import (
    resolve_context_builder,
)
from maverick.dsl.serialization.executor.handlers.base import EventCallback
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
    event_callback: EventCallback | None = None,
) -> Any:
    """Execute an agent step with streaming event emission.

    Implements T027 (AgentStreamChunk emission during execution) and
    T028 (thinking indicator at agent start).

    Args:
        step: AgentStepRecord containing agent reference and context.
        resolved_inputs: Resolved context values.
        context: WorkflowContext with inputs and step results.
        registry: Component registry for resolving agent.
        config: Optional configuration (unused).

    Returns:
        Dictionary containing:
        - result: Agent execution result
        - events: List of AgentStreamChunk events emitted during execution

    Raises:
        ReferenceResolutionError: If agent not found in registry.
    """
    # Collect streaming events during execution
    emitted_events: list[AgentStreamChunk] = []

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
            "failed_to_instantiate_agent",
            agent=step.agent,
            error=str(e),
            hint="Agent classes must be instantiable without arguments",
        )
        raise

    # Runtime validation: ensure execute method exists
    if not hasattr(agent_instance, "execute"):
        raise AttributeError(
            f"Agent instance '{step.agent}' does not have an 'execute' method"
        )

    # Get agent name for events (use class name or configured name)
    agent_name = getattr(agent_instance, "name", step.agent)

    # T028: Emit thinking indicator at agent start
    thinking_event = AgentStreamChunk(
        step_name=step.name,
        agent_name=agent_name,
        text="",
        chunk_type="thinking",
    )
    if event_callback:
        await event_callback(thinking_event)
    else:
        emitted_events.append(thinking_event)

    logger.debug(
        "agent_step_starting",
        step_name=step.name,
        agent_name=agent_name,
    )

    try:
        # Call execute method (runtime validated above)
        result = agent_instance.execute(agent_context)

        # If result is a coroutine, await it
        if inspect.iscoroutine(result):
            result = await result

        # T027: Extract text output from result and emit OUTPUT chunk
        # The result may contain an 'output' attribute or be a structured result
        output_text = _extract_output_text(result)
        if output_text:
            output_event = AgentStreamChunk(
                step_name=step.name,
                agent_name=agent_name,
                text=output_text,
                chunk_type="output",
            )
            if event_callback:
                await event_callback(output_event)
            else:
                emitted_events.append(output_event)

    except Exception as e:
        # T027: Emit ERROR chunk on exception
        error_event = AgentStreamChunk(
            step_name=step.name,
            agent_name=agent_name,
            text=str(e),
            chunk_type="error",
        )
        if event_callback:
            await event_callback(error_event)
        else:
            emitted_events.append(error_event)
        logger.error(
            "agent_step_failed",
            step_name=step.name,
            error=str(e),
        )
        raise

    # Register rollback if specified
    if step.rollback:
        if not registry.actions.has(step.rollback):
            logger.warning(
                "rollback_action_not_found",
                rollback_action=step.rollback,
                step_name=step.name,
                hint="Skipping rollback registration",
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

    # Return result with events (matches loop handler pattern)
    return {"result": result, "events": emitted_events}


def _extract_output_text(result: Any) -> str:
    """Extract text output from an agent result.

    Attempts to extract meaningful text content from various agent result
    formats for streaming display.

    Args:
        result: The result returned by agent.execute().

    Returns:
        Extracted text content, or empty string if no text found.
    """
    if result is None:
        return ""

    # Check for AgentResult-style objects with 'output' attribute
    if hasattr(result, "output"):
        output = result.output
        if isinstance(output, str):
            return output
        if output is not None:
            return str(output)

    # Check for dict with 'output' key
    if isinstance(result, dict) and "output" in result:
        output = result["output"]
        if isinstance(output, str):
            return output
        if output is not None:
            return str(output)

    # Check for string result
    if isinstance(result, str):
        return result

    # Fallback: convert to string if meaningful
    result_str = str(result)
    # Avoid unhelpful string representations
    if result_str.startswith("<") and result_str.endswith(">"):
        return ""
    return result_str
