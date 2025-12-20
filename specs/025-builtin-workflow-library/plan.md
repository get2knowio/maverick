# Implementation Plan: Built-in Workflow Library

**Branch**: `025-builtin-workflow-library` | **Date**: 2025-12-20 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/025-builtin-workflow-library/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Create a built-in workflow library shipping with Maverick containing five canonical workflows (fly, refuel, review, validate, quick_fix), three reusable fragments (validate_and_fix, commit_and_push, create_pr_with_summary), a multi-location discovery system with override precedence, and a template-based scaffolding system for new workflow creation.

## Technical Context

**Language/Version**: Python 3.10+ (with `from __future__ import annotations`)
**Primary Dependencies**: claude-agent-sdk, Pydantic, PyYAML, Click, Textual, pathlib (stdlib)
**Storage**: N/A (workflow files are user-managed YAML/Python; no Maverick-owned persistence)
**Testing**: pytest + pytest-asyncio (all tests async-compatible)
**Target Platform**: Linux/macOS (CLI/TUI application)
**Project Type**: Single project (existing Maverick structure)
**Performance Goals**: Workflow discovery < 500ms for 100 workflow files; template scaffolding < 1s
**Constraints**: Memory-efficient discovery (lazy loading); XDG-compliant user config paths
**Scale/Scope**: 5 built-in workflows, 3 fragments, 3 templates; discovery across 3 locations

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Async-First | ✅ PASS | Workflow discovery is sync (fast file I/O); execution uses existing async engine |
| II. Separation of Concerns | ✅ PASS | Discovery → registries; Templates → scaffolding; Workflows → DSL execution |
| III. Dependency Injection | ✅ PASS | Discovery paths injectable via config; registries passed to engine |
| IV. Fail Gracefully | ✅ PASS | FR-016a: invalid files logged and skipped; discovery continues |
| V. Test-First | ✅ PASS | Tests required for discovery, override precedence, templates |
| VI. Type Safety | ✅ PASS | Pydantic models for discovery results; typed workflow definitions |
| VII. Simplicity | ✅ PASS | Uses existing DSL infrastructure; no new abstractions beyond discovery |
| VIII. Relentless Progress | ✅ PASS | Discovery resilient to file errors; partial results preserved |

## Project Structure

### Documentation (this feature)

```text
specs/025-builtin-workflow-library/
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
│   ├── serialization/
│   │   └── registry.py          # Extend with WorkflowRegistry enhancements
│   └── discovery/               # NEW: Multi-location workflow discovery
│       ├── __init__.py
│       ├── locator.py           # WorkflowLocator: finds workflow files
│       ├── loader.py            # WorkflowLoader: parses and validates
│       └── registry.py          # DiscoveryRegistry: aggregates with precedence
├── library/                     # NEW: Built-in workflow library
│   ├── __init__.py
│   ├── workflows/               # Built-in workflow definitions
│   │   ├── __init__.py
│   │   ├── fly.yaml             # FR-004: fly workflow
│   │   ├── refuel.yaml          # FR-005: refuel workflow
│   │   ├── review.yaml          # FR-006: review workflow
│   │   ├── validate.yaml        # FR-007: validate workflow
│   │   └── quick_fix.yaml       # FR-008: quick_fix workflow
│   ├── fragments/               # Reusable workflow fragments
│   │   ├── __init__.py
│   │   ├── validate_and_fix.yaml    # FR-010
│   │   ├── commit_and_push.yaml     # FR-011
│   │   └── create_pr_with_summary.yaml  # FR-012
│   └── templates/               # Scaffolding templates
│       ├── __init__.py
│       ├── basic.yaml.j2        # FR-019: basic template
│       ├── full.yaml.j2         # FR-020: full template
│       ├── parallel.yaml.j2     # FR-021: parallel template
│       ├── basic.py.j2          # Python variant
│       ├── full.py.j2           # Python variant
│       └── parallel.py.j2       # Python variant
├── cli/
│   └── workflow.py              # Extend: maverick workflow new command
└── main.py                      # CLI entry point (Click)

tests/
├── unit/
│   ├── dsl/
│   │   └── discovery/
│   │       ├── test_locator.py
│   │       ├── test_loader.py
│   │       └── test_registry.py
│   └── library/
│       ├── test_workflows.py
│       ├── test_fragments.py
│       └── test_templates.py
└── integration/
    └── test_workflow_discovery.py
```

**Structure Decision**: Single project extending existing Maverick structure. New `dsl/discovery/` module for multi-location discovery. New `library/` module for built-in workflows, fragments, and templates. Built-in workflows defined in YAML for consistency with user-defined workflows.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No constitution violations identified. All principles pass.

## Post-Design Constitution Re-Check

*Re-evaluation after Phase 1 design completion.*

| Principle | Status | Design Validation |
|-----------|--------|-------------------|
| I. Async-First | ✅ PASS | Discovery is sync (sub-second file ops); WorkflowFileExecutor remains async |
| II. Separation of Concerns | ✅ PASS | Clear module boundaries: `discovery/` → `library/` → `cli/scaffold` |
| III. Dependency Injection | ✅ PASS | WorkflowDiscovery accepts custom locator/loader; TemplateScaffolder injectable |
| IV. Fail Gracefully | ✅ PASS | SkippedWorkflow captures errors; DiscoveryResult includes skipped list |
| V. Test-First | ✅ PASS | Contract modules define testable interfaces; frozen dataclasses for assertions |
| VI. Type Safety | ✅ PASS | All data models use frozen dataclasses with slots; enums for constrained values |
| VII. Simplicity | ✅ PASS | Reuses existing WorkflowFile/parse_workflow; no new step types |
| VIII. Relentless Progress | ✅ PASS | Discovery continues on errors; partial results in DiscoveryResult |

## Generated Artifacts

| Artifact | Path | Purpose |
|----------|------|---------|
| research.md | `specs/025-builtin-workflow-library/research.md` | Technical decisions and rationale |
| data-model.md | `specs/025-builtin-workflow-library/data-model.md` | Entity definitions and relationships |
| discovery.py | `specs/025-builtin-workflow-library/contracts/discovery.py` | Discovery API contract |
| scaffold.py | `specs/025-builtin-workflow-library/contracts/scaffold.py` | Scaffolding API contract |
| library.py | `specs/025-builtin-workflow-library/contracts/library.py` | Built-in library API contract |
| quickstart.md | `specs/025-builtin-workflow-library/quickstart.md` | User-facing usage guide |

## Next Steps

Run `/speckit.tasks` to generate the implementation task list from these design artifacts.
