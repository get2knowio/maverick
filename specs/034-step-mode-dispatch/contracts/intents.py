"""Contract definition for the intent registry.

Implementation lives in src/maverick/library/actions/intents.py.
"""

from __future__ import annotations

# Module-level constant mapping action names to intent descriptions.
# Every registered action in ComponentRegistry.actions MUST have an entry.
ACTION_INTENTS: dict[str, str] = {
    # Preflight
    "run_preflight_checks": "...",
    # Workspace
    "init_workspace": "...",
    "create_fly_workspace": "...",
    # Dependencies
    "sync_dependencies": "...",
    # Tasks
    "get_phase_names": "...",
    # Git
    "git_add": "...",
    "git_commit": "...",
    "git_push": "...",
    "git_check_and_stage": "...",
    "git_has_changes": "...",
    "git_stage_all": "...",
    "git_merge": "...",
    "create_git_branch": "...",
    # jj
    "jj_commit_bead": "...",
    "jj_describe": "...",
    "jj_snapshot_operation": "...",
    "jj_restore_operation": "...",
    "jj_squash": "...",
    "jj_absorb": "...",
    "jj_log": "...",
    "jj_diff": "...",
    "curate_history": "...",
    "gather_curation_context": "...",
    "execute_curation_plan": "...",
    # GitHub
    "create_github_pr": "...",
    "fetch_github_issues": "...",
    "fetch_github_issue": "...",
    # Review
    "gather_pr_context": "...",
    "gather_local_review_context": "...",
    "combine_review_results": "...",
    "analyze_review_findings": "...",
    "run_review_fix_loop": "...",
    "generate_review_fix_report": "...",
    # Review (prefixed aliases)
    "review.gather_pr_context": "...",
    "review.combine_review_results": "...",
    "review.analyze_review_findings": "...",
    "review.run_review_fix_loop": "...",
    "review.generate_review_fix_report": "...",
    # Cleanup
    "process_selected_issues": "...",
    "generate_cleanup_summary": "...",
    # Validation
    "run_fix_retry_loop": "...",
    "generate_validation_report": "...",
    "log_message": "...",
    # Beads
    "parse_speckit": "...",
    "create_beads": "...",
    "wire_dependencies": "...",
    "select_next_bead": "...",
    "mark_bead_complete": "...",
    "check_epic_done": "...",
    "create_beads_from_failures": "...",
    "create_beads_from_findings": "...",
    "verify_bead_completion": "...",
    "enrich_bead_descriptions": "...",
    # Dry-run
    "log_dry_run": "...",
}


def get_intent(action_name: str) -> str | None:
    """Look up the intent description for a registered action.

    Args:
        action_name: The registered action name.

    Returns:
        The intent description string, or None if not found.
    """
    return ACTION_INTENTS.get(action_name)
