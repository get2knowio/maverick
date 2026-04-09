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
            f"Duplicate step name: '{step_name}'. Step names must be unique within a workflow.",
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


class WorkflowStepError(WorkflowError):
    """Explicit workflow step failure raised by workflow code."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"Workflow failed: {reason}")


class CheckpointNotFoundError(WorkflowError):
    """Raised when resuming from a non-existent checkpoint."""

    def __init__(self, workflow_id: str, checkpoint_id: str | None = None) -> None:
        self.workflow_id = workflow_id
        self.checkpoint_id = checkpoint_id
        msg = f"No checkpoint found for workflow '{workflow_id}'"
        if checkpoint_id:
            msg += f" at '{checkpoint_id}'"
        super().__init__(msg)


class InputMismatchError(WorkflowError):
    """Raised when resume inputs don't match checkpoint inputs."""

    def __init__(self, expected_hash: str, actual_hash: str) -> None:
        self.expected_hash = expected_hash
        self.actual_hash = actual_hash
        super().__init__(
            f"Input hash mismatch: checkpoint has '{expected_hash}', "
            f"current inputs have '{actual_hash}'"
        )


class ReferenceResolutionError(WorkflowError):
    """Raised when a reference to an unknown component cannot be resolved."""

    def __init__(
        self,
        reference_type: str,
        reference_name: str,
        available_names: list[str] | None = None,
        file_path: str | None = None,
        line_number: int | None = None,
    ) -> None:
        self.reference_type = reference_type
        self.reference_name = reference_name
        self.available_names = available_names or []
        self.file_path = file_path
        self.line_number = line_number
        message = f"Unknown {reference_type} reference: '{reference_name}'"
        if available_names:
            names_str = ", ".join(f"'{n}'" for n in sorted(available_names)[:10])
            message += f". Available {reference_type}s: {names_str}"
            if len(available_names) > 10:
                message += f" (and {len(available_names) - 10} more)"
        super().__init__(message)


class DuplicateComponentError(WorkflowError):
    """Raised when attempting to register a component with a duplicate name."""

    def __init__(self, component_type: str, component_name: str) -> None:
        self.component_type = component_type
        self.component_name = component_name
        message = (
            f"Duplicate {component_type} registration: '{component_name}' is already registered"
        )
        super().__init__(message)
