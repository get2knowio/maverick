# Implementation Plan: Fly Workflow Interface

**Branch**: `009-fly-workflow` | **Date**: 2025-12-15 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/009-fly-workflow/spec.md`

**Note**: This spec defines the interface, stages, and data structures only. The full implementation will be done in Spec 26 using the workflow DSL.

## Summary

Define the Fly Workflow interface including WorkflowStage enum, FlyInputs/FlyConfig configuration models, WorkflowState for tracking execution, FlyResult for outcomes, and typed progress events for TUI consumption. The implementation will use Pydantic models and Python dataclasses following existing patterns from the ValidationWorkflow module.

## Technical Context

**Language/Version**: Python 3.10+ (with `from __future__ import annotations`)
**Primary Dependencies**: Pydantic (BaseModel), dataclasses (frozen/slots), asyncio
**Storage**: N/A (in-memory state during workflow execution)
**Testing**: pytest + pytest-asyncio
**Target Platform**: Linux/macOS CLI
**Project Type**: single
**Performance Goals**: N/A (interface definition only)
**Constraints**: Must integrate with existing MaverickConfig, AgentResult, and ValidationWorkflowResult types
**Scale/Scope**: Single module with ~15 public types

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Async-First | ✅ PASS | execute() method is async; yields progress via async generator pattern |
| II. Separation of Concerns | ✅ PASS | FlyWorkflow is orchestration (workflow layer); uses agents from agent layer |
| III. Dependency Injection | ✅ PASS | FlyConfig injected at construction; no global state |
| IV. Fail Gracefully | ✅ PASS | WorkflowState.errors accumulates errors; FAILED stage captures failure context |
| V. Test-First | ✅ PASS | Spec requires 100% test coverage (SC-010) |
| VI. Type Safety | ✅ PASS | All types are Pydantic/dataclass with complete annotations |
| VII. Simplicity | ✅ PASS | Interface-only spec; NotImplementedError defers complexity to Spec 26 |
| VIII. Relentless Progress | ✅ PASS | Stage design allows partial success; errors don't block state tracking |

**Gate Result**: ✅ PASSED - All principles satisfied

## Project Structure

### Documentation (this feature)

```text
specs/009-fly-workflow/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
src/maverick/
├── workflows/
│   ├── __init__.py      # Add FlyWorkflow exports
│   └── fly.py           # NEW: Fly workflow interface module
├── config.py            # Add FlyConfig integration to MaverickConfig
├── agents/
│   └── result.py        # Existing AgentResult, AgentUsage (import from here)
└── models/
    └── validation.py    # Existing ValidationWorkflowResult (import from here)

tests/
└── unit/
    └── workflows/
        └── test_fly.py  # NEW: Unit tests for fly workflow interface
```

**Structure Decision**: Single module (`src/maverick/workflows/fly.py`) containing all interface definitions. Follows existing pattern from `validation.py`. FlyConfig will be added to `config.py` to integrate with MaverickConfig hierarchy.

## Complexity Tracking

> **No violations requiring justification** - This is an interface-only implementation with minimal complexity.

## Post-Design Constitution Re-Check

*Re-evaluated after Phase 1 design completion.*

| Principle | Status | Post-Design Notes |
|-----------|--------|-------------------|
| I. Async-First | ✅ PASS | `execute()` is async; progress events support async generator pattern |
| II. Separation of Concerns | ✅ PASS | Clear separation: FlyWorkflow (orchestration), FlyConfig (config), events (TUI) |
| III. Dependency Injection | ✅ PASS | FlyConfig injected; FlyInputs validated separately from workflow |
| IV. Fail Gracefully | ✅ PASS | WorkflowState.errors accumulates; FAILED stage captures context |
| V. Test-First | ✅ PASS | Data model designed with testability; all validation rules explicit |
| VI. Type Safety | ✅ PASS | Full Pydantic/dataclass coverage; type stub contract provided |
| VII. Simplicity | ✅ PASS | Single module; no premature abstractions; NotImplementedError defers complexity |
| VIII. Relentless Progress | ✅ PASS | Stage design allows partial results; errors don't prevent state capture |

**Post-Design Gate Result**: ✅ PASSED - All principles satisfied after design phase

## Generated Artifacts

| Artifact | Path | Status |
|----------|------|--------|
| Plan | specs/009-fly-workflow/plan.md | ✅ Complete |
| Research | specs/009-fly-workflow/research.md | ✅ Complete |
| Data Model | specs/009-fly-workflow/data-model.md | ✅ Complete |
| Contract | specs/009-fly-workflow/contracts/fly_interface.pyi | ✅ Complete |
| Quickstart | specs/009-fly-workflow/quickstart.md | ✅ Complete |

## Ready for Task Generation

Run `/speckit.tasks` to generate the implementation task list.
