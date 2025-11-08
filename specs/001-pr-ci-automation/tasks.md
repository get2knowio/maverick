# Tasks: PR CI Automation

**Input**: Design documents from `/specs/001-pr-ci-automation/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Each user story defines focused unit and integration coverage; add only the tests listed below.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Shared scaffolding for fixtures and common helpers

- [X] T001 Create shared gh CLI stub helper in `tests/fixtures/pr_ci_automation/gh_cli_stub.py`
- [X] T002 Register gh CLI stub fixture for tests in `tests/conftest.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core data structures and persistence every story depends on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T003 Scaffold `src/activities/pr_ci_automation.py` with activity entrypoint, structured logger, and TODO placeholders
- [X] T004 Implement PR automation request/result dataclasses with validation, including SLA timing fields, in `src/models/phase_automation.py`
- [X] T005 Extend PR phase result persistence to handle automation payloads and SLA metrics in `src/utils/phase_results_store.py`
- [X] T006 Add model validation tests for new dataclasses in `tests/unit/test_phase_automation_models.py`
- [X] T028 Add remote branch existence and target resolution unit coverage in `tests/unit/test_pr_ci_automation_activity.py`
- [X] T029 Implement remote branch existence and target resolution helpers in `src/activities/pr_ci_automation.py`

**Checkpoint**: Data models and stubs ready for story-specific behavior

---

## Phase 3: User Story 1 - Automation merges a healthy PR (Priority: P1) 🎯 MVP

**Goal**: Create or reuse a pull request, monitor green CI, and merge automatically.

**Independent Test**: Start the activity against a branch that passes CI and confirm it publishes the PR, observes success, merges, and reports merge metadata without human help.

### Tests for User Story 1

- [X] T007 [US1] Add success-path unit coverage for PR creation, polling, and merge in `tests/unit/test_pr_ci_automation_activity.py`
- [X] T030 [US1] Add timeout and no-check polling coverage in `tests/unit/test_pr_ci_automation_activity.py`
- [X] T031 [US1] Add PR body update coverage when AI summary changes in `tests/unit/test_pr_ci_automation_activity.py`
- [X] T038 [US1] Add unit coverage for base-branch mismatch error handling in `tests/unit/test_pr_ci_automation_activity.py`
- [X] T040 [US1] Add unit coverage for polling metrics emission and SLA timing thresholds in `tests/unit/test_pr_ci_automation_activity.py`
- [X] T008 [P] [US1] Add green-path workflow integration test in `tests/integration/test_pr_ci_automation_workflow.py`
- [X] T039 [P] [US1] Add workflow integration test verifying base-branch mismatch returns structured `error` output in `tests/integration/test_pr_ci_automation_workflow.py`

### Implementation for User Story 1

- [X] T009 [US1] Implement PR discovery and creation helpers using `gh pr view/create` in `src/activities/pr_ci_automation.py`
- [X] T010 [US1] Implement CI polling loop with deterministic backoff, including empty-check handling and timeout returns, in `src/activities/pr_ci_automation.py`
- [X] T032 [US1] Update existing PR descriptions with new AI summaries while preserving human edits in `src/activities/pr_ci_automation.py`
- [X] T041 [US1] Implement base-branch alignment guard that returns an `error` result before merge in `src/activities/pr_ci_automation.py`
- [X] T042 [US1] Emit per-poll SLA metrics (status detection latency, merge duration) in `src/activities/pr_ci_automation.py`
- [X] T043 [US1] Surface SLA metrics and mismatch context through workflow orchestration in `src/workflows/phase_automation.py` and `src/utils/phase_results_store.py`
- [X] T011 [US1] Implement merge execution and optional branch deletion via `gh pr merge --merge --auto` in `src/activities/pr_ci_automation.py`
- [X] T012 [US1] Invoke PR automation activity from orchestrator in `src/workflows/phase_automation.py`
- [X] T013 [US1] Register PR automation activity with worker lifecycle in `src/workers/main.py`
- [X] T014 [US1] Export activity entrypoint from `src/activities/__init__.py`

**Checkpoint**: Healthy PR path merges automatically and workflows receive merge metadata

---

## Phase 4: User Story 2 - Automation surfaces failing CI for remediation (Priority: P1)

**Goal**: Capture failing CI evidence and return it without merging so remediation can proceed.

**Independent Test**: Run the activity on a branch whose CI fails; confirm it captures failing job names and log URLs, returns `ci_failed`, and leaves the PR open.

### Tests for User Story 2

- [X] T015 [US2] Add failure-path unit coverage for job aggregation and payload shaping in `tests/unit/test_pr_ci_automation_activity.py`
- [X] T034 [US2] Validate deterministic result payload schema across statuses in `tests/unit/test_pr_ci_automation_activity.py`
- [X] T035 [US2] Differentiate CLI/system errors from CI failures in `tests/unit/test_pr_ci_automation_activity.py`
- [X] T016 [P] [US2] Add workflow integration test exercising `ci_failed` output in `tests/integration/test_pr_ci_automation_workflow.py`

### Implementation for User Story 2

- [X] T017 [US2] Parse `gh run`/`gh pr checks` output to assemble `CiFailureDetail` entries in `src/activities/pr_ci_automation.py`
- [X] T018 [US2] Return structured `ci_failed` result with logging telemetry in `src/activities/pr_ci_automation.py`
- [X] T019 [US2] Persist failure evidence for downstream remediation in `src/workflows/phase_automation.py`
- [X] T036 [US2] Emit deterministic result payloads for all statuses in `src/activities/pr_ci_automation.py` and extend dataclasses in `src/models/phase_automation.py`
- [X] T037 [US2] Map actionable `error` results with structured logging in `src/activities/pr_ci_automation.py`

**Checkpoint**: Failing CI paths stop before merge and surface actionable evidence

---

## Phase 5: User Story 3 - Automation safely resumes mid-cycle (Priority: P2)

**Goal**: Resume automation after retries or interruptions without duplicating actions or corrupting history.

**Independent Test**: Re-run the activity after partial progress; confirm it reuses existing PRs, respects prior CI state, and returns consistent outputs for merged PRs.

### Tests for User Story 3

- [X] T020 [US3] Add idempotency and resume unit coverage in `tests/unit/test_pr_ci_automation_activity.py`
- [X] T021 [P] [US3] Add workflow integration test covering resume scenarios in `tests/integration/test_pr_ci_automation_workflow.py`

### Implementation for User Story 3

- [X] T022 [US3] Implement resume logic to reuse existing PRs and detect merged/timeout states in `src/activities/pr_ci_automation.py`
- [X] T023 [US3] Persist last-known PR metadata and run identifiers for resumption in `src/utils/phase_results_store.py`
- [X] T024 [US3] Update workflow orchestration to short-circuit completed PRs and feed stored metadata forward in `src/workflows/phase_automation.py`

**Checkpoint**: Automation can resume safely without duplicating PR actions

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final documentation and quality gates

- [X] T025 Document success, failure, and resume flows in `specs/001-pr-ci-automation/quickstart.md`
- [X] T026 Run full validation (`uv run pytest` + `uv run ruff check .`) from repository root `/workspaces/maverick`
- [X] T027 Add PR automation overview to maintenance documentation in `README.md`

---

## Dependencies & Execution Order

- **Setup → Foundational → Stories → Polish**: Each phase depends on completion of the previous phase.
- **User Stories**: US1 and US2 (both P1) may begin once Foundational is complete; US3 (P2) begins after US1 stabilizes shared activity logic.
- **Within Stories**: Tests precede implementation. Activity changes (T009/T010/T011/T017/T018/T022/T032/T036/T037/T041/T042/T043) must land before workflow/worker wiring (T012/T013/T019/T024).

## Parallel Opportunities

- T008 can run alongside T007 once foundational scaffolding exists.
- T016 can run alongside T015 after failure fixtures are ready.
- T021 can run alongside T020 with resume fixtures in place.
- Documentation (T025, T027) can progress while T026 validation runs, provided prior phases are stable.

## Implementation Strategy

1. Complete Setup and Foundational phases to establish fixtures, stubs, and validated data models.
2. Deliver MVP by finishing User Story 1 (tests then implementation), enabling automated merges for green PRs.
3. Layer in User Story 2 to expose failing CI evidence without regressing MVP behavior.
4. Add User Story 3 to guarantee idempotent resumes across retries and replays.
5. Conclude with documentation updates and full validation runs.
