"""Parallel step handler for concurrent execution.

This module handles execution of ParallelStepRecord steps.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from maverick.dsl.serialization.executor.conditions import evaluate_for_each_expression
from maverick.dsl.serialization.registry import ComponentRegistry
from maverick.dsl.serialization.schema import ParallelStepRecord

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine


async def execute_parallel_step(
    step: ParallelStepRecord,
    resolved_inputs: dict[str, Any],
    context: dict[str, Any],
    registry: ComponentRegistry,
    config: Any = None,
    execute_step_fn: Callable[..., Coroutine[Any, Any, Any]] | None = None,
) -> Any:
    """Execute a parallel step.

    Executes multiple steps concurrently using asyncio.gather.
    If for_each is specified, executes steps once per item in the iteration list.

    Args:
        step: ParallelStepRecord containing steps to execute in parallel.
        resolved_inputs: Resolved values.
        context: Execution context.
        registry: Component registry (unused).
        config: Optional configuration (unused).
        execute_step_fn: Function to execute nested steps (required).

    Returns:
        Dictionary containing results from all parallel steps or iterations.

    Raises:
        ValueError: If execute_step_fn is not provided.
    """
    if execute_step_fn is None:
        raise ValueError("execute_step_fn is required for parallel step execution")

    if step.for_each:
        # Execute steps for each item in the iteration list
        return await _execute_parallel_for_each(
            step, context, execute_step_fn
        )
    else:
        # Execute steps in parallel once
        tasks = [execute_step_fn(s, context) for s in step.steps]

        # Execute in parallel with exception handling
        results = await asyncio.gather(*tasks, return_exceptions=True)

        return {"results": results}


async def _execute_parallel_for_each(
    step: ParallelStepRecord,
    context: dict[str, Any],
    execute_step_fn: Callable[..., Coroutine[Any, Any, Any]],
) -> Any:
    """Execute parallel steps for each item in a list.

    Args:
        step: ParallelStepRecord with for_each expression.
        context: Execution context.
        execute_step_fn: Function to execute nested steps.

    Returns:
        Dictionary with results from all iterations.

    Raises:
        ValueError: If for_each is None.
        TypeError: If for_each expression doesn't evaluate to a list.
    """
    if step.for_each is None:
        raise ValueError(f"Step {step.name} has no for_each expression")

    # Evaluate the for_each expression to get the list of items
    items = evaluate_for_each_expression(step.for_each, context)

    # Create tasks for each item
    tasks = []
    for index, item in enumerate(items):
        # Create a copy of the context with the current item
        # Add 'item' and 'index' to iteration context for expression evaluation
        item_context = context.copy()
        item_context["iteration"] = {
            "item": item,
            "index": index,
        }

        # Create tasks for all steps in this iteration
        iteration_tasks = [execute_step_fn(s, item_context) for s in step.steps]

        # Each iteration's task is itself a gather of all steps in parallel
        tasks.append(asyncio.gather(*iteration_tasks, return_exceptions=True))

    # Execute all iterations in parallel
    iteration_results = await asyncio.gather(*tasks, return_exceptions=True)

    return {"results": iteration_results}
