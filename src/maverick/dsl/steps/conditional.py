"""ConditionalStep wrapper for conditional execution.

This module provides the ConditionalStep class that wraps any StepDefinition
to add conditional execution via a predicate function.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from maverick.dsl.results import SkipMarker, StepResult
from maverick.dsl.steps.base import StepDefinition
from maverick.dsl.types import Predicate, StepType
from maverick.logging import get_logger

if TYPE_CHECKING:
    from maverick.dsl.context import WorkflowContext

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ConditionalStep(StepDefinition):
    """Wrapper that adds conditional execution to any step.

    The wrapped step only executes if the predicate returns True.
    If predicate returns False or raises an exception, the step is skipped.

    Attributes:
        inner: The wrapped step to conditionally execute.
        predicate: Callable that returns bool (sync or async).
            Receives WorkflowContext.
    """

    inner: StepDefinition
    predicate: Predicate
    # Override parent fields - populated in __post_init__
    name: str = field(init=False)
    step_type: StepType = field(init=False)

    def __post_init__(self) -> None:
        """Initialize name and step_type from inner step."""
        # Use object.__setattr__ since dataclass is frozen
        object.__setattr__(self, "name", self.inner.name)
        object.__setattr__(self, "step_type", self.inner.step_type)

    async def execute(self, context: WorkflowContext) -> StepResult:
        """Execute step conditionally based on predicate result.

        Args:
            context: Workflow execution context.

        Returns:
            StepResult from inner step if predicate is True,
            or SkipMarker result if False or exception.

        Raises:
            TypeError: If predicate returns non-bool value (FR-005b).
        """
        start_time = time.perf_counter()

        try:
            result = self.predicate(context)
            if asyncio.iscoroutine(result):
                result = await result

            if not isinstance(result, bool):
                # FR-005b: non-boolean returns fail workflow
                raise TypeError(
                    f"Predicate for step '{self.name}' must return bool, "
                    f"got {type(result).__name__}"
                )

            if not result:
                # Predicate returned False - skip step
                duration_ms = int((time.perf_counter() - start_time) * 1000)
                return StepResult(
                    name=self.name,
                    step_type=self.step_type,
                    success=True,
                    output=SkipMarker(reason="predicate_false"),
                    duration_ms=duration_ms,
                )

        except TypeError:
            # Re-raise TypeError for non-bool returns
            raise
        except Exception as e:
            # FR-005a: exceptions treated as false, log warning
            logger.warning(
                f"Predicate for step '{self.name}' raised "
                f"{type(e).__name__}: {e}, skipping"
            )
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            return StepResult(
                name=self.name,
                step_type=self.step_type,
                success=True,
                output=SkipMarker(reason="predicate_exception"),
                duration_ms=duration_ms,
            )

        # Predicate returned True - execute inner step
        return await self.inner.execute(context)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for logging/persistence."""
        return {
            "name": self.name,
            "step_type": self.step_type.value,
            "wrapper": "conditional",
            "inner": self.inner.to_dict(),
            "predicate": getattr(self.predicate, "__name__", "<lambda>"),
        }
