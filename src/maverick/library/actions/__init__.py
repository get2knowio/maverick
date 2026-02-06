"""Python actions for DSL-based workflow execution.

This package contains Python callables (actions) that are used by workflow
steps. Each action is a function that can be referenced by name in YAML
workflow definitions.

Actions are organized by domain:
- workspace: Workspace initialization and management
- git: Git operations (commit, push, branch)
- github: GitHub operations (issues, PRs)
- validation: Validation and fix operations
- review: Code review operations
- cleanup: Cleanup workflow-specific operations
- dry_run: Dry-run mode support
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from maverick.dsl.serialization.registry import ComponentRegistry

# Import action functions
from maverick.library.actions.cleanup import (
    generate_cleanup_summary,
    process_selected_issues,
)
from maverick.library.actions.dependencies import sync_dependencies
from maverick.library.actions.dry_run import log_dry_run
from maverick.library.actions.git import (
    create_git_branch,
    git_check_and_stage,
    git_commit,
    git_has_changes,
    git_push,
    git_stage_all,
)
from maverick.library.actions.github import (
    create_github_pr,
    fetch_github_issue,
    fetch_github_issues,
)
from maverick.library.actions.preflight import run_preflight_checks
from maverick.library.actions.review import (
    analyze_review_findings,
    combine_review_results,
    gather_pr_context,
    generate_review_fix_report,
    run_review_fix_loop,
)
from maverick.library.actions.tasks import get_phase_names
from maverick.library.actions.validation import (
    generate_validation_report,
    log_message,
    run_fix_retry_loop,
)
from maverick.library.actions.workspace import init_workspace

__all__ = [
    # Preflight actions
    "run_preflight_checks",
    # Workspace actions
    "init_workspace",
    # Dependency actions
    "sync_dependencies",
    # Task actions
    "get_phase_names",
    # Git actions
    "git_commit",
    "git_push",
    "git_check_and_stage",
    "git_has_changes",
    "git_stage_all",
    "create_git_branch",
    # GitHub actions
    "create_github_pr",
    "fetch_github_issues",
    "fetch_github_issue",
    # Review actions
    "gather_pr_context",
    "combine_review_results",
    "analyze_review_findings",
    "run_review_fix_loop",
    "generate_review_fix_report",
    # Cleanup actions
    "process_selected_issues",
    "generate_cleanup_summary",
    # Validation actions
    "run_fix_retry_loop",
    "generate_validation_report",
    "log_message",
    # Dry-run actions
    "log_dry_run",
    # Registration
    "register_all_actions",
]


def register_all_actions(registry: ComponentRegistry) -> None:
    """Register all built-in actions with the component registry.

    Args:
        registry: Component registry to register actions with.

    Note:
        Actions are registered with `requires` metadata specifying which
        prerequisite checks they need. These are automatically collected
        by the preflight system before workflow execution.
    """
    # Preflight actions (no requires - it's the check itself)
    registry.actions.register("run_preflight_checks", run_preflight_checks)

    # Workspace actions
    registry.actions.register(
        "init_workspace",
        init_workspace,
        requires=("git", "git_repo", "git_remote"),
    )

    # Dependency actions (no requires - command availability is best-effort)
    registry.actions.register("sync_dependencies", sync_dependencies)

    # Task actions (no external deps)
    registry.actions.register("get_phase_names", get_phase_names)

    # Git actions - require git CLI and identity for commits
    registry.actions.register(
        "git_commit",
        git_commit,
        requires=("git", "git_identity"),
    )
    registry.actions.register(
        "git_push",
        git_push,
        requires=("git", "git_remote"),
    )
    registry.actions.register(
        "git_check_and_stage",
        git_check_and_stage,
        requires=("git", "git_repo"),
    )
    registry.actions.register(
        "git_has_changes",
        git_has_changes,
        requires=("git", "git_repo"),
    )
    registry.actions.register(
        "git_stage_all",
        git_stage_all,
        requires=("git", "git_repo"),
    )
    registry.actions.register(
        "create_git_branch",
        create_git_branch,
        requires=("git", "git_repo"),
    )

    # GitHub actions - require gh CLI and authentication
    registry.actions.register(
        "create_github_pr",
        create_github_pr,
        requires=("gh", "gh_auth"),
    )
    registry.actions.register(
        "fetch_github_issues",
        fetch_github_issues,
        requires=("gh", "gh_auth"),
    )
    registry.actions.register(
        "fetch_github_issue",
        fetch_github_issue,
        requires=("gh", "gh_auth"),
    )

    # Review actions (with both prefixed and unprefixed names for compatibility)
    # Note: Most review actions may use git internally
    registry.actions.register(
        "gather_pr_context",
        gather_pr_context,
        requires=("git", "git_repo"),
    )
    registry.actions.register("combine_review_results", combine_review_results)
    registry.actions.register("analyze_review_findings", analyze_review_findings)
    registry.actions.register("run_review_fix_loop", run_review_fix_loop)
    registry.actions.register("generate_review_fix_report", generate_review_fix_report)
    registry.actions.register(
        "review.gather_pr_context",
        gather_pr_context,
        requires=("git", "git_repo"),
    )
    registry.actions.register("review.combine_review_results", combine_review_results)
    registry.actions.register("review.analyze_review_findings", analyze_review_findings)
    registry.actions.register("review.run_review_fix_loop", run_review_fix_loop)
    registry.actions.register(
        "review.generate_review_fix_report", generate_review_fix_report
    )

    # Cleanup actions - work with GitHub issues
    registry.actions.register(
        "process_selected_issues",
        process_selected_issues,
        requires=("gh", "gh_auth"),
    )
    registry.actions.register("generate_cleanup_summary", generate_cleanup_summary)

    # Validation actions (no external deps - uses configured commands)
    registry.actions.register("run_fix_retry_loop", run_fix_retry_loop)
    registry.actions.register("generate_validation_report", generate_validation_report)
    registry.actions.register("log_message", log_message)

    # Dry-run actions (no external deps)
    registry.actions.register("log_dry_run", log_dry_run)
