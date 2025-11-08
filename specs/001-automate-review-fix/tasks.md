# Tasks: Automated Review & Fix Loop for AI-Generated Rust Changes

**Input**: Design documents from `/specs/001-automate-review-fix/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Test tasks are included because the specification mandates TDD and explicit acceptance scenarios for each user story.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Scaffold core modules and entry points required by all user stories.

- [x] T001 Bootstrap review-fix activity module with structured logger stub in `src/activities/review_fix.py`
- [x] T002 Wire review-fix activity into `src/activities/__init__.py` exports and `src/workers/main.py` registration list
- [x] T003 Create manual invocation CLI stub in `src/cli/review_fix.py` and add `review-fix-activity` script alias to `pyproject.toml`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared models and utilities that every user story depends on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T004 Create review loop dataclasses with invariants in `src/models/review_fix.py`
- [X] T005 [P] Export review loop models from `src/models/__init__.py` and add type hints where referenced
- [X] T006 Implement deterministic fingerprint helper in `src/utils/retry_fingerprint.py`
- [X] T007 Extend artifact persistence to handle sanitized prompts and fix summaries in `src/utils/phase_results_store.py`

**Checkpoint**: Foundation ready — user story implementation can now begin in parallel.
- All models pass type checks and invariant validation tests
- All utilities are exported with proper type hints and have passing unit tests
- Artifact persistence handles sanitized prompts and fix summaries with passing tests

---

## Phase 3: User Story 1 – Automation flags review outcome (Priority: P1) 🎯 MVP

**Goal**: Deliver a Temporal activity run that invokes CodeRabbit and reports "clean" or "issues-found" without applying fixes.

**Independent Test**: Run the activity on a branch with recent AI changes and verify it returns a structured "clean" or "issues-found" outcome without needing the fix portion.

### Tests for User Story 1 ⚠️

- [X] T008 [P] [US1] Author failing unit tests for review-only outcomes and CodeRabbit failure handling in `tests/unit/test_review_fix_activity.py`
- [X] T009 [P] [US1] Add integration test covering clean vs issues outcomes plus malformed CodeRabbit output in `tests/integration/test_review_fix_loop.py`

### Implementation for User Story 1

- [X] T010 [P] [US1] Invoke CodeRabbit via uv-managed subprocess and capture transcripts in `src/activities/review_fix.py`
- [X] T011 [US1] Parse CodeRabbit transcript into `CodeReviewFindings` and sanitize summaries in `src/activities/review_fix.py`
- [X] T012 [US1] Emit `ReviewLoopOutcome` for clean/issues states and persist artifacts via `src/utils/phase_results_store.py`

**Checkpoint**: User Story 1 is fully functional and testable independently.
- All unit tests for review-only outcomes pass with 90%+ coverage
- Integration test successfully handles clean and issues-found scenarios
- CodeRabbit subprocess invocation properly handles timeouts and errors

---

## Phase 4: User Story 2 – Automation applies guided fixes (Priority: P2)

**Goal**: When CodeRabbit reports actionable findings, automatically invoke OpenCode to apply fixes and rerun validation.

**Independent Test**: Provide a branch where CodeRabbit flags fixable issues and confirm the activity re-invokes OpenCode with the sanitized prompt, applies fixes, and re-runs validation.

### Tests for User Story 2 ⚠️

- [X] T013 [P] [US2] Add failing unit tests for OpenCode invocation, fixed-status emission, and failure escalation diagnostics in `tests/unit/test_review_fix_activity.py`
- [X] T014 [P] [US2] Extend integration test to cover successful fix runs and failure edge cases in `tests/integration/test_review_fix_loop.py`
- [X] T025 [P] [US2] Create resilience tests for OpenCode refusing prompts or producing no changes, ensuring sanitized artifacts in `tests/integration/test_review_fix_loop.py`

### Implementation for User Story 2

- [X] T015 [P] [US2] Implement sanitized prompt builder, OpenCode CLI invocation, and fixed-status result assembly in `src/activities/review_fix.py`
- [X] T016 [US2] Execute validation command with tolerant decoding, capture durations, and classify outcomes in `src/activities/review_fix.py`
- [X] T017 [US2] Persist fix attempt metadata, sanitized prompts, validation logs, and failure diagnostics via `src/utils/phase_results_store.py`
- [X] T026 [US2] Implement failure escalation paths that surface actionable diagnostics when CodeRabbit, OpenCode, or validation fails in `src/activities/review_fix.py`

**Checkpoint**: User Stories 1 and 2 operate independently and satisfy acceptance scenarios.
- All OpenCode invocation and fix application tests pass
- Validation command execution properly handles errors with tolerant decoding
- Failure diagnostics are persisted and accessible for all error paths

---

## Phase 5: User Story 3 – Automation supports safe retries (Priority: P3)

**Goal**: Ensure retries detect duplicate findings and avoid reapplying the same fixes while surfacing stored artifacts.

**Independent Test**: Execute the activity twice in succession against the same branch when no new commits were added and confirm the second run does not reapply the same fix attempt.

### Tests for User Story 3 ⚠️

- [X] T018 [P] [US3] Create unit tests validating fingerprint generation and retry short-circuiting in `tests/unit/test_retry_fingerprint.py`
- [X] T019 [P] [US3] Extend integration retry scenario in `tests/integration/test_review_fix_loop.py`

### Implementation for User Story 3

- [X] T020 [US3] Integrate fingerprint helper into retry flow within `src/activities/review_fix.py`
- [X] T021 [US3] Persist and surface retry metadata via `src/utils/phase_results_store.py` and `src/models/review_fix.py`

**Checkpoint**: User Story 3 prevents duplicate fix applications.
- Fingerprint computation is deterministic and passes all unit tests
- Retry detection correctly short-circuits on duplicate fingerprints
- Retry metadata is persisted and properly surfaced in outcomes

**Checkpoint**: All user stories now support idempotent retries with auditable artifacts.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Finalize documentation, logging, and quality gates that span all stories.

- [X] T022 [P] Update manual execution guidance in `specs/001-automate-review-fix/quickstart.md`
- [X] T023 Validate worker integration and logging fields in `src/workflows/phase_automation.py` and `src/activities/phase_runner.py`
- [X] T024 Run `uv run ruff check .` and `uv run pytest` to confirm feature readiness
- [X] T027 Add timing instrumentation metrics to surface SC-001/SC-002 performance data in `src/activities/review_fix.py`
- [X] T028 Validate recorded durations and first-pass fix metrics via new assertions in `tests/integration/test_review_fix_loop.py`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)** → enables Foundational work
- **Foundational (Phase 2)** → blocks all user stories until shared models/utilities exist
- **User Story Phases (3–5)** → depend on Foundational phase completion; can proceed sequentially by priority or in parallel with coordination
- **Polish (Phase 6)** → runs after desired user stories are complete

### User Story Dependencies

- **US1 (P1)**: No dependency on other stories once foundation is ready
- **US2 (P2)**: Depends on US1 artifacts for findings parsing and sanitized prompts
- **US3 (P3)**: Depends on US1/US2 outputs to compute fingerprints and retry metadata

### Within Each User Story

- Write failing tests before implementation tasks
- Implement CLI/utility logic before persistence/logging steps
- Ensure outcome emission occurs after underlying helpers are in place

---

## Parallel Opportunities

- [P] tasks in Setup and Foundational phases (T005) can execute concurrently once their prerequisites exist
- User story test tasks (T008, T009, T013, T014, T018, T019) can be tackled in parallel across different files
- Implementation tasks flagged [P] (T010, T015) can proceed concurrently after tests are in place, provided team members coordinate on shared modules

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 (Setup)
2. Complete Phase 2 (Foundational)
3. Deliver Phase 3 (US1) with passing tests and artifact persistence
4. Validate outputs via integration test before expanding scope

### Incremental Delivery

1. Finish Setup + Foundational
2. Implement US1 → validate & demo clean/issues outcomes
3. Layer in US2 → validate automated fixes end-to-end
4. Add US3 → validate retry idempotency
5. Apply Polish tasks and run full quality gate

### Parallel Team Strategy

- Developer A focuses on models/utilities (Phases 1–2)
- Developer B tackles US1 tests/implementation
- Developer C prepares US2/US3 test scaffolding in parallel once foundation completes
- Reconvene for Polish tasks and final verification
