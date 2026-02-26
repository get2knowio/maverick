"""Python step handler for executing Python callable actions.

This module handles execution of PythonStepRecord steps. Supports
mode-aware dispatch (Spec 034): when StepConfig.mode is AGENT,
execution delegates to dispatch_agent_mode instead of calling the
action directly.
"""

from __future__ import annotations

import inspect
from typing import Any

from maverick.dsl.context import WorkflowContext
from maverick.dsl.errors import ReferenceResolutionError
from maverick.dsl.events import AgentStreamChunk
from maverick.dsl.executor.config import StepConfig
from maverick.dsl.serialization.executor import context as context_module
from maverick.dsl.serialization.executor.handlers.base import EventCallback
from maverick.dsl.serialization.executor.handlers.dispatch import dispatch_agent_mode
from maverick.dsl.serialization.registry import ComponentRegistry
from maverick.dsl.serialization.schema import PythonStepRecord
from maverick.dsl.types import StepMode
from maverick.logging import get_logger

logger = get_logger(__name__)


def _resolve_mode(config: Any) -> StepMode:
    """Resolve the execution mode from config.

    Args:
        config: StepConfig instance or other config object.

    Returns:
        StepMode.AGENT when explicitly configured, DETERMINISTIC otherwise.
    """
    if isinstance(config, StepConfig) and config.mode == StepMode.AGENT:
        return StepMode.AGENT
    return StepMode.DETERMINISTIC


async def execute_python_step(
    step: PythonStepRecord,
    resolved_inputs: dict[str, Any],
    context: WorkflowContext,
    registry: ComponentRegistry,
    config: Any = None,
    event_callback: EventCallback | None = None,
) -> Any:
    """Execute a Python callable step.

    Supports mode-aware dispatch (Spec 034). When the resolved StepConfig
    has ``mode=AGENT``, execution is delegated to ``dispatch_agent_mode()``
    which routes through StepExecutor with autonomy gates. Otherwise, the
    action is called directly (deterministic mode).

    The ``force_deterministic`` flag in ``context.inputs`` overrides agent
    mode back to deterministic for safety/debugging.

    Args:
        step: PythonStepRecord containing action reference and arguments.
        resolved_inputs: Resolved keyword arguments.
        context: WorkflowContext with inputs and step results.
        registry: Component registry for resolving action.
        config: Optional StepConfig for mode/autonomy dispatch. When not a
            StepConfig instance, the handler falls through to deterministic.
        event_callback: Optional callback for real-time event streaming.

    Returns:
        Action return value (deterministic) or DispatchResult.output (agent).

    Raises:
        ReferenceResolutionError: If action not found in registry.
    """
    # Look up action in registry
    if not registry.actions.has(step.action):
        raise ReferenceResolutionError(
            reference_type="action",
            reference_name=step.action,
            available_names=registry.actions.list_names(),
        )

    # --- Mode-aware dispatch (Spec 034) ---
    mode = _resolve_mode(config)
    # Coerce at boundary: DSL expressions resolve to strings (Guardrail #8)
    raw_force = context.inputs.get("force_deterministic", False)
    force_deterministic = raw_force is True or (
        isinstance(raw_force, str) and raw_force.lower() == "true"
    )

    if mode == StepMode.AGENT and not force_deterministic:
        step_config: StepConfig = config  # type-narrowed by _resolve_mode
        logger.info(
            "python_step.agent_dispatch",
            step_name=step.name,
            action=step.action,
            autonomy=step_config.autonomy.value if step_config.autonomy else "operator",
        )
        dispatch_result = await dispatch_agent_mode(
            step=step,
            resolved_inputs=resolved_inputs,
            context=context,
            registry=registry,
            step_config=step_config,
            event_callback=event_callback,
        )
        return dispatch_result.output

    # --- Deterministic path (existing behavior) ---
    action = registry.actions.get(step.action)

    # Check if action accepts stream_callback parameter
    # If so, create a callback wrapper that emits AgentStreamChunk events
    action_sig = inspect.signature(action)
    if "stream_callback" in action_sig.parameters and event_callback is not None:

        async def stream_to_event(text: str) -> None:
            """Convert stream callback to AgentStreamChunk event."""
            chunk_event = AgentStreamChunk(
                step_name=step.name,
                agent_name="fixer",  # Actions typically use fixer agents
                text=text,
                chunk_type="output",
            )
            await event_callback(chunk_event)

        resolved_inputs["stream_callback"] = stream_to_event

    # Check if action accepts event_callback parameter
    # If so, pass it through so actions can emit StepOutput events directly
    if "event_callback" in action_sig.parameters and event_callback is not None:
        resolved_inputs["event_callback"] = event_callback

    # Call the action with resolved kwargs
    result = action(**resolved_inputs)

    # If result is a coroutine, await it
    if inspect.iscoroutine(result):
        result = await result

    # Check for failure in result dict (actions return {"success": False, "error": ...})
    # This ensures actions that return failure dicts actually fail the step
    if isinstance(result, dict) and result.get("success") is False:
        error_msg = result.get("error", "Action returned success=False")
        raise RuntimeError(f"Action '{step.action}' failed: {error_msg}")

    # Register rollback if specified
    if step.rollback:
        if not registry.actions.has(step.rollback):
            logger.warning(
                f"Rollback action '{step.rollback}' not found in registry "
                f"for step '{step.name}'. Skipping rollback registration."
            )
        else:
            rollback_action = registry.actions.get(step.rollback)

            # Wrap action to match SerializationRollbackAction signature
            # (takes WorkflowContext instead of resolved_inputs)
            async def rollback_wrapper(exec_context: WorkflowContext) -> None:
                rollback_result = rollback_action(**resolved_inputs)
                if inspect.iscoroutine(rollback_result):
                    await rollback_result

            context_module.register_rollback(context, step.name, rollback_wrapper)

    return result
