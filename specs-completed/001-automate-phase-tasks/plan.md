# Implementation Plan: Temporal Phase Automation for tasks.md

**Branch**: `001-automate-phase-tasks` | **Date**: 2025-11-08 | **Spec**: [specs/001-automate-phase-tasks/spec.md](specs/001-automate-phase-tasks/spec.md)
**Input**: Feature specification from `/specs/001-automate-phase-tasks/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Implement a Temporal workflow that parses Speckit-generated `tasks.md` files, executes each phase sequentially via an AI-backed `run_phase` activity that wraps `speckit.implement`, maintains checkpoints for resume support, exposes per-phase AI overrides, enforces tolerant CLI output decoding, and emits structured per-phase execution reports retrievable through workflow queries and CLI commands.

## Technical Context

<!--
  ACTION REQUIRED: Replace the content in this section with the technical details
  for the project. The structure here is presented in advisory capacity to guide
  the iteration process.
-->

**Language/Version**: Python 3.11  
**Primary Dependencies**: Temporal Python SDK, uv toolchain, OpenCode CLI (`speckit.implement`)  
**Storage**: Temporal workflow state (no new external stores)  
**Testing**: pytest with Temporal workflow/activity fixtures  
**Target Platform**: Linux Temporal workers running in containerized environments  
**Project Type**: Temporal workflows with supporting activities and CLI integration  
**Performance Goals**: Sustain long-running AI-backed phases (≥30 min timeout) while processing sequential phases without overlapping activity runs  
**Constraints**: Strict workflow determinism; activities must tolerate CLI failures, expose configurable timeout/backoff overrides, decode CLI output with `errors="replace"`, and produce structured logs
**Scale/Scope**: Designed for multi-phase Speckit plans (dozens of tasks) executed on a single repo per workflow run with phase-specific AI configuration metadata

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Simplicity First**: Reuse existing Temporal project structure; no additional services introduced. ✅
- **Test-Driven Development**: Plan requires unit tests for parsing and activities plus workflow integration tests before implementation. ✅
- **UV-Based Development**: All commands (tests, lint, CLI) executed via `uv run`; existing tooling satisfies requirement. ✅
- **Temporal-First Architecture**: Workflow remains orchestration-only; parsing, CLI calls, and verification live in activities to preserve determinism. ✅
- **Observability & Logging**: Structured JSON logging for activities, `workflow.logger` usage for progress events, and persisted phase reports ensure compliance. ✅

*Post-Phase 1 Review*: Design artifacts maintain alignment with constitution mandates; no new violations identified.

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)
<!--
  ACTION REQUIRED: Replace the placeholder tree below with the concrete layout
  for this feature. Delete unused options and expand the chosen structure with
  real paths (e.g., apps/admin, packages/something). The delivered plan must
  not include Option labels.
-->

```text
src/
├── activities/
├── cli/
├── common/
├── models/
├── utils/
├── workers/
└── workflows/

tests/
├── integration/
└── unit/
```

**Structure Decision**: The feature extends the existing Temporal-centric layout (activities, workflows, workers) and corresponding `tests/unit` + `tests/integration` suites without introducing new top-level packages.

## Data Model Notes

- `PhaseExecutionHints` captures per-phase overrides (model, agent profile, timeout/backoff adjustments) parsed from markdown metadata and validated before activities execute.
- `ResumeState` encapsulates checkpoint hash comparisons and earliest-incomplete phase tracking to support deterministic resume flows.
- Existing models (`PhaseDefinition`, `TaskItem`, `PhaseExecutionContext`, `PhaseResult`, `WorkflowCheckpoint`) extend to record tolerant-decoding artifact paths so automation consumers can retrieve sanitized and raw logs.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |
