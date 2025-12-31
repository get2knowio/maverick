#!/bin/bash
# on-implementation-done.sh - Called after all tasks in tasks.md are complete
#
# Usage: echo '{"branch": "...", ...}' | ./on-implementation-done.sh [--dry-run]
#
# Input JSON (stdin):
# {
#   "spec_dir": "specs/008-up-lifecycle-hooks",
#   "tasks_file": "specs/008-up-lifecycle-hooks/tasks.md",
#   "branch": "008-up-lifecycle-hooks",
#   "total_tasks": 15,
#   "phases_completed": 4,
#   "implementation_summary": [
#     {"task": "T001", "status": "complete", "files": ["src/foo.rs"]},
#     ...
#   ]
# }
#
# Output JSON (stdout):
# {
#   "continue": true,
#   "commit_sha": "abc123",
#   "message": "Implementation committed"
# }
#
# Config options (hooks.json):
#   hooks.on-implementation-done.enabled     - Enable/disable this hook (default: true)
#   hooks.on-implementation-done.auto_commit - Auto-commit changes (default: true)
#   hooks.on-implementation-done.auto_push   - Auto-push after commit (default: true)
#   hooks.on-implementation-done.notify      - Send notifications (default: true)

source "$(dirname "$0")/common.sh"

# Initialize hook (checks override, enabled status, dry-run)
init_hook "on-implementation-done" "$@"

# Parse input
BRANCH=$(get_input "branch" "unknown")
SPEC_DIR=$(get_input "spec_dir" "")
TOTAL_TASKS=$(get_input "total_tasks" "0")

log "info" "Implementation complete: $TOTAL_TASKS tasks on branch $BRANCH"

COMMIT_SHA=""

# 1. Stage and commit all implementation work (if enabled)
if hook_feature_enabled "on-implementation-done" "auto_commit"; then
    if [ -n "$(git status --porcelain)" ]; then
        COMMIT_MSG="feat($BRANCH): implement spec tasks

Completed $TOTAL_TASKS tasks from $SPEC_DIR/tasks.md"

        git_commit "$COMMIT_MSG"

        if ! is_dry_run; then
            COMMIT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "")
        else
            COMMIT_SHA="dry-run"
        fi
        log "info" "Created commit: $COMMIT_SHA"
    else
        log "info" "No changes to commit"
    fi
fi

# 2. Push changes (if enabled)
if hook_feature_enabled "on-implementation-done" "auto_push"; then
    git_push
fi

# 3. Send notification (if enabled)
if hook_feature_enabled "on-implementation-done" "notify"; then
    notify "implementation_done" "Implementation complete: $BRANCH ($TOTAL_TASKS tasks)"
fi

# 4. Return result
if [ -n "$COMMIT_SHA" ]; then
    respond "{\"continue\": true, \"commit_sha\": \"$COMMIT_SHA\", \"message\": \"Implementation committed\"}"
else
    respond '{"continue": true, "commit_sha": null, "message": "No changes to commit"}'
fi
