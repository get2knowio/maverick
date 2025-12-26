"""Unit tests for async utilities."""

from __future__ import annotations

import pytest

from maverick.utils.async_utils import (
    ParallelExecutionError,
    run_parallel,
    run_parallel_with_concurrency,
)


class TestRunParallel:
    """Tests for run_parallel function."""

    @pytest.mark.asyncio
    async def test_empty_task_list_returns_empty_results(self) -> None:
        """Empty task list should return empty results."""
        results = await run_parallel([])
        assert results == []

    @pytest.mark.asyncio
    async def test_single_task_returns_result(self) -> None:
        """Single task should execute and return result."""

        async def task() -> str:
            return "hello"

        results = await run_parallel([task])
        assert results == ["hello"]

    @pytest.mark.asyncio
    async def test_multiple_tasks_preserve_order(self) -> None:
        """Results should be in the same order as input tasks."""
        import anyio

        async def task_a() -> str:
            await anyio.sleep(0.02)
            return "a"

        async def task_b() -> str:
            await anyio.sleep(0.01)
            return "b"

        async def task_c() -> str:
            return "c"

        results = await run_parallel([task_a, task_b, task_c])
        assert results == ["a", "b", "c"]

    @pytest.mark.asyncio
    async def test_exception_with_return_exceptions_false_raises(self) -> None:
        """When return_exceptions=False, should raise ParallelExecutionError."""

        async def success() -> str:
            return "ok"

        async def failure() -> str:
            raise ValueError("test error")

        with pytest.raises(ParallelExecutionError) as exc_info:
            await run_parallel([success, failure], return_exceptions=False)

        assert len(exc_info.value.exceptions) == 1
        assert isinstance(exc_info.value.exceptions[0], ValueError)
        assert "test error" in str(exc_info.value.exceptions[0])
        # Results should contain both the success and the exception
        assert exc_info.value.results[0] == "ok"
        assert isinstance(exc_info.value.results[1], ValueError)

    @pytest.mark.asyncio
    async def test_exception_with_return_exceptions_true_captures(self) -> None:
        """When return_exceptions=True, exceptions should be in results list."""

        async def success() -> str:
            return "ok"

        async def failure() -> str:
            raise ValueError("test error")

        results = await run_parallel([success, failure], return_exceptions=True)

        assert results[0] == "ok"
        assert isinstance(results[1], ValueError)
        assert "test error" in str(results[1])

    @pytest.mark.asyncio
    async def test_multiple_exceptions_collected(self) -> None:
        """Multiple exceptions should all be collected."""

        async def fail_a() -> str:
            raise ValueError("error a")

        async def fail_b() -> str:
            raise KeyError("error b")

        async def fail_c() -> str:
            raise RuntimeError("error c")

        with pytest.raises(ParallelExecutionError) as exc_info:
            await run_parallel([fail_a, fail_b, fail_c])

        assert len(exc_info.value.exceptions) == 3
        exception_types = {type(e) for e in exc_info.value.exceptions}
        assert exception_types == {ValueError, KeyError, RuntimeError}

    @pytest.mark.asyncio
    async def test_tasks_run_concurrently(self) -> None:
        """Tasks should actually run concurrently, not sequentially."""
        import time

        import anyio

        execution_times: list[float] = []
        start_time = time.monotonic()

        async def timed_task(delay: float) -> float:
            await anyio.sleep(delay)
            elapsed = time.monotonic() - start_time
            execution_times.append(elapsed)
            return elapsed

        # If running sequentially, total time would be 0.1 + 0.1 + 0.1 = 0.3s
        # If running concurrently, total time should be ~0.1s
        await run_parallel(
            [
                lambda: timed_task(0.1),
                lambda: timed_task(0.1),
                lambda: timed_task(0.1),
            ]
        )

        # All tasks should complete around the same time (concurrent execution)
        max_time = max(execution_times)
        min_time = min(execution_times)
        assert max_time - min_time < 0.05  # Tasks completed within 50ms of each other
        assert max_time < 0.2  # Total time should be much less than sequential

    @pytest.mark.asyncio
    async def test_lambda_tasks_work(self) -> None:
        """Lambda expressions should work as task definitions."""
        results = await run_parallel(
            [
                lambda: async_return(1),
                lambda: async_return(2),
                lambda: async_return(3),
            ]
        )
        assert results == [1, 2, 3]


class TestRunParallelWithConcurrency:
    """Tests for run_parallel_with_concurrency function."""

    @pytest.mark.asyncio
    async def test_empty_task_list_returns_empty_results(self) -> None:
        """Empty task list should return empty results."""
        results = await run_parallel_with_concurrency([], max_concurrent=5)
        assert results == []

    @pytest.mark.asyncio
    async def test_max_concurrent_less_than_one_raises(self) -> None:
        """max_concurrent < 1 should raise ValueError."""
        with pytest.raises(ValueError, match="max_concurrent must be at least 1"):
            await run_parallel_with_concurrency([], max_concurrent=0)

    @pytest.mark.asyncio
    async def test_respects_concurrency_limit(self) -> None:
        """Should respect the maximum concurrency limit."""
        import anyio

        max_concurrent_observed = 0
        current_concurrent = 0
        lock = anyio.Lock()

        async def tracked_task(index: int) -> int:
            nonlocal max_concurrent_observed, current_concurrent
            async with lock:
                current_concurrent += 1
                if current_concurrent > max_concurrent_observed:
                    max_concurrent_observed = current_concurrent
            await anyio.sleep(0.05)
            async with lock:
                current_concurrent -= 1
            return index

        # Run 10 tasks with max 3 concurrent
        tasks = [lambda i=i: tracked_task(i) for i in range(10)]
        results = await run_parallel_with_concurrency(tasks, max_concurrent=3)

        assert max_concurrent_observed <= 3
        assert len(results) == 10
        # Verify all tasks completed
        assert sorted(results) == list(range(10))

    @pytest.mark.asyncio
    async def test_preserves_order(self) -> None:
        """Results should be in the same order as input tasks."""
        import anyio

        async def task(value: int) -> int:
            await anyio.sleep(0.01 * (10 - value))  # Shorter delays for higher values
            return value

        tasks = [lambda v=v: task(v) for v in range(5)]
        results = await run_parallel_with_concurrency(tasks, max_concurrent=2)

        assert results == [0, 1, 2, 3, 4]

    @pytest.mark.asyncio
    async def test_exception_handling_return_exceptions_true(self) -> None:
        """Exceptions should be captured when return_exceptions=True."""

        async def success() -> str:
            return "ok"

        async def failure() -> str:
            raise ValueError("fail")

        results = await run_parallel_with_concurrency(
            [success, failure],
            max_concurrent=2,
            return_exceptions=True,
        )

        assert results[0] == "ok"
        assert isinstance(results[1], ValueError)

    @pytest.mark.asyncio
    async def test_exception_handling_return_exceptions_false(self) -> None:
        """Should raise ParallelExecutionError when return_exceptions=False."""

        async def success() -> str:
            return "ok"

        async def failure() -> str:
            raise ValueError("fail")

        with pytest.raises(ParallelExecutionError):
            await run_parallel_with_concurrency(
                [success, failure],
                max_concurrent=2,
                return_exceptions=False,
            )


class TestParallelExecutionError:
    """Tests for ParallelExecutionError exception class."""

    def test_error_message(self) -> None:
        """Error message should be accessible."""
        exc = ParallelExecutionError(
            "2 tasks failed",
            exceptions=(ValueError("a"), KeyError("b")),
            results=("ok", ValueError("a"), KeyError("b")),
        )
        assert str(exc) == "2 tasks failed"

    def test_exceptions_accessible(self) -> None:
        """Exceptions tuple should be accessible."""
        val_err = ValueError("a")
        key_err = KeyError("b")
        exc = ParallelExecutionError(
            "test",
            exceptions=(val_err, key_err),
            results=(),
        )
        assert exc.exceptions == (val_err, key_err)

    def test_results_accessible(self) -> None:
        """Results tuple should be accessible."""
        val_err = ValueError("a")
        exc = ParallelExecutionError(
            "test",
            exceptions=(val_err,),
            results=("success", val_err),
        )
        assert exc.results[0] == "success"
        assert exc.results[1] is val_err


# Helper function for tests
async def async_return(value: int) -> int:
    """Simple async function that returns a value."""
    return value
