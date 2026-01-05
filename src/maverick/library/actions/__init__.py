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
- review_registry: Review-fix accountability loop registry management
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
from maverick.library.actions.dry_run import log_dry_run
from maverick.library.actions.git import (
    create_git_branch,
    git_commit,
    git_has_changes,
    git_push,
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
from maverick.library.actions.review_registry import (
    check_fix_loop_exit,
    create_issue_registry,
    create_tech_debt_issues,
    detect_deleted_files,
    generate_registry_summary,
    prepare_fixer_input,
    run_accountability_fix_loop,
    update_issue_registry,
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
    # Task actions
    "get_phase_names",
    # Git actions
    "git_commit",
    "git_push",
    "git_has_changes",
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
    # Review registry actions
    "create_issue_registry",
    "prepare_fixer_input",
    "update_issue_registry",
    "check_fix_loop_exit",
    "create_tech_debt_issues",
    "detect_deleted_files",
    "run_accountability_fix_loop",
    "generate_registry_summary",
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
    """
    # Preflight actions
    registry.actions.register("run_preflight_checks", run_preflight_checks)

    # Workspace actions
    registry.actions.register("init_workspace", init_workspace)

    # Task actions
    registry.actions.register("get_phase_names", get_phase_names)

    # Git actions
    registry.actions.register("git_commit", git_commit)
    registry.actions.register("git_push", git_push)
    registry.actions.register("git_has_changes", git_has_changes)
    registry.actions.register("create_git_branch", create_git_branch)

    # GitHub actions
    registry.actions.register("create_github_pr", create_github_pr)
    registry.actions.register("fetch_github_issues", fetch_github_issues)
    registry.actions.register("fetch_github_issue", fetch_github_issue)

    # Review actions (with both prefixed and unprefixed names for compatibility)
    registry.actions.register("gather_pr_context", gather_pr_context)
    registry.actions.register("combine_review_results", combine_review_results)
    registry.actions.register("analyze_review_findings", analyze_review_findings)
    registry.actions.register("run_review_fix_loop", run_review_fix_loop)
    registry.actions.register("generate_review_fix_report", generate_review_fix_report)
    registry.actions.register("review.gather_pr_context", gather_pr_context)
    registry.actions.register("review.combine_review_results", combine_review_results)
    registry.actions.register("review.analyze_review_findings", analyze_review_findings)
    registry.actions.register("review.run_review_fix_loop", run_review_fix_loop)
    registry.actions.register(
        "review.generate_review_fix_report", generate_review_fix_report
    )

    # Cleanup actions
    registry.actions.register("process_selected_issues", process_selected_issues)
    registry.actions.register("generate_cleanup_summary", generate_cleanup_summary)

    # Validation actions
    registry.actions.register("run_fix_retry_loop", run_fix_retry_loop)
    registry.actions.register("generate_validation_report", generate_validation_report)
    registry.actions.register("log_message", log_message)

    # Review registry actions
    registry.actions.register("create_issue_registry", create_issue_registry)
    registry.actions.register("prepare_fixer_input", prepare_fixer_input)
    registry.actions.register("update_issue_registry", update_issue_registry)
    registry.actions.register("check_fix_loop_exit", check_fix_loop_exit)
    registry.actions.register("create_tech_debt_issues", create_tech_debt_issues)
    registry.actions.register("detect_deleted_files", detect_deleted_files)
    # Also register with prefixed names for namespacing
    registry.actions.register(
        "review_registry.create_issue_registry", create_issue_registry
    )
    registry.actions.register(
        "review_registry.prepare_fixer_input", prepare_fixer_input
    )
    registry.actions.register(
        "review_registry.update_issue_registry", update_issue_registry
    )
    registry.actions.register(
        "review_registry.check_fix_loop_exit", check_fix_loop_exit
    )
    registry.actions.register(
        "review_registry.create_tech_debt_issues", create_tech_debt_issues
    )
    registry.actions.register(
        "review_registry.detect_deleted_files", detect_deleted_files
    )
    registry.actions.register(
        "run_accountability_fix_loop", run_accountability_fix_loop
    )
    registry.actions.register(
        "review_registry.run_accountability_fix_loop", run_accountability_fix_loop
    )
    registry.actions.register("generate_registry_summary", generate_registry_summary)
    registry.actions.register(
        "review_registry.generate_registry_summary", generate_registry_summary
    )

    # Dry-run actions
    registry.actions.register("log_dry_run", log_dry_run)
