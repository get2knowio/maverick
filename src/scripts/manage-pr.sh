#!/bin/bash
# manage-pr.sh
# Creates or updates a PR with the given title and body
# Usage: manage-pr.sh "title" "body_file"
# The body is read from a file to handle multi-line content safely
# Returns: {"action": "created"|"updated", "url": "..."}

set -e

TITLE="$1"
BODY_FILE="$2"

if [ -z "$TITLE" ] || [ -z "$BODY_FILE" ]; then
    echo '{"error": "Usage: manage-pr.sh \"title\" \"body_file\""}' >&2
    exit 1
fi

if [ ! -f "$BODY_FILE" ]; then
    echo "{\"error\": \"Body file not found: $BODY_FILE\"}" >&2
    exit 1
fi

BRANCH=$(git branch --show-current)

# Ensure we have commits to push
if ! git rev-parse HEAD >/dev/null 2>&1; then
    echo '{"error": "No commits to push"}' >&2
    exit 1
fi

# Push the branch
if ! git push -u origin "$BRANCH" 2>/dev/null; then
    # Force push if needed (rebase may have rewritten history)
    git push -u origin "$BRANCH" --force-with-lease 2>/dev/null || true
fi

# Check for existing PR
if gh pr view --json number,url 2>/dev/null > /tmp/pr_info.json; then
    PR_URL=$(jq -r '.url' /tmp/pr_info.json)
    PR_NUM=$(jq -r '.number' /tmp/pr_info.json)

    # Update existing PR
    gh pr edit "$PR_NUM" --title "$TITLE" --body-file "$BODY_FILE" >/dev/null 2>&1

    cat <<EOF
{
  "action": "updated",
  "url": "$PR_URL",
  "number": $PR_NUM,
  "branch": "$BRANCH"
}
EOF
else
    # Create new PR
    PR_URL=$(gh pr create --base main --title "$TITLE" --body-file "$BODY_FILE" 2>/dev/null | tail -1)
    PR_NUM=$(gh pr view --json number -q '.number' 2>/dev/null || echo "null")

    cat <<EOF
{
  "action": "created",
  "url": "$PR_URL",
  "number": $PR_NUM,
  "branch": "$BRANCH"
}
EOF
fi
