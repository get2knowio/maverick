"""Agent step handler for executing agent-based steps.

This module handles execution of AgentStepRecord steps with streaming events.
Implements T027 (AgentStreamChunk emission) and T028 (thinking indicator).
"""

from __future__ import annotations

import asyncio
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
from maverick.dsl.serialization.executor.handlers.models import HandlerOutput
from maverick.dsl.serialization.registry import ComponentRegistry
from maverick.dsl.serialization.schema import AgentStepRecord
from maverick.exceptions import ConfigError
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
        HandlerOutput containing:
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
        task_description = agent_context.get("task_description")
        branch = agent_context.get("branch", "")
        if not branch:
            try:
                proc = await asyncio.create_subprocess_exec(
                    "git",
                    "rev-parse",
                    "--abbrev-ref",
                    "HEAD",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await proc.communicate()
                if proc.returncode == 0:
                    branch = stdout.decode().strip()
            except OSError:
                pass
        phase_name = agent_context.get("phase_name")
        cwd_str = agent_context.get("cwd")
        cwd = Path(cwd_str) if cwd_str else Path.cwd()

        agent_context = ImplementerContext(
            task_file=task_file,
            task_description=task_description,
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

    # Build kwargs for agent construction
    agent_kwargs: dict[str, Any] = {}

    # Inject validation commands from maverick.yaml as prompt guidance
    if step.agent == "implementer":
        try:
            from maverick.config import load_config

            maverick_config = load_config()
            agent_kwargs["validation_commands"] = _extract_validation_commands(
                maverick_config.validation,
            )
        except (ImportError, ModuleNotFoundError) as e:
            logger.debug(
                "validation_config_unavailable",
                error=str(e),
                reason="module_not_found",
            )
        except ConfigError as e:
            logger.debug(
                "validation_config_failed",
                error=str(e),
                reason="config_error",
            )

    try:
        agent_instance = agent_class(**agent_kwargs)
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

    # Set up stream callback for real-time output streaming
    # Track whether any output was actually streamed to avoid duplicate emission
    has_event_callback = event_callback is not None
    has_stream_attr = hasattr(agent_instance, "stream_callback")
    output_was_streamed = False  # Track if streaming actually occurred
    last_was_tool_call = False  # Track output type for proper line breaks
    has_emitted_text = False  # Track if non-tool text was emitted
    logger.info(
        "stream_callback_setup",
        has_event_callback=has_event_callback,
        has_stream_attr=has_stream_attr,
        agent=step.agent,
    )
    if has_event_callback and has_stream_attr:

        async def stream_text_callback(text: str) -> None:
            """Forward agent output to event queue as AgentStreamChunk.

            Handles line break transitions between tool calls and text output:
            - Tool calls use dim └ prefix (from _format_tool_call)
            - First text after tool call gets extra newline prefix
            """
            nonlocal output_was_streamed, last_was_tool_call, has_emitted_text
            output_was_streamed = True  # Mark that we actually streamed output

            # Detect if this is a tool call (starts with └ or [dim]└)
            stripped = text.lstrip("\n")
            is_tool_call = stripped.startswith("\u2514") or stripped.startswith(
                "[dim]\u2514"
            )

            # Add extra newlines when switching between tool output and text
            # This creates visual separation (blank line) between modes
            output_text = text
            if last_was_tool_call and not is_tool_call and text.strip():
                output_text = "\n\n" + text

            # Ensure tool call starts on a new line after streamed text
            if has_emitted_text and not last_was_tool_call and is_tool_call:
                output_text = "\n" + output_text

            last_was_tool_call = is_tool_call

            # Track non-tool text emission
            if not is_tool_call and text.strip():
                has_emitted_text = True

            chunk_event = AgentStreamChunk(
                step_name=step.name,
                agent_name=agent_name,
                text=output_text,
                chunk_type="output",
            )
            # event_callback is guaranteed non-None here (checked at line 141)
            assert event_callback is not None  # for mypy
            await event_callback(chunk_event)

        agent_instance.stream_callback = stream_text_callback

    # T028: Emit thinking indicator at agent start
    thinking_event = AgentStreamChunk(
        step_name=step.name,
        agent_name=agent_name,
        text="Agent is working...",
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
        # Skip if output was already streamed in real-time to avoid duplication
        # Only emit the final output when streaming didn't occur
        if not output_was_streamed:
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

    # Return result with events using typed HandlerOutput
    return HandlerOutput(result=result, events=emitted_events)


def _extract_validation_commands(
    validation: Any,
) -> dict[str, list[str]]:
    """Extract validation commands from a ValidationConfig for prompt injection.

    Args:
        validation: A ValidationConfig instance.

    Returns:
        Dict mapping command type (e.g. "test_cmd") to argv list.
    """
    commands: dict[str, list[str]] = {}
    for key in ("sync_cmd", "format_cmd", "lint_cmd", "typecheck_cmd", "test_cmd"):
        value = getattr(validation, key, None)
        if value:
            commands[key] = list(value)
    return commands


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

    # Check for AgentResult-style objects with non-empty 'output' attribute
    if hasattr(result, "output"):
        output = result.output
        if isinstance(output, str) and output:
            return output
        if output is not None and not isinstance(output, str):
            return str(output)

    # Check for dict with non-empty 'output' key
    if isinstance(result, dict) and "output" in result:
        output = result["output"]
        if isinstance(output, str) and output:
            return output
        if output is not None and not isinstance(output, str):
            return str(output)

    # Check for ImplementationResult-style objects and generate summary
    if hasattr(result, "tasks_completed") and hasattr(result, "success"):
        parts = []
        completed = getattr(result, "tasks_completed", 0)
        failed = getattr(result, "tasks_failed", 0)
        skipped = getattr(result, "tasks_skipped", 0)
        success = getattr(result, "success", False)

        status = "Completed" if success else "Failed"
        parts.append(f"{status}: {completed} task(s) completed")
        if failed > 0:
            parts.append(f"{failed} failed")
        if skipped > 0:
            parts.append(f"{skipped} skipped")

        # Add file change info if available
        files_changed = getattr(result, "files_changed", [])
        if files_changed:
            parts.append(f"{len(files_changed)} file(s) modified")

        return ", ".join(parts)

    # Check for string result
    if isinstance(result, str):
        return result

    # Fallback: convert to string if meaningful
    result_str = str(result)
    # Avoid unhelpful string representations
    if result_str.startswith("<") and result_str.endswith(">"):
        return ""
    return result_str
