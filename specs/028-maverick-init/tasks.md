# Tasks: Unified Maverick Init with Claude-Powered Detection

**Input**: Design documents from `/specs/028-maverick-init/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Not explicitly requested in feature specification. Unit tests included as integral part of constitution compliance (Principle V: Test-First).

**Organization**: Tasks grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `src/maverick/`, `tests/unit/`, `tests/integration/` at repository root

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and exception hierarchy

- [X] T001 Create init package structure with `src/maverick/init/__init__.py`
- [X] T002 [P] Create exception hierarchy in `src/maverick/exceptions/init.py` (InitError, PrerequisiteError, DetectionError, ConfigExistsError, ConfigWriteError, AnthropicAPIError)
- [X] T003 [P] Create enums and constants in `src/maverick/init/models.py` (ProjectType, DetectionConfidence, PreflightStatus, MARKER_FILE_MAP)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core data models and utilities needed by ALL user stories

**CRITICAL**: No user story work can begin until this phase is complete

- [X] T004 Implement frozen dataclasses in `src/maverick/init/models.py`: ProjectMarker, ValidationCommands, PrerequisiteCheck, GitRemoteInfo
- [X] T005 Implement frozen dataclasses in `src/maverick/init/models.py`: ProjectDetectionResult, InitPreflightResult
- [X] T006 Implement Pydantic models in `src/maverick/init/models.py`: InitGitHubConfig, InitValidationConfig, InitModelConfig, InitConfig
- [X] T007 Implement InitResult frozen dataclass in `src/maverick/init/models.py`
- [X] T008 [P] Implement VALIDATION_DEFAULTS constant mapping ProjectType to ValidationCommands in `src/maverick/init/models.py`
- [X] T009 [P] Create unit tests for models in `tests/unit/init/test_models.py`

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 1 - First-Time Project Initialization (Priority: P1)

**Goal**: User runs `maverick init` to validate prerequisites, detect project type via Claude, and generate maverick.yaml

**Independent Test**: Run `maverick init` in a git repo with valid prerequisites to generate working config

### Implementation for User Story 1

- [X] T010 [P] [US1] Implement git_parser module with `parse_git_remote()` in `src/maverick/init/git_parser.py`
- [X] T011 [P] [US1] Implement `check_git_installed()` async function in `src/maverick/init/prereqs.py`
- [X] T012 [P] [US1] Implement `check_in_git_repo()` async function in `src/maverick/init/prereqs.py`
- [X] T013 [P] [US1] Implement `check_gh_installed()` async function in `src/maverick/init/prereqs.py`
- [X] T014 [P] [US1] Implement `check_gh_authenticated()` async function in `src/maverick/init/prereqs.py`
- [X] T015 [P] [US1] Implement `check_anthropic_key_set()` sync function in `src/maverick/init/prereqs.py`
- [X] T016 [US1] Implement `check_anthropic_api_accessible()` async function using Claude SDK query in `src/maverick/init/prereqs.py`
- [X] T017 [US1] Implement `verify_prerequisites()` orchestrator in `src/maverick/init/prereqs.py`
- [X] T018 [P] [US1] Implement `find_marker_files()` in `src/maverick/init/detector.py`
- [X] T019 [P] [US1] Implement `build_detection_context()` in `src/maverick/init/detector.py`
- [X] T020 [US1] Implement `detect_project_type()` async function with Claude SDK query in `src/maverick/init/detector.py`
- [X] T021 [US1] Implement `get_validation_commands()` in `src/maverick/init/detector.py`
- [X] T022 [P] [US1] Implement `generate_config()` in `src/maverick/init/config_generator.py`
- [X] T023 [P] [US1] Implement `write_config()` with force handling in `src/maverick/init/config_generator.py`
- [X] T024 [US1] Implement `run_init()` main entry point in `src/maverick/init/__init__.py`
- [X] T025 [US1] Implement Click command `init` with output formatting in `src/maverick/cli/commands/init.py`
- [X] T026 [US1] Register init command in CLI main group in `src/maverick/main.py`
- [X] T027 [P] [US1] Create unit tests for prereqs module in `tests/unit/init/test_prereqs.py`
- [X] T028 [P] [US1] Create unit tests for detector module in `tests/unit/init/test_detector.py`
- [X] T029 [P] [US1] Create unit tests for config_generator module in `tests/unit/init/test_config_generator.py`
- [X] T030 [P] [US1] Create unit tests for git_parser module in `tests/unit/init/test_git_parser.py`
- [X] T031 [US1] Create integration test for full init flow in `tests/integration/test_init_command.py` (include <30s performance assertion per SC-001)

**Checkpoint**: User Story 1 complete - `maverick init` works end-to-end

---

## Phase 4: User Story 2 - Preflight API Validation (Priority: P2)

**Goal**: `maverick fly` and `maverick refuel` validate Anthropic API access before workflow starts

**Independent Test**: Run `maverick fly` with valid/invalid API credentials and verify preflight check behavior

### Implementation for User Story 2

- [X] T032 [US2] Implement AnthropicAPIValidator dataclass in `src/maverick/runners/preflight.py`
- [ ] T033 [US2] Integrate AnthropicAPIValidator into FlyWorkflow in `src/maverick/workflows/fly/workflow.py`
- [ ] T034 [US2] Integrate AnthropicAPIValidator into RefuelWorkflow in `src/maverick/workflows/refuel/workflow.py`
- [X] T035 [P] [US2] Create unit tests for AnthropicAPIValidator in `tests/unit/runners/test_preflight_api.py`
- [ ] T036 [US2] Create integration test for workflow preflight with API validation in `tests/integration/test_preflight_api.py`

**Checkpoint**: User Story 2 complete - workflows block on API access failure

---

## Phase 5: User Story 3 - Override Auto-Detection (Priority: P3)

**Goal**: Users can use `--type`, `--no-detect`, and `--force` flags to override default behavior

**Independent Test**: Run `maverick init --type python` in any project and verify Python defaults applied

### Implementation for User Story 3

- [X] T037 [US3] Add `--type` choice option to init command in `src/maverick/cli/commands/init.py`
- [X] T038 [US3] Add `--no-detect` flag to init command in `src/maverick/cli/commands/init.py`
- [X] T039 [US3] Update `run_init()` to handle type_override and use_claude flags in `src/maverick/init/__init__.py`
- [X] T040 [US3] Update `detect_project_type()` to support override_type parameter in `src/maverick/init/detector.py`
- [X] T041 [P] [US3] Add unit tests for --type flag behavior in `tests/unit/init/test_cli_flags.py`
- [X] T042 [P] [US3] Add unit tests for --no-detect flag behavior in `tests/unit/init/test_cli_flags.py`
- [X] T043 [US3] Add integration test for override scenarios in `tests/integration/test_init_command.py` (combined with T031)

**Checkpoint**: User Story 3 complete - manual override options work

---

## Phase 6: User Story 4 - Deprecation Path (Priority: P4)

**Goal**: `maverick config init` shows deprecation warning and delegates to new `maverick init`

**Independent Test**: Run `maverick config init` and verify warning message appears

### Implementation for User Story 4

- [ ] T044 [US4] Update `config init` command to show deprecation warning in `src/maverick/cli/commands/config.py`
- [ ] T045 [US4] Delegate `config init` to new `init` command via ctx.invoke in `src/maverick/cli/commands/config.py`
- [ ] T046 [US4] Add unit test for deprecation warning in `tests/unit/cli/test_config_deprecation.py`

**Checkpoint**: User Story 4 complete - deprecation path works

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: API key redaction, verbose output, documentation

- [X] T047 [P] Implement `redact_api_key()` utility showing prefix + last 4 chars in `src/maverick/init/prereqs.py`
- [X] T048 [P] Add verbose output mode support to init command in `src/maverick/cli/commands/init.py`
- [X] T049 [P] Update init package exports in `src/maverick/init/__init__.py`
- [X] T050 Run `make check` to verify lint, typecheck, and test pass
- [ ] T051 Run quickstart.md validation scenarios manually

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup - BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational - primary functionality
- **User Story 2 (Phase 4)**: Depends on Foundational; can run in parallel with US1
- **User Story 3 (Phase 5)**: Depends on US1 completion (extends init command)
- **User Story 4 (Phase 6)**: Depends on US1 completion (delegates to init)
- **Polish (Phase 7)**: Depends on all user stories

### User Story Dependencies

- **User Story 1 (P1)**: Independent after Foundational - implements core init
- **User Story 2 (P2)**: Independent after Foundational - implements preflight
- **User Story 3 (P3)**: Extends US1 - adds override flags to existing command
- **User Story 4 (P4)**: Extends US1 - adds deprecation to existing config command

### Within Each User Story

- Models before functions using them
- Prereqs and detector before orchestrator (`run_init`)
- Core implementation before CLI command
- Unit tests can run in parallel with implementation
- Integration tests after implementation complete

### Parallel Opportunities

**Phase 2 (Foundational)**:
```
T004 ─┬─ T005 ─┬─ T006 ─── T007
      │        │
T008 ─┘        └─ T009
```

**Phase 3 (US1) - Prerequisites**:
```
T011 ─┬─ T012 ─┬─ T013 ─┬─ T014 ─┬─ T015 ─── T016 ─── T017
      │        │        │        │
T010 ─┘        └────────┴────────┘
```

**Phase 3 (US1) - Detection + Config**:
```
T018 ─┬─ T019 ─── T020 ─── T021
      │
T022 ─┼─ T023
      │
T024 ─┴─── T025 ─── T026
```

**Phase 3 (US1) - Tests**:
```
T027 ─┬─ T028 ─┬─ T029 ─┬─ T030 ─── T031
      │        │        │
      └────────┴────────┘
```

---

## Parallel Example: Phase 3 Setup Tasks

```bash
# Launch all prereq check implementations together:
Task: "Implement check_git_installed() in src/maverick/init/prereqs.py"
Task: "Implement check_in_git_repo() in src/maverick/init/prereqs.py"
Task: "Implement check_gh_installed() in src/maverick/init/prereqs.py"
Task: "Implement check_gh_authenticated() in src/maverick/init/prereqs.py"
Task: "Implement check_anthropic_key_set() in src/maverick/init/prereqs.py"

# Launch all unit test files together (after implementation):
Task: "Create unit tests for prereqs module in tests/unit/init/test_prereqs.py"
Task: "Create unit tests for detector module in tests/unit/init/test_detector.py"
Task: "Create unit tests for config_generator module in tests/unit/init/test_config_generator.py"
Task: "Create unit tests for git_parser module in tests/unit/init/test_git_parser.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T003)
2. Complete Phase 2: Foundational (T004-T009)
3. Complete Phase 3: User Story 1 (T010-T031)
4. **STOP and VALIDATE**: Test `maverick init` end-to-end
5. Delivers immediate value: working init command

### Incremental Delivery

1. Complete Setup + Foundational → Core models ready
2. Add User Story 1 → `maverick init` works → MVP!
3. Add User Story 2 → Workflow preflight validation
4. Add User Story 3 → Override flags for power users
5. Add User Story 4 → Smooth migration for existing users

### Parallel Team Strategy

With multiple developers:
1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1 (core init)
   - Developer B: User Story 2 (preflight validator)
3. After US1:
   - Developer A: User Story 3 (override flags)
   - Developer B: User Story 4 (deprecation)

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story
- Each user story independently testable
- US1 is MVP - delivers full init functionality
- US2-US4 are incremental improvements
- Commit after each task or logical group
- Avoid: vague tasks, same file conflicts, cross-story dependencies
