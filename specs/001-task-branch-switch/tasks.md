---
description: "Task list for per-task branch switching automation"
---

# Tasks: Per-Task Branch Switching

**Input**: Design documents from `/specs/001-task-branch-switch/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Each user story includes explicit test tasks. Tests remain optional globally, but this feature mandates coverage per the specification.

**Organization**: Tasks are grouped by user story so each increment is independently shippable and testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Maps task to user story (e.g., US1)
- Descriptions include exact file paths to modify or create

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish shared fixtures required across branch management stories.

- [X] T001 Add temporary git repository test helper in `tests/fixtures/git_repo/__init__.py` to bootstrap commits and branches for activity tests.
- [X] T002 Register `git_repo_factory` pytest fixture in `tests/conftest.py` that exposes the new helper to unit and integration suites.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core plumbing that all branch management stories rely on.

- [ ] T004 Add coverage for git helpers in `tests/unit/test_git_cli.py`, exercising success, failure, and invalid branch scenarios.
- [ ] T003 Implement tolerant git command runner and branch name validator in `src/utils/git_cli.py` using structured logging and `errors='replace'` decoding.
- [ ] T004A Extend `src/utils/git_cli.py` helpers to emit standardized error codes and retry hints consumed by branch activities.
- [ ] T005 Scaffold `src/activities/branch_checkout.py` with Temporal activity definitions for branch derive/checkout/reset/delete and structured logging stubs.
- [ ] T006 Update `src/activities/__init__.py` to export the branch checkout activities for worker registration.
- [ ] T009 Add unit tests for branch management models in `tests/unit/test_branch_management_models.py`, covering invariant enforcement and default fields.
- [ ] T007 Create branch management dataclasses (`BranchSelection`, `CheckoutResult`, `MainCheckoutResult`, `DeletionResult`, `BranchExecutionContext`) in `src/models/branch_management.py` enforcing invariants from data-model.md.
- [ ] T008 Expose new branch management types via `src/models/__init__.py` for workflow imports.
- [ ] T011 Extend `tests/unit/test_orchestration_models.py` to validate `TaskDescriptor` invariants and error messaging for missing branch context.
- [ ] T010 Introduce `TaskDescriptor` dataclass with slug/override validation in `src/models/orchestration.py` per data-model.md requirements.

---

## Phase 3: User Story 1 - Branch context prepared (Priority: P1) 🎯 MVP

**Goal**: Ensure each task resolves its git branch and checks it out before any phase runs.

**Independent Test**: Trigger the workflow with a task descriptor and confirm phases start only after `checkout_task_branch` succeeds and the repository head matches the descriptor branch.

### Tests for User Story 1

- [ ] T012 [US1] Add failing unit tests for `derive_task_branch` covering explicit branch overrides and `specs/<slug>/` derivation in `tests/unit/test_branch_checkout_activity.py`.
- [ ] T013 [US1] Add failing unit tests for `checkout_task_branch` handling clean checkouts, idempotent retries, and dirty worktree failures in `tests/unit/test_branch_checkout_activity.py`.
- [ ] T013A [US1] Add failing unit tests for `checkout_task_branch` missing-branch scenarios asserting actionable error payloads and retry metadata in `tests/unit/test_branch_checkout_activity.py`.

### Implementation for User Story 1

- [ ] T014 [US1] Implement `derive_task_branch` in `src/activities/branch_checkout.py` returning `BranchSelection` with audit log messaging.
- [ ] T015 [US1] Implement `checkout_task_branch` in `src/activities/branch_checkout.py` enforcing clean worktree, `git fetch`, `git switch`, and branch verification.
- [ ] T015A [US1] Extend `checkout_task_branch` in `src/activities/branch_checkout.py` to raise structured missing-branch errors with retry-safe details and logging.
- [ ] T016 [US1] Update `src/workflows/multi_task_orchestration.py` to build `TaskDescriptor` per task, gate phase execution on successful branch checkout, and persist the initial `BranchExecutionContext` snapshot before invoking any phases.
- [ ] T017 [US1] Extend `tests/integration/test_multi_task_orchestration.py` to assert branch checkout precedes phase execution and errors on dirty repositories.
- [ ] T018 [US1] Register derive and checkout activities in `src/workers/main.py` so workers can execute the new branch operations.

**Checkpoint**: Workflow blocks phases until branch checkout succeeds and records branch context.

---

## Phase 4: User Story 2 - Post-merge reset (Priority: P2)

**Goal**: Return to a clean, up-to-date main branch and remove the task branch after merge.

**Independent Test**: Simulate a merged PR, run cleanup activities, and confirm the working tree is on main, synchronized, and the task branch is removed locally.

### Tests for User Story 2

- [ ] T019 [US2] Add failing unit tests for `checkout_main` verifying fast-forward pulls, already-on-main short-circuit, and divergent pull errors in `tests/unit/test_branch_checkout_activity.py`.
- [ ] T020 [US2] Add failing unit tests for `delete_task_branch` ensuring deletion success and missing-branch no-ops in `tests/unit/test_branch_checkout_activity.py`.
- [ ] T020A [US2] Add failing unit tests for `delete_task_branch` transient remote failures validating retry hints and structured error payloads in `tests/unit/test_branch_checkout_activity.py`.

### Implementation for User Story 2

- [ ] T021 [US2] Implement `checkout_main` in `src/activities/branch_checkout.py` to switch, fast-forward pull, and validate cleanliness.
- [ ] T022 [US2] Implement `delete_task_branch` in `src/activities/branch_checkout.py` treating absent branches as success and logging reasons.
- [ ] T022A [US2] Implement retry/backoff handling and structured error propagation for remote deletion failures in `src/activities/branch_checkout.py` using standardized git helper codes.
- [ ] T023 [US2] Update `src/workflows/multi_task_orchestration.py` to invoke `checkout_main` and `delete_task_branch` after successful PR automation before proceeding to the next task.
- [ ] T024 [US2] Expand `tests/integration/test_multi_task_orchestration.py` to cover main reset and branch deletion sequencing.
- [ ] T025 [US2] Register cleanup activities with the worker in `src/workers/main.py`, ensuring task queue exposure.

**Checkpoint**: Workflow leaves repository on clean main with task branch removed and logged.

---

## Phase 5: User Story 3 - Branch naming transparency (Priority: P3)

**Goal**: Provide deterministic branch derivation rules and audit logs tying task files to branches.

**Independent Test**: Feed varied task descriptors and confirm derived branches match spec directory slugs, explicit overrides win, and logs expose the branch source.

### Tests for User Story 3

- [ ] T026 [US3] Add unit tests in `tests/unit/test_orchestration_models.py` verifying `TaskDescriptor` slug extraction, explicit overrides, and validation errors for invalid names.
- [ ] T027 [US3] Add unit tests in `tests/unit/test_branch_checkout_activity.py` asserting `BranchSelection` captures source metadata and log message formatting.

### Implementation for User Story 3

- [ ] T028 [US3] Enhance `TaskDescriptor` in `src/models/orchestration.py` to expose a `resolved_branch` property cached for workflow use.
- [ ] T029 [US3] Update `src/workflows/multi_task_orchestration.py` to enrich the stored `BranchExecutionContext` with audit metadata (branch source, slug, timestamps) and emit structured transparency logs.
- [ ] T030 [US3] Extend `src/models/orchestration.py` and related serializers to include optional branch context in `TaskResult`, updating tests accordingly.
- [ ] T031 [US3] Surface branch derivation decisions via CLI output in `src/cli/orchestrate.py`, including optional explicit overrides and validation messages for operators.

**Checkpoint**: Operators can trace each task file to its branch via logs, CLI output, and stored context.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Wrap-up tasks spanning multiple stories.

- [ ] T032 Refresh `specs/001-task-branch-switch/quickstart.md` with verification steps for branch context logging and cleanup validation.
- [ ] T032A Instrument workflow telemetry to capture branch derivation, checkout timing, and main restoration metrics satisfying SC-001 and SC-002.
- [ ] T032B Build automated branch deletion success aggregation covering SC-003 and persist reason codes for non-deletions.
- [ ] T032C Establish operator incident review loop for wrong-branch executions, capturing SC-004 feedback in monitoring channels.
- [ ] T032D Implement SC-001 audit pipeline that samples at least 10 completed tasks, compares recorded branch logs with git history, and reports discrepancies for remediation.
- [ ] T033 Run `uv run pytest` and `uv run ruff check .` to confirm green tests and lint after feature completion.

---

## Dependencies & Execution Order

- Complete Phase 1 before touching activities or models; fixtures enable deterministic git tests.
- Phase 2 tasks block all user stories by introducing shared helpers, models, and activity scaffolding.
- User stories progress in priority order (US1 → US2 → US3) with each relying on the previous phase's branch context enhancements.
- Polish tasks run only after all targeted user stories deliver their increments and tests.

## Parallel Opportunities

- **Setup**: T001 and T002 are sequential (fixture creation precedes registration).
- **US1**: After T014 and T015 land, T017 and T018 can proceed while integration scenarios (T017) and worker wiring (T018) run independently.
- **US2**: T021 and T022 can be implemented in parallel once T019–T020 establish expected behaviors.
- **US3**: T029 and T031 operate on different layers (workflow vs CLI) and can proceed concurrently after T028 introduces `resolved_branch`.

## Implementation Strategy

1. Establish git fixtures and core helpers (Phases 1–2) so subsequent stories share deterministic tooling.
2. Deliver MVP (US1) to guarantee branch checkout before any phase executions.
3. Layer post-merge cleanup (US2) to leave the repository stabilized for subsequent tasks.
4. Add transparency enhancements (US3) that expose branch derivation sources and persist audit context.
5. Finish with documentation refresh and quality gates to validate the end-to-end branch automation.
