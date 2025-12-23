"""Python Action Contracts for DSL-Based Built-in Workflows.

This module defines the function signatures (contracts) for all Python actions
used by the built-in workflow YAML definitions. These are the interfaces that
must be implemented in `src/maverick/library/actions/`.

Each action is a Python callable that:
1. Accepts keyword arguments matching the YAML `kwargs` section
2. Returns a result dataclass defined in data-model.md
3. May be sync or async (executor handles both)
"""

from __future__ import annotations

from typing import Any, Protocol

# =============================================================================
# Workspace Actions (workspace.py)
# =============================================================================


class InitWorkspaceAction(Protocol):
    """Initialize workspace for workflow execution.

    Used by: fly.yaml (init step)

    Args:
        branch_name: Feature branch name to create/checkout

    Returns:
        WorkspaceState with branch info and task file detection
    """

    async def __call__(self, branch_name: str) -> dict[str, Any]: ...


# =============================================================================
# Git Actions (git.py)
# =============================================================================


class GitCommitAction(Protocol):
    """Create a git commit with the given message.

    Used by: commit_and_push.yaml (commit_with_message, commit_with_generated)

    Args:
        message: Commit message
        add_all: Whether to stage all changes (git add .)
        include_attribution: Include AI co-author attribution

    Returns:
        GitCommitResult with commit SHA and status
    """

    async def __call__(
        self,
        message: str,
        add_all: bool = True,
        include_attribution: bool = True,
    ) -> dict[str, Any]: ...


class GitPushAction(Protocol):
    """Push current branch to remote.

    Used by: commit_and_push.yaml (push step)

    Args:
        set_upstream: Whether to set upstream tracking

    Returns:
        GitPushResult with push status
    """

    async def __call__(self, set_upstream: bool = True) -> dict[str, Any]: ...


class CreateGitBranchAction(Protocol):
    """Create or checkout a git branch.

    Used by: quick_fix.yaml (create_branch step)

    Args:
        branch_name: Name of branch to create/checkout
        base: Base branch to create from (default: main)

    Returns:
        GitBranchResult with branch creation status
    """

    async def __call__(
        self,
        branch_name: str,
        base: str = "main",
    ) -> dict[str, Any]: ...


# =============================================================================
# GitHub Actions (github.py)
# =============================================================================


class FetchGitHubIssuesAction(Protocol):
    """Fetch issues from GitHub with label filter.

    Used by: refuel.yaml (fetch_issues step)

    Args:
        label: Label to filter issues by
        limit: Maximum number of issues to fetch
        state: Issue state filter ("open", "closed", "all")

    Returns:
        FetchIssuesResult with list of issues
    """

    async def __call__(
        self,
        label: str,
        limit: int = 5,
        state: str = "open",
    ) -> dict[str, Any]: ...


class FetchGitHubIssueAction(Protocol):
    """Fetch a single issue from GitHub.

    Used by: quick_fix.yaml (fetch_issue step)

    Args:
        issue_number: GitHub issue number

    Returns:
        FetchSingleIssueResult with issue details
    """

    async def __call__(self, issue_number: int) -> dict[str, Any]: ...


class CreateGitHubPRAction(Protocol):
    """Create a pull request via GitHub CLI.

    Used by: create_pr_with_summary.yaml (create_pr step)

    Args:
        base_branch: Target branch for PR
        draft: Create as draft PR
        title: User-provided title (optional)
        generated_title: Auto-generated title (optional)
        generated_body: Auto-generated PR body

    Returns:
        PRCreationResult with PR URL and number
    """

    async def __call__(
        self,
        base_branch: str,
        draft: bool,
        title: str | None,
        generated_title: str | None,
        generated_body: str,
    ) -> dict[str, Any]: ...


# =============================================================================
# Validation Actions (validation.py)
# =============================================================================


class RunFixRetryLoopAction(Protocol):
    """Execute fix-and-retry loop for validation failures.

    Used by: validate_and_fix.yaml (fix_loop step)

    Args:
        stages: Validation stages to run
        max_attempts: Maximum fix attempts
        fixer_agent: Name of fixer agent to use
        validation_result: Initial validation result

    Returns:
        Dict with final validation status and fix history
    """

    async def __call__(
        self,
        stages: list[str],
        max_attempts: int,
        fixer_agent: str,
        validation_result: dict[str, Any],
    ) -> dict[str, Any]: ...


class GenerateValidationReportAction(Protocol):
    """Generate final validation report.

    Used by: validate_and_fix.yaml (report step), validate.yaml (report step)

    Args:
        initial_result: Initial validation result
        fix_loop_result: Result from fix loop (optional)
        max_attempts: Configured max attempts
        stages: Stages that were run
        fix_enabled: Whether fix was enabled (for validate.yaml)
        fix_result: Fix result (for validate.yaml)

    Returns:
        ValidationReportResult with summary
    """

    async def __call__(
        self,
        initial_result: dict[str, Any],
        fix_loop_result: dict[str, Any] | None = None,
        max_attempts: int = 3,
        stages: list[str] | None = None,
        fix_enabled: bool = True,
        fix_result: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...


class LogMessageAction(Protocol):
    """Log a message (for skip scenarios in validate.yaml).

    Used by: validate.yaml (skip_fixes, skip_fixes_disabled steps)

    Args:
        message: Message to log

    Returns:
        Dict with logged message
    """

    def __call__(self, message: str) -> dict[str, Any]: ...


# =============================================================================
# Review Actions (review.py)
# =============================================================================


class GatherPRContextAction(Protocol):
    """Gather PR context for code review.

    Used by: review.yaml (gather_context step)

    Args:
        pr_number: PR number (optional, auto-detect if None)
        base_branch: Base branch for comparison

    Returns:
        ReviewContextResult with PR metadata and diff
    """

    async def __call__(
        self,
        pr_number: int | None,
        base_branch: str,
    ) -> dict[str, Any]: ...


class RunCodeRabbitReviewAction(Protocol):
    """Execute CodeRabbit review if available.

    Used by: review.yaml (run_coderabbit step)

    Args:
        pr_number: PR number to review
        context: Gathered PR context

    Returns:
        CodeRabbitResult with findings
    """

    async def __call__(
        self,
        pr_number: int | None,
        context: dict[str, Any],
    ) -> dict[str, Any]: ...


class CombineReviewResultsAction(Protocol):
    """Combine review results from multiple sources.

    Used by: review.yaml (combine_results step)

    Args:
        agent_review: Agent review output
        coderabbit_review: CodeRabbit review output
        pr_metadata: PR metadata

    Returns:
        CombinedReviewResult with unified report
    """

    async def __call__(
        self,
        agent_review: dict[str, Any],
        coderabbit_review: dict[str, Any],
        pr_metadata: dict[str, Any],
    ) -> dict[str, Any]: ...


# =============================================================================
# Refuel Actions (refuel.py)
# =============================================================================


class ProcessSelectedIssuesAction(Protocol):
    """Process selected issues (parallel or sequential).

    Used by: refuel.yaml (process_issues, process_issues_sequential steps)

    Args:
        issues: List of selected issues to process
        parallel: Whether to process in parallel

    Returns:
        Dict with list of ProcessedIssueEntry results
    """

    async def __call__(
        self,
        issues: list[dict[str, Any]],
        parallel: bool,
    ) -> dict[str, Any]: ...


class GenerateRefuelSummaryAction(Protocol):
    """Generate summary of refuel workflow execution.

    Used by: refuel.yaml (report_summary step)

    Args:
        parallel_result: Result from parallel processing (optional)
        sequential_result: Result from sequential processing (optional)
        total_requested: Total issues requested
        label: Label used for filtering
        parallel_mode: Whether parallel mode was used

    Returns:
        RefuelSummaryResult with aggregated results
    """

    async def __call__(
        self,
        parallel_result: dict[str, Any] | None,
        sequential_result: dict[str, Any] | None,
        total_requested: int,
        label: str,
        parallel_mode: bool,
    ) -> dict[str, Any]: ...


# =============================================================================
# Dry-Run Actions (dry_run.py)
# =============================================================================


class LogDryRunAction(Protocol):
    """Log a planned operation in dry-run mode.

    Used by: fly.yaml, refuel.yaml (dry-run variants)

    Args:
        operation: Name of operation that would be performed
        details: Description of what would happen

    Returns:
        Dict with operation and details for logging
    """

    def __call__(
        self,
        operation: str,
        details: str,
    ) -> dict[str, Any]: ...


# =============================================================================
# Action Registry
# =============================================================================

# Mapping of action names (as used in YAML) to their protocol types
ACTION_CONTRACTS: dict[str, type] = {
    # Workspace
    "init_workspace": InitWorkspaceAction,
    # Git
    "git_commit": GitCommitAction,
    "git_push": GitPushAction,
    "create_git_branch": CreateGitBranchAction,
    # GitHub
    "fetch_github_issues": FetchGitHubIssuesAction,
    "fetch_github_issue": FetchGitHubIssueAction,
    "create_github_pr": CreateGitHubPRAction,
    # Validation
    "run_fix_retry_loop": RunFixRetryLoopAction,
    "generate_validation_report": GenerateValidationReportAction,
    "log_message": LogMessageAction,
    # Review
    "review.gather_pr_context": GatherPRContextAction,
    "review.run_coderabbit_review": RunCodeRabbitReviewAction,
    "review.combine_review_results": CombineReviewResultsAction,
    # Refuel
    "process_selected_issues": ProcessSelectedIssuesAction,
    "generate_refuel_summary": GenerateRefuelSummaryAction,
    # Dry-run
    "log_dry_run": LogDryRunAction,
}
