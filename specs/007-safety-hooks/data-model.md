# Data Model: Safety and Logging Hooks

**Feature Branch**: `007-safety-hooks`
**Date**: 2025-12-15
**Status**: Complete

## Entity Overview

```
┌─────────────────┐     ┌──────────────────┐
│   HookConfig    │────▶│  SafetyConfig    │
│                 │     │  LoggingConfig   │
│                 │     │  MetricsConfig   │
└─────────────────┘     └──────────────────┘
         │
         ▼
┌─────────────────┐     ┌──────────────────┐
│  Hook Factory   │────▶│   HookMatcher    │
│ create_safety   │     │   (SDK type)     │
│ create_logging  │     └──────────────────┘
└─────────────────┘
         │
         ▼
┌─────────────────┐     ┌──────────────────┐
│ ValidationResult│     │ ToolExecutionLog │
│ (safety output) │     │ (logging output) │
└─────────────────┘     └──────────────────┘
         │
         │
         ▼
┌─────────────────┐
│ MetricsCollector│
│   ToolMetrics   │
│ ToolMetricEntry │
└─────────────────┘
```

---

## Entities

### 1. HookConfig

Root configuration for all hooks. Follows existing MaverickConfig pattern from `src/maverick/config.py`.

```python
from pydantic import BaseModel, Field

class HookConfig(BaseModel):
    """Configuration for safety and logging hooks (FR-005, FR-018-022)."""

    safety: SafetyConfig = Field(default_factory=SafetyConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    metrics: MetricsConfig = Field(default_factory=MetricsConfig)
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `safety` | `SafetyConfig` | (defaults) | Safety hook configuration |
| `logging` | `LoggingConfig` | (defaults) | Logging hook configuration |
| `metrics` | `MetricsConfig` | (defaults) | Metrics collection configuration |

**Validation Rules**:
- All fields are optional with secure defaults (FR-022)
- Nested configs validated by Pydantic

---

### 2. SafetyConfig

Configuration for safety hooks (PreToolUse validation).

```python
class SafetyConfig(BaseModel):
    """Configuration for safety hooks (FR-006-011)."""

    bash_validation_enabled: bool = True
    file_write_validation_enabled: bool = True

    # Bash command patterns
    bash_blocklist: list[str] = Field(default_factory=list)
    bash_allow_override: list[str] = Field(default_factory=list)

    # File path patterns
    sensitive_paths: list[str] = Field(default_factory=_default_sensitive_paths)
    path_allowlist: list[str] = Field(default_factory=list)
    path_blocklist: list[str] = Field(default_factory=list)

    # Hook behavior
    fail_closed: bool = True
    hook_timeout_seconds: int = Field(default=10, ge=1, le=120)
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `bash_validation_enabled` | `bool` | `True` | Enable bash command validation (FR-018) |
| `file_write_validation_enabled` | `bool` | `True` | Enable file write validation (FR-018) |
| `bash_blocklist` | `list[str]` | `[]` | Additional bash patterns to block (FR-007, FR-019) |
| `bash_allow_override` | `list[str]` | `[]` | Patterns to allow (override defaults) |
| `sensitive_paths` | `list[str]` | (defaults) | Paths blocked for writes (FR-009) |
| `path_allowlist` | `list[str]` | `[]` | Paths to allow despite patterns (FR-010, FR-020) |
| `path_blocklist` | `list[str]` | `[]` | Additional paths to block (FR-010, FR-020) |
| `fail_closed` | `bool` | `True` | Block on hook exception (FR-011a) |
| `hook_timeout_seconds` | `int` | `10` | Per-hook timeout |

**Default Sensitive Paths** (FR-009):
```python
def _default_sensitive_paths() -> list[str]:
    return [
        ".env",
        ".env.*",
        "secrets/",
        ".secrets/",
        "~/.ssh/",
        "~/.aws/",
        "~/.config/gcloud/",
        "/etc/",
        "/usr/",
        "/bin/",
        "/sbin/",
        "/root/",
    ]
```

**Validation Rules**:
- `hook_timeout_seconds` must be 1-120 seconds
- Pattern strings validated for valid regex syntax

---

### 3. LoggingConfig

Configuration for logging hooks (PostToolUse).

```python
class LoggingConfig(BaseModel):
    """Configuration for logging hooks (FR-012-014, FR-021)."""

    enabled: bool = True
    log_level: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR)$")
    output_destination: str = "maverick.hooks"  # Logger name

    sanitize_inputs: bool = True
    max_output_length: int = Field(default=1000, ge=100, le=10000)

    # Custom sensitive patterns (in addition to defaults)
    sensitive_patterns: list[str] = Field(default_factory=list)
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | `bool` | `True` | Enable execution logging (FR-018) |
| `log_level` | `str` | `"INFO"` | Python log level (FR-021) |
| `output_destination` | `str` | `"maverick.hooks"` | Logger name (FR-021) |
| `sanitize_inputs` | `bool` | `True` | Sanitize sensitive data (FR-013) |
| `max_output_length` | `int` | `1000` | Max output chars (FR-014) |
| `sensitive_patterns` | `list[str]` | `[]` | Additional patterns to sanitize |

**Validation Rules**:
- `log_level` must match pattern `^(DEBUG|INFO|WARNING|ERROR)$`
- `max_output_length` must be 100-10000 characters

---

### 4. MetricsConfig

Configuration for metrics collection.

```python
class MetricsConfig(BaseModel):
    """Configuration for metrics collection (FR-015-017a)."""

    enabled: bool = True
    max_entries: int = Field(default=10000, ge=100, le=1000000)
    time_window_seconds: int | None = Field(default=None, ge=60)
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | `bool` | `True` | Enable metrics collection (FR-018) |
| `max_entries` | `int` | `10000` | Max entries in rolling window (FR-017a) |
| `time_window_seconds` | `int \| None` | `None` | Optional time-based window |

**Validation Rules**:
- `max_entries` must be 100-1,000,000
- `time_window_seconds` must be >= 60 if set

---

### 5. ValidationResult

Result of a safety validation check.

```python
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Result of a safety validation (Key Entity from spec)."""

    allowed: bool
    reason: str | None = None
    tool_name: str | None = None
    blocked_pattern: str | None = None
```

| Field | Type | Description |
|-------|------|-------------|
| `allowed` | `bool` | Whether operation is permitted |
| `reason` | `str \| None` | Human-readable explanation (FR-011) |
| `tool_name` | `str \| None` | Tool that was validated |
| `blocked_pattern` | `str \| None` | Pattern that triggered block (for debugging) |

**State Transitions**:
- Created as `allowed=True` (default)
- Set to `allowed=False` when validation fails
- Immutable after creation (frozen dataclass)

---

### 6. ToolExecutionLog

Structured log entry for tool executions.

```python
from dataclasses import dataclass
from datetime import datetime

@dataclass(frozen=True, slots=True)
class ToolExecutionLog:
    """Structured log entry for tool execution (FR-012)."""

    tool_name: str
    tool_use_id: str | None
    timestamp: datetime
    duration_ms: float
    success: bool
    sanitized_inputs: dict[str, Any]
    output_summary: str | None
    error_summary: str | None = None
```

| Field | Type | Description |
|-------|------|-------------|
| `tool_name` | `str` | Name of tool executed |
| `tool_use_id` | `str \| None` | SDK tool use ID |
| `timestamp` | `datetime` | When execution started |
| `duration_ms` | `float` | Execution time in ms |
| `success` | `bool` | Whether execution succeeded |
| `sanitized_inputs` | `dict` | Inputs with secrets redacted (FR-013) |
| `output_summary` | `str \| None` | Truncated output (FR-014) |
| `error_summary` | `str \| None` | Error message if failed |

**Validation Rules**:
- `duration_ms` must be non-negative
- `sanitized_inputs` must not contain raw secrets
- `output_summary` must be truncated to config max length

---

### 7. ToolMetricEntry

Single metric data point for a tool execution.

```python
@dataclass(frozen=True, slots=True)
class ToolMetricEntry:
    """Single metric entry for rolling window (FR-015)."""

    tool_name: str
    timestamp: float  # Unix timestamp
    duration_ms: float
    success: bool
```

| Field | Type | Description |
|-------|------|-------------|
| `tool_name` | `str` | Name of tool executed |
| `timestamp` | `float` | Unix timestamp of execution |
| `duration_ms` | `float` | Execution time in ms |
| `success` | `bool` | Whether execution succeeded |

---

### 8. ToolMetrics

Aggregated metrics for a tool type.

```python
@dataclass(frozen=True, slots=True)
class ToolMetrics:
    """Aggregated metrics for a tool type (FR-017)."""

    tool_name: str | None  # None = all tools
    call_count: int
    success_count: int
    failure_count: int
    avg_duration_ms: float
    p50_duration_ms: float
    p95_duration_ms: float
    p99_duration_ms: float
```

| Field | Type | Description |
|-------|------|-------------|
| `tool_name` | `str \| None` | Tool name or None for all |
| `call_count` | `int` | Total executions (FR-015) |
| `success_count` | `int` | Successful executions (FR-015) |
| `failure_count` | `int` | Failed executions (FR-015) |
| `avg_duration_ms` | `float` | Average duration (FR-015) |
| `p50_duration_ms` | `float` | Median duration |
| `p95_duration_ms` | `float` | 95th percentile |
| `p99_duration_ms` | `float` | 99th percentile |

**Computed Properties**:
- `success_rate = success_count / call_count if call_count > 0 else 0.0`
- `failure_rate = failure_count / call_count if call_count > 0 else 0.0`

---

### 9. MetricsCollector

Stateful component for metrics aggregation. Not a data model but included for completeness.

```python
class MetricsCollector:
    """Thread-safe metrics collector (FR-015-017a)."""

    def __init__(self, config: MetricsConfig) -> None: ...

    async def record(self, entry: ToolMetricEntry) -> None:
        """Record a metric entry (thread-safe)."""

    async def get_metrics(
        self,
        tool_name: str | None = None
    ) -> ToolMetrics:
        """Get aggregated metrics (thread-safe)."""

    async def clear(self) -> None:
        """Clear all metrics."""
```

**Thread Safety** (FR-016):
- Uses `asyncio.Lock` for all mutations
- Read operations also acquire lock for consistency

**Rolling Window** (FR-017a):
- Uses `collections.deque(maxlen=config.max_entries)`
- Old entries automatically dropped when max reached

---

## Relationships

```
HookConfig
├── SafetyConfig (1:1)
├── LoggingConfig (1:1)
└── MetricsConfig (1:1)

MetricsCollector
├── MetricsConfig (1:1) - configuration
├── ToolMetricEntry (1:N) - stored entries
└── ToolMetrics (computed) - aggregated output

ValidationResult (standalone) - created per validation
ToolExecutionLog (standalone) - created per execution
```

---

## Exception Hierarchy

Extends existing `src/maverick/exceptions.py`:

```python
class HookError(MaverickError):
    """Base exception for hook-related errors."""

class SafetyHookError(HookError):
    """Exception raised when a safety hook blocks an operation."""

    def __init__(
        self,
        message: str,
        tool_name: str | None = None,
        blocked_pattern: str | None = None,
    ) -> None: ...

class HookConfigError(HookError):
    """Exception raised for hook configuration errors."""

    def __init__(
        self,
        message: str,
        field: str | None = None,
        value: Any = None,
    ) -> None: ...
```

---

## Integration Points

### With MaverickAgent (base.py)

Hooks are passed via `ClaudeAgentOptions.hooks`:

```python
from maverick.hooks import create_safety_hooks, create_logging_hooks

options = ClaudeAgentOptions(
    allowed_tools=self._allowed_tools,
    hooks={
        "PreToolUse": create_safety_hooks(hook_config),
        "PostToolUse": create_logging_hooks(hook_config),
    }
)
```

### With MaverickConfig (config.py)

HookConfig can be added to root config:

```python
class MaverickConfig(BaseSettings):
    # ... existing fields ...
    hooks: HookConfig = Field(default_factory=HookConfig)
```

### With Workflows

Workflows pass hook configuration via AgentContext:

```python
context = AgentContext(
    cwd=Path.cwd(),
    branch="feature-branch",
    hook_config=HookConfig(...)  # Optional extension
)
```
