"""Refuel Workflow interface module.

This module defines the interface and data models for the Refuel Workflow, which
orchestrates tech-debt resolution by discovering GitHub issues by label, processing
them using IssueFixerAgent, and creating PRs.

Note: Full implementation is deferred to Spec 26 (026-refuel-workflow-implementation).
This module provides the interface contracts and data structures.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from maverick.agents.result import AgentUsage

__all__ = [
    # Data structures
    "GitHubIssue",
    "IssueStatus",
    "RefuelInputs",
    "IssueProcessingResult",
    "RefuelResult",
    # Configuration
    "RefuelConfig",
    # Progress Events
    "RefuelStarted",
    "IssueProcessingStarted",
    "IssueProcessingCompleted",
    "RefuelCompleted",
    "RefuelProgressEvent",
    # Workflow
    "RefuelWorkflow",
]


@dataclass(frozen=True, slots=True)
class GitHubIssue:
    """Minimal representation of a GitHub issue for refuel workflow.

    Attributes:
        number: Issue number (e.g., 123).
        title: Issue title.
        body: Issue body/description (optional).
        labels: List of label names.
        assignee: Assigned username (optional).
        url: Full GitHub issue URL.
    """

    number: int
    title: str
    body: str | None
    labels: list[str]
    assignee: str | None
    url: str


class IssueStatus(str, Enum):
    """Enum representing issue processing lifecycle.

    Values:
        PENDING: Issue identified, not yet processed.
        IN_PROGRESS: Currently being processed by agent.
        FIXED: Successfully fixed, PR created.
        FAILED: Processing failed (with error details).
        SKIPPED: Skipped due to policy (dry_run, assigned, etc.).
    """

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    FIXED = "fixed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class RefuelInputs:
    """Configuration for a single workflow execution.

    Attributes:
        label: Label filter for discovering issues.
        limit: Maximum issues to process.
        parallel: Enable parallel processing.
        dry_run: Preview mode (no changes).
        auto_assign: Auto-assign issues to self.
    """

    label: str = "tech-debt"
    limit: int = 5
    parallel: bool = True
    dry_run: bool = False
    auto_assign: bool = True


@dataclass(frozen=True, slots=True)
class IssueProcessingResult:
    """Outcome of processing a single issue.

    Attributes:
        issue: The processed issue.
        status: Processing outcome.
        branch: Created branch name (if any).
        pr_url: Created PR URL (if any).
        error: Error message (if FAILED).
        duration_ms: Processing duration in milliseconds.
        agent_usage: Token/cost metrics.

    Invariants:
        - If status == FIXED: branch and pr_url must be non-None.
        - If status == FAILED: error must be non-None.
        - If status == SKIPPED: branch, pr_url, error should be None.
    """

    issue: GitHubIssue
    status: IssueStatus
    branch: str | None
    pr_url: str | None
    error: str | None
    duration_ms: int
    agent_usage: AgentUsage


@dataclass(frozen=True, slots=True)
class RefuelResult:
    """Aggregate outcome of workflow execution.

    Attributes:
        success: Overall workflow success.
        issues_found: Total issues matching label.
        issues_processed: Issues actually processed.
        issues_fixed: Issues successfully fixed.
        issues_failed: Issues that failed.
        issues_skipped: Issues skipped.
        results: Per-issue outcomes.
        total_duration_ms: Total execution time in milliseconds.
        total_cost_usd: Total API cost in USD.

    Invariants:
        - issues_processed == issues_fixed + issues_failed (excludes skipped issues)
        - issues_found reflects total matching issues (before skip filtering)
        - len(results) == issues_found (after limit applied)
        - success == True if issues_failed == 0 and no exceptions occurred
    """

    success: bool
    issues_found: int
    issues_processed: int
    issues_fixed: int
    issues_failed: int
    issues_skipped: int
    results: list[IssueProcessingResult]
    total_duration_ms: int
    total_cost_usd: float


class RefuelConfig(BaseModel):
    """Persistent configuration for refuel workflow.

    Attributes:
        default_label: Default label filter.
        branch_prefix: Branch naming prefix (must end with "/" or "-").
        link_pr_to_issue: Add "Fixes #N" to PR.
        close_on_merge: Close issue when PR merges.
        skip_if_assigned: Skip already-assigned issues.
        max_parallel: Max concurrent issue processing (1-10).
    """

    model_config = ConfigDict(frozen=True)

    default_label: str = Field(default="tech-debt", description="Default label filter")
    branch_prefix: str = Field(default="fix/issue-", description="Branch naming prefix")
    link_pr_to_issue: bool = Field(default=True, description="Add 'Fixes #N' to PR")
    close_on_merge: bool = Field(
        default=False, description="Close issue when PR merges"
    )
    skip_if_assigned: bool = Field(
        default=True, description="Skip already-assigned issues"
    )
    max_parallel: int = Field(
        default=3, ge=1, le=10, description="Max concurrent issue processing"
    )

    @field_validator("branch_prefix")
    @classmethod
    def validate_branch_prefix(cls, v: str) -> str:
        """Ensure branch_prefix ends with '/' or '-'."""
        if not v.endswith(("/", "-")):
            raise ValueError("branch_prefix must end with '/' or '-'")
        return v


# Progress Events


@dataclass(frozen=True, slots=True)
class RefuelStarted:
    """Event emitted when refuel workflow starts.

    Attributes:
        inputs: Workflow input configuration.
        issues_found: Number of matching issues.
    """

    inputs: RefuelInputs
    issues_found: int


@dataclass(frozen=True, slots=True)
class IssueProcessingStarted:
    """Event emitted when issue processing begins.

    Attributes:
        issue: Issue being processed.
        index: Current index (1-based) of this issue in the processing queue.
        total: Total issues to process.
    """

    issue: GitHubIssue
    index: int
    total: int


@dataclass(frozen=True, slots=True)
class IssueProcessingCompleted:
    """Event emitted when issue processing completes.

    Attributes:
        result: Processing outcome.
    """

    result: IssueProcessingResult


@dataclass(frozen=True, slots=True)
class RefuelCompleted:
    """Event emitted when refuel workflow completes.

    Attributes:
        result: Aggregate workflow result.
    """

    result: RefuelResult


# Union type for event handling
RefuelProgressEvent = (
    RefuelStarted | IssueProcessingStarted | IssueProcessingCompleted | RefuelCompleted
)


class RefuelWorkflow:
    """Refuel workflow orchestrator.

    Orchestrates tech-debt resolution workflow:
    1. Discover issues by label from GitHub
    2. Filter by limit and skip_if_assigned policy
    3. Per-issue processing flow (implementation in Spec 26):
       a. Create branch using branch_prefix + issue number
       b. Run IssueFixerAgent to analyze and fix the issue
       c. Run ValidationWorkflow (format, lint, test)
       d. Commit changes with conventional message referencing issue
       e. Push branch and create PR linking to issue
       f. Optionally close issue on PR merge (if close_on_merge=True)
    4. Aggregate results and emit RefuelCompleted

    Note: Full implementation in Spec 26 using workflow DSL.
    """

    def __init__(self, config: RefuelConfig | None = None) -> None:
        """Initialize the refuel workflow.

        Args:
            config: Optional workflow configuration. Uses defaults if None.
        """
        self._config = config or RefuelConfig()

    async def execute(
        self, inputs: RefuelInputs
    ) -> AsyncGenerator[RefuelProgressEvent, None]:
        """Execute the refuel workflow.

        Per-issue processing flow (implementation in Spec 26):
            1. Create branch using branch_prefix + issue number
            2. Run IssueFixerAgent to analyze and fix the issue
            3. Run ValidationWorkflow (format, lint, test)
            4. Commit changes with conventional message referencing issue
            5. Push branch and create PR linking to issue
            6. Optionally close issue on PR merge (if close_on_merge=True)

        Args:
            inputs: Workflow inputs (label, limit, parallel, etc.)

        Yields:
            Progress events (RefuelStarted, IssueProcessing*, RefuelCompleted)

        Raises:
            NotImplementedError: Always - implementation in Spec 26.
        """
        raise NotImplementedError(
            "RefuelWorkflow.execute() is not implemented. "
            "Full implementation will be provided in Spec 26 using the workflow DSL."
        )
        # Yield statement for async generator type hint (never reached after raise)
        yield RefuelStarted(inputs=inputs, issues_found=0)  # pragma: no cover
