"""RetryStep wrapper for retry with exponential backoff.

This module provides the RetryStep class that wraps any StepDefinition
to add automatic retry behavior with exponential backoff.
"""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from maverick.dsl.results import StepResult
from maverick.dsl.steps.base import StepDefinition
from maverick.dsl.types import StepType

if TYPE_CHECKING:
    from maverick.dsl.context import WorkflowContext


@dataclass(frozen=True, slots=True)
class RetryStep(StepDefinition):
    """Wrapper that retries a step on failure with exponential backoff.

    Attributes:
        inner: The wrapped step to retry.
        max_attempts: Maximum number of attempts (including first try).
        backoff_base: Base delay in seconds for exponential backoff.
        backoff_max: Maximum delay cap in seconds.
        jitter: Whether to add random jitter to delays.
    """

    inner: StepDefinition
    max_attempts: int
    backoff_base: float = 1.0
    backoff_max: float = 60.0
    jitter: bool = True
    name: str = field(init=False)
    step_type: StepType = field(init=False)

    def __post_init__(self) -> None:
        """Initialize derived fields from inner step."""
        object.__setattr__(self, "name", self.inner.name)
        object.__setattr__(self, "step_type", self.inner.step_type)

    async def execute(self, context: WorkflowContext) -> StepResult:
        """Execute step with retry logic.

        Args:
            context: Workflow execution context.

        Returns:
            StepResult from successful attempt or final failed attempt.
        """
        start_time = time.perf_counter()
        last_result: StepResult | None = None

        for attempt in range(1, self.max_attempts + 1):
            result = await self.inner.execute(context)

            if result.success:
                # Adjust duration to include retry time
                total_duration = int((time.perf_counter() - start_time) * 1000)
                return StepResult(
                    name=result.name,
                    step_type=result.step_type,
                    success=True,
                    output=result.output,
                    duration_ms=total_duration,
                )

            last_result = result

            # Don't sleep after the last attempt
            if attempt < self.max_attempts:
                delay = self._calculate_delay(attempt)
                await asyncio.sleep(delay)

        # All attempts exhausted - return final failure
        # last_result is guaranteed to be non-None here since max_attempts >= 1
        assert last_result is not None, "last_result should be set after at least one attempt"
        total_duration = int((time.perf_counter() - start_time) * 1000)
        return StepResult(
            name=last_result.name,
            step_type=last_result.step_type,
            success=False,
            output=last_result.output,
            duration_ms=total_duration,
            error=last_result.error,
        )

    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay for next retry attempt.

        Args:
            attempt: Current attempt number (1-based).

        Returns:
            Delay in seconds with optional jitter.
        """
        # Exponential backoff: base * 2^(attempt-1), capped at max
        delay: float = min(self.backoff_base * (2 ** (attempt - 1)), self.backoff_max)

        if self.jitter:
            # Apply jitter: multiply by random factor between 0.5 and 1.5
            delay = delay * (0.5 + random.random())

        return delay

    def to_dict(self) -> dict[str, Any]:
        """Serialize for logging/persistence."""
        return {
            "name": self.name,
            "step_type": self.step_type.value,
            "wrapper": "retry",
            "max_attempts": self.max_attempts,
            "backoff_base": self.backoff_base,
            "backoff_max": self.backoff_max,
            "jitter": self.jitter,
            "inner": self.inner.to_dict(),
        }
