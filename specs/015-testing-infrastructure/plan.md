# Implementation Plan: Testing Infrastructure

**Branch**: `015-testing-infrastructure` | **Date**: 2025-12-17 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/015-testing-infrastructure/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Create comprehensive testing infrastructure for Maverick including enhanced test fixtures for Claude Agent SDK mocking, async generator utilities, coverage enforcement, and CI configuration. The existing test suite provides a foundation with pytest/pytest-asyncio configured and organized test directories; this feature enhances it with reusable fixtures, utilities, and automated CI validation on GitHub Actions.

## Technical Context

**Language/Version**: Python 3.10+ (with `from __future__ import annotations`)
**Primary Dependencies**: pytest>=7.0.0, pytest-asyncio>=0.21.0, pytest-cov>=4.0.0, ruff, mypy, textual (for pilot testing), click (for CliRunner)
**Storage**: N/A (no persistent storage; in-memory state during test execution)
**Testing**: pytest + pytest-asyncio (already configured in pyproject.toml)
**Target Platform**: Linux (CI), macOS, Windows (developer machines)
**Project Type**: Single Python package (`src/maverick/`)
**Performance Goals**: Unit test suite completes in <60 seconds; CI pipeline completes in <10 minutes
**Constraints**: 80% minimum code coverage; 30-second async test timeout; no real API calls in tests
**Scale/Scope**: ~75 source files, 6 major component types (agents, tools, workflows, config, TUI, CLI)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Requirement | Compliance | Notes |
|-----------|-------------|------------|-------|
| I. Async-First | All agent interactions async; workflows yield progress updates | ✅ PASS | Tests use `pytest.mark.asyncio`; async utilities planned for generators |
| II. Separation of Concerns | Components have distinct responsibilities | ✅ PASS | Test fixtures separate from business logic; utilities modular |
| III. Dependency Injection | Dependencies received, not accessed globally | ✅ PASS | Fixtures provide mock objects via pytest DI; no global state |
| IV. Fail Gracefully | One failure doesn't crash entire workflow | ✅ PASS | Test isolation via pytest; clear error messages on fixture failures |
| V. Test-First | Every public class/function has tests | ✅ PASS | This feature creates the infrastructure for comprehensive testing |
| VI. Type Safety | Complete type hints required | ✅ PASS | All fixtures and utilities will have full type annotations |
| VII. Simplicity | No over-engineering | ✅ PASS | Start with essential fixtures; add complexity only as needed |
| VIII. Relentless Progress | Forward progress at all costs | ⚠️ N/A | Testing infrastructure, not runtime workflow |

**Gate Status**: ✅ PASS - All applicable principles satisfied

## Project Structure

### Documentation (this feature)

```text
specs/015-testing-infrastructure/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
src/maverick/                    # Source code (existing structure)
├── agents/                      # Agent implementations
├── workflows/                   # Workflow orchestration
├── tools/                       # MCP tool definitions
├── hooks/                       # Safety and logging hooks
├── tui/                         # Textual application
│   ├── screens/                 # Screen components
│   └── widgets/                 # Reusable widgets
├── cli/                         # CLI context and utilities
└── utils/                       # Shared utilities

tests/                           # Test suite
├── conftest.py                  # Root-level fixtures (enhanced)
├── fixtures/                    # NEW: Shared fixture modules
│   ├── __init__.py
│   ├── agents.py                # Mock Claude SDK client fixtures
│   ├── config.py                # MaverickConfig fixtures
│   ├── github.py                # Mock GitHub CLI fixtures
│   └── responses.py             # Sample agent response fixtures
├── utils/                       # NEW: Test utility modules
│   ├── __init__.py
│   ├── async_helpers.py         # Async generator capture utilities
│   ├── assertions.py            # AgentResult assertion helpers
│   └── mcp.py                   # MCP tool response validators
├── unit/                        # Existing unit tests (enhanced)
│   ├── agents/
│   ├── tools/
│   ├── workflows/
│   ├── config/                  # NEW: Configuration tests
│   ├── hooks/
│   ├── models/
│   ├── tui/
│   │   ├── screens/
│   │   └── widgets/
│   ├── cli/
│   └── utils/
├── integration/                 # Existing integration tests (enhanced)
│   ├── workflows/
│   ├── hooks/
│   ├── cli/
│   └── tools/
└── tui/                         # NEW: Dedicated TUI tests with Textual pilot
    ├── __init__.py
    └── screens/

.github/workflows/
└── test.yml                     # NEW: CI workflow for Python tests
```

**Structure Decision**: Enhance existing single-project Python package structure. Tests organized by layer (unit/integration/tui) with shared fixtures and utilities in dedicated directories.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations - all principles satisfied. Implementation uses standard pytest patterns and enhances existing infrastructure.
