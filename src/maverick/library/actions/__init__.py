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
from maverick.library.actions.beads import (
    check_epic_done,
    create_beads,
    create_beads_from_failures,
    create_beads_from_findings,
    enrich_bead_descriptions,
    mark_bead_complete,
    parse_speckit,
    select_next_bead,
    verify_bead_completion,
    wire_dependencies,
)
from maverick.library.actions.cleanup import (
    generate_cleanup_summary,
    process_selected_issues,
)
from maverick.library.actions.dependencies import sync_dependencies
from maverick.library.actions.dry_run import log_dry_run
from maverick.library.actions.github import (
    create_github_pr,
    fetch_github_issue,
    fetch_github_issues,
)
from maverick.library.actions.jj import (
    create_git_branch,
    curate_history,
    git_add,
    git_check_and_stage,
    git_commit,
    git_has_changes,
    git_merge,
    git_push,
    git_stage_all,
    jj_absorb,
    jj_describe,
    jj_diff,
    jj_log,
    jj_restore_operation,
    jj_snapshot_operation,
    jj_squash,
)
from maverick.library.actions.preflight import run_preflight_checks
from maverick.library.actions.review import (
    analyze_review_findings,
    combine_review_results,
    gather_local_review_context,
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
    # Bead actions
    "parse_speckit",
    "create_beads",
    "wire_dependencies",
    "select_next_bead",
    "mark_bead_complete",
    "check_epic_done",
    "create_beads_from_failures",
    "create_beads_from_findings",
    "verify_bead_completion",
    "enrich_bead_descriptions",
    # Preflight actions
    "run_preflight_checks",
    # Workspace actions
    "init_workspace",
    # Dependency actions
    "sync_dependencies",
    # Task actions
    "get_phase_names",
    # Git actions (via jj)
    "git_add",
    "git_commit",
    "git_push",
    "git_check_and_stage",
    "git_has_changes",
    "git_merge",
    "git_stage_all",
    "create_git_branch",
    # jj-specific actions
    "jj_describe",
    "jj_snapshot_operation",
    "jj_restore_operation",
    "jj_squash",
    "jj_absorb",
    "jj_log",
    "jj_diff",
    "curate_history",
    # GitHub actions
    "create_github_pr",
    "fetch_github_issues",
    "fetch_github_issue",
    # Review actions
    "gather_pr_context",
    "gather_local_review_context",
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

    # Git actions (via jj) - require jj CLI and colocated repo
    registry.actions.register(
        "git_add",
        git_add,
        requires=("jj", "jj_colocated"),
    )
    registry.actions.register(
        "git_commit",
        git_commit,
        requires=("jj", "jj_colocated"),
    )
    registry.actions.register(
        "git_push",
        git_push,
        requires=("jj", "jj_colocated", "git_remote"),
    )
    registry.actions.register(
        "git_check_and_stage",
        git_check_and_stage,
        requires=("jj", "jj_colocated"),
    )
    registry.actions.register(
        "git_has_changes",
        git_has_changes,
        requires=("jj", "jj_colocated"),
    )
    registry.actions.register(
        "git_stage_all",
        git_stage_all,
        requires=("jj", "jj_colocated"),
    )
    registry.actions.register(
        "git_merge",
        git_merge,
        requires=("jj", "jj_colocated"),
    )
    registry.actions.register(
        "create_git_branch",
        create_git_branch,
        requires=("jj", "jj_colocated"),
    )

    # jj-specific actions
    registry.actions.register(
        "jj_describe",
        jj_describe,
        requires=("jj", "jj_colocated"),
    )
    registry.actions.register(
        "jj_snapshot_operation",
        jj_snapshot_operation,
        requires=("jj",),
    )
    registry.actions.register(
        "jj_restore_operation",
        jj_restore_operation,
        requires=("jj",),
    )
    registry.actions.register(
        "jj_squash",
        jj_squash,
        requires=("jj",),
    )
    registry.actions.register(
        "jj_absorb",
        jj_absorb,
        requires=("jj",),
    )
    registry.actions.register(
        "jj_log",
        jj_log,
        requires=("jj",),
    )
    registry.actions.register(
        "jj_diff",
        jj_diff,
        requires=("jj",),
    )
    registry.actions.register(
        "curate_history",
        curate_history,
        requires=("jj", "jj_colocated"),
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
    registry.actions.register(
        "gather_local_review_context",
        gather_local_review_context,
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

    # Bead actions - parse_speckit only reads spec files (no bd needed),
    # but create_beads and wire_dependencies require the bd CLI.
    registry.actions.register("parse_speckit", parse_speckit)
    registry.actions.register("create_beads", create_beads, requires=("bd",))
    registry.actions.register("wire_dependencies", wire_dependencies, requires=("bd",))
    registry.actions.register("select_next_bead", select_next_bead, requires=("bd",))
    registry.actions.register(
        "mark_bead_complete", mark_bead_complete, requires=("bd",)
    )
    registry.actions.register("check_epic_done", check_epic_done, requires=("bd",))
    registry.actions.register(
        "create_beads_from_failures", create_beads_from_failures, requires=("bd",)
    )
    registry.actions.register(
        "create_beads_from_findings", create_beads_from_findings, requires=("bd",)
    )
    registry.actions.register("verify_bead_completion", verify_bead_completion)
    registry.actions.register("enrich_bead_descriptions", enrich_bead_descriptions)

    # Dry-run actions (no external deps)
    registry.actions.register("log_dry_run", log_dry_run)
