# Tasks: CLI Entry Point

**Input**: Design documents from `/specs/014-cli-entry-point/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Tests are included as specified by Constitution Principle V (Test-First) in plan.md.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create CLI utilities module structure and core components

- [x] T001 Create CLI module directory structure at src/maverick/cli/
- [x] T002 [P] Create src/maverick/cli/__init__.py with public exports
- [x] T003 [P] Create tests/unit/cli/__init__.py for test module

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core CLI infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

### Core Data Models

- [x] T004 [P] Implement ExitCode enum in src/maverick/cli/context.py
- [x] T005 [P] Implement OutputFormat enum in src/maverick/cli/output.py
- [x] T006 [P] Implement DependencyStatus dataclass in src/maverick/cli/validators.py

### Core Utilities

- [x] T007 Implement CLIContext dataclass with use_tui property in src/maverick/cli/context.py
- [x] T008 Implement async_command decorator in src/maverick/cli/context.py
- [x] T009 [P] Implement check_dependencies() function in src/maverick/cli/validators.py
- [x] T010 [P] Implement check_git_auth() function in src/maverick/cli/validators.py
- [x] T011 [P] Implement output formatting helpers in src/maverick/cli/output.py

### Command Input Models

- [x] T012 [P] Implement FlyCommandInputs dataclass in src/maverick/cli/context.py
- [x] T013 [P] Implement RefuelCommandInputs dataclass in src/maverick/cli/context.py
- [x] T014 [P] Implement ReviewCommandInputs dataclass in src/maverick/cli/context.py

### Foundation Tests

- [x] T015 [P] Unit tests for ExitCode and CLIContext in tests/unit/cli/test_context.py
- [x] T016 [P] Unit tests for OutputFormat in tests/unit/cli/test_output.py
- [x] T017 [P] Unit tests for DependencyStatus and validators in tests/unit/cli/test_validators.py

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 6 - Use Global Options (Priority: P1) 🎯 MVP

**Goal**: Enable developers to control Maverick's behavior across all commands with `--config`, `--verbose`, `--quiet`, and `--no-tui` options

**Independent Test**: Run any command with `--verbose` and verify increased output detail. Run `maverick --version` and `maverick --help` to verify basic CLI works.

**Why First**: Global options are the foundation for all other commands. The CLI group must be properly configured before commands can use the context.

### Tests for User Story 6

- [x] T018 [P] [US6] Test --config option loading in tests/unit/cli/test_main.py
- [x] T019 [P] [US6] Test --verbose stacking (-v, -vv, -vvv) in tests/unit/cli/test_main.py
- [x] T020 [P] [US6] Test --quiet suppression in tests/unit/cli/test_main.py
- [x] T021 [P] [US6] Test --no-tui flag in tests/unit/cli/test_main.py
- [x] T022 [P] [US6] Test --version output in tests/unit/cli/test_main.py
- [x] T023 [P] [US6] Test --help output in tests/unit/cli/test_main.py
- [x] T024 [P] [US6] Test quiet takes precedence over verbose in tests/unit/cli/test_main.py
- [x] T024a [P] [US6] Test piped input detection disables interactive prompts in tests/unit/cli/test_main.py

### Implementation for User Story 6

- [x] T025 [US6] Extend CLI group with global options (--config, --verbose, --quiet, --no-tui) in src/maverick/main.py
- [x] T026 [US6] Implement CLIContext creation and storage in Click context in src/maverick/main.py
- [x] T027 [US6] Add --version option with version from __init__.py in src/maverick/main.py
- [x] T028 [US6] Implement verbosity level to logging configuration in src/maverick/main.py
- [x] T029 [US6] Add TTY and pipe auto-detection logic (stdin.isatty, stdout.isatty) in CLI group callback in src/maverick/main.py

**Checkpoint**: Global options work - `maverick --help`, `maverick --version`, `maverick -vvv` all work correctly

---

## Phase 4: User Story 1 - Run Fly Workflow from Command Line (Priority: P1)

**Goal**: Enable developers to execute the FlyWorkflow for a specific feature branch via `maverick fly <branch>`

**Independent Test**: Run `maverick fly <branch>` with a valid spec and verify workflow execution starts. Test `--dry-run` to show planned actions.

### Tests for User Story 1

- [x] T030 [P] [US1] Test fly command with valid branch in tests/unit/cli/test_main.py
- [x] T031 [P] [US1] Test fly --task-file option in tests/unit/cli/test_main.py
- [x] T032 [P] [US1] Test fly --skip-review option in tests/unit/cli/test_main.py
- [x] T033 [P] [US1] Test fly --skip-pr option in tests/unit/cli/test_main.py
- [x] T034 [P] [US1] Test fly --dry-run option in tests/unit/cli/test_main.py
- [x] T035 [P] [US1] Test fly with non-existent branch error in tests/unit/cli/test_main.py
- [x] T036 [P] [US1] Test fly keyboard interrupt handling in tests/unit/cli/test_main.py

### Implementation for User Story 1

- [x] T037 [US1] Implement fly command with branch argument in src/maverick/main.py
- [x] T038 [US1] Add fly command options (--task-file, --skip-review, --skip-pr, --dry-run) in src/maverick/main.py
- [x] T039 [US1] Implement branch validation in fly command in src/maverick/main.py
- [x] T040 [US1] Implement task file detection and validation in fly command in src/maverick/main.py
- [x] T041 [US1] Integrate FlyWorkflow execution with TUI/headless mode in src/maverick/main.py
- [x] T042 [US1] Implement dry-run output showing planned actions in src/maverick/main.py
- [x] T043 [US1] Add keyboard interrupt handling with exit code 130 in fly command in src/maverick/main.py
- [x] T044 [US1] Add error handling for MaverickError hierarchy in fly command in src/maverick/main.py

**Checkpoint**: `maverick fly feature-branch` executes workflow and shows progress

---

## Phase 5: User Story 2 - Run Refuel Workflow for Tech Debt (Priority: P1)

**Goal**: Enable developers to address tech debt issues via `maverick refuel` with customizable label and limit options

**Independent Test**: Run `maverick refuel --dry-run` to list matching issues without processing

### Tests for User Story 2

- [x] T045 [P] [US2] Test refuel command default behavior in tests/unit/cli/test_main.py
- [x] T046 [P] [US2] Test refuel --label option in tests/unit/cli/test_main.py
- [x] T047 [P] [US2] Test refuel --limit option in tests/unit/cli/test_main.py
- [x] T048 [P] [US2] Test refuel --sequential flag in tests/unit/cli/test_main.py
- [x] T049 [P] [US2] Test refuel --dry-run option in tests/unit/cli/test_main.py
- [x] T050 [P] [US2] Test refuel keyboard interrupt handling in tests/unit/cli/test_main.py

### Implementation for User Story 2

- [x] T051 [US2] Implement refuel command in src/maverick/main.py
- [x] T052 [US2] Add refuel options (--label, --limit, --parallel/--sequential, --dry-run) in src/maverick/main.py
- [x] T053 [US2] Implement GitHub CLI authentication check in refuel command in src/maverick/main.py
- [x] T054 [US2] Integrate RefuelWorkflow execution with TUI/headless mode in src/maverick/main.py
- [x] T055 [US2] Implement dry-run output listing matching issues in src/maverick/main.py
- [x] T056 [US2] Add keyboard interrupt and error handling in refuel command in src/maverick/main.py

**Checkpoint**: `maverick refuel --dry-run` lists tech-debt issues correctly

---

## Phase 6: User Story 3 - Review a Pull Request (Priority: P2)

**Goal**: Enable developers to get AI-powered review of a pull request via `maverick review <pr-number>`

**Independent Test**: Run `maverick review <pr-number> --output json` on an existing PR and verify JSON output

### Tests for User Story 3

- [x] T057 [P] [US3] Test review command with valid PR number in tests/unit/cli/test_main.py
- [x] T058 [P] [US3] Test review --fix option in tests/unit/cli/test_main.py
- [x] T059 [P] [US3] Test review --output json option in tests/unit/cli/test_main.py
- [x] T060 [P] [US3] Test review --output markdown option in tests/unit/cli/test_main.py
- [x] T061 [P] [US3] Test review with non-existent PR error in tests/unit/cli/test_main.py

### Implementation for User Story 3

- [x] T062 [US3] Implement review command with pr-number argument in src/maverick/main.py
- [x] T063 [US3] Add review options (--fix/--no-fix, --output) in src/maverick/main.py
- [x] T064 [US3] Implement PR validation in review command in src/maverick/main.py
- [x] T064a [US3] Validate CodeReviewerAgent interface compatibility (review_pr method exists, returns ReviewResult) in src/maverick/main.py
- [x] T065 [US3] Integrate CodeReviewerAgent.review_pr() execution with async_command wrapper in src/maverick/main.py
- [x] T066 [US3] Implement JSON output formatting in review command in src/maverick/main.py
- [x] T067 [US3] Implement markdown output formatting in review command in src/maverick/main.py
- [x] T068 [US3] Add error handling for PR not found in review command in src/maverick/main.py

**Checkpoint**: `maverick review 123 --output json` outputs valid JSON review results

---

## Phase 7: User Story 4 - Manage Configuration (Priority: P2)

**Goal**: Enable developers to customize Maverick via `maverick config` subcommands (init, show, edit, validate)

**Independent Test**: Run `maverick config init` in a new project and verify a valid configuration file is created

### Tests for User Story 4

- [x] T069 [P] [US4] Test config init creates default file in tests/unit/cli/test_main.py
- [x] T070 [P] [US4] Test config init --force overwrites in tests/unit/cli/test_main.py
- [x] T071 [P] [US4] Test config show displays YAML in tests/unit/cli/test_main.py
- [x] T072 [P] [US4] Test config show --format json in tests/unit/cli/test_main.py
- [x] T073 [P] [US4] Test config edit opens editor in tests/unit/cli/test_main.py
- [x] T074 [P] [US4] Test config validate with valid config in tests/unit/cli/test_main.py
- [x] T075 [P] [US4] Test config validate with invalid config in tests/unit/cli/test_main.py

### Implementation for User Story 4

- [x] T076 [US4] Implement config command group in src/maverick/main.py
- [x] T077 [US4] Implement config init subcommand with --force option in src/maverick/main.py
- [x] T078 [US4] Implement config show subcommand with --format option in src/maverick/main.py
- [x] T079 [US4] Implement config edit subcommand with --user/--project options in src/maverick/main.py
- [x] T080 [US4] Implement config validate subcommand with --file option in src/maverick/main.py
- [x] T081 [US4] Generate default config template for config init in src/maverick/main.py

**Checkpoint**: `maverick config init && maverick config validate` creates and validates config

---

## Phase 8: User Story 5 - Check Project Status (Priority: P3)

**Goal**: Enable developers to understand project state via `maverick status`

**Independent Test**: Run `maverick status` in a project and verify branch and task information is displayed

### Tests for User Story 5

- [x] T082 [P] [US5] Test status command displays branch info in tests/unit/cli/test_main.py
- [x] T083 [P] [US5] Test status command with pending tasks in tests/unit/cli/test_main.py
- [x] T084 [P] [US5] Test status --format json option in tests/unit/cli/test_main.py
- [x] T085 [P] [US5] Test status in non-git directory error in tests/unit/cli/test_main.py

### Implementation for User Story 5

- [x] T086 [US5] Implement status command in src/maverick/main.py
- [x] T087 [US5] Add status --format option (text, json) in src/maverick/main.py
- [x] T088 [US5] Implement git branch detection in status command in src/maverick/main.py
- [x] T089 [US5] Implement pending tasks detection in status command in src/maverick/main.py
- [x] T090 [US5] Implement recent workflow history display in status command in src/maverick/main.py
- [x] T091 [US5] Implement JSON output formatting for status command in src/maverick/main.py

**Checkpoint**: `maverick status` shows branch, tasks, and history

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

### Integration Tests

- [x] T092 [P] Integration test for fly workflow end-to-end in tests/integration/cli/test_cli_commands.py
- [x] T093 [P] Integration test for refuel workflow end-to-end in tests/integration/cli/test_cli_commands.py
- [x] T094 [P] Integration test for review command end-to-end in tests/integration/cli/test_cli_commands.py
- [x] T095 [P] Integration test for config subcommands in tests/integration/cli/test_cli_commands.py

### Final Polish

- [x] T096 Update src/maverick/cli/__init__.py with all public exports
- [x] T097 Verify all commands appear in maverick --help output
- [x] T098 Run quickstart.md verification checklist
- [x] T099 Verify exit codes match contract specification
- [x] T100 Verify error messages match contract error handling format
- [x] T101 Verify CLI startup time is under 500ms per NFR-001 using time measurement in tests/integration/cli/test_cli_commands.py

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Story 6 (Phase 3)**: Depends on Foundational - MUST complete first (global options needed by all commands)
- **User Stories 1-2 (Phases 4-5)**: Depend on User Story 6 completion - Both P1, can run in parallel
- **User Stories 3-4 (Phases 6-7)**: Depend on User Story 6 - Both P2, can run in parallel
- **User Story 5 (Phase 8)**: Depends on User Story 6 - P3, lowest priority
- **Polish (Phase 9)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 6 (Global Options)**: Foundation for all other stories - MUST complete first
- **User Story 1 (Fly)**: Depends on US6, no other story dependencies
- **User Story 2 (Refuel)**: Depends on US6, no other story dependencies
- **User Story 3 (Review)**: Depends on US6, no other story dependencies
- **User Story 4 (Config)**: Depends on US6, no other story dependencies
- **User Story 5 (Status)**: Depends on US6, no other story dependencies

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- CLI command stub before options
- Options before validation
- Validation before workflow integration
- Workflow integration before error handling
- Story complete before moving to next priority

### Parallel Opportunities

- All Setup tasks (T001-T003) can run sequentially (directory creation first)
- All Foundational tasks marked [P] can run in parallel within Phase 2
- Once User Story 6 completes:
  - User Stories 1 and 2 can run in parallel (both P1)
  - User Stories 3 and 4 can run in parallel (both P2)
- All tests for a user story marked [P] can run in parallel
- All integration tests marked [P] can run in parallel

---

## Parallel Example: Foundational Phase

```bash
# Launch all data models in parallel:
Task: "Implement ExitCode enum in src/maverick/cli/context.py"
Task: "Implement OutputFormat enum in src/maverick/cli/output.py"
Task: "Implement DependencyStatus dataclass in src/maverick/cli/validators.py"

# Then launch command input models in parallel:
Task: "Implement FlyCommandInputs dataclass in src/maverick/cli/context.py"
Task: "Implement RefuelCommandInputs dataclass in src/maverick/cli/context.py"
Task: "Implement ReviewCommandInputs dataclass in src/maverick/cli/context.py"

# Then launch all foundation tests in parallel:
Task: "Unit tests for ExitCode and CLIContext in tests/unit/cli/test_context.py"
Task: "Unit tests for OutputFormat in tests/unit/cli/test_output.py"
Task: "Unit tests for DependencyStatus and validators in tests/unit/cli/test_validators.py"
```

---

## Parallel Example: User Stories 1 and 2 (P1 Priority)

After User Story 6 completes, both can run in parallel:

```bash
# Developer A works on User Story 1 (Fly):
Task: "Test fly command with valid branch in tests/unit/cli/test_main.py"
Task: "Implement fly command with branch argument in src/maverick/main.py"

# Developer B works on User Story 2 (Refuel):
Task: "Test refuel command default behavior in tests/unit/cli/test_main.py"
Task: "Implement refuel command in src/maverick/main.py"
```

---

## Implementation Strategy

### MVP First (User Story 6 → User Story 1)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 6 (Global Options) - CRITICAL for all commands
4. Complete Phase 4: User Story 1 (Fly)
5. **STOP and VALIDATE**: `maverick fly feature-branch --dry-run` works
6. Deploy/demo if ready - developers can now run fly workflow from CLI

### Incremental Delivery

1. Complete Setup + Foundational + US6 → CLI framework ready
2. Add User Story 1 (Fly) → Test independently → Core workflow accessible via CLI
3. Add User Story 2 (Refuel) → Test independently → Tech debt workflow available
4. Add User Story 3 (Review) → Test independently → PR review available
5. Add User Story 4 (Config) → Test independently → Configuration management
6. Add User Story 5 (Status) → Test independently → Full CLI complete
7. Each story adds value without breaking previous stories

### Suggested MVP Scope

- **Phase 1**: Setup (T001-T003)
- **Phase 2**: Foundational (T004-T017)
- **Phase 3**: User Story 6 - Global Options (T018-T029)
- **Phase 4**: User Story 1 - Fly Command (T030-T044)

This delivers a functional CLI that can run the primary FlyWorkflow with proper global options.

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verify tests fail before implementing
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- User Story 6 (Global Options) is ordered first because all commands depend on CLIContext
