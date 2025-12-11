#!/bin/bash
# on-phase-complete.sh - Called after each tasks.md phase completes
#
# Usage: echo '{"phase": 1, ...}' | ./on-phase-complete.sh [--dry-run]
#
# Input JSON (stdin):
# {
#   "phase": 2,
#   "phase_name": "Core Implementation",
#   "tasks_completed": 5,
#   "tasks_remaining": 3,
#   "total_phases": 4,
#   "spec_dir": "specs/008-up-lifecycle-hooks",
#   "branch": "008-up-lifecycle-hooks",
#   "clean_cmd": "make clean"
# }
#
# Output JSON (stdout):
# {
#   "continue": true,
#   "message": "Phase 2 complete, cleaned build artifacts"
# }
#
# Config options (hooks.json):
#   hooks.on-phase-complete.enabled    - Enable/disable this hook (default: true)
#   hooks.on-phase-complete.run_clean  - Run clean command between phases (default: true)
#   hooks.on-phase-complete.notify     - Send notifications (default: true)

source "$(dirname "$0")/common.sh"

# Initialize hook (checks override, enabled status, dry-run)
init_hook "on-phase-complete" "$@"

# Parse input
PHASE=$(get_input "phase" "0")
PHASE_NAME=$(get_input "phase_name" "Unknown")
TASKS_COMPLETED=$(get_input "tasks_completed" "0")
TASKS_REMAINING=$(get_input "tasks_remaining" "0")
TOTAL_PHASES=$(get_input "total_phases" "1")
BRANCH=$(get_input "branch" "unknown")
CLEAN_CMD=$(get_input "clean_cmd" "")

log "info" "Phase $PHASE ($PHASE_NAME) complete: $TASKS_COMPLETED tasks done, $TASKS_REMAINING remaining"

# 1. Run clean command between phases (if enabled and more tasks remain)
if hook_feature_enabled "on-phase-complete" "run_clean" && [ "$TASKS_REMAINING" -gt 0 ]; then
    run_clean "$CLEAN_CMD"
fi

# 2. Send notification (if enabled)
if hook_feature_enabled "on-phase-complete" "notify"; then
    notify "phase_complete" "Phase $PHASE/$TOTAL_PHASES complete: $PHASE_NAME ($BRANCH)"
fi

# 3. Return continue signal
respond '{"continue": true, "message": "Phase '"$PHASE"' complete"}'
