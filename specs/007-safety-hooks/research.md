# Research: Safety and Logging Hooks

**Feature Branch**: `007-safety-hooks`
**Date**: 2025-12-15
**Status**: Complete

## Research Questions

1. Claude Agent SDK hook signature and capabilities
2. Dangerous bash command patterns to block
3. Sensitive path patterns for file write protection
4. Log sanitization best practices
5. Thread-safe metrics collection patterns

---

## 1. Claude Agent SDK Hook Capabilities

### Decision: Use async HookMatcher with PreToolUse/PostToolUse events

### Rationale
The Claude Agent SDK provides a flexible hook system via `ClaudeAgentOptions.hooks`. Hooks are async functions that receive tool execution context and can block operations by returning permission decisions.

### Hook Signature

```python
HookCallback = Callable[
    [dict[str, Any], str | None, HookContext],
    Awaitable[dict[str, Any]]
]

async def hook_function(
    input_data: dict[str, Any],    # Contains tool_name, tool_input
    tool_use_id: str | None,        # Tool execution ID
    context: HookContext            # Extensibility context
) -> dict[str, Any]:                # Return decision/modifications
```

### Hook Registration

```python
from claude_agent_sdk import ClaudeAgentOptions, HookMatcher

options = ClaudeAgentOptions(
    hooks={
        "PreToolUse": [
            HookMatcher(
                matcher="Bash",           # Tool name pattern (regex)
                hooks=[validate_bash],    # List of async callbacks
                timeout=10                # Per-matcher timeout in seconds
            ),
        ],
        "PostToolUse": [
            HookMatcher(
                matcher=None,             # None = all tools
                hooks=[log_execution],
                timeout=5
            ),
        ]
    }
)
```

### Blocking Operations

```python
async def validate_command(input_data, tool_use_id, context):
    if is_dangerous(input_data['tool_input']):
        return {
            'hookSpecificOutput': {
                'hookEventName': 'PreToolUse',
                'permissionDecision': 'deny',
                'permissionDecisionReason': 'Dangerous command detected'
            }
        }
    return {}  # Empty dict = allow
```

### Alternatives Considered
- **Decorator-based hooks**: Rejected - less flexible for dynamic configuration
- **Global hook registry**: Rejected - violates dependency injection principle
- **Sync functions**: Rejected - SDK requires async for I/O operations

---

## 2. Dangerous Bash Command Patterns

### Decision: Pattern-based blocklist with environment variable expansion

### Rationale
Dangerous commands must be detected before execution to prevent system damage. The patterns cover destructive operations, resource exhaustion, and unauthorized modifications.

### Blocked Patterns

| Category | Pattern | Example |
|----------|---------|---------|
| Recursive delete root | `rm\s+(-[rf]+\s+)*(/\|~\|\$HOME)` | `rm -rf /`, `rm -rf ~` |
| Fork bombs | `:\(\)\s*\{.*:\|:.*\}` | `:(){ :|:& };:` |
| Disk formatting | `mkfs\.\w+` | `mkfs.ext4 /dev/sda1` |
| Raw disk write | `dd\s+.*if=` | `dd if=/dev/zero of=/dev/sda` |
| System directory writes | write to `/etc/`, `/usr/`, `/bin/`, `/sbin/` | `echo "x" > /etc/passwd` |
| Shutdown/reboot | `(shutdown\|reboot\|halt\|poweroff)` | `shutdown now` |
| Kill all | `kill\s+-9\s+-1` | `kill -9 -1` |

### Compound Command Handling

Per FR-008a, compound commands (`&&`, `||`, `;`, `|`) are parsed and each component validated:

```python
def parse_compound_command(cmd: str) -> list[str]:
    """Parse compound bash commands into components."""
    # Split on &&, ||, ;, | while respecting quotes
    components = []
    # Use shlex or regex to handle quoted strings
    return components
```

### Environment Variable Expansion (FR-008)

```python
import os

def expand_variables(cmd: str) -> str:
    """Expand $VAR and ${VAR} patterns."""
    return os.path.expandvars(cmd)
```

### Unicode/Escape Normalization (FR-008b)

```python
def normalize_input(cmd: str) -> str:
    """Normalize unicode and decode escape sequences."""
    # Decode common escape sequences
    # Normalize unicode to NFC form
    import unicodedata
    return unicodedata.normalize('NFC', cmd.encode().decode('unicode_escape'))
```

### Alternatives Considered
- **AST-based parsing**: More accurate but slower and complex for shell commands
- **Sandbox execution**: Out of scope; hooks prevent execution entirely
- **Whitelist-only approach**: Too restrictive for general agent use

---

## 3. Sensitive Path Patterns

### Decision: Canonical path resolution with pattern matching

### Rationale
Sensitive paths must be protected from accidental or malicious writes. Path resolution prevents bypass via symlinks or relative paths.

### Default Blocked Paths

| Category | Pattern | Purpose |
|----------|---------|---------|
| Environment files | `.env`, `.env.*` | Credentials, secrets |
| Secrets directories | `secrets/`, `.secrets/` | Secret storage |
| SSH configuration | `~/.ssh/` | SSH keys, config |
| AWS credentials | `~/.aws/` | AWS access keys |
| GCloud credentials | `~/.config/gcloud/` | GCP credentials |
| System paths | `/etc/`, `/usr/`, `/bin/`, `/sbin/` | System integrity |
| Root home | `/root/` | Privileged user data |
| Password files | `/etc/passwd`, `/etc/shadow` | User authentication |

### Path Resolution (FR-010a)

```python
from pathlib import Path

def resolve_path(path: str) -> str:
    """Resolve path to canonical form."""
    # Expand ~ and environment variables
    expanded = Path(path).expanduser()
    # Resolve symlinks and normalize
    try:
        return str(expanded.resolve())
    except (OSError, RuntimeError):
        # If resolution fails (broken symlink), use as-is
        return str(expanded)
```

### Alternatives Considered
- **Exact path matching only**: Rejected - too easy to bypass with symlinks
- **Container sandboxing**: Out of scope; hooks prevent at application level
- **Deny-all with explicit allow**: Too restrictive for development workflows

---

## 4. Log Sanitization Best Practices

### Decision: Regex-based pattern replacement with configurable patterns

### Rationale
Logs must never contain secrets. Sanitization uses pattern matching to redact sensitive values while preserving debugging utility.

### Sensitive Patterns to Redact

| Pattern | Description |
|---------|-------------|
| `(password\|passwd\|pwd)\s*[=:]\s*\S+` | Password assignments |
| `(api[_-]?key\|apikey)\s*[=:]\s*\S+` | API keys |
| `(secret\|token)\s*[=:]\s*\S+` | Tokens and secrets |
| `(bearer\|authorization)\s+\S+` | Auth headers |
| `[a-zA-Z0-9+/]{40,}={0,2}` | Base64-encoded secrets (long) |
| `ghp_[a-zA-Z0-9]{36}` | GitHub personal access tokens |
| `sk-[a-zA-Z0-9]{48}` | OpenAI/Anthropic API keys |
| AWS keys pattern | `AKIA[0-9A-Z]{16}` |

### Sanitization Implementation

```python
import re

SENSITIVE_PATTERNS = [
    (r'(password|passwd|pwd)\s*[=:]\s*\S+', r'\1=***REDACTED***'),
    (r'(api[_-]?key|apikey)\s*[=:]\s*\S+', r'\1=***REDACTED***'),
    # ... additional patterns
]

def sanitize_string(text: str) -> str:
    """Sanitize sensitive data from a string."""
    for pattern, replacement in SENSITIVE_PATTERNS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text
```

### Output Truncation (FR-014)

```python
def truncate_output(text: str, max_length: int = 1000) -> str:
    """Truncate output to max length with indicator."""
    if len(text) <= max_length:
        return text
    return text[:max_length] + f"... [truncated {len(text) - max_length} chars]"
```

### Alternatives Considered
- **Structured secret management**: Out of scope; assumes secrets in environment
- **Full encryption**: Overkill for logs; redaction sufficient
- **Allow-list sanitization**: Too complex; block-list patterns more maintainable

---

## 5. Thread-Safe Metrics Collection

### Decision: asyncio Lock with rolling window deque

### Rationale
Metrics must be accurate under concurrent workflow execution (FR-016). Python's asyncio Lock provides async-safe synchronization, and deque with maxlen provides efficient rolling window.

### Implementation Pattern

```python
import asyncio
from collections import deque
from dataclasses import dataclass, field
from time import time

@dataclass
class ToolMetricEntry:
    """Single metric entry for a tool execution."""
    tool_name: str
    timestamp: float
    duration_ms: float
    success: bool

class MetricsCollector:
    """Thread-safe metrics collector with rolling window."""

    def __init__(self, max_entries: int = 10000):
        self._lock = asyncio.Lock()
        self._entries: deque[ToolMetricEntry] = deque(maxlen=max_entries)

    async def record(self, entry: ToolMetricEntry) -> None:
        """Record a metric entry (thread-safe)."""
        async with self._lock:
            self._entries.append(entry)

    async def get_metrics(self, tool_name: str | None = None) -> ToolMetrics:
        """Get aggregated metrics (thread-safe)."""
        async with self._lock:
            filtered = [e for e in self._entries
                       if tool_name is None or e.tool_name == tool_name]
            return self._aggregate(filtered)
```

### Rolling Window Strategies (FR-017a)

| Strategy | Pros | Cons |
|----------|------|------|
| Max entries | Simple, predictable memory | Loses time context |
| Time-based | Preserves time window | Complex cleanup |
| Hybrid | Best of both | More complexity |

**Decision**: Max entries (10,000 default) for simplicity. Time-based queries can filter.

### Alternatives Considered
- **threading.Lock**: Not async-aware; could block event loop
- **Queue-based**: Adds complexity without benefit for in-memory storage
- **External metrics (Prometheus)**: Out of scope; adds dependency

---

## Summary of Decisions

| Area | Decision |
|------|----------|
| Hook System | Async HookMatcher with PreToolUse/PostToolUse events |
| Bash Validation | Pattern blocklist + env expansion + compound parsing |
| File Validation | Canonical path resolution + pattern blocklist |
| Log Sanitization | Regex patterns + output truncation |
| Metrics Collection | asyncio Lock + deque rolling window |

## Sources

- [Claude Agent SDK - Python Reference](https://platform.claude.com/docs/en/agent-sdk/python)
- [Claude Agent SDK Overview](https://docs.claude.com/en/docs/agent-sdk/overview)
- [OWASP Command Injection Prevention](https://cheatsheetseries.owasp.org/cheatsheets/OS_Command_Injection_Defense_Cheat_Sheet.html)
- [Python asyncio Synchronization](https://docs.python.org/3/library/asyncio-sync.html)
- [Existing Maverick base agent patterns](../002-base-agent/research.md)
