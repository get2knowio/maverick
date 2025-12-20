"""DSL-specific error types for the Maverick workflow DSL.

This module defines exceptions specific to workflow DSL execution,
distinct from the general WorkflowError in maverick.exceptions.
"""

from __future__ import annotations

from maverick.exceptions import MaverickError


class DSLWorkflowError(MaverickError):
    """Explicit workflow failure raised by workflow code.

    Use this to signal that a workflow should stop with a specific
    error reason, distinct from step failures. This is raised explicitly
    by user code via `raise WorkflowError(reason)`.

    Attributes:
        reason: Human-readable explanation of why the workflow failed.
    """

    def __init__(self, reason: str) -> None:
        """Initialize the DSLWorkflowError.

        Args:
            reason: Human-readable explanation of why the workflow failed.
        """
        self.reason = reason
        super().__init__(f"Workflow failed: {reason}")


class CheckpointNotFoundError(MaverickError):
    """Raised when resuming from a non-existent checkpoint.

    Attributes:
        workflow_id: ID of the workflow that was being resumed.
        checkpoint_id: Specific checkpoint that was not found (if any).
    """

    def __init__(
        self,
        workflow_id: str,
        checkpoint_id: str | None = None,
    ) -> None:
        """Initialize the CheckpointNotFoundError.

        Args:
            workflow_id: ID of the workflow.
            checkpoint_id: Specific checkpoint ID (optional).
        """
        self.workflow_id = workflow_id
        self.checkpoint_id = checkpoint_id
        msg = f"No checkpoint found for workflow '{workflow_id}'"
        if checkpoint_id:
            msg += f" at '{checkpoint_id}'"
        super().__init__(msg)


class InputMismatchError(MaverickError):
    """Raised when resume inputs don't match checkpoint inputs.

    Attributes:
        expected_hash: Hash from the checkpoint.
        actual_hash: Hash of current inputs.
    """

    def __init__(
        self,
        expected_hash: str,
        actual_hash: str,
    ) -> None:
        """Initialize the InputMismatchError.

        Args:
            expected_hash: Hash stored in checkpoint.
            actual_hash: Hash of current inputs.
        """
        self.expected_hash = expected_hash
        self.actual_hash = actual_hash
        super().__init__(
            f"Input hash mismatch: checkpoint has '{expected_hash}', "
            f"current inputs have '{actual_hash}'"
        )
