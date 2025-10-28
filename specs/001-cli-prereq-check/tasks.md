---

description: "Tasks for implementing CLI Prerequisite Check"
---

# Tasks: CLI Prerequisite Check

Input: Design documents from `/specs/001-cli-prereq-check/`
Prerequisites: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

Tests: Tests are INCLUDED (TDD required by plan).
Organization: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- [P]: Can run in parallel (different files, no dependencies)
- [Story]: Which user story this task belongs to (e.g., US1, US2)
- Include exact file paths in descriptions

## Path Conventions

- Single project: `src/`, `tests/` at repository root (per plan.md)

---

## Phase 1: Setup (Shared Infrastructure)

Purpose: Project initialization and basic structure

- [X] T001 Create project structure (dirs) at repo root: src/activities/, src/workflows/, src/workers/, src/cli/, src/models/, tests/unit/, tests/integration/
- [X] T002 Initialize Python project with uv: create `pyproject.toml` with project metadata at `pyproject.toml`
- [X] T003 [P] Add core dependencies in `pyproject.toml` ([tool.uv] and [project.dependencies]): temporalio, pytest, pytest-asyncio
- [X] T004 [P] Configure ruff linting in `pyproject.toml` ([tool.ruff]) and add `ruff check .` task

---

## Phase 2: Foundational (Blocking Prerequisites)

Purpose: Core infrastructure that MUST be complete before ANY user story can be implemented

⚠️ CRITICAL: No user story work can begin until this phase is complete

- [ ] T005 Create data models per data-model.md: define `PrereqCheckResult` and `ReadinessSummary` dataclasses in `src/models/prereq.py`
- [ ] T006 [P] Add structured logging setup in `src/common/logging.py` (formatter, level, module logger helper)
- [ ] T007 [P] Create test scaffolding: `tests/conftest.py` with common fixtures and Temporal test env bootstrap (placeholder)

Checkpoint: Foundation ready — user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Verify CLI prerequisites (Priority: P1) 🎯 MVP

Goal: A readiness check verifies gh is installed/authenticated and copilot binary is available; outputs pass/fail summary and overall status.

Independent Test: Run the readiness check with tools properly installed/authenticated; it reports success without requiring other features.

### Tests for User Story 1 (write first)

- [ ] T008 [P] [US1] Unit test for gh auth status parsing and exit codes in `tests/unit/test_gh_status.py`
- [ ] T009 [P] [US1] Unit test for copilot availability (`copilot help`) in `tests/unit/test_copilot_help.py`
- [ ] T010 [US1] Integration test for readiness workflow orchestration in `tests/integration/test_readiness_workflow.py`

### Implementation for User Story 1

- [ ] T011 [P] [US1] Implement gh_status activity function in `src/activities/gh_status.py` (non-interactive, parse `gh auth status`)
- [ ] T012 [P] [US1] Implement copilot_help activity function in `src/activities/copilot_help.py` (execute `copilot help` safely)
- [ ] T013 [US1] Implement readiness workflow in `src/workflows/readiness.py` (call both activities; assemble `ReadinessSummary`)
- [ ] T014 [US1] Implement Temporal worker to host activities/workflows in `src/workers/readiness_worker.py`
- [ ] T015 [US1] Implement CLI entrypoint to trigger workflow and print human-readable summary in `src/cli/readiness.py`
- [ ] T016 [US1] Add uv scripts in `pyproject.toml` for `uv run readiness:worker` and `uv run readiness:check`
- [ ] T017 [US1] Add structured logging in activities/workflow per constitution (use `src/common/logging.py`)

Checkpoint: At this point, User Story 1 should be fully functional and testable independently

---

## Phase 4: User Story 2 - Actionable guidance on failures (Priority: P2)

Goal: When any prerequisite fails, output clear, step-by-step remediation guidance with links to official docs.

Independent Test: Temporarily deconfigure a tool and verify the guidance directs remediation steps that resolve the issue.

### Tests for User Story 2 (write first)

- [ ] T018 [P] [US2] Unit tests for remediation messages (gh unauthenticated; copilot missing) in `tests/unit/test_remediation_messages.py`
- [ ] T019 [US2] Extend integration test to assert guidance content appears on failure in `tests/integration/test_readiness_workflow.py`

### Implementation for User Story 2

- [ ] T020 [US2] Implement remediation guidance strings for gh in `src/activities/gh_status.py` (auth steps, docs link)
- [ ] T021 [US2] Implement remediation guidance strings for copilot in `src/activities/copilot_help.py` (install steps, docs link)
- [ ] T022 [US2] Ensure workflow summary includes `remediation` fields where applicable in `src/workflows/readiness.py`
- [ ] T023 [US2] Improve CLI formatting to show guidance clearly (headings/bullets) in `src/cli/readiness.py`
- [ ] T024 [P] [US2] Document contract mapping from `POST /readiness-check` to workflow/CLI in `specs/001-cli-prereq-check/contracts/README.md`

Checkpoint: At this point, User Stories 1 AND 2 should both work; US2 guidance builds on US1 readiness checks

---

## Phase 5: Polish & Cross-Cutting Concerns

Purpose: Improvements that affect multiple user stories

- [ ] T025 [P] Update `specs/001-cli-prereq-check/quickstart.md` with exact uv commands and examples verified against current code
- [ ] T026 Code cleanup and ruff fixes across `src/` and `tests/`
- [ ] T027 [P] Update repository `README.md` with feature overview and run instructions
- [ ] T028 Validate OpenAPI contract alignment with implementation in `specs/001-cli-prereq-check/contracts/openapi.yaml` and note gaps

---

## Dependencies & Execution Order

### Phase Dependencies

- Setup (Phase 1): No dependencies — can start immediately
- Foundational (Phase 2): Depends on Setup completion — BLOCKS all user stories
- User Stories (Phase 3+): Depend on Foundational completion
  - Proceed sequentially by priority (P1 → P2) or in parallel where independent
- Polish (Final Phase): Depends on selected user stories being complete

### User Story Dependencies

- User Story 1 (P1): Starts after Foundational (Phase 2); no dependencies on other stories
- User Story 2 (P2): Starts after Foundational (Phase 2); builds on US1 checks to add guidance

### Within Each User Story

- Tests MUST be written and fail before implementation
- Activities before workflow; workflow before CLI wiring
- Logging and formatting after core behavior

### Parallel Opportunities

- Setup: T003–T004 can run in parallel
- Foundational: T006–T007 can run in parallel
- US1: T008–T009 (unit tests) and T011–T012 (activities) can run in parallel; T013 depends on activities; T014–T015 parallel after T013
- US2: T018 and T020–T021 can run in parallel; T019/T022–T023 depend on earlier tasks; T024 is independent
- Polish: T025 and T027 can run in parallel

---

## Parallel Example: User Story 1

- Launch tests in parallel:
  - Task: "Unit test for gh auth status parsing and exit codes in tests/unit/test_gh_status.py"
  - Task: "Unit test for copilot availability (copilot help) in tests/unit/test_copilot_help.py"
- Implement activities in parallel:
  - Task: "Implement gh_status activity function in src/activities/gh_status.py"
  - Task: "Implement copilot_help activity function in src/activities/copilot_help.py"

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL)
3. Complete Phase 3: User Story 1
4. STOP and VALIDATE: Run US1 tests and manual check
5. Demo/ship MVP

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently → Demo (MVP)
3. Add User Story 2 → Test independently → Demo

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Non-interactive design and no environment mutation required throughout
