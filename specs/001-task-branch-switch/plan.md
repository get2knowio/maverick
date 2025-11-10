# Implementation Plan: Per-Task Branch Switching

**Branch**: `001-task-branch-switch` | **Date**: 2025-11-10 | **Spec**: `specs/001-task-branch-switch/spec.md`
**Input**: Feature specification from `/specs/001-task-branch-switch/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Extend the Temporal automation workflow so each task resolves its git branch, checks out the branch before any phase runs, and returns to a clean, up-to-date `main` after the task completes. Implement supporting activities for branch derivation, checkout, main reset, and cleanup, capturing audit logs throughout.

## Technical Context

**Language/Version**: Python 3.11  
**Primary Dependencies**: Temporal Python SDK, git CLI (via subprocess), uv toolchain, structured logging utilities  
**Storage**: N/A (Temporal workflow state only)  
**Testing**: pytest with Temporal workflow/activity fixtures  
**Target Platform**: Linux Temporal worker containers (dev container + CI)  
**Project Type**: Backend automation (Temporal workflows, activities, CLI)  
**Performance Goals**: Complete branch operations within existing workflow activity timeouts (≤120s)  
**Constraints**: Deterministic workflows, clean working tree guarantees, idempotent branch activities, UV-only tooling  
**Scale/Scope**: Single-repository automation supporting sequential Speckit tasks per workflow run

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Simplicity First**: Reuse existing activity and workflow scaffolding; introduce only targeted git branch helpers. ✅
- **II. Test-Driven Development**: Plan includes new pytest coverage for each activity and workflow branch path before implementation. ✅
- **III. UV-Based Development**: All scripts continue to run through uv; no conflicting tooling introduced. ✅
- **IV. Temporal-First Architecture**: Branch logic implemented as activities with deterministic workflow orchestration; no side effects inside workflows. ✅
- **V. Observability & Monitoring**: Activities will emit structured JSON logs capturing branch decisions and outcomes. ✅
- **VI. Documentation Standards**: Feature docs confined to `specs/001-task-branch-switch/`; no durable docs impacted. ✅

Gate Status: **PASS** (initial)

Post-Phase-1 Review: **PASS** — design artifacts preserve Temporal determinism, UV tooling, and observability requirements without introducing new complexity.

## Project Structure

### Documentation (this feature)

```text
specs/001-task-branch-switch/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)
```text
src/
├── activities/
│   ├── __init__.py
│   ├── phase_runner.py
│   ├── pr_ci_automation.py
│   └── (new) branch_checkout.py            # git branch management activities
├── workflows/
│   ├── multi_task_orchestration.py
│   ├── phase_automation.py
│   └── (updated) multi_task_orchestration.py to orchestrate branch phases
├── workers/
│   └── main.py
├── utils/
│   ├── logging.py
│   └── (possible) git_cli.py               # shared git subprocess helpers
└── cli/
    └── orchestrate.py

tests/
├── fixtures/
│   └── multi_task_orchestration/
├── integration/
│   └── test_multi_task_orchestration.py
└── unit/
    ├── test_branch_checkout_activity.py    # new activity tests
    └── workflows/
        └── test_branch_orchestration.py    # new workflow path tests
```

**Structure Decision**: Extend the existing single-project Temporal layout. Add a dedicated `branch_checkout.py` activity module (plus optional shared git helpers) and corresponding unit/integration test coverage alongside current workflow orchestration files.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |
