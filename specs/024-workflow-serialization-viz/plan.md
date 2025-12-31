# Implementation Plan: Workflow Serialization & Visualization

**Branch**: `024-workflow-serialization-viz` | **Date**: 2025-12-20 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/024-workflow-serialization-viz/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Add YAML/JSON serialization, file-based workflow parsing, and visualization (Mermaid/ASCII diagrams) to the existing Maverick workflow DSL. This enables workflow definitions to be stored in repositories, reviewed as code changes, and executed without writing Python code. The implementation extends the existing `StepDefinition` serialization, adds a string-based expression system for runtime references, creates registries for component resolution, and provides CLI commands for workflow management.

## Technical Context

**Language/Version**: Python 3.10+ (with `from __future__ import annotations`)
**Primary Dependencies**: claude-agent-sdk, Textual 0.40+, Click, Pydantic, PyYAML (for YAML parsing)
**Storage**: N/A (workflow files are user-managed; no Maverick-owned persistence)
**Testing**: pytest + pytest-asyncio (async-compatible tests)
**Target Platform**: Linux/macOS CLI (developer machines)
**Project Type**: Single project - extends existing `src/maverick/` structure
**Performance Goals**: Parse/validate 100-step workflows in <2 seconds; generate diagrams for 50-step workflows in <1 second
**Constraints**: No new heavyweight dependencies; leverage existing Pydantic for schema validation
**Scale/Scope**: Typical workflows: 5-30 steps; maximum 100 steps per workflow

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Requirement | Compliance | Notes |
|-----------|-------------|------------|-------|
| I. Async-First | All agent interactions and workflows MUST be async | ✅ PASS | Workflow execution already async; parsing/serialization are sync (acceptable for file I/O) |
| II. Separation of Concerns | Components have distinct responsibilities | ✅ PASS | New modules: `dsl/serialization/` (parsing), `dsl/visualization/` (diagrams), `dsl/expressions/` (expression eval) |
| III. Dependency Injection | No global state; dependencies injected | ✅ PASS | Registries passed in or module-level singletons following AgentRegistry pattern |
| IV. Fail Gracefully | One failure MUST NOT crash workflow | ✅ PASS | Parsing errors return structured validation results; execution failures handled by existing engine |
| V. Test-First | Every public class/function MUST have tests | ✅ PASS | TDD for all new modules; round-trip tests for serialization |
| VI. Type Safety | Complete type hints required | ✅ PASS | Pydantic models for schema; dataclasses for expressions/visualization |
| VII. Simplicity | No over-engineering | ✅ PASS | Expression syntax limited to `${{ }}` references; no full expression language |
| VIII. Relentless Progress | Forward progress; checkpoint state | ✅ PASS | File-based workflows don't affect checkpoint system; existing engine handles resumability |

**Gate Status**: ✅ PASS - No violations identified

## Project Structure

### Documentation (this feature)

```text
specs/024-workflow-serialization-viz/
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
├── dsl/
│   ├── expressions/              # NEW: String-based expression parser & evaluator
│   │   ├── __init__.py
│   │   ├── parser.py             # Expression AST parsing (${{ ... }})
│   │   ├── evaluator.py          # Runtime evaluation against WorkflowContext
│   │   └── errors.py             # Expression-specific errors
│   ├── serialization/            # NEW: Workflow YAML/JSON serialization
│   │   ├── __init__.py
│   │   ├── schema.py             # Pydantic models for workflow file format
│   │   ├── parser.py             # YAML/JSON → WorkflowDefinition + StepDefinitions
│   │   ├── writer.py             # WorkflowDefinition → YAML/JSON
│   │   ├── registry.py           # Component registries (actions, generators, etc.)
│   │   └── errors.py             # Parsing/validation errors
│   ├── visualization/            # NEW: Diagram generation
│   │   ├── __init__.py
│   │   ├── mermaid.py            # Mermaid diagram generator
│   │   └── ascii.py              # ASCII diagram generator
│   └── [existing files...]       # builder.py, context.py, engine.py, etc.
├── main.py                       # MODIFIED: Add 'workflow' CLI command group
└── [existing structure...]

tests/
├── unit/
│   └── dsl/
│       ├── expressions/          # NEW: Expression parser/evaluator tests
│       │   ├── test_parser.py
│       │   └── test_evaluator.py
│       ├── serialization/        # NEW: Serialization tests
│       │   ├── test_schema.py
│       │   ├── test_parser.py
│       │   ├── test_writer.py
│       │   └── test_registry.py
│       └── visualization/        # NEW: Visualization tests
│           ├── test_mermaid.py
│           └── test_ascii.py
└── integration/
    └── dsl/
        └── test_workflow_roundtrip.py  # NEW: End-to-end YAML → execute → verify
```

**Structure Decision**: Single project structure extending existing `src/maverick/dsl/` with three new subdirectories for expressions, serialization, and visualization. CLI commands added to existing `main.py`.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations identified. All principles pass without needing justification.

## Post-Design Constitution Re-Check

*Verified after Phase 1 design completion.*

| Principle | Design Decision | Compliance |
|-----------|-----------------|------------|
| I. Async-First | Parsing/serialization are sync (file I/O); expression evaluation happens during async engine execution | ✅ PASS |
| II. Separation of Concerns | Three distinct modules: `expressions/`, `serialization/`, `visualization/` with clear boundaries | ✅ PASS |
| III. Dependency Injection | ComponentRegistry is injectable; module singletons follow AgentRegistry pattern | ✅ PASS |
| IV. Fail Gracefully | ValidationResult provides structured errors; lenient mode defers resolution; no crashes on parse errors | ✅ PASS |
| V. Test-First | Test structure defined; round-trip tests ensure serialization integrity | ✅ PASS |
| VI. Type Safety | Pydantic models for schema; discriminated unions; dataclasses for value objects | ✅ PASS |
| VII. Simplicity | Expression system intentionally limited to references + `not`; rejected Jinja2/CEL as overkill | ✅ PASS |
| VIII. Relentless Progress | Lenient mode supports development; file workflows integrate with existing checkpoint system | ✅ PASS |

**Final Gate Status**: ✅ PASS - Design is constitution-compliant

## Generated Artifacts

| Artifact | Path | Description |
|----------|------|-------------|
| Plan | `specs/024-workflow-serialization-viz/plan.md` | This file - implementation plan |
| Research | `specs/024-workflow-serialization-viz/research.md` | Design decisions and rationale |
| Data Model | `specs/024-workflow-serialization-viz/data-model.md` | Entity definitions and relationships |
| Quickstart | `specs/024-workflow-serialization-viz/quickstart.md` | Usage guide for workflow authors |
| Schema Contract | `specs/024-workflow-serialization-viz/contracts/workflow-schema.json` | JSON Schema for workflow files |
| Serialization API | `specs/024-workflow-serialization-viz/contracts/serialization-api.md` | Parser and writer interfaces |
| Visualization API | `specs/024-workflow-serialization-viz/contracts/visualization-api.md` | Mermaid and ASCII generator interfaces |
| Editor Interface | `specs/024-workflow-serialization-viz/contracts/editor-interface.md` | Future workflow editor contract (FR-029) |
| CLI Commands | `specs/024-workflow-serialization-viz/contracts/cli-commands.md` | CLI command specifications |

## Next Steps

Run `/speckit.tasks` to generate `tasks.md` with implementation tasks ordered by dependency.
