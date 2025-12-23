from __future__ import annotations

from maverick.exceptions.base import MaverickError


class WorkflowError(MaverickError):
    """Base exception for workflow-related errors.

    Attributes:
        message: Human-readable error message.
        workflow_name: Name of the workflow that failed (if known).
    """

    def __init__(self, message: str, workflow_name: str | None = None) -> None:
        """Initialize the WorkflowError.

        Args:
            message: Human-readable error message.
            workflow_name: Optional name of the workflow that failed.
        """
        self.workflow_name = workflow_name
        super().__init__(message)


class DuplicateStepNameError(WorkflowError):
    """Raised when two steps share the same name within a workflow (FR-005).

    Attributes:
        message: Human-readable error message.
        step_name: The duplicate step name.
    """

    def __init__(self, step_name: str) -> None:
        """Initialize the DuplicateStepNameError.

        Args:
            step_name: The duplicate step name.
        """
        self.step_name = step_name
        super().__init__(
            f"Duplicate step name: '{step_name}'. "
            f"Step names must be unique within a workflow.",
        )


class StagesNotFoundError(WorkflowError):
    """Raised when validate step references unknown stages config key.

    Attributes:
        message: Human-readable error message.
        config_key: The config key that was not found.
    """

    def __init__(self, config_key: str) -> None:
        """Initialize the StagesNotFoundError.

        Args:
            config_key: The config key that was not found.
        """
        self.config_key = config_key
        super().__init__(
            f"Validation stages config key '{config_key}' not found in configuration.",
        )
