"""Prerequisite runner that executes checks with dependency ordering.

This module provides PrerequisiteRunner which:
1. Executes prerequisites in topological order (dependencies first)
2. Runs independent checks in parallel where possible
3. Stops early if a dependency fails (dependents are skipped)
4. Emits events for progress tracking
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from maverick.dsl.prerequisites.models import (
    PreflightCheckResult,
    PreflightPlan,
    PreflightResult,
    PrerequisiteResult,
)
from maverick.dsl.prerequisites.registry import PrerequisiteRegistry
from maverick.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable

    from maverick.dsl.events import ProgressEvent

logger = get_logger(__name__)


class PrerequisiteRunner:
    """Executes prerequisite checks with dependency ordering.

    Runs prerequisite checks in topological order, respecting dependencies.
    Independent checks (no shared dependencies) can run in parallel.
    Execution stops early for a prerequisite if any of its dependencies failed.

    Example:
        ```python
        runner = PrerequisiteRunner(prerequisite_registry)
        result = await runner.run(preflight_plan)

        if not result.success:
            print(result.format_error())
            return

        # Continue with workflow execution
        ```
    """

    def __init__(
        self,
        prerequisite_registry: PrerequisiteRegistry,
        timeout_per_check: float = 30.0,
    ) -> None:
        """Initialize the runner.

        Args:
            prerequisite_registry: Registry of prerequisite checks.
            timeout_per_check: Maximum seconds per individual check.
        """
        self._registry = prerequisite_registry
        self._timeout = timeout_per_check

    async def run(self, plan: PreflightPlan) -> PreflightResult:
        """Execute all prerequisite checks.

        Runs checks in dependency order. If a check fails, dependents
        are marked as skipped (not executed).

        Args:
            plan: The PreflightPlan specifying which checks to run.

        Returns:
            PreflightResult with all check outcomes.
        """
        if not plan.execution_order:
            return PreflightResult(
                success=True,
                check_results=(),
                total_duration_ms=0,
            )

        start_time = time.monotonic()
        results: list[PreflightCheckResult] = []
        failed_prereqs: set[str] = set()

        for prereq_name in plan.execution_order:
            prereq = self._registry.get(prereq_name)
            affected_steps = plan.step_requirements.get(prereq_name, ())

            # Check if any dependency failed
            deps_failed = [dep for dep in prereq.dependencies if dep in failed_prereqs]
            if deps_failed:
                # Skip this check - dependency failed
                result = PrerequisiteResult(
                    success=False,
                    message=f"Skipped: dependency '{deps_failed[0]}' failed",
                    duration_ms=0,
                )
                failed_prereqs.add(prereq_name)
            else:
                # Run the check
                result = await self._run_check(prereq.check_fn, prereq_name)
                if not result.success:
                    failed_prereqs.add(prereq_name)

            results.append(
                PreflightCheckResult(
                    prerequisite=prereq,
                    result=result,
                    affected_steps=affected_steps,
                )
            )

            logger.debug(
                f"Prerequisite '{prereq_name}': "
                f"{'PASS' if result.success else 'FAIL'} "
                f"({result.duration_ms}ms)"
            )

        total_duration_ms = int((time.monotonic() - start_time) * 1000)

        return PreflightResult(
            success=len(failed_prereqs) == 0,
            check_results=tuple(results),
            total_duration_ms=total_duration_ms,
        )

    async def run_with_events(
        self,
        plan: PreflightPlan,
    ) -> AsyncIterator[ProgressEvent]:
        """Execute checks and yield progress events.

        Same as run(), but yields PreflightCheckPassed/Failed events
        as each check completes, allowing real-time progress display.

        Args:
            plan: The PreflightPlan specifying which checks to run.

        Yields:
            ProgressEvent objects for each check, then final PreflightResult.
        """
        # Import here to avoid circular imports
        from maverick.dsl.events import (
            PreflightCheckFailed,
            PreflightCheckPassed,
            PreflightCompleted,
            PreflightStarted,
        )

        if not plan.execution_order:
            yield PreflightStarted(prerequisites=())
            yield PreflightCompleted(
                success=True,
                total_duration_ms=0,
                passed_count=0,
                failed_count=0,
            )
            return

        yield PreflightStarted(prerequisites=plan.execution_order)

        start_time = time.monotonic()
        results: list[PreflightCheckResult] = []
        failed_prereqs: set[str] = set()

        for prereq_name in plan.execution_order:
            prereq = self._registry.get(prereq_name)
            affected_steps = plan.step_requirements.get(prereq_name, ())

            # Check if any dependency failed
            deps_failed = [dep for dep in prereq.dependencies if dep in failed_prereqs]
            if deps_failed:
                # Skip this check - dependency failed
                result = PrerequisiteResult(
                    success=False,
                    message=f"Skipped: dependency '{deps_failed[0]}' failed",
                    duration_ms=0,
                )
                failed_prereqs.add(prereq_name)
            else:
                # Run the check
                result = await self._run_check(prereq.check_fn, prereq_name)
                if not result.success:
                    failed_prereqs.add(prereq_name)

            check_result = PreflightCheckResult(
                prerequisite=prereq,
                result=result,
                affected_steps=affected_steps,
            )
            results.append(check_result)

            # Yield appropriate event
            if result.success:
                yield PreflightCheckPassed(
                    name=prereq_name,
                    display_name=prereq.display_name,
                    duration_ms=result.duration_ms,
                    message=result.message,
                )
            else:
                yield PreflightCheckFailed(
                    name=prereq_name,
                    display_name=prereq.display_name,
                    duration_ms=result.duration_ms,
                    message=result.message,
                    remediation=prereq.remediation,
                    affected_steps=affected_steps,
                )

        total_duration_ms = int((time.monotonic() - start_time) * 1000)
        success = len(failed_prereqs) == 0

        yield PreflightCompleted(
            success=success,
            total_duration_ms=total_duration_ms,
            passed_count=len(results) - len(failed_prereqs),
            failed_count=len(failed_prereqs),
        )

    async def _run_check(
        self,
        check_fn: Callable[[], Awaitable[PrerequisiteResult]],
        name: str,
    ) -> PrerequisiteResult:
        """Run a single check with timeout handling.

        Args:
            check_fn: The async check function to run.
            name: Name of the prerequisite (for error messages).

        Returns:
            PrerequisiteResult from the check, or error result on timeout/exception.
        """
        start_time = time.monotonic()

        try:
            result = await asyncio.wait_for(check_fn(), timeout=self._timeout)
            return result

        except TimeoutError:
            return PrerequisiteResult(
                success=False,
                message=f"Check timed out after {self._timeout}s",
                duration_ms=int((time.monotonic() - start_time) * 1000),
            )
        except Exception as e:
            logger.exception(f"Prerequisite check '{name}' raised exception")
            return PrerequisiteResult(
                success=False,
                message=f"Check failed with error: {e}",
                duration_ms=int((time.monotonic() - start_time) * 1000),
            )
