# Implementation Plan: Flight Plan and Work Unit Data Models

**Branch**: `037-flight-plan-models` | **Date**: 2026-02-27 | **Spec**: `specs/037-flight-plan-models/spec.md`
**Input**: Feature specification from `/specs/037-flight-plan-models/spec.md`

## Summary

Implement Pydantic-based data models for Flight Plans and Work Units with Markdown+YAML parsing/serialization, completion introspection, and topological dependency resolution. The `src/maverick/flight/` package follows the established top-level package pattern (`jj/`, `vcs/`, `workspace/`) using frozen Pydantic models, manual `---`-delimited YAML frontmatter parsing with PyYAML, and DFS-based topological sorting adapted from the existing `PrerequisiteRegistry`.

## Technical Context

**Language/Version**: Python 3.10+ (with `from __future__ import annotations`)
**Primary Dependencies**: Pydantic (frozen models, validators), PyYAML (frontmatter parsing), pathlib (file operations)
**Storage**: Markdown+YAML files on disk (`flight-plan.md`, `###-slug.md`)
**Testing**: pytest + pytest-asyncio (parallel via xdist)
**Target Platform**: Linux (CLI application)
**Project Type**: Single project — library package within `src/maverick/`
**Performance Goals**: N/A (file parsing, not a hot path)
**Constraints**: No new dependencies; frozen immutable models; `<500 LOC` per module
**Scale/Scope**: Dozens of Work Units per Flight Plan (not thousands)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Async-First | PASS | `FlightPlanFile` and `WorkUnitFile` provide async loading via `asyncio.to_thread`. No blocking I/O in async paths. |
| II. Separation of Concerns | PASS | Models are pure data. Parsers handle I/O. Resolver handles dependency logic. No agent or workflow logic. |
| III. Dependency Injection | PASS | No global state. Loaders accept paths; resolver accepts Work Unit collections. |
| IV. Fail Gracefully | PASS | Typed errors with context (field name, file path). No bare exceptions. |
| V. Test-First | PASS | All modules have corresponding test files. Edge cases covered. |
| VI. Type Safety | PASS | Frozen Pydantic models with validators. Typed contracts (`to_dict()`). No `dict[str, Any]` returns. |
| VII. Simplicity & DRY | PASS | Shared `_parse_frontmatter()` utility. No premature abstractions. |
| VIII. Relentless Progress | N/A | Library package, not an autonomous workflow. |
| IX. Hardening | N/A | No external API calls. File I/O only. |
| X. Guardrails | PASS | No subprocess calls. No TUI code. No agent logic. |
| XI. Modularize Early | PASS | Six focused modules, each `<500 LOC`. |
| XII. Ownership | PASS | Complete implementation with tests and error hierarchy. |

No violations. No complexity tracking needed.

## Project Structure

### Documentation (this feature)

```text
specs/037-flight-plan-models/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── contracts/           # Phase 1 output (Python API contracts)
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
src/maverick/
├── flight/                      # NEW PACKAGE
│   ├── __init__.py              # Public API exports (__all__)
│   ├── models.py                # Pydantic models (FlightPlan, WorkUnit, etc.)
│   ├── errors.py                # Re-exports from exceptions.flight
│   ├── parser.py                # Markdown+YAML frontmatter parser
│   ├── serializer.py            # Model → Markdown+YAML serialization
│   ├── loader.py                # FlightPlanFile, WorkUnitFile (sync+async load)
│   └── resolver.py              # Topological sort + parallel group resolution
├── exceptions/
│   └── flight.py                # NEW: FlightError hierarchy

tests/unit/flight/               # NEW TEST PACKAGE
├── conftest.py                  # Fixtures: sample markdown, factories
├── test_models.py               # Model construction, validation, computed props
├── test_parser.py               # Frontmatter parsing, section extraction
├── test_serializer.py           # Serialization + round-trip fidelity
├── test_loader.py               # File loading (sync + async), error paths
└── test_resolver.py             # Dependency resolution, cycles, parallel groups
```

**Structure Decision**: Dedicated `src/maverick/flight/` package following the `jj/`, `vcs/`, `workspace/` pattern. Six focused modules, each with a single responsibility. Error hierarchy in `src/maverick/exceptions/flight.py` following the `exceptions/jj.py` pattern.
