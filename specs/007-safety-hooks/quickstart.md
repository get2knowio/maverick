# Quickstart: Safety and Logging Hooks

**Feature Branch**: `007-safety-hooks`
**Date**: 2025-12-15

## Overview

Safety and logging hooks provide:
- **Safety hooks**: Block dangerous bash commands and writes to sensitive files
- **Logging hooks**: Log all tool executions with sanitized inputs
- **Metrics collection**: Track call counts, success rates, and execution times

## Quick Setup

### 1. Basic Usage with Defaults

```python
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions
from maverick.hooks import create_safety_hooks, create_logging_hooks

# Create hooks with secure defaults
options = ClaudeAgentOptions(
    allowed_tools=["Bash", "Write", "Read", "Edit"],
    hooks={
        "PreToolUse": create_safety_hooks(),
        "PostToolUse": create_logging_hooks(),
    }
)

async with ClaudeSDKClient(options=options) as client:
    await client.query("List files in current directory")
    # Safe commands execute normally
    # Dangerous commands are blocked
```

### 2. Custom Configuration

```python
from maverick.hooks import HookConfig, SafetyConfig, LoggingConfig, MetricsConfig

config = HookConfig(
    safety=SafetyConfig(
        bash_blocklist=["wget.*malware"],  # Add custom blocked pattern
        path_allowlist=[".env.example"],    # Allow specific file
    ),
    logging=LoggingConfig(
        log_level="DEBUG",
        max_output_length=2000,
    ),
    metrics=MetricsConfig(
        max_entries=50000,  # Larger rolling window
    ),
)

safety_hooks = create_safety_hooks(config)
logging_hooks = create_logging_hooks(config)
```

### 3. Metrics Collection

```python
from maverick.hooks import create_logging_hooks, MetricsCollector

# Create shared collector for querying later
collector = MetricsCollector()
logging_hooks = create_logging_hooks(metrics_collector=collector)

# After agent execution...
metrics = await collector.get_metrics("Bash")
print(f"Calls: {metrics.call_count}")
print(f"Success rate: {metrics.success_rate:.1%}")
print(f"P95 latency: {metrics.p95_duration_ms:.1f}ms")
```

### 4. Metrics with Time Window

Configure metrics to track only recent activity using `time_window_seconds`:

```python
from maverick.hooks import HookConfig, MetricsConfig, create_logging_hooks, MetricsCollector

# Track metrics for the last 5 minutes only
config = HookConfig(
    metrics=MetricsConfig(
        max_entries=10000,        # Maximum entries in rolling window
        time_window_seconds=300,  # 5 minutes (must be >= 60)
    ),
)

collector = MetricsCollector()
logging_hooks = create_logging_hooks(config, metrics_collector=collector)

# After agent execution...
# Metrics reflect only the last 5 minutes of activity
metrics = await collector.get_metrics("Bash")
print(f"Recent calls (last 5 min): {metrics.call_count}")
```

**Relationship between `max_entries` and `time_window_seconds`:**
- `max_entries`: Hard limit on stored metric entries (prevents unbounded memory growth)
- `time_window_seconds`: Soft limit that filters entries by age when querying
- Use both together: `max_entries` prevents memory issues, `time_window_seconds` focuses on recency
- If `time_window_seconds` is `None` (default), all entries up to `max_entries` are considered

## What Gets Blocked

### Dangerous Bash Commands

| Pattern | Example | Why Blocked |
|---------|---------|-------------|
| Recursive delete | `rm -rf /` | System destruction |
| Fork bomb | `:(){ :\|:& };:` | Resource exhaustion |
| Disk format | `mkfs.ext4 /dev/sda` | Data loss |
| Raw disk write | `dd if=/dev/zero of=/dev/sda` | Data loss |
| System shutdown | `shutdown now` | Service disruption |

### Sensitive File Paths

| Path Pattern | Why Protected |
|--------------|---------------|
| `.env`, `.env.*` | Credentials, secrets |
| `~/.ssh/` | SSH keys |
| `~/.aws/` | AWS credentials |
| `/etc/passwd` | System users |
| `/etc/shadow` | Password hashes |

## Configuration Reference

### Disable Specific Hooks

```python
config = HookConfig(
    safety=SafetyConfig(
        bash_validation_enabled=False,  # Allow all bash commands
    ),
    logging=LoggingConfig(
        enabled=False,  # Disable logging
    ),
)
```

### Add Custom Patterns

```python
config = HookConfig(
    safety=SafetyConfig(
        bash_blocklist=[
            r"curl.*evil\.com",      # Block requests to evil.com
            r"base64\s+-d",          # Block base64 decoding
        ],
        path_blocklist=[
            "/var/log/",             # Block log directory writes
            "config/production/",    # Block production config
        ],
    ),
)
```

### Allow Specific Exceptions

```python
config = HookConfig(
    safety=SafetyConfig(
        bash_allow_override=[
            r"rm -rf node_modules",  # Allow node cleanup
        ],
        path_allowlist=[
            ".env.example",          # Allow example env file
            ".env.test",             # Allow test env file
        ],
    ),
)
```

## Integration with MaverickAgent

```python
from maverick.agents.base import MaverickAgent
from maverick.hooks import create_safety_hooks, create_logging_hooks, HookConfig

class SecureAgent(MaverickAgent):
    def __init__(self, hook_config: HookConfig | None = None):
        super().__init__(
            name="secure-agent",
            system_prompt="You are a secure agent.",
            allowed_tools=["Bash", "Read", "Write"],
        )
        self._hook_config = hook_config or HookConfig()

    def _build_options(self, cwd=None):
        options = super()._build_options(cwd)
        options.hooks = {
            "PreToolUse": create_safety_hooks(self._hook_config),
            "PostToolUse": create_logging_hooks(self._hook_config),
        }
        return options
```

## Logging Output

When logging is enabled, entries look like:

```
INFO maverick.hooks - Tool execution: Bash
  Duration: 45.2ms
  Status: success
  Inputs: {"command": "ls -la /home/user"}
  Output: [truncated 1000 chars]

WARNING maverick.hooks - Tool blocked: Bash
  Reason: Dangerous command detected: rm -rf /
  Pattern: rm\s+(-[rf]+\s+)*(/|~|\$HOME)
```

## Error Handling

### Fail-Closed Behavior

If a hook itself throws an exception, the operation is blocked:

```python
# Hook exception → operation blocked with generic error
# Exception is logged for debugging
# Agent receives safe error message
```

### Blocked Operation Response

When an operation is blocked, the agent receives:

```python
{
    "hookSpecificOutput": {
        "permissionDecision": "deny",
        "permissionDecisionReason": "Dangerous command blocked: rm -rf /"
    }
}
```

## Testing Hooks

Hooks are independently testable without full agent setup:

```python
import pytest
from maverick.hooks.safety import validate_bash_command

@pytest.mark.asyncio
async def test_blocks_rm_rf():
    input_data = {
        "tool_name": "Bash",
        "tool_input": {"command": "rm -rf /"}
    }
    result = await validate_bash_command(input_data, None, None)
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"

@pytest.mark.asyncio
async def test_allows_safe_command():
    input_data = {
        "tool_name": "Bash",
        "tool_input": {"command": "ls -la"}
    }
    result = await validate_bash_command(input_data, None, None)
    assert result == {}  # Empty = allowed
```

## Next Steps

1. See [data-model.md](data-model.md) for entity definitions
2. See [contracts/hooks-api.md](contracts/hooks-api.md) for full API reference
3. See [research.md](research.md) for design decisions and rationale
