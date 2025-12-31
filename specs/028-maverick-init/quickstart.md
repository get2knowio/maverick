# Quickstart: Maverick Init

**Feature**: 028-maverick-init | **Date**: 2025-12-29

## Prerequisites

Before using `maverick init`, ensure you have:

1. **Git** installed and accessible
2. **GitHub CLI** (`gh`) installed and authenticated
3. **Anthropic API key** set in environment

```bash
# Verify prerequisites
git --version
gh --version
gh auth status
echo $ANTHROPIC_API_KEY  # Should show your key
```

## Basic Usage

### Initialize a New Project

```bash
cd /path/to/your/project
maverick init
```

This will:
1. Validate all prerequisites
2. Detect your project type using Claude
3. Parse GitHub owner/repo from git remote
4. Generate `maverick.yaml` with appropriate settings

### Output Example

```
Maverick Init
=============

Prerequisites
  ✓ Git installed (2.43.0)
  ✓ Git repository detected
  ✓ GitHub CLI installed (2.40.0)
  ✓ GitHub CLI authenticated (user: @johndoe)
  ✓ ANTHROPIC_API_KEY set (sk-ant-...1234)
  ✓ Anthropic API accessible

Project Detection
  Primary type: Python
  Detected types: Python
  Confidence: high
  Detection method: claude

Findings
  • pyproject.toml found at project root
  • pytest configured as test runner
  • ruff configured for linting

Git Remote
  Owner: myorg
  Repo: myproject

Generated Configuration
  Format: ruff format .
  Lint: ruff check --fix .
  Typecheck: mypy .
  Test: pytest -x --tb=short

✓ Configuration written to maverick.yaml
```

## Command Options

### Override Project Type

Skip Claude detection and force a specific project type:

```bash
maverick init --type python
maverick init --type nodejs
maverick init --type go
maverick init --type rust
maverick init --type ansible_collection
maverick init --type ansible_playbook
```

### Marker-Only Detection

Use local marker files without calling Claude API:

```bash
maverick init --no-detect
```

This is useful when:
- Working offline
- Saving API credits
- Project type is unambiguous

### Overwrite Existing Config

Replace an existing `maverick.yaml`:

```bash
maverick init --force
```

### Verbose Output

Show detailed prerequisite and detection output:

```bash
maverick init -v
```

## Generated Configuration

The command generates `maverick.yaml` in your project root:

```yaml
github:
  owner: myorg
  repo: myproject
  default_branch: main

validation:
  format_cmd:
    - ruff
    - format
    - "."
  lint_cmd:
    - ruff
    - check
    - --fix
    - "."
  typecheck_cmd:
    - mypy
    - "."
  test_cmd:
    - pytest
    - -x
    - --tb=short
  timeout_seconds: 300
  max_errors: 50

model:
  model_id: claude-sonnet-4-20250514
  max_tokens: 8192
  temperature: 0.0

notifications:
  enabled: false

parallel:
  max_agents: 3
  max_tasks: 5

verbosity: warning
```

## Workflow Preflight

After initialization, the `fly` and `refuel` commands include Anthropic API validation in their preflight checks:

```bash
maverick fly

# Output:
# Preflight Checks
#   ✓ Git repository valid
#   ✓ GitHub CLI authenticated
#   ✓ Anthropic API accessible
#   ✓ Custom tools available
#
# Starting workflow...
```

If the API is inaccessible, workflows are blocked:

```bash
maverick fly

# Output:
# Preflight Checks
#   ✓ Git repository valid
#   ✓ GitHub CLI authenticated
#   ✗ Anthropic API inaccessible
#
# Error: Workflow blocked due to preflight failure.
```

## Troubleshooting

### "Git not installed"

Install Git from https://git-scm.com/

### "Not in a git repository"

```bash
git init
git remote add origin git@github.com:owner/repo.git
```

### "GitHub CLI not installed"

Install from https://cli.github.com/

### "GitHub CLI not authenticated"

```bash
gh auth login
```

### "ANTHROPIC_API_KEY not set"

```bash
export ANTHROPIC_API_KEY=sk-ant-your-key-here
```

Add to your shell profile (`~/.bashrc`, `~/.zshrc`) for persistence.

### "Anthropic API inaccessible"

- Verify your API key is valid
- Check your Anthropic account status
- Ensure your plan includes the configured model

### "maverick.yaml already exists"

Use `--force` to overwrite:

```bash
maverick init --force
```

## Migration from Legacy Command

If you were using `maverick config init`, update your workflow:

```bash
# Old (deprecated)
maverick config init

# New
maverick init
```

The legacy command still works but displays a deprecation warning.

## Next Steps

After initialization:

1. **Review the configuration**: Open `maverick.yaml` and adjust settings if needed
2. **Run a workflow**: `maverick fly` or `maverick refuel`
3. **Enable notifications**: Set `notifications.enabled: true` and provide a topic
