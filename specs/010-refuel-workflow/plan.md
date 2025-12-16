# Implementation Plan: Refuel Workflow Interface

**Branch**: `010-refuel-workflow` | **Date**: 2025-12-15 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/010-refuel-workflow/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Define the interface and data structures for the Refuel Workflow - a tech-debt resolution workflow that discovers GitHub issues by label, processes them in parallel using IssueFixerAgent, and creates PRs. This spec defines **contracts only** (interface-first design); full implementation is deferred to Spec 26.

## Technical Context

**Language/Version**: Python 3.10+ (with `from __future__ import annotations`)
**Primary Dependencies**: Claude Agent SDK (`claude-agent-sdk`), Pydantic (BaseModel), dataclasses (frozen/slots), asyncio
**Storage**: N/A (no persistence; in-memory state during workflow execution)
**Testing**: pytest + pytest-asyncio (async-compatible)
**Target Platform**: Linux server / macOS (CLI/TUI environment)
**Project Type**: single
**Performance Goals**: N/A (interface-only spec)
**Constraints**: Async-first, immutable data structures (frozen=True, slots=True)
**Scale/Scope**: Interface definition: ~8 dataclasses, 4 progress events, 1 workflow class, 1 config class

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Compliance | Notes |
|-----------|------------|-------|
| I. Async-First | ✅ PASS | execute() yields async generator of progress events |
| II. Separation of Concerns | ✅ PASS | Workflow defines WHAT/WHEN; IssueFixerAgent (future) defines HOW |
| III. Dependency Injection | ✅ PASS | RefuelConfig passed to workflow; no global state |
| IV. Fail Gracefully | ✅ PASS | Per-issue failure tracking (FAILED status); workflow continues |
| V. Test-First | ✅ PASS | All dataclasses testable; interface raises NotImplementedError |
| VI. Type Safety | ✅ PASS | Complete type hints; frozen dataclasses; Optional[] for nullable |
| VII. Simplicity | ✅ PASS | Minimal interface; no implementation complexity |
| VIII. Relentless Progress | ✅ PASS | Design supports isolated failures and partial results |

**Gate Status**: ✅ PASSED - No constitution violations

### Post-Design Re-evaluation (Phase 1 Complete)

| Principle | Status | Design Artifacts |
|-----------|--------|------------------|
| I. Async-First | ✅ Confirmed | `AsyncGenerator[RefuelProgressEvent, None]` in data-model.md |
| II. Separation of Concerns | ✅ Confirmed | Workflow/Agent boundaries in quickstart.md |
| III. Dependency Injection | ✅ Confirmed | RefuelConfig injection in workflow __init__ |
| IV. Fail Gracefully | ✅ Confirmed | IssueStatus.FAILED with error field |
| V. Test-First | ✅ Confirmed | Test cases in quickstart.md |
| VI. Type Safety | ✅ Confirmed | All fields typed in data-model.md |
| VII. Simplicity | ✅ Confirmed | Single file (refuel.py) with minimal entities |
| VIII. Relentless Progress | ✅ Confirmed | Per-issue isolation in RefuelResult.results |

**Post-Design Gate**: ✅ PASSED - Design artifacts comply with constitution

## Project Structure

### Documentation (this feature)

```text
specs/010-refuel-workflow/
├── plan.md              # This file
├── research.md          # Phase 0: Research findings
├── data-model.md        # Phase 1: Entity definitions
├── quickstart.md        # Phase 1: Implementation guide
├── contracts/           # Phase 1: API contracts (N/A - internal interfaces)
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
src/maverick/
├── workflows/
│   ├── __init__.py      # Update: export RefuelWorkflow
│   ├── fly.py           # Existing: FlyWorkflow reference pattern
│   └── refuel.py        # NEW: RefuelWorkflow interface + data models
├── config.py            # Update: add RefuelConfig to MaverickConfig
└── agents/
    └── result.py        # Existing: AgentUsage (imported by refuel.py)

tests/
└── unit/
    └── workflows/
        └── test_refuel.py  # NEW: Unit tests for refuel interface
```

**Structure Decision**: Single project - extends existing `src/maverick/workflows/` following FlyWorkflow pattern. All dataclasses and the workflow class go in `refuel.py`.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

*No violations - interface-only design with minimal complexity.*
