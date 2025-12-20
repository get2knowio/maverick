# Implementation Plan: Safety and Logging Hooks

**Branch**: `007-safety-hooks` | **Date**: 2025-12-15 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/007-safety-hooks/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Implement a hooks system for safety validation and execution logging using Claude Agent SDK hook capabilities. The system provides:
- **Safety hooks** (PreToolUse): Block dangerous bash commands (rm -rf, fork bombs), prevent writes to sensitive paths (.env, .ssh)
- **Logging hooks** (PostToolUse): Log all tool executions with sanitized inputs, collect execution metrics
- **Configuration**: Enable/disable hooks, customize blocklists/allowlists via HookConfig

## Technical Context

**Language/Version**: Python 3.10+ (with `from __future__ import annotations`)
**Primary Dependencies**: Claude Agent SDK (`claude-agent-sdk`), Pydantic (for configuration models)
**Storage**: N/A (metrics in-memory with rolling window; logs via standard Python logging)
**Testing**: pytest + pytest-asyncio
**Target Platform**: Linux server (Unix paths/conventions assumed)
**Project Type**: Single project (existing Maverick CLI/TUI application)
**Performance Goals**: Hook validation <10ms overhead per tool execution (SC-004)
**Constraints**: Thread-safe metrics collection for concurrent workflows; fail-closed on hook exceptions
**Scale/Scope**: Per-agent hook attachment; metrics bounded by rolling window

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evidence |
|-----------|--------|----------|
| I. Async-First | ✅ PASS | Hooks are async functions per Claude Agent SDK patterns; metrics use asyncio locks |
| II. Separation of Concerns | ✅ PASS | Hooks module isolated in `src/maverick/hooks/`; hooks know HOW to validate/log, agents/workflows use them |
| III. Dependency Injection | ✅ PASS | HookConfig injected to factory functions; no global mutable state |
| IV. Fail Gracefully | ✅ PASS | Fail-closed on hook exceptions (FR-011a); errors logged with context |
| V. Test-First | ✅ PASS | All hooks independently testable (FR-004); no full agent setup needed |
| VI. Type Safety | ✅ PASS | Complete type hints; Pydantic models for HookConfig, ValidationResult |
| VII. Simplicity | ✅ PASS | No premature abstractions; rolling window for metrics bounds complexity |
| VIII. Relentless Progress | ✅ PASS | Hook failures don't crash workflows; fail-closed protects system integrity |

## Project Structure

### Documentation (this feature)

```text
specs/007-safety-hooks/
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
├── hooks/
│   ├── __init__.py      # Public exports: create_safety_hooks, create_logging_hooks
│   ├── config.py        # HookConfig Pydantic model
│   ├── safety.py        # Safety hooks: validate_bash_command, validate_file_write
│   ├── logging.py       # Logging hooks: log_tool_execution
│   ├── metrics.py       # MetricsCollector with rolling window
│   └── types.py         # ValidationResult, ToolExecutionLog, ToolMetrics
├── exceptions.py        # Add: SafetyHookError, HookConfigError (extend existing)

tests/
├── unit/
│   └── hooks/
│       ├── __init__.py
│       ├── test_config.py
│       ├── test_safety.py
│       ├── test_logging.py
│       └── test_metrics.py
└── integration/
    └── hooks/
        ├── __init__.py
        └── test_hook_composition.py
```

**Structure Decision**: Single project structure following existing Maverick layout. Hooks module extends `src/maverick/hooks/` (currently empty `__init__.py`). Tests follow existing pattern with unit and integration directories.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations. All complexity is justified by functional requirements:
- Rolling window metrics: Required by FR-017a to bound memory usage
- Thread-safe locks: Required by FR-016 for concurrent workflow execution
- Fail-closed behavior: Required by FR-011a for safety guarantees

---

## Post-Design Constitution Re-Check

*Re-evaluated after Phase 1 design completion.*

| Principle | Status | Post-Design Evidence |
|-----------|--------|----------------------|
| I. Async-First | ✅ PASS | All hooks are `async def`; MetricsCollector uses `asyncio.Lock` |
| II. Separation of Concerns | ✅ PASS | Clear module boundaries: config.py, safety.py, logging.py, metrics.py, types.py |
| III. Dependency Injection | ✅ PASS | HookConfig and MetricsCollector injected via factory params; no globals |
| IV. Fail Gracefully | ✅ PASS | Fail-closed wraps all validation in try/except; errors logged |
| V. Test-First | ✅ PASS | Each hook function testable in isolation; no SDK mock needed for unit tests |
| VI. Type Safety | ✅ PASS | Pydantic models with validators; frozen dataclasses for immutable types |
| VII. Simplicity | ✅ PASS | Single-responsibility modules; no inheritance hierarchy beyond base exception |
| VIII. Relentless Progress | ✅ PASS | Hook errors don't propagate to agent/workflow; operations blocked safely |

---

## Generated Artifacts

| Artifact | Path | Status |
|----------|------|--------|
| Research | `specs/007-safety-hooks/research.md` | ✅ Complete |
| Data Model | `specs/007-safety-hooks/data-model.md` | ✅ Complete |
| API Contract | `specs/007-safety-hooks/contracts/hooks-api.md` | ✅ Complete |
| Quickstart | `specs/007-safety-hooks/quickstart.md` | ✅ Complete |

---

## Next Steps

Run `/speckit.tasks` to generate implementation tasks from this plan.
