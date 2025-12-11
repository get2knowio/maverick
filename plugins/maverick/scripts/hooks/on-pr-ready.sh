#!/bin/bash
# on-pr-ready.sh - Called when PR is created or updated
#
# Usage: echo '{"branch": "...", ...}' | ./on-pr-ready.sh [--dry-run]
#
# Input JSON (stdin):
# {
#   "branch": "008-up-lifecycle-hooks",
#   "spec_dir": "specs/008-up-lifecycle-hooks",
#   "pr_title": "feat(008-up-lifecycle-hooks): implement lifecycle hooks",
#   "pr_body_file": "/tmp/pr-body.md",
#   "workflow_summary": {
#     "tasks_completed": 15,
#     "review_issues_fixed": 6,
#     "validation_iterations": 2,
#     "convention_updates": true
#   }
# }
#
# Output JSON (stdout):
# {
#   "action": "created" | "updated",
#   "pr_url": "https://github.com/...",
#   "pr_number": 123
# }
#
# Config options (hooks.json):
#   hooks.on-pr-ready.enabled   - Enable/disable this hook (default: true)
#   hooks.on-pr-ready.auto_push - Push before creating PR (default: true)
#   hooks.on-pr-ready.notify    - Send notifications (default: true)

source "$(dirname "$0")/common.sh"

# Initialize hook (checks override, enabled status, dry-run)
init_hook "on-pr-ready" "$@"

# Parse input
BRANCH=$(get_input "branch" "unknown")
PR_TITLE=$(get_input "pr_title" "")
PR_BODY_FILE=$(get_input "pr_body_file" "/tmp/pr-body.md")

log "info" "Creating/updating PR for branch: $BRANCH"

# Validate inputs
if [ -z "$PR_TITLE" ]; then
    log "error" "PR title is required"
    respond '{"error": "PR title is required"}'
    exit 1
fi

if [ ! -f "$PR_BODY_FILE" ]; then
    log "error" "PR body file not found: $PR_BODY_FILE"
    respond "{\"error\": \"PR body file not found: $PR_BODY_FILE\"}"
    exit 1
fi

# 1. Ensure branch is pushed (if enabled)
if hook_feature_enabled "on-pr-ready" "auto_push"; then
    git_push
fi

# Handle dry-run mode for PR operations
if is_dry_run; then
    dry_run_log "check for existing PR" "gh pr view"
    dry_run_log "create/update PR" "title='$PR_TITLE', body_file='$PR_BODY_FILE'"

    # 3. Send notification (if enabled)
    if hook_feature_enabled "on-pr-ready" "notify"; then
        notify "complete" "PR would be created/updated: $BRANCH"
    fi

    respond '{
  "action": "dry-run",
  "pr_url": "https://github.com/example/repo/pull/0",
  "pr_number": 0,
  "branch": "'"$BRANCH"'"
}'
    exit 0
fi

# 2. Check for existing PR
ACTION=""
PR_URL=""
PR_NUM=""

if gh pr view --json number,url 2>/dev/null > /tmp/pr_info.json; then
    PR_URL=$(jq -r '.url' /tmp/pr_info.json)
    PR_NUM=$(jq -r '.number' /tmp/pr_info.json)

    # Update existing PR
    gh pr edit "$PR_NUM" --title "$PR_TITLE" --body-file "$PR_BODY_FILE" >/dev/null 2>&1
    ACTION="updated"
    log "info" "Updated PR #$PR_NUM"
else
    # Create new PR
    PR_URL=$(gh pr create --base main --title "$PR_TITLE" --body-file "$PR_BODY_FILE" 2>/dev/null | tail -1)
    PR_NUM=$(gh pr view --json number -q '.number' 2>/dev/null || echo "null")
    ACTION="created"
    log "info" "Created PR #$PR_NUM"
fi

# 3. Send notification (if enabled)
if hook_feature_enabled "on-pr-ready" "notify"; then
    notify "complete" "PR $ACTION: $BRANCH - $PR_URL"
fi

# 4. Return result
cat <<EOF
{
  "action": "$ACTION",
  "pr_url": "$PR_URL",
  "pr_number": $PR_NUM,
  "branch": "$BRANCH"
}
EOF
