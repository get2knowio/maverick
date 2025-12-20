"""Workflow execution context for the Maverick workflow DSL.

This module defines the WorkflowContext dataclass that holds runtime state
during workflow execution, including inputs, step results, and shared configuration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from maverick.dsl.results import StepResult


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
            This can be any object that steps need to access during execution.

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
    config: Any = None

    def get_step_output(self, step_name: str) -> Any:
        """Access prior step output via results[step_name].output.

        This is a convenience method for retrieving the output of a previously
        executed step. Steps can use this to access results from earlier steps
        in the workflow.

        Args:
            step_name: The name of the step whose output to retrieve.

        Returns:
            The output value from the specified step's execution.

        Raises:
            KeyError: If the step name is not found in results (either the step
                hasn't been executed yet, or the name is invalid).

        Example:
            >>> context.get_step_output("parse_tasks")
            ["task1", "task2", "task3"]
        """
        if step_name not in self.results:
            raise KeyError(f"Step '{step_name}' not found in results")
        return self.results[step_name].output
