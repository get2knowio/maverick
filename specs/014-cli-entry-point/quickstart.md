# Quickstart: CLI Entry Point

**Feature**: 014-cli-entry-point
**Date**: 2025-12-17

## Overview

This quickstart guide covers implementing the Maverick CLI entry point, extending the existing `main.py` with full command support.

---

## Prerequisites

- Python 3.10+
- Click library (already in dependencies)
- Existing `src/maverick/main.py` with basic CLI group
- Existing workflows: `FlyWorkflow`, `RefuelWorkflow`
- Existing TUI: `MaverickApp`

---

## Implementation Order

### Phase 1: CLI Utilities Module

Create the `cli/` subdirectory with core utilities:

```
src/maverick/cli/
├── __init__.py
├── context.py      # CLIContext, ExitCode, async_command decorator
├── output.py       # OutputFormat, formatting helpers
└── validators.py   # Dependency checks, input validators
```

#### 1.1 Create `cli/__init__.py`

```python
"""CLI utilities for Maverick."""
from maverick.cli.context import (
    CLIContext,
    ExitCode,
    async_command,
)
from maverick.cli.output import OutputFormat
from maverick.cli.validators import check_dependencies

__all__ = [
    "CLIContext",
    "ExitCode",
    "OutputFormat",
    "async_command",
    "check_dependencies",
]
```

#### 1.2 Create `cli/context.py`

```python
"""CLI context and utilities."""
from __future__ import annotations

import asyncio
import functools
import sys
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Any, Callable, TypeVar

from maverick.config import MaverickConfig

F = TypeVar("F", bound=Callable[..., Any])


class ExitCode(IntEnum):
    """Standard exit codes for Maverick CLI."""
    SUCCESS = 0
    FAILURE = 1
    PARTIAL = 2
    INTERRUPTED = 130


@dataclass(frozen=True, slots=True)
class CLIContext:
    """Type-safe CLI context."""
    config: MaverickConfig
    config_path: Path | None = None
    verbosity: int = 0
    quiet: bool = False
    no_tui: bool = False

    @property
    def use_tui(self) -> bool:
        """Whether TUI should be used."""
        if self.no_tui or self.quiet:
            return False
        return sys.stdin.isatty() and sys.stdout.isatty()


def async_command(f: F) -> F:
    """Decorator to run async Click commands."""
    @functools.wraps(f)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return asyncio.run(f(*args, **kwargs))
    return wrapper  # type: ignore[return-value]
```

### Phase 2: Extend main.py

Add global options and commands to existing CLI group.

#### 2.1 Add Global Options

```python
@click.group(invoke_without_command=True)
@click.version_option(version=__version__, prog_name="maverick")
@click.option("-c", "--config", type=click.Path(exists=True), help="Config file path")
@click.option("-v", "--verbose", count=True, help="Increase verbosity")
@click.option("-q", "--quiet", is_flag=True, help="Suppress non-essential output")
@click.option("--no-tui", is_flag=True, help="Disable TUI mode")
@click.pass_context
def cli(ctx: click.Context, config: str | None, verbose: int, quiet: bool, no_tui: bool) -> None:
    """Maverick - AI-powered development workflow orchestration."""
    # ... setup CLIContext
```

#### 2.2 Add Commands

Add each command following this pattern:

```python
@cli.command()
@click.argument("branch_name")
@click.option("-t", "--task-file", type=click.Path(exists=True))
@click.option("--skip-review", is_flag=True)
@click.option("--skip-pr", is_flag=True)
@click.option("--dry-run", is_flag=True)
@click.pass_context
@async_command
async def fly(ctx: click.Context, branch_name: str, task_file: str | None,
              skip_review: bool, skip_pr: bool, dry_run: bool) -> None:
    """Execute FlyWorkflow for a feature branch."""
    cli_ctx: CLIContext = ctx.obj["cli_ctx"]
    # Implementation
```

### Phase 3: Command Implementations

#### 3.1 fly command
- Validate branch exists
- Load task file
- Launch TUI or run headless
- Handle workflow events
- Exit with appropriate code

#### 3.2 refuel command
- Check gh authentication
- Run RefuelWorkflow
- Display progress
- Report results

#### 3.3 review command
- Validate PR exists
- Run code review
- Format output per --output option

#### 3.4 config subcommands
- show: Display current config
- edit: Open in $EDITOR
- validate: Check config validity
- init: Create default config

#### 3.5 status command
- Show git branch
- Show pending tasks
- Show recent history

### Phase 4: Testing

Create tests in `tests/unit/cli/`:

```
tests/unit/cli/
├── __init__.py
├── test_context.py      # Test CLIContext, ExitCode
├── test_output.py       # Test OutputFormat
├── test_validators.py   # Test dependency checks
└── test_main.py         # Test CLI commands
```

Use Click's `CliRunner` for command tests:

```python
from click.testing import CliRunner
from maverick.main import cli

def test_fly_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["fly", "--help"])
    assert result.exit_code == 0
    assert "Execute FlyWorkflow" in result.output
```

---

## Key Implementation Notes

### Async Bridge
All workflow calls must use `@async_command` decorator to bridge sync Click to async workflows.

### Error Handling
```python
try:
    # workflow execution
except MaverickError as e:
    click.echo(f"Error: {e.message}", err=True)
    sys.exit(ExitCode.FAILURE)
except KeyboardInterrupt:
    click.echo("\nInterrupted", err=True)
    sys.exit(ExitCode.INTERRUPTED)
```

### TTY Detection
Always check `cli_ctx.use_tui` before launching TUI:

```python
if cli_ctx.use_tui:
    app = MaverickApp()
    await app.run_async()
else:
    # Headless output
    async for event in workflow.execute():
        click.echo(format_event(event))
```

### Dependency Validation
Check dependencies at command start, not at CLI group initialization (for faster startup):

```python
@cli.command()
@click.pass_context
@async_command
async def fly(ctx: click.Context, ...) -> None:
    check_dependencies(["git"])  # Only check what this command needs
    # ...
```

---

## Verification Checklist

- [ ] `maverick --help` shows all commands
- [ ] `maverick --version` shows version
- [ ] `maverick fly --help` shows fly options
- [ ] `maverick fly branch` launches workflow
- [ ] `maverick --no-tui fly branch` runs headless
- [ ] `maverick refuel --dry-run` lists issues
- [ ] `maverick review 123 --output json` outputs JSON
- [ ] `maverick config show` displays config
- [ ] `maverick status` shows project status
- [ ] Ctrl+C exits with code 130
- [ ] Missing git shows clear error
- [ ] Non-TTY auto-disables TUI
