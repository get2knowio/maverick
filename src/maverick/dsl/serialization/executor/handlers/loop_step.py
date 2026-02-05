"""Loop step handler for iteration with concurrency control.

This module handles execution of LoopStepRecord steps using anyio
for structured concurrency with configurable max_concurrency.
"""

from __future__ import annotations

import time
from dataclasses import replace
from typing import TYPE_CHECKING, Any

import anyio

from maverick.dsl.context import WorkflowContext
from maverick.dsl.errors import LoopStepExecutionError
from maverick.dsl.events import (
    LoopIterationCompleted,
    LoopIterationStarted,
    StepCompleted,
    StepStarted,
)
from maverick.dsl.serialization.executor.conditions import evaluate_for_each_expression
from maverick.dsl.serialization.executor.handlers.base import EventCallback
from maverick.dsl.serialization.executor.step_path import make_prefix_callback
from maverick.dsl.serialization.registry import ComponentRegistry
from maverick.dsl.serialization.schema import LoopStepRecord
from maverick.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

logger = get_logger(__name__)

# Key used in iteration_context to track parent loop for nested loop events
_CURRENT_LOOP_STEP_KEY = "_current_loop_step"


def _check_for_failures(
    results: list[Any],
    step_name: str,
) -> None:
    """Check results for exceptions and raise LoopStepExecutionError if any found.

    Args:
        results: List of results from loop iterations.
        step_name: Name of the loop step for error reporting.

    Raises:
        LoopStepExecutionError: If any result is an exception.
    """
    failed_iterations: list[tuple[int, str]] = []

    for idx, result in enumerate(results):
        if isinstance(result, BaseException):
            failed_iterations.append((idx, str(result)))
        elif isinstance(result, list):
            # For for_each loops, results may be lists of step results
            for step_result in result:
                if isinstance(step_result, BaseException):
                    failed_iterations.append((idx, str(step_result)))
                    break  # Only report first failure per iteration

    if failed_iterations:
        raise LoopStepExecutionError(
            step_name=step_name,
            failed_iterations=failed_iterations,
            total_iterations=len(results),
        )


def _extract_item_label(item: Any, index: int) -> str:
    """Extract display label from loop item for UI visibility.

    Attempts to extract a human-readable label from the loop item.
    Tries common dictionary keys first, then falls back to string
    representation or generic index-based label.

    Args:
        item: The loop iteration item (can be dict, str, or any type).
        index: The 0-based iteration index.

    Returns:
        A human-readable label for the item, suitable for TUI display.

    Examples:
        >>> _extract_item_label({"name": "build"}, 0)
        'build'
        >>> _extract_item_label({"phase": "Phase 1: Core"}, 0)
        'Phase 1: Core'
        >>> _extract_item_label("simple_string", 0)
        'simple_string'
        >>> _extract_item_label(12345, 0)
        'Item 1'
    """
    if isinstance(item, dict):
        # Try common label keys in order of preference
        for key in ("label", "name", "title", "phase", "id"):
            if key in item:
                return str(item[key])
    if isinstance(item, str):
        return item
    return f"Item {index + 1}"


async def execute_loop_step(
    step: LoopStepRecord,
    resolved_inputs: dict[str, Any],
    context: WorkflowContext,
    registry: ComponentRegistry,
    config: Any = None,
    execute_step_fn: Callable[..., Coroutine[Any, Any, Any]] | None = None,
    resume_iteration_index: int | None = None,
    resume_after_nested_step_index: int | None = None,
    event_callback: EventCallback | None = None,
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
        resume_iteration_index: If resuming, skip iterations before this index.
        resume_after_nested_step_index: If resuming, skip steps at or before
            this index within the resume iteration.

    Returns:
        Dictionary containing results from all iterations.

    Raises:
        ValueError: If execute_step_fn is not provided.
    """
    if execute_step_fn is None:
        raise ValueError("execute_step_fn is required for loop step execution")

    # Resolve parallel shorthand to effective max_concurrency
    effective_max_concurrency = step.get_effective_max_concurrency()

    if step.for_each:
        # Execute steps for each item in the iteration list
        return await _execute_loop_for_each(
            step,
            context,
            execute_step_fn,
            resume_iteration_index=resume_iteration_index,
            resume_after_nested_step_index=resume_after_nested_step_index,
            event_callback=event_callback,
            effective_max_concurrency=effective_max_concurrency,
        )
    else:
        # Execute steps once with concurrency control
        return await _execute_loop_tasks(
            step.steps,
            context,
            execute_step_fn,
            effective_max_concurrency,
            step_name=step.name,
            event_callback=event_callback,
        )


async def _execute_loop_tasks(
    steps: list[Any],
    context: WorkflowContext,
    execute_step_fn: Callable[..., Coroutine[Any, Any, Any]],
    max_concurrency: int = 1,
    step_name: str = "loop",
    event_callback: EventCallback | None = None,
) -> dict[str, Any]:
    """Execute a list of steps with concurrency control.

    Emits LoopIterationStarted and LoopIterationCompleted events for each
    step execution. Note that for parallel execution, events may arrive
    out of order.

    Args:
        steps: List of step records to execute.
        context: Execution context.
        execute_step_fn: Function to execute nested steps.
        max_concurrency: Max concurrent executions (1=sequential, 0=unlimited).
        step_name: Name of the loop step (for event emission).

    Returns:
        Dictionary with results list preserving step order and emitted events.
    """
    if not steps:
        return {"results": [], "events": []}

    total_steps = len(steps)

    # Pre-allocate results to maintain order
    results: list[Any] = [None] * total_steps

    # Collect emitted events (thread-safe for parallel execution)
    emitted_events: list[LoopIterationStarted | LoopIterationCompleted] = []
    events_lock = anyio.Lock()

    # Create semaphore for concurrency control (0 means unlimited)
    semaphore = anyio.Semaphore(max_concurrency) if max_concurrency > 0 else None

    # Fail-fast: shared flag to stop pending iterations after a failure
    failure_event = anyio.Event()

    # Track parent loop for nested loop visibility
    parent_step_name = context.iteration_context.get(_CURRENT_LOOP_STEP_KEY)
    # Set current loop as parent for any nested loops
    context.iteration_context[_CURRENT_LOOP_STEP_KEY] = step_name

    async def run_step(index: int, step_record: Any) -> None:
        """Execute a step and store result at the correct index."""

        async def _execute() -> None:
            # Skip if a previous iteration already failed
            if failure_event.is_set():
                logger.debug(
                    "loop_task_skipped",
                    step_name=step_name,
                    index=index,
                    reason="previous iteration failed",
                )
                return

            # Extract label from step name if available
            item_label = getattr(step_record, "name", None) or f"Task {index + 1}"

            # Wrap callback with iteration prefix for hierarchical paths
            iter_callback: EventCallback | None = None
            if event_callback:
                iter_callback = make_prefix_callback(f"[{index}]", event_callback)

            # Emit LoopIterationStarted event
            start_event = LoopIterationStarted(
                step_name=step_name,
                iteration_index=index,
                total_iterations=total_steps,
                item_label=item_label,
                parent_step_name=parent_step_name,
                step_path=f"[{index}]",
            )
            if event_callback:
                await event_callback(start_event)
            else:
                async with events_lock:
                    emitted_events.append(start_event)

            logger.debug(
                "loop_task_started",
                step_name=step_name,
                index=index,
                total_steps=total_steps,
                item_label=item_label,
            )

            # Track timing
            start_time = time.time()
            success = True
            error_msg: str | None = None

            # Emit StepStarted for nested step so the TUI can
            # track lifecycle (running -> completed/failed).
            nested_step_name = getattr(step_record, "name", None)
            nested_step_type = getattr(step_record, "type", None)
            if iter_callback is not None and nested_step_name and nested_step_type:
                await iter_callback(
                    StepStarted(
                        step_name=nested_step_name,
                        step_type=nested_step_type,
                        step_path=nested_step_name,
                    )
                )

            try:
                results[index] = await execute_step_fn(
                    step_record, context, iter_callback
                )
            except BaseException as exc:
                results[index] = exc
                success = False
                error_msg = str(exc)
                failure_event.set()

            # Calculate duration
            duration_ms = int((time.time() - start_time) * 1000)

            # Emit StepCompleted for nested step
            if iter_callback is not None and nested_step_name and nested_step_type:
                await iter_callback(
                    StepCompleted(
                        step_name=nested_step_name,
                        step_type=nested_step_type,
                        success=success,
                        duration_ms=duration_ms,
                        error=error_msg,
                        step_path=nested_step_name,
                    )
                )

            # Emit LoopIterationCompleted event
            completed_event = LoopIterationCompleted(
                step_name=step_name,
                iteration_index=index,
                success=success,
                duration_ms=duration_ms,
                error=error_msg,
                step_path=f"[{index}]",
            )
            if event_callback:
                await event_callback(completed_event)
            else:
                async with events_lock:
                    emitted_events.append(completed_event)

            logger.debug(
                "loop_task_completed",
                step_name=step_name,
                index=index,
                total_steps=total_steps,
                success=success,
                duration_ms=duration_ms,
            )

        if semaphore:
            async with semaphore:
                await _execute()
        else:
            await _execute()

    try:
        async with anyio.create_task_group() as tg:
            for idx, step_record in enumerate(steps):
                tg.start_soon(run_step, idx, step_record)
    except ExceptionGroup:
        # Exceptions are captured in results array; we'll check below
        pass
    finally:
        # Restore parent loop context for proper nesting
        if parent_step_name is not None:
            context.iteration_context[_CURRENT_LOOP_STEP_KEY] = parent_step_name
        else:
            context.iteration_context.pop(_CURRENT_LOOP_STEP_KEY, None)

    # Check for failures and raise if any iterations failed
    _check_for_failures(results, step_name)

    return {"results": results, "events": emitted_events}


async def _execute_loop_for_each(
    step: LoopStepRecord,
    context: WorkflowContext,
    execute_step_fn: Callable[..., Coroutine[Any, Any, Any]],
    resume_iteration_index: int | None = None,
    resume_after_nested_step_index: int | None = None,
    event_callback: EventCallback | None = None,
    effective_max_concurrency: int | None = None,
) -> Any:
    """Execute loop steps for each item in a list with concurrency control.

    Supports resuming from a checkpoint by skipping iterations and steps
    that were completed before the checkpoint. Emits LoopIterationStarted
    and LoopIterationCompleted events for each iteration.

    Args:
        step: LoopStepRecord with for_each expression.
        context: Execution context.
        execute_step_fn: Function to execute nested steps.
        resume_iteration_index: If resuming, skip iterations before this index.
        resume_after_nested_step_index: If resuming, skip steps at or before
            this index within the resume iteration.

    Returns:
        Dictionary with results from all iterations and emitted events.

    Raises:
        ValueError: If for_each is None.
        TypeError: If for_each expression doesn't evaluate to a list.
    """
    if step.for_each is None:
        raise ValueError(f"Step {step.name} has no for_each expression")

    # Evaluate the for_each expression to get the list of items
    items = evaluate_for_each_expression(step.for_each, context)

    if not items:
        return {"results": [], "events": []}

    total_iterations = len(items)

    # Pre-allocate results to maintain order
    iteration_results: list[Any] = [None] * total_iterations

    # Collect emitted events (thread-safe for parallel execution)
    emitted_events: list[LoopIterationStarted | LoopIterationCompleted] = []
    events_lock = anyio.Lock()

    # Fail-fast: shared flag to stop pending iterations after a failure
    failure_event = anyio.Event()

    # Track parent loop for nested loop visibility
    parent_step_name = context.iteration_context.get(_CURRENT_LOOP_STEP_KEY)
    # Set current loop as parent for any nested loops
    context.iteration_context[_CURRENT_LOOP_STEP_KEY] = step.name

    # Log resume info if resuming
    if resume_iteration_index is not None:
        logger.info(
            f"Resuming loop from iteration {resume_iteration_index}, "
            f"after nested step index {resume_after_nested_step_index}"
        )

    # Create semaphore for concurrency control (0 means unlimited)
    # Use effective_max_concurrency if provided, otherwise fall back to step value
    max_concurrency = (
        effective_max_concurrency
        if effective_max_concurrency is not None
        else step.get_effective_max_concurrency()
    )
    semaphore = anyio.Semaphore(max_concurrency) if max_concurrency > 0 else None

    async def run_iteration(
        index: int,
        item: Any,
        skip_steps_before: int | None = None,
    ) -> None:
        """Execute all steps for a single iteration.

        Args:
            index: Iteration index.
            item: Item from for_each list.
            skip_steps_before: If set, skip steps at or before this index.
        """

        async def _execute() -> None:
            # Skip if a previous iteration already failed
            if failure_event.is_set():
                logger.debug(
                    "loop_iteration_skipped",
                    step_name=step.name,
                    index=index,
                    reason="previous iteration failed",
                )
                return

            # Extract label for TUI display
            item_label = _extract_item_label(item, index)

            # Wrap callback with iteration prefix for hierarchical paths
            iter_callback: EventCallback | None = None
            if event_callback:
                iter_callback = make_prefix_callback(f"[{index}]", event_callback)

            # Emit LoopIterationStarted event
            start_event = LoopIterationStarted(
                step_name=step.name,
                iteration_index=index,
                total_iterations=total_iterations,
                item_label=item_label,
                parent_step_name=parent_step_name,
                step_path=f"[{index}]",
            )
            if event_callback:
                await event_callback(start_event)
            else:
                async with events_lock:
                    emitted_events.append(start_event)

            logger.debug(
                "loop_iteration_started",
                step_name=step.name,
                index=index,
                total_iterations=total_iterations,
                item_label=item_label,
            )

            # Track timing
            start_time = time.time()
            success = True
            error_msg: str | None = None

            # Create a copy of the context with iteration variables
            # Preserve the current loop key for nested loop tracking
            item_context = replace(
                context,
                iteration_context={
                    "item": item,
                    "index": index,
                    _CURRENT_LOOP_STEP_KEY: step.name,
                },
            )

            # Execute all steps in this iteration sequentially
            # (nested steps within an iteration run in sequence)
            step_results: list[Any] = []
            try:
                for step_idx, s in enumerate(step.steps):
                    # Skip steps before resume point in the resume iteration
                    if skip_steps_before is not None and step_idx <= skip_steps_before:
                        logger.debug(
                            f"Skipping step index {step_idx} in iteration {index} "
                            f"(before resume point)"
                        )
                        step_results.append(None)  # Placeholder for skipped step
                        continue

                    # Emit StepStarted for nested step so the TUI can
                    # track lifecycle (running -> completed/failed).
                    # The iter_callback prefixes with [index], and the
                    # outer event_callback prefixes with the loop step
                    # name, producing paths like
                    # "implement_by_phase/[0]/implement_phase".
                    nested_step_start = time.time()
                    if iter_callback is not None:
                        await iter_callback(
                            StepStarted(
                                step_name=s.name,
                                step_type=s.type,
                                step_path=s.name,
                            )
                        )

                    try:
                        result = await execute_step_fn(s, item_context, iter_callback)
                        step_results.append(result)

                        # Emit StepCompleted (success) for nested step
                        if iter_callback is not None:
                            nested_duration = int(
                                (time.time() - nested_step_start) * 1000
                            )
                            await iter_callback(
                                StepCompleted(
                                    step_name=s.name,
                                    step_type=s.type,
                                    success=True,
                                    duration_ms=nested_duration,
                                    step_path=s.name,
                                )
                            )
                    except BaseException as exc:
                        # Emit StepCompleted (failure) for nested step
                        if iter_callback is not None:
                            nested_duration = int(
                                (time.time() - nested_step_start) * 1000
                            )
                            await iter_callback(
                                StepCompleted(
                                    step_name=s.name,
                                    step_type=s.type,
                                    success=False,
                                    duration_ms=nested_duration,
                                    error=str(exc),
                                    step_path=s.name,
                                )
                            )
                        step_results.append(exc)
                        success = False
                        error_msg = str(exc)
                        failure_event.set()
                        break  # Stop iteration on error
            except BaseException as exc:
                success = False
                error_msg = str(exc)
                failure_event.set()

            iteration_results[index] = step_results

            # Calculate duration
            duration_ms = int((time.time() - start_time) * 1000)

            # Emit LoopIterationCompleted event
            completed_event = LoopIterationCompleted(
                step_name=step.name,
                iteration_index=index,
                success=success,
                duration_ms=duration_ms,
                error=error_msg,
                step_path=f"[{index}]",
            )
            if event_callback:
                await event_callback(completed_event)
            else:
                async with events_lock:
                    emitted_events.append(completed_event)

            logger.debug(
                "loop_iteration_completed",
                step_name=step.name,
                index=index,
                total_iterations=total_iterations,
                success=success,
                duration_ms=duration_ms,
            )

        if semaphore:
            async with semaphore:
                await _execute()
        else:
            await _execute()

    try:
        async with anyio.create_task_group() as tg:
            for idx, item in enumerate(items):
                # Skip iterations before the resume point
                if resume_iteration_index is not None and idx < resume_iteration_index:
                    logger.debug(
                        f"Skipping iteration {idx} (before resume iteration "
                        f"{resume_iteration_index})"
                    )
                    iteration_results[idx] = None  # Mark as skipped
                    continue

                # For the resume iteration, skip steps before the checkpoint
                skip_steps = None
                if (
                    resume_iteration_index is not None
                    and idx == resume_iteration_index
                    and resume_after_nested_step_index is not None
                ):
                    skip_steps = resume_after_nested_step_index

                tg.start_soon(run_iteration, idx, item, skip_steps)
    except ExceptionGroup:
        # Exceptions captured in iteration_results; we'll check below
        pass
    finally:
        # Restore parent loop context for proper nesting
        if parent_step_name is not None:
            context.iteration_context[_CURRENT_LOOP_STEP_KEY] = parent_step_name
        else:
            context.iteration_context.pop(_CURRENT_LOOP_STEP_KEY, None)

    # Check for failures and raise if any iterations failed
    _check_for_failures(iteration_results, step.name)

    return {"results": iteration_results, "events": emitted_events}
