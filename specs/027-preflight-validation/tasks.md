# Tasks: Preflight Validation System

**Input**: Design documents from `/specs/027-preflight-validation/`
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/ ✓

**Tests**: Required per Constitution Principle V (Test-First). Test tasks accompany each implementation phase.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create new module structure and base types

- [x] T001 Create protocols module at src/maverick/runners/protocols.py
- [x] T002 [P] Create preflight exception module at src/maverick/exceptions/preflight.py
- [x] T003 [P] Update src/maverick/runners/**init**.py to export ValidationResult, PreflightResult, ValidatableRunner

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core data types and validator infrastructure that ALL user stories depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T004 Implement ValidationResult frozen dataclass in src/maverick/runners/preflight.py with success, component, errors, warnings, duration_ms fields and to_dict() method
- [x] T005 Implement PreflightResult frozen dataclass in src/maverick/runners/preflight.py with from_results() classmethod and to_dict() method
- [x] T006 Implement PreflightConfig frozen dataclass in src/maverick/runners/preflight.py with timeout_per_check and fail_on_warning fields
- [x] T007 Implement ValidatableRunner Protocol in src/maverick/runners/protocols.py with async validate() method signature
- [x] T008 Implement PreflightValidationError exception in src/maverick/exceptions/preflight.py with result attribute and formatted error message

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Clear Failure Before Work Begins (Priority: P1) 🎯 MVP

**Goal**: Validate all required tools and configurations BEFORE creating any branches or modifying state, providing clear actionable error messages when something is missing.

**Independent Test**: Run a workflow with a deliberately missing tool (e.g., renamed `gh` binary) and verify the workflow fails immediately with a clear message before any git operations occur.

### Implementation for User Story 1

- [x] T009 [P] [US1] Implement GitRunner.validate() method in src/maverick/runners/git.py: check git on PATH, in repository, not in merge/rebase state, user identity configured; handle corrupted git state gracefully; populate duration_ms timing
- [x] T010 [P] [US1] Implement GitHubCLIRunner.validate() method in src/maverick/runners/github.py: check gh on PATH, authenticated via `gh auth status`, required scopes (repo, read:org) via `gh auth status --show-token`; handle expired tokens gracefully; populate duration_ms timing
- [x] T011 [P] [US1] Implement ValidationRunner.validate() method in src/maverick/runners/validation.py: check all configured validation tools from config are on PATH using shutil.which(); handle missing or broken tools; populate duration_ms timing
- [x] T012 [P] [US1] Implement CodeRabbitRunner.validate() method in src/maverick/runners/coderabbit.py: check coderabbit CLI on PATH (failure is WARNING not error since optional); populate duration_ms timing
- [x] T013 [US1] Implement PreflightValidator.run() method in src/maverick/runners/preflight.py with parallel validation using asyncio.gather and per-check timeouts
- [x] T014 [US1] Implement run_preflight() method in src/maverick/workflows/base.py (WorkflowDSLMixin) that: (1) dynamically discovers runners from workflow instance attributes matching ValidatableRunner protocol, (2) validates all discovered runners in parallel, (3) raises PreflightValidationError on any critical failure
- [x] T015 [US1] Integrate preflight validation into FlyWorkflow execute() in src/maverick/workflows/fly.py before any state-changing operations
- [x] T016 [US1] Integrate preflight validation into RefuelWorkflow execute() in src/maverick/workflows/refuel.py before any state-changing operations

**Checkpoint**: At this point, User Story 1 should be fully functional - workflows fail immediately with clear errors when tools are missing

---

## Phase 4: User Story 2 - Aggregated Error Reporting (Priority: P1)

**Goal**: Report ALL missing requirements at once rather than failing on the first error, allowing developers to fix everything in one pass.

**Independent Test**: Remove multiple tools (git, gh, pytest) simultaneously and verify all are reported in a single error message.

### Implementation for User Story 2

- [x] T017 [US2] Enhance PreflightValidator.run() in src/maverick/runners/preflight.py to aggregate all validation results before reporting (ensure asyncio.gather with return_exceptions=True)
- [x] T018 [US2] Enhance PreflightValidationError.\_format_message() in src/maverick/exceptions/preflight.py to list all failed components with remediation steps using rich formatting
- [x] T019 [US2] Add remediation hints to GitRunner.validate() errors in src/maverick/runners/git.py (e.g., "Run: git config --global user.name 'Your Name'")
- [x] T020 [P] [US2] Add remediation hints to GitHubCLIRunner.validate() errors in src/maverick/runners/github.py (e.g., "Install: brew install gh", "Run: gh auth login")
- [x] T021 [P] [US2] Add remediation hints to ValidationRunner.validate() errors in src/maverick/runners/validation.py (e.g., "Install: pip install ruff")

**Checkpoint**: At this point, User Stories 1 AND 2 should both work - multiple errors reported together with actionable hints

---

## Phase 5: User Story 3 - Validation in Dry-Run Mode (Priority: P2)

**Goal**: Ensure preflight validation runs even in `dry_run` mode so developers can verify environment before committing to a real run.

**Independent Test**: Run `maverick fly --dry-run` with a missing tool and verify the validation error appears.

### Implementation for User Story 3

- [x] T022 [US3] Ensure run_preflight() in src/maverick/workflows/base.py executes regardless of dry_run flag
- [x] T023 [US3] Verify FlyWorkflow calls run_preflight() before checking dry_run mode in src/maverick/workflows/fly.py
- [x] T024 [US3] Verify RefuelWorkflow calls run_preflight() before checking dry_run mode in src/maverick/workflows/refuel.py

**Checkpoint**: At this point, User Stories 1, 2, AND 3 should all work - preflight runs in dry-run mode

---

## Phase 6: User Story 4 - Fast Parallel Validation (Priority: P2)

**Goal**: Complete preflight validation quickly (<2 seconds when all tools present) by running checks in parallel with configurable timeouts.

**Independent Test**: Measure preflight completion time with all tools present, targeting completion in under 2 seconds.

### Implementation for User Story 4

- [x] T025 [US4] Implement per-check timeout wrapper in PreflightValidator using asyncio.wait_for() in src/maverick/runners/preflight.py
- [x] T026 [US4] Handle asyncio.TimeoutError in PreflightValidator converting to ValidationResult with timeout message in src/maverick/runners/preflight.py
- [x] T027 [US4] Add timing instrumentation to PreflightValidator.run() populating total_duration_ms and per-check duration_ms in src/maverick/runners/preflight.py

**Checkpoint**: Preflight completes in <2 seconds when all tools present, with 5s timeout per check

---

## Phase 7: User Story 5 - Extensible Validation for Custom Tools (Priority: P3)

**Goal**: Allow project maintainers to add custom validation checks via maverick.toml configuration.

**Independent Test**: Configure a custom validation tool in project config and verify it's included in preflight checks.

### Implementation for User Story 5

- [x] T028 [US5] Add PreflightConfig schema to MaverickConfig for custom tool validation in src/maverick/config.py
- [x] T029 [US5] Implement custom tool validation loading in PreflightValidator based on maverick.toml [preflight.custom_tools] section in src/maverick/runners/preflight.py
- [x] T030 [US5] Document custom tool validation configuration in docs/ or README section

**Checkpoint**: All user stories should now be independently functional

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [x] T031 [P] Update src/maverick/runners/**init**.py with all new exports (ValidationResult, PreflightResult, ValidatableRunner, PreflightValidator)
- [x] T032 [P] Update src/maverick/exceptions/**init**.py with PreflightValidationError export
- [x] T033 Add type hints verification for all new modules using mypy
- [x] T034 Run quickstart.md validation scenarios manually to verify end-to-end behavior
- [x] T035 Code cleanup: ensure all validate() methods follow consistent error message patterns

---

## Phase 9: Testing (Required by Constitution)

**Purpose**: Constitution Principle V mandates tests for all public classes and functions

### Unit Tests

- [x] T036 [P] Create tests/unit/runners/test_preflight.py with tests for ValidationResult, PreflightResult, PreflightConfig dataclasses
- [x] T037 [P] Create tests/unit/runners/test_protocols.py with protocol compliance tests for ValidatableRunner
- [x] T038 [P] Add validate() tests to tests/unit/runners/test_git.py for GitRunner.validate()
- [x] T039 [P] Add validate() tests to tests/unit/runners/test_github.py for GitHubCLIRunner.validate()
- [x] T040 [P] Add validate() tests to tests/unit/runners/test_validation.py for ValidationRunner.validate()
- [x] T041 [P] Add validate() tests to tests/unit/runners/test_coderabbit.py for CodeRabbitRunner.validate()
- [x] T042 Add PreflightValidator.run() tests to tests/unit/runners/test_preflight.py covering parallel execution, timeout handling, and error aggregation
- [x] T043 Add run_preflight() tests to tests/unit/workflows/test_base.py for WorkflowDSLMixin.run_preflight()

### Integration Tests

- [x] T044 Create tests/integration/test_preflight_integration.py with end-to-end preflight tests using mock runners
- [x] T045 Add preflight failure scenario tests to tests/integration/test_fly_workflow.py
- [x] T046 Add preflight failure scenario tests to tests/integration/test_refuel_workflow.py

**Checkpoint**: All new public classes and methods have test coverage per Constitution Principle V

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phases 3-7)**: All depend on Foundational phase completion
  - User stories can proceed sequentially in priority order (P1 → P2 → P3)
  - US1 and US2 are both P1 and should be implemented together
- **Polish (Phase 8)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 2 (P1)**: Can start after Foundational (Phase 2) - Enhances US1 but independently testable
- **User Story 3 (P2)**: Depends on US1 being complete (needs run_preflight() to exist)
- **User Story 4 (P2)**: Can start after Foundational (Phase 2) - Enhances PreflightValidator independently
- **User Story 5 (P3)**: Can start after Foundational (Phase 2) - Extends validation system

### Within Each User Story

- Models/dataclasses before services
- Core implementation before workflow integration
- Each runner's validate() can be implemented in parallel with other runners
- Story complete before moving to next priority

### Parallel Opportunities

**Setup (Phase 1)**:

```bash
# All can run in parallel:
T001 Create protocols module
T002 Create preflight exception module
T003 Update runners __init__.py
```

**User Story 1 - Runner Implementations**:

```bash
# All runner validate() methods can run in parallel:
T009 GitRunner.validate()
T010 GitHubCLIRunner.validate()
T011 ValidationRunner.validate()
T012 CodeRabbitRunner.validate()
```

**User Story 2 - Remediation Hints**:

```bash
# Remediation hint tasks can run in parallel:
T020 GitHubCLIRunner remediation hints
T021 ValidationRunner remediation hints
```

---

## Implementation Strategy

### MVP First (User Stories 1 + 2)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1 (Clear Failure)
4. Complete Phase 4: User Story 2 (Aggregated Errors)
5. **STOP and VALIDATE**: Test preflight with missing tools
6. Deploy/demo if ready - core value delivered!

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. Add User Story 1 + 2 → Test with missing tools → Deploy (MVP!)
3. Add User Story 3 → Test dry-run mode → Deploy
4. Add User Story 4 → Test performance → Deploy
5. Add User Story 5 → Test custom tools → Deploy
6. Each story adds value without breaking previous stories

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Existing runners (GitRunner, GitHubCLIRunner, ValidationRunner, CodeRabbitRunner) need validate() method ADDED - do not replace existing functionality
- All validate() methods must be async and return ValidationResult
- All validate() methods must NOT raise exceptions - failures go in ValidationResult.errors
