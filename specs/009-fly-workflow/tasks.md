# Tasks: Fly Workflow Interface

**Input**: Design documents from `/specs/009-fly-workflow/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/fly_interface.pyi

**Note**: This spec defines the interface only. Full implementation deferred to Spec 26.

**Tests**: Required per SC-010 (100% test coverage for all dataclass validation and enum definitions)

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Source**: `src/maverick/workflows/fly.py`
- **Config integration**: `src/maverick/config.py`
- **Tests**: `tests/unit/workflows/test_fly.py`
- **Workflows init**: `src/maverick/workflows/__init__.py`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and module structure

- [X] T001 Create fly workflow module file at src/maverick/workflows/fly.py with module docstring and imports
- [X] T002 [P] Create test file at tests/unit/workflows/test_fly.py with imports and test markers

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core enum that ALL user stories depend on (WorkflowStage is used by State, Result, and Events)

**CRITICAL**: WorkflowStage enum MUST be complete before ANY user story can be implemented

- [X] T003 Implement WorkflowStage enum (str, Enum) with 8 stages in src/maverick/workflows/fly.py (FR-001, FR-002)
- [X] T004 Add unit tests for WorkflowStage enum values and string representation in tests/unit/workflows/test_fly.py

**Checkpoint**: WorkflowStage enum ready - user story implementation can now begin

---

## Phase 3: User Story 1 - Execute Complete Fly Workflow (Priority: P1)

**Goal**: Define FlyInputs validated inputs and FlyWorkflow class with stub execute() method

**Independent Test**: Verify FlyWorkflow instantiation, execute() raises NotImplementedError with Spec 26 reference

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T005 [P] [US1] Test FlyInputs validates branch_name not empty in tests/unit/workflows/test_fly.py
- [X] T006 [P] [US1] Test FlyInputs default values (skip_review=False, skip_pr=False, draft_pr=False, base_branch="main") in tests/unit/workflows/test_fly.py
- [X] T007 [P] [US1] Test FlyInputs accepts all optional fields with custom values in tests/unit/workflows/test_fly.py
- [X] T008 [P] [US1] Test FlyWorkflow.execute() raises NotImplementedError with "Spec 26" message in tests/unit/workflows/test_fly.py
- [X] T009 [P] [US1] Test FlyWorkflow accepts optional FlyConfig in constructor in tests/unit/workflows/test_fly.py

### Implementation for User Story 1

- [X] T010 [US1] Implement FlyInputs Pydantic model with branch_name validation (min_length=1) and optional fields in src/maverick/workflows/fly.py (FR-003, FR-004, FR-005)
- [X] T011 [US1] Implement FlyWorkflow class with __init__(config: FlyConfig | None) and async execute(inputs: FlyInputs) -> FlyResult stub in src/maverick/workflows/fly.py (FR-017, FR-018, FR-019)
- [X] T012 [US1] Add detailed docstring to FlyWorkflow.execute() describing all 8 stage behaviors (FR-020)

**Checkpoint**: FlyInputs and FlyWorkflow class with stub are functional and testable

---

## Phase 4: User Story 2 - Track Workflow State (Priority: P1)

**Goal**: Define WorkflowState mutable Pydantic model for tracking execution progress

**Independent Test**: Verify WorkflowState has all 10 required fields with correct types and defaults

### Tests for User Story 2

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T013 [P] [US2] Test WorkflowState has all required fields (stage, branch, task_file, implementation_result, validation_result, review_results, pr_url, errors, started_at, completed_at) in tests/unit/workflows/test_fly.py
- [X] T014 [P] [US2] Test WorkflowState.stage can hold any WorkflowStage enum value in tests/unit/workflows/test_fly.py
- [X] T015 [P] [US2] Test WorkflowState.errors list accumulates strings without losing previous entries in tests/unit/workflows/test_fly.py
- [X] T016 [P] [US2] Test WorkflowState default values (stage=INIT, review_results=[], errors=[], etc.) in tests/unit/workflows/test_fly.py

### Implementation for User Story 2

- [X] T017 [US2] Implement WorkflowState Pydantic model with mutable state fields in src/maverick/workflows/fly.py (FR-006, FR-007, FR-008)
- [X] T018 [US2] Add imports for AgentResult and ValidationWorkflowResult types from existing modules in src/maverick/workflows/fly.py

**Checkpoint**: WorkflowState is fully functional with correct types and mutability

---

## Phase 5: User Story 5 - Retrieve Workflow Result (Priority: P1)

**Goal**: Define FlyResult immutable Pydantic model for workflow completion outcomes

**Independent Test**: Verify FlyResult has success, state, summary, token_usage, total_cost_usd fields

### Tests for User Story 5

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T019 [P] [US5] Test FlyResult has all required fields (success, state, summary, token_usage, total_cost_usd) in tests/unit/workflows/test_fly.py
- [X] T020 [P] [US5] Test FlyResult.total_cost_usd validates non-negative (ge=0.0) in tests/unit/workflows/test_fly.py
- [X] T021 [P] [US5] Test FlyResult is frozen (immutable) in tests/unit/workflows/test_fly.py
- [X] T022 [P] [US5] Test FlyResult.summary is human-readable string in tests/unit/workflows/test_fly.py

### Implementation for User Story 5

- [X] T023 [US5] Implement FlyResult Pydantic model with frozen=True in src/maverick/workflows/fly.py (FR-009, FR-010, FR-011)
- [X] T024 [US5] Import AgentUsage type from maverick.agents.result in src/maverick/workflows/fly.py

**Checkpoint**: FlyResult is fully functional with correct types and immutability

---

## Phase 6: User Story 3 - Receive Progress Events (Priority: P2)

**Goal**: Define 5 progress event dataclasses for TUI consumption

**Independent Test**: Verify all 5 event types exist with correct fields and types

### Tests for User Story 3

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T025 [P] [US3] Test FlyWorkflowStarted event contains inputs (FlyInputs) and timestamp in tests/unit/workflows/test_fly.py
- [X] T026 [P] [US3] Test FlyStageStarted event contains stage (WorkflowStage) and timestamp in tests/unit/workflows/test_fly.py
- [X] T027 [P] [US3] Test FlyStageCompleted event contains stage, result (Any), and timestamp in tests/unit/workflows/test_fly.py
- [X] T028 [P] [US3] Test FlyWorkflowCompleted event contains result (FlyResult) and timestamp in tests/unit/workflows/test_fly.py
- [X] T029 [P] [US3] Test FlyWorkflowFailed event contains error (str), state (WorkflowState), and timestamp in tests/unit/workflows/test_fly.py
- [X] T030 [P] [US3] Test all progress events are frozen dataclasses with slots=True in tests/unit/workflows/test_fly.py

### Implementation for User Story 3

- [X] T031 [P] [US3] Implement FlyWorkflowStarted dataclass (frozen=True, slots=True) with inputs and timestamp in src/maverick/workflows/fly.py (FR-012)
- [X] T032 [P] [US3] Implement FlyStageStarted dataclass (frozen=True, slots=True) with stage and timestamp in src/maverick/workflows/fly.py (FR-013)
- [X] T033 [P] [US3] Implement FlyStageCompleted dataclass (frozen=True, slots=True) with stage, result, timestamp in src/maverick/workflows/fly.py (FR-014)
- [X] T034 [P] [US3] Implement FlyWorkflowCompleted dataclass (frozen=True, slots=True) with result and timestamp in src/maverick/workflows/fly.py (FR-015)
- [X] T035 [P] [US3] Implement FlyWorkflowFailed dataclass (frozen=True, slots=True) with error, state, timestamp in src/maverick/workflows/fly.py (FR-016)
- [X] T036 [US3] Define FlyProgressEvent union type for type-safe event handling in src/maverick/workflows/fly.py

**Checkpoint**: All 5 progress events are defined and independently testable

---

## Phase 7: User Story 4 - Configure Workflow Behavior (Priority: P2)

**Goal**: Define FlyConfig Pydantic model and integrate into MaverickConfig

**Independent Test**: Verify FlyConfig defaults match specification and integrates with MaverickConfig

### Tests for User Story 4

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T037 [P] [US4] Test FlyConfig default values (parallel_reviews=True, max_validation_attempts=3, coderabbit_enabled=False, auto_merge=False, notification_on_complete=True) in tests/unit/workflows/test_fly.py
- [X] T038 [P] [US4] Test FlyConfig.max_validation_attempts validates range 1-10 in tests/unit/workflows/test_fly.py
- [X] T039 [P] [US4] Test FlyConfig is frozen (immutable) in tests/unit/workflows/test_fly.py

### Implementation for User Story 4

- [X] T040 [US4] Implement FlyConfig Pydantic model with frozen=True and field constraints in src/maverick/workflows/fly.py (FR-021, FR-022)
- [X] T041 [US4] Add FlyConfig import and fly: FlyConfig field to MaverickConfig in src/maverick/config.py (FR-023)
- [X] T042 [US4] Add FlyConfig to config.py __all__ exports in src/maverick/config.py
- [X] T043 [US4] Test MaverickConfig.fly field exists and uses FlyConfig defaults in tests/unit/workflows/test_fly.py

**Checkpoint**: FlyConfig is complete and integrated into MaverickConfig

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Module exports, final integration, and validation

- [X] T044 [P] Add __all__ exports list with all 12 public types in src/maverick/workflows/fly.py (SC-008)
- [X] T045 [P] Update src/maverick/workflows/__init__.py to export FlyWorkflow and related types
- [X] T046 Test all interface types are importable from maverick.workflows.fly in tests/unit/workflows/test_fly.py (SC-008)
- [X] T047 Test interface types integrate with existing AgentResult and ValidationWorkflowResult in tests/unit/workflows/test_fly.py (SC-009)
- [X] T048 Run ruff format and ruff check --fix on src/maverick/workflows/fly.py
- [X] T049 Run mypy type check on src/maverick/workflows/fly.py
- [X] T050 Run pytest to verify 100% test coverage for fly module (SC-010)
- [X] T051 Validate quickstart.md examples work with implemented types

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup - BLOCKS all user stories (WorkflowStage used everywhere)
- **User Stories (Phase 3-7)**: All depend on Foundational phase completion
  - US1 (FlyInputs, FlyWorkflow) - can proceed immediately after Foundational
  - US2 (WorkflowState) - depends on US1 for FlyInputs type reference
  - US5 (FlyResult) - depends on US2 for WorkflowState type
  - US3 (Progress Events) - depends on US1, US2, US5 for type references
  - US4 (FlyConfig) - can proceed in parallel with US2/US3/US5
- **Polish (Phase 8)**: Depends on all user stories being complete

### User Story Dependencies

```
                    Foundational (WorkflowStage)
                              |
            +-----------------+-----------------+
            |                                   |
        US1 (FlyInputs/FlyWorkflow)          US4 (FlyConfig)
            |                                   |
        US2 (WorkflowState)                     |
            |                                   |
        US5 (FlyResult)                         |
            |                                   |
        US3 (Progress Events)                   |
            |                                   |
            +-------------- Polish -------------+
```

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- Types before classes
- Simple types before complex types (enum → inputs → state → result → events)

### Parallel Opportunities

- T001, T002: Setup tasks can run in parallel
- T005-T009: All US1 tests can run in parallel
- T013-T016: All US2 tests can run in parallel
- T019-T022: All US5 tests can run in parallel
- T025-T030: All US3 tests can run in parallel
- T031-T035: All US3 event implementations can run in parallel
- T037-T039: All US4 tests can run in parallel
- T044-T045: Polish export tasks can run in parallel

---

## Parallel Example: User Story 3

```bash
# Launch all tests for User Story 3 together:
Task: "T025: Test FlyWorkflowStarted event"
Task: "T026: Test FlyStageStarted event"
Task: "T027: Test FlyStageCompleted event"
Task: "T028: Test FlyWorkflowCompleted event"
Task: "T029: Test FlyWorkflowFailed event"
Task: "T030: Test all events are frozen dataclasses"

# Launch all event implementations together:
Task: "T031: Implement FlyWorkflowStarted dataclass"
Task: "T032: Implement FlyStageStarted dataclass"
Task: "T033: Implement FlyStageCompleted dataclass"
Task: "T034: Implement FlyWorkflowCompleted dataclass"
Task: "T035: Implement FlyWorkflowFailed dataclass"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (WorkflowStage enum)
3. Complete Phase 3: User Story 1 (FlyInputs + FlyWorkflow stub)
4. **STOP and VALIDATE**: Test US1 independently
5. FlyWorkflow can be instantiated, execute() raises NotImplementedError

### Incremental Delivery

1. Setup + Foundational -> WorkflowStage ready
2. Add US1 (FlyInputs/FlyWorkflow) -> Core workflow interface
3. Add US2 (WorkflowState) -> State tracking ready
4. Add US5 (FlyResult) -> Result type ready
5. Add US3 (Progress Events) -> TUI events ready
6. Add US4 (FlyConfig) -> Configuration ready
7. Polish -> Exports, validation, coverage

### Total Task Count

- **Phase 1 (Setup)**: 2 tasks
- **Phase 2 (Foundational)**: 2 tasks
- **Phase 3 (US1)**: 8 tasks (5 tests + 3 impl)
- **Phase 4 (US2)**: 6 tasks (4 tests + 2 impl)
- **Phase 5 (US5)**: 6 tasks (4 tests + 2 impl)
- **Phase 6 (US3)**: 12 tasks (6 tests + 6 impl)
- **Phase 7 (US4)**: 7 tasks (3 tests + 4 impl)
- **Phase 8 (Polish)**: 8 tasks
- **Total**: 51 tasks

---

## Notes

- [P] tasks = different files or independent implementations, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story is independently completable and testable
- Verify tests fail before implementing
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- This is interface-only: FlyWorkflow.execute() raises NotImplementedError
