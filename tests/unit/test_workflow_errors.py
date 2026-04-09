"""Tests for workflow error hierarchy.

Tests the live error classes in maverick.exceptions.workflow.
"""

from __future__ import annotations

from maverick.exceptions import MaverickError
from maverick.exceptions.workflow import (
    CheckpointNotFoundError,
    DuplicateComponentError,
    InputMismatchError,
    ReferenceResolutionError,
    WorkflowError,
    WorkflowStepError,
)


class TestDuplicateComponentError:
    """Test DuplicateComponentError attributes and message."""

    def test_duplicate_action_error(self) -> None:
        """Test duplicate action registration error."""
        error = DuplicateComponentError(component_type="action", component_name="validate_files")
        message = str(error)
        assert "action" in message
        assert "validate_files" in message
        assert "already registered" in message
        assert error.component_type == "action"
        assert error.component_name == "validate_files"

    def test_duplicate_agent_error(self) -> None:
        """Test duplicate agent registration error."""
        error = DuplicateComponentError(component_type="agent", component_name="code_reviewer")
        message = str(error)
        assert "agent" in message
        assert "code_reviewer" in message

    def test_is_workflow_error(self) -> None:
        """Test that DuplicateComponentError is a WorkflowError."""
        error = DuplicateComponentError("action", "test")
        assert isinstance(error, WorkflowError)
        assert isinstance(error, MaverickError)


class TestReferenceResolutionError:
    """Test ReferenceResolutionError attributes and message."""

    def test_basic_reference_error(self) -> None:
        """Test basic reference error without suggestions."""
        error = ReferenceResolutionError(reference_type="agent", reference_name="unknown_agent")
        message = str(error)
        assert "agent" in message
        assert "unknown_agent" in message
        assert error.reference_type == "agent"
        assert error.reference_name == "unknown_agent"
        assert error.available_names == []

    def test_reference_error_with_suggestions(self) -> None:
        """Test reference error with available alternatives."""
        error = ReferenceResolutionError(
            reference_type="agent",
            reference_name="unknown_agent",
            available_names=["code_reviewer", "implementer", "issue_fixer"],
        )
        message = str(error)
        assert "code_reviewer" in message
        assert "implementer" in message
        assert "issue_fixer" in message

    def test_reference_error_with_many_suggestions(self) -> None:
        """Test reference error with many alternatives (should truncate)."""
        many_names = [f"agent_{i}" for i in range(15)]
        error = ReferenceResolutionError(
            reference_type="agent",
            reference_name="unknown_agent",
            available_names=many_names,
        )
        message = str(error)
        assert "agent_0" in message
        assert "agent_4" in message  # Should be in first 10
        assert "5 more" in message

    def test_reference_error_with_file_location(self) -> None:
        """Test reference error with file path and line number."""
        error = ReferenceResolutionError(
            reference_type="generator",
            reference_name="unknown_gen",
            file_path="workflow.yaml",
            line_number=42,
        )
        assert error.file_path == "workflow.yaml"
        assert error.line_number == 42

    def test_is_workflow_error(self) -> None:
        """Test that ReferenceResolutionError is a WorkflowError."""
        error = ReferenceResolutionError("agent", "test")
        assert isinstance(error, WorkflowError)
        assert isinstance(error, MaverickError)


class TestWorkflowStepError:
    """Test WorkflowStepError attributes and message."""

    def test_workflow_error_message(self) -> None:
        """Test workflow error message format."""
        error = WorkflowStepError("Validation failed: 3 tests failing")
        message = str(error)
        assert "Workflow failed:" in message
        assert "Validation failed: 3 tests failing" in message
        assert error.reason == "Validation failed: 3 tests failing"

    def test_is_workflow_error(self) -> None:
        """Test that WorkflowStepError is a WorkflowError."""
        error = WorkflowStepError("test")
        assert isinstance(error, WorkflowError)
        assert isinstance(error, MaverickError)


class TestCheckpointNotFoundError:
    """Test CheckpointNotFoundError attributes and message."""

    def test_checkpoint_error_with_workflow_id_only(self) -> None:
        """Test checkpoint error with workflow ID only."""
        error = CheckpointNotFoundError(workflow_id="fly-123")
        message = str(error)
        assert "fly-123" in message
        assert error.workflow_id == "fly-123"
        assert error.checkpoint_id is None

    def test_checkpoint_error_with_checkpoint_id(self) -> None:
        """Test checkpoint error with both workflow and checkpoint IDs."""
        error = CheckpointNotFoundError(workflow_id="fly-123", checkpoint_id="after_validation")
        message = str(error)
        assert "fly-123" in message
        assert "after_validation" in message
        assert error.checkpoint_id == "after_validation"

    def test_is_workflow_error(self) -> None:
        """Test that CheckpointNotFoundError is a WorkflowError."""
        error = CheckpointNotFoundError("test")
        assert isinstance(error, WorkflowError)
        assert isinstance(error, MaverickError)


class TestInputMismatchError:
    """Test InputMismatchError attributes and message."""

    def test_input_mismatch_error(self) -> None:
        """Test input mismatch error message and attributes."""
        error = InputMismatchError(expected_hash="abc123", actual_hash="def456")
        message = str(error)
        assert "abc123" in message
        assert "def456" in message
        assert "mismatch" in message.lower()
        assert error.expected_hash == "abc123"
        assert error.actual_hash == "def456"

    def test_is_workflow_error(self) -> None:
        """Test that InputMismatchError is a WorkflowError."""
        error = InputMismatchError("abc", "def")
        assert isinstance(error, WorkflowError)
        assert isinstance(error, MaverickError)
