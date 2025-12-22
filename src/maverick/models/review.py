"""Data models for code review operations.

This module defines all data models used by the CodeReviewerAgent:
- ReviewSeverity: Enum for finding severity levels
- UsageStats: Token usage and cost tracking
- ReviewFinding: Individual code review finding
- ReviewResult: Aggregate review execution result
- ReviewContext: Input context for review execution

All models use Pydantic v2 for validation and serialization.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# =============================================================================
# Enums
# =============================================================================


class ReviewSeverity(str, Enum):
    """Severity levels for code review findings.

    Attributes:
        CRITICAL: Security vulnerabilities, potential data loss, system crashes.
                  Must fix before merge.
        MAJOR: Logic errors, incorrect behavior, breaking changes.
               Should fix before merge.
        MINOR: Style inconsistencies, minor code smells, formatting.
               Fix if time permits.
        SUGGESTION: Potential improvements, best practices, optimizations.
                    Consider for future.

    Examples:
        >>> ReviewSeverity.CRITICAL
        <ReviewSeverity.CRITICAL: 'critical'>
        >>> ReviewSeverity.CRITICAL.value
        'critical'
    """

    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    SUGGESTION = "suggestion"


# =============================================================================
# Data Models
# =============================================================================


class UsageStats(BaseModel):
    """Usage statistics for agent execution.

    Tracks token usage, cost, and execution time for monitoring
    and cost optimization.

    Attributes:
        input_tokens: Number of tokens in input/prompt.
        output_tokens: Number of tokens in response.
        total_cost: Estimated cost in USD (if available).
        duration_ms: Execution time in milliseconds.

    Examples:
        >>> stats = UsageStats(
        ...     input_tokens=1000,
        ...     output_tokens=500,
        ...     total_cost=0.025,
        ...     duration_ms=2500
        ... )
        >>> stats.total_tokens
        1500
    """

    input_tokens: int = Field(ge=0, description="Number of tokens in input/prompt")
    output_tokens: int = Field(ge=0, description="Number of tokens in response")
    total_cost: float | None = Field(
        default=None, ge=0, description="Estimated cost in USD"
    )
    duration_ms: int = Field(ge=0, description="Execution time in milliseconds")

    @property
    def total_tokens(self) -> int:
        """Calculate total tokens used.

        Returns:
            Sum of input and output tokens.
        """
        return self.input_tokens + self.output_tokens


class ReviewFinding(BaseModel):
    """A single finding from code review.

    Represents an individual issue identified during code review,
    with severity categorization, location information, and
    suggested fixes.

    Attributes:
        severity: Categorization of issue importance.
        file: File path relative to repository root.
        line: Line number where issue occurs (None if file-level).
        message: Human-readable description of the issue.
        suggestion: Recommended fix, ideally with code example.
        convention_ref: Reference to CLAUDE.md section if convention violation.

    Examples:
        >>> finding = ReviewFinding(
        ...     severity=ReviewSeverity.CRITICAL,
        ...     file="src/api/auth.py",
        ...     line=42,
        ...     message="SQL uses string interpolation, vulnerable to injection",
        ...     suggestion="Use parameterized queries instead"
        ... )
        >>> finding.severity
        <ReviewSeverity.CRITICAL: 'critical'>
    """

    severity: ReviewSeverity = Field(
        description="Severity level: critical, major, minor, or suggestion"
    )
    file: str = Field(description="File path relative to repository root")
    line: int | None = Field(
        default=None,
        ge=1,
        description="Line number (1-indexed) or None for file-level findings",
    )
    message: str = Field(
        min_length=10, description="Clear description of the issue found"
    )
    suggestion: str = Field(
        default="",
        description="Actionable fix recommendation with code example if applicable",
    )
    convention_ref: str | None = Field(
        default=None, description="Reference to violated convention in CLAUDE.md"
    )

    model_config = ConfigDict(
        frozen=True,
        json_schema_extra={
            "examples": [
                {
                    "severity": "critical",
                    "file": "src/api/auth.py",
                    "line": 42,
                    "message": "SQL uses string interpolation",
                    "suggestion": "Use parameterized queries",
                    "convention_ref": None,
                },
                {
                    "severity": "minor",
                    "file": "src/utils/helpers.py",
                    "line": 15,
                    "message": "Name uses camelCase not snake_case",
                    "suggestion": "Rename to 'get_data'",
                    "convention_ref": "Code Style > Naming",
                },
            ]
        },
    )


class ReviewResult(BaseModel):
    """Result of a code review execution.

    Aggregates all findings, file counts, and metadata from a
    code review operation. Extends the base AgentResult pattern
    with review-specific fields.

    Attributes:
        success: Whether the review completed without errors.
        findings: List of issues identified during review.
        files_reviewed: Number of files analyzed.
        summary: Human-readable summary of review outcome.
        truncated: Whether the diff was truncated due to size limits.
        output: Raw output from the review (for debugging).
        metadata: Additional context (e.g., branch names, timestamps).
        errors: List of non-fatal errors encountered.
        usage: Token and cost statistics.

    Examples:
        >>> result = ReviewResult(
        ...     success=True,
        ...     findings=[],
        ...     files_reviewed=12,
        ...     summary="Reviewed 12 files, no issues found"
        ... )
        >>> result.has_critical_findings
        False
    """

    success: bool = Field(description="True if review completed, False if failed")
    findings: list[ReviewFinding] = Field(
        default_factory=list, description="List of issues found during review"
    )
    files_reviewed: int = Field(
        ge=0, description="Number of files analyzed (excludes binary files)"
    )
    summary: str = Field(description="Human-readable summary of review outcome")
    truncated: bool = Field(
        default=False, description="True if diff exceeded size limits and was truncated"
    )
    output: str = Field(default="", description="Raw agent output for debugging")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional context (branch, timestamp, etc.)"
    )
    errors: list[str] = Field(
        default_factory=list, description="Non-fatal errors encountered during review"
    )
    usage: UsageStats | None = Field(
        default=None, description="Token usage and cost statistics"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "success": True,
                    "findings": [],
                    "files_reviewed": 0,
                    "summary": "No changes to review",
                    "truncated": False,
                },
                {
                    "success": True,
                    "findings": [
                        {
                            "severity": "major",
                            "file": "src/api/handlers.py",
                            "line": 87,
                            "message": "Missing error handling for DB failure",
                            "suggestion": "Wrap in try/except, return 500",
                        }
                    ],
                    "files_reviewed": 12,
                    "summary": "Reviewed 12 files, found 1 major issue",
                    "truncated": False,
                },
            ]
        }
    )

    @property
    def has_critical_findings(self) -> bool:
        """Check if any findings are critical severity.

        Returns:
            True if at least one finding has CRITICAL severity.
        """
        return any(f.severity == ReviewSeverity.CRITICAL for f in self.findings)

    @property
    def findings_by_severity(self) -> dict[ReviewSeverity, list[ReviewFinding]]:
        """Group findings by severity level.

        Returns:
            Dictionary mapping each severity level to its findings.
            All severity levels are included, even if empty.

        Examples:
            >>> result.findings_by_severity[ReviewSeverity.CRITICAL]
            [ReviewFinding(...), ...]
        """
        result: dict[ReviewSeverity, list[ReviewFinding]] = {
            s: [] for s in ReviewSeverity
        }
        for finding in self.findings:
            result[finding.severity].append(finding)
        return result

    @property
    def findings_by_file(self) -> dict[str, list[ReviewFinding]]:
        """Group findings by file path.

        Returns:
            Dictionary mapping file paths to their findings.
            Only includes files that have at least one finding.

        Examples:
            >>> result.findings_by_file["src/api/auth.py"]
            [ReviewFinding(...), ...]
        """
        result: dict[str, list[ReviewFinding]] = {}
        for finding in self.findings:
            if finding.file not in result:
                result[finding.file] = []
            result[finding.file].append(finding)
        return result


class ReviewContext(BaseModel):
    """Context for code review execution.

    Provides all inputs needed for the CodeReviewerAgent to perform
    a review, including branch information and optional file filters.

    Attributes:
        branch: Feature branch name to review.
        base_branch: Base branch for comparison (default: main).
        file_list: Optional list of specific files to review.
        cwd: Working directory for git operations.

    Examples:
        >>> context = ReviewContext(
        ...     branch="feature/add-auth",
        ...     base_branch="main",
        ...     file_list=["src/api/auth.py", "tests/test_auth.py"]
        ... )
        >>> context.branch
        'feature/add-auth'
    """

    branch: str = Field(description="Feature branch name to review")
    base_branch: str = Field(
        default="main", description="Base branch for diff comparison"
    )
    file_list: list[str] | None = Field(
        default=None, description="Specific files to review (None = all changed)"
    )
    cwd: Path = Field(
        default_factory=Path.cwd, description="Working directory for git operations"
    )

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        json_schema_extra={
            "examples": [
                {
                    "branch": "feature/add-auth",
                    "base_branch": "main",
                    "file_list": None,
                    "cwd": "/path/to/repo",
                },
                {
                    "branch": "bugfix/fix-login",
                    "base_branch": "develop",
                    "file_list": ["src/api/auth.py", "tests/test_auth.py"],
                    "cwd": "/path/to/repo",
                },
            ]
        },
    )
