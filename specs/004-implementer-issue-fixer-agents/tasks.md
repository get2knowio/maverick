# Tasks: ImplementerAgent and IssueFixerAgent

**Input**: Design documents from `/specs/004-implementer-issue-fixer-agents/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/agent-interfaces.md

**Tests**: Included per project testing requirements (pytest + pytest-asyncio)

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `src/maverick/`, `tests/` at repository root (per plan.md)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project structure and new module initialization

- [x] T001 Create directory `src/maverick/utils/` if it doesn't exist
- [x] T002 [P] Create `src/maverick/utils/__init__.py` with public exports for git, github, validation, task_parser
- [x] T003 [P] Create `tests/unit/utils/` directory structure with `__init__.py`
- [x] T004 [P] Create `tests/integration/` directory structure with `__init__.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**CRITICAL**: No user story work can begin until this phase is complete

### Exception Types (required by all agents)

- [x] T005 [P] Add `TaskParseError` exception class to `src/maverick/exceptions.py`
- [x] T006 [P] Add `GitError` exception class to `src/maverick/exceptions.py`
- [x] T007 [P] Add `GitHubError` exception class to `src/maverick/exceptions.py`
- [x] T008 [P] Add `ValidationError` exception class to `src/maverick/exceptions.py`

### Enums and Value Objects (shared by both agents)

- [x] T009 [P] Create `TaskStatus`, `ChangeType`, `ValidationStep` enums in `src/maverick/models/implementation.py`
- [x] T010 [P] Create `Task` model (id, description, status, parallel, user_story, phase, dependencies) in `src/maverick/models/implementation.py`
- [x] T011 [P] Create `FileChange` model (file_path, change_type, lines_added, lines_removed, old_path) in `src/maverick/models/implementation.py`
- [x] T012 [P] Create `ValidationResult` model (step, success, output, duration_ms, auto_fixed) in `src/maverick/models/implementation.py`

### Shared Utilities (required by both agents)

- [x] T013 Implement `TaskFile` model with `parse()`, `pending_tasks`, `get_parallel_batch()`, `get_next_sequential()` in `src/maverick/models/implementation.py`
- [x] T014 [P] Create `src/maverick/utils/git.py` with async git helper functions (commit, stash, unstash, recovery)
- [x] T015 [P] Create `src/maverick/utils/github.py` with async GitHub CLI wrapper (fetch_issue with retry/backoff)
- [x] T016 Create `src/maverick/utils/validation.py` with validation pipeline runner (format, lint, typecheck, test)
- [x] T017 Implement `task_parser.py` with regex-based parsing for .specify tasks.md format in `src/maverick/utils/task_parser.py`

### Unit Tests for Foundational Components

- [x] T018 [P] Create unit tests for exception classes in `tests/unit/test_exceptions.py`
- [x] T019 [P] Create unit tests for enums in `tests/unit/models/test_implementation_enums.py`
- [x] T020 [P] Create unit tests for `Task`, `FileChange`, `ValidationResult` models in `tests/unit/models/test_implementation_models.py`
- [x] T021 Create unit tests for `TaskFile` model and parsing in `tests/unit/models/test_task_file.py`
- [x] T022 [P] Create unit tests for git utilities in `tests/unit/utils/test_git.py`
- [x] T023 [P] Create unit tests for GitHub utilities in `tests/unit/utils/test_github.py`
- [x] T024 Create unit tests for validation runner in `tests/unit/utils/test_validation.py`
- [x] T025 Create unit tests for task parser in `tests/unit/utils/test_task_parser.py`

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 1 - Execute Implementation Tasks from Task File (Priority: P1) MVP

**Goal**: ImplementerAgent executes structured task lists (tasks.md) with TDD approach, sequential execution, and conventional commits.

**Independent Test**: Provide a task file with 2-3 tasks and verify the agent produces commits with expected code changes.

**Maps to**: FR-001, FR-002, FR-003, FR-004, FR-005, FR-006, FR-007, FR-008, FR-009, FR-010, FR-022, FR-023, FR-024, FR-025

### Context and Result Models for User Story 1

- [x] T026 [P] [US1] Create `TaskResult` model (task_id, status, files_changed, tests_added, commit_sha, error, duration_ms, validation) in `src/maverick/models/implementation.py`
- [x] T027 [P] [US1] Create `ImplementationResult` model (success, tasks_completed/failed/skipped, task_results, files_changed, commits, validation_passed, output, metadata, errors) in `src/maverick/models/implementation.py`
- [x] T028 [US1] Create `ImplementerContext` model with validation (task_file XOR task_description, branch, cwd, skip_validation, dry_run) in `src/maverick/models/implementation.py`

### ImplementerAgent Core Implementation

- [x] T029 [US1] Create `ImplementerAgent` class extending `MaverickAgent` with name="implementer" in `src/maverick/agents/implementer.py`
- [x] T030 [US1] Implement `IMPLEMENTER_SYSTEM_PROMPT` constant with TDD guidance and conventional commits instructions in `src/maverick/agents/implementer.py`
- [x] T031 [US1] Implement `allowed_tools` property returning ["Read", "Write", "Edit", "Bash", "Glob", "Grep"] in `src/maverick/agents/implementer.py`
- [x] T032 [US1] Implement `execute()` method skeleton with context validation and task file parsing in `src/maverick/agents/implementer.py`
- [x] T033 [US1] Implement `_execute_single_task()` private method for task execution with Claude SDK in `src/maverick/agents/implementer.py`
- [x] T034 [US1] Implement `_create_commit()` private method with conventional commit format and git recovery in `src/maverick/agents/implementer.py`
- [x] T035 [US1] Implement `_run_validation()` private method calling validation pipeline in `src/maverick/agents/implementer.py`
- [x] T036 [US1] Integrate task file parsing, sequential execution, validation, and commit flow in `execute()` in `src/maverick/agents/implementer.py`

### Unit Tests for User Story 1

- [ ] T037 [P] [US1] Create unit tests for `TaskResult`, `ImplementationResult` models in `tests/unit/models/test_implementation_results.py`
- [ ] T038 [P] [US1] Create unit tests for `ImplementerContext` validation in `tests/unit/models/test_implementer_context.py`
- [ ] T039 [US1] Create unit tests for `ImplementerAgent` properties and initialization in `tests/unit/agents/test_implementer.py`
- [ ] T040 [US1] Create unit tests for `_execute_single_task()` with mocked Claude SDK in `tests/unit/agents/test_implementer.py`
- [ ] T041 [US1] Create unit tests for `_create_commit()` with mocked git in `tests/unit/agents/test_implementer.py`
- [ ] T042 [US1] Create integration test for `execute()` with task file in `tests/integration/test_implementer_e2e.py`

### Module Exports for User Story 1

- [x] T043 [US1] Update `src/maverick/agents/__init__.py` to export `ImplementerAgent`
- [x] T044 [US1] Update `src/maverick/models/__init__.py` to export implementation models

**Checkpoint**: User Story 1 complete - ImplementerAgent can execute sequential tasks from task files

---

## Phase 4: User Story 2 - Fix GitHub Issue with Minimal Changes (Priority: P1)

**Goal**: IssueFixerAgent resolves GitHub issues with minimal, targeted code changes and verification.

**Independent Test**: Provide a GitHub issue number for a known bug and verify the agent produces a working fix.

**Maps to**: FR-011, FR-012, FR-013, FR-014, FR-015, FR-015a, FR-016, FR-017, FR-018, FR-019, FR-020, FR-021, FR-022, FR-023, FR-024, FR-024a, FR-025

### Context and Result Models for User Story 2

- [x] T045 [P] [US2] Create `FixResult` model (success, issue_number/title/url, root_cause, fix_description, files_changed, commit_sha, verification_passed, validation_passed, output, metadata, errors) in `src/maverick/models/issue_fix.py`
- [x] T046 [US2] Create `IssueFixerContext` model with validation (issue_number XOR issue_data, cwd, skip_validation, dry_run) in `src/maverick/models/issue_fix.py`

### IssueFixerAgent Core Implementation

- [x] T047 [US2] Create `IssueFixerAgent` class extending `MaverickAgent` with name="issue-fixer" in `src/maverick/agents/issue_fixer.py`
- [x] T048 [US2] Implement `ISSUE_FIXER_SYSTEM_PROMPT` constant emphasizing minimal changes and verification in `src/maverick/agents/issue_fixer.py`
- [x] T049 [US2] Implement `allowed_tools` property returning ["Read", "Write", "Edit", "Bash", "Glob", "Grep"] in `src/maverick/agents/issue_fixer.py`
- [x] T050 [US2] Implement `execute()` method skeleton with context validation in `src/maverick/agents/issue_fixer.py`
- [x] T051 [US2] Implement `_fetch_issue()` private method using GitHub CLI with retry/backoff in `src/maverick/agents/issue_fixer.py`
- [x] T052 [US2] Implement `_analyze_and_fix()` private method for issue analysis and fix with Claude SDK in `src/maverick/agents/issue_fixer.py`
- [x] T053 [US2] Implement `_verify_fix()` private method for fix verification in `src/maverick/agents/issue_fixer.py`
- [x] T054 [US2] Implement `_create_commit()` private method with issue reference in commit message in `src/maverick/agents/issue_fixer.py`
- [x] T055 [US2] Integrate issue fetch, analysis, fix, verification, validation, and commit flow in `execute()` in `src/maverick/agents/issue_fixer.py`

### Unit Tests for User Story 2

- [ ] T056 [P] [US2] Create unit tests for `FixResult` model in `tests/unit/models/test_fix_result.py`
- [ ] T057 [P] [US2] Create unit tests for `IssueFixerContext` validation in `tests/unit/models/test_issue_fixer_context.py`
- [ ] T058 [US2] Create unit tests for `IssueFixerAgent` properties and initialization in `tests/unit/agents/test_issue_fixer.py`
- [ ] T059 [US2] Create unit tests for `_fetch_issue()` with mocked GitHub CLI in `tests/unit/agents/test_issue_fixer.py`
- [ ] T060 [US2] Create unit tests for `_analyze_and_fix()` with mocked Claude SDK in `tests/unit/agents/test_issue_fixer.py`
- [ ] T061 [US2] Create integration test for `execute()` with issue data in `tests/integration/test_issue_fixer_e2e.py`

### Module Exports for User Story 2

- [x] T062 [US2] Update `src/maverick/agents/__init__.py` to export `IssueFixerAgent`
- [x] T063 [US2] Update `src/maverick/models/__init__.py` to export issue_fix models

**Checkpoint**: User Story 2 complete - IssueFixerAgent can fetch and fix GitHub issues

---

## Phase 5: User Story 3 - Run Validation Before Completing Work (Priority: P2)

**Goal**: Both agents ensure work passes project validation (format, lint, test) before completing tasks.

**Independent Test**: Have an agent complete work that introduces a linting error and verify it auto-fixes before committing.

**Maps to**: FR-008, FR-021, FR-024, FR-024a

### Validation Integration for User Story 3

- [ ] T064 [US3] Enhance `_run_validation()` in ImplementerAgent with auto-fix retry logic (max 3 attempts) in `src/maverick/agents/implementer.py`
- [ ] T065 [US3] Enhance `_run_validation()` in IssueFixerAgent with auto-fix retry logic (max 3 attempts) in `src/maverick/agents/issue_fixer.py`
- [ ] T066 [US3] Add validation result aggregation to `TaskResult` and `ImplementationResult` in ImplementerAgent in `src/maverick/agents/implementer.py`
- [ ] T067 [US3] Add validation result to `FixResult` in IssueFixerAgent in `src/maverick/agents/issue_fixer.py`

### Unit Tests for User Story 3

- [ ] T068 [P] [US3] Create unit tests for validation auto-fix retry in ImplementerAgent in `tests/unit/agents/test_implementer.py`
- [ ] T069 [P] [US3] Create unit tests for validation auto-fix retry in IssueFixerAgent in `tests/unit/agents/test_issue_fixer.py`
- [ ] T070 [US3] Create integration test for validation failure and auto-fix in `tests/integration/test_validation_flow.py`

**Checkpoint**: User Story 3 complete - both agents run validation with auto-fix before committing

---

## Phase 6: User Story 4 - Provide Structured Implementation Summary (Priority: P2)

**Goal**: Both agents return structured summaries including files changed, tests added, commits created.

**Independent Test**: Verify result dataclass contains all expected fields after successful execution.

**Maps to**: FR-009, FR-020, FR-025

### Summary Enhancement for User Story 4

- [ ] T071 [US4] Add `to_summary()` method to `ImplementationResult` for human-readable summary in `src/maverick/models/implementation.py`
- [ ] T072 [US4] Add `to_summary()` method to `FixResult` for human-readable summary in `src/maverick/models/issue_fix.py`
- [ ] T073 [US4] Add `total_lines_changed`, `tests_added` computed properties to `ImplementationResult` in `src/maverick/models/implementation.py`
- [ ] T074 [US4] Add `total_lines_changed`, `is_minimal_fix` computed properties to `FixResult` in `src/maverick/models/issue_fix.py`
- [ ] T075 [US4] Ensure JSON serialization roundtrip works for all result models in `src/maverick/models/implementation.py` and `src/maverick/models/issue_fix.py`

### Unit Tests for User Story 4

- [ ] T076 [P] [US4] Create unit tests for `to_summary()` methods in `tests/unit/models/test_implementation_results.py`
- [ ] T077 [P] [US4] Create unit tests for `to_summary()` methods in `tests/unit/models/test_fix_result.py`
- [ ] T078 [US4] Create unit tests for JSON serialization roundtrip in `tests/unit/models/test_serialization.py`

**Checkpoint**: User Story 4 complete - both agents provide structured, serializable summaries

---

## Phase 7: User Story 5 - Execute Task from Direct Description (Priority: P3)

**Goal**: ImplementerAgent executes a single task without creating a task file.

**Independent Test**: Provide a task description string and verify execution matches task file behavior.

**Maps to**: FR-004 (task_description alternative)

### Direct Task Execution for User Story 5

- [ ] T079 [US5] Implement direct task description handling in `execute()` method (create synthetic single-task TaskFile) in `src/maverick/agents/implementer.py`
- [ ] T080 [US5] Add validation for mutual exclusivity of task_file/task_description in `ImplementerContext` in `src/maverick/models/implementation.py`

### Unit Tests for User Story 5

- [ ] T081 [US5] Create unit tests for direct task description execution in `tests/unit/agents/test_implementer.py`
- [ ] T082 [US5] Create integration test for direct task execution in `tests/integration/test_implementer_e2e.py`

**Checkpoint**: User Story 5 complete - ImplementerAgent accepts direct task descriptions

---

## Phase 8: User Story 6 - Accept Issue Data Dictionary (Priority: P3)

**Goal**: IssueFixerAgent accepts pre-fetched issue data instead of fetching from GitHub.

**Independent Test**: Provide issue data dict and verify the agent skips GitHub fetch.

**Maps to**: FR-014 (issue_data alternative)

### Pre-fetched Issue Data for User Story 6

- [ ] T083 [US6] Implement pre-fetched issue data handling in `execute()` method (skip GitHub fetch) in `src/maverick/agents/issue_fixer.py`
- [ ] T084 [US6] Add validation for required fields in issue_data (number, title, body) in `IssueFixerContext` in `src/maverick/models/issue_fix.py`

### Unit Tests for User Story 6

- [ ] T085 [US6] Create unit tests for pre-fetched issue data in `tests/unit/agents/test_issue_fixer.py`
- [ ] T086 [US6] Create integration test for pre-fetched issue data in `tests/integration/test_issue_fixer_e2e.py`

**Checkpoint**: User Story 6 complete - IssueFixerAgent accepts pre-fetched issue data

---

## Phase 9: Parallel Task Execution Enhancement (Priority: P2)

**Goal**: ImplementerAgent supports parallel task execution for tasks marked with [P] prefix.

**Maps to**: FR-006, FR-006a

### Parallel Execution Implementation

- [ ] T087 Implement `_execute_parallel_tasks()` private method with asyncio.gather and retry logic in `src/maverick/agents/implementer.py`
- [ ] T088 Integrate parallel batch detection and execution in main `execute()` loop in `src/maverick/agents/implementer.py`
- [ ] T089 Add parallel result aggregation to `ImplementationResult` in `src/maverick/agents/implementer.py`

### Unit Tests for Parallel Execution

- [ ] T090 Create unit tests for `_execute_parallel_tasks()` with mocked sub-agents in `tests/unit/agents/test_implementer.py`
- [ ] T091 Create unit tests for parallel task retry on failure in `tests/unit/agents/test_implementer.py`
- [ ] T092 Create integration test for parallel task execution in `tests/integration/test_implementer_e2e.py`

**Checkpoint**: Parallel execution complete - ImplementerAgent can run [P] tasks concurrently

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [ ] T093 [P] Add type hints and docstrings to all public APIs in `src/maverick/agents/implementer.py`
- [ ] T094 [P] Add type hints and docstrings to all public APIs in `src/maverick/agents/issue_fixer.py`
- [ ] T095 [P] Add type hints and docstrings to all public APIs in `src/maverick/utils/*.py`
- [ ] T096 [P] Add type hints and docstrings to all public APIs in `src/maverick/models/implementation.py`
- [ ] T097 [P] Add type hints and docstrings to all public APIs in `src/maverick/models/issue_fix.py`
- [ ] T098 Run quickstart.md scenarios to validate all acceptance criteria
- [ ] T099 Run full test suite and fix any failures: `pytest tests/ -v`
- [ ] T100 Run linting and fix issues: `ruff check --fix .`
- [ ] T101 Run type checking and fix issues: `mypy src/maverick/`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational - ImplementerAgent core
- **User Story 2 (Phase 4)**: Depends on Foundational - IssueFixerAgent core (can parallel with US1)
- **User Story 3 (Phase 5)**: Depends on US1 and US2 - validation enhancement
- **User Story 4 (Phase 6)**: Depends on US1 and US2 - structured output
- **User Story 5 (Phase 7)**: Depends on US1 - direct task description
- **User Story 6 (Phase 8)**: Depends on US2 - pre-fetched issue data
- **Parallel Execution (Phase 9)**: Depends on US1 - parallel task execution
- **Polish (Phase 10)**: Depends on all phases

### User Story Dependencies

- **User Story 1 (P1)**: Core ImplementerAgent - can start after Foundational
- **User Story 2 (P1)**: Core IssueFixerAgent - can start after Foundational (parallel with US1)
- **User Story 3 (P2)**: Validation - requires US1 and US2 base implementations
- **User Story 4 (P2)**: Summaries - requires US1 and US2 base implementations
- **User Story 5 (P3)**: Direct task - requires US1 complete
- **User Story 6 (P3)**: Pre-fetched data - requires US2 complete

### Within Each User Story

- Models before agents (dependencies)
- Agent skeleton before methods
- Private methods before public execute()
- Unit tests can parallel with implementation
- Integration tests after implementation

### Parallel Opportunities

- All Setup tasks marked [P] can run in parallel
- All Foundational exception tasks (T005-T008) can run in parallel
- All Foundational model tasks (T009-T012) can run in parallel
- All Foundational utility tasks (T014-T015) can run in parallel
- All Foundational unit test tasks can run in parallel (within their groups)
- US1 and US2 can be developed in parallel after Foundational
- US3 and US4 can be developed in parallel after US1/US2
- US5 and US6 can be developed in parallel after their respective dependencies
- All Polish tasks marked [P] can run in parallel

---

## Parallel Example: User Story 1

```bash
# Launch all US1 model tasks together:
Task: "T026 [P] [US1] Create TaskResult model"
Task: "T027 [P] [US1] Create ImplementationResult model"

# Launch all US1 unit test tasks together:
Task: "T037 [P] [US1] Create unit tests for TaskResult, ImplementationResult"
Task: "T038 [P] [US1] Create unit tests for ImplementerContext"
```

---

## Implementation Strategy

### MVP First (User Stories 1 + 2 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1 (ImplementerAgent core)
4. Complete Phase 4: User Story 2 (IssueFixerAgent core)
5. **STOP and VALIDATE**: Test both agents independently
6. Deploy/demo if ready

### Incremental Delivery

1. Setup + Foundational -> Foundation ready
2. Add User Story 1 -> Test independently -> ImplementerAgent MVP
3. Add User Story 2 -> Test independently -> IssueFixerAgent MVP
4. Add User Story 3 -> Validation enhancement
5. Add User Story 4 -> Structured summaries
6. Add User Story 5/6 -> Convenience features
7. Add Phase 9 -> Parallel execution
8. Polish and finalize

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1 (ImplementerAgent)
   - Developer B: User Story 2 (IssueFixerAgent)
3. After both complete:
   - Developer A: User Story 3 + 5
   - Developer B: User Story 4 + 6
4. Together: Phase 9 + Polish

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verify tests pass after each task
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Both agents share validation and git patterns - refactor into utilities
