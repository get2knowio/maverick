# Implementation Plan: Validation Workflow

**Branch**: `008-validation-workflow` | **Date**: 2025-12-15 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/008-validation-workflow/spec.md`

## Summary

Implement a reusable ValidationWorkflow that orchestrates format, lint, build, and test validation stages with auto-fix capabilities. The workflow yields async progress updates for TUI consumption, supports configurable stages with custom commands, and integrates with a fix agent (via constructor injection) to automatically resolve fixable issues before retrying failed stages.

## Technical Context

**Language/Version**: Python 3.10+ (with `from __future__ import annotations`)
**Primary Dependencies**: Claude Agent SDK (`claude-agent-sdk`), Pydantic, asyncio
**Storage**: N/A (in-memory state during workflow execution)
**Testing**: pytest + pytest-asyncio (all tests async-compatible)
**Target Platform**: Linux/macOS CLI/TUI application
**Project Type**: Single project (existing Maverick codebase)
**Performance Goals**: Progress updates emitted within 1 second of status changes (SC-003)
**Constraints**: Cancellation within 5 seconds (SC-005), configurable per-stage timeouts
**Scale/Scope**: Single workflow processing 4 validation stages sequentially

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Pre-Design Check (Phase 0)

| Principle | Compliant | Notes |
|-----------|-----------|-------|
| I. Async-First | ✅ | Workflow uses async generators for progress updates |
| II. Separation of Concerns | ✅ | Workflow orchestrates; fix agent does fixing; TUI displays |
| III. Dependency Injection | ✅ | Fix agent injected via constructor (per clarification) |
| IV. Fail Gracefully | ✅ | Per-stage failures don't crash workflow; partial results preserved |
| V. Test-First | ✅ | TDD approach planned; tests written before implementation |
| VI. Type Safety | ✅ | Pydantic models for stages, results; complete type hints |
| VII. Simplicity | ✅ | Sequential stages, no premature abstractions |
| VIII. Relentless Progress | ✅ | Continue to next stage on failure; checkpoint after each stage |

**Pre-Design Gate Status**: ✅ PASSED - No violations identified.

### Post-Design Check (Phase 1)

| Principle | Compliant | Design Evidence |
|-----------|-----------|-----------------|
| I. Async-First | ✅ | `run() -> AsyncIterator[ProgressUpdate]` in contract; asyncio.Event for cancellation |
| II. Separation of Concerns | ✅ | ValidationWorkflow orchestrates; MaverickAgent fixes; Pydantic models hold data |
| III. Dependency Injection | ✅ | `__init__(stages, fix_agent?, config?)` pattern documented in contracts |
| IV. Fail Gracefully | ✅ | StageResult captures errors; workflow continues to next stage; partial results preserved |
| V. Test-First | ✅ | Test examples in quickstart.md; test structure in project layout |
| VI. Type Safety | ✅ | All models frozen Pydantic; Protocol defined for workflow; type hints complete |
| VII. Simplicity | ✅ | Single workflow class; no factory patterns; direct composition |
| VIII. Relentless Progress | ✅ | Cooperative cancellation; exhausts fix attempts before failing; no silent failures |

**Post-Design Gate Status**: ✅ PASSED - Design adheres to all constitution principles.

**Design Artifacts Created**:
- `research.md`: 10 research areas resolved with decisions and rationale
- `data-model.md`: 7 entities defined with relationships and validation rules
- `contracts/validation_workflow.py`: Full type stubs and protocol definitions
- `quickstart.md`: Usage examples covering all major scenarios

## Project Structure

### Documentation (this feature)

```text
specs/008-validation-workflow/
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
│   ├── __init__.py      # Export ValidationWorkflow
│   └── validation.py    # ValidationWorkflow implementation (NEW)
├── models/
│   └── validation.py    # ValidationStage, StageResult, etc. (NEW)
└── exceptions.py        # Add ValidationWorkflowError if needed

tests/
├── unit/
│   └── workflows/
│       ├── __init__.py          # (NEW)
│       └── test_validation.py   # Unit tests (NEW)
└── integration/
    └── workflows/
        ├── __init__.py              # (NEW)
        └── test_validation_e2e.py   # Integration tests (NEW)
```

**Structure Decision**: Single project structure following existing Maverick patterns. New workflow in `src/maverick/workflows/validation.py` with models in `src/maverick/models/validation.py`.

## Complexity Tracking

> **No violations identified - Constitution Check passed.**

N/A - No complexity justifications needed.
