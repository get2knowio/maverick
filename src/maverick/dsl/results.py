"""Result dataclasses for the Maverick Workflow DSL.

This module defines the result types returned by workflow and step executions,
including serialization logic for complex output types.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from maverick.dsl.types import StepType

if TYPE_CHECKING:
    pass


@dataclass(frozen=True, slots=True)
class StepResult:
    """Result of executing a single workflow step.

    Attributes:
        name: Step name (matches StepDefinition.name).
        step_type: Step type for categorization.
        success: True if step succeeded.
        output: Step output value (varies by step type).
        duration_ms: Execution time in milliseconds.
        error: Human-readable error string on failure.
    """

    name: str
    step_type: StepType
    success: bool
    output: Any
    duration_ms: int
    error: str | None = None

    def __post_init__(self) -> None:
        """Validate invariants."""
        if self.duration_ms < 0:
            raise ValueError("duration_ms must be non-negative")
        if not self.success and self.error is None:
            raise ValueError("Failed steps must have an error message")

    def to_dict(self) -> dict[str, Any]:
        """Serialize for logging/persistence.

        Returns:
            Dictionary representation with complex output types safely serialized.
        """
        return {
            "name": self.name,
            "step_type": self.step_type.value,
            "success": self.success,
            "output": self._serialize_output(),
            "duration_ms": self.duration_ms,
            "error": self.error,
        }

    def _serialize_output(self) -> Any:
        """Handle complex output types safely.

        Serialization logic:
        - Objects with to_dict(): call to_dict()
        - Primitives (str, int, float, bool, None): use directly
        - Lists/tuples: recursively serialize items
        - Dicts: recursively serialize values
        - Other types: convert to str

        Returns:
            Serialized output value.
        """
        if hasattr(self.output, "to_dict"):
            return self.output.to_dict()
        if isinstance(self.output, (str, int, float, bool, type(None))):
            return self.output
        if isinstance(self.output, (list, tuple)):
            return [self._serialize_item(item) for item in self.output]
        if isinstance(self.output, dict):
            return {k: self._serialize_item(v) for k, v in self.output.items()}
        return str(self.output)

    def _serialize_item(self, item: Any) -> Any:
        """Serialize a single item from a collection.

        Args:
            item: Item to serialize.

        Returns:
            Serialized item value.
        """
        if hasattr(item, "to_dict"):
            return item.to_dict()
        return (
            str(item)
            if not isinstance(item, (str, int, float, bool, type(None)))
            else item
        )


@dataclass(frozen=True, slots=True)
class WorkflowResult:
    """Complete workflow execution result.

    Attributes:
        workflow_name: Name from WorkflowDefinition.
        success: True if all steps succeeded.
        step_results: Ordered tuple of all step results.
        total_duration_ms: Total execution time.
        final_output: Workflow's final output.
    """

    workflow_name: str
    success: bool
    step_results: tuple[StepResult, ...]
    total_duration_ms: int
    final_output: Any

    def __post_init__(self) -> None:
        """Validate invariants."""
        if self.total_duration_ms < 0:
            raise ValueError("total_duration_ms must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        """Serialize for logging/persistence.

        Returns:
            Dictionary representation with all step results serialized.
        """
        return {
            "workflow_name": self.workflow_name,
            "success": self.success,
            "step_results": [sr.to_dict() for sr in self.step_results],
            "total_duration_ms": self.total_duration_ms,
            "final_output": str(self.final_output),
        }

    @property
    def failed_step(self) -> StepResult | None:
        """Return the first failed step, if any.

        Returns:
            First failed StepResult, or None if all steps succeeded.
        """
        for result in self.step_results:
            if not result.success:
                return result
        return None


@dataclass(frozen=True, slots=True)
class SubWorkflowInvocationResult:
    """Result from executing a sub-workflow.

    Exposes both final output and full workflow result to parent workflow.

    Attributes:
        final_output: The sub-workflow's final output.
        workflow_result: Full WorkflowResult for detailed inspection.
    """

    final_output: Any
    workflow_result: WorkflowResult

    def to_dict(self) -> dict[str, Any]:
        """Serialize for logging/persistence.

        Returns:
            Dictionary with summary information about the sub-workflow execution.
        """
        return {
            "final_output": str(self.final_output),
            "workflow_name": self.workflow_result.workflow_name,
            "success": self.workflow_result.success,
            "step_count": len(self.workflow_result.step_results),
        }
