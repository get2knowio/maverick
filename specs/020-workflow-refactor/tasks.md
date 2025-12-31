# Tasks: Workflow Refactor to Python-Orchestrated Pattern

**Input**: Design documents from `/specs/020-workflow-refactor/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Tests ARE included as this is a core infrastructure feature requiring comprehensive coverage.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `src/maverick/`, `tests/` at repository root
- Paths shown below follow the existing Maverick structure

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the new GitRunner abstraction that all workflows depend on

- [X] T001 Create GitResult dataclass in src/maverick/runners/git.py
- [X] T002 Implement GitRunner class skeleton with CommandRunner injection in src/maverick/runners/git.py
- [X] T003 [P] Add GitRunner to src/maverick/runners/__init__.py exports

---

## Phase 2: Foundational (GitRunner Implementation)

**Purpose**: Complete GitRunner implementation - MUST be complete before ANY user story can be implemented

**CRITICAL**: No user story work can begin until GitRunner is fully functional

- [X] T004 Implement GitRunner.create_branch() method in src/maverick/runners/git.py
- [X] T005 Implement GitRunner.checkout() method in src/maverick/runners/git.py
- [X] T006 [P] Implement GitRunner.commit() method in src/maverick/runners/git.py
- [X] T007 [P] Implement GitRunner.push() method in src/maverick/runners/git.py
- [X] T008 [P] Implement GitRunner.diff() method in src/maverick/runners/git.py
- [X] T009 [P] Implement GitRunner.add() method in src/maverick/runners/git.py
- [X] T010 [P] Implement GitRunner.status() method in src/maverick/runners/git.py
- [X] T011 Implement create_branch_with_fallback() for branch conflict resolution (FR-001a) in src/maverick/runners/git.py
- [X] T012 [P] Write unit tests for GitRunner in tests/unit/runners/test_git.py
- [X] T013 Run GitRunner tests: PYTHONPATH=src python -m pytest tests/unit/runners/test_git.py -v

**Checkpoint**: GitRunner ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Run FlyWorkflow with Reduced Token Usage (Priority: P1)

**Goal**: Implement FlyWorkflow.execute() with Python orchestration for deterministic operations and reduced token consumption

**Independent Test**: Run complete FlyWorkflow from task file to PR creation and verify token consumption reduced by 40%+

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T014 [P] [US1] Create test for INIT stage (branch creation without AI) in tests/unit/workflows/test_fly.py
- [X] T015 [P] [US1] Create test for IMPLEMENTATION stage (ImplementerAgent invocation) in tests/unit/workflows/test_fly.py
- [X] T016 [P] [US1] Create test for VALIDATION stage (ValidationRunner + retry) in tests/unit/workflows/test_fly.py
- [X] T017 [P] [US1] Create test for CODE_REVIEW stage (CodeRabbit optional) in tests/unit/workflows/test_fly.py
- [X] T018 [P] [US1] Create test for PR_CREATION stage (PR body generation) in tests/unit/workflows/test_fly.py
- [X] T019 [P] [US1] Create test for progress event emission at each stage in tests/unit/workflows/test_fly.py
- [X] T020 [P] [US1] Create test for error handling (stage failure continues workflow) in tests/unit/workflows/test_fly.py

### Implementation for User Story 1

- [X] T021 [US1] Add injectable dependency parameters to FlyWorkflow.__init__() in src/maverick/workflows/fly.py
- [X] T022 [US1] Add _cancel_event and internal state tracking in src/maverick/workflows/fly.py
- [X] T023 [US1] Implement execute() method signature returning AsyncIterator[FlyProgressEvent] in src/maverick/workflows/fly.py
- [X] T024 [US1] Implement INIT stage: branch creation via GitRunner (FR-001, FR-002) in src/maverick/workflows/fly.py
- [X] T025 [US1] Implement task file parsing via Python file I/O (FR-002) in src/maverick/workflows/fly.py
- [X] T026 [US1] Implement context building for ImplementerAgent (FR-003) in src/maverick/workflows/fly.py
- [X] T027 [US1] Implement IMPLEMENTATION stage: ImplementerAgent invocation (FR-004) in src/maverick/workflows/fly.py
- [X] T028 [US1] Implement VALIDATION stage: ValidationRunner integration (FR-007) in src/maverick/workflows/fly.py
- [X] T029 [US1] Implement validation retry loop with fix agent (FR-008, FR-009) in src/maverick/workflows/fly.py
- [X] T030 [US1] Implement CODE_REVIEW stage: CodeRabbitRunner + CodeReviewerAgent (FR-010, FR-011) in src/maverick/workflows/fly.py
- [X] T031 [US1] Implement COMMIT stage: diff + CommitMessageGenerator + GitRunner.commit (FR-005, FR-006) in src/maverick/workflows/fly.py
- [X] T032 [US1] Implement PR_CREATION stage: PRDescriptionGenerator + GitHubCLIRunner (FR-012, FR-013) in src/maverick/workflows/fly.py
- [X] T033 [US1] Implement token usage aggregation in _aggregate_tokens() method in src/maverick/workflows/fly.py
- [X] T034 [US1] Implement get_result() method returning FlyResult in src/maverick/workflows/fly.py
- [X] T035 [US1] Implement cancel() method for cooperative cancellation in src/maverick/workflows/fly.py
- [X] T036 [US1] Run FlyWorkflow tests: PYTHONPATH=src python -m pytest tests/unit/workflows/test_fly.py -v

**Checkpoint**: FlyWorkflow should be fully functional and testable independently

---

## Phase 4: User Story 2 - Run RefuelWorkflow for Multiple Issues (Priority: P1)

**Goal**: Implement RefuelWorkflow.execute() with per-issue isolation and Python orchestration

**Independent Test**: Create 3 test issues, run RefuelWorkflow, verify each produces its own branch, commits, and PR

### Tests for User Story 2

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T037 [P] [US2] Create test for issue discovery via GitHubCLIRunner (FR-014) in tests/unit/workflows/test_refuel.py
- [X] T038 [P] [US2] Create test for branch creation per issue (FR-015) in tests/unit/workflows/test_refuel.py
- [X] T039 [P] [US2] Create test for issue isolation (one failure doesn't crash others) in tests/unit/workflows/test_refuel.py
- [X] T040 [P] [US2] Create test for result aggregation (FR-019) in tests/unit/workflows/test_refuel.py
- [X] T041 [P] [US2] Create test for progress events per issue in tests/unit/workflows/test_refuel.py

### Implementation for User Story 2

- [X] T042 [US2] Add injectable dependency parameters to RefuelWorkflow.__init__() in src/maverick/workflows/refuel.py
- [X] T043 [US2] Implement execute() method signature returning AsyncGenerator[RefuelProgressEvent, None] in src/maverick/workflows/refuel.py
- [X] T044 [US2] Implement issue discovery via GitHubCLIRunner.list_issues() (FR-014) in src/maverick/workflows/refuel.py
- [X] T045 [US2] Implement issue filtering by skip_if_assigned policy in src/maverick/workflows/refuel.py
- [X] T046 [US2] Implement _process_issue() helper method for per-issue processing in src/maverick/workflows/refuel.py
- [X] T047 [US2] Implement branch creation per issue via GitRunner (FR-015) in src/maverick/workflows/refuel.py
- [X] T048 [US2] Implement issue context building (FR-016) in src/maverick/workflows/refuel.py
- [X] T049 [US2] Implement IssueFixerAgent invocation (FR-017) in src/maverick/workflows/refuel.py
- [X] T050 [US2] Implement per-issue validation via ValidationRunner in src/maverick/workflows/refuel.py
- [X] T051 [US2] Implement per-issue commit with CommitMessageGenerator in src/maverick/workflows/refuel.py
- [X] T052 [US2] Implement per-issue PR creation via GitHubCLIRunner in src/maverick/workflows/refuel.py
- [X] T053 [US2] Implement error isolation: try/except per issue with continue (FR-018) in src/maverick/workflows/refuel.py
- [X] T054 [US2] Implement result aggregation in RefuelResult (FR-019) in src/maverick/workflows/refuel.py
- [X] T054a [US2] Implement network failure retry with exponential backoff (FR-025) in src/maverick/workflows/refuel.py
- [X] T054b [US2] Implement skip-after-3-attempts logic for stuck issues (FR-026) in src/maverick/workflows/refuel.py
- [X] T054c [P] [US2] Create test for network failure retry behavior in tests/unit/workflows/test_refuel.py
- [X] T054d [P] [US2] Create test for issue skip after max attempts in tests/unit/workflows/test_refuel.py
- [X] T055 [US2] Run RefuelWorkflow tests: PYTHONPATH=src python -m pytest tests/unit/workflows/test_refuel.py -v

**Checkpoint**: RefuelWorkflow should be fully functional and testable independently

---

## Phase 5: User Story 3 - Test Workflows with Mocked Runners (Priority: P2)

**Goal**: Ensure all runners are injectable and mockable for comprehensive testing

**Independent Test**: Write workflow test using mocked GitRunner, ValidationRunner, GitHubCLIRunner to verify stage sequencing

### Tests for User Story 3

- [X] T056 [P] [US3] Create test fixture for mock_git_runner in tests/fixtures/runners.py
- [X] T057 [P] [US3] Create test fixture for mock_validation_runner in tests/fixtures/runners.py
- [X] T058 [P] [US3] Create test fixture for mock_github_runner in tests/fixtures/runners.py
- [X] T059 [P] [US3] Create test fixture for mock_implementer_agent in tests/fixtures/agents.py
- [X] T060 [P] [US3] Create test fixture for mock_commit_generator in tests/fixtures/agents.py

### Implementation for User Story 3

- [X] T061 [US3] Verify FlyWorkflow constructor accepts all injectable dependencies (FR-020) in src/maverick/workflows/fly.py
- [X] T062 [US3] Verify RefuelWorkflow constructor accepts all injectable dependencies (FR-020) in src/maverick/workflows/refuel.py
- [X] T063 [US3] Add integration test using all mocked runners in tests/integration/workflows/test_fly_e2e.py
- [X] T064 [US3] Add integration test for mocked runner error responses in tests/integration/workflows/test_fly_e2e.py
- [X] T065 [US3] Verify mocked ValidationRunner failure triggers fixer agent in tests/integration/workflows/test_fly_e2e.py
- [X] T066 [US3] Run integration tests: PYTHONPATH=src python -m pytest tests/integration/workflows/ -v

**Checkpoint**: Workflows should be fully testable with mocked dependencies

---

## Phase 6: User Story 4 - Monitor Workflow Progress at Each Stage (Priority: P2)

**Goal**: Verify progress updates emitted at each deterministic step

**Independent Test**: Subscribe to workflow progress events and verify each stage transition emits appropriate updates

### Tests for User Story 4

- [X] T067 [P] [US4] Create test for FlyWorkflowStarted event emission in tests/unit/workflows/test_fly.py
- [X] T068 [P] [US4] Create test for FlyStageStarted/Completed event pairs in tests/unit/workflows/test_fly.py
- [X] T069 [P] [US4] Create test for validation retry progress updates in tests/unit/workflows/test_fly.py
- [X] T070 [P] [US4] Create test for RefuelStarted event with issues_found in tests/unit/workflows/test_refuel.py
- [X] T071 [P] [US4] Create test for IssueProcessingStarted/Completed event pairs in tests/unit/workflows/test_refuel.py

### Implementation for User Story 4

- [X] T072 [US4] Add progress event emission at each stage transition in FlyWorkflow (FR-022) in src/maverick/workflows/fly.py
- [X] T073 [US4] Add validation retry progress updates with attempt counter in src/maverick/workflows/fly.py
- [X] T074 [US4] Add progress event emission at each issue transition in RefuelWorkflow (FR-022) in src/maverick/workflows/refuel.py
- [X] T075 [US4] Add agent completion progress updates with summary info in src/maverick/workflows/fly.py
- [X] T076 [US4] Run progress event tests: PYTHONPATH=src python -m pytest tests/unit/workflows/ -k "progress" -v

**Checkpoint**: All progress events should be emitted correctly

---

## Phase 7: User Story 5 - Agent Tool Permissions are Properly Scoped (Priority: P3)

**Goal**: Verify agents have minimal required permissions

**Independent Test**: Inspect agent configurations and verify allowed_tools lists match defined permissions

### Tests for User Story 5

- [X] T077 [P] [US5] Create test for ImplementerAgent allowed_tools in tests/unit/agents/test_implementer.py
- [X] T078 [P] [US5] Create test for CodeReviewerAgent allowed_tools in tests/unit/agents/test_code_reviewer.py
- [X] T079 [P] [US5] Create test for IssueFixerAgent allowed_tools in tests/unit/agents/test_issue_fixer.py
- [X] T080 [P] [US5] Create test for CommitMessageGenerator has no tools in tests/unit/agents/test_generators.py
- [X] T081 [P] [US5] Create test for PRDescriptionGenerator has no tools in tests/unit/agents/test_generators.py

### Implementation for User Story 5

- [X] T082 [US5] Verify ImplementerAgent uses IMPLEMENTER_TOOLS constant (Read, Write, Edit, Bash, Glob, Grep) in src/maverick/agents/implementer.py
- [X] T083 [US5] Verify CodeReviewerAgent uses CODE_REVIEWER_TOOLS constant (Read, Glob, Grep, Bash) in src/maverick/agents/code_reviewer.py
- [X] T084 [US5] Verify IssueFixerAgent uses ISSUE_FIXER_TOOLS constant (Read, Write, Edit, Bash, Glob, Grep) in src/maverick/agents/issue_fixer.py
- [X] T085 [US5] Verify CommitMessageGenerator uses allowed_tools=[] in src/maverick/agents/generators/commit_message.py
- [X] T086 [US5] Verify PRDescriptionGenerator uses allowed_tools=[] in src/maverick/agents/generators/pr_description.py
- [X] T087 [US5] Add tool permission validation test matrix in tests/unit/agents/test_tool_permissions.py
- [X] T088 [US5] Run agent tool tests: PYTHONPATH=src python -m pytest tests/unit/agents/ -k "tool" -v

**Checkpoint**: All agent tool permissions should be properly scoped

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Final validation and documentation

- [X] T089 [P] Add dry-run mode support (FR-024) in src/maverick/workflows/fly.py
- [X] T090 [P] Add dry-run mode support (FR-024) in src/maverick/workflows/refuel.py
- [X] T090a [P] Create test for FlyWorkflow dry-run mode (logs operations without executing) in tests/unit/workflows/test_fly.py
- [X] T090b [P] Create test for RefuelWorkflow dry-run mode (logs operations without executing) in tests/unit/workflows/test_refuel.py
- [X] T090c [P] Create test verifying dry-run emits same progress events as real run in tests/unit/workflows/test_fly.py
- [X] T091 Run full test suite: PYTHONPATH=src python -m pytest tests/ -v
- [X] T092 Run linting: PYTHONPATH=src ruff check src/maverick/workflows/ src/maverick/runners/git.py
- [X] T093 Run type checking: PYTHONPATH=src mypy src/maverick/workflows/ src/maverick/runners/git.py
- [X] T094 Verify token usage reduction meets SC-001 target (40-60%)
- [X] T095 Run quickstart.md validation checklist

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3-7)**: All depend on Foundational phase completion
  - US1 (FlyWorkflow) and US2 (RefuelWorkflow) can proceed in parallel
  - US3 (Testing) depends on US1 and US2 being complete
  - US4 (Progress) can proceed in parallel with US1/US2
  - US5 (Permissions) can proceed in parallel with US1/US2
- **Polish (Phase 8)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 2 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 3 (P2)**: Depends on US1 and US2 being complete (needs working workflows to test)
- **User Story 4 (P2)**: Can start after Foundational (Phase 2) - Integrated into US1/US2 implementation
- **User Story 5 (P3)**: Can start after Foundational (Phase 2) - Independent of workflow implementation

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- Implementation tasks follow the stage order defined in contracts
- Run validation command after implementation complete
- Story complete before moving to next priority

### Parallel Opportunities

- T003 can run in parallel (export updates)
- T004-T010 git methods can run in parallel (different methods)
- T014-T020 (US1 tests) can run in parallel
- T037-T041 (US2 tests) can run in parallel
- T056-T060 (US3 fixtures) can run in parallel
- T067-T071 (US4 tests) can run in parallel
- T077-T081 (US5 tests) can run in parallel
- T089-T090 (dry-run) can run in parallel
- US1 and US2 implementation can run in parallel after Foundational complete

---

## Parallel Example: Phase 2 - GitRunner Methods

```bash
# Launch all GitRunner method implementations together:
Task: "Implement GitRunner.create_branch() method in src/maverick/runners/git.py"
Task: "Implement GitRunner.checkout() method in src/maverick/runners/git.py"
Task: "Implement GitRunner.commit() method in src/maverick/runners/git.py"
Task: "Implement GitRunner.push() method in src/maverick/runners/git.py"
Task: "Implement GitRunner.diff() method in src/maverick/runners/git.py"
Task: "Implement GitRunner.add() method in src/maverick/runners/git.py"
Task: "Implement GitRunner.status() method in src/maverick/runners/git.py"
```

## Parallel Example: User Story 1 Tests

```bash
# Launch all US1 tests together:
Task: "Create test for INIT stage in tests/unit/workflows/test_fly.py"
Task: "Create test for IMPLEMENTATION stage in tests/unit/workflows/test_fly.py"
Task: "Create test for VALIDATION stage in tests/unit/workflows/test_fly.py"
Task: "Create test for CODE_REVIEW stage in tests/unit/workflows/test_fly.py"
Task: "Create test for PR_CREATION stage in tests/unit/workflows/test_fly.py"
Task: "Create test for progress event emission in tests/unit/workflows/test_fly.py"
Task: "Create test for error handling in tests/unit/workflows/test_fly.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T003)
2. Complete Phase 2: Foundational GitRunner (T004-T013)
3. Complete Phase 3: User Story 1 - FlyWorkflow (T014-T036)
4. **STOP and VALIDATE**: Test FlyWorkflow independently
5. Verify token usage reduction meets 40% target

### Incremental Delivery

1. Complete Setup + Foundational (T001-T013) -> GitRunner ready
2. Add User Story 1 (T014-T036) -> FlyWorkflow complete -> MVP!
3. Add User Story 2 (T037-T055) -> RefuelWorkflow complete
4. Add User Story 3 (T056-T066) -> Full test coverage
5. Add User Story 4 (T067-T076) -> Progress visibility
6. Add User Story 5 (T077-T088) -> Security hardened
7. Complete Polish (T089-T095) -> Production ready

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together (T001-T013)
2. Once Foundational is done:
   - Developer A: User Story 1 (FlyWorkflow)
   - Developer B: User Story 2 (RefuelWorkflow)
   - Developer C: User Story 5 (Permissions) - independent
3. Once US1 + US2 complete:
   - Developer A: User Story 3 (Integration tests)
   - Developer B: User Story 4 (Progress events)
4. All complete Polish phase together

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verify tests fail before implementing
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Avoid: vague tasks, same file conflicts, cross-story dependencies that break independence
