"""Branch step handler for conditional branching.

This module handles execution of BranchStepRecord steps.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from maverick.dsl.context import WorkflowContext
from maverick.dsl.serialization.executor.conditions import evaluate_condition
from maverick.dsl.serialization.executor.handlers.base import EventCallback
from maverick.dsl.serialization.registry import ComponentRegistry
from maverick.dsl.serialization.schema import BranchStepRecord

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine


async def execute_branch_step(
    step: BranchStepRecord,
    resolved_inputs: dict[str, Any],
    context: WorkflowContext,
    registry: ComponentRegistry,
    config: Any = None,
    execute_step_fn: Callable[..., Coroutine[Any, Any, Any]] | None = None,
    event_callback: EventCallback | None = None,
) -> Any:
    """Execute a branch step.

    Evaluates branch options in order and executes the first matching step.

    Args:
        step: BranchStepRecord containing branch options.
        resolved_inputs: Resolved values.
        context: WorkflowContext with inputs and step results.
        registry: Component registry (unused).
        config: Optional configuration (unused).
        execute_step_fn: Function to execute nested steps (required).
        event_callback: Optional callback for real-time event streaming.

    Returns:
        Result from the first matching branch, or None if no match.

    Raises:
        ValueError: If execute_step_fn is not provided.
    """
    if execute_step_fn is None:
        raise ValueError("execute_step_fn is required for branch step execution")

    # Evaluate options in order, execute first matching step
    for option in step.options:
        if evaluate_condition(option.when, context):
            return await execute_step_fn(option.step, context, event_callback)

    # No matching branch found
    return None
