# Implementation Plan: Git Operations Module

**Branch**: `016-git-operations` | **Date**: 2025-12-18 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/016-git-operations/spec.md`

## Summary

Create a pure Python synchronous git operations module (`src/maverick/utils/git_operations.py`) that wraps git CLI commands with typed exceptions and structured return types. This module provides deterministic git actions (branch, commit, push, pull, diff, stash) for Maverick workflows without AI/Claude integration.

## Technical Context

**Language/Version**: Python 3.10+ (with `from __future__ import annotations`)
**Primary Dependencies**: subprocess (stdlib), dataclasses (stdlib), pathlib (stdlib)
**Storage**: N/A (operates on git repositories)
**Testing**: pytest + pytest-asyncio (module is sync but test infrastructure is unified)
**Target Platform**: Unix-like systems and Windows with git CLI 2.0+
**Project Type**: single (fits within existing `src/maverick/utils/` structure)
**Performance Goals**: All operations complete within 5 seconds for repositories under 10,000 files
**Constraints**: No shell=True in subprocess calls, thread-safe (no mutable instance state beyond cwd)
**Scale/Scope**: Module exposes 12 operations across 6 user stories

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Compliance | Notes |
|-----------|------------|-------|
| I. Async-First | N/A | Module is intentionally sync (FR-003); workflows can call via `asyncio.to_thread()` |
| II. Separation of Concerns | PASS | Module is pure wrapper (Tools layer); no workflow/agent/TUI logic |
| III. Dependency Injection | PASS | Working directory injected via constructor; no global state |
| IV. Fail Gracefully | PASS | All errors raise typed exceptions with context; recoverable flag on GitError |
| V. Test-First | PASS | 100% test coverage required (SC-008) |
| VI. Type Safety | PASS | Complete type hints required; dataclasses for structured returns |
| VII. Simplicity | PASS | No shell=True (FR-005); no premature abstractions; single module |
| VIII. Relentless Progress | N/A | Module is synchronous utility; retry logic is caller's responsibility |

**GATE STATUS: PASS** - No violations to justify.

## Project Structure

### Documentation (this feature)

```text
specs/016-git-operations/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (internal Python API)
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
src/maverick/
├── exceptions.py        # Add GitNotFoundError, NotARepositoryError, BranchExistsError,
│                        # MergeConflictError, PushRejectedError (extend existing GitError)
└── utils/
    ├── git.py           # Existing async git utilities (unchanged)
    └── git_operations.py # NEW: Synchronous GitOperations class

tests/
└── unit/
    └── utils/
        └── test_git_operations.py  # NEW: Unit tests for GitOperations
```

**Structure Decision**: Extend existing `src/maverick/utils/` with a new `git_operations.py` module. The existing `git.py` provides async helpers for workflows; the new module provides sync operations for direct use. Exception types extend the existing `GitError` in `exceptions.py`.

## Complexity Tracking

> No Constitution Check violations to justify.
