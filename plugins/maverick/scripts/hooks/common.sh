#!/bin/bash
# common.sh - Shared utilities for maverick hooks
# Source this file in hooks: source "$(dirname "$0")/common.sh"
#
# Features:
#   - Config loading from hooks.json
#   - Dry-run mode (--dry-run or MAVERICK_DRY_RUN=1)
#   - Project-local hook overrides
#   - JSON input/output helpers

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOKS_DIR="$SCRIPT_DIR"
SCRIPTS_DIR="$(dirname "$SCRIPT_DIR")"

# =============================================================================
# Dry-run mode
# =============================================================================

# Check for --dry-run flag in arguments or environment
DRY_RUN="${MAVERICK_DRY_RUN:-false}"
for arg in "$@"; do
    if [ "$arg" = "--dry-run" ]; then
        DRY_RUN="true"
    fi
done

is_dry_run() {
    [ "$DRY_RUN" = "true" ] || [ "$DRY_RUN" = "1" ]
}

# Log what would happen in dry-run mode
dry_run_log() {
    local action="$1"
    local details="$2"
    if is_dry_run; then
        echo "[DRY-RUN] Would $action: $details" >&2
    fi
}

# =============================================================================
# Project root detection
# =============================================================================

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

# =============================================================================
# Configuration loading
# =============================================================================

# Default config (used if no hooks.json found)
_DEFAULT_CONFIG='{
  "hooks": {
    "on-phase-complete": {
      "enabled": true,
      "run_clean": true,
      "notify": true
    },
    "on-implementation-done": {
      "enabled": true,
      "auto_commit": true,
      "auto_push": true,
      "notify": true
    },
    "on-review-done": {
      "enabled": true,
      "auto_commit": true,
      "auto_push": true,
      "notify": true
    },
    "on-validation-done": {
      "enabled": true,
      "auto_commit": true,
      "auto_push": true,
      "notify": true
    },
    "on-pr-ready": {
      "enabled": true,
      "auto_push": true,
      "notify": true
    },
    "on-workflow-end": {
      "enabled": true,
      "cleanup_marker": true,
      "cleanup_temp_files": true,
      "notify": true
    }
  },
  "notifications": {
    "enabled": true,
    "on_phase_complete": true,
    "on_implementation_done": true,
    "on_review_done": true,
    "on_validation_done": true,
    "on_pr_ready": true,
    "on_workflow_end": true
  },
  "git": {
    "auto_commit": true,
    "auto_push": true,
    "force_with_lease": true
  }
}'

# Load config from hooks.json (project-local or plugin default)
_load_config() {
    local config_file=""

    # Check project-local config first
    if [ -f "${PROJECT_ROOT}/.maverick/hooks.json" ]; then
        config_file="${PROJECT_ROOT}/.maverick/hooks.json"
    # Then check plugin config
    elif [ -f "${HOOKS_DIR}/hooks.json" ]; then
        config_file="${HOOKS_DIR}/hooks.json"
    fi

    if [ -n "$config_file" ] && [ -f "$config_file" ]; then
        # Merge with defaults (config file overrides defaults)
        echo "$_DEFAULT_CONFIG" | jq -s '.[0] * .[1]' - "$config_file" 2>/dev/null || echo "$_DEFAULT_CONFIG"
    else
        echo "$_DEFAULT_CONFIG"
    fi
}

# Cache loaded config
_HOOK_CONFIG=""
get_config() {
    if [ -z "$_HOOK_CONFIG" ]; then
        _HOOK_CONFIG=$(_load_config)
    fi
    echo "$_HOOK_CONFIG"
}

# Get a config value by path (e.g., "hooks.on-phase-complete.enabled")
# Handles keys with hyphens by converting dot notation to bracket notation
config_get() {
    local path="$1"
    local default="${2:-}"

    # Convert dot path to jq bracket notation for keys with special chars
    # e.g., "hooks.on-phase-complete.enabled" -> '.hooks["on-phase-complete"]["enabled"]'
    local jq_path
    jq_path=$(echo "$path" | sed 's/\./"]["/g' | sed 's/^/.["/' | sed 's/$/"]/')

    local value
    value=$(echo "$(get_config)" | jq -r "$jq_path" 2>/dev/null)

    # Handle null (key not found) - use default
    if [ "$value" = "null" ]; then
        echo "$default"
    # Handle actual values including "false", "0", empty strings that are intentional
    else
        echo "$value"
    fi
}

# Check if a hook is enabled
hook_enabled() {
    local hook_name="$1"
    local enabled
    enabled=$(config_get "hooks.${hook_name}.enabled" "true")
    [ "$enabled" = "true" ]
}

# Check if a specific hook feature is enabled
hook_feature_enabled() {
    local hook_name="$1"
    local feature="$2"
    local default="${3:-true}"
    local enabled
    enabled=$(config_get "hooks.${hook_name}.${feature}" "$default")
    [ "$enabled" = "true" ]
}

# =============================================================================
# Input/Output helpers
# =============================================================================

# Cache for stdin input - must be read once at hook start
_HOOK_INPUT=""

# Read and cache JSON input from stdin
# MUST be called once at the start of each hook before any get_input calls
read_hook_input() {
    if [ -z "$_HOOK_INPUT" ]; then
        _HOOK_INPUT=$(cat)
    fi
}

# Get the cached input (for use after read_hook_input)
get_raw_input() {
    echo "$_HOOK_INPUT"
}

# Legacy function for backwards compatibility
read_input() {
    get_raw_input
}

# Get a value from the input JSON
# Supports dot notation for nested keys (e.g., "review_summary.total_unique")
# IMPORTANT: read_hook_input must be called first!
get_input() {
    local key="$1"
    local default="${2:-}"

    # Convert dot path to jq bracket notation for robustness
    local jq_path
    jq_path=$(echo "$key" | sed 's/\./"]["/g' | sed 's/^/.["/' | sed 's/$/"]/')

    local value
    value=$(echo "$_HOOK_INPUT" | jq -r "$jq_path // \"$default\"" 2>/dev/null)
    if [ "$value" = "null" ] || [ -z "$value" ]; then
        echo "$default"
    else
        echo "$value"
    fi
}

# Output JSON response (for hooks that need to communicate back)
respond() {
    local json="$1"
    if is_dry_run; then
        # Add dry_run flag to response
        echo "$json" | jq '. + {"dry_run": true}' 2>/dev/null || echo "$json"
    else
        echo "$json"
    fi
}

# =============================================================================
# Logging
# =============================================================================

log() {
    local level="${1:-info}"
    local message="$2"
    local prefix=""
    if is_dry_run; then
        prefix="[DRY-RUN] "
    fi
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [$level] ${prefix}$message" >&2
}

# =============================================================================
# Notifications
# =============================================================================

# Send notification via notify.sh (respects config)
notify() {
    local event_type="$1"
    local message="$2"

    # Check global notifications enabled
    if [ "$(config_get 'notifications.enabled' 'true')" != "true" ]; then
        log "debug" "Notifications disabled globally, skipping"
        return 0
    fi

    if is_dry_run; then
        dry_run_log "send notification" "$event_type: $message"
        return 0
    fi

    "$SCRIPTS_DIR/notify.sh" "$event_type" "$message"
}

# =============================================================================
# Hook override support
# =============================================================================

# Check for project-local hook override
# Usage: check_override "$0" "$@" && exit 0
check_override() {
    local hook_script="$1"
    shift
    local hook_name
    hook_name=$(basename "$hook_script")
    local project_hook="${PROJECT_ROOT}/.maverick/hooks/${hook_name}"

    if [ -x "$project_hook" ]; then
        log "info" "Using project-local hook: $project_hook"
        exec "$project_hook" "$@"
    fi
}

# =============================================================================
# Clean command support
# =============================================================================

# Safe eval of clean command (respects dry-run)
run_clean() {
    local clean_cmd="$1"
    if [ -n "$clean_cmd" ] && [ "$clean_cmd" != "null" ]; then
        if is_dry_run; then
            dry_run_log "run clean command" "$clean_cmd"
            return 0
        fi
        log "info" "Running clean command: $clean_cmd"
        eval "$clean_cmd" 2>&1 || log "warn" "Clean command failed (continuing anyway)"
    fi
}

# =============================================================================
# Git helpers (respect dry-run and config)
# =============================================================================

git_commit() {
    local message="$1"

    if [ -z "$(git status --porcelain)" ]; then
        log "info" "No changes to commit"
        return 0
    fi

    # Check if auto_commit is enabled in config
    if [ "$(config_get 'git.auto_commit' 'true')" != "true" ]; then
        log "info" "Auto-commit disabled in config, skipping"
        return 0
    fi

    if is_dry_run; then
        dry_run_log "git add -A && git commit" "$message"
        return 0
    fi

    git add -A
    git commit -m "$message

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
}

git_push() {
    # Check if auto_push is enabled in config
    if [ "$(config_get 'git.auto_push' 'true')" != "true" ]; then
        log "info" "Auto-push disabled in config, skipping"
        return 0
    fi

    local branch
    branch=$(git branch --show-current)

    if is_dry_run; then
        dry_run_log "git push" "origin $branch"
        return 0
    fi

    local use_force_lease
    use_force_lease=$(config_get 'git.force_with_lease' 'true')

    if git push -u origin "$branch" 2>/dev/null; then
        return 0
    elif [ "$use_force_lease" = "true" ]; then
        git push -u origin "$branch" --force-with-lease 2>/dev/null || \
            log "warn" "Push failed"
    else
        log "warn" "Push failed (force-with-lease disabled)"
    fi
}

# =============================================================================
# Hook entry point helper
# =============================================================================

# Call at the start of each hook to handle common setup
# Usage: init_hook "on-phase-complete" "$@"
# Note: Must be called from the hook script, not sourced indirectly
# This function:
#   1. Reads and caches stdin (JSON input)
#   2. Checks for project-local override
#   3. Checks if hook is enabled in config
#   4. Logs dry-run mode if active
init_hook() {
    local hook_name="$1"
    shift

    # FIRST: Read stdin and cache it (must happen before any get_input calls)
    read_hook_input

    # Check for project-local override (use $0 from caller's context)
    local caller_script="${HOOKS_DIR}/${hook_name}.sh"
    check_override "$caller_script" "$@"

    # Check if hook is enabled
    if ! hook_enabled "$hook_name"; then
        log "info" "Hook '$hook_name' is disabled in config"
        respond '{"skipped": true, "reason": "disabled in config"}'
        exit 0
    fi

    if is_dry_run; then
        log "info" "Running hook '$hook_name' in dry-run mode"
    fi
}
