"""Unit tests for subprocess runner models.

Tests all dataclass models in maverick.runners.models for:
- Basic creation and field assignment
- Property methods and computed values
- Validation rules and error handling
- Immutability (frozen dataclasses)
"""

from __future__ import annotations

import pytest

from maverick.runners.models import (
    CheckStatus,
    CodeRabbitFinding,
    CodeRabbitResult,
    CommandResult,
    GitHubIssue,
    ParsedError,
    PullRequest,
    StageResult,
    StreamLine,
    ValidationOutput,
    ValidationStage,
)


class TestCommandResult:
    """Tests for CommandResult dataclass."""

    def test_success_when_returncode_zero_and_not_timed_out(self) -> None:
        """Test success property is True when returncode=0 and not timed_out."""
        result = CommandResult(
            returncode=0,
            stdout="output",
            stderr="",
            duration_ms=100,
            timed_out=False,
        )
        assert result.success is True

    def test_success_false_when_returncode_nonzero(self) -> None:
        """Test success property is False when returncode != 0."""
        result = CommandResult(
            returncode=1,
            stdout="output",
            stderr="error",
            duration_ms=100,
            timed_out=False,
        )
        assert result.success is False

    def test_success_false_when_timed_out(self) -> None:
        """Test success property is False when timed_out=True."""
        result = CommandResult(
            returncode=0,
            stdout="partial output",
            stderr="",
            duration_ms=5000,
            timed_out=True,
        )
        assert result.success is False

    def test_output_combines_stdout_and_stderr(self) -> None:
        """Test output property combines stdout and stderr with newline."""
        result = CommandResult(
            returncode=0,
            stdout="normal output",
            stderr="error output",
            duration_ms=100,
            timed_out=False,
        )
        assert result.output == "normal output\nerror output"

    def test_output_returns_only_stdout_when_no_stderr(self) -> None:
        """Test output property returns only stdout when stderr is empty."""
        result = CommandResult(
            returncode=0,
            stdout="just stdout",
            stderr="",
            duration_ms=100,
            timed_out=False,
        )
        assert result.output == "just stdout"

    def test_output_returns_only_stderr_when_no_stdout(self) -> None:
        """Test output property returns only stderr when stdout is empty."""
        result = CommandResult(
            returncode=1,
            stdout="",
            stderr="just stderr",
            duration_ms=100,
            timed_out=False,
        )
        assert result.output == "just stderr"

    def test_frozen_immutability(self) -> None:
        """Test that CommandResult is frozen and cannot be modified."""
        result = CommandResult(
            returncode=0,
            stdout="output",
            stderr="",
            duration_ms=100,
            timed_out=False,
        )
        with pytest.raises(AttributeError):
            result.returncode = 1  # type: ignore[misc]

    def test_default_timed_out_is_false(self) -> None:
        """Test that timed_out defaults to False."""
        result = CommandResult(
            returncode=0,
            stdout="output",
            stderr="",
            duration_ms=100,
        )
        assert result.timed_out is False


class TestStreamLine:
    """Tests for StreamLine dataclass."""

    def test_basic_creation_with_all_fields(self) -> None:
        """Test creating StreamLine with all fields."""
        line = StreamLine(
            content="test output line",
            stream="stdout",
            timestamp_ms=1500,
        )
        assert line.content == "test output line"
        assert line.stream == "stdout"
        assert line.timestamp_ms == 1500

    def test_stderr_stream(self) -> None:
        """Test creating StreamLine with stderr stream."""
        line = StreamLine(
            content="error line",
            stream="stderr",
            timestamp_ms=2000,
        )
        assert line.stream == "stderr"

    def test_frozen_immutability(self) -> None:
        """Test that StreamLine is frozen and cannot be modified."""
        line = StreamLine(
            content="test",
            stream="stdout",
            timestamp_ms=100,
        )
        with pytest.raises(AttributeError):
            line.content = "modified"  # type: ignore[misc]


class TestParsedError:
    """Tests for ParsedError dataclass."""

    def test_with_all_fields(self) -> None:
        """Test creating ParsedError with all fields."""
        error = ParsedError(
            file="src/main.py",
            line=42,
            message="Line too long",
            column=80,
            severity="error",
            code="E501",
        )
        assert error.file == "src/main.py"
        assert error.line == 42
        assert error.message == "Line too long"
        assert error.column == 80
        assert error.severity == "error"
        assert error.code == "E501"

    def test_with_optional_fields_as_none(self) -> None:
        """Test creating ParsedError with optional fields as None."""
        error = ParsedError(
            file="src/main.py",
            line=42,
            message="Line too long",
        )
        assert error.file == "src/main.py"
        assert error.line == 42
        assert error.message == "Line too long"
        assert error.column is None
        assert error.severity is None
        assert error.code is None

    def test_frozen_immutability(self) -> None:
        """Test that ParsedError is frozen and cannot be modified."""
        error = ParsedError(
            file="src/main.py",
            line=42,
            message="error",
        )
        with pytest.raises(AttributeError):
            error.line = 43  # type: ignore[misc]


class TestValidationStage:
    """Tests for ValidationStage dataclass."""

    def test_valid_creation(self) -> None:
        """Test creating a valid ValidationStage."""
        stage = ValidationStage(
            name="Test stage",
            command=("pytest", "tests/"),
            fixable=False,
            timeout_seconds=300.0,
        )
        assert stage.name == "Test stage"
        assert stage.command == ("pytest", "tests/")
        assert stage.fixable is False
        assert stage.timeout_seconds == 300.0

    def test_with_fix_command(self) -> None:
        """Test creating ValidationStage with fix command."""
        stage = ValidationStage(
            name="Format check",
            command=("ruff", "format", "--check", "."),
            fixable=True,
            fix_command=("ruff", "format", "."),
            timeout_seconds=60.0,
        )
        assert stage.fixable is True
        assert stage.fix_command == ("ruff", "format", ".")

    def test_raises_value_error_for_empty_command(self) -> None:
        """Test that ValidationStage raises ValueError for empty command tuple."""
        with pytest.raises(ValueError, match="Command tuple cannot be empty"):
            ValidationStage(
                name="Invalid stage",
                command=(),
                timeout_seconds=60.0,
            )

    def test_raises_value_error_for_zero_timeout(self) -> None:
        """Test that ValidationStage raises ValueError for zero timeout."""
        with pytest.raises(ValueError, match="Timeout must be positive"):
            ValidationStage(
                name="Invalid stage",
                command=("pytest",),
                timeout_seconds=0.0,
            )

    def test_raises_value_error_for_negative_timeout(self) -> None:
        """Test that ValidationStage raises ValueError for negative timeout."""
        with pytest.raises(ValueError, match="Timeout must be positive"):
            ValidationStage(
                name="Invalid stage",
                command=("pytest",),
                timeout_seconds=-10.0,
            )

    def test_default_values(self) -> None:
        """Test default values for optional fields."""
        stage = ValidationStage(
            name="Test",
            command=("pytest",),
        )
        assert stage.fixable is False
        assert stage.fix_command is None
        assert stage.timeout_seconds == 300.0

    def test_frozen_immutability(self) -> None:
        """Test that ValidationStage is frozen and cannot be modified."""
        stage = ValidationStage(
            name="Test",
            command=("pytest",),
        )
        with pytest.raises(AttributeError):
            stage.name = "Modified"  # type: ignore[misc]


class TestStageResult:
    """Tests for StageResult dataclass."""

    def test_with_default_values(self) -> None:
        """Test creating StageResult with default values."""
        result = StageResult(
            stage_name="Test stage",
            passed=True,
            output="All tests passed",
            duration_ms=1500,
        )
        assert result.stage_name == "Test stage"
        assert result.passed is True
        assert result.output == "All tests passed"
        assert result.duration_ms == 1500
        assert result.fix_attempts == 0
        assert result.errors == ()

    def test_with_errors_tuple(self) -> None:
        """Test creating StageResult with errors tuple."""
        error1 = ParsedError(file="test.py", line=1, message="Error 1")
        error2 = ParsedError(file="test.py", line=2, message="Error 2")
        result = StageResult(
            stage_name="Lint",
            passed=False,
            output="2 errors found",
            duration_ms=500,
            fix_attempts=2,
            errors=(error1, error2),
        )
        assert result.fix_attempts == 2
        assert len(result.errors) == 2
        assert result.errors[0].message == "Error 1"
        assert result.errors[1].message == "Error 2"

    def test_frozen_immutability(self) -> None:
        """Test that StageResult is frozen and cannot be modified."""
        result = StageResult(
            stage_name="Test",
            passed=True,
            output="output",
            duration_ms=100,
        )
        with pytest.raises(AttributeError):
            result.passed = False  # type: ignore[misc]


class TestValidationOutput:
    """Tests for ValidationOutput dataclass."""

    def test_stages_run_property(self) -> None:
        """Test stages_run property returns total number of stages."""
        result1 = StageResult("Stage 1", True, "ok", 100)
        result2 = StageResult("Stage 2", True, "ok", 200)
        result3 = StageResult("Stage 3", False, "fail", 150)

        output = ValidationOutput(
            success=False,
            stages=(result1, result2, result3),
            total_duration_ms=450,
        )
        assert output.stages_run == 3

    def test_stages_passed_property(self) -> None:
        """Test stages_passed property counts only passed stages."""
        result1 = StageResult("Stage 1", True, "ok", 100)
        result2 = StageResult("Stage 2", True, "ok", 200)
        result3 = StageResult("Stage 3", False, "fail", 150)

        output = ValidationOutput(
            success=False,
            stages=(result1, result2, result3),
            total_duration_ms=450,
        )
        assert output.stages_passed == 2

    def test_stages_failed_property(self) -> None:
        """Test stages_failed property counts only failed stages."""
        result1 = StageResult("Stage 1", True, "ok", 100)
        result2 = StageResult("Stage 2", False, "fail", 200)
        result3 = StageResult("Stage 3", False, "fail", 150)

        output = ValidationOutput(
            success=False,
            stages=(result1, result2, result3),
            total_duration_ms=450,
        )
        assert output.stages_failed == 2

    def test_empty_stages(self) -> None:
        """Test properties with empty stages tuple."""
        output = ValidationOutput(
            success=True,
            stages=(),
            total_duration_ms=0,
        )
        assert output.stages_run == 0
        assert output.stages_passed == 0
        assert output.stages_failed == 0

    def test_frozen_immutability(self) -> None:
        """Test that ValidationOutput is frozen and cannot be modified."""
        output = ValidationOutput(
            success=True,
            stages=(),
            total_duration_ms=0,
        )
        with pytest.raises(AttributeError):
            output.success = False  # type: ignore[misc]


class TestGitHubIssue:
    """Tests for GitHubIssue dataclass."""

    def test_valid_creation(self) -> None:
        """Test creating a valid GitHubIssue."""
        issue = GitHubIssue(
            number=123,
            title="Bug report",
            body="Description of the bug",
            labels=("bug", "priority-high"),
            state="open",
            assignees=("user1", "user2"),
            url="https://github.com/repo/issues/123",
        )
        assert issue.number == 123
        assert issue.title == "Bug report"
        assert issue.state == "open"
        assert issue.labels == ("bug", "priority-high")
        assert len(issue.assignees) == 2

    def test_raises_value_error_for_zero_number(self) -> None:
        """Test that GitHubIssue raises ValueError for issue number 0."""
        with pytest.raises(ValueError, match="Issue number must be positive"):
            GitHubIssue(
                number=0,
                title="Invalid",
                body="body",
                labels=(),
                state="open",
                assignees=(),
                url="https://github.com/repo/issues/0",
            )

    def test_raises_value_error_for_negative_number(self) -> None:
        """Test that GitHubIssue raises ValueError for negative number."""
        with pytest.raises(ValueError, match="Issue number must be positive"):
            GitHubIssue(
                number=-1,
                title="Invalid",
                body="body",
                labels=(),
                state="open",
                assignees=(),
                url="https://github.com/repo/issues/-1",
            )

    def test_raises_value_error_for_invalid_state(self) -> None:
        """Test that GitHubIssue raises ValueError for invalid state."""
        with pytest.raises(ValueError, match="Invalid state: invalid"):
            GitHubIssue(
                number=1,
                title="Issue",
                body="body",
                labels=(),
                state="invalid",
                assignees=(),
                url="https://github.com/repo/issues/1",
            )

    def test_closed_state(self) -> None:
        """Test creating GitHubIssue with closed state."""
        issue = GitHubIssue(
            number=1,
            title="Fixed",
            body="body",
            labels=(),
            state="closed",
            assignees=(),
            url="https://github.com/repo/issues/1",
        )
        assert issue.state == "closed"

    def test_uppercase_state_open(self) -> None:
        """Test creating GitHubIssue with uppercase OPEN state (from GitHub API)."""
        issue = GitHubIssue(
            number=1,
            title="Issue",
            body="body",
            labels=(),
            state="OPEN",
            assignees=(),
            url="https://github.com/repo/issues/1",
        )
        assert issue.state == "OPEN"

    def test_uppercase_state_closed(self) -> None:
        """Test creating GitHubIssue with uppercase CLOSED state (from GitHub API)."""
        issue = GitHubIssue(
            number=1,
            title="Issue",
            body="body",
            labels=(),
            state="CLOSED",
            assignees=(),
            url="https://github.com/repo/issues/1",
        )
        assert issue.state == "CLOSED"

    def test_mixed_case_state(self) -> None:
        """Test creating GitHubIssue with mixed case state."""
        issue = GitHubIssue(
            number=1,
            title="Issue",
            body="body",
            labels=(),
            state="Open",
            assignees=(),
            url="https://github.com/repo/issues/1",
        )
        assert issue.state == "Open"

    def test_frozen_immutability(self) -> None:
        """Test that GitHubIssue is frozen and cannot be modified."""
        issue = GitHubIssue(
            number=1,
            title="Issue",
            body="body",
            labels=(),
            state="open",
            assignees=(),
            url="url",
        )
        with pytest.raises(AttributeError):
            issue.number = 2  # type: ignore[misc]


class TestPullRequest:
    """Tests for PullRequest dataclass."""

    def test_valid_creation(self) -> None:
        """Test creating a valid PullRequest."""
        pr = PullRequest(
            number=456,
            title="Feature: Add new feature",
            body="PR description",
            state="open",
            url="https://github.com/repo/pull/456",
            head_branch="feature/new-feature",
            base_branch="main",
            mergeable=True,
            draft=False,
        )
        assert pr.number == 456
        assert pr.title == "Feature: Add new feature"
        assert pr.state == "open"
        assert pr.head_branch == "feature/new-feature"
        assert pr.base_branch == "main"
        assert pr.mergeable is True
        assert pr.draft is False

    def test_raises_value_error_for_zero_number(self) -> None:
        """Test that PullRequest raises ValueError for PR number 0."""
        with pytest.raises(ValueError, match="PR number must be positive"):
            PullRequest(
                number=0,
                title="Invalid",
                body="body",
                state="open",
                url="url",
                head_branch="feature",
                base_branch="main",
                mergeable=None,
            )

    def test_raises_value_error_for_negative_number(self) -> None:
        """Test that PullRequest raises ValueError for negative number."""
        with pytest.raises(ValueError, match="PR number must be positive"):
            PullRequest(
                number=-5,
                title="Invalid",
                body="body",
                state="open",
                url="url",
                head_branch="feature",
                base_branch="main",
                mergeable=None,
            )

    def test_mergeable_none(self) -> None:
        """Test creating PullRequest with mergeable=None (unknown state)."""
        pr = PullRequest(
            number=1,
            title="PR",
            body="body",
            state="open",
            url="url",
            head_branch="feature",
            base_branch="main",
            mergeable=None,
        )
        assert pr.mergeable is None

    def test_draft_pr(self) -> None:
        """Test creating PullRequest with draft=True."""
        pr = PullRequest(
            number=1,
            title="WIP: Feature",
            body="body",
            state="open",
            url="url",
            head_branch="feature",
            base_branch="main",
            mergeable=True,
            draft=True,
        )
        assert pr.draft is True

    def test_default_draft_is_false(self) -> None:
        """Test that draft defaults to False."""
        pr = PullRequest(
            number=1,
            title="PR",
            body="body",
            state="open",
            url="url",
            head_branch="feature",
            base_branch="main",
            mergeable=True,
        )
        assert pr.draft is False

    def test_frozen_immutability(self) -> None:
        """Test that PullRequest is frozen and cannot be modified."""
        pr = PullRequest(
            number=1,
            title="PR",
            body="body",
            state="open",
            url="url",
            head_branch="feature",
            base_branch="main",
            mergeable=True,
        )
        with pytest.raises(AttributeError):
            pr.number = 2  # type: ignore[misc]


class TestCheckStatus:
    """Tests for CheckStatus dataclass."""

    def test_passed_property_when_completed_successfully(self) -> None:
        """Test passed property returns True when status=completed and
        conclusion=success."""
        check = CheckStatus(
            name="test",
            status="completed",
            conclusion="success",
            url="https://github.com/repo/runs/1",
        )
        assert check.passed is True

    def test_passed_property_when_completed_with_failure(self) -> None:
        """Test passed property returns False when conclusion is not success."""
        check = CheckStatus(
            name="test",
            status="completed",
            conclusion="failure",
        )
        assert check.passed is False

    def test_passed_property_when_not_completed(self) -> None:
        """Test passed property returns False when status is not completed."""
        check = CheckStatus(
            name="test",
            status="in_progress",
            conclusion=None,
        )
        assert check.passed is False

    def test_pending_property_when_queued(self) -> None:
        """Test pending property returns True when status=queued."""
        check = CheckStatus(
            name="test",
            status="queued",
        )
        assert check.pending is True

    def test_pending_property_when_in_progress(self) -> None:
        """Test pending property returns True when status=in_progress."""
        check = CheckStatus(
            name="test",
            status="in_progress",
        )
        assert check.pending is True

    def test_pending_property_when_completed(self) -> None:
        """Test pending property returns False when status=completed."""
        check = CheckStatus(
            name="test",
            status="completed",
            conclusion="success",
        )
        assert check.pending is False

    def test_with_optional_fields_as_none(self) -> None:
        """Test creating CheckStatus with optional fields as None."""
        check = CheckStatus(
            name="test",
            status="queued",
        )
        assert check.conclusion is None
        assert check.url is None

    def test_frozen_immutability(self) -> None:
        """Test that CheckStatus is frozen and cannot be modified."""
        check = CheckStatus(
            name="test",
            status="queued",
        )
        with pytest.raises(AttributeError):
            check.status = "completed"  # type: ignore[misc]


class TestCodeRabbitFinding:
    """Tests for CodeRabbitFinding dataclass."""

    def test_basic_creation(self) -> None:
        """Test creating CodeRabbitFinding with all fields."""
        finding = CodeRabbitFinding(
            file="src/module.py",
            line=25,
            severity="warning",
            message="Consider using a more descriptive variable name",
            suggestion="Use 'user_count' instead of 'uc'",
            category="style",
        )
        assert finding.file == "src/module.py"
        assert finding.line == 25
        assert finding.severity == "warning"
        assert finding.message == "Consider using a more descriptive variable name"
        assert finding.suggestion == "Use 'user_count' instead of 'uc'"
        assert finding.category == "style"

    def test_with_optional_fields_as_none(self) -> None:
        """Test creating CodeRabbitFinding with optional fields as None."""
        finding = CodeRabbitFinding(
            file="src/module.py",
            line=25,
            severity="error",
            message="Security vulnerability detected",
        )
        assert finding.suggestion is None
        assert finding.category is None

    def test_frozen_immutability(self) -> None:
        """Test that CodeRabbitFinding is frozen and cannot be modified."""
        finding = CodeRabbitFinding(
            file="test.py",
            line=1,
            severity="error",
            message="error",
        )
        with pytest.raises(AttributeError):
            finding.line = 2  # type: ignore[misc]


class TestCodeRabbitResult:
    """Tests for CodeRabbitResult dataclass."""

    def test_has_findings_property_with_findings(self) -> None:
        """Test has_findings property returns True when findings exist."""
        finding = CodeRabbitFinding(
            file="test.py",
            line=1,
            severity="warning",
            message="warning",
        )
        result = CodeRabbitResult(
            findings=(finding,),
            summary="1 finding",
        )
        assert result.has_findings is True

    def test_has_findings_property_without_findings(self) -> None:
        """Test has_findings property returns False when no findings."""
        result = CodeRabbitResult(
            findings=(),
            summary="No issues found",
        )
        assert result.has_findings is False

    def test_error_count_property(self) -> None:
        """Test error_count property counts only error-level findings."""
        error1 = CodeRabbitFinding(
            file="test.py", line=1, severity="error", message="error 1"
        )
        error2 = CodeRabbitFinding(
            file="test.py", line=2, severity="error", message="error 2"
        )
        warning = CodeRabbitFinding(
            file="test.py", line=3, severity="warning", message="warning"
        )
        info = CodeRabbitFinding(
            file="test.py", line=4, severity="info", message="info"
        )

        result = CodeRabbitResult(
            findings=(error1, error2, warning, info),
            summary="4 findings",
        )
        assert result.error_count == 2

    def test_warning_count_property(self) -> None:
        """Test warning_count property counts only warning-level findings."""
        error = CodeRabbitFinding(
            file="test.py", line=1, severity="error", message="error"
        )
        warning1 = CodeRabbitFinding(
            file="test.py", line=2, severity="warning", message="warning 1"
        )
        warning2 = CodeRabbitFinding(
            file="test.py", line=3, severity="warning", message="warning 2"
        )
        warning3 = CodeRabbitFinding(
            file="test.py", line=4, severity="warning", message="warning 3"
        )

        result = CodeRabbitResult(
            findings=(error, warning1, warning2, warning3),
            summary="4 findings",
        )
        assert result.warning_count == 3

    def test_default_values(self) -> None:
        """Test default values for optional fields."""
        result = CodeRabbitResult(findings=())
        assert result.summary == ""
        assert result.raw_output == ""
        assert result.warnings == ()

    def test_with_warnings(self) -> None:
        """Test creating CodeRabbitResult with warnings tuple."""
        result = CodeRabbitResult(
            findings=(),
            summary="Review completed with warnings",
            warnings=("Timeout warning", "Rate limit warning"),
        )
        assert len(result.warnings) == 2
        assert result.warnings[0] == "Timeout warning"

    def test_frozen_immutability(self) -> None:
        """Test that CodeRabbitResult is frozen and cannot be modified."""
        result = CodeRabbitResult(findings=())
        with pytest.raises(AttributeError):
            result.summary = "modified"  # type: ignore[misc]
