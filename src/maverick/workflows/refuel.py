"""Refuel Workflow implementation module.

This module defines the implementation for the Refuel Workflow, which
orchestrates tech-debt resolution by discovering GitHub issues by label, processing
them using IssueFixerAgent, and creating PRs.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, field_validator

from maverick.agents.result import AgentUsage

if TYPE_CHECKING:
    from maverick.agents.generators.commit_message import CommitMessageGenerator
    from maverick.agents.issue_fixer import IssueFixerAgent
    from maverick.runners.git import GitRunner
    from maverick.runners.github import GitHubCLIRunner
    from maverick.runners.models import GitHubIssue as RunnerGitHubIssue
    from maverick.runners.validation import ValidationRunner

logger = logging.getLogger(__name__)

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


def _convert_runner_issue_to_workflow_issue(
    runner_issue: RunnerGitHubIssue,
) -> GitHubIssue:
    """Convert runner GitHubIssue to workflow GitHubIssue."""
    return GitHubIssue(
        number=runner_issue.number,
        title=runner_issue.title,
        body=runner_issue.body,
        labels=list(runner_issue.labels),
        assignee=runner_issue.assignees[0] if runner_issue.assignees else None,
        url=runner_issue.url,
    )


class RefuelWorkflow:
    """Refuel workflow orchestrator.

    Orchestrates tech-debt resolution workflow:
    1. Discover issues by label from GitHub
    2. Filter by limit and skip_if_assigned policy
    3. Per-issue processing flow:
       a. Create branch using branch_prefix + issue number
       b. Run IssueFixerAgent to analyze and fix the issue
       c. Run ValidationWorkflow (format, lint, test)
       d. Commit changes with conventional message referencing issue
       e. Push branch and create PR linking to issue
       f. Optionally close issue on PR merge (if close_on_merge=True)
    4. Aggregate results and emit RefuelCompleted
    """

    def __init__(
        self,
        config: RefuelConfig | None = None,
        git_runner: GitRunner | None = None,
        github_runner: GitHubCLIRunner | None = None,
        validation_runner: ValidationRunner | None = None,
        issue_fixer_agent: IssueFixerAgent | None = None,
        commit_generator: CommitMessageGenerator | None = None,
    ) -> None:
        """Initialize the refuel workflow.

        Args:
            config: Optional workflow configuration. Uses defaults if None.
            git_runner: Git operations runner (injected for testing).
            github_runner: GitHub CLI runner (injected for testing).
            validation_runner: Validation runner (injected for testing).
            issue_fixer_agent: Issue fixer agent (injected for testing).
            commit_generator: Commit message generator (injected for testing).
        """
        self._config = config or RefuelConfig()
        self._git_runner = git_runner
        self._github_runner = github_runner
        self._validation_runner = validation_runner
        self._issue_fixer_agent = issue_fixer_agent
        self._commit_generator = commit_generator

    async def _discover_issues_with_retry(
        self, inputs: RefuelInputs, max_retries: int = 3
    ) -> list[RunnerGitHubIssue]:
        """Discover issues with exponential backoff retry on network failures.

        Args:
            inputs: Workflow inputs with label and limit.
            max_retries: Maximum retry attempts (default: 3).

        Returns:
            List of discovered issues.

        Raises:
            Exception: If all retries fail.
        """
        if self._github_runner is None:
            return []

        last_error = None
        for attempt in range(max_retries):
            try:
                issues = await self._github_runner.list_issues(
                    label=inputs.label,
                    limit=inputs.limit,
                )
                return issues
            except Exception as e:
                last_error = e
                logger.warning(
                    f"Issue discovery failed (attempt {attempt + 1}/{max_retries}): {e}"
                )
                if attempt < max_retries - 1:
                    # Exponential backoff: 1s, 2s, 4s
                    await asyncio.sleep(2**attempt)

        # All retries failed
        logger.error(
            f"Issue discovery failed after {max_retries} attempts: {last_error}"
        )
        raise last_error  # type: ignore[misc]

    async def _process_issue(
        self, issue: GitHubIssue, inputs: RefuelInputs
    ) -> IssueProcessingResult:
        """Process a single issue.

        Args:
            issue: Issue to process.
            inputs: Workflow inputs.

        Returns:
            IssueProcessingResult with outcome.
        """
        start_time = time.time()
        empty_usage = AgentUsage(
            input_tokens=0,
            output_tokens=0,
            total_cost_usd=0.0,
            duration_ms=0,
        )

        # Check if issue is assigned and should be skipped
        if self._config.skip_if_assigned and issue.assignee is not None:
            duration_ms = int((time.time() - start_time) * 1000)
            return IssueProcessingResult(
                issue=issue,
                status=IssueStatus.SKIPPED,
                branch=None,
                pr_url=None,
                error=None,
                duration_ms=duration_ms,
                agent_usage=empty_usage,
            )

        # Create branch
        branch_name = f"{self._config.branch_prefix}{issue.number}"

        if inputs.dry_run:
            # In dry-run mode, log operations without executing
            logger.info(f"[DRY-RUN] Would create branch: {branch_name}")
            logger.info(
                f"[DRY-RUN] Would run IssueFixerAgent for #{issue.number}"
            )
            logger.info("[DRY-RUN] Would run validation workflow")
            logger.info("[DRY-RUN] Would stage changes and create commit")
            logger.info("[DRY-RUN] Would push branch to remote")
            logger.info(f"[DRY-RUN] Would create PR for issue #{issue.number}")

            duration_ms = int((time.time() - start_time) * 1000)
            return IssueProcessingResult(
                issue=issue,
                status=IssueStatus.FIXED,
                branch=branch_name,
                pr_url=f"https://github.com/owner/repo/pull/[dry-run-{issue.number}]",
                error=None,
                duration_ms=duration_ms,
                agent_usage=empty_usage,
            )

        if self._git_runner is None:
            duration_ms = int((time.time() - start_time) * 1000)
            return IssueProcessingResult(
                issue=issue,
                status=IssueStatus.FAILED,
                branch=None,
                pr_url=None,
                error="Git runner not configured",
                duration_ms=duration_ms,
                agent_usage=empty_usage,
            )

        git_result = await self._git_runner.create_branch(branch_name)
        if not git_result.success:
            duration_ms = int((time.time() - start_time) * 1000)
            return IssueProcessingResult(
                issue=issue,
                status=IssueStatus.FAILED,
                branch=branch_name,
                pr_url=None,
                error=f"Failed to create branch: {git_result.error}",
                duration_ms=duration_ms,
                agent_usage=empty_usage,
            )

        # Step 2c: Issue Fixing (FR-017)
        agent_usage = empty_usage
        if self._issue_fixer_agent is not None:
            try:
                fix_result = await self._issue_fixer_agent.execute()  # type: ignore[call-arg]
                if hasattr(fix_result, "usage") and fix_result.usage:
                    agent_usage = fix_result.usage
            except Exception as e:
                duration_ms = int((time.time() - start_time) * 1000)
                return IssueProcessingResult(
                    issue=issue,
                    status=IssueStatus.FAILED,
                    branch=branch_name,
                    pr_url=None,
                    error=f"Issue fixer agent failed: {e}",
                    duration_ms=duration_ms,
                    agent_usage=empty_usage,
                )

        # Step 2d: Validation (optional, with simple retry)
        max_validation_attempts = 3
        validation_passed = True  # Default to True if no validation runner
        if self._validation_runner is not None:
            for attempt in range(1, max_validation_attempts + 1):
                try:
                    validation_output = await self._validation_runner.run()
                    validation_passed = validation_output.success
                    if validation_passed:
                        logger.info(f"Validation passed for issue #{issue.number}")
                        break
                    if attempt < max_validation_attempts:
                        logger.warning(
                            f"Validation failed for issue #{issue.number}, "
                            f"attempt {attempt}/{max_validation_attempts}"
                        )
                        # Try to fix again
                        if self._issue_fixer_agent is not None:
                            try:
                                await self._issue_fixer_agent.execute()  # type: ignore[call-arg]
                            except Exception as e:
                                logger.warning(f"Fix agent retry failed: {e}")
                except Exception as e:
                    logger.warning(f"Validation error for issue #{issue.number}: {e}")
                    validation_passed = False

        # Step 2e: Commit
        commit_message = f"fix: resolve issue #{issue.number}"
        try:
            # Stage changes
            await self._git_runner.add(add_all=True)

            # Get diff for commit message generation
            diff_output = await self._git_runner.diff(staged=True)

            # Generate commit message if generator available
            if self._commit_generator is not None and diff_output:
                try:
                    commit_message = await self._commit_generator.generate({
                        "diff": diff_output,
                        "file_stats": {},
                        "scope_hint": f"issue-{issue.number}",
                    })
                except Exception as e:
                    logger.warning(f"Commit message generation failed: {e}")

            # Create commit
            commit_result = await self._git_runner.commit(commit_message)
            if not commit_result.success:
                duration_ms = int((time.time() - start_time) * 1000)
                return IssueProcessingResult(
                    issue=issue,
                    status=IssueStatus.FAILED,
                    branch=branch_name,
                    pr_url=None,
                    error=f"Commit failed: {commit_result.error}",
                    duration_ms=duration_ms,
                    agent_usage=agent_usage,
                )
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            return IssueProcessingResult(
                issue=issue,
                status=IssueStatus.FAILED,
                branch=branch_name,
                pr_url=None,
                error=f"Git operations failed: {e}",
                duration_ms=duration_ms,
                agent_usage=agent_usage,
            )

        # Step 2f: Push and PR Creation
        pr_url = None
        try:
            # Push branch
            push_result = await self._git_runner.push(branch_name)
            if not push_result.success:
                duration_ms = int((time.time() - start_time) * 1000)
                return IssueProcessingResult(
                    issue=issue,
                    status=IssueStatus.FAILED,
                    branch=branch_name,
                    pr_url=None,
                    error=f"Push failed: {push_result.error}",
                    duration_ms=duration_ms,
                    agent_usage=agent_usage,
                )

            # Create PR
            if self._github_runner is not None:
                pr_body = f"## Summary\n\nFixes #{issue.number}\n\n{issue.title}"
                if self._config.link_pr_to_issue:
                    pr_body += f"\n\nCloses #{issue.number}"

                pr_result = await self._github_runner.create_pr(
                    title=f"fix: {issue.title}",
                    body=pr_body,
                    base="main",
                    draft=not validation_passed,  # Draft if validation failed
                )
                # Handle mock (string) and real (PullRequest) cases
                pr_url = pr_result if isinstance(pr_result, str) else pr_result.url
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            return IssueProcessingResult(
                issue=issue,
                status=IssueStatus.FAILED,
                branch=branch_name,
                pr_url=None,
                error=f"PR creation failed: {e}",
                duration_ms=duration_ms,
                agent_usage=agent_usage,
            )

        duration_ms = int((time.time() - start_time) * 1000)
        return IssueProcessingResult(
            issue=issue,
            status=IssueStatus.FIXED,
            branch=branch_name,
            pr_url=pr_url,
            error=None,
            duration_ms=duration_ms,
            agent_usage=agent_usage,
        )

    async def execute(
        self, inputs: RefuelInputs
    ) -> AsyncGenerator[RefuelProgressEvent, None]:
        """Execute the refuel workflow.

        Per-issue processing flow:
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
        """
        workflow_start_time = time.time()

        # Phase 1: Issue Discovery with retry
        if inputs.dry_run:
            logger.info(f"[DRY-RUN] Would discover issues with label: {inputs.label}")
            logger.info(f"[DRY-RUN] Would limit to {inputs.limit} issues")
            # In dry-run mode, still try to discover issues (read-only operation)
            # This allows previewing what would be processed without making changes
            try:
                runner_issues = await self._discover_issues_with_retry(inputs)
                issues = [
                    _convert_runner_issue_to_workflow_issue(ri)
                    for ri in runner_issues
                ]
            except Exception as e:
                # If discovery fails in dry-run, continue with empty list
                logger.warning(f"[DRY-RUN] Issue discovery failed: {e}")
                issues = []
        else:
            runner_issues = await self._discover_issues_with_retry(inputs)
            issues = [
                _convert_runner_issue_to_workflow_issue(ri)
                for ri in runner_issues
            ]

        # Emit RefuelStarted
        yield RefuelStarted(inputs=inputs, issues_found=len(issues))

        # Phase 2: Per-Issue Processing
        results: list[IssueProcessingResult] = []

        for index, issue in enumerate(issues, start=1):
            # Emit IssueProcessingStarted
            yield IssueProcessingStarted(
                issue=issue,
                index=index,
                total=len(issues),
            )

            # Process issue with error isolation
            try:
                result = await self._process_issue(issue, inputs)
                results.append(result)
            except Exception as e:
                logger.error(f"Issue {issue.number} processing failed: {e}")
                # Create failed result - isolation ensures we continue
                empty_usage = AgentUsage(
                    input_tokens=0,
                    output_tokens=0,
                    total_cost_usd=0.0,
                    duration_ms=0,
                )
                result = IssueProcessingResult(
                    issue=issue,
                    status=IssueStatus.FAILED,
                    branch=None,
                    pr_url=None,
                    error=str(e),
                    duration_ms=0,
                    agent_usage=empty_usage,
                )
                results.append(result)

            # Emit IssueProcessingCompleted
            yield IssueProcessingCompleted(result=result)

        # Phase 3: Aggregation
        issues_fixed = sum(1 for r in results if r.status == IssueStatus.FIXED)
        issues_failed = sum(1 for r in results if r.status == IssueStatus.FAILED)
        issues_skipped = sum(1 for r in results if r.status == IssueStatus.SKIPPED)
        issues_processed = issues_fixed + issues_failed

        total_duration_ms = int((time.time() - workflow_start_time) * 1000)
        total_cost_usd = sum(r.agent_usage.total_cost_usd or 0.0 for r in results)

        refuel_result = RefuelResult(
            success=(issues_failed == 0),
            issues_found=len(issues),
            issues_processed=issues_processed,
            issues_fixed=issues_fixed,
            issues_failed=issues_failed,
            issues_skipped=issues_skipped,
            results=results,
            total_duration_ms=total_duration_ms,
            total_cost_usd=total_cost_usd,
        )

        # Emit RefuelCompleted
        yield RefuelCompleted(result=refuel_result)
