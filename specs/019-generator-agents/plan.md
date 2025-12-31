# Implementation Plan: Generator Agents

**Branch**: `019-generator-agents` | **Date**: 2025-12-18 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/019-generator-agents/spec.md`

## Summary

Implement lightweight, single-purpose generator agents that use the Claude Agent SDK's `query()` function for stateless text generation without tools. The feature provides four generators: CommitMessageGenerator, PRDescriptionGenerator, CodeAnalyzer, and ErrorExplainer, all inheriting from a common GeneratorAgent base class.

## Technical Context

**Language/Version**: Python 3.10+ (with `from __future__ import annotations`)
**Primary Dependencies**: Claude Agent SDK (`claude-agent-sdk`), Pydantic (for input models)
**Storage**: N/A (stateless text generation, no persistence)
**Testing**: pytest + pytest-asyncio (all tests async-compatible)
**Target Platform**: Linux/macOS CLI
**Project Type**: Single project
**Performance Goals**: All generators return results within 5 seconds for typical inputs
**Constraints**: 100KB max diff size, 10KB max code snippet size
**Scale/Scope**: 4 concrete generators + 1 base class

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Async-First | ✅ PASS | All generators use async `generate()` method per FR-013 |
| II. Separation of Concerns | ✅ PASS | Generators are agents (HOW), called by workflows (WHEN) |
| III. Dependency Injection | ✅ PASS | Model/config passed at construction; no global state |
| IV. Fail Gracefully | ✅ PASS | Per FR-018, generators fail fast; callers handle retry |
| V. Test-First | ✅ PASS | TDD approach; mock `query()` for unit tests |
| VI. Type Safety | ✅ PASS | Complete type hints; Pydantic/dataclass for contexts |
| VII. Simplicity | ✅ PASS | Single-purpose generators, no premature abstractions |
| VIII. Relentless Progress | ✅ PASS | Generators stateless; workflow handles recovery |

**Post-Design Re-check**: ✅ All principles satisfied. Design uses existing patterns from agents/base.py and utils.py.

## Project Structure

### Documentation (this feature)

```text
specs/019-generator-agents/
├── plan.md              # This file
├── research.md          # Phase 0 output ✅
├── data-model.md        # Phase 1 output ✅
├── quickstart.md        # Phase 1 output ✅
├── contracts/           # Phase 1 output ✅
│   └── generator_api.py
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (repository root)

```text
src/maverick/
├── agents/
│   ├── generators/           # NEW: Generator implementations
│   │   ├── __init__.py       # Public exports
│   │   ├── base.py           # GeneratorAgent base class
│   │   ├── commit_message.py # CommitMessageGenerator
│   │   ├── pr_description.py # PRDescriptionGenerator
│   │   ├── code_analyzer.py  # CodeAnalyzer
│   │   └── error_explainer.py# ErrorExplainer
│   └── utils.py              # EXISTING: Text extraction utilities
├── exceptions.py             # EXISTING: Add GeneratorError

tests/
├── unit/
│   └── agents/
│       └── generators/       # NEW: Generator tests
│           ├── test_base.py
│           ├── test_commit_message.py
│           ├── test_pr_description.py
│           ├── test_code_analyzer.py
│           └── test_error_explainer.py
```

**Structure Decision**: Single project layout following existing `src/maverick/agents/` pattern. Generators are a submodule under agents/ to maintain separation while reusing shared utilities.

## Complexity Tracking

> No violations to justify - design follows constitution principles.

## Phase Artifacts

### Phase 0: Research ✅

- **research.md**: Completed - resolved all technical unknowns
  - Claude SDK `query()` usage pattern
  - Text extraction from responses
  - Error handling strategy
  - Input truncation approach
  - Conventional commit format
  - PR description sections
  - Code analysis types

### Phase 1: Design ✅

- **data-model.md**: Completed - entity definitions, fields, validation rules
- **contracts/generator_api.py**: Completed - Python Protocol/ABC interfaces
- **quickstart.md**: Completed - usage examples and integration patterns

### Phase 2: Tasks ✅

- **tasks.md**: Completed - 23 tasks across 7 phases
  - Setup (3 tasks)
  - Foundational base class (3 tasks)
  - User Story 1-4 implementations (12 tasks)
  - Polish & validation (5 tasks)

## Dependencies

- **018-context-builder**: Provides input context (diff, file stats) - assumed complete
- **002-base-agent**: Existing MaverickAgent patterns for reference
- **agents/utils.py**: Existing text extraction utilities (`extract_all_text`)

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Claude SDK API changes | Use stable `query()` interface; pin SDK version |
| Prompt quality variance | Define strict output format in system prompts |
| Large input handling | Truncation with warning per FR-017 |
