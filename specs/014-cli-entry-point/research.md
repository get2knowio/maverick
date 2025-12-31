# Research: CLI Entry Point

**Feature**: 014-cli-entry-point
**Date**: 2025-12-17
**Status**: Complete

## Overview

Research findings for implementing the Maverick CLI entry point using Click, covering best practices for global options, async handling, TTY detection, exit codes, output formatting, and configuration loading.

---

## 1. Global Options Pattern

### Decision
Use the **Context Object Pattern** with `@click.pass_context` decorator at the group level to share global options across all subcommands.

### Rationale
- Click's context object (`ctx.obj`) provides clean dependency injection
- Aligns with Maverick's architectural principle: "Dependency Injection"
- Current implementation in `main.py` already uses this pattern correctly
- Enables subcommands to access global options without tight coupling

### Alternatives Considered
| Alternative | Why Rejected |
|-------------|--------------|
| Common options decorator on each command | Violates DRY, maintenance burden |
| Custom Group class override | Overcomplicates simple use case |
| Global module state | Violates "No global mutable state" principle |

---

## 2. Async Command Handling

### Decision
Implement a custom `@async_command` decorator using `asyncio.run()` to bridge Click's synchronous interface to async workflow functions.

### Rationale
- Click has no native async support (open issue since 2017)
- Maverick's core principle: "Async-First: All agent interactions and workflows MUST be async"
- Custom decorator is explicit, simple, no external dependencies
- Production-proven pattern from Safir library

### Implementation
```python
import asyncio
import functools
from typing import TypeVar, Callable, Any

F = TypeVar('F', bound=Callable[..., Any])

def async_command(f: F) -> F:
    """Decorator to run async Click commands with asyncio.run()."""
    @functools.wraps(f)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return asyncio.run(f(*args, **kwargs))
    return wrapper
```

### Alternatives Considered
| Alternative | Why Rejected |
|-------------|--------------|
| asyncclick library | External dependency, incompatible with Click |
| Manual asyncio.run() in each command | Repetitive, error-prone |
| Wait for Click 9.0 async support | Timeline uncertain (7+ years open) |

---

## 3. TTY Detection

### Decision
Use `sys.stdin.isatty()` and `sys.stdout.isatty()` to detect non-interactive environments and automatically disable TUI mode.

### Rationale
- Standard Python approach, no external dependencies
- Aligns with FR-011: "System MUST auto-detect non-TTY environments"
- Textual TUI requires both stdin and stdout to be TTY

### Implementation
```python
import sys

def should_use_tui(ctx: click.Context) -> bool:
    """Determine if TUI should be enabled."""
    if ctx.obj.get('no_tui', False):
        return False
    if ctx.obj.get('quiet', False):
        return False
    return sys.stdin.isatty() and sys.stdout.isatty()
```

### Alternatives Considered
| Alternative | Why Rejected |
|-------------|--------------|
| Check at import time | Can't be overridden by --no-tui flag |
| Environment variable only (CI=true) | Not portable, misses pipe/redirect |

---

## 4. Keyboard Interrupt Handling

### Decision
Catch `KeyboardInterrupt` at command boundaries and exit with code 130 (Unix convention for SIGINT).

### Rationale
- Users expect Ctrl+C to terminate cleanly without stack traces
- FR-016: "System MUST gracefully handle keyboard interrupts"
- Exit code 130 = 128 + signal 2 (SIGINT)

### Implementation
```python
@cli.command()
@async_command
async def fly(ctx: click.Context, branch: str) -> None:
    try:
        # Execute workflow
        pass
    except KeyboardInterrupt:
        click.echo("\nWorkflow interrupted. Cleaning up...", err=True)
        sys.exit(130)
```

### Alternatives Considered
| Alternative | Why Rejected |
|-------------|--------------|
| Signal handlers | Conflicts with asyncio event loop |
| No special handling | Poor UX, shows stack traces |

---

## 5. Exit Code Conventions

### Decision
Use an `ExitCode` enum with standard values: SUCCESS=0, FAILURE=1, PARTIAL=2, INTERRUPTED=130.

### Rationale
- FR-012: "System MUST use standard exit codes: 0 for success, 1 for failure, 2 for partial success"
- Exit code 130 is Unix standard for SIGINT
- Enum provides type safety and documentation

### Implementation
```python
from enum import IntEnum

class ExitCode(IntEnum):
    """Standard exit codes for Maverick CLI."""
    SUCCESS = 0         # Successful execution
    FAILURE = 1         # General failure
    PARTIAL = 2         # Partial success (some tasks failed)
    INTERRUPTED = 130   # Keyboard interrupt (128 + SIGINT=2)
```

### Alternatives Considered
| Alternative | Why Rejected |
|-------------|--------------|
| sysexits.h constants (os.EX_OK) | Not portable to Windows |
| Custom range 64-113 | Deprecated, non-standard |

---

## 6. Output Formatting

### Decision
Use `OutputFormat` enum with choices (tui, json, markdown, text) via `--output/-o` option. Use `click.echo()` for output.

### Rationale
- Click's `type=click.Choice()` provides validation
- JSON enables programmatic consumption (CI/CD)
- Markdown enables documentation integration

### Implementation
```python
from enum import Enum

class OutputFormat(str, Enum):
    """Supported output formats."""
    TUI = "tui"
    JSON = "json"
    MARKDOWN = "markdown"
    TEXT = "text"
```

### Best Practices
- Use `click.echo()` not `print()` (handles Unicode properly)
- Use `click.echo(..., err=True)` for error messages
- Create Rich Console once at module level if using rich output

### Alternatives Considered
| Alternative | Why Rejected |
|-------------|--------------|
| Multiple boolean flags (--json, --markdown) | Mutually exclusive, harder to validate |
| Template system (Jinja2) | Overkill for simple formats |

---

## 7. Configuration Loading

### Decision
Keep existing Pydantic BaseSettings with custom YAML source. Load config in CLI group context setup.

### Rationale
- Current Maverick implementation already excellent
- Pydantic provides validation and type safety
- Hierarchy: defaults -> user config -> project config -> env vars -> CLI flags

### Current Implementation Strengths
- Global options with context object (main.py lines 17-30)
- Config loading with validation and clear errors (main.py lines 32-45)
- Pydantic-based configuration hierarchy (config.py)
- Comprehensive exception hierarchy (exceptions.py)

### No Changes Needed
The existing pattern is correct and should be preserved.

---

## 8. Dependency Validation

### Decision
Check required CLI tools (git, gh) at startup before command execution.

### Rationale
- FR-013: "System MUST validate required dependencies at startup"
- Clear error messages with installation instructions
- Fail fast rather than mid-execution

### Implementation
```python
import shutil

def check_dependencies() -> None:
    """Validate required CLI tools are installed."""
    if not shutil.which('git'):
        click.echo("Error: git is not installed or not in PATH", err=True)
        click.echo("Install: https://git-scm.com/downloads", err=True)
        sys.exit(ExitCode.FAILURE)

    if not shutil.which('gh'):
        click.echo("Error: GitHub CLI (gh) is not installed", err=True)
        click.echo("Install: https://cli.github.com/", err=True)
        sys.exit(ExitCode.FAILURE)
```

---

## Summary: New Components Needed

| Component | Location | Purpose |
|-----------|----------|---------|
| `@async_command` decorator | `cli/context.py` | Bridge sync Click to async workflows |
| `should_use_tui()` function | `cli/context.py` | TTY detection logic |
| `ExitCode` enum | `cli/context.py` | Standardized exit codes |
| `OutputFormat` enum | `cli/output.py` | Output format choices |
| `check_dependencies()` | `cli/validators.py` | Dependency validation |
| `CLIContext` dataclass | `cli/context.py` | Type-safe context wrapper |

---

## Sources

- [Using Click for command-line interfaces - Safir](https://safir.lsst.io/user-guide/click.html)
- [Click Exception Handling](https://click.palletsprojects.com/en/stable/exceptions/)
- [Exit Code Best Practices](https://chrisdown.name/2013/11/03/exit-code-best-practises.html)
- [rich-click GitHub](https://github.com/ewels/rich-click)
- [Pydantic Settings Guide](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
