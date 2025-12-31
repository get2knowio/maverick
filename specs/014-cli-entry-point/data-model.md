# Data Model: CLI Entry Point

**Feature**: 014-cli-entry-point
**Date**: 2025-12-17
**Status**: Complete

## Overview

This document defines the data models for the CLI entry point, including context objects, enums, and type definitions used across CLI commands.

---

## Core Entities

### 1. CLIContext

**Purpose**: Type-safe wrapper for Click context object, storing global options and configuration.

**Location**: `src/maverick/cli/context.py`

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from maverick.config import MaverickConfig


@dataclass(frozen=True, slots=True)
class CLIContext:
    """Type-safe CLI context containing global options and configuration.

    Attributes:
        config: Loaded Maverick configuration.
        config_path: Path to config file (if specified via --config).
        verbosity: Verbosity level (0=default, 1=INFO, 2+=DEBUG).
        quiet: Suppress non-essential output.
        no_tui: Disable TUI mode regardless of TTY.
    """
    config: MaverickConfig
    config_path: Path | None = None
    verbosity: int = 0
    quiet: bool = False
    no_tui: bool = False

    @property
    def use_tui(self) -> bool:
        """Whether TUI should be used (considers TTY detection)."""
        import sys
        if self.no_tui:
            return False
        if self.quiet:
            return False
        return sys.stdin.isatty() and sys.stdout.isatty()
```

**Validation Rules**:
- `verbosity` >= 0 (no upper limit, but 3+ treated same as 3)
- `config` must be a valid MaverickConfig instance
- `config_path` if provided must point to existing file (validated at load time)

---

### 2. ExitCode

**Purpose**: Standardized exit codes for consistent CLI behavior.

**Location**: `src/maverick/cli/context.py`

```python
from enum import IntEnum


class ExitCode(IntEnum):
    """Standard exit codes for Maverick CLI.

    Follows Unix conventions and FR-012 requirements:
    - 0 for success
    - 1 for failure
    - 2 for partial success
    - 130 for keyboard interrupt (128 + SIGINT=2)
    """
    SUCCESS = 0
    FAILURE = 1
    PARTIAL = 2
    INTERRUPTED = 130
```

**State Transitions**:
- Command starts -> SUCCESS (default)
- Error occurs -> FAILURE
- Partial completion -> PARTIAL
- Ctrl+C pressed -> INTERRUPTED

---

### 3. OutputFormat

**Purpose**: Supported output formats for commands with `--output` option.

**Location**: `src/maverick/cli/output.py`

```python
from enum import Enum


class OutputFormat(str, Enum):
    """Supported output formats for CLI commands.

    Values:
        TUI: Interactive terminal UI (default when TTY available).
        JSON: Machine-readable JSON output.
        MARKDOWN: Formatted markdown for documentation.
        TEXT: Plain text output (default in non-TTY).
    """
    TUI = "tui"
    JSON = "json"
    MARKDOWN = "markdown"
    TEXT = "text"
```

---

### 4. DependencyStatus

**Purpose**: Track status of required external dependencies.

**Location**: `src/maverick/cli/validators.py`

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DependencyStatus:
    """Status of a required CLI dependency.

    Attributes:
        name: Dependency name (e.g., "git", "gh").
        available: Whether the dependency is installed and accessible.
        version: Version string if available.
        path: Path to executable if found.
        error: Error message if not available.
        install_url: URL for installation instructions.
    """
    name: str
    available: bool
    version: str | None = None
    path: str | None = None
    error: str | None = None
    install_url: str | None = None
```

---

## Command Input Models

### 5. FlyCommandInputs

**Purpose**: Validated inputs for the `fly` command before passing to FlyWorkflow.

**Location**: `src/maverick/cli/context.py` (or inline in main.py)

```python
@dataclass(frozen=True, slots=True)
class FlyCommandInputs:
    """Inputs for fly command execution.

    Maps CLI arguments/options to FlyInputs for workflow.

    Attributes:
        branch_name: Target branch for workflow.
        task_file: Optional path to task file.
        skip_review: Skip code review stage.
        skip_pr: Skip PR creation.
        dry_run: Show planned actions without executing.
    """
    branch_name: str
    task_file: Path | None = None
    skip_review: bool = False
    skip_pr: bool = False
    dry_run: bool = False

    def to_fly_inputs(self) -> FlyInputs:
        """Convert to workflow FlyInputs."""
        from maverick.workflows.fly import FlyInputs
        return FlyInputs(
            branch_name=self.branch_name,
            task_file=self.task_file,
            skip_review=self.skip_review,
            skip_pr=self.skip_pr,
        )
```

---

### 6. RefuelCommandInputs

**Purpose**: Validated inputs for the `refuel` command.

```python
@dataclass(frozen=True, slots=True)
class RefuelCommandInputs:
    """Inputs for refuel command execution.

    Attributes:
        label: Issue label to filter by.
        limit: Maximum issues to process.
        parallel: Run in parallel mode.
        dry_run: Show matching issues without processing.
    """
    label: str = "tech-debt"
    limit: int = 5
    parallel: bool = True
    dry_run: bool = False

    def to_refuel_inputs(self) -> RefuelInputs:
        """Convert to workflow RefuelInputs."""
        from maverick.workflows.refuel import RefuelInputs
        return RefuelInputs(
            label=self.label,
            limit=self.limit,
            parallel=self.parallel,
            dry_run=self.dry_run,
        )
```

---

### 7. ReviewCommandInputs

**Purpose**: Validated inputs for the `review` command.

```python
@dataclass(frozen=True, slots=True)
class ReviewCommandInputs:
    """Inputs for review command execution.

    Attributes:
        pr_number: Pull request number to review.
        fix: Automatically apply suggested fixes.
        output_format: Output format (tui, json, markdown, text).
    """
    pr_number: int
    fix: bool = False
    output_format: OutputFormat = OutputFormat.TUI
```

---

## Relationships

```
CLIContext (1) ----contains----> (1) MaverickConfig
     |
     +-- passed to --> FlyCommandInputs --> FlyInputs --> FlyWorkflow
     +-- passed to --> RefuelCommandInputs --> RefuelInputs --> RefuelWorkflow
     +-- passed to --> ReviewCommandInputs --> CodeReviewerAgent
```

---

## Entity Summary

| Entity | Type | Location | Purpose |
|--------|------|----------|---------|
| CLIContext | @dataclass | cli/context.py | Global options wrapper |
| ExitCode | IntEnum | cli/context.py | Exit code constants |
| OutputFormat | str Enum | cli/output.py | Output format choices |
| DependencyStatus | @dataclass | cli/validators.py | Dependency check result |
| FlyCommandInputs | @dataclass | cli/context.py | Fly command inputs |
| RefuelCommandInputs | @dataclass | cli/context.py | Refuel command inputs |
| ReviewCommandInputs | @dataclass | cli/context.py | Review command inputs |

---

## Existing Entities (No Changes)

These entities from existing modules are used but not modified:

| Entity | Module | Usage |
|--------|--------|-------|
| MaverickConfig | config.py | Root configuration |
| FlyInputs | workflows/fly.py | Workflow inputs |
| FlyConfig | workflows/fly.py | Workflow config |
| RefuelInputs | workflows/refuel.py | Workflow inputs |
| RefuelConfig | workflows/refuel.py | Workflow config |
| MaverickError | exceptions.py | Base exception |
| ConfigError | exceptions.py | Config validation errors |
