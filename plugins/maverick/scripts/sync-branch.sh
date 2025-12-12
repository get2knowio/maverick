#!/bin/bash
# sync-branch.sh
# Syncs current branch with origin/main and returns structured JSON
# Usage: sync-branch.sh [branch-name]
#   If branch-name is provided, switches to that branch first
#   If not provided, uses the current branch
# Returns: {"status": "ok"|"conflicts"|"error", "branch": "...", "spec_dir": "...", "tasks_file": "...", ...}

set -e

# Track if we stashed changes
STASHED=false

# Helper to output error JSON and exit
error_exit() {
    local branch="${1:-unknown}"
    local error_msg="$2"
    cat <<EOF
{
  "status": "error",
  "branch": "$branch",
  "spec_dir": "specs/$branch",
  "tasks_file": "specs/$branch/tasks.md",
  "error": "$error_msg"
}
EOF
    # Restore stashed changes if we stashed them
    if [ "$STASHED" = true ]; then
        git stash pop >/dev/null 2>&1 || true
    fi
    exit 1
}

# Validate that origin remote exists
if ! git remote get-url origin >/dev/null 2>&1; then
    error_exit "unknown" "No 'origin' remote configured"
fi

# Handle dirty working directory by stashing
if [ -n "$(git status --porcelain)" ]; then
    if ! git stash push -m "maverick-auto-stash-$(date +%s)" >/dev/null 2>&1; then
        error_exit "$(git branch --show-current 2>/dev/null || echo unknown)" "Failed to stash uncommitted changes"
    fi
    STASHED=true
fi

# If a branch argument is provided and matches the expected pattern (3 digits + hyphen), switch to it
# This prevents accidental branch switches when extra context is passed to the command
if [ -n "$1" ] && [[ "$1" =~ ^[0-9]{3}- ]]; then
    TARGET_BRANCH="$1"

    # Fetch to ensure we have latest refs (with timeout)
    if ! timeout 30 git fetch origin 2>/dev/null; then
        error_exit "$TARGET_BRANCH" "Failed to fetch from origin (network issue or timeout)"
    fi

    # Check if we need to switch branches
    CURRENT=$(git branch --show-current)
    if [ "$CURRENT" != "$TARGET_BRANCH" ]; then
        # Try to switch to the branch
        if ! git checkout "$TARGET_BRANCH" 2>/dev/null; then
            # Branch might not exist locally, try to check out from origin
            if ! git checkout -b "$TARGET_BRANCH" "origin/$TARGET_BRANCH" 2>/dev/null; then
                error_exit "$TARGET_BRANCH" "Could not switch to branch: $TARGET_BRANCH"
            fi
        fi
    fi
fi

BRANCH_NAME=$(git branch --show-current)
SPEC_DIR="specs/$BRANCH_NAME"
TASKS_FILE="$SPEC_DIR/tasks.md"

# Fetch latest (with timeout)
if ! timeout 30 git fetch origin 2>/dev/null; then
    error_exit "$BRANCH_NAME" "Failed to fetch from origin (network issue or timeout)"
fi

# Attempt rebase
if ! git rebase origin/main 2>/dev/null; then
    # Capture conflict info before aborting
    CONFLICTS=$(git diff --name-only --diff-filter=U 2>/dev/null | tr '\n' ' ')

    # Abort the failed rebase to leave repo in clean state
    git rebase --abort 2>/dev/null || true

    # Restore stashed changes
    if [ "$STASHED" = true ]; then
        git stash pop >/dev/null 2>&1 || true
        STASHED=false
    fi

    cat <<EOF
{
  "status": "conflicts",
  "branch": "$BRANCH_NAME",
  "spec_dir": "$SPEC_DIR",
  "tasks_file": "$TASKS_FILE",
  "conflicts": "$CONFLICTS",
  "suggestion": "Resolve conflicts manually, then retry. Or try: git merge origin/main"
}
EOF
    exit 1
fi

# Check if spec directory exists
if [ ! -d "$SPEC_DIR" ]; then
    error_exit "$BRANCH_NAME" "Spec directory does not exist: $SPEC_DIR"
fi

# Check if tasks file exists
if [ ! -f "$TASKS_FILE" ]; then
    error_exit "$BRANCH_NAME" "Tasks file does not exist: $TASKS_FILE"
fi

# Restore stashed changes after successful rebase
if [ "$STASHED" = true ]; then
    if ! git stash pop >/dev/null 2>&1; then
        # Stash pop failed (likely conflicts with rebased changes)
        cat <<EOF
{
  "status": "stash_conflict",
  "branch": "$BRANCH_NAME",
  "spec_dir": "$SPEC_DIR",
  "tasks_file": "$TASKS_FILE",
  "warning": "Rebase succeeded but stashed changes conflict. Run 'git stash show' and 'git stash drop' or 'git stash pop' manually."
}
EOF
        exit 1
    fi
    STASHED=false
fi

# Gather useful metadata for success response
COMMITS_AHEAD=$(git rev-list origin/main..HEAD --count 2>/dev/null || echo 0)
PENDING_TASKS=$(grep -c '^\s*- \[ \]' "$TASKS_FILE" 2>/dev/null || echo 0)
COMPLETED_TASKS=$(grep -c '^\s*- \[x\]' "$TASKS_FILE" 2>/dev/null || echo 0)

cat <<EOF
{
  "status": "ok",
  "branch": "$BRANCH_NAME",
  "spec_dir": "$SPEC_DIR",
  "tasks_file": "$TASKS_FILE",
  "commits_ahead": $COMMITS_AHEAD,
  "pending_tasks": $PENDING_TASKS,
  "completed_tasks": $COMPLETED_TASKS
}
EOF
