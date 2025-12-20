# Tasks: Core Workflow DSL

**Input**: Design documents from `/specs/022-workflow-dsl/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Tests are REQUIRED for this feature per Constitution Check (V. Test-First: TDD required) and plan.md testing section.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure for the DSL module

- [X] T001 Create dsl module structure with `__init__.py` in `src/maverick/dsl/__init__.py`
- [X] T002 Create steps subpackage structure with `__init__.py` in `src/maverick/dsl/steps/__init__.py`
- [X] T003 [P] Create test directories `tests/unit/dsl/` and `tests/unit/dsl/steps/` with `__init__.py` files
- [X] T004 [P] Create integration test directory `tests/integration/dsl/` with `__init__.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core types and base classes that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T005 Implement `StepType` enum in `src/maverick/dsl/types.py` (PYTHON, AGENT, GENERATE, VALIDATE, SUBWORKFLOW)
- [X] T006 [P] Implement `WorkflowParameter` frozen dataclass in `src/maverick/dsl/decorator.py` (name, annotation, default, kind)
- [X] T007 [P] Implement `WorkflowDefinition` frozen dataclass in `src/maverick/dsl/decorator.py` (name, description, parameters, func)
- [X] T008 Implement `StepResult` frozen dataclass in `src/maverick/dsl/results.py` with `__post_init__` validation and `to_dict()` method
- [X] T009 Implement `WorkflowResult` frozen dataclass in `src/maverick/dsl/results.py` with `to_dict()` and `failed_step` property
- [X] T010 Implement `SubWorkflowInvocationResult` frozen dataclass in `src/maverick/dsl/results.py` with `to_dict()` method
- [X] T011 Implement `WorkflowContext` dataclass in `src/maverick/dsl/context.py` with `get_step_output()` method
- [X] T012 Implement `StepDefinition` abstract base class in `src/maverick/dsl/steps/base.py` with `execute()` and `to_dict()` abstract methods
- [X] T013 Implement progress event dataclasses in `src/maverick/dsl/events.py` (StepStarted, StepCompleted, WorkflowStarted, WorkflowCompleted)
- [X] T014 Implement error hierarchy in `src/maverick/exceptions.py` (WorkflowError, DuplicateStepNameError, StagesNotFoundError, ContextBuilderError)
- [X] T015 [P] Write unit tests for `StepType` enum in `tests/unit/dsl/test_types.py`
- [X] T016 [P] Write unit tests for `StepResult` in `tests/unit/dsl/test_results.py`
- [X] T017 [P] Write unit tests for `WorkflowResult` in `tests/unit/dsl/test_results.py`
- [X] T018 [P] Write unit tests for `WorkflowContext` in `tests/unit/dsl/test_context.py`
- [X] T019 [P] Write unit tests for progress events in `tests/unit/dsl/test_events.py`
- [X] T020 Update public exports in `src/maverick/dsl/__init__.py` with foundational types

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Define and run a workflow (Priority: P1) 🎯 MVP

**Goal**: Enable workflow authors to define a workflow as a sequence of named steps and execute it with inputs, accessing step outputs in later steps

**Independent Test**: Can be fully tested by defining a workflow with 2 Python steps, executing it with inputs, and verifying the final output and per-step results

### Tests for User Story 1 ⚠️

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T021 [P] [US1] Write unit tests for `@workflow` decorator in `tests/unit/dsl/test_decorator.py` - test signature capture, validation
- [X] T022 [P] [US1] Write unit tests for `step()` builder function in `tests/unit/dsl/test_builder.py` - test StepBuilder creation
- [X] T023 [P] [US1] Write unit tests for `PythonStep` in `tests/unit/dsl/steps/test_python_step.py` - test execute() and to_dict()
- [X] T024 [P] [US1] Write unit tests for `WorkflowEngine` in `tests/unit/dsl/test_engine.py` - test basic execution with Python steps
- [X] T025 [US1] Write integration test for two-step workflow execution in `tests/integration/dsl/test_workflow_execution.py`

### Implementation for User Story 1

- [X] T026 [US1] Implement `@workflow` decorator in `src/maverick/dsl/decorator.py` with signature inspection using `inspect.signature()`
- [X] T027 [US1] Implement `StepBuilder` class in `src/maverick/dsl/builder.py` with `python()` method only
- [X] T028 [US1] Implement `step(name)` factory function in `src/maverick/dsl/builder.py`
- [X] T029 [US1] Implement `PythonStep` class in `src/maverick/dsl/steps/python.py` with `execute()` and `to_dict()` methods
- [X] T030 [US1] Implement `WorkflowEngine` class in `src/maverick/dsl/engine.py` with generator-based execution loop using `send()` pattern
- [X] T031 [US1] Implement duplicate step name detection in `WorkflowEngine` per FR-005
- [X] T032 [US1] Implement final output logic in `WorkflowEngine` per FR-021 (explicit return vs last step output)
- [X] T033 [US1] Implement progress event emission in `WorkflowEngine` per FR-019
- [X] T034 [US1] Update step exports in `src/maverick/dsl/steps/__init__.py` with PythonStep
- [X] T035 [US1] Update public exports in `src/maverick/dsl/__init__.py` with workflow, step, WorkflowEngine

**Checkpoint**: At this point, User Story 1 should be fully functional and testable independently

---

## Phase 4: User Story 2 - Invoke agents with context (Priority: P2)

**Goal**: Enable workflow authors to invoke agent steps or generator steps with provided context (static or computed) and use their outputs in subsequent steps

**Independent Test**: Can be fully tested by running a workflow that yields a generate step and verifying the produced text is returned to the workflow and recorded as a step output

### Tests for User Story 2 ⚠️

- [X] T036 [P] [US2] Write unit tests for `AgentStep` in `tests/unit/dsl/steps/test_agent_step.py` - test execute() with static and callable context
- [X] T037 [P] [US2] Write unit tests for `GenerateStep` in `tests/unit/dsl/steps/test_generate_step.py` - test execute() with static and callable context
- [X] T038 [P] [US2] Write unit tests for context builder resolution in `tests/unit/dsl/steps/test_agent_step.py` - test _resolve_context() method
- [X] T039 [P] [US2] Write unit tests for context builder failure handling in `tests/unit/dsl/steps/test_agent_step.py`
- [X] T040 [US2] Write integration test for agent workflow execution in `tests/integration/dsl/test_workflow_execution.py`

### Implementation for User Story 2

- [X] T041 [US2] Add `ContextBuilder` type alias in `src/maverick/dsl/types.py`
- [X] T042 [US2] Implement `AgentStep` class in `src/maverick/dsl/steps/agent.py` with `_resolve_context()`, `execute()`, and `to_dict()` methods
- [X] T043 [US2] Implement `GenerateStep` class in `src/maverick/dsl/steps/generate.py` with `_resolve_context()`, `execute()`, and `to_dict()` methods
- [X] T044 [US2] Add `agent()` method to `StepBuilder` in `src/maverick/dsl/builder.py`
- [X] T045 [US2] Add `generate()` method to `StepBuilder` in `src/maverick/dsl/builder.py`
- [X] T046 [US2] Update step exports in `src/maverick/dsl/steps/__init__.py` with AgentStep, GenerateStep
- [X] T047 [US2] Update public exports in `src/maverick/dsl/__init__.py` with AgentStep, GenerateStep

**Checkpoint**: At this point, User Stories 1 AND 2 should both work independently

---

## Phase 5: User Story 3 - Validate outputs with retry and optional fixes (Priority: P3)

**Goal**: Enable workflow authors to validate prior step outputs with retry logic and optional fix steps to build resilient, self-correcting workflows

**Independent Test**: Can be fully tested by configuring a validate step to fail once, run an on-failure fix step, and then pass on the next attempt

### Tests for User Story 3 ⚠️

- [X] T048 [P] [US3] Write unit tests for `ValidateStep` in `tests/unit/dsl/steps/test_validate_step.py` - test execute() with stages resolution
- [X] T049 [P] [US3] Write unit tests for retry logic in `tests/unit/dsl/steps/test_validate_step.py` - test retry=0, retry=1, retry=N scenarios
- [X] T050 [P] [US3] Write unit tests for on-failure step execution in `tests/unit/dsl/steps/test_validate_step.py`
- [X] T051 [P] [US3] Write unit tests for `SubWorkflowStep` in `tests/unit/dsl/steps/test_subworkflow_step.py` - test execute() and to_dict()
- [X] T052 [US3] Write integration test for validate-retry-fix workflow in `tests/integration/dsl/test_workflow_execution.py`

### Implementation for User Story 3

- [X] T053 [US3] Implement `ValidateStep` class in `src/maverick/dsl/steps/validate.py` with stages resolution, retry loop, and on-failure execution
- [X] T054 [US3] Implement `SubWorkflowStep` class in `src/maverick/dsl/steps/subworkflow.py` with nested workflow execution
- [X] T055 [US3] Add `validate()` method to `StepBuilder` in `src/maverick/dsl/builder.py`
- [X] T056 [US3] Add `subworkflow()` method to `StepBuilder` in `src/maverick/dsl/builder.py`
- [X] T057 [US3] Update step exports in `src/maverick/dsl/steps/__init__.py` with ValidateStep, SubWorkflowStep
- [X] T058 [US3] Update public exports in `src/maverick/dsl/__init__.py` with ValidateStep, SubWorkflowStep

**Checkpoint**: All user stories should now be independently functional

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [X] T059 [P] Add comprehensive docstrings to all public classes and functions per Google-style format
- [X] T060 [P] Run type checker (mypy) on `src/maverick/dsl/` and fix any issues
- [X] T061 [P] Run linter (ruff) on `src/maverick/dsl/` and fix any issues
- [X] T062 Run full test suite and ensure all tests pass
- [X] T063 Validate quickstart.md examples work correctly with implemented DSL

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3+)**: All depend on Foundational phase completion
  - User stories can then proceed in parallel (if staffed)
  - Or sequentially in priority order (P1 → P2 → P3)
- **Polish (Final Phase)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 2 (P2)**: Can start after Foundational (Phase 2) - May integrate with US1 but should be independently testable
- **User Story 3 (P3)**: Can start after Foundational (Phase 2) - May integrate with US1/US2 but should be independently testable

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- Core types before step implementations
- Step implementations before builder methods
- Engine updates after step implementations
- Story complete before moving to next priority

### Parallel Opportunities

- All Setup tasks marked [P] can run in parallel
- All Foundational tasks marked [P] can run in parallel (within Phase 2)
- Once Foundational phase completes, all user stories can start in parallel (if team capacity allows)
- All tests for a user story marked [P] can run in parallel
- Different user stories can be worked on in parallel by different team members

---

## Parallel Example: Phase 2 (Foundational)

```bash
# Launch parallel foundational tasks:
Task: T006 "Implement WorkflowParameter in src/maverick/dsl/decorator.py"
Task: T007 "Implement WorkflowDefinition in src/maverick/dsl/decorator.py"

# Launch parallel test writing:
Task: T015 "Write unit tests for StepType in tests/unit/dsl/test_types.py"
Task: T016 "Write unit tests for StepResult in tests/unit/dsl/test_results.py"
Task: T017 "Write unit tests for WorkflowResult in tests/unit/dsl/test_results.py"
Task: T018 "Write unit tests for WorkflowContext in tests/unit/dsl/test_context.py"
Task: T019 "Write unit tests for progress events in tests/unit/dsl/test_events.py"
```

## Parallel Example: User Story 1

```bash
# Launch all tests for User Story 1 together:
Task: T021 "Write unit tests for @workflow decorator in tests/unit/dsl/test_decorator.py"
Task: T022 "Write unit tests for step() builder in tests/unit/dsl/test_builder.py"
Task: T023 "Write unit tests for PythonStep in tests/unit/dsl/steps/test_python_step.py"
Task: T024 "Write unit tests for WorkflowEngine in tests/unit/dsl/test_engine.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Test User Story 1 independently
5. Deploy/demo if ready

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently → Deploy/Demo (MVP!)
3. Add User Story 2 → Test independently → Deploy/Demo
4. Add User Story 3 → Test independently → Deploy/Demo
5. Each story adds value without breaking previous stories

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1
   - Developer B: User Story 2
   - Developer C: User Story 3
3. Stories complete and integrate independently

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verify tests fail before implementing (TDD per Constitution)
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Avoid: vague tasks, same file conflicts, cross-story dependencies that break independence
