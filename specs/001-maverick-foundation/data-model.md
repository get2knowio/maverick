# Data Model: Maverick Foundation

**Feature**: 001-maverick-foundation
**Date**: 2025-12-12

## Overview

This document defines the Pydantic models for Maverick's configuration system. All models use Pydantic v2 syntax with complete type annotations.

## Entity Relationship

```
MaverickConfig (root)
├── github: GitHubConfig
├── notifications: NotificationConfig
├── model: ModelConfig
├── parallel: ParallelConfig
└── agents: dict[str, AgentConfig]
```

## Configuration Models

### MaverickConfig

**Description**: Root configuration object containing all Maverick settings. Composed of nested configuration sections for different concerns.

**Source File**: `src/maverick/config.py`

| Field | Type | Default | Validation | Description |
|-------|------|---------|------------|-------------|
| github | GitHubConfig | GitHubConfig() | nested model | GitHub integration settings |
| notifications | NotificationConfig | NotificationConfig() | nested model | Push notification settings |
| model | ModelConfig | ModelConfig() | nested model | Claude model settings |
| parallel | ParallelConfig | ParallelConfig() | nested model | Concurrency limits |
| agents | dict[str, AgentConfig] | {} | dict of nested models | Agent-specific overrides |
| verbosity | Literal["error", "warning", "info", "debug"] | "warning" | enum | Default logging verbosity |

**Class Configuration**:
- `env_prefix = "MAVERICK_"`
- `env_nested_delimiter = "__"`
- `extra = "ignore"` (ignores unknown keys with warning)
- YAML file sources: project (`maverick.yaml`), user (`~/.config/maverick/config.yaml`)

---

### GitHubConfig

**Description**: Settings for GitHub integration including repository owner, name, and default branch.

**Source File**: `src/maverick/config.py`

| Field | Type | Default | Validation | Description |
|-------|------|---------|------------|-------------|
| owner | str \| None | None | optional string | Repository owner (org or user) |
| repo | str \| None | None | optional string | Repository name |
| default_branch | str | "main" | non-empty string | Default branch for PRs |

**Environment Variables**:
- `MAVERICK_GITHUB__OWNER`
- `MAVERICK_GITHUB__REPO`
- `MAVERICK_GITHUB__DEFAULT_BRANCH`

---

### NotificationConfig

**Description**: Settings for ntfy-based push notifications including server URL, topic, and enable flag.

**Source File**: `src/maverick/config.py`

| Field | Type | Default | Validation | Description |
|-------|------|---------|------------|-------------|
| enabled | bool | False | boolean | Enable/disable notifications |
| server | str | "https://ntfy.sh" | valid URL | ntfy server URL |
| topic | str \| None | None | optional string | ntfy topic name |

**Environment Variables**:
- `MAVERICK_NOTIFICATIONS__ENABLED`
- `MAVERICK_NOTIFICATIONS__SERVER`
- `MAVERICK_NOTIFICATIONS__TOPIC`

**Validation Rules**:
- If `enabled=True` and `topic=None`, emit warning about missing topic

---

### ModelConfig

**Description**: Settings for Claude model selection including model ID, max tokens, and temperature.

**Source File**: `src/maverick/config.py`

| Field | Type | Default | Validation | Description |
|-------|------|---------|------------|-------------|
| model_id | str | "claude-sonnet-4-20250514" | non-empty string | Claude model identifier |
| max_tokens | int | 8192 | gt=0, le=200000 | Maximum tokens per request |
| temperature | float | 0.0 | ge=0.0, le=1.0 | Sampling temperature |

**Environment Variables**:
- `MAVERICK_MODEL__MODEL_ID`
- `MAVERICK_MODEL__MAX_TOKENS`
- `MAVERICK_MODEL__TEMPERATURE`

---

### ParallelConfig

**Description**: Settings for concurrency limits including max agents and max tasks.

**Source File**: `src/maverick/config.py`

| Field | Type | Default | Validation | Description |
|-------|------|---------|------------|-------------|
| max_agents | int | 3 | gt=0, le=10 | Maximum concurrent agents |
| max_tasks | int | 5 | gt=0, le=20 | Maximum concurrent tasks per agent |

**Environment Variables**:
- `MAVERICK_PARALLEL__MAX_AGENTS`
- `MAVERICK_PARALLEL__MAX_TASKS`

---

### AgentConfig

**Description**: Flat key-value configuration for a single agent, supporting overrides for model, max_tokens, and temperature.

**Source File**: `src/maverick/config.py`

| Field | Type | Default | Validation | Description |
|-------|------|---------|------------|-------------|
| model_id | str \| None | None | optional string | Override model for this agent |
| max_tokens | int \| None | None | gt=0, le=200000 if set | Override max tokens |
| temperature | float \| None | None | ge=0.0, le=1.0 if set | Override temperature |

**Access Pattern**: `agents.<agent_name>.<setting>` in YAML

**Example YAML**:
```yaml
agents:
  code_reviewer:
    model_id: "claude-sonnet-4-20250514"
    max_tokens: 4096
  spec_compliance:
    temperature: 0.2
```

**Environment Variables**:
- `MAVERICK_AGENTS__CODE_REVIEWER__MODEL_ID`
- `MAVERICK_AGENTS__CODE_REVIEWER__MAX_TOKENS`

---

## Exception Classes

### MaverickError

**Description**: Base exception class for all Maverick-specific errors. Enables consistent error handling at CLI boundaries.

**Source File**: `src/maverick/exceptions.py`

| Attribute | Type | Description |
|-----------|------|-------------|
| message | str | Human-readable error description |

**Usage**:
```python
try:
    # Maverick operations
except MaverickError as e:
    click.echo(f"Error: {e.message}", err=True)
    ctx.exit(1)
```

---

### ConfigError

**Description**: Subclass of MaverickError for configuration loading, parsing, and validation errors.

**Source File**: `src/maverick/exceptions.py`

| Attribute | Type | Description |
|-----------|------|-------------|
| message | str | Human-readable error description |
| field | str \| None | Field that caused the error (if applicable) |
| value | Any \| None | Invalid value (if applicable) |

**Raised When**:
- YAML parsing fails (invalid syntax)
- Pydantic validation fails (invalid field types/values)
- Required field missing without default
- Environment variable contains invalid value

**Usage**:
```python
raise ConfigError(
    message="Invalid parallel.max_agents: must be between 1 and 10",
    field="parallel.max_agents",
    value=15
)
```

---

## Configuration Loading Flow

```
1. Load built-in defaults (model defaults in Pydantic)
         ↓
2. Load user config (~/.config/maverick/config.yaml) if exists
         ↓
3. Merge: user config overrides defaults
         ↓
4. Load project config (./maverick.yaml) if exists
         ↓
5. Merge: project config overrides user config
         ↓
6. Apply environment variables (MAVERICK_*)
         ↓
7. Validate merged config via Pydantic
         ↓
8. Return MaverickConfig instance
```

## State Transitions

N/A - Configuration is immutable after loading. The `MaverickConfig` object is loaded once at CLI startup and passed to agents/workflows via dependency injection.

## Validation Rules Summary

| Rule | Fields | Error Message |
|------|--------|---------------|
| max_tokens range | ModelConfig.max_tokens, AgentConfig.max_tokens | "max_tokens must be between 1 and 200000" |
| temperature range | ModelConfig.temperature, AgentConfig.temperature | "temperature must be between 0.0 and 1.0" |
| max_agents range | ParallelConfig.max_agents | "max_agents must be between 1 and 10" |
| max_tasks range | ParallelConfig.max_tasks | "max_tasks must be between 1 and 20" |
| verbosity enum | MaverickConfig.verbosity | "verbosity must be one of: error, warning, info, debug" |
