"""Data model types for action results.

All action result types are frozen dataclasses with slots for memory efficiency
and immutability. These types are returned by Python actions in workflow steps.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

# =============================================================================
# Workspace Types
# =============================================================================


@dataclass(frozen=True, slots=True)
class WorkspaceState:
    """State of the workspace after initialization."""

    branch_name: str
    base_branch: str
    is_clean: bool
    synced_with_base: bool
    task_file_path: Path | None


# =============================================================================
# Git Types
# =============================================================================


@dataclass(frozen=True, slots=True)
class GitCommitResult:
    """Result of git commit operation."""

    success: bool
    commit_sha: str | None
    message: str
    files_committed: tuple[str, ...]
    error: str | None


@dataclass(frozen=True, slots=True)
class GitPushResult:
    """Result of git push operation."""

    success: bool
    remote: str
    branch: str
    upstream_set: bool
    error: str | None


@dataclass(frozen=True, slots=True)
class GitBranchResult:
    """Result of branch creation."""

    success: bool
    branch_name: str
    base_branch: str
    created: bool  # True if created, False if checked out existing
    error: str | None


# =============================================================================
# GitHub Types
# =============================================================================


@dataclass(frozen=True, slots=True)
class FetchedIssue:
    """Single GitHub issue fetched from API."""

    number: int
    title: str
    body: str | None
    labels: tuple[str, ...]
    assignee: str | None
    url: str
    state: str  # "open", "closed"


@dataclass(frozen=True, slots=True)
class FetchIssuesResult:
    """Result of fetching multiple issues."""

    success: bool
    issues: tuple[FetchedIssue, ...]
    total_count: int
    error: str | None


@dataclass(frozen=True, slots=True)
class FetchSingleIssueResult:
    """Result of fetching a single issue."""

    success: bool
    issue: FetchedIssue | None
    error: str | None


@dataclass(frozen=True, slots=True)
class PRCreationResult:
    """Result of PR creation via GitHub CLI."""

    success: bool
    pr_number: int | None
    pr_url: str | None
    title: str
    draft: bool
    base_branch: str
    error: str | None


# =============================================================================
# Validation Types
# =============================================================================


@dataclass(frozen=True, slots=True)
class StageResultEntry:
    """Result of a single validation stage."""

    name: str
    passed: bool
    errors: tuple[str, ...]
    duration_ms: int


@dataclass(frozen=True, slots=True)
class ValidationReportResult:
    """Final validation report from validate_and_fix fragment."""

    passed: bool
    stages: tuple[StageResultEntry, ...]
    attempts: int
    fixes_applied: tuple[str, ...]
    remaining_errors: tuple[str, ...]
    suggestions: tuple[str, ...]


# =============================================================================
# Review Types
# =============================================================================


@dataclass(frozen=True, slots=True)
class PRMetadata:
    """Pull request metadata."""

    number: int | None
    title: str | None
    description: str | None
    author: str | None
    labels: tuple[str, ...]
    base_branch: str


@dataclass(frozen=True, slots=True)
class ReviewContextResult:
    """Gathered context for code review."""

    pr_metadata: PRMetadata
    changed_files: tuple[str, ...]
    diff: str
    commits: tuple[str, ...]
    coderabbit_available: bool


@dataclass(frozen=True, slots=True)
class CodeRabbitResult:
    """Result from CodeRabbit review."""

    available: bool
    findings: tuple[dict[str, Any], ...]
    error: str | None


@dataclass(frozen=True, slots=True)
class CombinedReviewResult:
    """Combined review results from all sources."""

    review_report: str
    issues: tuple[dict[str, Any], ...]
    recommendation: str  # "approve", "request_changes", "comment"


# =============================================================================
# Refuel Types
# =============================================================================


@dataclass(frozen=True, slots=True)
class ProcessedIssueEntry:
    """Result of processing a single issue."""

    issue_number: int
    issue_title: str
    status: str  # "fixed", "failed", "skipped"
    branch_name: str | None
    pr_url: str | None
    error: str | None


@dataclass(frozen=True, slots=True)
class RefuelSummaryResult:
    """Summary of refuel workflow execution."""

    total_issues: int
    processed_count: int
    success_count: int
    failure_count: int
    skipped_count: int
    issues: tuple[ProcessedIssueEntry, ...]
    pr_urls: tuple[str, ...]
