"""Result dataclasses for the Maverick Workflow DSL.

This module defines the result types returned by workflow and step executions,
including serialization logic for complex output types.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from maverick.dsl.types import StepType

if TYPE_CHECKING:
    from maverick.dsl.types import RollbackAction


@dataclass(frozen=True, slots=True)
class SkipMarker:
    """Marker indicating step was skipped.

    Attributes:
        reason: Why the step was skipped.
            - "predicate_false": .when() predicate returned False
            - "predicate_exception": .when() predicate raised exception
            - "error_skipped": .skip_on_error() converted failure to skip
    """

    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"skipped": True, "reason": self.reason}


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

    @classmethod
    def create_success(
        cls,
        name: str,
        step_type: StepType,
        output: Any,
        duration_ms: int,
    ) -> StepResult:
        """Create a successful StepResult.

        Factory method for cleaner instantiation of successful results.

        Args:
            name: Step name.
            step_type: Type of step.
            output: Output data from the step.
            duration_ms: Execution duration in milliseconds.

        Returns:
            A StepResult instance with success=True and error=None.

        Example:
            >>> result = StepResult.create_success(
            ...     name="my-step",
            ...     step_type=StepType.PYTHON,
            ...     output={"data": "value"},
            ...     duration_ms=150,
            ... )
        """
        return cls(
            name=name,
            step_type=step_type,
            success=True,
            output=output,
            duration_ms=duration_ms,
            error=None,
        )

    @classmethod
    def create_failure(
        cls,
        name: str,
        step_type: StepType,
        duration_ms: int,
        error: str,
        output: Any = None,
    ) -> StepResult:
        """Create a failed StepResult.

        Factory method for cleaner instantiation of failed results.

        Args:
            name: Step name.
            step_type: Type of step.
            duration_ms: Execution duration in milliseconds.
            error: Error message describing the failure.
            output: Optional output data (defaults to None).

        Returns:
            A StepResult instance with success=False.

        Example:
            >>> result = StepResult.create_failure(
            ...     name="my-step",
            ...     step_type=StepType.PYTHON,
            ...     duration_ms=50,
            ...     error="Connection timeout",
            ... )
        """
        return cls(
            name=name,
            step_type=step_type,
            success=False,
            output=output,
            duration_ms=duration_ms,
            error=error,
        )

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
        rollback_errors: Errors from rollback execution (if any).
    """

    workflow_name: str
    success: bool
    step_results: tuple[StepResult, ...]
    total_duration_ms: int
    final_output: Any
    rollback_errors: tuple[RollbackError, ...] = ()

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
            "rollback_errors": [re.to_dict() for re in self.rollback_errors],
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

    @property
    def had_rollback_failures(self) -> bool:
        """True if any rollback actions failed."""
        return len(self.rollback_errors) > 0


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


@dataclass(frozen=True, slots=True)
class RollbackError:
    """Error from a failed rollback action.

    Attributes:
        step_name: Name of the step whose rollback failed.
        error: Human-readable error message.
    """

    step_name: str
    error: str

    def to_dict(self) -> dict[str, Any]:
        return {"step_name": self.step_name, "error": self.error}


@dataclass(frozen=True, slots=True)
class RollbackRegistration:
    """A registered rollback action for a completed step.

    Attributes:
        step_name: Name of the step this rollback compensates.
        action: Callable to execute during rollback.
    """

    step_name: str
    action: RollbackAction


@dataclass(frozen=True, slots=True)
class BranchResult:
    """Output of a branch step execution.

    Attributes:
        selected_index: Zero-based index of the selected branch option.
        selected_step_name: Name of the step that was executed.
        inner_output: Output from the executed step.
    """

    selected_index: int
    selected_step_name: str
    inner_output: Any

    def to_dict(self) -> dict[str, Any]:
        """Serialize for logging/persistence."""
        return {
            "selected_index": self.selected_index,
            "selected_step_name": self.selected_step_name,
            "inner_output": str(self.inner_output),
        }


@dataclass(frozen=True, slots=True)
class ParallelResult:
    """Output of a parallel step execution.

    Attributes:
        child_results: Tuple of StepResult objects in input order.
    """

    child_results: tuple[StepResult, ...]

    def to_dict(self) -> dict[str, Any]:
        """Serialize for logging/persistence."""
        return {
            "child_count": len(self.child_results),
            "children": [r.to_dict() for r in self.child_results],
            "all_success": all(r.success for r in self.child_results),
        }

    def __getitem__(self, index: int) -> StepResult:
        """Access child result by index."""
        return self.child_results[index]

    def get_output(self, step_name: str) -> Any:
        """Get child step output by name.

        Args:
            step_name: Name of child step.

        Returns:
            Output from the named child step.

        Raises:
            KeyError: If step_name not found in children.
        """
        for result in self.child_results:
            if result.name == step_name:
                return result.output
        raise KeyError(f"Child step '{step_name}' not found")
