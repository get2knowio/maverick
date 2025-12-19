# Implementation Plan: Workflow Refactor to Python-Orchestrated Pattern

**Branch**: `020-workflow-refactor` | **Date**: 2025-12-18 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/020-workflow-refactor/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Refactor FlyWorkflow and RefuelWorkflow to use a Python-orchestrated pattern where Python directly handles deterministic actions (git operations, file I/O, process execution, GitHub CLI calls) while Claude agents handle only judgment tasks (code implementation, commit message generation, code review interpretation, PR description generation). This reduces token consumption by 40-60% by eliminating unnecessary AI involvement in mechanical operations.

The existing codebase has ready-to-use runners (CommandRunner, ValidationRunner, GitHubCLIRunner) and agent abstractions with explicit tool scoping. The ValidationWorkflow provides a reference implementation of the async generator progress pattern. The refactor implements the currently-NotImplementedError `execute()` methods in FlyWorkflow and RefuelWorkflow.

## Technical Context

**Language/Version**: Python 3.10+ (with `from __future__ import annotations`)
**Primary Dependencies**: Claude Agent SDK (`claude-agent-sdk`), Pydantic, Click, asyncio
**Storage**: N/A (in-memory state during workflow execution; git for persistence)
**Testing**: pytest + pytest-asyncio with mocked runners
**Target Platform**: Linux server (CLI/TUI application)
**Project Type**: Single Python package
**Performance Goals**: 40-60% reduction in AI token consumption per workflow run
**Constraints**: Workflow must complete unattended; individual stage failures must not crash entire workflow
**Scale/Scope**: 2 workflows (FlyWorkflow, RefuelWorkflow), ~8-10 stages each, processing 1-10 tasks/issues per run

## Constitution Check (Pre-Design)

*GATE: Must pass before Phase 0 research.*

| Principle | Status | Evidence |
|-----------|--------|----------|
| I. Async-First | ✅ PASS | Workflows use async generators for progress events; ValidationWorkflow pattern is the reference |
| II. Separation of Concerns | ✅ PASS | Runners handle external systems, agents handle AI judgment, workflows handle orchestration |
| III. Dependency Injection | ✅ PASS | All runners (GitRunner, ValidationRunner, GithubRunner) injectable via constructor |
| IV. Fail Gracefully, Recover Aggressively | ✅ PASS | FR-009a, FR-010a specify graceful degradation; individual stage failures don't crash workflow |
| V. Test-First | ✅ PASS | Mocked runners enable comprehensive unit testing (FR-020, SC-003) |
| VI. Type Safety | ✅ PASS | Pydantic models for config; frozen dataclasses for events; explicit Result types |
| VII. Simplicity | ✅ PASS | No new abstractions; reuses existing runners; no premature patterns |
| VIII. Relentless Progress | ✅ PASS | Exhausted retries continue workflow with draft PR; partial results preserved |

## Constitution Check (Post-Design)

*Re-evaluation after Phase 1 design completion.*

| Principle | Status | Evidence (from design artifacts) |
|-----------|--------|----------------------------------|
| I. Async-First | ✅ PASS | `research.md`: Async generator pattern documented; `contracts/fly-workflow.md`: execute() returns AsyncIterator |
| II. Separation of Concerns | ✅ PASS | `contracts/`: GitRunner, FlyWorkflow, RefuelWorkflow have distinct responsibilities; `agent-tool-permissions.md`: Agents have scoped tools |
| III. Dependency Injection | ✅ PASS | `contracts/fly-workflow.md`: Constructor accepts injectable runners; `quickstart.md`: Mock injection patterns documented |
| IV. Fail Gracefully | ✅ PASS | `contracts/refuel-workflow.md`: Per-issue error isolation; `data-model.md`: State transitions allow FAILED terminal state |
| V. Test-First | ✅ PASS | `quickstart.md`: Test patterns documented; `contracts/`: Test requirements in each contract |
| VI. Type Safety | ✅ PASS | `data-model.md`: All entities use frozen dataclasses or Pydantic models; GitResult defined with slots |
| VII. Simplicity | ✅ PASS | Only 1 new entity (GitRunner); reuses existing patterns from ValidationWorkflow |
| VIII. Relentless Progress | ✅ PASS | `research.md`: Retry pattern with fix agents; `contracts/fly-workflow.md`: Validation exhaustion continues to draft PR |

**Post-Design Assessment**: All principles remain satisfied. No new violations introduced during design phase.

## Project Structure

### Documentation (this feature)

```text
specs/020-workflow-refactor/
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
├── workflows/
│   ├── fly.py           # FlyWorkflow implementation (MODIFY - implement execute())
│   ├── refuel.py        # RefuelWorkflow implementation (MODIFY - implement execute())
│   └── validation.py    # ValidationWorkflow (reference, no changes)
├── runners/
│   ├── command.py       # CommandRunner (existing, no changes)
│   ├── validation.py    # ValidationRunner (existing, no changes)
│   ├── github.py        # GitHubCLIRunner (existing, no changes)
│   ├── coderabbit.py    # CodeRabbitRunner (existing, no changes)
│   └── git.py           # GitRunner (NEW - async git operations wrapper)
├── agents/
│   ├── base.py          # MaverickAgent (existing, no changes)
│   ├── implementer.py   # ImplementerAgent (existing, possibly minor updates)
│   ├── code_reviewer.py # CodeReviewerAgent (existing, no changes)
│   └── generators/      # Lightweight generators (existing, no changes)
└── utils/
    ├── context_builder.py  # Context aggregation (existing, may extend)
    └── git_operations.py   # Sync git utils (existing, reference for GitRunner)

tests/
├── unit/
│   ├── workflows/
│   │   ├── test_fly.py     # FlyWorkflow unit tests (EXTEND - test execute())
│   │   └── test_refuel.py  # RefuelWorkflow unit tests (EXTEND - test execute())
│   └── runners/
│       └── test_git.py     # GitRunner unit tests (NEW)
└── integration/
    └── workflows/
        └── test_fly_e2e.py # End-to-end workflow tests (NEW)
```

**Structure Decision**: Single Python package (existing Maverick structure). Primary changes are implementing `execute()` methods in fly.py and refuel.py, adding GitRunner to runners/, and extending tests. No new directories required.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations. All constitution principles pass.
