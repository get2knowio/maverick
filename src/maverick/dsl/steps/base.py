"""Base class for all workflow step definitions.

This module defines the abstract StepDefinition class that all concrete
step types (PythonStep, AgentStep, GenerateStep, ValidateStep, SubWorkflowStep)
must inherit from.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from maverick.dsl.context import WorkflowContext
    from maverick.dsl.results import StepResult

from maverick.dsl.types import StepType


@dataclass(frozen=True, slots=True)
class StepDefinition(ABC):
    """Abstract base for step definitions.

    All step types must implement execute() and to_dict().

    Attributes:
        name: Unique step name within workflow.
        step_type: Categorization for reporting.
    """

    name: str
    step_type: StepType

    @abstractmethod
    async def execute(self, context: WorkflowContext) -> StepResult:
        """Execute step and return result.

        Args:
            context: Workflow execution context with inputs and prior step results.

        Returns:
            StepResult with success status and output.
        """
        ...

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        """Serialize step definition for logging/persistence.

        Returns:
            Dictionary representation of this step.
        """
        ...
