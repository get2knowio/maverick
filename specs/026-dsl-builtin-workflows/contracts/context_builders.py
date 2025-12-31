"""Context Builder Contracts for DSL-Based Built-in Workflows.

This module defines the function signatures (contracts) for all context builders
used by agent and generate steps in the built-in workflow YAML definitions.

Each context builder is an async function that:
1. Receives a WorkflowContext with inputs and prior step results
2. Gathers necessary data (file reads, git commands, etc.)
3. Returns a dict suitable for the target agent/generator
"""

from __future__ import annotations

from typing import Any, Protocol

# =============================================================================
# Agent Context Builders
# =============================================================================


class ImplementationContextBuilder(Protocol):
    """Build context for the implementer agent.

    Used by: fly.yaml (implement step)

    The context includes:
    - task_file: Path from inputs or auto-detected
    - task_content: Full content of tasks.md
    - project_structure: Directory tree
    - spec_artifacts: Spec files (spec.md, plan.md, etc.)
    - conventions: CLAUDE.md content

    Args:
        inputs: Workflow inputs (branch_name, task_file, etc.)
        step_results: Results from prior steps (init workspace result)

    Returns:
        ImplementationContext as dict
    """

    async def __call__(
        self,
        inputs: dict[str, Any],
        step_results: dict[str, dict[str, Any]],
    ) -> dict[str, Any]: ...


class ReviewContextBuilder(Protocol):
    """Build context for the code reviewer agent.

    Used by: fly.yaml (review step), review.yaml (agent_review step)

    The context includes:
    - diff: Git diff against base branch
    - changed_files: List of changed file paths
    - conventions: CLAUDE.md content
    - base_branch: Target branch
    - pr_metadata: PR info if available
    - coderabbit_findings: CodeRabbit results if available

    Args:
        inputs: Workflow inputs (base_branch, pr_number, etc.)
        step_results: Results from prior steps (gather_context, run_coderabbit)

    Returns:
        ReviewContext as dict
    """

    async def __call__(
        self,
        inputs: dict[str, Any],
        step_results: dict[str, dict[str, Any]],
    ) -> dict[str, Any]: ...


class IssueFixContextBuilder(Protocol):
    """Build context for the issue fixer agent.

    Used by: quick_fix.yaml (fix_issue step)

    The context includes:
    - issue_number: GitHub issue number
    - issue_title: Issue title
    - issue_body: Issue description
    - branch_name: Current branch
    - related_files: Files potentially related to the issue
    - conventions: CLAUDE.md content

    Args:
        inputs: Workflow inputs (issue_number)
        step_results: Results from prior steps (fetch_issue, create_branch)

    Returns:
        IssueFixContext as dict
    """

    async def __call__(
        self,
        inputs: dict[str, Any],
        step_results: dict[str, dict[str, Any]],
    ) -> dict[str, Any]: ...


class IssueAnalyzerContextBuilder(Protocol):
    """Build context for the issue analyzer agent.

    Used by: refuel.yaml (analyze_issues step)

    The context includes:
    - issues: List of fetched issues
    - max_parallel: Whether parallel processing is requested

    Args:
        inputs: Workflow inputs (parallel, limit)
        step_results: Results from prior steps (fetch_issues)

    Returns:
        Dict with issues and analysis parameters
    """

    async def __call__(
        self,
        inputs: dict[str, Any],
        step_results: dict[str, dict[str, Any]],
    ) -> dict[str, Any]: ...


# =============================================================================
# Generator Context Builders
# =============================================================================


class CommitMessageContextBuilder(Protocol):
    """Build context for the commit message generator.

    Used by: commit_and_push.yaml (generate_message step)

    The context includes:
    - diff: Git diff of staged changes
    - file_stats: Insertions/deletions per file
    - recent_commits: Recent commit messages for style reference

    Args:
        inputs: Workflow inputs (message if provided)
        step_results: Results from prior steps

    Returns:
        CommitMessageContext as dict
    """

    async def __call__(
        self,
        inputs: dict[str, Any],
        step_results: dict[str, dict[str, Any]],
    ) -> dict[str, Any]: ...


class PRBodyContextBuilder(Protocol):
    """Build context for the PR body generator.

    Used by: create_pr_with_summary.yaml (generate_body step)

    The context includes:
    - commits: All commits on the branch
    - diff_stats: File change statistics
    - task_summary: Summary from task file (if available)
    - validation_results: Validation/test results

    Args:
        inputs: Workflow inputs (base_branch, draft, title)
        step_results: Results from prior steps

    Returns:
        PRBodyContext as dict
    """

    async def __call__(
        self,
        inputs: dict[str, Any],
        step_results: dict[str, dict[str, Any]],
    ) -> dict[str, Any]: ...


class PRTitleContextBuilder(Protocol):
    """Build context for the PR title generator.

    Used by: create_pr_with_summary.yaml (generate_title step)

    The context includes:
    - commits: Commit messages from the branch
    - branch_name: Current branch name
    - task_summary: Summary from task file (if available)
    - diff_overview: Brief overview of changes

    Args:
        inputs: Workflow inputs (title if provided)
        step_results: Results from prior steps

    Returns:
        Dict with title generation context
    """

    async def __call__(
        self,
        inputs: dict[str, Any],
        step_results: dict[str, dict[str, Any]],
    ) -> dict[str, Any]: ...


# =============================================================================
# Context Builder Registry
# =============================================================================

# Mapping of context builder names (as used in YAML) to their protocol types
CONTEXT_BUILDER_CONTRACTS: dict[str, type] = {
    # Agent contexts
    "implementation_context": ImplementationContextBuilder,
    "review_context": ReviewContextBuilder,
    "issue_fix_context": IssueFixContextBuilder,
    "issue_analyzer_context": IssueAnalyzerContextBuilder,
    # Generator contexts
    "commit_message_context": CommitMessageContextBuilder,
    "pr_body_context": PRBodyContextBuilder,
    "pr_title_context": PRTitleContextBuilder,
}
