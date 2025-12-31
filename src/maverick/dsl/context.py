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

    This context model is used by both the decorator DSL and serialization DSL
    to ensure consistency across the codebase.

    Attributes:
        inputs: Workflow input parameters (read-only after creation).
            These are the arguments passed when executing the workflow.
        results: Completed step results keyed by step name (mutable during execution).
            The workflow engine populates this dict as each step completes.
        workflow_name: Name of the workflow being executed. Used by serialization
            DSL for checkpointing and logging. Optional for decorator DSL.
        config: Shared services/configuration needed by steps (e.g., MaverickConfig).
            Must implement ConfigProtocol (validation_stages attribute and
            run_validation_stages method).
        iteration_context: Iteration variables for for_each loops (item, index).
            Only populated within parallel/for_each step execution contexts.
        _pending_rollbacks: List of rollback actions registered during execution.
            These are executed in reverse order if workflow fails.

    Example:
        >>> context = WorkflowContext(
        ...     inputs={"branch": "main", "issue_num": 42},
        ...     workflow_name="feature-workflow",
        ...     config=maverick_config
        ... )
        >>> # After step execution:
        >>> output = context.get_step_output("review_code")
    """

    inputs: dict[str, Any]
    results: dict[str, StepResult] = field(default_factory=dict)
    workflow_name: str | None = None
    config: ConfigProtocol | None = None
    iteration_context: dict[str, Any] = field(default_factory=dict)
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

    def store_step_output(
        self, step_name: str, output: Any, step_type: str = "python"
    ) -> None:
        """Store a step's output in the context.

        This method is used by the serialization DSL executor to store step outputs
        as StepResult objects. For decorator DSL, the engine stores StepResult
        objects directly in the results dict.

        Args:
            step_name: Name of the step.
            output: Output value from the step.
            step_type: Type of the step (for StepResult metadata). Can be lowercase.
        """
        from maverick.dsl.results import StepResult
        from maverick.dsl.types import StepType

        # Convert string step_type to StepType enum if needed
        if isinstance(step_type, str):
            # StepType values are lowercase (e.g., "python", "agent")
            try:
                step_type_enum = StepType(step_type.lower())
            except ValueError:
                # Fallback to PYTHON if unknown type
                step_type_enum = StepType.PYTHON
        else:
            step_type_enum = step_type

        # Create a StepResult with minimal metadata
        # Duration is unknown at this point, will be tracked by executor
        self.results[step_name] = StepResult(
            name=step_name,
            step_type=step_type_enum,
            success=True,  # Failures are handled by executor
            output=output,
            duration_ms=0,  # Will be updated by executor
        )

    def get_pending_rollbacks(self) -> list[RollbackRegistration]:
        """Get list of pending rollback registrations.

        Returns:
            List of RollbackRegistration objects in registration order.
        """
        return self._pending_rollbacks
