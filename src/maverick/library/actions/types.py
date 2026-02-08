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
    error: str | None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "branch_name": self.branch_name,
            "base_branch": self.base_branch,
            "is_clean": self.is_clean,
            "synced_with_base": self.synced_with_base,
            "task_file_path": str(self.task_file_path) if self.task_file_path else None,
            "error": self.error,
        }


# =============================================================================
# Dependency Types
# =============================================================================


@dataclass(frozen=True, slots=True)
class DependencySyncResult:
    """Result of dependency sync operation."""

    success: bool
    command: str | None
    output: str | None
    skipped: bool
    reason: str | None
    error: str | None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "success": self.success,
            "command": self.command,
            "output": self.output,
            "skipped": self.skipped,
            "reason": self.reason,
            "error": self.error,
        }


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

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "success": self.success,
            "commit_sha": self.commit_sha,
            "message": self.message,
            "files_committed": list(self.files_committed),
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class GitPushResult:
    """Result of git push operation."""

    success: bool
    remote: str
    branch: str
    upstream_set: bool
    error: str | None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "success": self.success,
            "remote": self.remote,
            "branch": self.branch,
            "upstream_set": self.upstream_set,
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class GitBranchResult:
    """Result of branch creation."""

    success: bool
    branch_name: str
    base_branch: str
    created: bool  # True if created, False if checked out existing
    error: str | None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "success": self.success,
            "branch_name": self.branch_name,
            "base_branch": self.base_branch,
            "created": self.created,
            "error": self.error,
        }


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

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "number": self.number,
            "title": self.title,
            "body": self.body,
            "labels": list(self.labels),
            "assignee": self.assignee,
            "url": self.url,
            "state": self.state,
        }


@dataclass(frozen=True, slots=True)
class FetchIssuesResult:
    """Result of fetching multiple issues."""

    success: bool
    issues: tuple[FetchedIssue, ...]
    total_count: int
    error: str | None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "success": self.success,
            "issues": [issue.to_dict() for issue in self.issues],
            "total_count": self.total_count,
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class FetchSingleIssueResult:
    """Result of fetching a single issue."""

    success: bool
    issue: FetchedIssue | None
    error: str | None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "success": self.success,
            "issue": self.issue.to_dict() if self.issue else None,
            "error": self.error,
        }


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

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "success": self.success,
            "pr_number": self.pr_number,
            "pr_url": self.pr_url,
            "title": self.title,
            "draft": self.draft,
            "base_branch": self.base_branch,
            "error": self.error,
        }


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

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "name": self.name,
            "passed": self.passed,
            "errors": list(self.errors),
            "duration_ms": self.duration_ms,
        }


@dataclass(frozen=True, slots=True)
class ValidationReportResult:
    """Final validation report from validate_and_fix fragment."""

    passed: bool
    stages: tuple[StageResultEntry, ...]
    attempts: int
    fixes_applied: tuple[str, ...]
    remaining_errors: tuple[str, ...]
    suggestions: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "passed": self.passed,
            "stages": [stage.to_dict() for stage in self.stages],
            "attempts": self.attempts,
            "fixes_applied": list(self.fixes_applied),
            "remaining_errors": list(self.remaining_errors),
            "suggestions": list(self.suggestions),
        }


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

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "number": self.number,
            "title": self.title,
            "description": self.description,
            "author": self.author,
            "labels": list(self.labels),
            "base_branch": self.base_branch,
        }


@dataclass(frozen=True, slots=True)
class ReviewContextResult:
    """Gathered context for code review."""

    pr_metadata: PRMetadata
    changed_files: tuple[str, ...]
    diff: str
    commits: tuple[str, ...]
    spec_files: dict[str, str]  # Spec file contents keyed by filename
    error: str | None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "pr_metadata": self.pr_metadata.to_dict(),
            "changed_files": list(self.changed_files),
            "diff": self.diff,
            "commits": list(self.commits),
            "spec_files": self.spec_files,
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class CombinedReviewResult:
    """Combined review results from all sources."""

    review_report: str
    issues: tuple[dict[str, Any], ...]
    recommendation: str  # "approve", "request_changes", "comment"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "review_report": self.review_report,
            "issues": list(self.issues),
            "recommendation": self.recommendation,
        }


@dataclass(frozen=True, slots=True)
class ReviewIssue:
    """Individual issue identified in code review."""

    id: str  # Unique ID for tracking
    file_path: str | None  # File path affected (None if general issue)
    line_number: int | None  # Line number if applicable
    severity: str  # "critical", "major", "minor", "suggestion"
    category: str  # "security", "correctness", "performance", "maintainability"
    # (continued): "spec_compliance", "style", "other"
    description: str
    suggested_fix: str | None
    reviewer: str  # "spec" or "technical"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "id": self.id,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "severity": self.severity,
            "category": self.category,
            "description": self.description,
            "suggested_fix": self.suggested_fix,
            "reviewer": self.reviewer,
        }


@dataclass(frozen=True, slots=True)
class IssueGroup:
    """Group of issues that can be addressed together.

    Issues affecting different files can be fixed in parallel.
    Issues affecting the same file are grouped for sequential processing.
    """

    group_id: str
    file_path: str | None  # File path for file-specific groups, None for general
    issues: tuple[ReviewIssue, ...]
    can_parallelize: bool  # True if this group can run in parallel with others

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "group_id": self.group_id,
            "file_path": self.file_path,
            "issues": [issue.to_dict() for issue in self.issues],
            "can_parallelize": self.can_parallelize,
        }


@dataclass(frozen=True, slots=True)
class AnalyzedFindingsResult:
    """Result of analyzing review findings for fix prioritization."""

    total_issues: int
    critical_count: int
    major_count: int
    minor_count: int
    suggestion_count: int
    issue_groups: tuple[IssueGroup, ...]
    needs_fixes: bool  # True if there are issues that should be fixed
    skip_reason: str | None  # Reason to skip fixing (e.g., already approved)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "total_issues": self.total_issues,
            "critical_count": self.critical_count,
            "major_count": self.major_count,
            "minor_count": self.minor_count,
            "suggestion_count": self.suggestion_count,
            "issue_groups": [group.to_dict() for group in self.issue_groups],
            "needs_fixes": self.needs_fixes,
            "skip_reason": self.skip_reason,
        }


@dataclass(frozen=True, slots=True)
class IssueFixResult:
    """Result of attempting to fix a single issue."""

    issue_id: str
    fixed: bool
    fix_description: str | None
    error: str | None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "issue_id": self.issue_id,
            "fixed": self.fixed,
            "fix_description": self.fix_description,
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class ReviewFixLoopResult:
    """Result of the review fix loop."""

    success: bool  # True if all issues resolved or review passed
    attempts: int
    issues_fixed: tuple[IssueFixResult, ...]
    issues_remaining: tuple[ReviewIssue, ...]
    final_recommendation: str  # Final review recommendation after fixes
    skipped: bool  # True if fix loop was skipped
    skip_reason: str | None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "success": self.success,
            "attempts": self.attempts,
            "issues_fixed": [fix.to_dict() for fix in self.issues_fixed],
            "issues_remaining": [issue.to_dict() for issue in self.issues_remaining],
            "final_recommendation": self.final_recommendation,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
        }


@dataclass(frozen=True, slots=True)
class ReviewAndFixReport:
    """Final report from review-and-fix workflow."""

    review_report: str
    recommendation: str  # "approve", "request_changes", "comment"
    issues_found: int
    issues_fixed: int
    issues_remaining: int
    attempts: int
    fix_summary: tuple[str, ...]  # Summary of fixes applied

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "review_report": self.review_report,
            "recommendation": self.recommendation,
            "issues_found": self.issues_found,
            "issues_fixed": self.issues_fixed,
            "issues_remaining": self.issues_remaining,
            "attempts": self.attempts,
            "fix_summary": list(self.fix_summary),
        }


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

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "issue_number": self.issue_number,
            "issue_title": self.issue_title,
            "status": self.status,
            "branch_name": self.branch_name,
            "pr_url": self.pr_url,
            "error": self.error,
        }


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

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "total_issues": self.total_issues,
            "processed_count": self.processed_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "skipped_count": self.skipped_count,
            "issues": [issue.to_dict() for issue in self.issues],
            "pr_urls": list(self.pr_urls),
        }


# =============================================================================
# Tech Debt Types
# =============================================================================


# =============================================================================
# Bead Types
# =============================================================================


@dataclass(frozen=True, slots=True)
class SpecKitParseResult:
    """Result of parsing a SpecKit specification directory.

    Attributes:
        epic_definition: Serialized BeadDefinition for the epic.
        work_definitions: Serialized BeadDefinitions for work beads.
        tasks_content: Raw tasks.md content for dependency extraction.
        dependency_section: Extracted "User Story Dependencies" text block.
    """

    epic_definition: dict[str, Any]
    work_definitions: tuple[dict[str, Any], ...]
    tasks_content: str
    dependency_section: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "epic_definition": self.epic_definition,
            "work_definitions": list(self.work_definitions),
            "tasks_content": self.tasks_content,
            "dependency_section": self.dependency_section,
        }


@dataclass(frozen=True, slots=True)
class BeadCreationResult:
    """Result of creating epic and work beads via bd CLI.

    Attributes:
        epic: Serialized CreatedBead for the epic (None if creation failed).
        work_beads: Serialized CreatedBeads for work beads.
        created_map: Mapping from bead title to bd_id.
        errors: Errors encountered during creation.
    """

    epic: dict[str, Any] | None
    work_beads: tuple[dict[str, Any], ...]
    created_map: dict[str, str]
    errors: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "epic": self.epic,
            "work_beads": list(self.work_beads),
            "created_map": dict(self.created_map),
            "errors": list(self.errors),
        }


@dataclass(frozen=True, slots=True)
class DependencyWiringResult:
    """Result of computing and wiring dependencies between beads.

    Attributes:
        dependencies: Serialized BeadDependency objects that were wired.
        errors: Errors encountered during wiring.
        success: Whether all dependencies were wired successfully.
    """

    dependencies: tuple[dict[str, Any], ...]
    errors: tuple[str, ...]
    success: bool

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "dependencies": list(self.dependencies),
            "errors": list(self.errors),
            "success": self.success,
        }


@dataclass(frozen=True, slots=True)
class TechDebtIssueResult:
    """Result of creating a tech debt issue.

    Used to track the outcome of creating GitHub issues for findings
    that cannot be fixed in the current PR (blocked, deferred, minor).

    Attributes:
        success: Whether the issue was created successfully.
        issue_number: GitHub issue number if created.
        issue_url: URL to the GitHub issue if created.
        title: Title of the issue.
        labels: Labels applied to the issue.
        finding_id: ID of the finding this issue is for.
        error: Error message if creation failed.
    """

    success: bool
    issue_number: int | None
    issue_url: str | None
    title: str
    labels: tuple[str, ...]
    finding_id: str
    error: str | None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "success": self.success,
            "issue_number": self.issue_number,
            "issue_url": self.issue_url,
            "title": self.title,
            "labels": list(self.labels),
            "finding_id": self.finding_id,
            "error": self.error,
        }
