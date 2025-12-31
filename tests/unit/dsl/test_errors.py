"""Tests for unified DSL error hierarchy.

This module tests the unified error hierarchy in maverick.dsl.errors,
ensuring that:
- All errors inherit from the correct base classes
- Error messages are preserved correctly
- Error attributes are set properly
- isinstance checks work as expected
"""

from __future__ import annotations

import pytest

from maverick.dsl.errors import (
    CheckpointNotFoundError,
    DSLError,
    DSLWorkflowError,
    DuplicateComponentError,
    InputMismatchError,
    ReferenceResolutionError,
    UnsupportedVersionError,
    WorkflowDefinitionError,
    WorkflowExecutionError,
    WorkflowParseError,
    WorkflowSerializationError,
)
from maverick.exceptions import MaverickError


class TestErrorHierarchy:
    """Test the error inheritance hierarchy."""

    def test_dsl_error_inherits_from_maverick_error(self) -> None:
        """Test that DSLError is a MaverickError."""
        error = DSLError("test error")
        assert isinstance(error, MaverickError)

    def test_workflow_definition_error_inherits_from_dsl_error(self) -> None:
        """Test that WorkflowDefinitionError is a DSLError."""
        error = WorkflowDefinitionError("test error")
        assert isinstance(error, DSLError)
        assert isinstance(error, MaverickError)

    def test_workflow_execution_error_inherits_from_dsl_error(self) -> None:
        """Test that WorkflowExecutionError is a DSLError."""
        error = WorkflowExecutionError("test error")
        assert isinstance(error, DSLError)
        assert isinstance(error, MaverickError)

    def test_workflow_serialization_error_inherits_from_workflow_definition_error(
        self,
    ) -> None:
        """Test that WorkflowSerializationError is a WorkflowDefinitionError."""
        error = WorkflowSerializationError("test error")
        assert isinstance(error, WorkflowDefinitionError)
        assert isinstance(error, DSLError)
        assert isinstance(error, MaverickError)

    def test_parse_error_inherits_from_workflow_definition_error(self) -> None:
        """Test that WorkflowParseError is a WorkflowDefinitionError."""
        error = WorkflowParseError("test error")
        assert isinstance(error, WorkflowDefinitionError)
        assert isinstance(error, DSLError)

    def test_unsupported_version_error_inherits_from_workflow_definition_error(
        self,
    ) -> None:
        """Test that UnsupportedVersionError is a WorkflowDefinitionError."""
        error = UnsupportedVersionError(
            requested_version="2.0", supported_versions=["1.0"]
        )
        assert isinstance(error, WorkflowDefinitionError)
        assert isinstance(error, DSLError)

    def test_duplicate_component_error_inherits_from_workflow_definition_error(
        self,
    ) -> None:
        """Test that DuplicateComponentError is a WorkflowDefinitionError."""
        error = DuplicateComponentError(
            component_type="action", component_name="test_action"
        )
        assert isinstance(error, WorkflowDefinitionError)
        assert isinstance(error, DSLError)

    def test_reference_resolution_error_inherits_from_workflow_definition_error(
        self,
    ) -> None:
        """Test that ReferenceResolutionError is a WorkflowDefinitionError."""
        error = ReferenceResolutionError(
            reference_type="agent", reference_name="unknown_agent"
        )
        assert isinstance(error, WorkflowDefinitionError)
        assert isinstance(error, DSLError)

    def test_dsl_workflow_error_inherits_from_workflow_execution_error(self) -> None:
        """Test that DSLWorkflowError is a WorkflowExecutionError."""
        error = DSLWorkflowError("test reason")
        assert isinstance(error, WorkflowExecutionError)
        assert isinstance(error, DSLError)

    def test_checkpoint_not_found_error_inherits_from_workflow_execution_error(
        self,
    ) -> None:
        """Test that CheckpointNotFoundError is a WorkflowExecutionError."""
        error = CheckpointNotFoundError(workflow_id="test-workflow")
        assert isinstance(error, WorkflowExecutionError)
        assert isinstance(error, DSLError)

    def test_input_mismatch_error_inherits_from_workflow_execution_error(
        self,
    ) -> None:
        """Test that InputMismatchError is a WorkflowExecutionError."""
        error = InputMismatchError(expected_hash="abc123", actual_hash="def456")
        assert isinstance(error, WorkflowExecutionError)
        assert isinstance(error, DSLError)


class TestCatchAllDSLErrors:
    """Test that DSLError catches all DSL exceptions."""

    def test_catch_all_definition_errors(self) -> None:
        """Test catching all definition errors with DSLError."""
        errors = [
            WorkflowDefinitionError("test"),
            WorkflowParseError("test"),
            UnsupportedVersionError("2.0", ["1.0"]),
            DuplicateComponentError("action", "test"),
            ReferenceResolutionError("agent", "unknown"),
            WorkflowSerializationError("test"),
        ]

        for error in errors:
            with pytest.raises(DSLError):
                raise error

    def test_catch_all_execution_errors(self) -> None:
        """Test catching all execution errors with DSLError."""
        errors = [
            WorkflowExecutionError("test"),
            DSLWorkflowError("test"),
            CheckpointNotFoundError("workflow-id"),
            InputMismatchError("abc123", "def456"),
        ]

        for error in errors:
            with pytest.raises(DSLError):
                raise error


class TestWorkflowParseError:
    """Test WorkflowParseError attributes and message."""

    def test_basic_parse_error(self) -> None:
        """Test basic parse error with message only."""
        error = WorkflowParseError("Invalid YAML syntax")
        assert str(error) == "Invalid YAML syntax"
        assert error.file_path is None
        assert error.line_number is None
        assert error.parse_error is None

    def test_parse_error_with_file_path(self) -> None:
        """Test parse error with file path."""
        error = WorkflowParseError("Invalid YAML syntax", file_path="workflow.yaml")
        assert str(error) == "Invalid YAML syntax"
        assert error.file_path == "workflow.yaml"
        assert error.line_number is None

    def test_parse_error_with_line_number(self) -> None:
        """Test parse error with line number."""
        error = WorkflowParseError(
            "Invalid YAML syntax", file_path="workflow.yaml", line_number=15
        )
        assert str(error) == "Invalid YAML syntax"
        assert error.file_path == "workflow.yaml"
        assert error.line_number == 15

    def test_parse_error_with_underlying_exception(self) -> None:
        """Test parse error with underlying parse exception."""
        underlying = ValueError("Bad value")
        error = WorkflowParseError("Invalid YAML syntax", parse_error=underlying)
        assert str(error) == "Invalid YAML syntax"
        assert error.parse_error is underlying


class TestUnsupportedVersionError:
    """Test UnsupportedVersionError attributes and message."""

    def test_unsupported_version_with_single_supported(self) -> None:
        """Test error with single supported version."""
        error = UnsupportedVersionError(
            requested_version="2.0", supported_versions=["1.0"]
        )
        assert "2.0" in str(error)
        assert "'1.0'" in str(error)
        assert error.requested_version == "2.0"
        assert error.supported_versions == ["1.0"]

    def test_unsupported_version_with_multiple_supported(self) -> None:
        """Test error with multiple supported versions."""
        error = UnsupportedVersionError(
            requested_version="2.0", supported_versions=["1.0", "1.1", "1.2"]
        )
        message = str(error)
        assert "2.0" in message
        assert "'1.0'" in message
        assert "'1.1'" in message
        assert "'1.2'" in message

    def test_unsupported_version_with_file_path(self) -> None:
        """Test error with file path."""
        error = UnsupportedVersionError(
            requested_version="2.0",
            supported_versions=["1.0"],
            file_path="workflow.yaml",
        )
        assert error.file_path == "workflow.yaml"


class TestDuplicateComponentError:
    """Test DuplicateComponentError attributes and message."""

    def test_duplicate_action_error(self) -> None:
        """Test duplicate action registration error."""
        error = DuplicateComponentError(
            component_type="action", component_name="validate_files"
        )
        message = str(error)
        assert "action" in message
        assert "validate_files" in message
        assert "already registered" in message
        assert error.component_type == "action"
        assert error.component_name == "validate_files"

    def test_duplicate_agent_error(self) -> None:
        """Test duplicate agent registration error."""
        error = DuplicateComponentError(
            component_type="agent", component_name="code_reviewer"
        )
        message = str(error)
        assert "agent" in message
        assert "code_reviewer" in message


class TestReferenceResolutionError:
    """Test ReferenceResolutionError attributes and message."""

    def test_basic_reference_error(self) -> None:
        """Test basic reference error without suggestions."""
        error = ReferenceResolutionError(
            reference_type="agent", reference_name="unknown_agent"
        )
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
        # Should show first 10 (sorted) plus "and X more"
        assert "agent_0" in message
        # Note: sorted alphabetically, so agent_9 won't be in first 10
        # (agent_10, agent_11, etc. come before agent_9)
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


class TestDSLWorkflowError:
    """Test DSLWorkflowError attributes and message."""

    def test_workflow_error_message(self) -> None:
        """Test workflow error message format."""
        error = DSLWorkflowError("Validation failed: 3 tests failing")
        message = str(error)
        assert "Workflow failed:" in message
        assert "Validation failed: 3 tests failing" in message
        assert error.reason == "Validation failed: 3 tests failing"


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
        error = CheckpointNotFoundError(
            workflow_id="fly-123", checkpoint_id="after_validation"
        )
        message = str(error)
        assert "fly-123" in message
        assert "after_validation" in message
        assert error.checkpoint_id == "after_validation"


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


class TestWorkflowSerializationError:
    """Test WorkflowSerializationError backwards compatibility."""

    def test_serialization_error_basic(self) -> None:
        """Test basic serialization error."""
        error = WorkflowSerializationError("Serialization failed")
        assert str(error) == "Serialization failed"
        assert error.file_path is None
        assert error.line_number is None

    def test_serialization_error_with_file_info(self) -> None:
        """Test serialization error with file path and line number."""
        error = WorkflowSerializationError(
            "Serialization failed", file_path="workflow.yaml", line_number=25
        )
        assert str(error) == "Serialization failed"
        assert error.file_path == "workflow.yaml"
        assert error.line_number == 25

    def test_serialization_error_is_definition_error(self) -> None:
        """Test that WorkflowSerializationError is a WorkflowDefinitionError."""
        error = WorkflowSerializationError("test")
        # Should be catchable as WorkflowDefinitionError
        with pytest.raises(WorkflowDefinitionError):
            raise error

    def test_can_catch_parse_error_as_serialization_error(self) -> None:
        """Test WorkflowParseError and WorkflowSerializationError."""
        # WorkflowParseError inherits from WorkflowDefinitionError
        # WorkflowSerializationError also inherits from
        # WorkflowDefinitionError. So they're siblings, not parent-child.
        # This test documents that you CAN'T catch WorkflowParseError as
        # WorkflowSerializationError
        error = WorkflowParseError("test")
        # This should NOT work (they're siblings, not parent-child)
        assert not isinstance(error, WorkflowSerializationError)
        # But both can be caught as WorkflowDefinitionError
        assert isinstance(error, WorkflowDefinitionError)
