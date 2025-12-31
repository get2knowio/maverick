# CLI Interface Contract: maverick init

**Feature**: 028-maverick-init | **Date**: 2025-12-29

## Command Signature

```
maverick init [OPTIONS]
```

## Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--type` | Choice | None | Override project type detection |
| `--no-detect` | Flag | False | Use marker-based heuristics instead of Claude |
| `--force` | Flag | False | Overwrite existing maverick.yaml |
| `-v, --verbose` | Flag | False | Show detailed output |

### --type Values

```
python, nodejs, go, rust, ansible_collection, ansible_playbook
```

## Exit Codes

| Code | Constant | Description |
|------|----------|-------------|
| 0 | SUCCESS | Init completed successfully |
| 1 | FAILURE | Init failed (prerequisite or detection error) |
| 2 | CONFIG_EXISTS | maverick.yaml exists and --force not provided |

## Output Format

### Successful Initialization

```
Maverick Init
=============

Prerequisites
  ✓ Git installed (2.43.0)
  ✓ Git repository detected
  ✓ GitHub CLI installed (2.40.0)
  ✓ GitHub CLI authenticated (user: @username)
  ✓ ANTHROPIC_API_KEY set (sk-ant-...xxxx)
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
  • mypy configured for type checking

Git Remote
  Owner: myorg
  Repo: myproject
  Remote: git@github.com:myorg/myproject.git

Generated Configuration
  Format: ruff format .
  Lint: ruff check --fix .
  Typecheck: mypy .
  Test: pytest -x --tb=short

✓ Configuration written to maverick.yaml
```

### Prerequisite Failure

```
Maverick Init
=============

Prerequisites
  ✓ Git installed (2.43.0)
  ✓ Git repository detected
  ✗ GitHub CLI not installed

Error: GitHub CLI (gh) is required but not installed.

Remediation: Install from https://cli.github.com/
```

### Config Exists Error

```
Error: maverick.yaml already exists.

Use --force to overwrite the existing configuration.
```

### Detection Failure (Claude Error)

```
Maverick Init
=============

Prerequisites
  ✓ Git installed (2.43.0)
  ✓ Git repository detected
  ✓ GitHub CLI installed (2.40.0)
  ✓ GitHub CLI authenticated (user: @username)
  ✓ ANTHROPIC_API_KEY set (sk-ant-...xxxx)
  ✗ Anthropic API error

Error: Failed to access Anthropic API.

Details: Rate limit exceeded. Please try again later.
```

### No Git Remote Warning

```
Maverick Init
=============

Prerequisites
  ✓ Git installed (2.43.0)
  ✓ Git repository detected
  ✓ GitHub CLI installed (2.40.0)
  ✓ GitHub CLI authenticated (user: @username)
  ✓ ANTHROPIC_API_KEY set (sk-ant-...xxxx)
  ✓ Anthropic API accessible

Project Detection
  Primary type: Python
  Detected types: Python
  Confidence: high
  Detection method: claude

⚠ Warning: No git remote configured. GitHub owner/repo set to null.

Generated Configuration
  ...

✓ Configuration written to maverick.yaml
```

## Deprecation Warning (config init)

```
maverick config init [OPTIONS]
```

Output:
```
⚠️  'maverick config init' is deprecated. Use 'maverick init' instead.

[proceeds with init...]
```

---

# CLI Interface Contract: Workflow Preflight

**Feature**: 028-maverick-init (FR-016, FR-017) | **Date**: 2025-12-29

## Affected Commands

```
maverick fly [OPTIONS]
maverick refuel [OPTIONS]
```

## New Preflight Check: Anthropic API

Added to existing preflight validation sequence.

### Successful Preflight

```
Preflight Checks
  ✓ Git repository valid
  ✓ GitHub CLI authenticated
  ✓ Anthropic API accessible
  ✓ Custom tools available

Starting workflow...
```

### API Validation Failure

```
Preflight Checks
  ✓ Git repository valid
  ✓ GitHub CLI authenticated
  ✗ Anthropic API inaccessible

Error: Workflow blocked due to preflight failure.

Anthropic API check failed:
  • API key may be invalid or expired
  • Model may not be accessible with current plan

Remediation:
  1. Verify ANTHROPIC_API_KEY is set correctly
  2. Check your Anthropic account status and plan limits
  3. Run 'maverick init' to revalidate configuration
```

### API Key Not Set

```
Preflight Checks
  ✓ Git repository valid
  ✓ GitHub CLI authenticated
  ✗ ANTHROPIC_API_KEY not set

Error: Workflow blocked due to preflight failure.

Environment variable ANTHROPIC_API_KEY is not set.

Remediation:
  export ANTHROPIC_API_KEY=sk-ant-your-key-here
```

---

# Generated Configuration Contract: maverick.yaml

**Feature**: 028-maverick-init | **Date**: 2025-12-29

## Schema

```yaml
# GitHub repository configuration
github:
  owner: string | null      # GitHub owner/organization
  repo: string | null       # Repository name
  default_branch: string    # Default: "main"

# Validation commands
validation:
  format_cmd: list[string] | null    # Formatting command
  lint_cmd: list[string] | null      # Linting command
  typecheck_cmd: list[string] | null # Type checking command
  test_cmd: list[string] | null      # Test command
  timeout_seconds: int               # Default: 300
  max_errors: int                    # Default: 50

# Claude model configuration
model:
  model_id: string     # Default: "claude-sonnet-4-20250514"
  max_tokens: int      # Default: 8192
  temperature: float   # Default: 0.0

# Notification configuration (ntfy.sh)
notifications:
  enabled: bool        # Default: false
  server: string       # Default: "https://ntfy.sh"
  topic: string | null # Required if enabled

# Parallel execution limits
parallel:
  max_agents: int      # Default: 3
  max_tasks: int       # Default: 5

# Logging verbosity
verbosity: string      # Default: "warning"
```

## Example: Python Project

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

## Example: Ansible Collection

```yaml
github:
  owner: myorg
  repo: ansible-collection-myns
  default_branch: main

validation:
  format_cmd:
    - yamllint
    - "."
  lint_cmd:
    - ansible-lint
  typecheck_cmd: null
  test_cmd:
    - molecule
    - test
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

## Example: No Git Remote

```yaml
github:
  owner: null
  repo: null
  default_branch: main

validation:
  # ... (rest of config)
```
