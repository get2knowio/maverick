"""Parallel step handler for concurrent execution.

This module handles execution of ParallelStepRecord steps using anyio
for structured concurrency.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

import anyio

from maverick.dsl.context import WorkflowContext
from maverick.dsl.serialization.executor.conditions import evaluate_for_each_expression
from maverick.dsl.serialization.registry import ComponentRegistry
from maverick.dsl.serialization.schema import ParallelStepRecord

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine


async def execute_parallel_step(
    step: ParallelStepRecord,
    resolved_inputs: dict[str, Any],
    context: WorkflowContext,
    registry: ComponentRegistry,
    config: Any = None,
    execute_step_fn: Callable[..., Coroutine[Any, Any, Any]] | None = None,
) -> Any:
    """Execute a parallel step.

    Executes multiple steps concurrently using anyio TaskGroup for
    structured concurrency.
    If for_each is specified, executes steps once per item in the iteration list.

    Args:
        step: ParallelStepRecord containing steps to execute in parallel.
        resolved_inputs: Resolved values.
        context: WorkflowContext with inputs and step results.
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
        return await _execute_parallel_for_each(step, context, execute_step_fn)
    else:
        # Execute steps in parallel once
        return await _execute_parallel_tasks(step.steps, context, execute_step_fn)


async def _execute_parallel_tasks(
    steps: list[Any],
    context: WorkflowContext,
    execute_step_fn: Callable[..., Coroutine[Any, Any, Any]],
) -> dict[str, Any]:
    """Execute a list of steps in parallel using anyio TaskGroup.

    Args:
        steps: List of step records to execute.
        context: Execution context.
        execute_step_fn: Function to execute nested steps.

    Returns:
        Dictionary with results list preserving step order.
    """
    if not steps:
        return {"results": []}

    # Pre-allocate results to maintain order
    results: list[Any] = [None] * len(steps)

    async def run_step(index: int, step: Any) -> None:
        """Execute a step and store result at the correct index."""
        try:
            results[index] = await execute_step_fn(step, context)
        except BaseException as exc:
            results[index] = exc

    try:
        async with anyio.create_task_group() as tg:
            for idx, step in enumerate(steps):
                tg.start_soon(run_step, idx, step)
    except ExceptionGroup:
        # Exceptions are captured in results array; continue to return them
        pass

    return {"results": results}


async def _execute_parallel_for_each(
    step: ParallelStepRecord,
    context: WorkflowContext,
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

    if not items:
        return {"results": []}

    # Pre-allocate results to maintain order
    iteration_results: list[Any] = [None] * len(items)

    async def run_iteration(index: int, item: Any) -> None:
        """Execute all steps for a single iteration."""
        # Create a copy of the context with iteration variables
        item_context = replace(
            context,
            iteration_context={"item": item, "index": index},
        )

        # Execute all steps in this iteration in parallel
        step_results: list[Any] = [None] * len(step.steps)

        async def run_step(step_idx: int, s: Any) -> None:
            try:
                step_results[step_idx] = await execute_step_fn(s, item_context)
            except BaseException as exc:
                step_results[step_idx] = exc

        try:
            async with anyio.create_task_group() as tg:
                for step_idx, s in enumerate(step.steps):
                    tg.start_soon(run_step, step_idx, s)
        except ExceptionGroup:
            # Exceptions captured in step_results
            pass

        iteration_results[index] = step_results

    try:
        async with anyio.create_task_group() as tg:
            for idx, item in enumerate(items):
                tg.start_soon(run_iteration, idx, item)
    except ExceptionGroup:
        # Exceptions captured in iteration_results
        pass

    return {"results": iteration_results}
