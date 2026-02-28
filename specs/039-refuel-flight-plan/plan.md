# Implementation Plan: Refuel Flight-Plan Subcommand

**Branch**: `039-refuel-flight-plan` | **Date**: 2026-02-28 | **Spec**: `specs/039-refuel-flight-plan/spec.md`
**Input**: Feature specification from `/specs/039-refuel-flight-plan/spec.md`

## Summary

Add a `maverick refuel flight-plan` CLI subcommand that accepts a path to a Maverick Flight Plan Markdown file and delegates to the existing `RefuelMaverickWorkflow` (spec 038) for decomposition into work units and beads. This is a thin CLI entry point — the workflow, models, and actions already exist; only a new Click command and its tests are needed.

## Technical Context

**Language/Version**: Python 3.10+ (with `from __future__ import annotations`)
**Primary Dependencies**: Click (CLI), Rich (console output), RefuelMaverickWorkflow (workflow engine)
**Storage**: N/A (reuses existing `.maverick/work-units/{plan-name}/` convention)
**Testing**: pytest + pytest-asyncio (parallel via xdist)
**Target Platform**: Linux (dev container)
**Project Type**: Single — CLI command addition within existing package
**Performance Goals**: N/A (inherits from workflow)
**Constraints**: Must not modify existing `refuel speckit` or `refuel maverick` commands (FR-012)
**Scale/Scope**: ~2 new source files, ~2 new test files

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Async-First | PASS | Uses `@async_command` + `execute_python_workflow()` (async) |
| II. Separation of Concerns | PASS | CLI command is display/delegation only; workflow owns logic |
| III. Dependency Injection | PASS | Reuses `execute_python_workflow()` which injects config/registry/executor |
| IV. Fail Gracefully | PASS | Inherits workflow error handling; CLI uses `cli_error_handler()` |
| V. Test-First | PASS | CLI tests planned; workflow tests already exist |
| VI. Type Safety | PASS | Typed Click decorators; `PythonWorkflowRunConfig` dataclass |
| VII. Simplicity & DRY | PASS | Reuses existing workflow — no duplication of decomposition logic |
| VIII. Relentless Progress | PASS | Inherited from workflow |
| IX. Hardening | PASS | Inherited from workflow (retries, timeouts) |
| X. Guardrails | PASS | No new subprocess calls; canonical library usage preserved |
| XI. Modularize Early | PASS | Single-file command module (~50 LOC) well under thresholds |
| XII. Ownership | PASS | Full test coverage for new code |

**Gate result**: PASS — no violations.

## Project Structure

### Documentation (this feature)

```text
specs/039-refuel-flight-plan/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
└── quickstart.md        # Phase 1 output
```

### Source Code (repository root)

```text
src/maverick/cli/commands/refuel/
├── __init__.py              # MODIFY — add flight_plan import for registration
├── _group.py                # UNCHANGED
├── speckit.py               # UNCHANGED
├── maverick_cmd.py          # UNCHANGED
└── flight_plan.py           # CREATE — new Click command

src/maverick/workflows/refuel_maverick/
├── __init__.py              # UNCHANGED
├── constants.py             # UNCHANGED
├── models.py                # UNCHANGED
└── workflow.py              # UNCHANGED

tests/unit/cli/commands/refuel/
├── __init__.py              # UNCHANGED
├── test_maverick_cmd.py     # UNCHANGED
└── test_flight_plan.py      # CREATE — CLI command tests
```

**Structure Decision**: Single project layout. The new command is a single module (`flight_plan.py`) in the existing `src/maverick/cli/commands/refuel/` package. No new workflow, models, or actions are needed — everything is reused from spec 038.

## Complexity Tracking

No constitution violations. No complexity justifications needed.

## Phase 0: Research

### Key Decision: Reuse vs. New Workflow

**Decision**: Reuse `RefuelMaverickWorkflow` directly.

**Rationale**: The existing `RefuelMaverickWorkflow` already implements the full pipeline (parse flight plan → gather context → decompose → validate → write work units → create beads → wire deps). The `refuel flight-plan` command has identical functional requirements. Creating a separate workflow would violate DRY (Principle VII).

**Alternatives considered**:
- New `RefuelFlightPlanWorkflow` class: Rejected — would duplicate all 7 steps with no behavioral difference
- Wrapper workflow: Rejected — unnecessary indirection for identical behavior

### Key Decision: Command Name Registration

**Decision**: Register as `@refuel.command("flight-plan")` with function name `flight_plan_cmd`.

**Rationale**: Click supports hyphens in command names via the `name` parameter. Using `flight-plan` (with hyphen) matches the spec and is consistent with CLI conventions. The Python function name uses underscore (`flight_plan_cmd`) since hyphens are invalid in Python identifiers. This follows the same pattern as `@refuel.command("maverick")` → `maverick_cmd`.

### Key Decision: Argument Naming

**Decision**: Use `FLIGHT-PLAN-PATH` as the metavar (identical to `refuel maverick`).

**Rationale**: Exact same argument semantics — a path to a flight plan Markdown file. Consistent metavar aids user understanding across related commands.

## Phase 1: Design

### Data Model

No new data models needed. The feature reuses:

- `FlightPlan` (from `maverick.flight.models`) — parsed by workflow step 1
- `WorkUnit` (from `maverick.flight.models`) — produced by workflow step 5
- `DecompositionOutput` (from `maverick.workflows.refuel_maverick.models`) — agent output schema
- `RefuelMaverickResult` (from `maverick.workflows.refuel_maverick.models`) — workflow result
- `PythonWorkflowRunConfig` (from `maverick.cli.workflow_executor`) — CLI→workflow config

### API Contract

**CLI Interface**:
```
maverick refuel flight-plan FLIGHT-PLAN-PATH [OPTIONS]

Arguments:
  FLIGHT-PLAN-PATH    Path to the flight plan Markdown file (required)

Options:
  --dry-run           Write work unit files but skip bead creation
  --list-steps        List workflow steps and exit without executing
  --session-log PATH  Write session journal (JSONL) to this file path
  --help              Show this message and exit
```

**Workflow Inputs** (passed via `PythonWorkflowRunConfig.inputs`):
```python
{
    "flight_plan_path": str,  # Resolved path string
    "dry_run": bool,          # Default False
}
```

**Workflow Output**: `RefuelMaverickResult.to_dict()` — already defined.

### Implementation Details

#### 1. CLI Command Module (`src/maverick/cli/commands/refuel/flight_plan.py`)

Pattern: Mirror `maverick_cmd.py` exactly with these differences:
- Command name: `"flight-plan"` (hyphenated)
- Function name: `flight_plan_cmd`
- Docstring/help text: Tailored to "flight-plan" terminology
- Step list constant: `_REFUEL_FLIGHT_PLAN_STEPS` (same values as `_REFUEL_MAVERICK_STEPS`)
- Workflow class: `RefuelMaverickWorkflow` (same)
- Workflow name constant: Reuse `WORKFLOW_NAME` from `refuel_maverick.constants`

The command follows the exact pattern of the existing `refuel maverick` command:

```python
@refuel.command("flight-plan")
@click.argument("flight_plan_path", metavar="FLIGHT-PLAN-PATH", type=click.Path(...))
@click.option("--dry-run", ...)
@click.option("--list-steps", ...)
@click.option("--session-log", ...)
@click.pass_context
@async_command
async def flight_plan_cmd(ctx, flight_plan_path, dry_run, list_steps, session_log):
    ...
```

#### 2. Registration (`src/maverick/cli/commands/refuel/__init__.py`)

Add one import line to register the new subcommand on the `refuel` group:

```python
from maverick.cli.commands.refuel import flight_plan as _flight_plan  # noqa: F401
```

#### 3. Tests (`tests/unit/cli/commands/refuel/test_flight_plan.py`)

Mirror `test_maverick_cmd.py` test structure:

| Test | Purpose |
|------|---------|
| `test_flight_plan_in_refuel_help` | Verify `flight-plan` appears in `refuel --help` |
| `test_missing_flight_plan_arg` | Required argument validation |
| `test_list_steps_prints_step_names_and_exits` | `--list-steps` shows all 7 steps and exits 0 |
| `test_delegates_to_refuel_maverick_workflow` | Normal execution uses `RefuelMaverickWorkflow` |
| `test_dry_run_flag_passed_to_workflow` | `--dry-run` is forwarded as input |
| `test_dry_run_is_false_by_default` | Default `dry_run=False` |
| `test_flight_plan_path_passed_as_string` | Path argument is forwarded as string |
| `test_session_log_passed_to_run_config` | `--session-log` goes to config |
| `test_help_shows_correct_options` | Help text includes all options |

### Quickstart

After implementation, users will run:

```bash
# Decompose a flight plan into work units and beads
maverick refuel flight-plan .maverick/flight-plans/add-auth.md

# Preview decomposition without creating beads
maverick refuel flight-plan .maverick/flight-plans/add-auth.md --dry-run

# List workflow steps
maverick refuel flight-plan .maverick/flight-plans/add-auth.md --list-steps

# Save session log for debugging
maverick refuel flight-plan .maverick/flight-plans/add-auth.md --session-log ./session.jsonl
```

## Post-Design Constitution Re-Check

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Async-First | PASS | `@async_command` + `execute_python_workflow()` |
| II. Separation of Concerns | PASS | CLI delegates to workflow; no business logic in command |
| VII. Simplicity & DRY | PASS | Single-file command (~50 LOC); reuses existing workflow entirely |
| X.8 Canonical Libraries | PASS | No new libraries; Click + Rich as established |
| XI. Modularize Early | PASS | ~50 LOC new module; ~100 LOC test file |

**Gate result**: PASS — design is constitution-compliant.
