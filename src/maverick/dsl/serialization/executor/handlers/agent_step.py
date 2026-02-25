"""Agent step handler for executing agent-based steps.

This module handles execution of AgentStepRecord steps with streaming events.
Implements T027 (AgentStreamChunk emission) and T028 (thinking indicator).
Delegates execution to StepExecutor (FR-001, FR-008).
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from maverick.dsl.context import WorkflowContext
from maverick.dsl.errors import ReferenceResolutionError
from maverick.dsl.executor.config import (
    IMPLEMENTER_AGENT_NAME,
    RetryPolicy,
    StepExecutorConfig,
)
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
    """Execute an agent step by delegating to StepExecutor.

    Implements T027 (AgentStreamChunk emission during execution) and
    T028 (thinking indicator at agent start) via StepExecutor.

    Args:
        step: AgentStepRecord containing agent reference and context.
        resolved_inputs: Resolved context values.
        context: WorkflowContext with inputs and step results.
        registry: Component registry for resolving agent.
        config: Optional configuration (unused).
        event_callback: Optional callback for real-time event streaming.

    Returns:
        HandlerOutput containing:
        - result: Agent execution result (ExecutorResult.output)
        - events: List of AgentStreamChunk events (empty if event_callback
          was provided, as events were forwarded in real-time)

    Raises:
        ReferenceResolutionError: If agent not found in registry.
        OutputSchemaValidationError: If output_schema validation fails.
        ConfigError: If executor_config or output_schema has invalid values.
    """
    # Fast fail: check agent exists before expensive context building
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
    if step.agent == IMPLEMENTER_AGENT_NAME and isinstance(agent_context, dict):
        agent_context = await _convert_to_implementer_context(agent_context)

    # Get or create executor
    executor = context.step_executor
    if executor is None:
        from maverick.dsl.executor import ClaudeStepExecutor

        executor = ClaudeStepExecutor(registry=registry)

    # Resolve output_schema dotted path if provided (FR-007)
    output_schema = _resolve_output_schema(step)

    # Deserialize executor_config if provided (US4)
    step_config = _resolve_executor_config(step)

    # Delegate execution to StepExecutor
    # TODO(032): Forward instructions/allowed_tools/cwd per FR-001.
    # The StepExecutor protocol accepts these but AgentStepRecord
    # does not yet surface them. Once the DSL schema adds
    # instructions/allowed_tools/cwd fields, pass them here.
    executor_result = await executor.execute(
        step_name=step.name,
        agent_name=step.agent,
        prompt=agent_context,
        output_schema=output_schema,
        config=step_config,
        event_callback=event_callback,
    )

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

    # When event_callback was provided, events were already forwarded
    # in real-time. Returning them in HandlerOutput.events would cause
    # double-emission in the executor.
    events_to_embed = [] if event_callback else list(executor_result.events)
    return HandlerOutput(result=executor_result.output, events=events_to_embed)


async def _convert_to_implementer_context(
    agent_context: dict[str, Any],
) -> ImplementerContext:
    """Convert a dict agent context to an ImplementerContext.

    Args:
        agent_context: Dict with task_file, task_description, branch, etc.

    Returns:
        ImplementerContext instance.
    """
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

    return ImplementerContext(
        task_file=task_file,
        task_description=task_description,
        phase_name=phase_name,
        branch=branch,
        cwd=cwd,
        skip_validation=agent_context.get("skip_validation", False),
        dry_run=agent_context.get("dry_run", False),
    )


def _resolve_output_schema(step: AgentStepRecord) -> type[BaseModel] | None:
    """Resolve the output_schema dotted path to a Pydantic BaseModel class.

    Args:
        step: AgentStepRecord potentially containing output_schema.

    Returns:
        The resolved BaseModel subclass, or None if not specified.

    Raises:
        ConfigError: If the dotted path cannot be imported or resolved.
    """
    schema_path = getattr(step, "output_schema", None)
    if not schema_path:
        return None
    try:
        module_path, class_name = schema_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)
    except (ImportError, AttributeError, ValueError) as e:
        raise ConfigError(f"Cannot resolve output_schema '{schema_path}': {e}") from e

    if not (isinstance(cls, type) and issubclass(cls, BaseModel)):
        raise ConfigError(
            f"output_schema '{schema_path}' resolved to {cls!r}, "
            f"which is not a Pydantic BaseModel subclass"
        )
    return cls


def _resolve_executor_config(step: AgentStepRecord) -> StepExecutorConfig | None:
    """Deserialize executor_config dict to StepExecutorConfig if present.

    Args:
        step: AgentStepRecord potentially containing executor_config.

    Returns:
        StepExecutorConfig instance, or None if not specified.

    Raises:
        ConfigError: If executor_config contains unrecognized keys.
    """
    config_dict = getattr(step, "executor_config", None)
    if not config_dict:
        return None

    known_keys = {"timeout", "retry_policy", "model", "temperature", "max_tokens"}
    unknown_keys = set(config_dict.keys()) - known_keys
    if unknown_keys:
        raise ConfigError(
            f"Unrecognized executor_config keys: {unknown_keys}. "
            f"Supported keys: {known_keys}"
        )

    retry_policy = None
    if "retry_policy" in config_dict:
        rp_dict = config_dict["retry_policy"]
        if isinstance(rp_dict, dict):
            retry_policy = RetryPolicy(
                max_attempts=rp_dict.get("max_attempts", 3),
                wait_min=rp_dict.get("wait_min", 1.0),
                wait_max=rp_dict.get("wait_max", 10.0),
            )

    return StepExecutorConfig(
        timeout=config_dict.get("timeout"),
        retry_policy=retry_policy,
        model=config_dict.get("model"),
        temperature=config_dict.get("temperature"),
        max_tokens=config_dict.get("max_tokens"),
    )
