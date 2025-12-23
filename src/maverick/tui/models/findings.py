from __future__ import annotations

from dataclasses import dataclass

from maverick.tui.models.enums import FindingSeverity, IssueSeverity


@dataclass(frozen=True, slots=True)
class CodeLocation:
    """Location in source code.

    Attributes:
        file_path: Path to the file relative to repo root.
        line_number: Line number (1-indexed).
        end_line: End line for multi-line ranges.
    """

    file_path: str
    line_number: int
    end_line: int | None = None


@dataclass(frozen=True, slots=True)
class CodeContext:
    """Code context for a finding.

    Attributes:
        file_path: Path to the file.
        start_line: First line of context.
        end_line: Last line of context.
        content: The code content.
        highlight_line: Line to highlight (the finding line).
    """

    file_path: str
    start_line: int
    end_line: int
    content: str
    highlight_line: int


@dataclass(frozen=True, slots=True)
class ReviewFinding:
    """A single finding from code review.

    Attributes:
        id: Unique identifier for the finding.
        severity: Error, warning, or suggestion.
        location: File path and line number.
        title: Short summary of the finding.
        description: Full description with context.
        suggested_fix: Optional suggested code change.
        source: Review source (e.g., "coderabbit", "architecture").
    """

    id: str
    severity: FindingSeverity
    location: CodeLocation
    title: str
    description: str
    suggested_fix: str | None = None
    source: str = "review"


@dataclass(frozen=True, slots=True)
class ReviewFindingItem:
    """A finding with selection state for the UI.

    Attributes:
        finding: The review finding data.
        selected: Whether this item is selected for bulk action.
    """

    finding: ReviewFinding
    selected: bool = False


@dataclass(frozen=True, slots=True)
class FixResult:
    """Result of fixing a single finding.

    Attributes:
        finding_id: ID of the finding.
        success: Whether fix succeeded.
        error_message: Error message (if failed).
    """

    finding_id: str
    success: bool
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class ReviewIssue:
    """A single issue from code review.

    Attributes:
        file_path: Path to the file.
        line_number: Line number (1-indexed).
        severity: Issue severity.
        message: Issue message.
        source: Issue source.
    """

    file_path: str
    line_number: int | None
    severity: IssueSeverity
    message: str
    source: str  # "architecture" | "coderabbit" | "validation"
