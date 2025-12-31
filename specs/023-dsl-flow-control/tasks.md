# Tasks: Workflow DSL Flow Control

**Input**: Design documents from `/specs/023-dsl-flow-control/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅

**Tests**: Tests ARE required - spec.md references pytest-asyncio for async testing.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create new files/directories and add foundational types needed by all user stories

- [X] T001 Create dsl/steps/ directory structure per plan.md
- [X] T002 Create dsl/checkpoint/ directory structure per plan.md
- [X] T003 [P] Add new StepType enum values (BRANCH, PARALLEL) in src/maverick/dsl/types.py
- [X] T004 [P] Create Predicate and RollbackAction type aliases in src/maverick/dsl/types.py
- [X] T005 [P] Create SkipMarker dataclass in src/maverick/dsl/results.py
- [X] T006 [P] Create WorkflowError exception in src/maverick/dsl/errors.py
- [X] T007 [P] Create RollbackError dataclass in src/maverick/dsl/results.py
- [X] T008 [P] Create RollbackRegistration dataclass in src/maverick/dsl/results.py

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T009 Extend WorkflowContext with `_pending_rollbacks` list and `register_rollback()` method in src/maverick/dsl/context.py
- [X] T010 Update WorkflowContext.get_step_output() to return None for missing steps (FR-009a) in src/maverick/dsl/context.py
- [X] T011 Add `is_step_skipped()` helper method to WorkflowContext in src/maverick/dsl/context.py
- [X] T012 [P] Create tests/unit/dsl/steps/ directory structure
- [X] T013 [P] Create tests/unit/dsl/checkpoint/ directory structure

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 1 - Control Flow with Conditions and Branches (Priority: P1) 🎯 MVP

**Goal**: Enable workflow authors to conditionally execute steps and route between alternative steps using `.when()` and `.branch()` without leaving the workflow DSL.

**Independent Test**: Create a workflow that conditionally runs one step, branches between two steps, and verify only expected steps executed and outputs match the chosen path.

### Tests for User Story 1

- [X] T014 [P] [US1] Create test file tests/unit/dsl/steps/test_conditional.py with test fixtures
- [X] T015 [P] [US1] Create test file tests/unit/dsl/steps/test_branch.py with test fixtures

### Implementation for User Story 1

- [X] T016 [P] [US1] Create ConditionalStep wrapper class in src/maverick/dsl/steps/conditional.py
- [X] T017 [P] [US1] Create BranchOption dataclass in src/maverick/dsl/steps/branch.py
- [X] T018 [P] [US1] Create BranchResult dataclass in src/maverick/dsl/results.py
- [X] T019 [US1] Create BranchStep class in src/maverick/dsl/steps/branch.py (depends on T017, T018)
- [X] T020 [US1] Add `.when()` method to StepBuilder in src/maverick/dsl/builder.py
- [X] T021 [US1] Add `branch()` helper function in src/maverick/dsl/builder.py
- [X] T022 [US1] Export new types from src/maverick/dsl/steps/__init__.py
- [X] T023 [US1] Update src/maverick/dsl/__init__.py exports for User Story 1 types
- [X] T024 [US1] Implement test cases: predicate returns True, predicate returns False in tests/unit/dsl/steps/test_conditional.py
- [X] T025 [US1] Implement test cases: predicate raises exception, predicate returns non-bool in tests/unit/dsl/steps/test_conditional.py
- [X] T026 [US1] Implement test cases: first branch matches, later branch matches in tests/unit/dsl/steps/test_branch.py
- [X] T027 [US1] Implement test cases: no branch matches fails, branch with missing step result in tests/unit/dsl/steps/test_branch.py

**Checkpoint**: User Story 1 complete - conditional and branching execution works independently

---

## Phase 4: User Story 2 - Reliability Controls (Priority: P2)

**Goal**: Enable workflow authors to retry steps, handle failures with fallbacks, skip optional failures, and register rollbacks for safe, predictable workflows.

**Independent Test**: Run a workflow with a flaky step retried to success, an optional step skipped on error, and a rollback registered and invoked after a later failure.

### Tests for User Story 2

- [X] T028 [P] [US2] Create test file tests/unit/dsl/steps/test_retry.py with test fixtures
- [X] T029 [P] [US2] Create test file tests/unit/dsl/steps/test_error_handler.py with test fixtures
- [X] T030 [P] [US2] Create test file tests/unit/dsl/steps/test_rollback.py with test fixtures

### Implementation for User Story 2

- [X] T031 [P] [US2] Create RetryStep wrapper class in src/maverick/dsl/steps/retry.py
- [X] T032 [P] [US2] Create ErrorHandlerStep wrapper class in src/maverick/dsl/steps/error_handler.py
- [X] T033 [P] [US2] Create RollbackStep wrapper class in src/maverick/dsl/steps/rollback.py
- [X] T034 [US2] Add `.retry()` method to StepBuilder in src/maverick/dsl/builder.py
- [X] T035 [US2] Add `.on_error()` method to StepBuilder in src/maverick/dsl/builder.py
- [X] T036 [US2] Add `.skip_on_error()` method to StepBuilder in src/maverick/dsl/builder.py
- [X] T037 [US2] Add `.with_rollback()` method to StepBuilder in src/maverick/dsl/builder.py
- [X] T038 [US2] Implement `_execute_rollbacks()` method in WorkflowEngine in src/maverick/dsl/engine.py
- [X] T039 [US2] Update WorkflowEngine execution loop to call rollbacks on failure in src/maverick/dsl/engine.py
- [X] T040 [US2] Extend WorkflowResult with `rollback_errors` field in src/maverick/dsl/results.py
- [X] T041 [US2] Export new types from src/maverick/dsl/steps/__init__.py
- [X] T042 [US2] Update src/maverick/dsl/__init__.py exports for User Story 2 types
- [X] T043 [US2] Implement test cases: retry succeeds after N attempts, retry exhausts all attempts, step succeeds on first attempt (no retry triggered) in tests/unit/dsl/steps/test_retry.py
- [X] T044 [US2] Implement test cases: exponential backoff timing, jitter applied in tests/unit/dsl/steps/test_retry.py
- [X] T045 [US2] Implement test cases: on_error fallback succeeds, fallback fails in tests/unit/dsl/steps/test_error_handler.py
- [X] T046 [US2] Implement test cases: skip_on_error converts failure to skip in tests/unit/dsl/steps/test_error_handler.py
- [X] T047 [US2] Implement test cases: rollback triggered on workflow failure in tests/unit/dsl/steps/test_rollback.py
- [X] T048 [US2] Implement test cases: rollbacks run in reverse order, continue on rollback error in tests/unit/dsl/steps/test_rollback.py

**Checkpoint**: User Stories 1 AND 2 complete - conditions, branches, retry, error handling, and rollback all work

---

## Phase 5: User Story 3 - Advanced Control Flow (Priority: P3)

**Goal**: Enable workflow authors to iterate over collections, express parallel-ready interfaces, and checkpoint/resume workflows for scalability and long-running process recovery.

**Independent Test**: Yield multiple steps in a Python loop, execute a parallel interface step returning multiple outputs, and resume a workflow from a saved checkpoint.

### Tests for User Story 3

- [X] T049 [P] [US3] Create test file tests/unit/dsl/steps/test_parallel.py with test fixtures
- [X] T050 [P] [US3] Create test file tests/unit/dsl/steps/test_checkpoint.py with test fixtures
- [X] T051 [P] [US3] Create test file tests/unit/dsl/checkpoint/test_store.py with test fixtures
- [X] T052 [P] [US3] Create test file tests/unit/dsl/checkpoint/test_data.py with test fixtures
- [X] T053 [P] [US3] Create test file tests/unit/dsl/test_engine_flow_control.py for integration tests
- [X] T053a [US3] Implement test case: workflow raises WorkflowError, verify workflow fails with error message in result in tests/unit/dsl/test_engine_flow_control.py

### Implementation for User Story 3

- [X] T054 [P] [US3] Create ParallelResult dataclass in src/maverick/dsl/results.py
- [X] T055 [P] [US3] Create ParallelStep class in src/maverick/dsl/steps/parallel.py
- [X] T056 [P] [US3] Create CheckpointData dataclass in src/maverick/dsl/checkpoint/data.py
- [X] T057 [P] [US3] Create CheckpointStore protocol in src/maverick/dsl/checkpoint/store.py
- [X] T058 [P] [US3] Create FileCheckpointStore implementation in src/maverick/dsl/checkpoint/store.py
- [X] T059 [P] [US3] Create MemoryCheckpointStore (testing) in src/maverick/dsl/checkpoint/store.py
- [X] T060 [US3] Create CheckpointStep wrapper class in src/maverick/dsl/steps/checkpoint.py (depends on T056, T057)
- [X] T061 [US3] Create CheckpointNotFoundError and InputMismatchError exceptions in src/maverick/dsl/errors.py
- [X] T062 [US3] Implement compute_inputs_hash() function in src/maverick/dsl/checkpoint/data.py
- [X] T063 [US3] Add `parallel()` helper function in src/maverick/dsl/builder.py
- [X] T064 [US3] Add `.checkpoint()` method to StepBuilder in src/maverick/dsl/builder.py
- [X] T065 [US3] Extend WorkflowEngine with checkpoint_store parameter in src/maverick/dsl/engine.py
- [X] T066 [US3] Implement `resume()` method on WorkflowEngine in src/maverick/dsl/engine.py
- [X] T067 [US3] Update engine execution loop to save checkpoints after checkpoint-marked steps in src/maverick/dsl/engine.py
- [X] T068 [US3] Export new types from src/maverick/dsl/checkpoint/__init__.py
- [X] T069 [US3] Export new types from src/maverick/dsl/steps/__init__.py
- [X] T070 [US3] Update src/maverick/dsl/__init__.py exports for User Story 3 types
- [X] T071 [US3] Implement test cases: parallel executes sequentially, returns ParallelResult in tests/unit/dsl/steps/test_parallel.py
- [X] T072 [US3] Implement test cases: parallel detects duplicate names, fails before execution in tests/unit/dsl/steps/test_parallel.py
- [X] T073 [US3] Implement test cases: checkpoint saves state after step in tests/unit/dsl/steps/test_checkpoint.py
- [X] T074 [US3] Implement test cases: CheckpointData serialization/deserialization in tests/unit/dsl/checkpoint/test_data.py
- [X] T075 [US3] Implement test cases: compute_inputs_hash determinism in tests/unit/dsl/checkpoint/test_data.py
- [X] T076 [US3] Implement test cases: FileCheckpointStore save/load/clear in tests/unit/dsl/checkpoint/test_store.py
- [X] T077 [US3] Implement test cases: MemoryCheckpointStore operations in tests/unit/dsl/checkpoint/test_store.py
- [X] T078 [US3] Implement test cases: workflow resumes from checkpoint in tests/unit/dsl/test_engine_flow_control.py
- [X] T079 [US3] Implement test cases: resume fails on input mismatch in tests/unit/dsl/test_engine_flow_control.py
- [X] T080 [US3] Implement test cases: full flow control integration (conditions + retry + rollback + checkpoint) in tests/unit/dsl/test_engine_flow_control.py
- [X] T080a [US3] Implement test case: workflow yields duplicate step names in loop, verify engine fails with clear error before executing duplicate in tests/unit/dsl/test_engine_flow_control.py

**Checkpoint**: All user stories complete - full flow control capabilities available

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [X] T081 [P] Add RollbackStarted event in src/maverick/dsl/events.py
- [X] T082 [P] Add RollbackCompleted event in src/maverick/dsl/events.py
- [X] T083 [P] Add CheckpointSaved event in src/maverick/dsl/events.py
- [X] T084 Update WorkflowEngine to emit new events at appropriate points in src/maverick/dsl/engine.py
- [X] T085 Verify all test files pass with pytest in tests/unit/dsl/
- [X] T086 Run ruff linting and fix any issues
- [X] T087 Run mypy type checking and fix any issues
- [X] T088 Run quickstart.md validation scenarios manually

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3-5)**: All depend on Foundational phase completion
  - User stories can proceed in priority order (P1 → P2 → P3)
  - Or in parallel if multiple developers available
- **Polish (Phase 6)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 2 (P2)**: Can start after Foundational (Phase 2) - Independent of US1
- **User Story 3 (P3)**: Can start after Foundational (Phase 2) - Independent of US1/US2

### Within Each User Story

- Tests SHOULD be created before implementation (test files first, then step classes)
- Types/dataclasses before step wrapper classes
- Step wrapper classes before StepBuilder methods
- StepBuilder methods before engine integration
- Complete test cases after implementation is done

### Parallel Opportunities

**Phase 1 (Setup):**
- T003, T004 can run in parallel (both modify types.py but different sections)
- T005, T006, T007, T008 can run in parallel (different files)

**Phase 2 (Foundational):**
- T012, T013 can run in parallel (directory creation)

**User Story 1:**
- T014, T015 can run in parallel (test files)
- T016, T017, T018 can run in parallel (different files)

**User Story 2:**
- T028, T029, T030 can run in parallel (test files)
- T031, T032, T033 can run in parallel (different step files)

**User Story 3:**
- T049, T050, T051, T052, T053 can run in parallel (test files)
- T054, T055, T056, T057, T058, T059 can run in parallel (different files)

**Phase 6 (Polish):**
- T081, T082, T083 can run in parallel (all add events to same file but different classes)

---

## Parallel Example: User Story 1

```bash
# Launch all tests for User Story 1 together:
Task: "Create test file tests/unit/dsl/steps/test_conditional.py"
Task: "Create test file tests/unit/dsl/steps/test_branch.py"

# Launch all independent step types together:
Task: "Create ConditionalStep wrapper in src/maverick/dsl/steps/conditional.py"
Task: "Create BranchOption dataclass in src/maverick/dsl/steps/branch.py"
Task: "Create BranchResult dataclass in src/maverick/dsl/results.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1 (Conditions + Branches)
4. **STOP and VALIDATE**: Test User Story 1 independently
5. Deploy/demo if ready - workflows can now use `.when()` and `branch()`

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently → Conditions + Branches work (MVP!)
3. Add User Story 2 → Test independently → Retry + Error handling + Rollbacks work
4. Add User Story 3 → Test independently → Parallel + Checkpointing work
5. Each story adds value without breaking previous stories

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1 (conditions, branches)
   - Developer B: User Story 2 (retry, error handling, rollbacks)
   - Developer C: User Story 3 (parallel, checkpointing)
3. Stories complete and integrate independently

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Tests should be written first, then verified to fail, then implementation added
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- All new step types follow the wrapper pattern from research.md
