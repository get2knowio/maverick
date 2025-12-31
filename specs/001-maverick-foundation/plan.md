# Implementation Plan: Maverick Foundation - Project Skeleton & Configuration System

**Branch**: `001-maverick-foundation` | **Date**: 2025-12-12 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-maverick-foundation/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Create the foundational Python CLI application for Maverick: a project skeleton using `pyproject.toml` with `src/maverick/` layout, a Click-based CLI entry point with `--version` and `--help`, and a Pydantic-based configuration system supporting YAML files with environment variable overrides and hierarchical config merging.

## Technical Context

**Language/Version**: Python 3.10+ (with `from __future__ import annotations`)
**Primary Dependencies**: claude-agent-sdk, textual, click, pyyaml, pydantic
**Storage**: YAML config files (project: `maverick.yaml`, user: `~/.config/maverick/config.yaml`)
**Testing**: pytest + pytest-asyncio
**Target Platform**: Cross-platform (Linux, macOS, Windows)
**Project Type**: Single CLI application
**Performance Goals**: Configuration loading < 100ms (per SC-005)
**Constraints**: No sensitive values in YAML files; secrets via environment variables only
**Scale/Scope**: Foundation for multi-agent workflow system

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Async-First | N/A | Foundation spec excludes workflows/agents; config loading is sync (appropriate) |
| II. Separation of Concerns | PASS | Config system is isolated from agents, workflows, and TUI |
| III. Dependency Injection | PASS | Config objects will be injected; no global mutable state |
| IV. Fail Gracefully | PASS | ConfigError provides structured errors; validation produces actionable messages |
| V. Test-First | PASS | Tests required for all public classes/functions (pytest + pytest-asyncio) |
| VI. Type Safety | PASS | Pydantic models enforce types; complete annotations required |
| VII. Simplicity | PASS | Minimal foundation; no premature abstractions |

**Technology Stack Compliance**:
- Language: Python 3.10+ ✓
- CLI: Click ✓
- Validation: Pydantic ✓
- Testing: pytest ✓

**Gate Result**: PASS - Proceed to Phase 0

### Post-Design Re-evaluation

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Async-First | N/A | No async operations in config loading; appropriate for foundation |
| II. Separation of Concerns | PASS | Config models (config.py), exceptions (exceptions.py), CLI (main.py) cleanly separated |
| III. Dependency Injection | PASS | MaverickConfig loaded at CLI entry, injected to subcommands via ctx.obj |
| IV. Fail Gracefully | PASS | ConfigError with field/value context enables actionable error messages |
| V. Test-First | PASS | Test structure defined in project layout; TDD required |
| VI. Type Safety | PASS | Pydantic v2 models with complete annotations; Literal types for enums |
| VII. Simplicity | PASS | No premature abstractions; flat AgentConfig, no repository patterns |

**Post-Design Gate Result**: PASS - Design complies with constitution

## Project Structure

### Documentation (this feature)

```text
specs/001-maverick-foundation/
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
├── __init__.py          # Version string, public API exports
├── main.py              # Click CLI entry point (maverick command)
├── config.py            # Pydantic configuration models (MaverickConfig hierarchy)
├── exceptions.py        # MaverickError base + ConfigError subclass
├── agents/              # (placeholder for future agent implementations)
│   └── __init__.py
├── workflows/           # (placeholder for future workflow implementations)
│   └── __init__.py
├── tools/               # (placeholder for future MCP tools)
│   └── __init__.py
├── hooks/               # (placeholder for future hooks)
│   └── __init__.py
├── tui/                 # (placeholder for future TUI)
│   └── __init__.py
└── utils/               # (placeholder for future utilities)
    └── __init__.py

tests/
├── conftest.py          # Shared pytest fixtures
├── unit/
│   ├── test_config.py   # Unit tests for configuration loading
│   └── test_cli.py      # Unit tests for CLI commands
└── integration/
    └── test_config_loading.py  # Integration tests for config merging
```

**Structure Decision**: Single project layout per constitution File Organization. Uses `src/maverick/` package structure as required by FR-002. Placeholder directories included for future features (agents, workflows, TUI, tools, hooks) to establish the target architecture.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations. Design adheres to all constitution principles.
