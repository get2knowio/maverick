#!/bin/bash
# on-workflow-end.sh - Called at the end of any maverick workflow (fly/refuel)
#
# Usage: echo '{"workflow": "fly", ...}' | ./on-workflow-end.sh [--dry-run]
#
# Input JSON (stdin):
# {
#   "workflow": "fly" | "refuel",
#   "branch": "008-up-lifecycle-hooks",
#   "spec_dir": "specs/008-up-lifecycle-hooks",
#   "status": "success" | "failed" | "blocked",
#   "pr_url": "https://github.com/...",
#   "summary": {
#     "tasks_completed": 15,
#     "review_issues_fixed": 6,
#     "validation_passed": true,
#     "duration_minutes": 45
#   },
#   "blockers": []
# }
#
# Output JSON (stdout):
# {
#   "cleanup_done": true,
#   "message": "Workflow complete"
# }
#
# Config options (hooks.json):
#   hooks.on-workflow-end.enabled           - Enable/disable this hook (default: true)
#   hooks.on-workflow-end.cleanup_marker    - Remove workflow marker file (default: true)
#   hooks.on-workflow-end.cleanup_temp_files - Remove temp files (default: true)
#   hooks.on-workflow-end.notify            - Send notifications (default: true)

source "$(dirname "$0")/common.sh"

# Initialize hook (checks override, enabled status, dry-run)
init_hook "on-workflow-end" "$@"

# Parse input
WORKFLOW=$(get_input "workflow" "unknown")
BRANCH=$(get_input "branch" "unknown")
STATUS=$(get_input "status" "unknown")
PR_URL=$(get_input "pr_url" "")

log "info" "Workflow '$WORKFLOW' ending with status: $STATUS"

CLEANUP_DONE=false

# 1. Remove workflow marker (disables auto-approvals) - if enabled
MARKER_FILE="/tmp/maverick-workflow-active"
if hook_feature_enabled "on-workflow-end" "cleanup_marker"; then
    if [ -f "$MARKER_FILE" ]; then
        if is_dry_run; then
            dry_run_log "remove file" "$MARKER_FILE"
        else
            rm -f "$MARKER_FILE"
            log "info" "Removed workflow marker"
        fi
        CLEANUP_DONE=true
    fi
fi

# 2. Clean up temp files - if enabled
if hook_feature_enabled "on-workflow-end" "cleanup_temp_files"; then
    TEMP_FILES="/tmp/pr-body.md /tmp/pr-body-final.md /tmp/pr_info.json"
    for f in $TEMP_FILES; do
        if [ -f "$f" ]; then
            if is_dry_run; then
                dry_run_log "remove file" "$f"
            else
                rm -f "$f"
            fi
            CLEANUP_DONE=true
        fi
    done
    if [ "$CLEANUP_DONE" = true ] && ! is_dry_run; then
        log "info" "Cleaned up temp files"
    fi
fi

# 3. Send final notification based on status - if enabled
if hook_feature_enabled "on-workflow-end" "notify"; then
    case "$STATUS" in
        success)
            notify "complete" "Workflow complete: $BRANCH - $PR_URL"
            ;;
        failed)
            notify "error" "Workflow failed: $BRANCH"
            ;;
        blocked)
            notify "error" "Workflow blocked: $BRANCH - needs human intervention"
            ;;
        *)
            notify "complete" "Workflow ended: $BRANCH ($STATUS)"
            ;;
    esac
fi

# 4. Return result
respond '{"cleanup_done": true, "message": "Workflow complete"}'
