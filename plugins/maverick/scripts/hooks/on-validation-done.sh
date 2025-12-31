#!/bin/bash
# on-validation-done.sh - Called after validation phase completes
#
# Usage: echo '{"branch": "...", ...}' | ./on-validation-done.sh [--dry-run]
#
# Input JSON (stdin):
# {
#   "branch": "008-up-lifecycle-hooks",
#   "spec_dir": "specs/008-up-lifecycle-hooks",
#   "validation_result": {
#     "all_passed": true,
#     "iterations": 2,
#     "checks": {
#       "fmt": true,
#       "clippy": true,
#       "build": true,
#       "test": true
#     }
#   },
#   "fixes_applied": 3,
#   "blockers": []
# }
#
# Output JSON (stdout):
# {
#   "continue": true,
#   "commit_sha": "ghi789",
#   "message": "Validation fixes committed"
# }
#
# Config options (hooks.json):
#   hooks.on-validation-done.enabled     - Enable/disable this hook (default: true)
#   hooks.on-validation-done.auto_commit - Auto-commit changes (default: true)
#   hooks.on-validation-done.auto_push   - Auto-push after commit (default: true)
#   hooks.on-validation-done.notify      - Send notifications (default: true)

source "$(dirname "$0")/common.sh"

# Initialize hook (checks override, enabled status, dry-run)
init_hook "on-validation-done" "$@"

# Parse input
BRANCH=$(get_input "branch" "unknown")
ALL_PASSED=$(get_input "validation_result.all_passed" "false")
ITERATIONS=$(get_input "validation_result.iterations" "1")
FIXES_APPLIED=$(get_input "fixes_applied" "0")

log "info" "Validation complete: passed=$ALL_PASSED, iterations=$ITERATIONS, fixes=$FIXES_APPLIED"

COMMIT_SHA=""

# 1. Commit validation fixes if any changes (if enabled)
if hook_feature_enabled "on-validation-done" "auto_commit"; then
    if [ -n "$(git status --porcelain)" ]; then
        COMMIT_MSG="fix($BRANCH): resolve validation failures

Applied $FIXES_APPLIED fixes over $ITERATIONS validation iterations."

        git_commit "$COMMIT_MSG"

        if ! is_dry_run; then
            COMMIT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "")
        else
            COMMIT_SHA="dry-run"
        fi
        log "info" "Created commit: $COMMIT_SHA"
    else
        log "info" "No validation changes to commit"
    fi
fi

# 2. Push changes (if enabled)
if hook_feature_enabled "on-validation-done" "auto_push"; then
    git_push
fi

# 3. Send notification based on result (if enabled)
if hook_feature_enabled "on-validation-done" "notify"; then
    if [ "$ALL_PASSED" = "true" ]; then
        notify "testing" "Validation passed ($BRANCH)"
    else
        notify "error" "Validation has blockers ($BRANCH)"
    fi
fi

# 4. Return result
if [ -n "$COMMIT_SHA" ]; then
    respond "{\"continue\": $ALL_PASSED, \"commit_sha\": \"$COMMIT_SHA\", \"message\": \"Validation fixes committed\"}"
else
    respond "{\"continue\": $ALL_PASSED, \"commit_sha\": null, \"message\": \"Validation complete\"}"
fi
