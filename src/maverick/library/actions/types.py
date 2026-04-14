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
class ReviewMetadata:
    """Metadata about the changes being reviewed."""

    base_branch: str
    title: str | None = None
    description: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "base_branch": self.base_branch,
            "title": self.title,
            "description": self.description,
        }


@dataclass(frozen=True, slots=True)
class ReviewContextResult:
    """Gathered context for code review."""

    review_metadata: ReviewMetadata
    changed_files: tuple[str, ...]
    diff: str
    commits: tuple[str, ...]
    spec_files: dict[str, str]  # Spec file contents keyed by filename
    error: str | None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "review_metadata": self.review_metadata.to_dict(),
            "changed_files": list(self.changed_files),
            "diff": self.diff,
            "commits": list(self.commits),
            "spec_files": self.spec_files,
            "error": self.error,
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
    review_findings: tuple[dict[str, Any], ...] = ()  # Structured Finding dicts from reviewers
    fixed_count: int = 0  # Count of findings addressed by the fixer agent

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
            "review_findings": list(self.review_findings),
            "fixed_count": self.fixed_count,
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
    review_findings: tuple[dict[str, Any], ...] = ()  # Structured Finding dicts

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
            "review_findings": list(self.review_findings),
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
# Runway Types
# =============================================================================


@dataclass(frozen=True, slots=True)
class RunwayRetrievalResult:
    """Result of retrieving runway context for prompt injection.

    Attributes:
        success: Whether the retrieval completed without error.
        context_text: Formatted markdown ready for prompt injection.
        passages_used: Number of BM25 passages included.
        outcomes_used: Number of structured outcomes included.
        error: Error message if retrieval failed.
    """

    success: bool
    context_text: str
    passages_used: int
    outcomes_used: int
    error: str | None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "success": self.success,
            "context_text": self.context_text,
            "passages_used": self.passages_used,
            "outcomes_used": self.outcomes_used,
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class RunwayConsolidationResult:
    """Result of consolidating runway episodic records.

    Attributes:
        success: Whether consolidation completed successfully.
        records_pruned: Number of episodic records removed.
        summary_updated: Whether consolidated-insights.md was updated.
        skipped: Whether consolidation was skipped (below thresholds).
        skip_reason: Reason for skipping, if applicable.
        error: Error message if consolidation failed.
    """

    success: bool
    records_pruned: int
    summary_updated: bool
    skipped: bool
    skip_reason: str | None
    error: str | None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "success": self.success,
            "records_pruned": self.records_pruned,
            "summary_updated": self.summary_updated,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class RecordBeadOutcomeResult:
    """Result of recording a bead outcome to the runway store.

    Attributes:
        success: Whether the record was written successfully.
        bead_id: ID of the bead recorded.
        error: Error message if recording failed.
    """

    success: bool
    bead_id: str
    error: str | None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "success": self.success,
            "bead_id": self.bead_id,
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class RecordReviewFindingsResult:
    """Result of recording review findings to the runway store.

    Attributes:
        success: Whether the records were written successfully.
        findings_recorded: Number of findings written.
        error: Error message if recording failed.
    """

    success: bool
    findings_recorded: int
    error: str | None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "success": self.success,
            "findings_recorded": self.findings_recorded,
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class RecordFixAttemptResult:
    """Result of recording a fix attempt to the runway store.

    Attributes:
        success: Whether the record was written successfully.
        attempt_id: ID of the attempt recorded.
        error: Error message if recording failed.
    """

    success: bool
    attempt_id: str
    error: str | None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "success": self.success,
            "attempt_id": self.attempt_id,
            "error": self.error,
        }


# =============================================================================
# Tech Debt Types
# =============================================================================


# =============================================================================
# Bead Types
# =============================================================================


@dataclass(frozen=True, slots=True)
class SelectNextBeadResult:
    """Result of selecting the next ready bead from an epic.

    Attributes:
        found: Whether a ready bead was found.
        bead_id: ID of the selected bead (empty if not found).
        title: Title of the selected bead.
        description: Description of the selected bead.
        priority: Priority of the selected bead.
        epic_id: Parent epic ID of the selected bead.
        done: Whether the epic has no more ready beads.
        flight_plan_name: Name of the originating flight plan (from epic state).
    """

    found: bool
    bead_id: str
    title: str
    description: str
    priority: int
    epic_id: str
    done: bool
    flight_plan_name: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "found": self.found,
            "bead_id": self.bead_id,
            "title": self.title,
            "description": self.description,
            "priority": self.priority,
            "epic_id": self.epic_id,
            "done": self.done,
            "flight_plan_name": self.flight_plan_name,
        }


@dataclass(frozen=True, slots=True)
class MarkBeadCompleteResult:
    """Result of closing/completing a bead.

    Attributes:
        success: Whether the bead was closed successfully.
        bead_id: ID of the bead that was closed.
        error: Error message if closing failed.
    """

    success: bool
    bead_id: str
    error: str | None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "success": self.success,
            "bead_id": self.bead_id,
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class CreateBeadsFromFailuresResult:
    """Result of creating fix beads from validation failures.

    Attributes:
        created_count: Number of beads created.
        bead_ids: IDs of created beads.
        errors: Errors encountered during creation.
    """

    created_count: int
    bead_ids: tuple[str, ...]
    errors: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "created_count": self.created_count,
            "bead_ids": list(self.bead_ids),
            "errors": list(self.errors),
        }


@dataclass(frozen=True, slots=True)
class CreateBeadsFromFindingsResult:
    """Result of creating fix beads from review findings.

    Attributes:
        created_count: Number of beads created.
        bead_ids: IDs of created beads.
        errors: Errors encountered during creation.
    """

    created_count: int
    bead_ids: tuple[str, ...]
    errors: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "created_count": self.created_count,
            "bead_ids": list(self.bead_ids),
            "errors": list(self.errors),
        }


@dataclass(frozen=True, slots=True)
class CheckEpicDoneResult:
    """Result of checking whether an epic has remaining work.

    Attributes:
        done: Whether the epic has no more ready beads.
        remaining_count: Number of remaining ready beads.
        all_children_closed: Whether every child bead has status "closed".
            True means the epic can safely be closed. False when some
            children are still open or blocked (even if none are ready).
        total_children: Total number of child beads under the epic.
        closed_children: Number of child beads with status "closed".
    """

    done: bool
    remaining_count: int
    all_children_closed: bool = False
    total_children: int = 0
    closed_children: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "done": self.done,
            "remaining_count": self.remaining_count,
            "all_children_closed": self.all_children_closed,
            "total_children": self.total_children,
            "closed_children": self.closed_children,
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
class VerifyBeadCompletionResult:
    """Result of verifying bead completion before commit/close.

    Attributes:
        passed: Whether the bead is ready to commit and close.
        reasons: Reasons for failure (empty if passed).
    """

    passed: bool
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {"passed": self.passed, "reasons": list(self.reasons)}


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
