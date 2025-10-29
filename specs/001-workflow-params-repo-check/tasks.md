---

description: "Tasks for Parameterized Workflow with Repo Verification"
---

# Tasks: Parameterized Workflow with Repo Verification

**Input**: Design documents from `/specs/001-workflow-params-repo-check/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

**Tests**: Tests are optional. This feature mentions pytest and contract tests, but unless explicitly requested, implementation tasks below exclude test tasks. Independent test criteria are provided per story.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- [P]: Can run in parallel (different files, no dependencies)
- [Story]: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- Single project: `src/`, `tests/` at repository root (per plan.md)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Initialize the Python 3.11 project with uv-managed dependencies and basic tooling.

- [ ] T001 Initialize uv project with Temporal SDK and tooling in pyproject.toml
- [ ] T002 [P] Configure Ruff linter settings in ruff.toml

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core building blocks that MUST be complete before ANY user story.

**CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T003 Create Parameters dataclass defining required keys in src/models/parameters.py
- [ ] T004 [P] Define VerificationResult dataclass and error taxonomy in src/models/verification_result.py
- [ ] T005 [P] Define WorkflowState dataclass and literals in src/models/workflow_state.py
- [ ] T006 Implement GitHub URL normalization utility (HTTPS/SSH → host + owner/repo) in src/utils/url_normalization.py
- [ ] T007 [P] Implement typed parameter accessor utility in src/utils/param_accessor.py
- [ ] T008 [P] Add structured logging helper in src/utils/logging.py
- [ ] T009 Create Temporal worker entrypoint (no registrations yet) in src/workers/main.py

Checkpoint: Foundation ready — user story implementation can now begin.

---

## Phase 3: User Story 1 - Provide Repo URL and Verify (Priority: P1) 🎯 MVP

**Goal**: Start a workflow with `github_repo_url`, verify the repository exists before any downstream steps.

**Independent Test**: Start the workflow with a repository URL and observe a pass/fail verification result without running any other steps.

### Implementation for User Story 1

- [ ] T010 [US1] Implement repo verification activity using gh CLI (auth check + repo view) in src/activities/repo_verification.py
- [ ] T011 [US1] Implement workflow to read params and invoke verification activity in src/workflows/repo_verification_workflow.py
- [ ] T012 [US1] Register workflow and activity with worker in src/workers/main.py
- [ ] T013 [P] [US1] Add auth pre-check (`gh auth status` with host) handling in src/activities/repo_verification.py
- [ ] T014 [P] [US1] Add timeout and single-retry with backoff around gh calls in src/activities/repo_verification.py
- [ ] T015 [P] [US1] Add structured logging for verification lifecycle in src/activities/repo_verification.py
- [ ] T016 [P] [US1] Add structured logging for workflow start/result in src/workflows/repo_verification_workflow.py

Checkpoint: User Story 1 is fully functional and independently testable.

---

## Phase 4: User Story 2 - Parameters Available to Steps (Priority: P2)

**Goal**: All workflow steps can access named parameters provided at workflow start via a consistent accessor.

**Independent Test**: Execute any single step in isolation and confirm it can read the `github_repo_url` parameter by key.

### Implementation for User Story 2

- [ ] T017 [US2] Integrate typed parameter accessor into verification activity in src/activities/repo_verification.py
- [ ] T018 [P] [US2] Add a simple parameter echo activity demonstrating accessor usage in src/activities/param_echo.py
- [ ] T019 [US2] Update workflow to call parameter echo activity after verification in src/workflows/repo_verification_workflow.py

Checkpoint: User Stories 1 and 2 both work independently (US2 demonstrably accesses parameters in steps).

---

## Phase 5: User Story 3 - Clear Failure Handling (Priority: P3)

**Goal**: On verification failure, halt cleanly before any dependent steps and surface actionable guidance.

**Independent Test**: Provide an invalid or unauthorized repository and confirm the run stops with a clear error without executing later steps.

### Implementation for User Story 3

- [ ] T020 [US3] Map failure modes to structured error_code/messages in src/activities/repo_verification.py
- [ ] T021 [US3] Implement workflow state transitions (`pending` → `verified`/`failed`) and early halt in src/workflows/repo_verification_workflow.py
- [ ] T022 [P] [US3] Ensure retry-once with small backoff on transient gh failures in src/activities/repo_verification.py
- [ ] T023 [P] [US3] Add failure result emission to structured logs in src/workers/main.py

Checkpoint: All three user stories are independently functional with clear failure behavior.

---

## Phase N: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories.

- [ ] T024 [P] Document parameter keys and URL formats in specs/001-workflow-params-repo-check/quickstart.md
- [ ] T025 Run Ruff checks and fix lint across src/ (ruff check .)
- [ ] T026 [P] Validate Quickstart end-to-end with dev Temporal server per specs/001-workflow-params-repo-check/quickstart.md
- [ ] T027 Performance tune timeouts/backoff to meet p95≤5s target in src/activities/repo_verification.py
- [ ] T028 [P] Optional: Scaffold HTTP API aligning to contracts at src/api/server.py

---

## Dependencies & Execution Order

### Phase Dependencies

- Setup (Phase 1): No dependencies — start immediately
- Foundational (Phase 2): Depends on Setup completion — BLOCKS all user stories
- User Stories (Phases 3–5): Depend on Foundational; can run in parallel after Phase 2, or sequentially in priority order (P1 → P2 → P3)
- Polish (Final Phase): Depends on desired user stories being complete

### User Story Dependencies

- User Story 1 (P1): No dependency on other stories; requires Phase 2
- User Story 2 (P2): No dependency on US1; requires Phase 2 (demonstrates parameter accessor in steps)
- User Story 3 (P3): Depends on US1’s verification behavior; requires Phase 2

### Contracts Mapping

- /workflows/start → US1 (start run with parameters; returns initial verification result)
- /workflows/{run_id} → US3 (surface run state and failure details)

### Parallel Opportunities

- Setup: T002 can run in parallel with T001
- Foundational: T004–T008 can run in parallel where marked [P]
- US1: T013–T016 can run in parallel with T010–T012 where files differ
- US2: T018 can run in parallel with T017; T019 follows T017
- US3: T022 and T023 can run in parallel with T020; T021 follows T020

---

## Parallel Example: User Story 1

```bash
# Parallelizable tasks for US1 (different files):
Task: "T013 [P] [US1] Add auth pre-check in src/activities/repo_verification.py"
Task: "T014 [P] [US1] Add timeout and retry in src/activities/repo_verification.py"
Task: "T015 [P] [US1] Add structured logging in src/activities/repo_verification.py"
Task: "T016 [P] [US1] Add structured logging in src/workflows/repo_verification_workflow.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Complete Phase 3: User Story 1
4. STOP and VALIDATE: Test User Story 1 independently
5. Deploy/demo if ready

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently → Deploy/Demo (MVP)
3. Add User Story 2 → Test independently → Deploy/Demo
4. Add User Story 3 → Test independently → Deploy/Demo

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Avoid vague tasks; ensure each task includes an exact file path
