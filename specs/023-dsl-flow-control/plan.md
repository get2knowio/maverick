# Implementation Plan: Workflow DSL Flow Control

**Branch**: `023-dsl-flow-control` | **Date**: 2025-12-20 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/023-dsl-flow-control/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Extend the Maverick Workflow DSL (spec 022) with flow control constructs: conditional execution (`.when()`), branching (`.branch()`), retry with backoff (`.retry()`), parallel interface (`.parallel()`), error handling (`.on_error()`, `.skip_on_error()`), rollback support (`.with_rollback()`), and checkpointing/resumability (`.checkpoint()`, `Workflow.resume()`). The implementation follows the existing generator-based execution pattern, extending StepBuilder with fluent methods and adding new step wrappers that compose with existing step types.

## Technical Context

**Language/Version**: Python 3.10+ (with `from __future__ import annotations`)
**Primary Dependencies**: claude-agent-sdk, pydantic, asyncio (stdlib), pathlib (stdlib), hashlib (stdlib), json (stdlib)
**Storage**: JSON files under `.maverick/checkpoints/` for checkpoint persistence
**Testing**: pytest + pytest-asyncio (all tests async-compatible)
**Target Platform**: Linux/macOS (CLI/TUI application)
**Project Type**: Single project (extends existing DSL module)
**Performance Goals**: N/A (workflow execution is I/O-bound by agent operations)
**Constraints**: Checkpoints must be atomic (write to temp file, then rename)
**Scale/Scope**: Workflows with 10-100 steps, checkpoint files <10MB each

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Pre-Design Check

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Async-First | ✅ PASS | All step execution already async; new wrappers will be async |
| II. Separation of Concerns | ✅ PASS | Flow control remains in DSL module; no TUI/agent leakage |
| III. Dependency Injection | ✅ PASS | CheckpointStore injected via WorkflowConfig |
| IV. Fail Gracefully, Recover Aggressively | ✅ PASS | Rollbacks run best-effort; retry with backoff built-in |
| V. Test-First | ✅ PASS | Unit tests for each new construct required |
| VI. Type Safety | ✅ PASS | Frozen dataclasses, complete type annotations |
| VII. Simplicity | ✅ PASS | Composes with existing step pattern; no new god-classes |
| VIII. Relentless Progress | ✅ PASS | Checkpointing enables resumption; rollbacks preserve state |

### Post-Design Re-evaluation (2025-12-20)

| Principle | Status | Design Evidence |
|-----------|--------|-----------------|
| I. Async-First | ✅ PASS | All predicates support both sync and async callables. RetryStep uses `asyncio.sleep()`. CheckpointStore protocol is fully async. |
| II. Separation of Concerns | ✅ PASS | Flow control wrappers only handle execution logic. CheckpointStore is a protocol (injectable). No TUI/agent code in DSL. |
| III. Dependency Injection | ✅ PASS | `WorkflowEngine.__init__` accepts `checkpoint_store` parameter. `MemoryCheckpointStore` for testing. |
| IV. Fail Gracefully, Recover Aggressively | ✅ PASS | `.skip_on_error()` converts failures to skips. Rollbacks continue on error. Retry with exponential backoff. |
| V. Test-First | ✅ PASS | Test files defined in project structure. `MemoryCheckpointStore` enables isolated testing. |
| VI. Type Safety | ✅ PASS | All new types are frozen dataclasses with slots. `Predicate` and `RollbackAction` type aliases defined. Protocol for `CheckpointStore`. |
| VII. Simplicity | ✅ PASS | No external dependencies added (no tenacity/backoff). Wrapper pattern reuses existing step execution. JSON for checkpoints (human-readable). |
| VIII. Relentless Progress | ✅ PASS | Checkpointing enables resume from any marked point. Rollbacks preserve completed work. Best-effort rollback continues on failure. |

**Gate Status: PASS** - All principles satisfied. No violations requiring justification.

## Project Structure

### Documentation (this feature)

```text
specs/023-dsl-flow-control/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
src/maverick/dsl/
├── __init__.py                 # Updated exports
├── builder.py                  # Extended with flow control methods
├── context.py                  # WorkflowContext (minor updates for rollback tracking)
├── engine.py                   # Extended execution loop for rollbacks/checkpoints
├── events.py                   # New events: RollbackStarted, RollbackCompleted, CheckpointSaved
├── results.py                  # Extended with skip markers, branch results
├── types.py                    # New types: Predicate, RollbackAction, BranchOption
├── steps/
│   ├── __init__.py             # Updated exports
│   ├── base.py                 # StepDefinition (unchanged)
│   ├── conditional.py          # NEW: ConditionalStep wrapper (.when())
│   ├── branch.py               # NEW: BranchStep (.branch())
│   ├── retry.py                # NEW: RetryStep wrapper (.retry())
│   ├── parallel.py             # NEW: ParallelStep (.parallel())
│   ├── error_handler.py        # NEW: ErrorHandlerStep (.on_error(), .skip_on_error())
│   ├── rollback.py             # NEW: RollbackStep wrapper (.with_rollback())
│   └── checkpoint.py           # NEW: CheckpointStep (.checkpoint())
├── checkpoint/
│   ├── __init__.py             # CheckpointStore, FileCheckpointStore
│   ├── store.py                # CheckpointStore protocol + FileCheckpointStore
│   └── data.py                 # CheckpointData dataclass
└── errors.py                   # NEW: WorkflowError exception

tests/unit/dsl/
├── steps/
│   ├── test_conditional.py     # NEW
│   ├── test_branch.py          # NEW
│   ├── test_retry.py           # NEW
│   ├── test_parallel.py        # NEW
│   ├── test_error_handler.py   # NEW
│   ├── test_rollback.py        # NEW
│   └── test_checkpoint.py      # NEW
├── checkpoint/
│   ├── test_store.py           # NEW
│   └── test_data.py            # NEW
└── test_engine_flow_control.py # NEW: integration tests for engine + flow control
```

**Structure Decision**: Extends the existing `src/maverick/dsl/` module with new step types in `steps/` subdirectory and a new `checkpoint/` subdirectory for persistence. This follows the established pattern from spec 022.

## Complexity Tracking

> No constitution violations detected. All constructs compose with existing patterns.
