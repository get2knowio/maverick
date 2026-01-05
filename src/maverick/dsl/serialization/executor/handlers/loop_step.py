"""Loop step handler for iteration with concurrency control.

This module handles execution of LoopStepRecord steps using anyio
for structured concurrency with configurable max_concurrency.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

import anyio

from maverick.dsl.context import WorkflowContext
from maverick.dsl.serialization.executor.conditions import evaluate_for_each_expression
from maverick.dsl.serialization.registry import ComponentRegistry
from maverick.dsl.serialization.schema import LoopStepRecord

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine


async def execute_loop_step(
    step: LoopStepRecord,
    resolved_inputs: dict[str, Any],
    context: WorkflowContext,
    registry: ComponentRegistry,
    config: Any = None,
    execute_step_fn: Callable[..., Coroutine[Any, Any, Any]] | None = None,
) -> Any:
    """Execute a loop step with concurrency control.

    Executes steps with configurable concurrency using anyio TaskGroup.
    If for_each is specified, executes steps once per item in the iteration list.

    Args:
        step: LoopStepRecord containing steps to execute.
        resolved_inputs: Resolved values.
        context: WorkflowContext with inputs and step results.
        registry: Component registry (unused).
        config: Optional configuration (unused).
        execute_step_fn: Function to execute nested steps (required).

    Returns:
        Dictionary containing results from all iterations.

    Raises:
        ValueError: If execute_step_fn is not provided.
    """
    if execute_step_fn is None:
        raise ValueError("execute_step_fn is required for loop step execution")

    if step.for_each:
        # Execute steps for each item in the iteration list
        return await _execute_loop_for_each(step, context, execute_step_fn)
    else:
        # Execute steps once with concurrency control
        return await _execute_loop_tasks(
            step.steps, context, execute_step_fn, step.max_concurrency
        )


async def _execute_loop_tasks(
    steps: list[Any],
    context: WorkflowContext,
    execute_step_fn: Callable[..., Coroutine[Any, Any, Any]],
    max_concurrency: int = 1,
) -> dict[str, Any]:
    """Execute a list of steps with concurrency control.

    Args:
        steps: List of step records to execute.
        context: Execution context.
        execute_step_fn: Function to execute nested steps.
        max_concurrency: Max concurrent executions (1=sequential, 0=unlimited).

    Returns:
        Dictionary with results list preserving step order.
    """
    if not steps:
        return {"results": []}

    # Pre-allocate results to maintain order
    results: list[Any] = [None] * len(steps)

    # Create semaphore for concurrency control (0 means unlimited)
    semaphore = anyio.Semaphore(max_concurrency) if max_concurrency > 0 else None

    async def run_step(index: int, step: Any) -> None:
        """Execute a step and store result at the correct index."""

        async def _execute() -> None:
            try:
                results[index] = await execute_step_fn(step, context)
            except BaseException as exc:
                results[index] = exc

        if semaphore:
            async with semaphore:
                await _execute()
        else:
            await _execute()

    try:
        async with anyio.create_task_group() as tg:
            for idx, step in enumerate(steps):
                tg.start_soon(run_step, idx, step)
    except ExceptionGroup:
        # Exceptions are captured in results array; continue to return them
        pass

    return {"results": results}


async def _execute_loop_for_each(
    step: LoopStepRecord,
    context: WorkflowContext,
    execute_step_fn: Callable[..., Coroutine[Any, Any, Any]],
) -> Any:
    """Execute loop steps for each item in a list with concurrency control.

    Args:
        step: LoopStepRecord with for_each expression.
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

    # Create semaphore for concurrency control (0 means unlimited)
    max_concurrency = step.max_concurrency
    semaphore = anyio.Semaphore(max_concurrency) if max_concurrency > 0 else None

    async def run_iteration(index: int, item: Any) -> None:
        """Execute all steps for a single iteration."""

        async def _execute() -> None:
            # Create a copy of the context with iteration variables
            item_context = replace(
                context,
                iteration_context={"item": item, "index": index},
            )

            # Execute all steps in this iteration sequentially
            # (nested steps within an iteration run in sequence)
            step_results: list[Any] = []
            for s in step.steps:
                try:
                    result = await execute_step_fn(s, item_context)
                    step_results.append(result)
                except BaseException as exc:
                    step_results.append(exc)
                    break  # Stop iteration on error

            iteration_results[index] = step_results

        if semaphore:
            async with semaphore:
                await _execute()
        else:
            await _execute()

    try:
        async with anyio.create_task_group() as tg:
            for idx, item in enumerate(items):
                tg.start_soon(run_iteration, idx, item)
    except ExceptionGroup:
        # Exceptions captured in iteration_results
        pass

    return {"results": iteration_results}
