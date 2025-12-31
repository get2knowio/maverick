"""Execution context management for workflow execution.

This module provides utilities for managing and validating execution context.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from maverick.dsl.config import DEFAULTS
from maverick.dsl.context import WorkflowContext
from maverick.logging import get_logger

logger = get_logger(__name__)

# Type alias for rollback actions in serialization DSL
# Rollbacks receive the WorkflowContext as their only argument
SerializationRollbackAction = Callable[[WorkflowContext], None | Awaitable[None]]


def create_execution_context(
    workflow_name: str, inputs: dict[str, Any]
) -> WorkflowContext:
    """Create initial execution context.

    Args:
        workflow_name: Name of the workflow being executed.
        inputs: Workflow input values.

    Returns:
        WorkflowContext instance with workflow_name and inputs set.
    """
    return WorkflowContext(
        workflow_name=workflow_name,
        inputs=inputs,
    )


def validate_step_output(
    output: Any,
    step_name: str,
    step_type: str,
) -> Any:
    """Validate and sanitize step output before storing in context.

    This ensures that step outputs are safe to store and reference in
    subsequent expressions. Invalid outputs are logged and replaced with
    a safe default.

    Args:
        output: The raw output from step execution.
        step_name: Name of the step for logging.
        step_type: Type of the step for logging.

    Returns:
        Validated/sanitized output safe for context storage.
    """
    # None is a valid output (e.g., from failed steps)
    if output is None:
        return None

    # Primitive types are always safe
    if isinstance(output, (str, int, float, bool)):
        return output

    # Collections need basic validation
    if isinstance(output, (list, tuple)):
        # Ensure reasonable size to prevent memory issues
        if len(output) > DEFAULTS.MAX_STEP_OUTPUT_SIZE:
            logger.warning(
                f"Step '{step_name}' ({step_type}) output list/tuple is very large "
                f"({len(output)} items), which may impact performance"
            )
        return output

    if isinstance(output, dict):
        # Ensure reasonable size to prevent memory issues
        if len(output) > DEFAULTS.MAX_STEP_OUTPUT_SIZE:
            logger.warning(
                f"Step '{step_name}' ({step_type}) output dict is very large "
                f"({len(output)} keys), which may impact performance"
            )
        # Check for circular references (basic check)
        try:
            # Attempt JSON-like serialization check
            str(output)
        except Exception as e:
            logger.warning(
                f"Step '{step_name}' ({step_type}) output dict may contain "
                f"circular references or non-serializable objects: {e}"
            )
        return output

    # For other types (dataclass, pydantic model, etc.), try to convert to dict
    # If the object has a to_dict() method, use it for expression-safe storage
    if hasattr(output, "to_dict") and callable(output.to_dict):
        logger.debug(
            f"Step '{step_name}' ({step_type}) output is of type "
            f"{type(output).__name__}, converting to dict via to_dict()"
        )
        return output.to_dict()

    # Otherwise, log a warning but allow it through
    logger.debug(
        f"Step '{step_name}' ({step_type}) output is of type "
        f"{type(output).__name__}, which may not be fully compatible with "
        f"expression evaluation"
    )
    return output


def store_step_output(
    context: WorkflowContext,
    step_name: str,
    output: Any,
    step_type: str = "python",
) -> None:
    """Store a step's output in the execution context.

    Args:
        context: WorkflowContext (modified in-place).
        step_name: Name of the step.
        output: Validated output from the step.
        step_type: Type of the step (for StepResult metadata).
    """
    context.store_step_output(step_name, output, step_type)


def register_rollback(
    context: WorkflowContext,
    step_name: str,
    rollback_fn: SerializationRollbackAction,
) -> None:
    """Register a rollback action for a completed step.

    Rollback actions are stored in reverse order of execution and will be
    executed in LIFO order if the workflow fails.

    Args:
        context: WorkflowContext (modified in-place).
        step_name: Name of the step this rollback compensates.
        rollback_fn: Callable to execute during rollback. Receives the
            WorkflowContext as its only argument.
    """

    # Wrap the SerializationRollbackAction to match RollbackAction signature
    # RollbackAction expects WorkflowContext arg (already correct signature)
    context.register_rollback(step_name, rollback_fn)
    logger.debug(f"Registered rollback for step '{step_name}'")


def get_pending_rollbacks(
    context: WorkflowContext,
) -> list[tuple[str, SerializationRollbackAction]]:
    """Get list of pending rollback registrations.

    Args:
        context: WorkflowContext.

    Returns:
        List of (step_name, rollback_fn) tuples in registration order.
        Note: The rollback_fn signature is adapted to match SerializationRollbackAction.
    """
    rollback_regs = context.get_pending_rollbacks()

    # Convert RollbackRegistration objects to (step_name, rollback_fn) tuples
    # rollback_fn signature is SerializationRollbackAction (takes WorkflowContext)
    result: list[tuple[str, SerializationRollbackAction]] = []
    for reg in rollback_regs:
        result.append((reg.step_name, reg.action))

    return result
