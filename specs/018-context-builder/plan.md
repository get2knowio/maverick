# Implementation Plan: Context Builder Utilities

**Branch**: `018-context-builder` | **Date**: 2025-12-18 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/018-context-builder/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Create a set of synchronous utility functions in `src/maverick/utils/context.py` that build optimized context dictionaries for agent prompts. The context builders will:

1. **`build_implementation_context()`** - Aggregate task definitions, CLAUDE.md conventions, branch info, and recent commits
2. **`build_review_context()`** - Compile diffs, changed file contents, and conventions for code review agents
3. **`build_fix_context()`** - Extract validation errors with surrounding source code context
4. **`build_issue_context()`** - Combine GitHub issue details with related file context
5. **Supporting utilities** - `truncate_file()`, `estimate_tokens()`, `fit_to_budget()` for content management

All functions are synchronous (file I/O only) and return plain dicts for easy prompt interpolation.

## Technical Context

**Language/Version**: Python 3.10+ (with `from __future__ import annotations`)
**Primary Dependencies**: pathlib (stdlib), logging (stdlib), re (stdlib), existing GitOperations utility
**Storage**: N/A (read-only file access, no persistence)
**Testing**: pytest + pytest-asyncio (sync tests, async tests for integration)
**Target Platform**: Linux/macOS CLI environment
**Project Type**: Single project (existing Maverick structure)
**Performance Goals**: < 500ms for typical repository sizes (up to 10,000 files) per SC-001
**Constraints**: < 100MB memory per operation (SC-007), token accuracy within 20% (SC-003)
**Scale/Scope**: Repositories up to 10,000 files, files up to 50,000 lines

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Pre-Design Check (Phase 0)

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Async-First | ✅ N/A | Context builders are synchronous (file I/O only, no Claude SDK) |
| II. Separation of Concerns | ✅ PASS | Utils module - pure data transformation, no orchestration |
| III. Dependency Injection | ✅ PASS | GitOperations, paths passed as parameters |
| IV. Fail Gracefully | ✅ PASS | Missing files return empty content + metadata |
| V. Test-First | ✅ PASS | Will follow TDD with pytest fixtures |
| VI. Type Safety | ✅ PASS | Full type hints, TypedDict for return types |
| VII. Simplicity | ✅ PASS | No classes needed - pure functions with dict returns |
| VIII. Relentless Progress | ✅ N/A | Utility module, not workflow orchestration |

**Pre-Design Gate Result**: PASS

### Post-Design Check (Phase 1)

| Principle | Status | Verification |
|-----------|--------|--------------|
| I. Async-First | ✅ N/A | All functions synchronous per FR-008; no Claude SDK interaction |
| II. Separation of Concerns | ✅ PASS | Pure data transformation in utils/context.py; no business logic leak |
| III. Dependency Injection | ✅ PASS | GitOperations, ValidationOutput, GitHubIssue injected as parameters |
| IV. Fail Gracefully | ✅ PASS | All missing file cases return empty content with metadata per FR-014 |
| V. Test-First | ✅ PASS | Type stubs in contracts/ define test interfaces; unit test file specified |
| VI. Type Safety | ✅ PASS | TypedDict definitions for all return types; .pyi stub file created |
| VII. Simplicity | ✅ PASS | Single module, pure functions, no new abstractions; stdlib only |
| VIII. Relentless Progress | ✅ N/A | Not a workflow component |

**Post-Design Gate Result**: PASS - Design fully compliant with constitution.

## Project Structure

### Documentation (this feature)

```text
specs/018-context-builder/
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
└── utils/
    ├── __init__.py          # Export new context functions
    └── context.py           # NEW: Context builder utilities

tests/
└── unit/
    └── utils/
        ├── __init__.py
        └── test_context.py  # NEW: Unit tests for context builders
```

**Structure Decision**: Single module `src/maverick/utils/context.py` following existing Maverick patterns. Uses existing `GitOperations` from `utils/git_operations.py` and `ValidationOutput` from `models/validation.py`. No new packages or abstractions needed.

## Complexity Tracking

No constitution violations. Implementation uses existing patterns:
- Pure functions with dict returns (like existing utils modules)
- Integration with established `GitOperations` class
- Standard logging patterns from constitution
