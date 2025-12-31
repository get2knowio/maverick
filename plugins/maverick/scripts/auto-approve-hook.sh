#!/bin/bash
# Auto-approve hook for maverick workflows
# This hook approves all tool uses when running under maverick fly/refuel commands
# and sends a notification for each NEW approval (deduped by signature)
#
# Only activates when MAVERICK_WORKFLOW marker file exists (created by /fly or /refuel)

SCRIPT_DIR="$(dirname "$0")"
MARKER_FILE="/tmp/maverick-workflow-active"

# Check if we're in a maverick workflow
if [ ! -f "$MARKER_FILE" ]; then
    # Not in a maverick workflow - don't auto-approve, let normal flow handle it
    exit 0
fi

# Find the project root (look for .git in current dir or parents)
find_project_root() {
    local dir="$PWD"
    while [ "$dir" != "/" ]; do
        if [ -d "$dir/.git" ]; then
            echo "$dir"
            return 0
        fi
        dir="$(dirname "$dir")"
    done
    echo "$PWD"
}

PROJECT_ROOT="$(find_project_root)"

# Find the current feature spec directory
# 1. Try to match from git branch name (e.g., 008-up-lifecycle-hooks)
# 2. Fall back to most recently modified spec directory
find_current_spec_dir() {
    # Check multiple possible spec directory locations
    local specs_dir=""
    for candidate in "$PROJECT_ROOT/specs" "$PROJECT_ROOT/docs/subcommand-specs"; do
        if [ -d "$candidate" ]; then
            specs_dir="$candidate"
            break
        fi
    done

    # If no specs directory exists, fall back to .specify
    if [ -z "$specs_dir" ] || [ ! -d "$specs_dir" ]; then
        specs_dir="$PROJECT_ROOT/.specify"
        if [ -d "$specs_dir" ]; then
            echo "$specs_dir"
        else
            echo "$PROJECT_ROOT"
        fi
        return 0
    fi

    # Try to get spec number from branch name
    local branch=$(git -C "$PROJECT_ROOT" branch --show-current 2>/dev/null)
    if [ -n "$branch" ]; then
        # Extract spec number pattern (e.g., "008" from "008-up-lifecycle-hooks" or "refuel/008-...")
        local spec_num=$(echo "$branch" | grep -oE '[0-9]{3}' | head -1)
        if [ -n "$spec_num" ]; then
            # Find matching spec directory
            local matching_dir=$(find "$specs_dir" -maxdepth 1 -type d -name "${spec_num}-*" 2>/dev/null | head -1)
            if [ -n "$matching_dir" ] && [ -d "$matching_dir" ]; then
                echo "$matching_dir"
                return 0
            fi
        fi
    fi

    # Fall back to most recently modified spec directory
    local latest_spec=$(ls -td "$specs_dir"/*/ 2>/dev/null | head -1)
    if [ -n "$latest_spec" ]; then
        echo "$latest_spec"
    else
        echo "$specs_dir"
    fi
}

SPEC_DIR="$(find_current_spec_dir)"
APPROVALS_LOG="$SPEC_DIR/MAVERICK_APPROVALS.md"

# Read the tool input from stdin (JSON with tool_name and tool_input)
INPUT=$(cat)

# Extract tool name
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // "unknown"' 2>/dev/null || echo "unknown")

# Extract context based on tool type
extract_context() {
    local tool="$1"
    local input="$2"

    case "$tool" in
        Bash)
            echo "$input" | jq -r '.tool_input.command // ""' 2>/dev/null | head -c 200
            ;;
        Read|Write)
            echo "$input" | jq -r '.tool_input.file_path // ""' 2>/dev/null
            ;;
        Edit)
            local file=$(echo "$input" | jq -r '.tool_input.file_path // ""' 2>/dev/null)
            local old=$(echo "$input" | jq -r '.tool_input.old_string // ""' 2>/dev/null | head -c 50)
            echo "$file: ${old}..."
            ;;
        Grep)
            local pattern=$(echo "$input" | jq -r '.tool_input.pattern // ""' 2>/dev/null)
            local path=$(echo "$input" | jq -r '.tool_input.path // "."' 2>/dev/null)
            echo "pattern='$pattern' in $path"
            ;;
        Glob)
            echo "$input" | jq -r '.tool_input.pattern // ""' 2>/dev/null
            ;;
        WebFetch)
            echo "$input" | jq -r '.tool_input.url // ""' 2>/dev/null
            ;;
        WebSearch)
            echo "$input" | jq -r '.tool_input.query // ""' 2>/dev/null
            ;;
        Task)
            local desc=$(echo "$input" | jq -r '.tool_input.description // ""' 2>/dev/null)
            local agent=$(echo "$input" | jq -r '.tool_input.subagent_type // ""' 2>/dev/null)
            echo "$agent: $desc"
            ;;
        *)
            # For other tools, try to get a summary of tool_input
            echo "$input" | jq -r '.tool_input | keys | join(", ")' 2>/dev/null || echo ""
            ;;
    esac
}

CONTEXT=$(extract_context "$TOOL_NAME" "$INPUT")

# Create approval signature (tool + context for deduplication)
if [ -n "$CONTEXT" ]; then
    APPROVAL_MSG="$TOOL_NAME: $CONTEXT"
else
    APPROVAL_MSG="$TOOL_NAME"
fi

# Truncate very long messages for the signature
SIGNATURE=$(echo "$APPROVAL_MSG" | head -c 300 | tr '\n' ' ')

# Initialize log file if it doesn't exist
if [ ! -f "$APPROVALS_LOG" ]; then
    cat > "$APPROVALS_LOG" << 'EOF'
# Maverick Auto-Approvals Log

This file tracks tool approvals during maverick workflows.
Notifications are only sent for new (unseen) approvals.

---

EOF
fi

# Check if this approval signature already exists in the log
if grep -qF "$SIGNATURE" "$APPROVALS_LOG" 2>/dev/null; then
    # Already approved before, skip notification
    IS_NEW=false
else
    # New approval, log it and notify
    IS_NEW=true
    TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
    echo "- [$TIMESTAMP] $SIGNATURE" >> "$APPROVALS_LOG"
fi

# Only send notification for new approvals
if [ "$IS_NEW" = true ]; then
    "$SCRIPT_DIR/notify.sh" permission "Auto-approved: $APPROVAL_MSG"
fi

# Always approve - maverick workflows are trusted
echo '{"decision": "approve"}'
