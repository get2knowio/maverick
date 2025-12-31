# Tasks: Refuel Workflow Interface

**Input**: Design documents from `/specs/010-refuel-workflow/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, quickstart.md

**Tests**: Tests are included as this is an interface-only spec where tests validate the contract before implementation.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `src/maverick/`, `tests/unit/` at repository root
- Follows existing FlyWorkflow pattern in `src/maverick/workflows/fly.py`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and file structure setup

> **Note**: For interface-only specs, module creation precedes tests since
> the interface contract must exist before tests can import it.

- [X] T001 Create refuel.py module file with imports in src/maverick/workflows/refuel.py
- [X] T002 Add refuel workflow exports to src/maverick/workflows/__init__.py

---

## Phase 2: Foundational (Data Models & Enums)

**Purpose**: Core data structures that ALL user stories depend on - MUST complete before any user story work

**CRITICAL**: These are the building blocks for all user stories. No user story can be implemented without these.

### Core Data Structures

- [X] T003 [P] Create GitHubIssue dataclass (frozen=True, slots=True) with fields: number, title, body, labels, assignee, url in src/maverick/workflows/refuel.py
- [X] T004 [P] Create IssueStatus enum (str, Enum) with values: PENDING, IN_PROGRESS, FIXED, FAILED, SKIPPED in src/maverick/workflows/refuel.py
- [X] T005 Create RefuelInputs dataclass (frozen=True, slots=True) with fields: label, limit, parallel, dry_run, auto_assign with defaults in src/maverick/workflows/refuel.py
- [X] T006 Create IssueProcessingResult dataclass (frozen=True, slots=True) with fields: issue, status, branch, pr_url, error, duration_ms, agent_usage in src/maverick/workflows/refuel.py
- [X] T007 Create RefuelResult dataclass (frozen=True, slots=True) with fields: success, issues_found, issues_processed, issues_fixed, issues_failed, issues_skipped, results, total_duration_ms, total_cost_usd in src/maverick/workflows/refuel.py

### Configuration

- [X] T008 Create RefuelConfig Pydantic BaseModel (frozen=True) with fields: default_label, branch_prefix, link_pr_to_issue, close_on_merge, skip_if_assigned, max_parallel with validation in src/maverick/workflows/refuel.py
- [X] T009 Add RefuelConfig field to MaverickConfig in src/maverick/config.py

**Checkpoint**: Foundation ready - all data structures defined and config integrated

---

## Phase 3: User Story 1 - Configure and Execute Refuel Workflow (Priority: P1) MVP

**Goal**: Define the RefuelWorkflow class interface that accepts RefuelInputs and returns RefuelResult

**Independent Test**: Create RefuelInputs, pass to RefuelWorkflow.execute(), verify NotImplementedError raised with correct message

### Tests for User Story 1

- [X] T010 [P] [US1] Test RefuelInputs default values (label="tech-debt", limit=5, parallel=False, dry_run=False, auto_assign=True) in tests/unit/workflows/test_refuel.py
- [X] T011 [P] [US1] Test RefuelInputs immutability (frozen=True) - modification raises FrozenInstanceError in tests/unit/workflows/test_refuel.py
- [X] T012 [P] [US1] Test RefuelResult has all required fields and success flag in tests/unit/workflows/test_refuel.py
- [X] T013 [P] [US1] Test RefuelWorkflow.execute() raises NotImplementedError with "Spec 26" message in tests/unit/workflows/test_refuel.py
- [X] T014 [P] [US1] Test RefuelWorkflow accepts optional RefuelConfig in constructor in tests/unit/workflows/test_refuel.py

### Implementation for User Story 1

- [X] T015 [US1] Create RefuelWorkflow class with __init__(config: RefuelConfig | None) in src/maverick/workflows/refuel.py
- [X] T016 [US1] Implement execute(inputs: RefuelInputs) method signature returning AsyncGenerator[RefuelProgressEvent, None] that raises NotImplementedError in src/maverick/workflows/refuel.py
- [X] T017 [US1] Add docstring to execute() describing the intended per-issue processing flow (6 steps from FR-012) in src/maverick/workflows/refuel.py

**Checkpoint**: User Story 1 complete - RefuelWorkflow can be instantiated and execute() raises NotImplementedError

---

## Phase 4: User Story 2 - Monitor Processing Progress (Priority: P2)

**Goal**: Define progress event dataclasses for real-time workflow status updates

**Independent Test**: Create instances of all 4 progress events, verify fields and immutability

### Tests for User Story 2

- [X] T018 [P] [US2] Test RefuelStarted event has inputs (RefuelInputs) and issues_found (int) fields in tests/unit/workflows/test_refuel.py
- [X] T019 [P] [US2] Test IssueProcessingStarted event has issue (GitHubIssue), index (int), total (int) fields in tests/unit/workflows/test_refuel.py
- [X] T020 [P] [US2] Test IssueProcessingCompleted event has result (IssueProcessingResult) field in tests/unit/workflows/test_refuel.py
- [X] T021 [P] [US2] Test RefuelCompleted event has result (RefuelResult) field in tests/unit/workflows/test_refuel.py
- [X] T022 [P] [US2] Test all progress events are frozen dataclasses with slots=True in tests/unit/workflows/test_refuel.py

### Implementation for User Story 2

- [X] T023 [P] [US2] Create RefuelStarted dataclass (frozen=True, slots=True) with inputs and issues_found fields in src/maverick/workflows/refuel.py
- [X] T024 [P] [US2] Create IssueProcessingStarted dataclass (frozen=True, slots=True) with issue, index, total fields in src/maverick/workflows/refuel.py
- [X] T025 [P] [US2] Create IssueProcessingCompleted dataclass (frozen=True, slots=True) with result field in src/maverick/workflows/refuel.py
- [X] T026 [P] [US2] Create RefuelCompleted dataclass (frozen=True, slots=True) with result field in src/maverick/workflows/refuel.py
- [X] T027 [US2] Create RefuelProgressEvent type alias as union of all 4 event types in src/maverick/workflows/refuel.py

**Checkpoint**: User Story 2 complete - all progress events defined and typed

---

## Phase 5: User Story 3 - Preview Issues Without Processing (Priority: P2)

**Goal**: Verify dry_run mode is supported in RefuelInputs

**Independent Test**: Create RefuelInputs with dry_run=True, verify field accessible

### Tests for User Story 3

- [X] T028 [P] [US3] Test RefuelInputs accepts dry_run=True and stores the value in tests/unit/workflows/test_refuel.py
- [X] T029 [P] [US3] Test IssueStatus.SKIPPED enum value exists for dry_run results in tests/unit/workflows/test_refuel.py

### Implementation for User Story 3

(Covered by T005 - RefuelInputs already includes dry_run field)

**Checkpoint**: User Story 3 complete - dry_run mode supported in inputs

---

## Phase 6: User Story 4 - Process Issues in Parallel (Priority: P3)

**Goal**: Verify parallel mode configuration is supported

**Independent Test**: Create RefuelInputs with parallel=True, verify field; Create RefuelConfig with max_parallel, verify validation

### Tests for User Story 4

- [X] T030 [P] [US4] Test RefuelInputs accepts parallel=True and stores the value in tests/unit/workflows/test_refuel.py
- [X] T031 [P] [US4] Test RefuelConfig.max_parallel validates range 1-10 in tests/unit/workflows/test_refuel.py
- [X] T032 [P] [US4] Test RefuelConfig.branch_prefix validation (must end with "/" or "-") in tests/unit/workflows/test_refuel.py

### Implementation for User Story 4

(Covered by T005 for RefuelInputs.parallel and T008 for RefuelConfig.max_parallel)

**Checkpoint**: User Story 4 complete - parallel mode configuration supported

---

## Phase 7: User Story 5 - Track Processing Results and Costs (Priority: P3)

**Goal**: Verify cost and duration tracking in result structures

**Independent Test**: Create IssueProcessingResult with AgentUsage, verify fields; Create RefuelResult with total_duration_ms and total_cost_usd

### Tests for User Story 5

- [X] T033 [P] [US5] Test IssueProcessingResult.agent_usage field holds AgentUsage instance in tests/unit/workflows/test_refuel.py
- [X] T034 [P] [US5] Test IssueProcessingResult.duration_ms field is int in tests/unit/workflows/test_refuel.py
- [X] T035 [P] [US5] Test RefuelResult.total_duration_ms and total_cost_usd fields are accessible in tests/unit/workflows/test_refuel.py

### Implementation for User Story 5

(Covered by T006 for IssueProcessingResult and T007 for RefuelResult)

**Checkpoint**: User Story 5 complete - cost and duration tracking supported

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Integration, validation, and code quality

### Edge Case Tests (interface contract validation)

> **Note**: These tests validate that dataclasses can represent all documented edge case states.

- [X] T036 [P] Test RefuelResult with issues_found=0 represents empty label match in tests/unit/workflows/test_refuel.py
- [X] T037 [P] Test IssueProcessingResult with status=SKIPPED and all optional fields None in tests/unit/workflows/test_refuel.py
- [X] T038 [P] Test IssueProcessingResult with status=FAILED requires error field non-None in tests/unit/workflows/test_refuel.py
- [X] T039 [P] Test RefuelResult.success=True when issues_failed=0 in tests/unit/workflows/test_refuel.py

### General Polish Tasks

- [X] T040 [P] Test GitHubIssue dataclass immutability (frozen=True) in tests/unit/workflows/test_refuel.py
- [X] T041 [P] Test IssueStatus enum string values and conversions in tests/unit/workflows/test_refuel.py
- [X] T042 [P] Test all interface types importable from maverick.workflows.refuel in tests/unit/workflows/test_refuel.py
- [X] T043 Test MaverickConfig.refuel field exists and returns RefuelConfig in tests/unit/workflows/test_refuel.py
- [X] T044 Add __all__ export list to src/maverick/workflows/refuel.py
- [X] T045 Run ruff format and ruff check --fix on src/maverick/workflows/refuel.py
- [X] T046 Run mypy strict mode on src/maverick/workflows/refuel.py
- [X] T047 Run pytest on tests/unit/workflows/test_refuel.py - verify all tests pass

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3-7)**: All depend on Foundational phase completion
  - US1 (P1): Core workflow interface - implement first
  - US2 (P2): Progress events - can parallel with US3-5 after US1
  - US3 (P2): Dry-run mode - mostly tests only (already in T005)
  - US4 (P3): Parallel mode - mostly tests only (already in T005, T008)
  - US5 (P3): Cost tracking - mostly tests only (already in T006, T007)
- **Polish (Phase 8)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 2 (P2)**: Can start after Foundational (Phase 2) - Independent of US1
- **User Story 3 (P2)**: Can start after Foundational (Phase 2) - Tests only, no new implementation
- **User Story 4 (P3)**: Can start after Foundational (Phase 2) - Tests only, no new implementation
- **User Story 5 (P3)**: Can start after Foundational (Phase 2) - Tests only, no new implementation

### Within Each User Story

- Tests written FIRST (marked [P] where possible)
- Tests should FAIL before implementation
- Implementation follows tests
- Story complete before moving to next priority

### Parallel Opportunities

- T003, T004: Core dataclass/enum creation in parallel
- T010-T014: All US1 tests in parallel
- T018-T022: All US2 tests in parallel
- T023-T026: All US2 event dataclasses in parallel
- T028-T029, T030-T032, T033-T035: All US3-5 tests in parallel
- T036-T039: Edge case tests in parallel
- T040-T042: General polish tests in parallel

---

## Parallel Example: User Story 2 (Progress Events)

```bash
# Launch all tests for User Story 2 together:
Task: "Test RefuelStarted event has inputs and issues_found fields in tests/unit/workflows/test_refuel.py"
Task: "Test IssueProcessingStarted event has issue, index, total fields in tests/unit/workflows/test_refuel.py"
Task: "Test IssueProcessingCompleted event has result field in tests/unit/workflows/test_refuel.py"
Task: "Test RefuelCompleted event has result field in tests/unit/workflows/test_refuel.py"
Task: "Test all progress events are frozen dataclasses with slots=True in tests/unit/workflows/test_refuel.py"

# Launch all event dataclasses together:
Task: "Create RefuelStarted dataclass in src/maverick/workflows/refuel.py"
Task: "Create IssueProcessingStarted dataclass in src/maverick/workflows/refuel.py"
Task: "Create IssueProcessingCompleted dataclass in src/maverick/workflows/refuel.py"
Task: "Create RefuelCompleted dataclass in src/maverick/workflows/refuel.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T002)
2. Complete Phase 2: Foundational (T003-T009)
3. Complete Phase 3: User Story 1 (T010-T017)
4. **STOP and VALIDATE**: Run all tests, verify NotImplementedError behavior
5. Commit and validate mypy/ruff

### Incremental Delivery

1. Complete Setup + Foundational -> All data structures defined
2. Add User Story 1 -> Workflow interface testable (MVP!)
3. Add User Story 2 -> Progress events defined
4. Add User Stories 3-5 -> Additional test coverage for config options
5. Complete Polish -> Full test coverage, linting, type checking

### Single Developer Strategy

Recommended execution order:
1. T001-T002 (Setup)
2. T003-T009 (Foundational - all in order, but T003-T004 in parallel)
3. T010-T017 (US1 - tests first T010-T014 in parallel, then implementation)
4. T018-T027 (US2 - tests T018-T022 in parallel, then events T023-T026 in parallel)
5. T028-T035 (US3-5 - all tests in parallel)
6. T036-T047 (Polish - edge case tests T036-T039 in parallel, then general polish)

---

## Notes

- [P] tasks = different files or independent code sections, no dependencies
- [Story] label maps task to specific user story for traceability
- All dataclasses use frozen=True, slots=True for immutability and memory efficiency
- RefuelConfig uses Pydantic BaseModel with frozen=True for YAML integration
- This is an interface-only spec - execute() raises NotImplementedError
- Full implementation deferred to Spec 26
- Follow existing FlyWorkflow pattern in fly.py for consistency
