"""Python actions for DSL-based workflow execution.

This package contains Python callables (actions) that are used by workflow
steps. Each action is a function that can be referenced by name in YAML
workflow definitions.

Actions are organized by domain:
- workspace: Workspace initialization and management
- git: Git operations (commit, push, branch)
- github: GitHub operations (issues, PRs)
- validation: Validation and fix operations
- dry_run: Dry-run mode support

The legacy ``review`` action surface (text-mode dual-reviewer + fix
loop) was removed in the OpenCode-substrate cleanup; the live actor
flow under :mod:`maverick.actors.xoscar.fly_supervisor` runs reviews
via two parallel ReviewerActor instances and a structured-output
fixer instead.
"""

from __future__ import annotations

# Import action functions
from maverick.library.actions.beads import (
    create_beads,
    defer_bead,
    mark_bead_complete,
    select_next_bead,
    wire_dependencies,
)
from maverick.library.actions.dependencies import sync_dependencies
from maverick.library.actions.dry_run import log_dry_run
from maverick.library.actions.git import (
    git_has_changes,
    git_merge,
)
from maverick.library.actions.github import (
    create_github_pr,
    fetch_github_issue,
    fetch_github_issues,
)
from maverick.library.actions.jj import (
    curate_history,
    execute_curation_plan,
    gather_curation_context,
    jj_absorb,
    jj_commit_bead,
    jj_describe,
    jj_diff,
    jj_log,
    jj_restore_operation,
    jj_snapshot_operation,
    jj_squash,
)
from maverick.library.actions.preflight import run_preflight_checks
from maverick.library.actions.validation import (
    generate_validation_report,
    log_message,
    run_fix_retry_loop,
)
from maverick.library.actions.workspace import create_fly_workspace, init_workspace

__all__ = [
    # Bead actions
    "create_beads",
    "defer_bead",
    "wire_dependencies",
    "select_next_bead",
    "mark_bead_complete",
    # Preflight actions
    "run_preflight_checks",
    # Workspace actions
    "init_workspace",
    "create_fly_workspace",
    # Dependency actions
    "sync_dependencies",
    # Git actions (read-only and merge fallback only — writes go through jj)
    "git_has_changes",
    "git_merge",
    # jj-specific actions
    "jj_commit_bead",
    "jj_describe",
    "jj_snapshot_operation",
    "jj_restore_operation",
    "jj_squash",
    "jj_absorb",
    "jj_log",
    "jj_diff",
    "curate_history",
    "gather_curation_context",
    "execute_curation_plan",
    # GitHub actions
    "create_github_pr",
    "fetch_github_issues",
    "fetch_github_issue",
    # Validation actions
    "run_fix_retry_loop",
    "generate_validation_report",
    "log_message",
    # Dry-run actions
    "log_dry_run",
]
