"""Async utilities for structured concurrency using anyio.

This module provides shared async primitives for parallel task execution
with proper exception handling and structured concurrency guarantees.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import anyio

T = TypeVar("T")


class ParallelExecutionError(Exception):
    """Exception raised when one or more parallel tasks fail.

    This exception collects all exceptions from failed tasks, making them
    accessible for inspection while providing a meaningful error message.

    Attributes:
        exceptions: Tuple of all exceptions from failed tasks.
        results: Tuple of results/exceptions in order of task completion.
    """

    def __init__(
        self,
        message: str,
        exceptions: tuple[BaseException, ...],
        results: tuple[Any | BaseException, ...],
    ) -> None:
        """Initialize ParallelExecutionError.

        Args:
            message: Human-readable error message.
            exceptions: Tuple of exceptions from failed tasks.
            results: Tuple of all results (successful values and exceptions).
        """
        super().__init__(message)
        self.exceptions = exceptions
        self.results = results


async def run_parallel(
    tasks: list[Callable[[], Awaitable[T]]],
    *,
    return_exceptions: bool = False,
) -> list[T | BaseException]:
    """Execute multiple async tasks concurrently using anyio TaskGroup.

    Uses structured concurrency via anyio.create_task_group() to ensure all
    spawned tasks complete (or are cancelled) before returning.

    Args:
        tasks: List of async callables (zero-argument coroutine functions).
            Each callable should return an awaitable when called.
        return_exceptions: If True, exceptions are collected in the results
            list instead of being raised. If False (default), raises
            ParallelExecutionError when any task fails.

    Returns:
        List of results in the same order as the input tasks.
        If return_exceptions=True, failed tasks have their exception
        in the corresponding position.

    Raises:
        ParallelExecutionError: If any task fails and return_exceptions=False.
            The exception contains all collected exceptions and partial results.

    Example:
        ```python
        async def fetch_user(user_id: int) -> dict:
            ...

        # Execute with exceptions returned in results
        results = await run_parallel(
            [lambda: fetch_user(1), lambda: fetch_user(2)],
            return_exceptions=True,
        )

        # Execute with exception raised on failure
        try:
            results = await run_parallel([
                lambda: fetch_user(1),
                lambda: fetch_user(2),
            ])
        except ParallelExecutionError as e:
            print(f"Failed tasks: {len(e.exceptions)}")
        ```
    """
    if not tasks:
        return []

    # Pre-allocate results list with sentinel values
    results: list[T | BaseException | None] = [None] * len(tasks)
    exceptions_collected: list[BaseException] = []

    async def run_task(index: int, task_fn: Callable[[], Awaitable[T]]) -> None:
        """Execute a single task and store result or exception."""
        try:
            results[index] = await task_fn()
        except BaseException as exc:
            results[index] = exc
            exceptions_collected.append(exc)

    try:
        async with anyio.create_task_group() as tg:
            for idx, task_fn in enumerate(tasks):
                tg.start_soon(run_task, idx, task_fn)
    except ExceptionGroup:
        # anyio wraps exceptions in ExceptionGroup; we've already captured them
        # in exceptions_collected, so just continue to error handling below
        pass

    # Cast results to final type (None sentinels replaced by actual values)
    final_results = list(results)

    if exceptions_collected and not return_exceptions:
        raise ParallelExecutionError(
            f"{len(exceptions_collected)} task(s) failed during parallel execution",
            exceptions=tuple(exceptions_collected),
            results=tuple(final_results),
        )

    return final_results  # type: ignore[return-value]


async def run_parallel_with_concurrency(
    tasks: list[Callable[[], Awaitable[T]]],
    *,
    max_concurrent: int,
    return_exceptions: bool = False,
) -> list[T | BaseException]:
    """Execute tasks with a concurrency limit using anyio CapacityLimiter.

    Similar to run_parallel but limits the number of concurrent tasks.
    Useful for rate-limiting or resource-constrained operations.

    Args:
        tasks: List of async callables (zero-argument coroutine functions).
        max_concurrent: Maximum number of tasks to run concurrently.
        return_exceptions: If True, exceptions are collected in results.
            If False (default), raises ParallelExecutionError on failure.

    Returns:
        List of results in the same order as the input tasks.

    Raises:
        ParallelExecutionError: If any task fails and return_exceptions=False.
        ValueError: If max_concurrent is less than 1.

    Example:
        ```python
        # Process 100 items with max 10 concurrent
        results = await run_parallel_with_concurrency(
            [lambda item=i: process(item) for i in range(100)],
            max_concurrent=10,
        )
        ```
    """
    if max_concurrent < 1:
        raise ValueError("max_concurrent must be at least 1")

    if not tasks:
        return []

    results: list[T | BaseException | None] = [None] * len(tasks)
    exceptions_collected: list[BaseException] = []
    limiter = anyio.CapacityLimiter(max_concurrent)

    async def run_task(index: int, task_fn: Callable[[], Awaitable[T]]) -> None:
        """Execute a single task with concurrency limit."""
        async with limiter:
            try:
                results[index] = await task_fn()
            except BaseException as exc:
                results[index] = exc
                exceptions_collected.append(exc)

    try:
        async with anyio.create_task_group() as tg:
            for idx, task_fn in enumerate(tasks):
                tg.start_soon(run_task, idx, task_fn)
    except ExceptionGroup:
        # Exceptions already captured in exceptions_collected
        pass

    final_results = list(results)

    if exceptions_collected and not return_exceptions:
        raise ParallelExecutionError(
            f"{len(exceptions_collected)} task(s) failed during parallel execution",
            exceptions=tuple(exceptions_collected),
            results=tuple(final_results),
        )

    return final_results  # type: ignore[return-value]
