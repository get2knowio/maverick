"""Issue fix models for IssueFixerAgent.

This module defines data models for GitHub issue resolution,
fix results, and agent context.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from maverick.models.implementation import FileChange

# =============================================================================
# Result Objects (T045)
# =============================================================================


class FixResult(BaseModel):
    """Result of a GitHub issue fix attempt.

    Returned by IssueFixerAgent.execute() to summarize
    the fix attempt and verification.

    Attributes:
        success: True if issue was fixed and verified.
        issue_number: GitHub issue number.
        issue_title: Issue title for reference.
        issue_url: Link to the GitHub issue.
        root_cause: Identified root cause of the issue.
        fix_description: Description of the fix applied.
        files_changed: List of file changes made.
        commit_sha: Git commit SHA if committed.
        verification_passed: True if fix was verified working.
        validation_passed: True if code validation passed.
        output: Raw agent output for debugging.
        metadata: Additional context.
        errors: List of error messages encountered.
    """

    success: bool = Field(description="True if issue was fixed")
    issue_number: int = Field(ge=1, description="GitHub issue number")
    issue_title: str = Field(description="Issue title")
    issue_url: str = Field(default="", description="GitHub issue URL")
    root_cause: str = Field(default="", description="Identified root cause")
    fix_description: str = Field(default="", description="Description of fix applied")
    files_changed: list[FileChange] = Field(
        default_factory=list, description="Files modified"
    )
    commit_sha: str | None = Field(default=None, description="Commit SHA")
    verification_passed: bool = Field(default=False, description="Fix verified")
    validation_passed: bool = Field(default=True, description="Validation passed")
    output: str = Field(default="", description="Raw output for debugging")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional context"
    )
    errors: list[str] = Field(default_factory=list, description="Error messages")

    @property
    def total_lines_changed(self) -> int:
        """Total lines added + removed."""
        return sum(c.lines_added + c.lines_removed for c in self.files_changed)

    @property
    def is_minimal_fix(self) -> bool:
        """Check if fix is under 100 lines (typical bug fix target)."""
        return self.total_lines_changed < 100

    def to_summary(self) -> str:
        """Generate human-readable summary."""
        status = "Fixed" if self.success else "Failed"
        parts = [f"{status} #{self.issue_number}: {self.issue_title}"]
        if self.files_changed:
            file_count = len(self.files_changed)
            lines = self.total_lines_changed
            parts.append(f"{file_count} files, {lines} lines")
        if self.verification_passed:
            parts.append("verified")
        return " | ".join(parts)


# =============================================================================
# Context Objects (T046)
# =============================================================================


class IssueFixerContext(BaseModel):
    """Input context for IssueFixerAgent execution.

    Provides issue source (number or pre-fetched data) and execution environment.

    Attributes:
        issue_number: GitHub issue number (mutually exclusive with issue_data).
        issue_data: Pre-fetched issue data (mutually exclusive with issue_number).
        cwd: Working directory for execution.
        skip_validation: If True, skip validation steps.
        dry_run: If True, don't commit changes.
    """

    issue_number: int | None = Field(
        default=None, ge=1, description="GitHub issue number"
    )
    issue_data: dict[str, Any] | None = Field(
        default=None, description="Pre-fetched issue data"
    )
    cwd: Path = Field(default_factory=Path.cwd, description="Working directory")
    skip_validation: bool = Field(default=False, description="Skip validation steps")
    dry_run: bool = Field(default=False, description="Don't create commits")

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @model_validator(mode="after")
    def validate_issue_source(self) -> IssueFixerContext:
        """Ensure exactly one issue source is provided."""
        if self.issue_number and self.issue_data:
            raise ValueError("Provide issue_number OR issue_data, not both")
        if not self.issue_number and not self.issue_data:
            raise ValueError("Must provide issue_number or issue_data")
        if self.issue_data:
            required = {"number", "title", "body"}
            missing = required - set(self.issue_data.keys())
            if missing:
                raise ValueError(f"issue_data missing required fields: {missing}")
        return self

    @property
    def effective_issue_number(self) -> int:
        """Get issue number from either source."""
        if self.issue_number:
            return self.issue_number
        num = self.issue_data["number"]  # type: ignore[index]
        return int(num)
