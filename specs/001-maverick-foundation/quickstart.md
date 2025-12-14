# Quickstart: Maverick Foundation

**Feature**: 001-maverick-foundation
**Date**: 2025-12-12

## Prerequisites

- Python 3.10+
- pip or uv package manager

## Installation

### From Source (Development)

```bash
# Clone the repository
git clone https://github.com/your-org/maverick.git
cd maverick

# Install in editable mode
pip install -e .

# Verify installation
maverick --version
```

### With Development Dependencies

```bash
# Using pip with dependency groups (requires pip 24.1+)
pip install -e . --dependency-groups dev

# Or using uv
uv sync --group dev
```

## Basic Usage

### Check Version

```bash
maverick --version
# Output: maverick, version 0.1.0
```

### View Help

```bash
maverick --help
```

### Increase Verbosity

```bash
# Info level logging
maverick -v

# Debug level logging
maverick -vv
```

## Configuration

Maverick uses a hierarchical configuration system. Settings are loaded in this order (later overrides earlier):

1. Built-in defaults
2. User config: `~/.config/maverick/config.yaml`
3. Project config: `./maverick.yaml`
4. Environment variables: `MAVERICK_*`

### Create Project Configuration

Create `maverick.yaml` in your project root:

```yaml
github:
  owner: "your-org"
  repo: "your-repo"
  default_branch: "main"

notifications:
  enabled: true
  topic: "maverick-notifications"

model:
  model_id: "claude-sonnet-4-20250514"
  max_tokens: 8192

parallel:
  max_agents: 3
  max_tasks: 5

verbosity: "info"
```

### Create User Configuration

Create `~/.config/maverick/config.yaml` for settings that apply across all projects:

```yaml
notifications:
  server: "https://ntfy.sh"
  topic: "my-notifications"

model:
  temperature: 0.1
```

### Environment Variable Overrides

Use environment variables to override any setting:

```bash
# Override GitHub owner
export MAVERICK_GITHUB__OWNER="my-org"

# Override model
export MAVERICK_MODEL__MODEL_ID="claude-sonnet-4-20250514"

# Override parallel limits
export MAVERICK_PARALLEL__MAX_AGENTS=5
```

Note: Use double underscore (`__`) to separate nested keys.

## Configuration Validation

Maverick validates configuration on startup. Invalid settings produce clear error messages:

```
Error: Invalid configuration
  Field: parallel.max_agents
  Value: 15
  Expected: integer between 1 and 10
```

## Running Without Configuration

Maverick works without any configuration file using sensible defaults:

```bash
# Works out of the box
maverick --help
```

If no configuration is found, Maverick logs an informational message:

```
INFO: No project configuration found, using defaults.
```

## Testing Installation

Run the test suite to verify your installation:

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=maverick

# Run specific test file
pytest tests/unit/test_config.py
```

## Troubleshooting

### Configuration Not Loading

1. Check file exists: `ls maverick.yaml`
2. Check YAML syntax: `python -c "import yaml; yaml.safe_load(open('maverick.yaml'))"`
3. Increase verbosity: `maverick -vv`

### Environment Variables Not Working

1. Verify variable is set: `echo $MAVERICK_GITHUB__OWNER`
2. Check double underscore separator for nested keys
3. Ensure prefix is `MAVERICK_` (case-sensitive)

### Import Errors

1. Verify editable install: `pip list | grep maverick`
2. Reinstall: `pip install -e .`
3. Check Python version: `python --version` (needs 3.10+)
