---
layout: section
---

# Part 8: CLI & Configuration

Command-line interface and configuration system

---
layout: default
---

# CLI Commands

<div class="grid grid-cols-2 gap-4">

<div>

## Global Options

```bash
# Override config file
maverick --config/-c <path>

# Increase verbosity (-vvv for max)
maverick --verbose/-v

# Suppress non-essential output
maverick --quiet/-q

# Headless mode (no TUI)
maverick --no-tui
```

</div>

<div>

## Main Commands

```bash
# Run FlyWorkflow
maverick fly <branch-name>

# Run RefuelWorkflow
maverick refuel --label tech-debt

# Review PR #123
maverick review 123

# Config management
maverick config init|show|edit|validate

# Current branch, pending tasks
maverick status

# Workflow management
maverick workflow list|run
```

</div>

</div>

<div v-click class="mt-8">

### Example Usage

```bash
# Start a feature workflow with verbose output
maverick -vv fly feature/add-caching

# Run tech-debt workflow in headless mode
maverick --no-tui refuel --label tech-debt

# Validate custom config
maverick -c ./custom-config.yaml config validate
```

</div>

---
layout: default
---

# Configuration System

## Priority Order (highest to lowest)

<div v-click>

1. **Environment variables** (`MAVERICK_*`)
2. **Project config** (`./maverick.yaml`)
3. **User config** (`~/.config/maverick/config.yaml`)
4. **Built-in defaults**

</div>

<div class="grid grid-cols-2 gap-4 mt-6">

<div v-click>

## Example maverick.yaml

```yaml
github:
  owner: your-org
  repo: your-repo

model:
  model_id: claude-sonnet-4-20250514
  max_tokens: 8192
  temperature: 0.0

validation:
  format_cmd: ["ruff", "format", "."]
  lint_cmd: ["ruff", "check", "--fix", "."]
  test_cmd: ["pytest", "-v"]

parallel:
  max_agents: 3
  max_tasks: 5
```

</div>

<div v-click>

## Environment Overrides

```bash
# Override model
export MAVERICK_MODEL_ID=claude-opus-4-5-20251101

# Override GitHub settings
export MAVERICK_GITHUB_OWNER=my-org
export MAVERICK_GITHUB_REPO=my-repo

# Disable parallel execution
export MAVERICK_PARALLEL_MAX_AGENTS=1

# Then run
maverick fly feature/new-feature
```

</div>

</div>

<div v-click class="mt-6">

### Config Management

```bash
# Initialize user config with interactive prompts
maverick config init

# Show merged configuration (all sources)
maverick config show

# Edit user config in $EDITOR
maverick config edit

# Validate configuration and show errors
maverick config validate
```

</div>
