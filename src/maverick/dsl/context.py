"""Workflow execution context for the Maverick workflow DSL.

This module defines the WorkflowContext dataclass that holds runtime state
during workflow execution, including inputs, step results, and shared configuration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from maverick.dsl.results import RollbackRegistration, StepResult
    from maverick.dsl.types import RollbackAction


class ConfigProtocol(Protocol):
    """Protocol for workflow configuration objects.

    This defines the interface that config objects must implement to be used
    with ValidateStep and other workflow components that need validation support.

    Attributes:
        validation_stages: Optional list of default validation stage names.

    Methods:
        run_validation_stages: Execute validation stages and return results.
    """

    validation_stages: list[str] | None

    async def run_validation_stages(self, stages: list[str]) -> Any:
        """Run validation stages and return results.

        Args:
            stages: List of validation stage names to execute.

        Returns:
            Validation result object with success status.
        """
        ...


@dataclass
class WorkflowContext:
    """Runtime context for workflow execution.

    The WorkflowContext is a mutable container that holds all runtime state
    during workflow execution. It provides access to workflow inputs, completed
    step results, and shared configuration/services.

    Attributes:
        inputs: Workflow input parameters (read-only after creation).
            These are the arguments passed when executing the workflow.
        results: Completed step results keyed by step name (mutable during execution).
            The workflow engine populates this dict as each step completes.
        config: Shared services/configuration needed by steps (e.g., MaverickConfig).
            Must implement ConfigProtocol (validation_stages attribute and
            run_validation_stages method).
        _pending_rollbacks: List of rollback actions registered during execution.
            These are executed in reverse order if workflow fails.

    Example:
        >>> context = WorkflowContext(
        ...     inputs={"branch": "main", "issue_num": 42},
        ...     config=maverick_config
        ... )
        >>> # After step execution:
        >>> output = context.get_step_output("review_code")
    """

    inputs: dict[str, Any]
    results: dict[str, StepResult] = field(default_factory=dict)
    config: ConfigProtocol | None = None
    _pending_rollbacks: list[RollbackRegistration] = field(default_factory=list)

    def get_step_output(self, step_name: str, default: Any = None) -> Any:
        """Get step output, returning default if step not found.

        This is a convenience method for retrieving the output of a previously
        executed step. Returns None (or default) if step hasn't been executed.

        Args:
            step_name: The name of the step whose output to retrieve.
            default: Value to return if step not found. Defaults to None.

        Returns:
            The output value from the specified step's execution, or default.
        """
        if step_name not in self.results:
            return default
        return self.results[step_name].output

    def register_rollback(self, step_name: str, action: RollbackAction) -> None:
        """Register a rollback action for a completed step.

        Args:
            step_name: Name of the step this rollback compensates.
            action: Callable to execute during rollback.
        """
        from maverick.dsl.results import RollbackRegistration

        self._pending_rollbacks.append(
            RollbackRegistration(step_name=step_name, action=action)
        )

    def is_step_skipped(self, step_name: str) -> bool:
        """Check if a step was skipped.

        Args:
            step_name: The name of the step to check.

        Returns:
            True if step exists and its output is a SkipMarker.
        """
        from maverick.dsl.results import SkipMarker

        output = self.get_step_output(step_name)
        return isinstance(output, SkipMarker)
