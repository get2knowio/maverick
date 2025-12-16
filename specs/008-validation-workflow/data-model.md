# Data Model: Validation Workflow

**Feature**: 008-validation-workflow
**Date**: 2025-12-15

## Entity Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         ValidationWorkflow                                   │
│  Orchestrates validation stages with fix attempts and progress updates       │
├─────────────────────────────────────────────────────────────────────────────┤
│  - stages: list[ValidationStage]                                            │
│  - fix_agent: MaverickAgent | None                                          │
│  - config: ValidationWorkflowConfig                                         │
│  + run() -> AsyncIterator[ProgressUpdate]                                   │
│  + cancel() -> None                                                         │
│  + get_result() -> ValidationWorkflowResult                                 │
└───────────────────────────┬─────────────────────────────────────────────────┘
                            │ orchestrates
                            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         ValidationStage                                      │
│  Configuration for a single validation step                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│  - name: str              # "format", "lint", "build", "test"               │
│  - command: list[str]     # ["ruff", "format", "."]                         │
│  - fixable: bool          # True if fix agent can attempt repairs           │
│  - max_fix_attempts: int  # 0 = non-fixable, default 3                      │
│  - timeout_seconds: float # Per-command timeout (default 300s)              │
└───────────────────────────┬─────────────────────────────────────────────────┘
                            │ produces
                            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         StageResult                                          │
│  Outcome of running a single stage                                           │
├─────────────────────────────────────────────────────────────────────────────┤
│  - stage_name: str        # References ValidationStage.name                 │
│  - status: StageStatus    # PASSED, FAILED, FIXED, CANCELLED                │
│  - fix_attempts: int      # Number of fix attempts made                     │
│  - error_message: str?    # Final error if failed                           │
│  - output: str            # Command stdout/stderr                           │
│  - duration_ms: int       # Total stage time including retries              │
└───────────────────────────┬─────────────────────────────────────────────────┘
                            │ aggregates into
                            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     ValidationWorkflowResult                                 │
│  Complete workflow outcome                                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│  - success: bool          # True if all stages passed                       │
│  - stage_results: list[StageResult]  # Per-stage breakdown                  │
│  - cancelled: bool        # True if workflow was cancelled                  │
│  - total_duration_ms: int # Total workflow execution time                   │
│  - metadata: dict         # Additional context                              │
└─────────────────────────────────────────────────────────────────────────────┘

Side-channel emissions during run():

┌─────────────────────────────────────────────────────────────────────────────┐
│                         ProgressUpdate                                       │
│  Event emitted during workflow execution                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│  - stage: str             # Current stage name                              │
│  - status: StageStatus    # Current status                                  │
│  - message: str           # Human-readable context                          │
│  - fix_attempt: int       # Current fix attempt number (0 = first run)      │
│  - timestamp: float       # Unix timestamp                                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Entity Definitions

### StageStatus (Enum)

Status of a validation stage during or after execution.

| Value | Description |
|-------|-------------|
| `PENDING` | Stage not yet started |
| `IN_PROGRESS` | Stage currently executing |
| `PASSED` | Stage completed successfully on first attempt |
| `FAILED` | Stage failed after exhausting all fix attempts |
| `FIXED` | Stage passed after one or more fix attempts |
| `CANCELLED` | Stage terminated due to workflow cancellation |

**State Transitions**:
```
PENDING → IN_PROGRESS → PASSED
                      → FIXED (via fix attempts)
                      → FAILED
                      → CANCELLED
```

### ValidationStage

Configuration for a single validation step.

| Field | Type | Default | Validation | Description |
|-------|------|---------|------------|-------------|
| `name` | `str` | required | `min_length=1` | Stage identifier (e.g., "format", "lint") |
| `command` | `list[str]` | required | `min_length=1` | Command and arguments to execute |
| `fixable` | `bool` | `True` | - | Whether fix agent can attempt repairs |
| `max_fix_attempts` | `int` | `3` | `ge=0` | Max fix attempts; 0 = non-fixable |
| `timeout_seconds` | `float` | `300.0` | `gt=0` | Per-command timeout |

**Invariants**:
- If `max_fix_attempts == 0`, stage is treated as non-fixable regardless of `fixable`
- `command[0]` must be an executable available in PATH

**Example**:
```python
ValidationStage(
    name="lint",
    command=["ruff", "check", "--fix", "."],
    fixable=True,
    max_fix_attempts=3,
    timeout_seconds=120.0,
)
```

### StageResult

Outcome of running a single validation stage.

| Field | Type | Default | Validation | Description |
|-------|------|---------|------------|-------------|
| `stage_name` | `str` | required | - | Stage identifier |
| `status` | `StageStatus` | required | - | Final status |
| `fix_attempts` | `int` | `0` | `ge=0` | Total fix attempts made |
| `error_message` | `str \| None` | `None` | - | Error if failed |
| `output` | `str` | `""` | - | Combined stdout/stderr |
| `duration_ms` | `int` | `0` | `ge=0` | Total time including retries |

**Computed Properties**:
- `was_fixed: bool` - True if `status == FIXED`
- `passed: bool` - True if `status in (PASSED, FIXED)`

### ValidationWorkflowResult

Complete workflow execution result.

| Field | Type | Default | Validation | Description |
|-------|------|---------|------------|-------------|
| `success` | `bool` | required | - | All stages passed |
| `stage_results` | `list[StageResult]` | required | - | Per-stage outcomes |
| `cancelled` | `bool` | `False` | - | Workflow was cancelled |
| `total_duration_ms` | `int` | `0` | `ge=0` | Total workflow time |
| `metadata` | `dict[str, Any]` | `{}` | - | Additional context |

**Computed Properties**:
- `passed_count: int` - Count of stages with status PASSED or FIXED
- `failed_count: int` - Count of stages with status FAILED
- `stages_summary: str` - Human-readable summary (e.g., "3/4 passed, 1 failed")

### ProgressUpdate

Progress event emitted during workflow execution.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `stage` | `str` | required | Current stage name |
| `status` | `StageStatus` | required | Current status |
| `message` | `str` | `""` | Human-readable context |
| `fix_attempt` | `int` | `0` | Current attempt (0 = first run) |
| `timestamp` | `float` | `time.time()` | Unix timestamp |

**Note**: Implemented as `@dataclass(slots=True, frozen=True)` for performance.

### ValidationWorkflowConfig

Configuration options for workflow execution.

| Field | Type | Default | Validation | Description |
|-------|------|---------|------------|-------------|
| `dry_run` | `bool` | `False` | - | Report without executing |
| `stop_on_failure` | `bool` | `False` | - | Stop at first stage failure |
| `cwd` | `Path \| None` | `None` | - | Working directory |

### ValidationWorkflow

The orchestrator class (not a Pydantic model).

| Field | Type | Description |
|-------|------|-------------|
| `_stages` | `list[ValidationStage]` | Stages to execute |
| `_fix_agent` | `MaverickAgent \| None` | Agent for fix attempts |
| `_config` | `ValidationWorkflowConfig` | Workflow configuration |
| `_cancel_event` | `asyncio.Event` | Cancellation signal |
| `_result` | `ValidationWorkflowResult \| None` | Cached result |

**Methods**:
- `__init__(stages, fix_agent?, config?)` - Initialize workflow
- `async run() -> AsyncIterator[ProgressUpdate]` - Execute and stream progress
- `cancel() -> None` - Request cancellation
- `get_result() -> ValidationWorkflowResult` - Get final result (after run completes)

## Default Stage Configurations

### Python (Default)

```python
DEFAULT_PYTHON_STAGES = [
    ValidationStage(
        name="format",
        command=["ruff", "format", "."],
        fixable=True,
        max_fix_attempts=2,
        timeout_seconds=60.0,
    ),
    ValidationStage(
        name="lint",
        command=["ruff", "check", "--fix", "."],
        fixable=True,
        max_fix_attempts=3,
        timeout_seconds=120.0,
    ),
    ValidationStage(
        name="typecheck",
        command=["mypy", "."],
        fixable=True,
        max_fix_attempts=2,
        timeout_seconds=300.0,
    ),
    ValidationStage(
        name="test",
        command=["pytest", "-x", "--tb=short"],
        fixable=False,
        max_fix_attempts=0,
        timeout_seconds=300.0,
    ),
]
```

## Relationships

```
MaverickAgent (abstract)
    ↑
    │ (fix_agent)
    │
ValidationWorkflow ───────→ ValidationStage (1..*)
    │                             │
    │                             ▼
    │                       StageResult
    │                             │
    ▼                             ▼
ProgressUpdate (*)        ValidationWorkflowResult
```

## File Location

All models defined in `src/maverick/models/validation.py`:

```python
# src/maverick/models/validation.py
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any
import time

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "StageStatus",
    "ValidationStage",
    "StageResult",
    "ValidationWorkflowResult",
    "ValidationWorkflowConfig",
    "ProgressUpdate",
    "DEFAULT_PYTHON_STAGES",
]

# ... model definitions ...
```

Workflow class in `src/maverick/workflows/validation.py`:

```python
# src/maverick/workflows/validation.py
from __future__ import annotations

from collections.abc import AsyncIterator
import asyncio

from maverick.agents.base import MaverickAgent
from maverick.models.validation import (
    ProgressUpdate,
    StageResult,
    StageStatus,
    ValidationStage,
    ValidationWorkflowConfig,
    ValidationWorkflowResult,
)

__all__ = ["ValidationWorkflow"]

# ... workflow implementation ...
```
