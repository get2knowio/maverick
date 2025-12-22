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
from maverick.dsl.events import (
    ProgressEvent,
)
from maverick.dsl.events import (
    StepCompleted as DslStepCompleted,
)
from maverick.dsl.events import (
    StepStarted as DslStepStarted,
)
from maverick.dsl.events import (
    WorkflowCompleted as DslWorkflowCompleted,
)
from maverick.dsl.events import (
    WorkflowStarted as DslWorkflowStarted,
)
from maverick.dsl.results import WorkflowResult
from maverick.dsl.serialization.executor import WorkflowFileExecutor
from maverick.dsl.serialization.registry import ComponentRegistry
from maverick.workflows.base import WorkflowDSLMixin

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
    "RefuelStepName",
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


class RefuelStepName(str, Enum):
    """DSL step names used in refuel workflow.

    These constants map to step names in refuel.yaml and are used
    for translating DSL events to RefuelProgressEvent types.

    Values:
        FETCH_ISSUES: Fetch issues from GitHub by label.
        PROCESS_ISSUE: Process a single issue (branch, fix, validate, commit, PR).
    """

    FETCH_ISSUES = "fetch_issues"
    PROCESS_ISSUE = "process_issue"


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


class RefuelWorkflow(WorkflowDSLMixin):
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
        registry: ComponentRegistry | None = None,
        git_runner: GitRunner | None = None,
        github_runner: GitHubCLIRunner | None = None,
        validation_runner: ValidationRunner | None = None,
        issue_fixer_agent: IssueFixerAgent | None = None,
        commit_generator: CommitMessageGenerator | None = None,
    ) -> None:
        """Initialize the refuel workflow.

        Args:
            config: Optional workflow configuration. Uses defaults if None.
            registry: Component registry for DSL execution.
            git_runner: Git operations runner (injected for testing).
            github_runner: GitHub CLI runner (injected for testing).
            validation_runner: Validation runner (injected for testing).
            issue_fixer_agent: Issue fixer agent (injected for testing).
            commit_generator: Commit message generator (injected for testing).
        """
        # Initialize the mixin first
        super().__init__()

        self._config = config or RefuelConfig()
        self._registry = registry or ComponentRegistry()
        self._git_runner = git_runner
        self._github_runner = github_runner
        self._validation_runner = validation_runner
        self._issue_fixer_agent = issue_fixer_agent
        self._commit_generator = commit_generator

        # DSL executor
        self._executor: WorkflowFileExecutor | None = None

    def _translate_event(self, event: ProgressEvent) -> RefuelProgressEvent | None:
        """Translate DSL progress events to RefuelProgressEvent types.

        Maps DSL events to corresponding Refuel workflow events based on step metadata
        and event types. Returns None for events that don't map to Refuel events.

        Note:
            When mapping step events in the future, use RefuelStepName constants
            instead of string literals. Example:
                if event.step_name == RefuelStepName.FETCH_ISSUES.value:
                    # Handle fetch_issues step
                elif event.step_name == RefuelStepName.PROCESS_ISSUE.value:
                    # Handle process_issue step

        Args:
            event: DSL ProgressEvent from WorkflowFileExecutor.

        Returns:
            Corresponding RefuelProgressEvent, or None if no mapping exists.
        """
        # Map DSL WorkflowStarted to RefuelStarted
        if isinstance(event, DslWorkflowStarted):
            # Extract inputs from DSL event
            refuel_inputs = RefuelInputs(
                label=event.inputs.get("label", "tech-debt"),
                limit=event.inputs.get("limit", 5),
                parallel=event.inputs.get("parallel", True),
                dry_run=event.inputs.get("dry_run", False),
                auto_assign=event.inputs.get("auto_assign", True),
            )
            # Note: We don't know issues_found yet at workflow start, will be set to 0
            # and updated when RefuelStepName.FETCH_ISSUES step completes
            return RefuelStarted(inputs=refuel_inputs, issues_found=0)

        # Map DSL StepStarted to IssueProcessingStarted (for process_issue steps)
        elif isinstance(event, DslStepStarted):
            # We could track issue processing if we add metadata to steps
            # For now, return None as we'll handle this in the executor
            # Future: Check if event.step_name == RefuelStepName.PROCESS_ISSUE.value
            return None

        # Map DSL StepCompleted to IssueProcessingCompleted (for process_issue steps)
        elif isinstance(event, DslStepCompleted):
            # Similar to StepStarted, this would require step metadata
            # Future: Check if event.step_name == RefuelStepName.PROCESS_ISSUE.value
            return None

        # WorkflowCompleted is handled separately in execute()
        return None

    def _build_refuel_result(self, workflow_result: WorkflowResult) -> RefuelResult:
        """Build RefuelResult from DSL WorkflowResult.

        Extracts relevant information from the DSL workflow result and constructs
        a RefuelResult with appropriate aggregations and metadata.

        Args:
            workflow_result: WorkflowResult from DSL execution.

        Returns:
            RefuelResult instance with workflow outcome.
        """
        # Extract results from workflow output
        # The DSL workflow should set these in its output
        output = workflow_result.final_output or {}

        # Get per-issue results if available
        results_data = output.get("results", [])
        results: list[IssueProcessingResult] = []

        # Convert output data to IssueProcessingResult instances
        # This assumes the workflow output includes structured result data
        for result_data in results_data:
            if isinstance(result_data, dict):
                # Reconstruct GitHubIssue
                issue_data = result_data.get("issue", {})
                issue = GitHubIssue(
                    number=issue_data.get("number", 0),
                    title=issue_data.get("title", ""),
                    body=issue_data.get("body"),
                    labels=issue_data.get("labels", []),
                    assignee=issue_data.get("assignee"),
                    url=issue_data.get("url", ""),
                )

                # Reconstruct AgentUsage
                usage_data = result_data.get("agent_usage", {})
                agent_usage = AgentUsage(
                    input_tokens=usage_data.get("input_tokens", 0),
                    output_tokens=usage_data.get("output_tokens", 0),
                    total_cost_usd=usage_data.get("total_cost_usd", 0.0),
                    duration_ms=usage_data.get("duration_ms", 0),
                )

                # Create result
                result = IssueProcessingResult(
                    issue=issue,
                    status=IssueStatus(result_data.get("status", "pending")),
                    branch=result_data.get("branch"),
                    pr_url=result_data.get("pr_url"),
                    error=result_data.get("error"),
                    duration_ms=result_data.get("duration_ms", 0),
                    agent_usage=agent_usage,
                )
                results.append(result)

        # Compute aggregations
        issues_found = output.get("issues_found", len(results))
        issues_fixed = sum(1 for r in results if r.status == IssueStatus.FIXED)
        issues_failed = sum(1 for r in results if r.status == IssueStatus.FAILED)
        issues_skipped = sum(1 for r in results if r.status == IssueStatus.SKIPPED)
        issues_processed = issues_fixed + issues_failed

        total_duration_ms = output.get(
            "total_duration_ms", workflow_result.total_duration_ms
        )
        total_cost_usd = sum(r.agent_usage.total_cost_usd or 0.0 for r in results)

        return RefuelResult(
            success=workflow_result.success and issues_failed == 0,
            issues_found=issues_found,
            issues_processed=issues_processed,
            issues_fixed=issues_fixed,
            issues_failed=issues_failed,
            issues_skipped=issues_skipped,
            results=results,
            total_duration_ms=total_duration_ms,
            total_cost_usd=total_cost_usd,
        )

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
            logger.info(f"[DRY-RUN] Would run IssueFixerAgent for #{issue.number}")
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
                    commit_message = await self._commit_generator.generate(
                        {
                            "diff": diff_output,
                            "file_stats": {},
                            "scope_hint": f"issue-{issue.number}",
                        }
                    )
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

        # DSL execution path (if enabled)
        if self._use_dsl:
            try:
                # Load workflow definition
                workflow = self._load_workflow("refuel")

                # Create executor
                self._executor = WorkflowFileExecutor(
                    registry=self._registry,
                    config=self._config,
                )

                # Convert RefuelInputs to dict for DSL executor
                workflow_inputs = {
                    "label": inputs.label,
                    "limit": inputs.limit,
                    "parallel": inputs.parallel,
                    "dry_run": inputs.dry_run,
                    "auto_assign": inputs.auto_assign,
                }

                # Execute workflow and translate events
                execution = self._executor.execute(workflow, inputs=workflow_inputs)
                async for event in execution:
                    # Translate DSL events to RefuelProgressEvent
                    refuel_event = self._translate_event(event)
                    if refuel_event:
                        yield refuel_event

                    # Handle WorkflowCompleted specially
                    if isinstance(event, DslWorkflowCompleted):
                        # Build final result
                        workflow_result = self._executor.get_result()
                        refuel_result = self._build_refuel_result(workflow_result)
                        yield RefuelCompleted(result=refuel_result)

                return

            except Exception as e:
                error_msg = f"DSL workflow execution failed: {e}"
                logger.exception(error_msg)
                # Return empty result on failure
                empty_usage = AgentUsage(
                    input_tokens=0,
                    output_tokens=0,
                    total_cost_usd=0.0,
                    duration_ms=0,
                )
                total_duration_ms = int((time.time() - workflow_start_time) * 1000)
                refuel_result = RefuelResult(
                    success=False,
                    issues_found=0,
                    issues_processed=0,
                    issues_fixed=0,
                    issues_failed=0,
                    issues_skipped=0,
                    results=[],
                    total_duration_ms=total_duration_ms,
                    total_cost_usd=0.0,
                )
                yield RefuelCompleted(result=refuel_result)
                return

        # Legacy execution path (original implementation)

        # Phase 1: Issue Discovery with retry
        if inputs.dry_run:
            logger.info(f"[DRY-RUN] Would discover issues with label: {inputs.label}")
            logger.info(f"[DRY-RUN] Would limit to {inputs.limit} issues")
            # In dry-run mode, still try to discover issues (read-only operation)
            # This allows previewing what would be processed without making changes
            try:
                runner_issues = await self._discover_issues_with_retry(inputs)
                issues = [
                    _convert_runner_issue_to_workflow_issue(ri) for ri in runner_issues
                ]
            except Exception as e:
                # If discovery fails in dry-run, continue with empty list
                logger.warning(f"[DRY-RUN] Issue discovery failed: {e}")
                issues = []
        else:
            runner_issues = await self._discover_issues_with_retry(inputs)
            issues = [
                _convert_runner_issue_to_workflow_issue(ri) for ri in runner_issues
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
