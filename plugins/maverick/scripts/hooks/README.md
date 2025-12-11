# Maverick Workflow Hooks

Lifecycle hooks that execute at defined points in maverick workflows (`/fly`, `/refuel`).

## Features

- **Configurable**: Enable/disable hooks and features via `hooks.json`
- **Dry-run mode**: Preview what hooks would do without making changes
- **Project-local overrides**: Customize hooks per-project
- **JSON contract**: Structured input/output for integration

## Architecture

```
hooks/
├── common.sh              # Shared utilities (config, dry-run, git helpers)
├── hooks.json.example     # Example configuration file
├── on-phase-complete.sh   # After each tasks.md phase completes
├── on-implementation-done.sh  # After all tasks complete
├── on-review-done.sh      # After code review phase
├── on-validation-done.sh  # After validation phase
├── on-pr-ready.sh         # When PR is created/updated
└── on-workflow-end.sh     # At workflow completion (cleanup)
```

## Quick Start

### Test a hook with dry-run

```bash
# See what on-phase-complete would do
echo '{"phase": 1, "branch": "test", "clean_cmd": "make clean"}' | \
  ./on-phase-complete.sh --dry-run
```

### Customize for your project

```bash
# Copy example config to your project
mkdir -p .maverick
cp /opt/maverick/plugins/maverick/scripts/hooks/hooks.json.example .maverick/hooks.json

# Edit to customize
vim .maverick/hooks.json
```

## Configuration

### hooks.json

Create `.maverick/hooks.json` in your project root to customize behavior:

```json
{
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
    }
  },
  "notifications": {
    "enabled": true
  },
  "git": {
    "auto_commit": true,
    "auto_push": true,
    "force_with_lease": true
  }
}
```

### Config Locations (in priority order)

1. `{project}/.maverick/hooks.json` - Project-local config
2. `{plugin}/scripts/hooks/hooks.json` - Plugin default config
3. Built-in defaults - If no config file found

### Hook-Specific Options

| Hook | Option | Default | Description |
|------|--------|---------|-------------|
| `on-phase-complete` | `enabled` | `true` | Enable/disable hook |
| | `run_clean` | `true` | Run clean command between phases |
| | `notify` | `true` | Send notifications |
| `on-implementation-done` | `enabled` | `true` | Enable/disable hook |
| | `auto_commit` | `true` | Auto-commit implementation changes |
| | `auto_push` | `true` | Auto-push after commit |
| | `notify` | `true` | Send notifications |
| `on-review-done` | `enabled` | `true` | Enable/disable hook |
| | `auto_commit` | `true` | Auto-commit review fixes |
| | `auto_push` | `true` | Auto-push after commit |
| | `notify` | `true` | Send notifications |
| `on-validation-done` | `enabled` | `true` | Enable/disable hook |
| | `auto_commit` | `true` | Auto-commit validation fixes |
| | `auto_push` | `true` | Auto-push after commit |
| | `notify` | `true` | Send notifications |
| `on-pr-ready` | `enabled` | `true` | Enable/disable hook |
| | `auto_push` | `true` | Push before creating PR |
| | `notify` | `true` | Send notifications |
| `on-workflow-end` | `enabled` | `true` | Enable/disable hook |
| | `cleanup_marker` | `true` | Remove workflow marker file |
| | `cleanup_temp_files` | `true` | Remove temp files |
| | `notify` | `true` | Send notifications |

### Global Options

| Section | Option | Default | Description |
|---------|--------|---------|-------------|
| `notifications` | `enabled` | `true` | Master switch for all notifications |
| `git` | `auto_commit` | `true` | Allow auto-commits globally |
| | `auto_push` | `true` | Allow auto-push globally |
| | `force_with_lease` | `true` | Use `--force-with-lease` on push failure |

## Dry-Run Mode

Preview what hooks would do without making any changes:

```bash
# Via command line flag
echo '{"branch": "test"}' | ./on-implementation-done.sh --dry-run

# Via environment variable
MAVERICK_DRY_RUN=1 echo '{"branch": "test"}' | ./on-implementation-done.sh
```

**Dry-run output:**
```
[2024-01-15 10:30:00] [info] [DRY-RUN] Running hook 'on-implementation-done' in dry-run mode
[2024-01-15 10:30:00] [info] [DRY-RUN] Implementation complete: 0 tasks on branch test
[DRY-RUN] Would git add -A && git commit: feat(test): implement spec tasks
[DRY-RUN] Would git push: origin test
[DRY-RUN] Would send notification: implementation_done: Implementation complete: test (0 tasks)
{"continue": true, "commit_sha": "dry-run", "message": "Implementation committed", "dry_run": true}
```

## Hook Contract

Each hook:
1. **Receives** JSON on stdin with context
2. **Performs** its actions (respecting config and dry-run)
3. **Returns** JSON on stdout with results
4. **Exit code**: 0 = continue, non-zero = halt workflow

## Input/Output Examples

### on-phase-complete.sh

**Input:**
```json
{
  "phase": 2,
  "phase_name": "Core Implementation",
  "tasks_completed": 5,
  "tasks_remaining": 3,
  "total_phases": 4,
  "branch": "008-up-lifecycle-hooks",
  "clean_cmd": "make clean"
}
```

**Output:**
```json
{
  "continue": true,
  "message": "Phase 2 complete"
}
```

### on-implementation-done.sh

**Input:**
```json
{
  "branch": "008-up-lifecycle-hooks",
  "spec_dir": "specs/008-up-lifecycle-hooks",
  "total_tasks": 15,
  "phases_completed": 4
}
```

**Output:**
```json
{
  "continue": true,
  "commit_sha": "abc123",
  "message": "Implementation committed"
}
```

### on-review-done.sh

**Input:**
```json
{
  "branch": "008-up-lifecycle-hooks",
  "review_summary": {
    "coderabbit_issues": 5,
    "architecture_issues": 3,
    "total_unique": 7,
    "issues_fixed": 6,
    "issues_deferred": 1
  }
}
```

### on-validation-done.sh

**Input:**
```json
{
  "branch": "008-up-lifecycle-hooks",
  "validation_result": {
    "all_passed": true,
    "iterations": 2
  },
  "fixes_applied": 3
}
```

### on-pr-ready.sh

**Input:**
```json
{
  "branch": "008-up-lifecycle-hooks",
  "pr_title": "feat(008-up-lifecycle-hooks): implement lifecycle hooks",
  "pr_body_file": "/tmp/pr-body.md"
}
```

**Output:**
```json
{
  "action": "created",
  "pr_url": "https://github.com/org/repo/pull/123",
  "pr_number": 123
}
```

### on-workflow-end.sh

**Input:**
```json
{
  "workflow": "fly",
  "branch": "008-up-lifecycle-hooks",
  "status": "success",
  "pr_url": "https://github.com/org/repo/pull/123"
}
```

## Project-Local Hook Overrides

Override specific hooks for your project:

```bash
mkdir -p .maverick/hooks
cp /opt/maverick/plugins/maverick/scripts/hooks/on-phase-complete.sh .maverick/hooks/
chmod +x .maverick/hooks/on-phase-complete.sh
# Edit to customize
```

The hook will automatically use your local version.

## Customization Examples

### Disable auto-push (manual review before push)

`.maverick/hooks.json`:
```json
{
  "git": {
    "auto_push": false
  }
}
```

### Disable notifications

`.maverick/hooks.json`:
```json
{
  "notifications": {
    "enabled": false
  }
}
```

### Skip clean between phases

`.maverick/hooks.json`:
```json
{
  "hooks": {
    "on-phase-complete": {
      "run_clean": false
    }
  }
}
```

### Add Slack notification on completion

Create `.maverick/hooks/on-workflow-end.sh`:
```bash
#!/bin/bash
source "$(dirname "$0")/common.sh"

init_hook "on-workflow-end" "$@"

STATUS=$(get_input "status")
BRANCH=$(get_input "branch")
PR_URL=$(get_input "pr_url")

# Custom: Slack webhook
if [ -n "$SLACK_WEBHOOK_URL" ]; then
    if is_dry_run; then
        dry_run_log "send Slack message" "$STATUS: $BRANCH"
    else
        curl -X POST "$SLACK_WEBHOOK_URL" \
            -H "Content-Type: application/json" \
            -d "{\"text\": \"Workflow $STATUS: $BRANCH - $PR_URL\"}"
    fi
fi

# Continue with default cleanup
if hook_feature_enabled "on-workflow-end" "cleanup_marker"; then
    if ! is_dry_run; then
        rm -f /tmp/maverick-workflow-active
    fi
fi

respond '{"cleanup_done": true}'
```

### Add metrics logging

Create `.maverick/hooks/on-phase-complete.sh`:
```bash
#!/bin/bash
source "$(dirname "$0")/common.sh"

init_hook "on-phase-complete" "$@"

PHASE=$(get_input "phase")
BRANCH=$(get_input "branch")

# Custom: Log to metrics service
if [ -n "$METRICS_URL" ]; then
    if is_dry_run; then
        dry_run_log "post metrics" "phase=$PHASE, branch=$BRANCH"
    else
        curl -X POST "$METRICS_URL/events" \
            -H "Content-Type: application/json" \
            -d "$(read_input)" || true
    fi
fi

# Run default behavior
if hook_feature_enabled "on-phase-complete" "run_clean"; then
    run_clean "$(get_input 'clean_cmd')"
fi

if hook_feature_enabled "on-phase-complete" "notify"; then
    notify "phase_complete" "Phase $PHASE complete ($BRANCH)"
fi

respond '{"continue": true}'
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `MAVERICK_DRY_RUN` | Set to `1` or `true` to enable dry-run mode |
| `NTFY_TOPIC` | ntfy.sh topic for notifications |
| `NTFY_SERVER` | Custom ntfy server (default: ntfy.sh) |
| `METRICS_URL` | Custom metrics endpoint (optional) |
| `SLACK_WEBHOOK_URL` | Slack webhook (optional) |

## common.sh Utilities

Source `common.sh` to get these helpers:

| Function | Description |
|----------|-------------|
| `init_hook "name" "$@"` | Initialize hook (check override, enabled, dry-run) |
| `get_input "key"` | Get value from input JSON |
| `read_input` | Get full input JSON |
| `config_get "path" "default"` | Get config value by path |
| `hook_enabled "name"` | Check if hook is enabled |
| `hook_feature_enabled "name" "feature"` | Check if hook feature is enabled |
| `is_dry_run` | Check if running in dry-run mode |
| `dry_run_log "action" "details"` | Log dry-run action |
| `notify "event" "msg"` | Send ntfy notification |
| `log "level" "msg"` | Log with timestamp |
| `run_clean "cmd"` | Execute clean command safely |
| `git_commit "msg"` | Stage all and commit (respects config) |
| `git_push` | Push with fallback (respects config) |
| `respond '{"json": ...}'` | Output response JSON |

## Testing

```bash
# Test all hooks with dry-run
for hook in on-phase-complete on-implementation-done on-review-done \
            on-validation-done on-pr-ready on-workflow-end; do
    echo "=== Testing $hook ==="
    echo '{"branch": "test", "phase": 1}' | "./$hook.sh" --dry-run
    echo
done
```
