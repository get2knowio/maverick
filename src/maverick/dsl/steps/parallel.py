"""ParallelStep for executing multiple steps.

This module provides the ParallelStep class that executes multiple
child steps. Initial implementation is sequential; interface supports
future concurrent execution.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from maverick.dsl.results import ParallelResult, StepResult
from maverick.dsl.steps.base import StepDefinition
from maverick.dsl.types import StepType

if TYPE_CHECKING:
    from maverick.dsl.context import WorkflowContext


@dataclass(frozen=True, slots=True)
class ParallelStep(StepDefinition):
    """Step that executes multiple steps (initially sequential).

    Child step names must be unique. Validated before any execution.

    Attributes:
        name: Step name for the parallel group.
        children: Tuple of steps to execute.
        step_type: Step type (always PARALLEL).
    """

    name: str
    step_type: StepType
    children: tuple[StepDefinition, ...]

    async def execute(self, context: WorkflowContext) -> StepResult:
        """Execute all child steps sequentially.

        Args:
            context: Workflow execution context.

        Returns:
            StepResult with ParallelResult output.
        """
        start_time = time.perf_counter()

        # FR-014a: validate unique names before execution
        names = [child.name for child in self.children]
        if len(names) != len(set(names)):
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            return StepResult(
                name=self.name,
                step_type=self.step_type,
                success=False,
                output=None,
                duration_ms=duration_ms,
                error="Parallel step contains duplicate child step names",
            )

        child_results: list[StepResult] = []
        for child in self.children:
            result = await child.execute(context)
            child_results.append(result)
            # Store result in context for access by other children
            context.results[child.name] = result
            if not result.success:
                break  # Fail fast

        duration_ms = int((time.perf_counter() - start_time) * 1000)
        all_success = all(r.success for r in child_results)

        return StepResult(
            name=self.name,
            step_type=self.step_type,
            success=all_success,
            output=ParallelResult(child_results=tuple(child_results)),
            duration_ms=duration_ms,
            error=child_results[-1].error if not all_success else None,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize for logging/persistence."""
        return {
            "name": self.name,
            "step_type": self.step_type.value,
            "children": [child.to_dict() for child in self.children],
        }
