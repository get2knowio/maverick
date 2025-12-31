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

## Setup Commands

```bash
# Initialize project configuration
# Uses Claude to detect project type and
# generate smart maverick.yaml
maverick init

# Override project type detection
maverick init --type python

# Remove maverick skills and config
maverick uninstall
maverick uninstall --config
```

</div>

<div>

## Workflow Commands

```bash
# Execute any workflow
maverick fly <workflow> [inputs]

# Feature implementation (tasks.md → PR)
maverick fly feature -i branch_name=001-foo

# Tech-debt cleanup
maverick fly cleanup -i label=tech-debt

# Workflow management
maverick workflow list
maverick workflow show <name>
maverick workflow viz <name>
```

</div>

</div>

<div v-click class="mt-8">

### Example Usage

```bash
# Build feature with verbose output
maverick -v fly feature -i branch_name=025-add-caching

# Preview workflow without executing (dry-run)
maverick fly feature -i branch_name=025-foo --dry-run

# Resume from checkpoint after interruption
maverick fly feature --resume
```

</div>

---
layout: default
---

# Project Initialization

`maverick init` uses Claude to intelligently configure your project

<div class="grid grid-cols-2 gap-6 mt-6">

<div v-click>

## What Init Does

1. **Prerequisites Check** - Verifies git, gh CLI, API key
2. **Project Detection** - Uses Claude to analyze project structure
3. **Config Generation** - Creates smart `maverick.yaml`
4. **Command Validation** - Verifies validation commands exist
5. **Skills Installation** - Copies relevant skills to `~/.claude/skills/`

</div>

<div v-click>

## Project Types Detected

- **Python** - pyproject.toml, setup.py, requirements.txt
- **Node.js** - package.json
- **Go** - go.mod
- **Rust** - Cargo.toml
- **Ansible Collection** - galaxy.yml
- **Ansible Playbook** - playbooks/*.yml

</div>

</div>

<div v-click class="mt-6">

```bash
# Auto-detect with Claude (recommended)
maverick init

# Override detection
maverick init --type python

# Use marker-only detection (no Claude)
maverick init --no-detect

# Overwrite existing config
maverick init --force
```

</div>

---
layout: default
---

# Skills System

Pre-packaged best practices that enhance Claude's guidance

<div class="grid grid-cols-2 gap-4 mt-4">

<div v-click>

## What Are Skills?

Markdown files in `~/.claude/skills/` providing:

- Best practices for technologies
- Code review guidelines
- Pattern references (good/bad examples)
- Trigger keywords for auto-activation

</div>

<div v-click>

## Available Skills

| Language | Skills |
|----------|--------|
| Python | testing, async, typing, security |
| Rust | ownership, async, errors |
| Ansible | playbook best practices |

</div>

</div>

<div v-click class="mt-4 p-2 bg-blue-500/20 border border-blue-500 rounded text-sm">

Skills are installed per-project based on detected type. Use `maverick uninstall` to remove.

</div>

---
layout: default
---

# Configuration System

<div class="grid grid-cols-2 gap-4">

<div>

## Priority Order

1. Environment (`MAVERICK_*`)
2. Project (`./maverick.yaml`)
3. User (`~/.config/maverick/config.yaml`)
4. Built-in defaults

<div v-click class="mt-4">

## Example maverick.yaml

```yaml
github:
  owner: your-org
  repo: your-repo
model:
  model_id: claude-sonnet-4-20250514
validation:
  format_cmd: ["ruff", "format", "."]
  lint_cmd: ["ruff", "check", "--fix", "."]
parallel:
  max_agents: 3
```

</div>

</div>

<div>

<div v-click>

## Environment Overrides

```bash
export MAVERICK_MODEL_ID=claude-opus-4-5-20251101
export MAVERICK_GITHUB_OWNER=my-org
export MAVERICK_PARALLEL_MAX_AGENTS=1
```

</div>

<div v-click class="mt-4">

## Config Commands

```bash
maverick config init     # Interactive setup
maverick config show     # Merged config
maverick config edit     # Edit in $EDITOR
maverick config validate # Check errors
```

</div>

</div>

</div>
