"""Unit tests for review data models.

Tests the Pydantic models used by CodeReviewerAgent:
- ReviewSeverity enum
- UsageStats model
- ReviewFinding model
- ReviewResult model
- ReviewContext model
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from maverick.models.review import (
    ReviewContext,
    ReviewFinding,
    ReviewResult,
    ReviewSeverity,
    UsageStats,
)

# =============================================================================
# ReviewSeverity Tests
# =============================================================================


class TestReviewSeverity:
    """Tests for ReviewSeverity enum."""

    def test_severity_values(self) -> None:
        """Test all severity values are strings."""
        assert ReviewSeverity.CRITICAL.value == "critical"
        assert ReviewSeverity.MAJOR.value == "major"
        assert ReviewSeverity.MINOR.value == "minor"
        assert ReviewSeverity.SUGGESTION.value == "suggestion"

    def test_severity_is_string_enum(self) -> None:
        """Test severity enum inherits from str."""
        assert isinstance(ReviewSeverity.CRITICAL, str)
        assert ReviewSeverity.CRITICAL == "critical"

    def test_severity_iteration(self) -> None:
        """Test all severity levels are iterable."""
        severities = list(ReviewSeverity)
        assert len(severities) == 4
        assert ReviewSeverity.CRITICAL in severities
        assert ReviewSeverity.MAJOR in severities
        assert ReviewSeverity.MINOR in severities
        assert ReviewSeverity.SUGGESTION in severities

    def test_severity_from_string(self) -> None:
        """Test creating severity from string value."""
        assert ReviewSeverity("critical") == ReviewSeverity.CRITICAL
        assert ReviewSeverity("major") == ReviewSeverity.MAJOR

    def test_severity_invalid_value_raises(self) -> None:
        """Test invalid string raises ValueError."""
        with pytest.raises(ValueError):
            ReviewSeverity("invalid")


# =============================================================================
# UsageStats Tests
# =============================================================================


class TestUsageStats:
    """Tests for UsageStats model."""

    def test_creation_with_valid_values(self) -> None:
        """Test creating UsageStats with valid values."""
        stats = UsageStats(
            input_tokens=1000,
            output_tokens=500,
            total_cost=0.025,
            duration_ms=2500,
        )

        assert stats.input_tokens == 1000
        assert stats.output_tokens == 500
        assert stats.total_cost == 0.025
        assert stats.duration_ms == 2500

    def test_total_tokens_property(self) -> None:
        """Test total_tokens calculated property."""
        stats = UsageStats(
            input_tokens=1000,
            output_tokens=500,
            total_cost=0.025,
            duration_ms=2500,
        )

        assert stats.total_tokens == 1500

    def test_total_cost_is_optional(self) -> None:
        """Test total_cost can be None."""
        stats = UsageStats(
            input_tokens=100,
            output_tokens=50,
            total_cost=None,
            duration_ms=500,
        )

        assert stats.total_cost is None

    def test_negative_tokens_raises_validation_error(self) -> None:
        """Test negative token counts are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            UsageStats(
                input_tokens=-1,
                output_tokens=50,
                duration_ms=500,
            )

        assert "input_tokens" in str(exc_info.value)

    def test_negative_duration_raises_validation_error(self) -> None:
        """Test negative duration is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            UsageStats(
                input_tokens=100,
                output_tokens=50,
                duration_ms=-1,
            )

        assert "duration_ms" in str(exc_info.value)

    def test_negative_cost_raises_validation_error(self) -> None:
        """Test negative cost is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            UsageStats(
                input_tokens=100,
                output_tokens=50,
                total_cost=-0.01,
                duration_ms=500,
            )

        assert "total_cost" in str(exc_info.value)

    def test_zero_values_are_valid(self) -> None:
        """Test zero values are accepted."""
        stats = UsageStats(
            input_tokens=0,
            output_tokens=0,
            total_cost=0,
            duration_ms=0,
        )

        assert stats.input_tokens == 0
        assert stats.output_tokens == 0
        assert stats.total_tokens == 0


# =============================================================================
# ReviewFinding Tests
# =============================================================================


class TestReviewFinding:
    """Tests for ReviewFinding model."""

    def test_creation_with_required_fields(self) -> None:
        """Test creating finding with required fields only."""
        finding = ReviewFinding(
            severity=ReviewSeverity.CRITICAL,
            file="src/api/auth.py",
            message="SQL injection vulnerability in query construction",
        )

        assert finding.severity == ReviewSeverity.CRITICAL
        assert finding.file == "src/api/auth.py"
        assert "SQL injection" in finding.message
        assert finding.line is None
        assert finding.suggestion == ""
        assert finding.convention_ref is None

    def test_creation_with_all_fields(self) -> None:
        """Test creating finding with all fields."""
        finding = ReviewFinding(
            severity=ReviewSeverity.MINOR,
            file="src/utils/helpers.py",
            line=42,
            message="Function name uses camelCase instead of snake_case",
            suggestion="Rename getData to get_data",
            convention_ref="Code Style > Naming",
        )

        assert finding.line == 42
        assert finding.suggestion == "Rename getData to get_data"
        assert finding.convention_ref == "Code Style > Naming"

    def test_finding_is_frozen(self) -> None:
        """Test finding model is immutable."""
        finding = ReviewFinding(
            severity=ReviewSeverity.MAJOR,
            file="test.py",
            message="Test finding message here",
        )

        with pytest.raises(ValidationError):
            finding.severity = ReviewSeverity.MINOR  # type: ignore[misc]

    def test_line_must_be_positive(self) -> None:
        """Test line number must be >= 1."""
        with pytest.raises(ValidationError) as exc_info:
            ReviewFinding(
                severity=ReviewSeverity.MINOR,
                file="test.py",
                line=0,
                message="Test finding with zero line",
            )

        assert "line" in str(exc_info.value)

    def test_message_minimum_length(self) -> None:
        """Test message must have minimum length."""
        with pytest.raises(ValidationError) as exc_info:
            ReviewFinding(
                severity=ReviewSeverity.MINOR,
                file="test.py",
                message="Short",  # Too short
            )

        assert "message" in str(exc_info.value)

    def test_severity_accepts_string_value(self) -> None:
        """Test severity can be set with string value."""
        finding = ReviewFinding(
            severity="critical",  # type: ignore[arg-type]
            file="test.py",
            message="Test finding with string severity",
        )

        assert finding.severity == ReviewSeverity.CRITICAL

    def test_invalid_severity_raises_error(self) -> None:
        """Test invalid severity string raises error."""
        with pytest.raises(ValidationError):
            ReviewFinding(
                severity="invalid",  # type: ignore[arg-type]
                file="test.py",
                message="Test finding with invalid severity",
            )


# =============================================================================
# ReviewResult Tests
# =============================================================================


class TestReviewResult:
    """Tests for ReviewResult model."""

    def test_creation_with_required_fields(self) -> None:
        """Test creating result with required fields only."""
        result = ReviewResult(
            success=True,
            files_reviewed=10,
            summary="Reviewed 10 files, no issues found",
        )

        assert result.success is True
        assert result.files_reviewed == 10
        assert result.findings == []
        assert result.truncated is False
        assert result.output == ""
        assert result.metadata == {}
        assert result.errors == []
        assert result.usage is None

    def test_creation_with_findings(self) -> None:
        """Test creating result with findings list."""
        findings = [
            ReviewFinding(
                severity=ReviewSeverity.CRITICAL,
                file="auth.py",
                message="Security vulnerability detected in authentication",
            ),
            ReviewFinding(
                severity=ReviewSeverity.MINOR,
                file="utils.py",
                message="Minor style issue with naming convention",
            ),
        ]

        result = ReviewResult(
            success=True,
            files_reviewed=2,
            summary="Reviewed 2 files, found 2 issues",
            findings=findings,
        )

        assert len(result.findings) == 2

    def test_has_critical_findings_true(self) -> None:
        """Test has_critical_findings returns True when critical exists."""
        result = ReviewResult(
            success=True,
            files_reviewed=1,
            summary="Found critical issue",
            findings=[
                ReviewFinding(
                    severity=ReviewSeverity.CRITICAL,
                    file="test.py",
                    message="Critical security vulnerability found",
                ),
            ],
        )

        assert result.has_critical_findings is True

    def test_has_critical_findings_false(self) -> None:
        """Test has_critical_findings returns False when no critical."""
        result = ReviewResult(
            success=True,
            files_reviewed=1,
            summary="Found minor issue",
            findings=[
                ReviewFinding(
                    severity=ReviewSeverity.MINOR,
                    file="test.py",
                    message="Minor style issue detected",
                ),
            ],
        )

        assert result.has_critical_findings is False

    def test_has_critical_findings_empty(self) -> None:
        """Test has_critical_findings returns False when no findings."""
        result = ReviewResult(
            success=True,
            files_reviewed=0,
            summary="No issues found",
        )

        assert result.has_critical_findings is False

    def test_findings_by_severity(self) -> None:
        """Test findings_by_severity groups correctly."""
        findings = [
            ReviewFinding(
                severity=ReviewSeverity.CRITICAL,
                file="a.py",
                message="Critical issue in file a",
            ),
            ReviewFinding(
                severity=ReviewSeverity.MINOR,
                file="b.py",
                message="Minor issue in file b",
            ),
            ReviewFinding(
                severity=ReviewSeverity.CRITICAL,
                file="c.py",
                message="Another critical issue",
            ),
        ]

        result = ReviewResult(
            success=True,
            files_reviewed=3,
            summary="Found issues",
            findings=findings,
        )

        by_severity = result.findings_by_severity

        assert len(by_severity[ReviewSeverity.CRITICAL]) == 2
        assert len(by_severity[ReviewSeverity.MINOR]) == 1
        assert len(by_severity[ReviewSeverity.MAJOR]) == 0
        assert len(by_severity[ReviewSeverity.SUGGESTION]) == 0

    def test_findings_by_severity_includes_all_levels(self) -> None:
        """Test findings_by_severity includes all severity levels."""
        result = ReviewResult(
            success=True,
            files_reviewed=0,
            summary="No issues",
        )

        by_severity = result.findings_by_severity

        for severity in ReviewSeverity:
            assert severity in by_severity
            assert by_severity[severity] == []

    def test_findings_by_file(self) -> None:
        """Test findings_by_file groups correctly."""
        findings = [
            ReviewFinding(
                severity=ReviewSeverity.MAJOR,
                file="auth.py",
                message="Issue 1 in auth.py file",
            ),
            ReviewFinding(
                severity=ReviewSeverity.MINOR,
                file="auth.py",
                message="Issue 2 in auth.py file",
            ),
            ReviewFinding(
                severity=ReviewSeverity.MINOR,
                file="utils.py",
                message="Issue in utils.py file",
            ),
        ]

        result = ReviewResult(
            success=True,
            files_reviewed=2,
            summary="Found issues",
            findings=findings,
        )

        by_file = result.findings_by_file

        assert len(by_file["auth.py"]) == 2
        assert len(by_file["utils.py"]) == 1
        assert "other.py" not in by_file

    def test_files_reviewed_cannot_be_negative(self) -> None:
        """Test files_reviewed must be >= 0."""
        with pytest.raises(ValidationError) as exc_info:
            ReviewResult(
                success=True,
                files_reviewed=-1,
                summary="Invalid count",
            )

        assert "files_reviewed" in str(exc_info.value)

    def test_result_with_usage_stats(self) -> None:
        """Test result can include usage statistics."""
        usage = UsageStats(
            input_tokens=1000,
            output_tokens=500,
            total_cost=0.025,
            duration_ms=2500,
        )

        result = ReviewResult(
            success=True,
            files_reviewed=5,
            summary="Reviewed 5 files",
            usage=usage,
        )

        assert result.usage is not None
        assert result.usage.input_tokens == 1000

    def test_result_with_metadata(self) -> None:
        """Test result can include metadata."""
        result = ReviewResult(
            success=True,
            files_reviewed=5,
            summary="Reviewed 5 files",
            metadata={
                "branch": "feature/test",
                "base_branch": "main",
                "duration_ms": 1500,
                "chunks_used": 0,
            },
        )

        assert result.metadata["branch"] == "feature/test"
        assert result.metadata["chunks_used"] == 0

    def test_result_with_errors(self) -> None:
        """Test result can include non-fatal errors."""
        result = ReviewResult(
            success=True,
            files_reviewed=5,
            summary="Reviewed 5 files with warnings",
            errors=[
                "Warning: Could not read .env file",
                "Warning: Binary file skipped",
            ],
        )

        assert len(result.errors) == 2


# =============================================================================
# ReviewContext Tests
# =============================================================================


class TestReviewContext:
    """Tests for ReviewContext model."""

    def test_creation_with_required_fields(self) -> None:
        """Test creating context with required fields only."""
        context = ReviewContext(
            branch="feature/test",
        )

        assert context.branch == "feature/test"
        assert context.base_branch == "main"  # default
        assert context.file_list is None
        # cwd defaults to current working directory (Path.cwd())
        assert isinstance(context.cwd, Path)

    def test_creation_with_all_fields(self) -> None:
        """Test creating context with all fields."""
        context = ReviewContext(
            branch="feature/auth",
            base_branch="develop",
            file_list=["src/auth.py", "tests/test_auth.py"],
            cwd=Path("/path/to/repo"),
        )

        assert context.branch == "feature/auth"
        assert context.base_branch == "develop"
        assert context.file_list == ["src/auth.py", "tests/test_auth.py"]
        assert context.cwd == Path("/path/to/repo")

    def test_cwd_accepts_string(self) -> None:
        """Test cwd accepts string and converts to Path."""
        context = ReviewContext(
            branch="feature/test",
            cwd="/path/to/repo",  # type: ignore[arg-type]
        )

        assert isinstance(context.cwd, Path)
        assert str(context.cwd) == "/path/to/repo"

    def test_default_base_branch_is_main(self) -> None:
        """Test default base_branch is 'main'."""
        context = ReviewContext(branch="feature/test")

        assert context.base_branch == "main"

    def test_empty_file_list_is_different_from_none(self) -> None:
        """Test empty file_list vs None have different meanings."""
        context_none = ReviewContext(
            branch="feature/test",
            file_list=None,
        )
        context_empty = ReviewContext(
            branch="feature/test",
            file_list=[],
        )

        assert context_none.file_list is None
        assert context_empty.file_list == []

    def test_file_list_preserved_exactly(self) -> None:
        """Test file_list entries are preserved exactly."""
        files = ["path/to/file.py", "another/file.tsx"]
        context = ReviewContext(
            branch="feature/test",
            file_list=files,
        )

        assert context.file_list == files


# =============================================================================
# Model Serialization Tests
# =============================================================================


class TestModelSerialization:
    """Tests for model JSON serialization."""

    def test_usage_stats_to_dict(self) -> None:
        """Test UsageStats serializes to dict correctly."""
        stats = UsageStats(
            input_tokens=100,
            output_tokens=50,
            total_cost=0.01,
            duration_ms=1000,
        )

        data = stats.model_dump()

        assert data["input_tokens"] == 100
        assert data["output_tokens"] == 50
        assert data["total_cost"] == 0.01
        assert data["duration_ms"] == 1000

    def test_finding_to_dict(self) -> None:
        """Test ReviewFinding serializes to dict correctly."""
        finding = ReviewFinding(
            severity=ReviewSeverity.MAJOR,
            file="test.py",
            line=10,
            message="Test message for serialization",
            suggestion="Fix the issue",
        )

        data = finding.model_dump()

        assert data["severity"] == "major"
        assert data["file"] == "test.py"
        assert data["line"] == 10

    def test_result_to_json(self) -> None:
        """Test ReviewResult serializes to JSON string."""
        result = ReviewResult(
            success=True,
            files_reviewed=5,
            summary="Test summary",
            findings=[
                ReviewFinding(
                    severity=ReviewSeverity.MINOR,
                    file="test.py",
                    message="Test finding message",
                ),
            ],
        )

        json_str = result.model_dump_json()

        assert '"success": true' in json_str or '"success":true' in json_str
        assert "test.py" in json_str

    def test_finding_from_dict(self) -> None:
        """Test ReviewFinding deserializes from dict."""
        data = {
            "severity": "critical",
            "file": "auth.py",
            "line": 42,
            "message": "Security vulnerability found",
            "suggestion": "Use secure function",
        }

        finding = ReviewFinding.model_validate(data)

        assert finding.severity == ReviewSeverity.CRITICAL
        assert finding.file == "auth.py"
        assert finding.line == 42

    def test_result_from_dict(self) -> None:
        """Test ReviewResult deserializes from dict."""
        data = {
            "success": True,
            "files_reviewed": 10,
            "summary": "Reviewed 10 files",
            "findings": [
                {
                    "severity": "major",
                    "file": "test.py",
                    "message": "Major issue found",
                }
            ],
        }

        result = ReviewResult.model_validate(data)

        assert result.success is True
        assert result.files_reviewed == 10
        assert len(result.findings) == 1
        assert result.findings[0].severity == ReviewSeverity.MAJOR
