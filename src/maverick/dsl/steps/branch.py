"""BranchStep for selecting and executing one of multiple options.

This module provides branching control flow for workflows, allowing
conditional selection between multiple step options.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from maverick.dsl.results import BranchResult, StepResult
from maverick.dsl.steps.base import StepDefinition
from maverick.dsl.types import Predicate, StepType
from maverick.logging import get_logger

if TYPE_CHECKING:
    from maverick.dsl.context import WorkflowContext

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class BranchOption:
    """Single branch option in a branch step.

    Attributes:
        predicate: Callable that returns bool (sync or async).
            Receives WorkflowContext.
        step: StepDefinition to execute if predicate is True.
    """

    predicate: Predicate
    step: StepDefinition

    def to_dict(self) -> dict[str, Any]:
        """Serialize for logging/persistence."""
        return {
            "predicate": getattr(self.predicate, "__name__", "<lambda>"),
            "step": self.step.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class BranchStep(StepDefinition):
    """Step that selects and executes one of multiple options.

    Evaluates predicates in order and executes the first matching option.
    If no predicate matches, the workflow fails (FR-008).

    Attributes:
        name: Step name for the branch.
        options: Tuple of BranchOption to evaluate.
    """

    name: str
    options: tuple[BranchOption, ...]
    # Override parent field - return constant value
    step_type: StepType = field(init=False, default=StepType.BRANCH)

    async def execute(self, context: WorkflowContext) -> StepResult:
        """Execute the first matching branch option.

        Args:
            context: Workflow execution context.

        Returns:
            StepResult with BranchResult output on success,
            or failed result if no branch matches.
        """
        start_time = time.perf_counter()

        for i, option in enumerate(self.options):
            try:
                result = option.predicate(context)
                if asyncio.iscoroutine(result):
                    result = await result

                if result:
                    # Execute the matching branch's step
                    inner_result = await option.step.execute(context)
                    duration_ms = int((time.perf_counter() - start_time) * 1000)

                    return StepResult(
                        name=self.name,
                        step_type=self.step_type,
                        success=inner_result.success,
                        output=BranchResult(
                            selected_index=i,
                            selected_step_name=option.step.name,
                            inner_output=inner_result.output,
                        ),
                        duration_ms=duration_ms,
                        error=inner_result.error,
                    )
            except Exception as e:
                # Predicate raised exception - try next branch
                logger.debug(
                    f"Branch '{self.name}' option {i} predicate raised "
                    f"{type(e).__name__}: {e}, trying next option"
                )
                continue

        # No matching branch - fail workflow (FR-008)
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        return StepResult(
            name=self.name,
            step_type=self.step_type,
            success=False,
            output=None,
            duration_ms=duration_ms,
            error="No branch predicate matched",
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize for logging/persistence."""
        return {
            "name": self.name,
            "step_type": self.step_type.value,
            "options": [opt.to_dict() for opt in self.options],
        }
