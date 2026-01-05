"""CodeReviewerAgent API Contract.

This module defines the interface contract for the CodeReviewerAgent.
It serves as the authoritative reference for:
- Input/output types
- Method signatures
- Expected behavior

Implementation must conform to this contract.
"""

from __future__ import annotations

from abc import abstractmethod
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    pass


# =============================================================================
# Enums
# =============================================================================


class ReviewSeverity(str, Enum):
    """Severity levels for code review findings.

    Attributes:
        CRITICAL: Security vulnerabilities, data loss risks. Must fix.
        MAJOR: Logic errors, incorrect behavior. Should fix.
        MINOR: Style issues, minor inconsistencies. Fix if time.
        SUGGESTION: Improvements, best practices. Consider.
    """

    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    SUGGESTION = "suggestion"


# =============================================================================
# Data Models (Pydantic)
# =============================================================================


class ReviewFinding(BaseModel):
    """A single finding from code review.

    Attributes:
        severity: Categorization of issue importance.
        file: File path relative to repository root.
        line: Line number where issue occurs (None if file-level).
        message: Human-readable description of the issue.
        suggestion: Recommended fix, ideally with code example.
        convention_ref: Reference to CLAUDE.md section if convention violation.
    """

    severity: ReviewSeverity
    file: str
    line: int | None = None
    message: str
    suggestion: str = ""
    convention_ref: str | None = None

    class Config:
        frozen = True


class UsageStats(BaseModel):
    """Usage statistics for agent execution.

    Attributes:
        input_tokens: Number of tokens in input/prompt.
        output_tokens: Number of tokens in response.
        total_cost: Estimated cost in USD (if available).
        duration_ms: Execution time in milliseconds.
    """

    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    total_cost: float | None = Field(default=None, ge=0)
    duration_ms: int = Field(ge=0)

    @property
    def total_tokens(self) -> int:
        """Total tokens used."""
        return self.input_tokens + self.output_tokens


class ReviewResult(BaseModel):
    """Result of a code review execution.

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
    """

    success: bool
    findings: list[ReviewFinding] = Field(default_factory=list)
    files_reviewed: int = Field(ge=0)
    summary: str
    truncated: bool = False
    output: str = ""
    metadata: dict = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    usage: UsageStats | None = None

    @property
    def has_critical_findings(self) -> bool:
        """Check if any findings are critical severity."""
        return any(f.severity == ReviewSeverity.CRITICAL for f in self.findings)

    @property
    def findings_by_severity(self) -> dict[ReviewSeverity, list[ReviewFinding]]:
        """Group findings by severity level."""
        result: dict[ReviewSeverity, list[ReviewFinding]] = {
            s: [] for s in ReviewSeverity
        }
        for finding in self.findings:
            result[finding.severity].append(finding)
        return result

    @property
    def findings_by_file(self) -> dict[str, list[ReviewFinding]]:
        """Group findings by file path."""
        result: dict[str, list[ReviewFinding]] = {}
        for finding in self.findings:
            if finding.file not in result:
                result[finding.file] = []
            result[finding.file].append(finding)
        return result


class ReviewContext(BaseModel):
    """Context for code review execution.

    Attributes:
        branch: Feature branch name to review.
        base_branch: Base branch for comparison (default: main).
        file_list: Optional list of specific files to review.
        cwd: Working directory for git operations.
    """

    branch: str
    base_branch: str = "main"
    file_list: list[str] | None = None
    cwd: Path = Field(default_factory=Path.cwd)

    class Config:
        arbitrary_types_allowed = True


# =============================================================================
# Agent Protocol (Interface)
# =============================================================================


@runtime_checkable
class CodeReviewerProtocol(Protocol):
    """Protocol defining the CodeReviewerAgent interface.

    Implementations must provide:
    - execute(): Async method to perform code review
    - name: Agent identifier
    - allowed_tools: List of permitted tool names

    Example:
        ```python
        agent = CodeReviewerAgent(config=config)
        context = ReviewContext(branch="feature/auth")
        result = await agent.execute(context)

        if result.has_critical_findings:
            print("Critical issues found!")
        ```
    """

    @property
    def name(self) -> str:
        """Agent identifier (e.g., 'code-reviewer')."""
        ...

    @property
    def allowed_tools(self) -> list[str]:
        """List of permitted tool names.

        Must be read-only tools: Read, Glob, Grep, Bash
        """
        ...

    @abstractmethod
    async def execute(self, context: ReviewContext) -> ReviewResult:
        """Execute code review on the specified branch.

        Args:
            context: Review context with branch info and optional file filter.

        Returns:
            ReviewResult with findings, file count, and summary.

        Raises:
            AgentError: If git operations fail, merge conflicts exist,
                or other unrecoverable errors occur.

        Behavior:
            - FR-008: Retrieves diff between context.branch and context.base_branch
            - FR-009: Reads CLAUDE.md for convention checking (if exists)
            - FR-014: Filters to context.file_list if provided
            - FR-015: Proceeds without conventions if CLAUDE.md missing
            - FR-017: Truncates if diff > 2000 lines or 50 files
            - FR-018: Raises AgentError for git failures
            - FR-019: Returns empty result if no changes
            - FR-020: Silently excludes binary files
            - FR-021: Auto-chunks if approaching token limits
        """
        ...


# =============================================================================
# Constants
# =============================================================================


# Truncation thresholds (FR-017)
MAX_DIFF_LINES: int = 2000
MAX_DIFF_FILES: int = 50

# Token budget for chunking (FR-021)
MAX_TOKENS_PER_CHUNK: int = 50_000

# Read-only tools (FR-006)
ALLOWED_TOOLS: list[str] = ["Read", "Glob", "Grep", "Bash"]

# Default base branch
DEFAULT_BASE_BRANCH: str = "main"


# =============================================================================
# Error Codes
# =============================================================================


class ReviewErrorCode(str, Enum):
    """Error codes for review failures.

    Used in AgentError for diagnostic purposes.
    """

    INVALID_BRANCH = "INVALID_BRANCH"
    GIT_ERROR = "GIT_ERROR"
    MERGE_CONFLICTS = "MERGE_CONFLICTS"
    TIMEOUT = "TIMEOUT"
    PARSE_ERROR = "PARSE_ERROR"
    TOKEN_LIMIT = "TOKEN_LIMIT"
