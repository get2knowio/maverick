# Implementation Plan: Refuel Maverick Method — Native Flight Plan Decomposition

**Branch**: `038-refuel-maverick-method` | **Date**: 2026-02-27 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/038-refuel-maverick-method/spec.md`

## Summary

Implement `maverick refuel maverick <flight-plan-path>` as a PythonWorkflow subclass that reads a Maverick Flight Plan file, gathers codebase context for in-scope files, executes a decomposition agent via StepExecutor to produce an ordered set of WorkUnit models, writes them to disk as Markdown files, and creates beads (one epic + task beads with dependency wiring) for consumption by `maverick fly`. The workflow follows the existing RefuelSpeckitWorkflow pattern — sequential steps with progress events, dry-run support, and typed result contracts.

## Technical Context

**Language/Version**: Python 3.10+ (with `from __future__ import annotations`)
**Primary Dependencies**: Claude Agent SDK (`claude-agent-sdk`), Click, Rich, Pydantic, pathlib, structlog, tenacity
**Storage**: Markdown+YAML files on disk (`.maverick/work-units/<name>/`), beads via `bd` CLI
**Testing**: pytest + pytest-asyncio (parallel via xdist, `make test-fast`)
**Target Platform**: Linux/macOS CLI
**Project Type**: Single project (Python package `src/maverick/`)
**Performance Goals**: Decomposition completes in a single agent invocation; no streaming latency requirements
**Constraints**: Agent retry ≤ 2 attempts with exponential backoff; work unit count soft-guided at 3-15
**Scale/Scope**: Simple flight plans (3-5 work units) to complex (10+ with parallel groups and dependencies)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Guardrail | Status | Notes |
|-----------|--------|-------|
| I. Async-First | PASS | All workflow steps async; FlightPlanFile.aload(), WorkUnitFile.asave() used; StepExecutor.execute() is async |
| II. Separation of Concerns | PASS | Workflow orchestrates; agent provides judgment (decomposition); deterministic steps (file I/O, bead creation) owned by workflow |
| III. Dependency Injection | PASS | Workflow receives config, registry, step_executor via constructor; no global state |
| IV. Fail Gracefully | PASS | Agent retries via tenacity (2 attempts); non-fatal warnings for uncovered SC; bead creation errors collected |
| V. Test-First | PASS | Tests planned with fixture flight plans for simple and complex cases |
| VI. Type Safety | PASS | Frozen dataclass for result; Pydantic models for WorkUnit/FlightPlan; StepExecutor with output_schema |
| VII. Simplicity & DRY | PASS | Reuses existing FlightPlanFile, WorkUnitFile, BeadClient, bead actions; no new abstractions beyond workflow + actions |
| VIII. Relentless Progress | PASS | Agent retry with backoff; partial work preserved (work units written before bead creation) |
| IX. Hardening by Default | PASS | Tenacity for agent retries; explicit timeouts via BeadClient (30s); structured error types |
| X.4 Typed contracts | PASS | RefuelMaverickResult frozen dataclass with to_dict() |
| X.6 One canonical wrapper | PASS | Uses existing BeadClient, FlightPlanFile, WorkUnitFile — no new wrappers |
| X.8 Canonical libraries | PASS | structlog for logging, tenacity for retries, GitPython for reads |
| XI. Modularize Early | PASS | Package-per-workflow pattern; separate actions module; <500 LOC per module expected |
| XII. Ownership | PASS | Full test coverage; all edge cases handled |

## Project Structure

### Documentation (this feature)

```text
specs/038-refuel-maverick-method/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
└── tasks.md             # Phase 2 output (via /speckit.tasks)
```

### Source Code (repository root)

```text
src/maverick/
├── cli/commands/refuel/
│   ├── _group.py                     # Existing refuel group (unchanged)
│   ├── speckit.py                    # Existing speckit command (unchanged)
│   └── maverick_cmd.py               # NEW: maverick subcommand
├── workflows/refuel_maverick/
│   ├── __init__.py                   # NEW: package exports
│   ├── constants.py                  # NEW: step name constants
│   ├── models.py                     # NEW: RefuelMaverickResult dataclass
│   └── workflow.py                   # NEW: RefuelMaverickWorkflow(PythonWorkflow)
├── library/actions/
│   ├── beads.py                      # EXISTING: reuse create_beads, wire_dependencies
│   ├── review.py                     # EXISTING: reference for context gathering pattern
│   └── decompose.py                  # NEW: decomposition-specific actions
└── flight/
    ├── models.py                     # EXISTING: FlightPlan, WorkUnit (unchanged)
    ├── loader.py                     # EXISTING: FlightPlanFile, WorkUnitFile (unchanged)
    ├── parser.py                     # EXISTING: parse functions (unchanged)
    └── serializer.py                 # EXISTING: serialize_work_unit (unchanged)

tests/unit/
├── workflows/refuel_maverick/
│   ├── conftest.py                   # NEW: fixture flight plans, mock step executor
│   ├── test_workflow.py              # NEW: workflow integration tests
│   └── test_workflow_edge_cases.py   # NEW: error paths, validation failures
├── library/actions/
│   └── test_decompose.py             # NEW: decomposition action unit tests
└── cli/commands/refuel/
    └── test_maverick_cmd.py          # NEW: CLI command tests
```

**Structure Decision**: Package-per-workflow pattern (`src/maverick/workflows/refuel_maverick/`) matching the existing `refuel_speckit` package structure. CLI command in `src/maverick/cli/commands/refuel/maverick_cmd.py` (suffixed `_cmd` to avoid collision with the `maverick` package name). New decomposition actions in `src/maverick/library/actions/decompose.py` to keep bead-specific vs decomposition-specific logic separated.

## Complexity Tracking

No constitution violations. No complexity justifications needed.
