"""ClaudeStepExecutor — Claude Agent SDK adapter for StepExecutor protocol.

This module wraps MaverickAgent subclasses to satisfy the StepExecutor protocol,
preserving all existing streaming, retry, timeout, and error-wrapping behavior.
"""

from __future__ import annotations

import asyncio
import inspect
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError
from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential

from maverick.dsl.errors import ReferenceResolutionError
from maverick.dsl.events import AgentStreamChunk
from maverick.dsl.executor.config import (
    DEFAULT_EXECUTOR_CONFIG,
    IMPLEMENTER_AGENT_NAME,
    RetryPolicy,
    StepExecutorConfig,
)
from maverick.dsl.executor.errors import OutputSchemaValidationError
from maverick.dsl.executor.protocol import EventCallback
from maverick.dsl.executor.result import ExecutorResult, UsageMetadata
from maverick.dsl.serialization.registry import ComponentRegistry
from maverick.logging import get_logger


class ClaudeStepExecutor:
    """Claude Agent SDK adapter implementing StepExecutor protocol.

    Wraps MaverickAgent subclasses, preserving streaming, timeout,
    retry, and error-wrapping behavior. Agent classes are looked up
    from the ComponentRegistry provided at construction time.

    Lifecycle:
        Created once per workflow run. Reused for all agent steps.

    Args:
        registry: Component registry for agent class lookup.
    """

    def __init__(self, registry: ComponentRegistry) -> None:
        self._registry = registry
        self._logger = get_logger(__name__)

    async def execute(
        self,
        *,
        step_name: str,
        agent_name: str,
        prompt: Any,
        instructions: str | None = None,
        allowed_tools: list[str] | None = None,
        cwd: Path | None = None,
        output_schema: type[BaseModel] | None = None,
        config: StepExecutorConfig | None = None,
        event_callback: EventCallback | None = None,
    ) -> ExecutorResult:
        """Execute an agent step and return a typed ExecutorResult.

        Args:
            step_name: DSL step name for observability logging.
            agent_name: Registered agent name (registry key).
            prompt: Provider-specific context/prompt (ImplementerContext, dict, etc.).
            instructions: Optional system instructions override
                (unused by current agents).
            allowed_tools: Optional tool list override (unused by current agents).
            cwd: Working directory (unused directly; passed through prompt context).
            output_schema: Optional Pydantic BaseModel subclass for output validation.
            config: Per-step execution configuration (timeout, retry, model overrides).
                None = use DEFAULT_EXECUTOR_CONFIG.
            event_callback: Async callback for streaming events in real-time.

        Returns:
            ExecutorResult with output, success=True, usage metadata, and events.

        Raises:
            ReferenceResolutionError: Agent not found in registry.
            OutputSchemaValidationError: Agent output failed output_schema validation.
            Exception: Any exception from agent execution is re-raised after logging.
        """
        effective_config = config if config is not None else DEFAULT_EXECUTOR_CONFIG
        emitted_events: list[AgentStreamChunk] = []

        self._logger.info(
            "executor.step_start",
            step_name=step_name,
            agent_name=agent_name,
            config=effective_config.model_dump(exclude_none=True),
        )
        start_time = time.monotonic()

        # Agent class lookup (fast fail before any expensive operations)
        if not self._registry.agents.has(agent_name):
            raise ReferenceResolutionError(
                reference_type="agent",
                reference_name=agent_name,
                available_names=self._registry.agents.list_names(),
            )

        agent_class = self._registry.agents.get(agent_name)

        # Runtime validation: ensure agent is callable
        if not callable(agent_class):
            raise TypeError(
                f"Agent '{agent_name}' is not callable. "
                f"Expected a class or callable, got {type(agent_class).__name__}"
            )

        # Build constructor kwargs
        agent_kwargs = self._build_agent_kwargs(agent_name)

        try:
            agent_instance = agent_class(**agent_kwargs)
        except TypeError as e:
            self._logger.error(
                "failed_to_instantiate_agent",
                agent=agent_name,
                error=str(e),
                hint="Agent classes must be instantiable without arguments",
            )
            raise

        # Get agent display name (used in events)
        display_name = getattr(agent_instance, "name", agent_name)

        # Set up stream callback for real-time output streaming
        output_was_streamed = False
        last_was_tool_call = False
        has_emitted_text = False
        has_stream_attr = hasattr(agent_instance, "stream_callback")

        self._logger.info(
            "stream_callback_setup",
            has_event_callback=event_callback is not None,
            has_stream_attr=has_stream_attr,
            agent=agent_name,
        )

        if has_stream_attr:

            async def stream_text_callback(text: str) -> None:
                """Forward agent output to event queue as AgentStreamChunk.

                Handles line break transitions between tool calls and text output:
                - Tool calls use dim └ prefix (from _format_tool_call)
                - First text after tool call gets extra newline prefix
                """
                nonlocal output_was_streamed, last_was_tool_call, has_emitted_text
                output_was_streamed = True

                # Detect if this is a tool call (starts with └ or [dim]└)
                stripped = text.lstrip("\n")
                is_tool_call = stripped.startswith("\u2514") or stripped.startswith(
                    "[dim]\u2514"
                )

                # Add extra newlines when switching between tool output and text
                output_text = text
                if last_was_tool_call and not is_tool_call and text.strip():
                    output_text = "\n" + text

                # Ensure tool call starts on a new line after streamed text
                if has_emitted_text and not last_was_tool_call and is_tool_call:
                    output_text = "\n" + output_text

                last_was_tool_call = is_tool_call

                # Track non-tool text emission
                if not is_tool_call and text.strip():
                    has_emitted_text = True

                chunk_event = AgentStreamChunk(
                    step_name=step_name,
                    agent_name=display_name,
                    text=output_text,
                    chunk_type="output",
                )
                emitted_events.append(chunk_event)
                if event_callback:
                    await event_callback(chunk_event)

            agent_instance.stream_callback = stream_text_callback

        # T028: Emit thinking indicator at agent start
        thinking_event = AgentStreamChunk(
            step_name=step_name,
            agent_name=display_name,
            text="Agent is working...",
            chunk_type="thinking",
        )
        emitted_events.append(thinking_event)
        if event_callback:
            await event_callback(thinking_event)

        self._logger.debug(
            "agent_step_starting",
            step_name=step_name,
            agent_name=display_name,
        )

        # Mutable counter so _execute_with_retry_and_timeout can
        # report which attempt failed (NFR-001 observability).
        attempt_tracker: list[int] = [1]

        try:
            result = await self._execute_with_retry_and_timeout(
                agent_instance,
                prompt,
                effective_config,
                attempt_tracker=attempt_tracker,
            )

            # T027: Extract text output from result and emit OUTPUT chunk
            # Skip if output was already streamed in real-time to avoid duplication
            if not output_was_streamed:
                output_text = _extract_output_text(result)
                if output_text:
                    output_event = AgentStreamChunk(
                        step_name=step_name,
                        agent_name=display_name,
                        text=output_text,
                        chunk_type="output",
                    )
                    emitted_events.append(output_event)
                    if event_callback:
                        await event_callback(output_event)

        except Exception as e:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            # T027: Emit ERROR chunk on exception
            error_event = AgentStreamChunk(
                step_name=step_name,
                agent_name=display_name,
                text=str(e),
                chunk_type="error",
            )
            emitted_events.append(error_event)
            if event_callback:
                await event_callback(error_event)

            self._logger.error(
                "executor.step_error",
                step_name=step_name,
                agent_name=agent_name,
                error_type=type(e).__name__,
                error=str(e),
                duration_ms=duration_ms,
                attempt_number=attempt_tracker[0],
            )
            raise

        # Output schema validation (FR-007)
        if output_schema is not None:
            try:
                result = output_schema.model_validate(result)
            except ValidationError as e:
                raise OutputSchemaValidationError(step_name, output_schema, e) from e

        # Extract usage metadata from result (duck-typed)
        usage = self._extract_usage(result)

        duration_ms = int((time.monotonic() - start_time) * 1000)
        self._logger.info(
            "executor.step_complete",
            step_name=step_name,
            agent_name=agent_name,
            duration_ms=duration_ms,
            usage=usage.to_dict() if usage else None,
            success=True,
        )

        return ExecutorResult(
            output=result,
            success=True,
            usage=usage,
            events=tuple(emitted_events),
        )

    async def _execute_with_retry_and_timeout(
        self,
        agent: Any,
        prompt: Any,
        config: StepExecutorConfig,
        *,
        attempt_tracker: list[int] | None = None,
    ) -> Any:
        """Execute agent with optional retry and timeout.

        Args:
            agent: Instantiated agent with execute() method.
            prompt: Context to pass to agent.execute().
            config: Execution config (timeout and retry_policy).
            attempt_tracker: Mutable ``[int]`` updated with
                the current attempt number for observability.

        Returns:
            Agent execution result.

        Raises:
            asyncio.TimeoutError: If execution exceeds timeout.
            tenacity.RetryError: If max_attempts exceeded.
        """

        async def _call_once() -> Any:
            result = agent.execute(prompt)
            if inspect.iscoroutine(result):
                result = await result
            return result

        # Resolve effective retry policy: max_retries (preferred) takes
        # precedence over the legacy retry_policy field.  The two are
        # mutually exclusive at the StepConfig validation layer, so at
        # most one will be set.
        effective_retry: RetryPolicy | None = None
        if config.max_retries is not None and config.max_retries > 0:
            effective_retry = RetryPolicy(max_attempts=config.max_retries)
        elif config.retry_policy is not None:
            effective_retry = config.retry_policy

        if effective_retry is not None:
            final_result: Any = None
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(effective_retry.max_attempts),
                wait=wait_exponential(
                    multiplier=1,
                    min=effective_retry.wait_min,
                    max=effective_retry.wait_max,
                ),
                reraise=True,
            ):
                with attempt:
                    if attempt_tracker is not None:
                        attempt_tracker[0] = attempt.retry_state.attempt_number
                    if config.timeout is not None:
                        final_result = await asyncio.wait_for(
                            _call_once(),
                            timeout=config.timeout,
                        )
                    else:
                        final_result = await _call_once()
            return final_result
        else:
            if config.timeout is not None:
                return await asyncio.wait_for(_call_once(), timeout=config.timeout)
            return await _call_once()

    def _build_agent_kwargs(self, agent_name: str) -> dict[str, Any]:
        """Build constructor kwargs for the agent class.

        For the implementer agent, injects validation_commands
        from maverick.yaml configuration. All other agents get
        empty kwargs.

        Args:
            agent_name: Registered agent name.

        Returns:
            Dict of keyword arguments for agent class instantiation.
        """
        if agent_name != IMPLEMENTER_AGENT_NAME:
            return {}

        try:
            from maverick.config import load_config
            from maverick.exceptions import ConfigError

            maverick_config = load_config()
            return {
                "validation_commands": _extract_validation_commands(
                    maverick_config.validation
                )
            }
        except (ImportError, ModuleNotFoundError) as e:
            self._logger.debug(
                "validation_config_unavailable",
                error=str(e),
                reason="module_not_found",
            )
        except ConfigError as e:
            self._logger.debug(
                "validation_config_failed",
                error=str(e),
                reason="config_error",
            )
        return {}

    def _extract_usage(self, result: Any) -> UsageMetadata | None:
        """Extract usage metadata from agent result via duck-typing.

        Args:
            result: Agent execution result.

        Returns:
            UsageMetadata if result exposes usage, None otherwise.
        """
        if not hasattr(result, "usage") or result.usage is None:
            return None
        usage = result.usage
        return UsageMetadata(
            input_tokens=getattr(usage, "input_tokens", 0),
            output_tokens=getattr(usage, "output_tokens", 0),
            cache_read_tokens=getattr(usage, "cache_read_tokens", 0),
            cache_write_tokens=getattr(usage, "cache_write_tokens", 0),
            total_cost_usd=getattr(usage, "total_cost_usd", None),
        )


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
    formats for streaming display. Checks are ordered from most specific
    to least specific to avoid false matches.

    Args:
        result: The result returned by agent.execute().

    Returns:
        Extracted text content, or empty string if no text found.
    """
    if result is None:
        return ""

    # Check for FixerResult-style objects (.summary field)
    if hasattr(result, "summary") and hasattr(result, "files_mentioned"):
        summary = result.summary
        status = "Success" if getattr(result, "success", False) else "Failed"
        parts = [f"{status}: {summary}"]
        files = getattr(result, "files_mentioned", [])
        if files:
            parts.append(f"{len(files)} file(s) mentioned")
        error = getattr(result, "error_details", None)
        if error:
            parts.append(f"error: {error}")
        return ", ".join(parts)

    # Check for GroupedReviewResult-style objects (.all_findings property)
    if hasattr(result, "all_findings") and hasattr(result, "groups"):
        findings = result.all_findings
        count = len(findings) if findings else 0
        groups = getattr(result, "groups", [])
        return f"Review complete: {count} finding(s) in {len(groups)} group(s)"

    # Check for list[FixOutcome]-style results
    if isinstance(result, list) and result and hasattr(result[0], "outcome"):
        total = len(result)
        fixed = sum(1 for o in result if getattr(o, "outcome", "") == "fixed")
        return f"Fix outcomes: {fixed}/{total} fixed"

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
