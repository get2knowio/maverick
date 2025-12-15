# Implementation Plan: CodeReviewerAgent

**Branch**: `003-code-reviewer-agent` | **Date**: 2025-12-13 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/003-code-reviewer-agent/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Create a `CodeReviewerAgent` that extends `MaverickAgent` to perform automated code reviews on feature branches. The agent analyzes git diffs, checks compliance with project conventions (CLAUDE.md), and returns structured `ReviewResult` findings categorized by severity (critical, major, minor, suggestion).

## Technical Context

**Language/Version**: Python 3.10+ (with `from __future__ import annotations`)
**Primary Dependencies**: Claude Agent SDK (`claude-agent-sdk`), Pydantic, Git CLI
**Storage**: N/A (reads from git, no persistent storage)
**Testing**: pytest + pytest-asyncio (all tests async-compatible)
**Target Platform**: Linux/macOS development environments
**Project Type**: Single project (extends existing Maverick architecture)
**Performance Goals**: Reviews complete within 2 minutes for typical PRs (<500 lines, <10 files)
**Constraints**: Configurable truncation at 2000 lines or 50 files; automatic chunking for token limits
**Scale/Scope**: Single-agent implementation; integrates with FlyWorkflow for parallel reviews

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Pre-Design Compliance (Phase 0 Gate)

| Principle | Requirement | Compliance | Notes |
|-----------|-------------|------------|-------|
| I. Async-First | All agent interactions MUST be async | ✅ PASS | `execute()` is async; returns `AsyncIterator` for streaming |
| II. Separation of Concerns | Agent knows HOW, not WHAT/WHEN | ✅ PASS | Agent performs review; workflow orchestrates when to call it |
| III. Dependency Injection | Dependencies passed in, not global | ✅ PASS | Config and context injected via `AgentContext` |
| IV. Fail Gracefully | Errors captured, not propagated blindly | ✅ PASS | FR-018 requires `AgentError` with diagnostics |
| V. Test-First | All public classes have tests | ✅ PASS | TDD approach; tests written before implementation |
| VI. Type Safety | Complete type hints required | ✅ PASS | Pydantic models, typed dataclasses, enum for severity |
| VII. Simplicity | No over-engineering | ✅ PASS | Single-purpose agent; no premature abstractions |

### Technology Stack Compliance

| Technology | Required | Planned | Status |
|------------|----------|---------|--------|
| Python 3.10+ | Yes | Yes | ✅ |
| Claude Agent SDK | Yes | Yes | ✅ |
| Pydantic | Yes | Yes (for models) | ✅ |
| pytest + pytest-asyncio | Yes | Yes | ✅ |
| Ruff | Yes | Yes | ✅ |
| MyPy | Yes | Yes | ✅ |

### Code Style Compliance

| Element | Convention | Planned | Status |
|---------|------------|---------|--------|
| Class names | PascalCase | `CodeReviewerAgent`, `ReviewResult`, `ReviewFinding`, `ReviewSeverity` | ✅ |
| Methods | snake_case | `execute()`, `_build_prompt()`, `_parse_findings()` | ✅ |
| Constants | SCREAMING_SNAKE_CASE | `MAX_DIFF_LINES`, `DEFAULT_BASE_BRANCH` | ✅ |
| Docstrings | Google-style | All public methods documented | ✅ |
| Exceptions | From hierarchy | `AgentError` (from base module) | ✅ |

**Gate Status**: ✅ PASS - All constitution checks pass. Proceed to Phase 0.

## Project Structure

### Documentation (this feature)

```text
specs/003-code-reviewer-agent/
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
├── __init__.py          # Version, public API exports
├── main.py              # CLI entry point (Click commands)
├── config.py            # Pydantic configuration models
├── exceptions.py        # Custom exception hierarchy (MaverickError base)
├── agents/
│   ├── __init__.py      # Agent exports, registry
│   ├── base.py          # MaverickAgent abstract base class (from 002-base-agent)
│   └── code_reviewer.py # CodeReviewerAgent implementation (THIS FEATURE)
├── models/
│   ├── __init__.py      # Model exports
│   └── review.py        # ReviewResult, ReviewFinding, ReviewSeverity, ReviewContext
├── workflows/           # Workflow orchestration (consumers of this agent)
├── tools/               # MCP tool definitions
├── hooks/               # Safety and logging hooks
├── tui/                 # Textual application
└── utils/               # Shared utilities

tests/
├── unit/
│   ├── agents/
│   │   └── test_code_reviewer.py    # Unit tests for CodeReviewerAgent
│   └── models/
│       └── test_review.py           # Unit tests for review models
├── integration/
│   └── agents/
│       └── test_code_reviewer_integration.py  # Integration tests with real git repos
└── conftest.py          # Shared fixtures
```

**Structure Decision**: Single project structure following Maverick's established architecture from CLAUDE.md. The `CodeReviewerAgent` is placed in `src/maverick/agents/code_reviewer.py`, with its data models in `src/maverick/models/review.py` to maintain separation between agent logic and data structures.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations identified. All design decisions align with constitution principles.

---

## Post-Design Constitution Check

*Re-evaluation after Phase 1 design artifacts generated.*

### Design Artifacts Review

| Artifact | Status | Constitution Alignment |
|----------|--------|------------------------|
| research.md | ✅ Complete | Documented all technical decisions with rationale |
| data-model.md | ✅ Complete | Pydantic models with full type hints (VI. Type Safety) |
| contracts/code_reviewer_api.py | ✅ Complete | Protocol-based interface (VI. Type Safety) |
| quickstart.md | ✅ Complete | Usage examples with async patterns (I. Async-First) |

### Post-Design Compliance Verification

| Principle | Design Evidence | Compliance |
|-----------|-----------------|------------|
| I. Async-First | `execute()` is async; uses `asyncio.gather()` for parallel setup; no blocking I/O | ✅ PASS |
| II. Separation of Concerns | Agent only knows HOW to review; ReviewContext/ReviewResult are value objects; no orchestration logic | ✅ PASS |
| III. Dependency Injection | ReviewContext passed to execute(); cwd configurable; no global state | ✅ PASS |
| IV. Fail Gracefully | AgentError with error codes (INVALID_BRANCH, GIT_ERROR, MERGE_CONFLICTS, TIMEOUT); errors list in ReviewResult | ✅ PASS |
| V. Test-First | Test examples in quickstart.md; test file structure defined; fixtures planned | ✅ PASS |
| VI. Type Safety | Pydantic models; Protocol for interface; Enum for severity; complete annotations | ✅ PASS |
| VII. Simplicity | Single-purpose agent; no abstractions beyond data models; direct git CLI usage | ✅ PASS |

### SDK Pattern Compliance

| Pattern | Implementation | Status |
|---------|----------------|--------|
| ClaudeSDKClient for stateful sessions | Used for multi-turn reviews (research.md) | ✅ |
| Explicit allowed_tools | `["Read", "Glob", "Grep", "Bash"]` only | ✅ |
| Structured output via JSON schema | Pydantic `.model_json_schema()` (contracts/) | ✅ |
| Extract and structure outputs | ReviewResult, not raw text | ✅ |

**Post-Design Gate Status**: ✅ PASS - Design artifacts comply with all constitution principles.

---

## Generated Artifacts

| Artifact | Path | Description |
|----------|------|-------------|
| Plan | `specs/003-code-reviewer-agent/plan.md` | This implementation plan |
| Research | `specs/003-code-reviewer-agent/research.md` | Technical decisions and rationale |
| Data Model | `specs/003-code-reviewer-agent/data-model.md` | Entity definitions and relationships |
| API Contract | `specs/003-code-reviewer-agent/contracts/code_reviewer_api.py` | Python interface contract |
| Quickstart | `specs/003-code-reviewer-agent/quickstart.md` | Usage examples and integration guide |

---

## Next Steps

1. Run `/speckit.tasks` to generate `tasks.md` with implementation tasks
2. Run `/speckit.implement` to execute implementation plan
