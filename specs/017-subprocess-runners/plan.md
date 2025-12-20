# Implementation Plan: Subprocess Execution Module

**Branch**: `017-subprocess-runners` | **Date**: 2025-12-18 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/017-subprocess-runners/spec.md`

## Summary

Implement a subprocess execution module that provides safe, async command execution with timeout handling, streaming output, validation stage orchestration, and CLI wrappers for GitHub and CodeRabbit. The module follows existing patterns from `maverick.tools` and `maverick.workflows.validation`, extending them with a unified, well-tested runner abstraction.

## Technical Context

**Language/Version**: Python 3.10+ with `from __future__ import annotations`
**Primary Dependencies**: asyncio (stdlib), dataclasses (stdlib), pathlib (stdlib), signal (stdlib)
**Storage**: N/A (in-memory state during execution)
**Testing**: pytest + pytest-asyncio with comprehensive mocking
**Target Platform**: Linux/macOS (Unix signals for process management)
**Project Type**: Single project - extends `src/maverick/`
**Performance Goals**: <100ms overhead per command, <50ms streaming latency
**Constraints**: Memory stable for >10MB output via streaming, graceful timeout within 1s
**Scale/Scope**: Integration with FlyWorkflow and RefuelWorkflow

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Async-First | PASS | All subprocess execution uses `asyncio.create_subprocess_exec()` |
| II. Separation of Concerns | PASS | Runners wrap external systems; workflows orchestrate; agents consume |
| III. Dependency Injection | PASS | Config and working directory passed in, no global state |
| IV. Fail Gracefully | PASS | All errors captured with context, partial results preserved |
| V. Test-First | PASS | Comprehensive test suite with mocking required |
| VI. Type Safety | PASS | Frozen dataclasses, complete type hints, Pydantic for config |
| VII. Simplicity | PASS | No shell=True, no global state, uses existing patterns |
| VIII. Relentless Progress | PASS | Graceful degradation, continue on partial failures |

**Pre-Design Gate**: PASSED - No violations.

## Project Structure

### Documentation (this feature)

```text
specs/017-subprocess-runners/
├── plan.md              # This file
├── research.md          # Phase 0 output - technology decisions
├── data-model.md        # Phase 1 output - entity definitions
├── quickstart.md        # Phase 1 output - usage guide
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (repository root)

```text
src/maverick/
├── runners/                    # NEW: Subprocess runner module
│   ├── __init__.py             # Public exports
│   ├── models.py               # Frozen dataclass models (CommandResult, etc.)
│   ├── command.py              # CommandRunner implementation (base runner)
│   ├── validation.py           # ValidationRunner implementation
│   ├── github.py               # GitHubCLIRunner implementation
│   ├── coderabbit.py           # CodeRabbitRunner implementation
│   └── parsers/                # Output parsers
│       ├── __init__.py
│       ├── base.py             # OutputParser Protocol
│       ├── python.py           # Python traceback parser
│       ├── rust.py             # Rust compiler error parser
│       └── eslint.py           # ESLint JSON parser
└── exceptions.py               # EXTEND: Add runner-specific exceptions

tests/
├── unit/
│   └── runners/                # NEW: Runner tests
│       ├── conftest.py         # Test fixtures
│       ├── test_command.py     # CommandRunner tests
│       ├── test_validation.py  # ValidationRunner tests
│       ├── test_github.py      # GitHubCLIRunner tests
│       ├── test_coderabbit.py  # CodeRabbitRunner tests
│       └── parsers/
│           ├── test_python.py
│           ├── test_rust.py
│           └── test_eslint.py
└── integration/
    └── runners/                # Integration tests (require actual CLI tools)
        └── test_integration.py
```

**Structure Decision**: Single project extending existing `src/maverick/` structure. New `runners/` submodule follows the pattern of `tools/`, `agents/`, and `workflows/`.

## Complexity Tracking

No constitution violations requiring justification.
