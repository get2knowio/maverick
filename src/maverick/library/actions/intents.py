"""Intent descriptions for workflow actions.

Each entry in ACTION_INTENTS maps an action function name (as exported in
``maverick.library.actions.__all__``) to a short, human-readable description
of WHAT the action accomplishes. These descriptions are used by the
mode-aware dispatch system to provide observability and context.
"""

from __future__ import annotations

# Module-level constant mapping action names to intent descriptions.
# Every exported action in maverick.library.actions.__all__ MUST have an entry.
ACTION_INTENTS: dict[str, str] = {
    # Preflight
    "run_preflight_checks": (
        "Verify all prerequisites (API keys, tools, repository state) "
        "are available before workflow execution."
    ),
    # Workspace
    "init_workspace": ("Initialize the development workspace for the current project."),
    "create_fly_workspace": ("Create an isolated jj workspace clone for fly workflow execution."),
    # Dependencies
    "sync_dependencies": (
        "Synchronize project dependencies by running the configured install command."
    ),
    # Git
    "git_add": ("Stage specified files in the git index for the next commit."),
    "git_commit": ("Create a git commit with the specified message in the working directory."),
    "git_push": ("Push local commits to the configured remote git repository."),
    "git_check_and_stage": ("Check for uncommitted changes and stage them for commit."),
    "git_has_changes": ("Detect whether the working directory has uncommitted changes."),
    "git_stage_all": ("Stage all modified and untracked files in the git index."),
    "git_merge": ("Merge the specified branch into the current branch."),
    "create_git_branch": ("Create and check out a new git branch with the given name."),
    # jj
    "jj_commit_bead": ("Create a jj commit for the current bead with the specified message."),
    "jj_describe": ("Update the description of a jj revision."),
    "jj_snapshot_operation": (
        "Capture a snapshot of the current jj operation for later rollback."
    ),
    "jj_restore_operation": (
        "Restore the jj repository state to a previously captured operation snapshot."
    ),
    "jj_squash": ("Squash jj revisions together to consolidate history."),
    "jj_absorb": ("Absorb outstanding changes into the appropriate jj revisions."),
    "jj_log": ("Retrieve the jj revision log for inspection or display."),
    "jj_diff": ("Compute the diff of changes in the current jj revision."),
    "curate_history": ("Reorganize jj commit history into a clean, logical sequence for landing."),
    "gather_curation_context": (
        "Collect revision log and diff context needed for history curation."
    ),
    "execute_curation_plan": (
        "Apply the curation plan to rewrite jj history according to the curator's instructions."
    ),
    # GitHub
    "create_github_pr": ("Create a pull request on the remote GitHub repository."),
    "fetch_github_issues": ("Retrieve a list of GitHub issues matching the specified filters."),
    "fetch_github_issue": ("Retrieve a single GitHub issue by number with full details."),
    # Review (unprefixed)
    "gather_local_review_context": (
        "Collect local review context from working directory diff and changed files."
    ),
    "analyze_review_findings": (
        "Analyze combined review findings and build an issue registry with deduplication."
    ),
    "run_review_fix_loop": (
        "Iterate review-fix cycles until all actionable "
        "findings are resolved or max attempts reached."
    ),
    "generate_review_fix_report": (
        "Generate a summary report of the review-fix process with outcomes and metrics."
    ),
    # Validation
    "run_fix_retry_loop": (
        "Run validation with fix retry loop until all checks pass or max attempts reached."
    ),
    "generate_validation_report": (
        "Generate a structured report summarizing validation results and any remaining failures."
    ),
    "log_message": ("Log a structured message to the workflow event stream."),
    # Beads
    "create_beads": ("Create epic and work beads via the bd CLI."),
    "wire_dependencies": (
        "Establish dependency relationships between beads based on task ordering."
    ),
    "select_next_bead": ("Select the next ready bead from the bead queue for processing."),
    "mark_bead_complete": (
        "Mark the specified bead as completed after successful implementation."
    ),
    "check_epic_done": ("Check whether all beads in the epic have been completed."),
    "create_beads_from_failures": (
        "Create new beads from validation or test failures for follow-up fixes."
    ),
    "create_beads_from_findings": (
        "Create new beads from review findings that require separate work items."
    ),
    "verify_bead_completion": (
        "Verify that a bead's implementation satisfies its acceptance criteria."
    ),
    # Dry-run
    "log_dry_run": (
        "Log a dry-run message indicating what would be executed without performing the action."
    ),
}


def get_intent(action_name: str) -> str | None:
    """Look up the intent description for a registered action.

    Args:
        action_name: The registered action name.

    Returns:
        The intent description string, or ``None`` if the action is not
        found in the intent registry.
    """
    return ACTION_INTENTS.get(action_name)
