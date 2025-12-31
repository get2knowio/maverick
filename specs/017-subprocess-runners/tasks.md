# Tasks: Subprocess Execution Module

**Input**: Design documents from `/specs/017-subprocess-runners/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, quickstart.md

**Tests**: Included - comprehensive unit tests with mocking per Testing Strategy (research.md Section 12)

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `src/maverick/`, `tests/unit/` at repository root
- Paths follow existing Maverick structure per plan.md

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization, module structure, and exception hierarchy

- [X] T001 Create runners module directory structure at src/maverick/runners/
- [X] T002 [P] Create src/maverick/runners/__init__.py with public exports
- [X] T003 [P] Create src/maverick/runners/parsers/__init__.py with parser exports
- [X] T004 Add runner-specific exceptions to src/maverick/exceptions.py (RunnerError, WorkingDirectoryError, CommandTimeoutError, CommandNotFoundError, GitHubCLINotFoundError, GitHubAuthError)
- [X] T005 [P] Create tests/unit/runners/ directory structure with conftest.py
- [X] T006 [P] Create tests/unit/runners/parsers/ directory structure

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core data models that ALL user stories depend on - MUST complete before any user story

**CRITICAL**: No user story work can begin until this phase is complete

- [X] T007 Create CommandResult frozen dataclass in src/maverick/runners/models.py with returncode, stdout, stderr, duration_ms, timed_out, success property, output property
- [X] T008 Create StreamLine frozen dataclass in src/maverick/runners/models.py with content, stream (Literal), timestamp_ms
- [X] T009 [P] Create ParsedError frozen dataclass in src/maverick/runners/models.py with file, line, message, column, severity, code
- [X] T010 [P] Create ValidationStage frozen dataclass in src/maverick/runners/models.py with name, command, fixable, fix_command, timeout_seconds, __post_init__ validation
- [X] T011 Create StageResult frozen dataclass in src/maverick/runners/models.py with stage_name, passed, output, duration_ms, fix_attempts, errors list
- [X] T012 Create ValidationOutput frozen dataclass in src/maverick/runners/models.py with success, stages list, total_duration_ms, computed properties
- [X] T013 [P] Create GitHubIssue frozen dataclass in src/maverick/runners/models.py with number, title, body, labels, state, assignees, url, __post_init__ validation
- [X] T014 [P] Create PullRequest frozen dataclass in src/maverick/runners/models.py with number, title, body, state, url, head_branch, base_branch, mergeable, draft, __post_init__ validation
- [X] T015 [P] Create CheckStatus frozen dataclass in src/maverick/runners/models.py with name, status, conclusion, url, passed property, pending property
- [X] T016 [P] Create CodeRabbitFinding frozen dataclass in src/maverick/runners/models.py with file, line, severity, message, suggestion, category
- [X] T017 Create CodeRabbitResult frozen dataclass in src/maverick/runners/models.py with findings list, summary, raw_output, warnings list, computed properties
- [X] T018 Write unit tests for all dataclass models in tests/unit/runners/test_models.py (validation, properties, immutability)
- [X] T019 Update src/maverick/runners/__init__.py to export all model classes

**Checkpoint**: Foundation ready - all data models tested and exported. User story implementation can now begin.

---

## Phase 3: User Story 1 - Execute External Commands Safely (Priority: P1)

**Goal**: Run arbitrary shell commands and capture results with timeout handling

**Independent Test**: Run simple commands like `echo "test"` and `ls`, verify returncode, stdout, stderr, and timing are correctly captured

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T020 [P] [US1] Write test_run_simple_command in tests/unit/runners/test_command.py (mock subprocess, verify result fields)
- [X] T021 [P] [US1] Write test_run_command_with_stderr in tests/unit/runners/test_command.py (verify stderr captured separately)
- [X] T022 [P] [US1] Write test_run_command_timeout in tests/unit/runners/test_command.py (verify SIGTERM, grace period, SIGKILL, timed_out flag)
- [X] T023 [P] [US1] Write test_run_command_not_found in tests/unit/runners/test_command.py (verify non-zero returncode, error in stderr)
- [X] T024 [P] [US1] Write test_working_directory_validation in tests/unit/runners/test_command.py (verify WorkingDirectoryError for missing cwd)
- [X] T025 [P] [US1] Write test_environment_merge in tests/unit/runners/test_command.py (verify env inherit + override)

### Implementation for User Story 1

- [X] T026 [US1] Create CommandRunner class in src/maverick/runners/command.py with __init__(cwd, timeout, env)
- [X] T027 [US1] Implement _validate_cwd() method in src/maverick/runners/command.py (fail-fast with WorkingDirectoryError)
- [X] T028 [US1] Implement _build_env() method in src/maverick/runners/command.py (merge parent env with overrides)
- [X] T029 [US1] Implement async run() method in src/maverick/runners/command.py (asyncio.create_subprocess_exec, capture stdout/stderr)
- [X] T030 [US1] Implement timeout handling with graceful escalation in run() (SIGTERM + 2s grace + SIGKILL per FR-004)
- [X] T031 [US1] Add duration_ms timing measurement to run() method
- [X] T032 [US1] Update src/maverick/runners/__init__.py to export CommandRunner

**Checkpoint**: User Story 1 complete - can execute commands safely with timeout handling

---

## Phase 4: User Story 2 - Stream Command Output in Real-Time (Priority: P1)

**Goal**: Yield output lines as async iterator for long-running commands

**Independent Test**: Run command that produces multiple lines over time, verify each line yielded with correct timestamp

### Tests for User Story 2

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T033 [P] [US2] Write test_stream_output_lines in tests/unit/runners/test_command.py (mock readline, verify async iteration)
- [X] T034 [P] [US2] Write test_stream_with_timeout in tests/unit/runners/test_command.py (verify clean termination on timeout)
- [X] T035 [P] [US2] Write test_stream_partial_on_failure in tests/unit/runners/test_command.py (verify partial output preserved)
- [X] T036 [P] [US2] Write test_stream_line_timestamps in tests/unit/runners/test_command.py (verify timestamp_ms increments)
- [X] T036b [P] [US2] Write test_large_output_memory_stable in tests/unit/runners/test_command.py (stream >10MB mock output, verify memory does not accumulate - covers SC-007)

### Implementation for User Story 2

- [X] T037 [US2] Implement async stream() method in src/maverick/runners/command.py returning AsyncIterator[StreamLine]
- [X] T038 [US2] Implement readline loop with timestamp tracking in stream() method
- [X] T039 [US2] Add timeout handling to stream() method with graceful termination
- [X] T040 [US2] Implement wait() method in src/maverick/runners/command.py to get final CommandResult after streaming

**Checkpoint**: User Story 2 complete - can stream output in real-time for long-running commands

---

## Phase 5: User Story 3 - Run Validation Stages Sequentially (Priority: P2)

**Goal**: Execute validation stages with fix attempts and structured error parsing

**Independent Test**: Define 3 validation stages where second fails, verify stage 1 passed, stage 2 failed with output, stage 3 not executed

### Tests for User Story 3

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T041 [P] [US3] Write test_all_stages_pass in tests/unit/runners/test_validation.py (mock all succeed, verify overall success)
- [X] T042 [P] [US3] Write test_stage_failure_stops_execution in tests/unit/runners/test_validation.py (verify subsequent stages skipped)
- [X] T043 [P] [US3] Write test_fixable_stage_retry in tests/unit/runners/test_validation.py (verify fix_command called, stage re-run)
- [X] T044 [P] [US3] Write test_parser_integration in tests/unit/runners/test_validation.py (verify ParsedError populated from output)

### Output Parsers

- [X] T045 [P] [US3] Create OutputParser Protocol in src/maverick/runners/parsers/base.py with can_parse() and parse() methods
- [X] T046 [P] [US3] Implement PythonTracebackParser in src/maverick/runners/parsers/python.py (extract file, line, message from tracebacks)
- [X] T047 [P] [US3] Write tests for PythonTracebackParser in tests/unit/runners/parsers/test_python.py
- [X] T048 [P] [US3] Implement RustCompilerParser in src/maverick/runners/parsers/rust.py (extract file, line, message from rustc output)
- [X] T049 [P] [US3] Write tests for RustCompilerParser in tests/unit/runners/parsers/test_rust.py
- [X] T050 [P] [US3] Implement ESLintJSONParser in src/maverick/runners/parsers/eslint.py (parse JSON format output)
- [X] T051 [P] [US3] Write tests for ESLintJSONParser in tests/unit/runners/parsers/test_eslint.py
- [X] T052 [US3] Create parser registry in src/maverick/runners/parsers/__init__.py with get_parser() function

### Implementation for User Story 3

- [X] T053 [US3] Create ValidationRunner class in src/maverick/runners/validation.py with __init__(stages, cwd, continue_on_failure)
- [X] T054 [US3] Implement async run() method in ValidationRunner that executes stages sequentially
- [X] T055 [US3] Implement _run_stage() method with fix attempt logic (run, check fail, run fix_command, re-run)
- [X] T056 [US3] Integrate parser registry to populate StageResult.errors from output
- [X] T057 [US3] Update src/maverick/runners/__init__.py to export ValidationRunner

**Checkpoint**: User Story 3 complete - can run validation stages with automatic fixes and error parsing

---

## Phase 6: User Story 4 - Get GitHub Issues and Pull Requests (Priority: P2)

**Goal**: Fetch and create GitHub issues/PRs via gh CLI with structured data

**Independent Test**: Mock `gh` CLI output for issue fetch, verify all fields correctly parsed into GitHubIssue

### Tests for User Story 4

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T058 [P] [US4] Write test_get_issue in tests/unit/runners/test_github.py (mock gh output, verify GitHubIssue fields)
- [X] T059 [P] [US4] Write test_list_issues_with_filter in tests/unit/runners/test_github.py (verify label/state filtering)
- [X] T060 [P] [US4] Write test_create_pr in tests/unit/runners/test_github.py (verify gh command args, PullRequest returned)
- [X] T061 [P] [US4] Write test_get_pr_checks in tests/unit/runners/test_github.py (verify CheckStatus list parsing)
- [X] T062 [P] [US4] Write test_gh_not_installed in tests/unit/runners/test_github.py (verify GitHubCLINotFoundError raised)
- [X] T063 [P] [US4] Write test_gh_not_authenticated in tests/unit/runners/test_github.py (verify GitHubAuthError raised)

### Implementation for User Story 4

- [X] T064 [US4] Create GitHubCLIRunner class in src/maverick/runners/github.py with __init__()
- [X] T065 [US4] Implement _check_gh_available() method (raise GitHubCLINotFoundError if gh not found)
- [X] T066 [US4] Implement _check_gh_auth() method (run gh auth status, raise GitHubAuthError if not authenticated)
- [X] T067 [US4] Implement _run_gh_command() helper method for executing gh CLI with JSON output
- [X] T068 [US4] Implement async get_issue(number) method returning GitHubIssue
- [X] T069 [US4] Implement async list_issues(label, state, limit) method returning list[GitHubIssue]
- [X] T070 [US4] Implement async create_pr(title, body, base, head, draft) method returning PullRequest
- [X] T071 [US4] Implement async get_pr(number) method returning PullRequest
- [X] T072 [US4] Implement async get_pr_checks(pr_number) method returning list[CheckStatus]
- [X] T073 [US4] Update src/maverick/runners/__init__.py to export GitHubCLIRunner

**Checkpoint**: User Story 4 complete - can interact with GitHub issues and PRs via gh CLI

---

## Phase 7: User Story 5 - Run CodeRabbit Reviews (Priority: P3)

**Goal**: Run CodeRabbit code review with graceful degradation if not installed

**Independent Test**: Mock CodeRabbit CLI output, verify findings correctly parsed; verify empty result with warning when not installed

### Tests for User Story 5

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T074 [P] [US5] Write test_run_review_success in tests/unit/runners/test_coderabbit.py (mock output, verify CodeRabbitResult)
- [X] T075 [P] [US5] Write test_coderabbit_not_installed in tests/unit/runners/test_coderabbit.py (verify empty result with warning)
- [X] T076 [P] [US5] Write test_review_specific_files in tests/unit/runners/test_coderabbit.py (verify file list passed correctly)
- [X] T077 [P] [US5] Write test_malformed_output_handling in tests/unit/runners/test_coderabbit.py (verify graceful handling of bad JSON)

### Implementation for User Story 5

- [X] T078 [US5] Create CodeRabbitRunner class in src/maverick/runners/coderabbit.py with __init__()
- [X] T079 [US5] Implement async is_available() method to check if CodeRabbit CLI installed
- [X] T080 [US5] Implement _parse_findings() method to extract CodeRabbitFinding list from output
- [X] T081 [US5] Implement async run_review(files) method returning CodeRabbitResult
- [X] T082 [US5] Handle graceful degradation when CodeRabbit not installed (return empty result with warning)
- [X] T083 [US5] Update src/maverick/runners/__init__.py to export CodeRabbitRunner

**Checkpoint**: User Story 5 complete - can run CodeRabbit reviews with graceful fallback

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Final validation, documentation, and integration readiness

- [X] T084 [P] Verify all public classes exported correctly in src/maverick/runners/__init__.py
- [X] T085 [P] Run full test suite for runners module (pytest tests/unit/runners/)
- [X] T086 [P] Run ruff check and ruff format on src/maverick/runners/
- [X] T087 [P] Run mypy type checking on src/maverick/runners/
- [X] T088 Validate quickstart.md examples work with implemented module
- [X] T089 Create integration test placeholder in tests/integration/runners/test_integration.py (marked with pytest.mark.integration)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational phase completion
- **User Story 2 (Phase 4)**: Depends on User Story 1 (extends CommandRunner with stream())
- **User Story 3 (Phase 5)**: Depends on Foundational phase (uses CommandRunner internally)
- **User Story 4 (Phase 6)**: Depends on Foundational phase (uses CommandRunner internally)
- **User Story 5 (Phase 7)**: Depends on Foundational phase (uses CommandRunner internally)
- **Polish (Phase 8)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational - No dependencies on other stories
- **User Story 2 (P1)**: Depends on User Story 1 (adds streaming to CommandRunner)
- **User Story 3 (P2)**: Tests can start after Foundational (mock CommandRunner); implementation requires US1 complete
- **User Story 4 (P2)**: Tests can start after Foundational (mock CommandRunner); implementation requires US1 complete
- **User Story 5 (P3)**: Tests can start after Foundational (mock CommandRunner); implementation requires US1 complete

**Note**: US3, US4, US5 unit tests use mocked subprocess calls and don't require a working CommandRunner. However, their implementations internally use CommandRunner, so US1 should complete before their implementation tasks begin. The test-first approach allows parallel test writing while maintaining correct implementation order.

### Parallel Opportunities

After Foundational phase completes:
- **US3, US4, US5** can all start in parallel (different files, use CommandRunner)
- **US1 must complete before US2** (streaming extends CommandRunner)

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- Parser implementations can run in parallel with each other (T046-T051)
- Model implementation must complete before runner implementation

---

## Parallel Example: User Story 3 Output Parsers

```bash
# Launch all parser implementations in parallel:
Task: "Implement PythonTracebackParser in src/maverick/runners/parsers/python.py"
Task: "Implement RustCompilerParser in src/maverick/runners/parsers/rust.py"
Task: "Implement ESLintJSONParser in src/maverick/runners/parsers/eslint.py"
```

## Parallel Example: User Stories 3, 4, 5 After Foundational

```bash
# After Phase 2 completes, launch tests for US3, US4, US5 in parallel:
Task: "Write test_all_stages_pass in tests/unit/runners/test_validation.py"
Task: "Write test_get_issue in tests/unit/runners/test_github.py"
Task: "Write test_run_review_success in tests/unit/runners/test_coderabbit.py"
```

---

## Implementation Strategy

### MVP First (User Stories 1 + 2 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1 (safe command execution)
4. Complete Phase 4: User Story 2 (streaming output)
5. **STOP and VALIDATE**: Test basic command execution independently
6. MVP delivers: CommandRunner with run() and stream() methods

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 + 2 → Test independently → MVP: Basic command execution
3. Add User Story 3 → Test independently → Validation orchestration
4. Add User Story 4 → Test independently → GitHub integration
5. Add User Story 5 → Test independently → CodeRabbit integration
6. Each story adds value without breaking previous stories

### Parallel Team Strategy

With multiple developers after Foundational:
- Developer A: User Story 1 → User Story 2 (sequential dependency)
- Developer B: User Story 3 (independent - parsers)
- Developer C: User Story 4 (independent - GitHub CLI)
- Developer D: User Story 5 (independent - CodeRabbit)

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verify tests fail before implementing (TDD)
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- All models use frozen dataclasses with slots=True per research.md
- No shell=True in subprocess calls per Constitution VII
