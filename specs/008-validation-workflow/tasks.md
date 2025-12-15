# Tasks: Validation Workflow

**Input**: Design documents from `/specs/008-validation-workflow/`
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/ ✓

**Tests**: Not explicitly requested in feature specification. Test tasks included based on plan.md TDD requirement (Principle V: Test-First).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and test infrastructure

- [X] T001 Create `src/maverick/models/__init__.py` if not exists and add validation exports
- [X] T002 Create `tests/unit/workflows/__init__.py` for workflow unit tests
- [X] T003 Create `tests/integration/workflows/__init__.py` for workflow integration tests

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core models and enums that ALL user stories depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T004 Implement `StageStatus` enum in `src/maverick/models/validation.py`
- [X] T005 Implement `ValidationStage` Pydantic model in `src/maverick/models/validation.py`
- [X] T006 Implement `StageResult` Pydantic model with computed properties in `src/maverick/models/validation.py`
- [X] T007 Implement `ValidationWorkflowResult` Pydantic model with computed properties in `src/maverick/models/validation.py`
- [X] T008 Implement `ValidationWorkflowConfig` Pydantic model in `src/maverick/models/validation.py`
- [X] T009 Implement `ProgressUpdate` dataclass in `src/maverick/models/validation.py`
- [X] T010 Implement `DEFAULT_PYTHON_STAGES` constant in `src/maverick/models/validation.py`
- [X] T011 Export all models from `src/maverick/models/__init__.py`
- [X] T012 Create `ValidationWorkflow` class skeleton with constructor in `src/maverick/workflows/validation.py`
- [X] T013 Export `ValidationWorkflow` from `src/maverick/workflows/__init__.py`

**Checkpoint**: Foundation ready - all models defined and workflow class skeleton exists

---

## Phase 3: User Story 1 - Run Validation Workflow (Priority: P1) 🎯 MVP

**Goal**: Execute validation stages in sequence with fix agent integration for auto-fixing failures

**Independent Test**: Run workflow against a project with intentional issues (formatting errors, lint warnings) and verify stages execute in order with fix attempts

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T014 [P] [US1] Unit test: workflow executes stages in configured order in `tests/unit/workflows/test_validation.py`
- [X] T015 [P] [US1] Unit test: stage passes on first attempt in `tests/unit/workflows/test_validation.py`
- [X] T016 [P] [US1] Unit test: fix agent invoked when fixable stage fails in `tests/unit/workflows/test_validation.py`
- [X] T017 [P] [US1] Unit test: stage retried after fix attempt in `tests/unit/workflows/test_validation.py`
- [X] T018 [P] [US1] Unit test: stage marked FIXED when passes after fix in `tests/unit/workflows/test_validation.py`
- [X] T019 [P] [US1] Unit test: stage marked FAILED after exhausting fix attempts in `tests/unit/workflows/test_validation.py`
- [X] T020 [P] [US1] Unit test: non-fixable stage not retried on failure in `tests/unit/workflows/test_validation.py`
- [X] T021 [P] [US1] Unit test: workflow continues to next stage after failure in `tests/unit/workflows/test_validation.py`
- [X] T022 [P] [US1] Unit test: workflow reports overall success when all stages pass in `tests/unit/workflows/test_validation.py`
- [X] T023 [P] [US1] Unit test: command not found fails stage immediately in `tests/unit/workflows/test_validation.py`
- [X] T023a [P] [US1] Unit test: command timeout fails stage immediately in `tests/unit/workflows/test_validation.py`

### Implementation for User Story 1

- [X] T024 [US1] Implement `_execute_command()` async method for subprocess execution in `src/maverick/workflows/validation.py`
- [X] T025 [US1] Implement `_run_stage()` method for single stage execution with retry logic in `src/maverick/workflows/validation.py`
- [X] T026 [US1] Implement `_invoke_fix_agent()` method for fix agent integration in `src/maverick/workflows/validation.py`
- [X] T027 [US1] Implement `run()` async generator method for workflow orchestration in `src/maverick/workflows/validation.py`
- [X] T028 [US1] Implement `get_result()` method to return final `ValidationWorkflowResult` in `src/maverick/workflows/validation.py`
- [X] T029 [US1] Handle edge case: max_fix_attempts=0 treated as non-fixable in `src/maverick/workflows/validation.py`
- [X] T030 [US1] Handle edge case: fix agent produces no changes (count as attempt) in `src/maverick/workflows/validation.py`

**Checkpoint**: User Story 1 complete - workflow executes stages with fix agent integration

---

## Phase 4: User Story 2 - View Progress Updates (Priority: P2)

**Goal**: Emit real-time progress updates for TUI consumption showing stage status and fix attempts

**Independent Test**: Run validation and observe streamed progress events appear in sequence with accurate stage and status information

### Tests for User Story 2

- [X] T031 [P] [US2] Unit test: progress update emitted when stage begins in `tests/unit/workflows/test_validation.py`
- [X] T032 [P] [US2] Unit test: progress update includes fix attempt number in `tests/unit/workflows/test_validation.py`
- [X] T033 [P] [US2] Unit test: progress update emitted on stage completion in `tests/unit/workflows/test_validation.py`
- [X] T034 [P] [US2] Unit test: timestamp included in progress updates in `tests/unit/workflows/test_validation.py`

### Implementation for User Story 2

- [X] T035 [US2] Yield `ProgressUpdate(status=IN_PROGRESS)` at stage start in `src/maverick/workflows/validation.py`
- [X] T036 [US2] Yield `ProgressUpdate` with fix_attempt number during fix cycles in `src/maverick/workflows/validation.py`
- [X] T037 [US2] Yield `ProgressUpdate` with final status on stage completion in `src/maverick/workflows/validation.py`
- [X] T038 [US2] Ensure progress updates emitted within 1 second of status changes (SC-003) in `src/maverick/workflows/validation.py`

**Checkpoint**: User Story 2 complete - progress updates stream to TUI consumer

---

## Phase 5: User Story 3 - Configure Validation Stages (Priority: P2)

**Goal**: Support custom stage configuration with commands, fixability, and max fix attempts

**Independent Test**: Provide custom stage configuration and verify workflow uses specified commands and settings

### Tests for User Story 3

- [X] T039 [P] [US3] Unit test: custom commands used instead of defaults in `tests/unit/workflows/test_validation.py`
- [X] T040 [P] [US3] Unit test: stage marked non-fixable skips fix agent in `tests/unit/workflows/test_validation.py`
- [X] T041 [P] [US3] Unit test: max_fix_attempts respected in retry loop in `tests/unit/workflows/test_validation.py`
- [X] T042 [P] [US3] Unit test: timeout_seconds enforced per command in `tests/unit/workflows/test_validation.py`

### Implementation for User Story 3

- [X] T043 [US3] Use `ValidationStage.command` for subprocess execution in `src/maverick/workflows/validation.py`
- [X] T044 [US3] Check `ValidationStage.is_fixable` property before invoking fix agent in `src/maverick/workflows/validation.py`
- [X] T045 [US3] Enforce `ValidationStage.timeout_seconds` in command execution in `src/maverick/workflows/validation.py`
- [X] T046 [US3] Use `ValidationWorkflowConfig.cwd` as working directory in `src/maverick/workflows/validation.py`
- [X] T047 [US3] Support `ValidationWorkflowConfig.stop_on_failure` option in `src/maverick/workflows/validation.py`

**Checkpoint**: User Story 3 complete - custom configuration fully supported

---

## Phase 6: User Story 4 - Dry-Run Mode (Priority: P3)

**Goal**: Preview planned actions without executing validation commands

**Independent Test**: Run with dry-run enabled and verify no actual commands execute while plan is reported

### Tests for User Story 4

- [X] T048 [P] [US4] Unit test: dry-run mode does not execute commands in `tests/unit/workflows/test_validation.py`
- [X] T049 [P] [US4] Unit test: dry-run reports planned commands in progress updates in `tests/unit/workflows/test_validation.py`
- [X] T050 [P] [US4] Unit test: dry-run returns success result in `tests/unit/workflows/test_validation.py`

### Implementation for User Story 4

- [X] T051 [US4] Check `config.dry_run` flag before command execution in `src/maverick/workflows/validation.py`
- [X] T052 [US4] Yield progress updates showing planned commands in dry-run mode in `src/maverick/workflows/validation.py`
- [X] T053 [US4] Return successful result with dry_run=True in metadata in `src/maverick/workflows/validation.py`

**Checkpoint**: User Story 4 complete - dry-run mode previews without execution

---

## Phase 7: User Story 5 - Cancel Workflow (Priority: P3)

**Goal**: Gracefully cancel running workflow and report partial results

**Independent Test**: Initiate cancellation mid-workflow and verify graceful termination with partial results

### Tests for User Story 5

- [X] T054 [P] [US5] Unit test: cancel() sets cancellation flag in `tests/unit/workflows/test_validation.py`
- [X] T055 [P] [US5] Unit test: workflow stops at earliest safe point after cancel in `tests/unit/workflows/test_validation.py`
- [X] T056 [P] [US5] Unit test: partial results available after cancellation in `tests/unit/workflows/test_validation.py`
- [X] T057 [P] [US5] Unit test: remaining stages marked CANCELLED in `tests/unit/workflows/test_validation.py`
- [X] T058 [P] [US5] Unit test: cancellation within 5 seconds (SC-005) in `tests/unit/workflows/test_validation.py`

### Implementation for User Story 5

- [X] T059 [US5] Initialize `asyncio.Event` for cancellation in constructor in `src/maverick/workflows/validation.py`
- [X] T060 [US5] Implement `cancel()` method to set cancellation event in `src/maverick/workflows/validation.py`
- [X] T061 [US5] Check cancellation flag between stages in `run()` method in `src/maverick/workflows/validation.py`
- [X] T062 [US5] Check cancellation flag between fix attempts in `src/maverick/workflows/validation.py`
- [X] T063 [US5] Mark remaining stages as CANCELLED when stopping in `src/maverick/workflows/validation.py`
- [X] T064 [US5] Set `cancelled=True` in `ValidationWorkflowResult` in `src/maverick/workflows/validation.py`

**Checkpoint**: User Story 5 complete - cancellation works with partial results

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Factory functions, integration tests, and final validation

- [X] T065 [P] Implement `create_python_workflow()` factory function in `src/maverick/workflows/validation.py`
- [X] T066 [P] Integration test: full workflow with real ruff commands in `tests/integration/workflows/test_validation_e2e.py`
- [X] T067 [P] Integration test: workflow with mock fix agent in `tests/integration/workflows/test_validation_e2e.py`
- [X] T068 Run `quickstart.md` examples to validate API usage
- [X] T069 Verify all FR requirements met (FR-001 to FR-018)
- [X] T070 Verify all SC success criteria met (SC-001 to SC-007)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational - core workflow execution
- **User Story 2 (Phase 4)**: Can start after Foundational (integrates with US1 implementation)
- **User Story 3 (Phase 5)**: Can start after Foundational (extends US1 configuration)
- **User Story 4 (Phase 6)**: Can start after US1 core is implemented
- **User Story 5 (Phase 7)**: Can start after US1 core is implemented
- **Polish (Phase 8)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Core workflow - no dependencies on other stories
- **User Story 2 (P2)**: Progress updates - tightly integrated with US1 `run()` method
- **User Story 3 (P2)**: Configuration - extends US1 stage execution
- **User Story 4 (P3)**: Dry-run - adds flag check to US1 execution path
- **User Story 5 (P3)**: Cancellation - adds cooperative cancellation to US1 loop

### Within Each User Story

- Tests MUST be written and FAIL before implementation (TDD)
- Models/enums before workflow methods
- Core logic before edge cases
- Unit tests before integration tests

### Parallel Opportunities

- **Phase 1**: All T001-T003 can run in parallel
- **Phase 2**: T004-T010 models can be written in parallel (same file but independent sections)
- **US1 Tests**: T014-T023 can all run in parallel (different test functions)
- **US2 Tests**: T031-T034 can all run in parallel
- **US3 Tests**: T039-T042 can all run in parallel
- **US4 Tests**: T048-T050 can all run in parallel
- **US5 Tests**: T054-T058 can all run in parallel
- **Polish**: T065-T067 can run in parallel

---

## Parallel Example: User Story 1 Tests

```bash
# Launch all US1 tests together:
Task: "Unit test: workflow executes stages in configured order"
Task: "Unit test: stage passes on first attempt"
Task: "Unit test: fix agent invoked when fixable stage fails"
Task: "Unit test: stage retried after fix attempt"
Task: "Unit test: stage marked FIXED when passes after fix"
Task: "Unit test: stage marked FAILED after exhausting fix attempts"
Task: "Unit test: non-fixable stage not retried on failure"
Task: "Unit test: workflow continues to next stage after failure"
Task: "Unit test: workflow reports overall success when all stages pass"
Task: "Unit test: command not found fails stage immediately"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (models, workflow skeleton)
3. Complete Phase 3: User Story 1 (core workflow execution)
4. **STOP and VALIDATE**: Test US1 independently with mock fix agent
5. Workflow can execute stages and invoke fix agent

### Incremental Delivery

1. Setup + Foundational → Models and skeleton ready
2. Add User Story 1 → Core execution works → MVP!
3. Add User Story 2 → Progress updates stream to TUI
4. Add User Story 3 → Custom configuration supported
5. Add User Story 4 → Dry-run mode works
6. Add User Story 5 → Cancellation supported
7. Polish → Factory functions, integration tests

### File Locations Summary

| Component | Location |
|-----------|----------|
| All models | `src/maverick/models/validation.py` |
| Workflow class | `src/maverick/workflows/validation.py` |
| Unit tests | `tests/unit/workflows/test_validation.py` |
| Integration tests | `tests/integration/workflows/test_validation_e2e.py` |

---

## Notes

- [P] tasks = different files or independent sections, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- TDD approach: Write tests first, ensure they fail, then implement
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
