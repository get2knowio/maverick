"""CheckpointStep wrapper for workflow resumability.

This module provides the CheckpointStep class that marks a step
as a checkpoint boundary for workflow resumption.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from maverick.dsl.results import StepResult
from maverick.dsl.steps.base import StepDefinition
from maverick.dsl.types import StepType

if TYPE_CHECKING:
    from maverick.dsl.context import WorkflowContext


@dataclass(frozen=True, slots=True)
class CheckpointStep(StepDefinition):
    """Wrapper that marks a step as a checkpoint boundary.

    When the wrapped step succeeds, the engine will save workflow
    state to the checkpoint store (if configured).

    Attributes:
        inner: The wrapped step to execute.
        is_checkpoint: Flag indicating this step is a checkpoint boundary.
    """

    inner: StepDefinition
    is_checkpoint: bool = True
    name: str = field(init=False)
    step_type: StepType = field(init=False)

    def __post_init__(self) -> None:
        """Initialize derived fields from inner step."""
        object.__setattr__(self, "name", self.inner.name)
        object.__setattr__(self, "step_type", self.inner.step_type)

    async def execute(self, context: WorkflowContext) -> StepResult:
        """Execute inner step.

        The checkpoint save is handled by the engine, not this step.

        Args:
            context: Workflow execution context.

        Returns:
            StepResult from inner step execution.
        """
        return await self.inner.execute(context)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for logging/persistence."""
        return {
            "name": self.name,
            "step_type": self.step_type.value,
            "wrapper": "checkpoint",
            "is_checkpoint": self.is_checkpoint,
            "inner": self.inner.to_dict(),
        }
