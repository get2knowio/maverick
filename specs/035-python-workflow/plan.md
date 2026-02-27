# Implementation Plan: Python-Native Workflow Definitions

**Branch**: `035-python-workflow` | **Date**: 2026-02-26 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/035-python-workflow/spec.md`

## Summary

Replace the YAML DSL as the primary execution path for Maverick's opinionated workflows (`fly-beads`, `refuel-speckit`) with Python-native workflow classes. A `PythonWorkflow` abstract base class provides configuration resolution, progress event emission, step tracking, rollback registration, and checkpointing. Concrete subclasses implement `execute()` as async generators yielding `ProgressEvent`s, using native Python control flow. The YAML DSL remains fully functional for user-authored workflows.

## Technical Context

**Language/Version**: Python 3.10+ (with `from __future__ import annotations`)
**Primary Dependencies**: Claude Agent SDK (`claude-agent-sdk`), Click, Rich, Pydantic, PyYAML, structlog, tenacity, GitPython
**Storage**: JSON files under `~/.maverick/checkpoints/` via `FileCheckpointStore`
**Testing**: pytest + pytest-asyncio (parallel via xdist `-n auto`)
**Target Platform**: Linux CLI
**Project Type**: Single (CLI application)
**Performance Goals**: N/A (CLI tool, no latency targets beyond existing behavior)
**Constraints**: Must emit identical `ProgressEvent` types consumed by CLI renderer; must not break existing YAML workflow execution
**Scale/Scope**: 2 concrete workflows (`fly-beads`, `refuel-speckit`), 1 abstract base class, CLI routing changes for 2 commands

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| # | Principle | Status | Notes |
|---|-----------|--------|-------|
| I | Async-First | PASS | `execute()` returns `AsyncGenerator[ProgressEvent, None]`; all action calls async |
| II | Separation of Concerns | PASS | Workflows orchestrate; agents provide judgment via `StepExecutor`; no TUI changes |
| III | Dependency Injection | PASS | `MaverickConfig`, `ComponentRegistry`, `CheckpointStore`, `StepExecutor` all injected at construction |
| IV | Fail Gracefully | PASS | Per-bead error isolation; workspace-level rollback; partial results preserved |
| V | Test-First | PASS | Standard pytest patterns; mock registry/config; no YAML fixtures required (FR-010) |
| VI | Type Safety | PASS | Reuses existing `WorkflowResult`, `StepResult`, `ProgressEvent` frozen dataclasses; `StepConfig` via Pydantic |
| VII | Simplicity & DRY | PASS | Direct Python control flow eliminates YAML expression evaluation; reuses all existing actions |
| VIII | Relentless Progress | PASS | Per-bead checkpointing via `CheckpointStore`; resume skips completed beads |
| IX | Hardening | PASS | Delegates to existing hardened actions (tenacity retries, timeouts); no new external calls |
| X.1 | TUI display-only | N/A | No TUI changes |
| X.2 | Async-first (no blocking) | PASS | All methods async; delegates subprocess to `CommandRunner` via actions |
| X.3 | Deterministic ops in workflows | PASS | Python workflows own all deterministic execution (commits, validation, checkpoints) |
| X.4 | Typed contracts | PASS | `WorkflowResult`, `StepResult` reused; no `dict[str, Any]` returns |
| X.5 | Real resilience | PASS | Fix loops delegate to existing `run_fix_retry_loop` action |
| X.6 | One canonical wrapper | PASS | Reuses existing `maverick.library.actions.*`; no new wrappers |
| X.7 | Async-safe factories | PASS | No `asyncio.run()` in any factory |
| X.8 | Canonical libraries | PASS | structlog, tenacity, GitPython, PyGithub — all canonical |
| X.9 | TUI streaming | PASS | Emits same `ProgressEvent` types; CLI renderer unchanged |
| X.10 | Branch naming | PASS | `035-python-workflow` follows convention |
| X.11 | Workspace isolation | PASS | `cwd` passed explicitly to all workspace-bound actions |
| X.12 | DSL expression coercion | N/A | Python workflows use native Python types; no `${{ }}` expressions |
| XI | Modularize Early | PASS | Package-per-workflow: `src/maverick/workflows/fly_beads/`, `src/maverick/workflows/refuel_speckit/` |
| XII | Ownership | PASS | Full ownership; fix collateral issues encountered |

**Gate Result**: PASS — No violations. Proceed to Phase 0.

## Project Structure

### Documentation (this feature)

```text
specs/035-python-workflow/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── python_workflow_protocol.py  # Interface contracts
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
src/maverick/
├── workflows/
│   ├── __init__.py              # Re-exports: PythonWorkflow, FlyBeadsWorkflow, RefuelSpeckitWorkflow
│   ├── base.py                  # PythonWorkflow ABC (~200 LOC)
│   ├── fly_beads/
│   │   ├── __init__.py          # Export FlyBeadsWorkflow
│   │   ├── workflow.py          # FlyBeadsWorkflow implementation (~400 LOC)
│   │   └── constants.py         # Step names, default config values
│   └── refuel_speckit/
│       ├── __init__.py          # Export RefuelSpeckitWorkflow
│       ├── workflow.py          # RefuelSpeckitWorkflow implementation (~250 LOC)
│       └── constants.py         # Step names, default config values
├── cli/
│   ├── commands/
│   │   ├── fly/_group.py        # Modified: instantiate FlyBeadsWorkflow directly
│   │   └── refuel/speckit.py    # Modified: instantiate RefuelSpeckitWorkflow directly
│   └── workflow_executor.py     # Modified: add execute_python_workflow() helper
└── dsl/
    └── executor/
        └── config.py            # No changes (resolve_step_config reused as-is)

tests/
├── unit/
│   └── workflows/
│       ├── __init__.py
│       ├── test_python_workflow_base.py     # PythonWorkflow ABC tests (~300 LOC)
│       ├── test_fly_beads_workflow.py       # FlyBeadsWorkflow unit tests (~400 LOC)
│       └── test_refuel_speckit_workflow.py  # RefuelSpeckitWorkflow unit tests (~250 LOC)
└── conftest.py                              # Shared workflow test fixtures
```

**Structure Decision**: Package-per-workflow under `src/maverick/workflows/` as prescribed by Constitution Appendix A. The existing `__init__.py` already exists (currently marks legacy workflows as removed). The `base.py` module is kept separate from concrete workflows to enforce single-responsibility. Each concrete workflow gets its own package with `workflow.py` (main logic), `constants.py` (step names, defaults), and `__init__.py` (re-exports).

## Key Implementation Notes

- **RollbackAction type**: The existing `RollbackAction` in `dsl/types.py` takes `WorkflowContext`, which Python workflows don't have. Define `PythonRollbackAction = Callable[[], Awaitable[None]]` in `base.py` as the rollback callable type for Python workflows. Do NOT reuse the DSL's `RollbackAction`.
- **WorkflowResult communication**: The `WorkflowCompleted` event does NOT embed a `WorkflowResult` (it only has `workflow_name`, `success`, `total_duration_ms`, `timestamp`). The `execute()` template method stores the aggregated `WorkflowResult` as `self.result` after the generator completes. Callers access `workflow.result` after iterating the generator.
- **step_path field**: YAML events use `step_path` for nested paths (e.g., `workflow.step`). Python workflow events should set `step_path` to `{workflow_name}.{step_name}` for consistency.
- **Event rendering extraction (T014)**: The inline event dispatch in `workflow_executor.py` (~lines 303-469) does NOT handle `StepOutput`, `LoopIteration*`, or `CheckpointSaved` events. The extracted `render_workflow_events()` MUST add `StepOutput` handling at minimum since Python workflows depend on `emit_output()`.
- **StepConfig import path**: `StepConfig` is NOT exported from `maverick.dsl.executor.__init__` — only the alias `StepExecutorConfig` is. Import directly from `maverick.dsl.executor.config`.
- **Action imports**: FlyBeadsWorkflow and RefuelSpeckitWorkflow import action functions directly (e.g., `from maverick.library.actions.preflight import run_preflight_checks`) for type safety, while using `self.registry` only for dynamic dispatch (agent lookup).

## Complexity Tracking

No constitution violations — this section is intentionally empty.
