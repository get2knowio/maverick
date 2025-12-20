"""ErrorHandlerStep wrapper for error handling and fallback.

This module provides the ErrorHandlerStep class that wraps any StepDefinition
to add error handling with fallback steps or skip-on-error behavior.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from maverick.dsl.results import SkipMarker, StepResult
from maverick.dsl.steps.base import StepDefinition
from maverick.dsl.types import StepType

if TYPE_CHECKING:
    from maverick.dsl.context import WorkflowContext

# Type for on_error handler: receives context and failed result, returns fallback step
ErrorHandler = Callable[["WorkflowContext", StepResult], StepDefinition]


@dataclass(frozen=True, slots=True)
class ErrorHandlerStep(StepDefinition):
    """Wrapper that handles step failures with fallback or skip behavior.

    Can be configured to either:
    - Run a fallback step when the primary step fails (on_error)
    - Convert failure to a skip marker (skip_on_error)

    Attributes:
        inner: The wrapped step to execute.
        on_error_handler: Optional handler that returns a fallback step.
        skip_on_error: If True, convert failures to SkipMarker.
    """

    inner: StepDefinition
    on_error_handler: ErrorHandler | None = None
    skip_on_error: bool = False
    name: str = field(init=False)
    step_type: StepType = field(init=False)

    def __post_init__(self) -> None:
        """Initialize derived fields from inner step."""
        object.__setattr__(self, "name", self.inner.name)
        object.__setattr__(self, "step_type", self.inner.step_type)

    async def execute(self, context: WorkflowContext) -> StepResult:
        """Execute step with error handling.

        Args:
            context: Workflow execution context.

        Returns:
            StepResult from primary step, fallback step, or SkipMarker.
        """
        start_time = time.perf_counter()

        # Execute the primary step
        result = await self.inner.execute(context)

        if result.success:
            return result

        # Primary step failed - handle the error
        if self.skip_on_error:
            # Convert failure to skip
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            return StepResult(
                name=self.name,
                step_type=self.step_type,
                success=True,
                output=SkipMarker(reason="error_skipped"),
                duration_ms=duration_ms,
            )

        if self.on_error_handler is not None:
            # Get fallback step from handler
            fallback_step = self.on_error_handler(context, result)

            # Execute fallback
            fallback_result = await fallback_step.execute(context)

            # Return fallback result with original step name
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            return StepResult(
                name=self.name,
                step_type=self.step_type,
                success=fallback_result.success,
                output=fallback_result.output,
                duration_ms=duration_ms,
                error=fallback_result.error if not fallback_result.success else None,
            )

        # No error handling configured - pass through the failure
        return result

    def to_dict(self) -> dict[str, Any]:
        """Serialize for logging/persistence."""
        return {
            "name": self.name,
            "step_type": self.step_type.value,
            "wrapper": "error_handler",
            "skip_on_error": self.skip_on_error,
            "has_on_error_handler": self.on_error_handler is not None,
            "inner": self.inner.to_dict(),
        }
