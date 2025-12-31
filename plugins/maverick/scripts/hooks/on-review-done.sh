#!/bin/bash
# on-review-done.sh - Called after code review phase completes
#
# Usage: echo '{"branch": "...", ...}' | ./on-review-done.sh [--dry-run]
#
# Input JSON (stdin):
# {
#   "branch": "008-up-lifecycle-hooks",
#   "spec_dir": "specs/008-up-lifecycle-hooks",
#   "review_summary": {
#     "coderabbit_issues": 5,
#     "architecture_issues": 3,
#     "total_unique": 7,
#     "issues_fixed": 6,
#     "issues_deferred": 1
#   },
#   "improvements": {
#     "critical": 1,
#     "major": 2,
#     "minor": 3,
#     "style": 0
#   },
#   "files_changed": ["src/foo.rs", "src/bar.rs"]
# }
#
# Output JSON (stdout):
# {
#   "continue": true,
#   "commit_sha": "def456",
#   "message": "Review fixes committed"
# }
#
# Config options (hooks.json):
#   hooks.on-review-done.enabled     - Enable/disable this hook (default: true)
#   hooks.on-review-done.auto_commit - Auto-commit changes (default: true)
#   hooks.on-review-done.auto_push   - Auto-push after commit (default: true)
#   hooks.on-review-done.notify      - Send notifications (default: true)

source "$(dirname "$0")/common.sh"

# Initialize hook (checks override, enabled status, dry-run)
init_hook "on-review-done" "$@"

# Parse input
BRANCH=$(get_input "branch" "unknown")
TOTAL_ISSUES=$(get_input "review_summary.total_unique" "0")
ISSUES_FIXED=$(get_input "review_summary.issues_fixed" "0")
ISSUES_DEFERRED=$(get_input "review_summary.issues_deferred" "0")

log "info" "Code review complete: $ISSUES_FIXED/$TOTAL_ISSUES issues fixed"

COMMIT_SHA=""

# 1. Commit review fixes if any changes (if enabled)
if hook_feature_enabled "on-review-done" "auto_commit"; then
    if [ -n "$(git status --porcelain)" ]; then
        DEFERRED_MSG=""
        if [ "$ISSUES_DEFERRED" -gt 0 ]; then
            DEFERRED_MSG="
Deferred $ISSUES_DEFERRED issues for follow-up."
        fi

        COMMIT_MSG="refactor($BRANCH): address code review feedback

Fixed $ISSUES_FIXED issues identified during review.$DEFERRED_MSG"

        git_commit "$COMMIT_MSG"

        if ! is_dry_run; then
            COMMIT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "")
        else
            COMMIT_SHA="dry-run"
        fi
        log "info" "Created commit: $COMMIT_SHA"
    else
        log "info" "No review changes to commit"
    fi
fi

# 2. Push changes (if enabled)
if hook_feature_enabled "on-review-done" "auto_push"; then
    git_push
fi

# 3. Send notification (if enabled)
if hook_feature_enabled "on-review-done" "notify"; then
    if [ "$ISSUES_DEFERRED" -gt 0 ]; then
        notify "review" "Review done: $ISSUES_FIXED fixed, $ISSUES_DEFERRED deferred ($BRANCH)"
    else
        notify "review" "Review done: $ISSUES_FIXED issues fixed ($BRANCH)"
    fi
fi

# 4. Return result
if [ -n "$COMMIT_SHA" ]; then
    respond "{\"continue\": true, \"commit_sha\": \"$COMMIT_SHA\", \"message\": \"Review fixes committed\"}"
else
    respond '{"continue": true, "commit_sha": null, "message": "No review changes"}'
fi
