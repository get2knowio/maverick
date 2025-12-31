# CLI Interface Contract

**Feature**: 014-cli-entry-point
**Date**: 2025-12-17
**Version**: 1.0.0

## Overview

This document defines the CLI interface contract for Maverick, including all commands, options, arguments, and expected behaviors.

---

## Global Options

All global options apply to every command and subcommand.

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--config` | `-c` | PATH | None | Path to config file (overrides project/user config) |
| `--verbose` | `-v` | COUNT | 0 | Increase verbosity (stackable: -v, -vv, -vvv) |
| `--quiet` | `-q` | FLAG | False | Suppress non-essential output |
| `--no-tui` | - | FLAG | False | Disable TUI mode (headless operation) |
| `--version` | - | FLAG | - | Show version and exit |
| `--help` | - | FLAG | - | Show help and exit |

### Verbosity Levels
- 0 (default): WARNING and above
- 1 (-v): INFO and above
- 2 (-vv): DEBUG and above
- 3+ (-vvv): DEBUG with trace details

### Option Precedence
When `--quiet` and `--verbose` are both specified, `--quiet` takes precedence.

---

## Commands

### 1. fly

Execute the FlyWorkflow for a feature branch.

```
maverick fly <branch-name> [OPTIONS]
```

**Arguments**:
| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `branch-name` | STRING | Yes | Feature branch to process |

**Options**:
| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--task-file` | `-t` | PATH | Auto-detect | Path to task specification file |
| `--skip-review` | - | FLAG | False | Skip code review stage |
| `--skip-pr` | - | FLAG | False | Skip PR creation stage |
| `--dry-run` | - | FLAG | False | Show planned actions without executing |

**Exit Codes**:
- 0: Workflow completed successfully
- 1: Workflow failed
- 2: Workflow partially completed (some tasks failed)
- 130: Interrupted by user (Ctrl+C)

**Examples**:
```bash
# Basic usage
maverick fly feature-123

# With custom task file
maverick fly feature-123 --task-file ./tasks.md

# Skip code review and PR creation
maverick fly feature-123 --skip-review --skip-pr

# Dry run to see planned actions
maverick fly feature-123 --dry-run

# Headless mode for CI
maverick --no-tui fly feature-123
```

---

### 2. refuel

Execute the RefuelWorkflow for tech debt resolution.

```
maverick refuel [OPTIONS]
```

**Options**:
| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--label` | `-l` | STRING | "tech-debt" | Issue label to filter by |
| `--limit` | `-n` | INT | 5 | Maximum issues to process |
| `--parallel/--sequential` | - | FLAG | --parallel | Processing mode |
| `--dry-run` | - | FLAG | False | List matching issues without processing |

**Exit Codes**:
- 0: All issues processed successfully
- 1: Workflow failed
- 2: Some issues failed to process
- 130: Interrupted by user (Ctrl+C)

**Examples**:
```bash
# Basic usage (default: tech-debt label, 5 issues)
maverick refuel

# Custom label and limit
maverick refuel --label bug --limit 3

# Sequential processing
maverick refuel --sequential

# Dry run to see matching issues
maverick refuel --dry-run

# CI-friendly output
maverick --no-tui --quiet refuel
```

---

### 3. review

Review a pull request using AI-powered analysis.

```
maverick review <pr-number> [OPTIONS]
```

**Arguments**:
| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `pr-number` | INT | Yes | Pull request number to review |

**Options**:
| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--fix/--no-fix` | - | FLAG | --no-fix | Automatically apply suggested fixes |
| `--output` | `-o` | CHOICE | tui | Output format: tui, json, markdown, text |

**Exit Codes**:
- 0: Review completed successfully
- 1: Review failed (PR not found, API error, etc.)
- 130: Interrupted by user (Ctrl+C)

**Examples**:
```bash
# Basic review
maverick review 123

# Review with auto-fix
maverick review 123 --fix

# JSON output for CI integration
maverick review 123 --output json

# Markdown output for documentation
maverick review 123 --output markdown
```

---

### 4. config

Manage Maverick configuration.

```
maverick config <subcommand> [OPTIONS]
```

#### 4.1 config show

Display current configuration.

```
maverick config show [OPTIONS]
```

**Options**:
| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--format` | `-f` | CHOICE | yaml | Output format: yaml, json |

**Exit Codes**:
- 0: Configuration displayed successfully
- 1: Error reading configuration

---

#### 4.2 config edit

Open configuration file in default editor.

```
maverick config edit [OPTIONS]
```

**Options**:
| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--user` | - | FLAG | False | Edit user config (~/.config/maverick/config.yaml) |
| `--project` | - | FLAG | True | Edit project config (./maverick.yaml) |

**Exit Codes**:
- 0: Editor opened successfully
- 1: Error opening editor or config file

---

#### 4.3 config validate

Validate configuration file.

```
maverick config validate [OPTIONS]
```

**Options**:
| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--file` | `-f` | PATH | Auto-detect | Config file to validate |

**Exit Codes**:
- 0: Configuration is valid
- 1: Configuration has validation errors

---

#### 4.4 config init

Initialize a new configuration file.

```
maverick config init [OPTIONS]
```

**Options**:
| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--force` | - | FLAG | False | Overwrite existing config file |

**Exit Codes**:
- 0: Configuration file created successfully
- 1: Error creating configuration file or file already exists

---

### 5. status

Display project status information.

```
maverick status [OPTIONS]
```

**Options**:
| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--format` | `-f` | CHOICE | text | Output format: text, json |

**Output Includes**:
- Current git branch
- Pending tasks (if task file exists)
- Recent workflow runs (from history)
- Configuration status

**Exit Codes**:
- 0: Status displayed successfully
- 1: Error (not in git repository, etc.)

**Examples**:
```bash
# Basic status
maverick status

# JSON output for scripting
maverick status --format json
```

---

## Error Handling

### Error Message Format
```
Error: <brief description>
  <detail line 1>
  <detail line 2>

Suggestion: <actionable suggestion>
```

### Common Error Scenarios

| Scenario | Message | Exit Code |
|----------|---------|-----------|
| Config file not found | "Error: Config file not found: /path/to/file" | 1 |
| Invalid config | "Error: Invalid configuration\n  Field: <field>\n  Value: <value>" | 1 |
| Branch not found | "Error: Branch 'feature-123' does not exist\nSuggestion: Create branch with 'git checkout -b feature-123'" | 1 |
| Task file not found | "Error: Task file not found: /path/to/tasks.md" | 1 |
| Git not installed | "Error: git is not installed\nSuggestion: Install from https://git-scm.com/downloads" | 1 |
| GitHub CLI not installed | "Error: GitHub CLI (gh) is not installed\nSuggestion: Install from https://cli.github.com/" | 1 |
| GitHub CLI not authenticated | "Error: GitHub CLI is not authenticated\nSuggestion: Run 'gh auth login'" | 1 |
| Not a git repository | "Error: Not a git repository\nSuggestion: Initialize with 'git init' or navigate to a git repository" | 1 |
| PR not found | "Error: Pull request #999 not found" | 1 |

---

## TTY Behavior

### Auto-Detection
- TUI is automatically disabled when stdin or stdout is not a TTY
- Detected scenarios: piped input, redirected output, CI environments

### Explicit Control
- `--no-tui`: Force disable TUI regardless of TTY
- `--quiet`: Suppress non-essential output (implies no TUI)

### Fallback Behavior
When TUI is disabled:
- Progress shown as streaming text output
- Structured data shown as plain text or specified format
- Interactive prompts converted to errors (require explicit flags)

---

## Version Information

```
maverick --version
```

Output format:
```
maverick, version X.Y.Z
```
