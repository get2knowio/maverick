"""Unit tests for exception classes.

Tests the custom exception hierarchy and implementation-specific exceptions:
- TaskParseError
- GitError
- GitHubError
- MaverickValidationError
"""

from __future__ import annotations

import pytest

from maverick.exceptions import (
    GitError,
    GitHubError,
    MaverickValidationError,
    TaskParseError,
)

# =============================================================================
# TaskParseError Tests
# =============================================================================


class TestTaskParseError:
    """Tests for TaskParseError exception class."""

    def test_instantiation_with_message_only(self) -> None:
        """Test creating TaskParseError with message only."""
        error = TaskParseError("Failed to parse tasks.md: invalid format")

        assert error.message == "Failed to parse tasks.md: invalid format"
        assert str(error) == "Failed to parse tasks.md: invalid format"
        assert error.line_number is None

    def test_instantiation_with_line_number(self) -> None:
        """Test creating TaskParseError with line number."""
        error = TaskParseError("Invalid task format", line_number=42)

        assert error.message == "Invalid task format"
        assert error.line_number == 42

    def test_line_number_defaults_to_none(self) -> None:
        """Test line_number defaults to None."""
        error = TaskParseError("Parse error")

        assert error.line_number is None

    def test_is_agent_error(self) -> None:
        """Test TaskParseError is an AgentError."""
        from maverick.exceptions import AgentError

        error = TaskParseError("Test error")
        assert isinstance(error, AgentError)

    def test_agent_name_inherited_from_agent_error(self) -> None:
        """Test agent_name attribute inherited from AgentError."""
        error = TaskParseError("Test error")

        assert hasattr(error, "agent_name")
        assert error.agent_name is None

    def test_error_code_inherited_from_agent_error(self) -> None:
        """Test error_code attribute inherited from AgentError."""
        error = TaskParseError("Test error")

        assert hasattr(error, "error_code")
        assert error.error_code is None

    def test_message_attribute_set_correctly(self) -> None:
        """Test message attribute is set correctly."""
        message = "Error at line 10"
        error = TaskParseError(message, line_number=10)

        assert error.message == message
        assert error.message in str(error)

    def test_multiple_instances_independent(self) -> None:
        """Test multiple instances are independent."""
        error1 = TaskParseError("Error 1", line_number=1)
        error2 = TaskParseError("Error 2", line_number=2)

        assert error1.message != error2.message
        assert error1.line_number != error2.line_number


# =============================================================================
# GitError Tests
# =============================================================================


class TestGitError:
    """Tests for GitError exception class."""

    def test_instantiation_with_message_only(self) -> None:
        """Test creating GitError with message only."""
        error = GitError("Failed to commit changes")

        assert error.message == "Failed to commit changes"
        assert str(error) == "Failed to commit changes"
        assert error.operation is None
        assert error.recoverable is False

    def test_instantiation_with_operation(self) -> None:
        """Test creating GitError with operation name."""
        error = GitError("Commit failed: nothing to commit", operation="commit")

        assert error.message == "Commit failed: nothing to commit"
        assert error.operation == "commit"
        assert error.recoverable is False

    def test_instantiation_with_recoverable_flag(self) -> None:
        """Test creating GitError with recoverable flag."""
        error = GitError(
            "Stash failed: dirty working directory",
            operation="stash",
            recoverable=True,
        )

        assert error.operation == "stash"
        assert error.recoverable is True

    def test_operation_defaults_to_none(self) -> None:
        """Test operation defaults to None."""
        error = GitError("Git operation failed")

        assert error.operation is None

    def test_recoverable_defaults_to_false(self) -> None:
        """Test recoverable defaults to False."""
        error = GitError("Git operation failed")

        assert error.recoverable is False

    def test_is_agent_error(self) -> None:
        """Test GitError is an AgentError."""
        from maverick.exceptions import AgentError

        error = GitError("Test error")
        assert isinstance(error, AgentError)

    def test_all_parameters_together(self) -> None:
        """Test creating GitError with all parameters."""
        error = GitError(
            "Branch operation failed",
            operation="branch",
            recoverable=True,
        )

        assert error.message == "Branch operation failed"
        assert error.operation == "branch"
        assert error.recoverable is True

    def test_recoverable_false_explicit(self) -> None:
        """Test creating GitError with recoverable=False explicitly."""
        error = GitError("Fatal error", operation="push", recoverable=False)

        assert error.recoverable is False

    def test_message_attribute_present(self) -> None:
        """Test message attribute is always present."""
        error = GitError("Test message", operation="test")

        assert hasattr(error, "message")
        assert error.message == "Test message"


# =============================================================================
# GitHubError Tests
# =============================================================================


class TestGitHubError:
    """Tests for GitHubError exception class."""

    def test_instantiation_with_message_only(self) -> None:
        """Test creating GitHubError with message only."""
        error = GitHubError("Failed to create pull request")

        assert error.message == "Failed to create pull request"
        assert str(error) == "Failed to create pull request"
        assert error.issue_number is None
        assert error.retry_after is None

    def test_instantiation_with_issue_number(self) -> None:
        """Test creating GitHubError with issue number."""
        error = GitHubError("Issue not found", issue_number=404)

        assert error.message == "Issue not found"
        assert error.issue_number == 404
        assert error.retry_after is None

    def test_instantiation_with_retry_after(self) -> None:
        """Test creating GitHubError with retry_after."""
        error = GitHubError(
            "API rate limit exceeded",
            retry_after=60,
        )

        assert error.message == "API rate limit exceeded"
        assert error.retry_after == 60
        assert error.issue_number is None

    def test_issue_number_defaults_to_none(self) -> None:
        """Test issue_number defaults to None."""
        error = GitHubError("GitHub operation failed")

        assert error.issue_number is None

    def test_retry_after_defaults_to_none(self) -> None:
        """Test retry_after defaults to None."""
        error = GitHubError("GitHub operation failed")

        assert error.retry_after is None

    def test_is_agent_error(self) -> None:
        """Test GitHubError is an AgentError."""
        from maverick.exceptions import AgentError

        error = GitHubError("Test error")
        assert isinstance(error, AgentError)

    def test_all_parameters_together(self) -> None:
        """Test creating GitHubError with all parameters."""
        error = GitHubError(
            "Issue update failed and rate limited",
            issue_number=123,
            retry_after=30,
        )

        assert error.message == "Issue update failed and rate limited"
        assert error.issue_number == 123
        assert error.retry_after == 30

    def test_issue_number_zero_valid(self) -> None:
        """Test issue_number can be zero (edge case)."""
        error = GitHubError("Error with issue 0", issue_number=0)

        assert error.issue_number == 0

    def test_retry_after_zero_valid(self) -> None:
        """Test retry_after can be zero (retry immediately)."""
        error = GitHubError("Retry immediately", retry_after=0)

        assert error.retry_after == 0

    def test_message_attribute_present(self) -> None:
        """Test message attribute is always present."""
        error = GitHubError("Test message", issue_number=1)

        assert hasattr(error, "message")
        assert error.message == "Test message"


# =============================================================================
# MaverickValidationError Tests
# =============================================================================


class TestMaverickValidationError:
    """Tests for MaverickValidationError exception class."""

    def test_instantiation_with_message_only(self) -> None:
        """Test creating MaverickValidationError with message only."""
        error = MaverickValidationError("Validation failed")

        assert error.message == "Validation failed"
        assert str(error) == "Validation failed"
        assert error.step is None
        assert error.output is None

    def test_instantiation_with_step(self) -> None:
        """Test creating MaverickValidationError with validation step."""
        error = MaverickValidationError(
            "Linting failed with errors",
            step="lint",
        )

        assert error.message == "Linting failed with errors"
        assert error.step == "lint"
        assert error.output is None

    def test_instantiation_with_output(self) -> None:
        """Test creating MaverickValidationError with command output."""
        output = "E501 line too long\nF401 unused import"
        error = MaverickValidationError(
            "Lint check failed",
            step="lint",
            output=output,
        )

        assert error.message == "Lint check failed"
        assert error.step == "lint"
        assert error.output == output
        assert "line too long" in error.output

    def test_step_defaults_to_none(self) -> None:
        """Test step defaults to None."""
        error = MaverickValidationError("Validation error")

        assert error.step is None

    def test_output_defaults_to_none(self) -> None:
        """Test output defaults to None."""
        error = MaverickValidationError("Validation error")

        assert error.output is None

    def test_is_agent_error(self) -> None:
        """Test MaverickValidationError is an AgentError."""
        from maverick.exceptions import AgentError

        error = MaverickValidationError("Test error")
        assert isinstance(error, AgentError)

    def test_all_parameters_together(self) -> None:
        """Test creating MaverickValidationError with all parameters."""
        output = "Test output message"
        error = MaverickValidationError(
            "Format check failed",
            step="format",
            output=output,
        )

        assert error.message == "Format check failed"
        assert error.step == "format"
        assert error.output == output

    def test_step_values_common(self) -> None:
        """Test common step values (format, lint, test, typecheck)."""
        for step in ["format", "lint", "typecheck", "test"]:
            error = MaverickValidationError("Error", step=step)
            assert error.step == step

    def test_empty_output_string(self) -> None:
        """Test empty output string is valid."""
        error = MaverickValidationError("Error", output="")

        assert error.output == ""

    def test_multiline_output(self) -> None:
        """Test multiline output is preserved."""
        output = "Line 1\nLine 2\nLine 3"
        error = MaverickValidationError("Error", output=output)

        assert error.output == output
        assert "\n" in error.output

    def test_message_attribute_present(self) -> None:
        """Test message attribute is always present."""
        error = MaverickValidationError("Test message", step="test")

        assert hasattr(error, "message")
        assert error.message == "Test message"


# =============================================================================
# Exception Hierarchy Tests
# =============================================================================


class TestExceptionHierarchy:
    """Tests for exception hierarchy relationships."""

    def test_task_parse_error_is_maverick_error(self) -> None:
        """Test TaskParseError inherits from MaverickError."""
        from maverick.exceptions import MaverickError

        error = TaskParseError("Test")
        assert isinstance(error, MaverickError)

    def test_git_error_is_maverick_error(self) -> None:
        """Test GitError inherits from MaverickError."""
        from maverick.exceptions import MaverickError

        error = GitError("Test")
        assert isinstance(error, MaverickError)

    def test_github_error_is_maverick_error(self) -> None:
        """Test GitHubError inherits from MaverickError."""
        from maverick.exceptions import MaverickError

        error = GitHubError("Test")
        assert isinstance(error, MaverickError)

    def test_validation_error_is_maverick_error(self) -> None:
        """Test MaverickValidationError inherits from MaverickError."""
        from maverick.exceptions import MaverickError

        error = MaverickValidationError("Test")
        assert isinstance(error, MaverickError)

    def test_all_errors_catchable_as_maverick_error(self) -> None:
        """Test all implementation errors can be caught as MaverickError."""
        from maverick.exceptions import MaverickError

        errors: list[MaverickError] = [
            TaskParseError("task parse"),
            GitError("git"),
            GitHubError("github"),
            MaverickValidationError("validation"),
        ]

        for error in errors:
            assert isinstance(error, MaverickError)

    def test_errors_catchable_as_exception(self) -> None:
        """Test all errors are standard Python exceptions."""
        errors: list[Exception] = [
            TaskParseError("task parse"),
            GitError("git"),
            GitHubError("github"),
            MaverickValidationError("validation"),
        ]

        for error in errors:
            assert isinstance(error, Exception)


# =============================================================================
# Exception String Representation Tests
# =============================================================================


class TestExceptionStringRepresentation:
    """Tests for exception string representation."""

    def test_task_parse_error_str(self) -> None:
        """Test TaskParseError string representation."""
        error = TaskParseError("Cannot parse task", line_number=5)

        assert "Cannot parse task" in str(error)

    def test_git_error_str(self) -> None:
        """Test GitError string representation."""
        error = GitError("Commit rejected", operation="commit")

        assert "Commit rejected" in str(error)

    def test_github_error_str(self) -> None:
        """Test GitHubError string representation."""
        error = GitHubError("PR creation failed", issue_number=42)

        assert "PR creation failed" in str(error)

    def test_validation_error_str(self) -> None:
        """Test MaverickValidationError string representation."""
        error = MaverickValidationError("Tests failed", step="test")

        assert "Tests failed" in str(error)

    def test_error_repr_contains_class_name(self) -> None:
        """Test error repr contains exception class name."""
        error = TaskParseError("Test message")

        repr_str = repr(error)
        assert "TaskParseError" in repr_str or "message" in repr_str.lower()


# =============================================================================
# Exception Raising Tests
# =============================================================================


class TestExceptionRaising:
    """Tests for raising and catching exceptions."""

    def test_can_raise_and_catch_task_parse_error(self) -> None:
        """Test raising and catching TaskParseError."""
        with pytest.raises(TaskParseError) as exc_info:
            raise TaskParseError("Parse failed", line_number=10)

        assert exc_info.value.message == "Parse failed"
        assert exc_info.value.line_number == 10

    def test_can_raise_and_catch_git_error(self) -> None:
        """Test raising and catching GitError."""
        with pytest.raises(GitError) as exc_info:
            raise GitError("Git operation failed", operation="merge")

        assert exc_info.value.operation == "merge"

    def test_can_raise_and_catch_github_error(self) -> None:
        """Test raising and catching GitHubError."""
        with pytest.raises(GitHubError) as exc_info:
            raise GitHubError("Rate limited", retry_after=60)

        assert exc_info.value.retry_after == 60

    def test_can_raise_and_catch_validation_error(self) -> None:
        """Test raising and catching MaverickValidationError."""
        with pytest.raises(MaverickValidationError) as exc_info:
            raise MaverickValidationError("Validation failed", step="lint")

        assert exc_info.value.step == "lint"

    def test_catch_implementation_error_as_agent_error(self) -> None:
        """Test catching implementation error as AgentError."""
        from maverick.exceptions import AgentError

        with pytest.raises(AgentError):
            raise TaskParseError("Test parse error")

        with pytest.raises(AgentError):
            raise GitError("Test git error")

    def test_catch_all_as_maverick_error(self) -> None:
        """Test catching any implementation error as MaverickError."""
        from maverick.exceptions import MaverickError

        with pytest.raises(MaverickError):
            raise TaskParseError("Test")

        with pytest.raises(MaverickError):
            raise GitError("Test")

        with pytest.raises(MaverickError):
            raise GitHubError("Test")

        with pytest.raises(MaverickError):
            raise MaverickValidationError("Test")
