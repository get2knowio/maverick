# Hooks API Contract

**Feature Branch**: `007-safety-hooks`
**Date**: 2025-12-15
**Status**: Complete

This document defines the public API contracts for the safety and logging hooks module.

---

## Module: `maverick.hooks`

### Public Exports

```python
from maverick.hooks import (
    # Factory functions (FR-001, FR-002)
    create_safety_hooks,
    create_logging_hooks,

    # Configuration (FR-005)
    HookConfig,
    SafetyConfig,
    LoggingConfig,
    MetricsConfig,

    # Types (Key Entities)
    ValidationResult,
    ToolExecutionLog,
    ToolMetrics,
    ToolMetricEntry,

    # Metrics collector
    MetricsCollector,

    # Exceptions
    HookError,
    SafetyHookError,
    HookConfigError,
)
```

---

## Factory Functions

### `create_safety_hooks`

Creates safety hooks for PreToolUse validation.

```python
def create_safety_hooks(config: HookConfig | None = None) -> list[HookMatcher]:
    """Create safety hooks for PreToolUse validation (FR-001).

    Args:
        config: Optional hook configuration. Uses secure defaults if None.

    Returns:
        List of HookMatcher objects for PreToolUse event.

    Example:
        >>> from maverick.hooks import create_safety_hooks, HookConfig
        >>> hooks = create_safety_hooks(HookConfig())
        >>> # Use in ClaudeAgentOptions
        >>> options = ClaudeAgentOptions(
        ...     hooks={"PreToolUse": hooks}
        ... )
    """
```

**Behavior**:
- Returns `HookMatcher` for "Bash" tool with `validate_bash_command`
- Returns `HookMatcher` for "Write|Edit" tools with `validate_file_write`
- Respects `config.safety.bash_validation_enabled` and `file_write_validation_enabled`
- Uses `config.safety.hook_timeout_seconds` for matcher timeout

**Returns**: `list[HookMatcher]` (may be empty if all validation disabled)

---

### `create_logging_hooks`

Creates logging hooks for PostToolUse logging and metrics.

```python
def create_logging_hooks(
    config: HookConfig | None = None,
    metrics_collector: MetricsCollector | None = None,
) -> list[HookMatcher]:
    """Create logging hooks for PostToolUse events (FR-002).

    Args:
        config: Optional hook configuration. Uses defaults if None.
        metrics_collector: Optional shared metrics collector. Created if None.

    Returns:
        List of HookMatcher objects for PostToolUse event.

    Example:
        >>> from maverick.hooks import create_logging_hooks, MetricsCollector
        >>> collector = MetricsCollector()
        >>> hooks = create_logging_hooks(metrics_collector=collector)
        >>> # Later: query metrics
        >>> metrics = await collector.get_metrics("Bash")
    """
```

**Behavior**:
- Returns `HookMatcher` with `matcher=None` (all tools) containing:
  - `log_tool_execution` hook (if `config.logging.enabled`)
  - `metrics_collector` hook (if `config.metrics.enabled`)
- If `metrics_collector` is None, creates internal instance

**Returns**: `list[HookMatcher]` (may be empty if all logging disabled)

---

## Safety Hooks

### `validate_bash_command`

PreToolUse hook for Bash command validation.

```python
async def validate_bash_command(
    input_data: dict[str, Any],
    tool_use_id: str | None,
    context: HookContext,
    *,
    config: SafetyConfig | None = None,
) -> dict[str, Any]:
    """Validate bash commands for dangerous patterns (FR-006-008b).

    Args:
        input_data: Contains 'tool_name' and 'tool_input' with 'command' key.
        tool_use_id: SDK tool use identifier.
        context: Hook context from SDK.
        config: Optional safety configuration.

    Returns:
        Empty dict if allowed, or dict with permissionDecision='deny' if blocked.

    Raises:
        Never raises (fail-closed behavior catches exceptions internally).
    """
```

**Input Data Structure**:
```python
{
    "tool_name": "Bash",
    "tool_input": {
        "command": "rm -rf /home/user",
        "timeout": 5000
    }
}
```

**Validation Steps** (FR-006-008b):
1. Normalize unicode and decode escape sequences
2. Expand environment variables (`$HOME`, `${VAR}`)
3. Parse compound commands (`&&`, `||`, `;`, `|`)
4. Check each component against dangerous patterns
5. Block if any component matches blocklist

**Dangerous Patterns** (FR-006):
- `rm -rf /`, `rm -rf ~`, `rm -rf $HOME`
- Fork bombs: `:(){ :|:& };:`
- Disk formatting: `mkfs.*`
- Raw disk write: `dd if=`
- System directory writes
- Shutdown/reboot commands

**Return on Block**:
```python
{
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": "Dangerous command blocked: rm -rf /"
    }
}
```

---

### `validate_file_write`

PreToolUse hook for file write validation.

```python
async def validate_file_write(
    input_data: dict[str, Any],
    tool_use_id: str | None,
    context: HookContext,
    *,
    config: SafetyConfig | None = None,
) -> dict[str, Any]:
    """Validate file writes to sensitive paths (FR-009-010b).

    Args:
        input_data: Contains 'tool_name' and 'tool_input' with 'file_path' key.
        tool_use_id: SDK tool use identifier.
        context: Hook context from SDK.
        config: Optional safety configuration.

    Returns:
        Empty dict if allowed, or dict with permissionDecision='deny' if blocked.

    Raises:
        Never raises (fail-closed behavior catches exceptions internally).
    """
```

**Input Data Structure**:
```python
{
    "tool_name": "Write",  # or "Edit"
    "tool_input": {
        "file_path": "/home/user/.env",
        "content": "..."
    }
}
```

**Validation Steps** (FR-010a-010b):
1. Normalize unicode in path
2. Expand `~` and environment variables
3. Resolve to canonical path (`realpath()`)
4. Check against allowlist (allow if matches)
5. Check against blocklist and sensitive_paths (block if matches)

**Sensitive Paths** (FR-009):
- `.env`, `.env.*`
- `secrets/`, `.secrets/`
- `~/.ssh/`
- `~/.aws/`, `~/.config/gcloud/`
- `/etc/`, `/usr/`, `/bin/`, `/sbin/`

---

## Logging Hooks

### `log_tool_execution`

PostToolUse hook for execution logging.

```python
async def log_tool_execution(
    input_data: dict[str, Any],
    tool_use_id: str | None,
    context: HookContext,
    *,
    config: LoggingConfig | None = None,
) -> dict[str, Any]:
    """Log tool execution with sanitized data (FR-012-014).

    Args:
        input_data: Contains tool_name, tool_input, output, status.
        tool_use_id: SDK tool use identifier.
        context: Hook context from SDK.
        config: Optional logging configuration.

    Returns:
        Empty dict (no modification to flow).
    """
```

**Input Data Structure** (PostToolUse):
```python
{
    "tool_name": "Bash",
    "tool_input": {"command": "ls -la"},
    "output": "total 16\ndrwxr-xr-x...",
    "status": "success"  # or "error"
}
```

**Logged Data** (FR-012):
- Tool name
- Sanitized inputs (FR-013)
- Duration (milliseconds)
- Success/failure status
- Truncated output summary (FR-014)

**Sanitization** (FR-013):
- Redacts passwords, API keys, tokens
- Redacts bearer/authorization headers
- Redacts base64-encoded secrets

---

### `collect_metrics`

PostToolUse hook for metrics collection.

```python
async def collect_metrics(
    input_data: dict[str, Any],
    tool_use_id: str | None,
    context: HookContext,
    *,
    collector: MetricsCollector,
) -> dict[str, Any]:
    """Collect execution metrics (FR-015-017a).

    Args:
        input_data: Contains tool_name, status, duration info.
        tool_use_id: SDK tool use identifier.
        context: Hook context from SDK.
        collector: MetricsCollector instance (required).

    Returns:
        Empty dict (no modification to flow).
    """
```

---

## MetricsCollector

Thread-safe metrics aggregator.

```python
class MetricsCollector:
    """Thread-safe metrics collector with rolling window (FR-015-017a)."""

    def __init__(self, config: MetricsConfig | None = None) -> None:
        """Initialize collector.

        Args:
            config: Optional metrics configuration.
        """

    async def record(self, entry: ToolMetricEntry) -> None:
        """Record a metric entry (thread-safe, FR-016).

        Args:
            entry: Metric data point to record.
        """

    async def get_metrics(
        self,
        tool_name: str | None = None,
    ) -> ToolMetrics:
        """Get aggregated metrics (thread-safe, FR-017).

        Args:
            tool_name: Filter by tool name. None for all tools.

        Returns:
            Aggregated metrics with counts, rates, and timing statistics.
        """

    async def clear(self) -> None:
        """Clear all collected metrics."""

    @property
    def entry_count(self) -> int:
        """Current number of entries in rolling window."""
```

---

## Configuration Classes

### `HookConfig`

```python
class HookConfig(BaseModel):
    """Root configuration for hooks (FR-005)."""

    safety: SafetyConfig = Field(default_factory=SafetyConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    metrics: MetricsConfig = Field(default_factory=MetricsConfig)

    model_config = ConfigDict(frozen=False, extra="forbid")
```

### `SafetyConfig`

```python
class SafetyConfig(BaseModel):
    """Safety hook configuration (FR-018-020)."""

    bash_validation_enabled: bool = True
    file_write_validation_enabled: bool = True
    bash_blocklist: list[str] = Field(default_factory=list)
    bash_allow_override: list[str] = Field(default_factory=list)
    sensitive_paths: list[str] = Field(default_factory=_default_sensitive_paths)
    path_allowlist: list[str] = Field(default_factory=list)
    path_blocklist: list[str] = Field(default_factory=list)
    fail_closed: bool = True
    hook_timeout_seconds: int = Field(default=10, ge=1, le=120)
```

### `LoggingConfig`

```python
class LoggingConfig(BaseModel):
    """Logging hook configuration (FR-021)."""

    enabled: bool = True
    log_level: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR)$")
    output_destination: str = "maverick.hooks"
    sanitize_inputs: bool = True
    max_output_length: int = Field(default=1000, ge=100, le=10000)
    sensitive_patterns: list[str] = Field(default_factory=list)
```

### `MetricsConfig`

```python
class MetricsConfig(BaseModel):
    """Metrics configuration (FR-017a)."""

    enabled: bool = True
    max_entries: int = Field(default=10000, ge=100, le=1000000)
    time_window_seconds: int | None = Field(default=None, ge=60)
```

---

## Type Definitions

### `ValidationResult`

```python
@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Result of a safety validation."""

    allowed: bool
    reason: str | None = None
    tool_name: str | None = None
    blocked_pattern: str | None = None
```

### `ToolExecutionLog`

```python
@dataclass(frozen=True, slots=True)
class ToolExecutionLog:
    """Structured log entry for tool execution."""

    tool_name: str
    tool_use_id: str | None
    timestamp: datetime
    duration_ms: float
    success: bool
    sanitized_inputs: dict[str, Any]
    output_summary: str | None
    error_summary: str | None = None
```

### `ToolMetricEntry`

```python
@dataclass(frozen=True, slots=True)
class ToolMetricEntry:
    """Single metric entry."""

    tool_name: str
    timestamp: float
    duration_ms: float
    success: bool
```

### `ToolMetrics`

```python
@dataclass(frozen=True, slots=True)
class ToolMetrics:
    """Aggregated metrics for a tool type."""

    tool_name: str | None
    call_count: int
    success_count: int
    failure_count: int
    avg_duration_ms: float
    p50_duration_ms: float
    p95_duration_ms: float
    p99_duration_ms: float

    @property
    def success_rate(self) -> float:
        """Success rate as fraction 0.0-1.0."""
        return self.success_count / self.call_count if self.call_count > 0 else 0.0

    @property
    def failure_rate(self) -> float:
        """Failure rate as fraction 0.0-1.0."""
        return self.failure_count / self.call_count if self.call_count > 0 else 0.0
```

---

## Exceptions

### `HookError`

```python
class HookError(MaverickError):
    """Base exception for hook-related errors."""
```

### `SafetyHookError`

```python
class SafetyHookError(HookError):
    """Exception raised when a safety hook blocks an operation."""

    def __init__(
        self,
        message: str,
        tool_name: str | None = None,
        blocked_pattern: str | None = None,
    ) -> None:
        self.tool_name = tool_name
        self.blocked_pattern = blocked_pattern
        super().__init__(message)
```

### `HookConfigError`

```python
class HookConfigError(HookError):
    """Exception raised for hook configuration errors."""

    def __init__(
        self,
        message: str,
        field: str | None = None,
        value: Any = None,
    ) -> None:
        self.field = field
        self.value = value
        super().__init__(message)
```

---

## Usage Examples

### Basic Setup

```python
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions
from maverick.hooks import create_safety_hooks, create_logging_hooks, HookConfig

# Create hooks with default configuration
config = HookConfig()
safety_hooks = create_safety_hooks(config)
logging_hooks = create_logging_hooks(config)

# Configure agent
options = ClaudeAgentOptions(
    allowed_tools=["Bash", "Write", "Read"],
    hooks={
        "PreToolUse": safety_hooks,
        "PostToolUse": logging_hooks,
    }
)

async with ClaudeSDKClient(options=options) as client:
    await client.query("List files in current directory")
```

### Custom Configuration

```python
from maverick.hooks import HookConfig, SafetyConfig, LoggingConfig

config = HookConfig(
    safety=SafetyConfig(
        bash_blocklist=["curl.*evil.com"],  # Custom pattern
        path_allowlist=[".env.example"],     # Allow specific file
    ),
    logging=LoggingConfig(
        log_level="DEBUG",
        max_output_length=2000,
    ),
)

hooks = create_safety_hooks(config)
```

### Metrics Collection

```python
from maverick.hooks import create_logging_hooks, MetricsCollector, HookConfig

# Create shared collector
collector = MetricsCollector()

# Create hooks with collector
hooks = create_logging_hooks(HookConfig(), metrics_collector=collector)

# After agent execution, query metrics
metrics = await collector.get_metrics("Bash")
print(f"Bash calls: {metrics.call_count}")
print(f"Success rate: {metrics.success_rate:.1%}")
print(f"Avg duration: {metrics.avg_duration_ms:.1f}ms")
```

### Disabling Specific Hooks

```python
config = HookConfig(
    safety=SafetyConfig(
        bash_validation_enabled=False,  # Disable bash validation
        file_write_validation_enabled=True,
    ),
    logging=LoggingConfig(enabled=False),  # Disable logging
    metrics=MetricsConfig(enabled=True),   # Keep metrics
)
```
