"""RollbackStep wrapper for rollback/compensation support.

This module provides the RollbackStep class that wraps any StepDefinition
to register a rollback action when the step succeeds.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from maverick.dsl.results import StepResult
from maverick.dsl.steps.base import StepDefinition
from maverick.dsl.types import RollbackAction, StepType

if TYPE_CHECKING:
    from maverick.dsl.context import WorkflowContext


@dataclass(frozen=True, slots=True)
class RollbackStep(StepDefinition):
    """Wrapper that registers a rollback action when step succeeds.

    The rollback action is only registered if the wrapped step succeeds.
    Rollbacks are executed in reverse order by the engine if the workflow fails.

    Attributes:
        inner: The wrapped step to execute.
        rollback_action: Callable to execute during rollback (sync or async).
    """

    inner: StepDefinition
    rollback_action: RollbackAction
    name: str = field(init=False)
    step_type: StepType = field(init=False)

    def __post_init__(self) -> None:
        """Initialize derived fields from inner step."""
        object.__setattr__(self, "name", self.inner.name)
        object.__setattr__(self, "step_type", self.inner.step_type)

    async def execute(self, context: WorkflowContext) -> StepResult:
        """Execute step and register rollback on success.

        Args:
            context: Workflow execution context.

        Returns:
            StepResult from inner step execution.
        """
        result = await self.inner.execute(context)

        if result.success:
            # Register rollback action for this step
            context.register_rollback(self.name, self.rollback_action)

        return result

    def to_dict(self) -> dict[str, Any]:
        """Serialize for logging/persistence."""
        return {
            "name": self.name,
            "step_type": self.step_type.value,
            "wrapper": "rollback",
            "rollback_action": getattr(self.rollback_action, "__name__", "<lambda>"),
            "inner": self.inner.to_dict(),
        }
