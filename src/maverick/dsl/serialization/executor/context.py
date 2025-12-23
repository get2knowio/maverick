"""Execution context management for workflow execution.

This module provides utilities for managing and validating execution context.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def create_execution_context(
    workflow_name: str, inputs: dict[str, Any]
) -> dict[str, Any]:
    """Create initial execution context.

    Args:
        workflow_name: Name of the workflow being executed.
        inputs: Workflow input values.

    Returns:
        Initial context dictionary with structure:
        {
            "workflow_name": str,
            "inputs": {...},
            "steps": {},  # Will hold step outputs
        }
    """
    return {
        "workflow_name": workflow_name,
        "inputs": inputs,
        "steps": {},  # Will hold step outputs: steps.<name>.output
    }


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
        if len(output) > 10000:
            logger.warning(
                f"Step '{step_name}' ({step_type}) output list/tuple is very large "
                f"({len(output)} items), which may impact performance"
            )
        return output

    if isinstance(output, dict):
        # Ensure reasonable size to prevent memory issues
        if len(output) > 10000:
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

    # For other types, log a warning but allow them through
    # (could be dataclass, pydantic model, or other structured data)
    logger.debug(
        f"Step '{step_name}' ({step_type}) output is of type "
        f"{type(output).__name__}, which may not be fully compatible with "
        f"expression evaluation"
    )
    return output


def store_step_output(
    context: dict[str, Any],
    step_name: str,
    output: Any,
) -> None:
    """Store a step's output in the execution context.

    Args:
        context: Execution context (modified in-place).
        step_name: Name of the step.
        output: Validated output from the step.
    """
    context["steps"][step_name] = {"output": output}
