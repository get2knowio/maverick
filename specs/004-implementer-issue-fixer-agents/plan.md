# Implementation Plan: ImplementerAgent and IssueFixerAgent

**Branch**: `004-implementer-issue-fixer-agents` | **Date**: 2025-12-14 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/004-implementer-issue-fixer-agents/spec.md`

## Summary

Implement two specialized agents extending `MaverickAgent`:
1. **ImplementerAgent**: Executes structured task lists (tasks.md) with TDD approach, supporting sequential and parallel task execution, automatic validation, and conventional commits.
2. **IssueFixerAgent**: Resolves GitHub issues with minimal, targeted code changes, fetching issue details via GitHub CLI, implementing fixes, and verifying resolution.

Both agents share validation patterns (format/lint/test), git commit handling, and error recovery strategies. They integrate with the existing `MaverickAgent` base class and follow established patterns from `CodeReviewerAgent`.

## Technical Context

**Language/Version**: Python 3.10+ (with `from __future__ import annotations`)
**Primary Dependencies**: Claude Agent SDK (`claude-agent-sdk`), Pydantic, Git CLI, GitHub CLI (`gh`)
**Storage**: N/A (file system for task files, Git for commits)
**Testing**: pytest + pytest-asyncio (all tests async-compatible)
**Target Platform**: Linux/macOS CLI
**Project Type**: single (existing `src/maverick/` structure)
**Performance Goals**: Task execution <5 min/task, issue fixes <10 min/issue (spec SC-005, SC-006)
**Constraints**: Validation auto-fix within 3 retries (SC-007), minimal code changes for fixes (<100 lines typical)
**Scale/Scope**: Task files up to 50+ tasks, concurrent parallel sub-agents

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Pre-Phase 0 Gate

| Principle | Compliance | Notes |
|-----------|------------|-------|
| **I. Async-First** | ✅ PASS | Both agents use `async def execute()`, async generators for progress, asyncio for parallel sub-agents |
| **II. Separation of Concerns** | ✅ PASS | Agents know HOW (prompts, tools, SDK); Workflows know WHEN (FlyWorkflow, RefuelWorkflow orchestrate) |
| **III. Dependency Injection** | ✅ PASS | MCP servers passed via constructor, config injected, git/gh clients injectable for testing |
| **IV. Fail Gracefully, Recover Aggressively** | ✅ PASS | Retry with exponential backoff, aggregate partial results, continue on sub-agent failure (FR-006a, FR-015a, FR-024a) |
| **V. Test-First** | ✅ PASS | TDD required per spec, mock external deps (Claude API, GitHub CLI, filesystem) |
| **VI. Type Safety** | ✅ PASS | Complete type hints, Pydantic models for results/contexts, dataclasses for value objects |
| **VII. Simplicity** | ✅ PASS | No global state, extends existing MaverickAgent, no premature abstractions |
| **VIII. Relentless Progress** | ✅ PASS | Checkpoint after commits, isolate task failures, auto-recover git/GitHub issues, preserve partial work |

**Gate Status**: ✅ PASSED - No violations requiring justification

## Project Structure

### Documentation (this feature)

```text
specs/004-implementer-issue-fixer-agents/
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
├── __init__.py
├── agents/
│   ├── __init__.py
│   ├── base.py              # MaverickAgent ABC (existing)
│   ├── code_reviewer.py     # CodeReviewerAgent (existing reference)
│   ├── context.py           # AgentContext (existing)
│   ├── result.py            # AgentResult, AgentUsage (existing)
│   ├── implementer.py       # NEW: ImplementerAgent
│   └── issue_fixer.py       # NEW: IssueFixerAgent
├── models/
│   ├── __init__.py
│   ├── review.py            # ReviewResult, ReviewFinding (existing)
│   ├── implementation.py    # NEW: ImplementationResult, ImplementerContext, TaskFile, Task
│   └── issue_fix.py         # NEW: FixResult, IssueFixerContext
├── utils/
│   ├── __init__.py
│   ├── git.py               # NEW: Git helper utilities (commit, stash, recovery)
│   ├── github.py            # NEW: GitHub CLI wrapper with retry logic
│   ├── validation.py        # NEW: Validation runner (format, lint, test)
│   └── task_parser.py       # NEW: Task file parser (.specify tasks.md format)
├── exceptions.py            # Extended with new error types
└── ...

tests/
├── unit/
│   ├── agents/
│   │   ├── test_implementer.py      # NEW
│   │   └── test_issue_fixer.py      # NEW
│   ├── models/
│   │   ├── test_implementation.py   # NEW
│   │   └── test_issue_fix.py        # NEW
│   └── utils/
│       ├── test_git.py              # NEW
│       ├── test_github.py           # NEW
│       ├── test_validation.py       # NEW
│       └── test_task_parser.py      # NEW
└── integration/
    ├── test_implementer_e2e.py      # NEW
    └── test_issue_fixer_e2e.py      # NEW
```

**Structure Decision**: Single project layout following existing `src/maverick/` structure. New agents in `agents/`, new models in `models/`, shared utilities in `utils/`. Tests mirror source structure.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations requiring justification. Design follows existing patterns established by `MaverickAgent` and `CodeReviewerAgent`.

---

## Post-Phase 1 Constitution Re-Check

*Re-evaluated after Phase 1 design completion.*

| Principle | Compliance | Design Evidence |
|-----------|------------|-----------------|
| **I. Async-First** | ✅ PASS | All agent methods async, `asyncio.gather()` for parallel tasks, async subprocess for git/gh |
| **II. Separation of Concerns** | ✅ PASS | Agents in `agents/`, models in `models/`, utilities in `utils/` - clear boundaries |
| **III. Dependency Injection** | ✅ PASS | `mcp_servers` param in constructor, context objects for runtime config |
| **IV. Fail Gracefully** | ✅ PASS | `TaskResult.error` captures failures, `ImplementationResult` aggregates partial results |
| **V. Test-First** | ✅ PASS | Test file structure defined, quickstart scenarios for verification |
| **VI. Type Safety** | ✅ PASS | All models use Pydantic `BaseModel` with `Field()` constraints and validators |
| **VII. Simplicity** | ✅ PASS | Reuses existing patterns, no new abstractions beyond what spec requires |
| **VIII. Relentless Progress** | ✅ PASS | `commits` list tracks checkpoints, retry logic in all external calls |

**Post-Design Gate Status**: ✅ PASSED - Ready for task generation

---

## Generated Artifacts

| Artifact | Path | Description |
|----------|------|-------------|
| Plan | `specs/004-implementer-issue-fixer-agents/plan.md` | This file |
| Research | `specs/004-implementer-issue-fixer-agents/research.md` | SDK patterns, git/gh handling, error recovery |
| Data Model | `specs/004-implementer-issue-fixer-agents/data-model.md` | All Pydantic models and enums |
| Contracts | `specs/004-implementer-issue-fixer-agents/contracts/agent-interfaces.md` | Agent interface specifications |
| Quickstart | `specs/004-implementer-issue-fixer-agents/quickstart.md` | Verification scenarios |

---

## Next Steps

1. Run `/speckit.tasks` to generate `tasks.md` from this plan
2. Review generated tasks for completeness
3. Begin implementation following task order
