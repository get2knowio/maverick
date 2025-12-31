# Tasks: Maverick Foundation - Project Skeleton & Configuration System

**Input**: Design documents from `/specs/001-maverick-foundation/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/cli-interface.md

**Tests**: Not explicitly requested in the feature specification. Tests will be included as they are mentioned in the project structure (plan.md) and align with constitution principle V (Test-First).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `src/maverick/`, `tests/` at repository root (per plan.md)

---

## Phase 1: Setup (Project Initialization)

**Purpose**: Create Python project structure with pyproject.toml and basic package layout

- [X] T001 Create pyproject.toml with hatchling build backend and project metadata in pyproject.toml
- [X] T002 [P] Create src/maverick/__init__.py with version string and public API exports
- [X] T003 [P] Create placeholder directories with __init__.py files: src/maverick/agents/, src/maverick/workflows/, src/maverick/tools/, src/maverick/hooks/, src/maverick/tui/, src/maverick/utils/
- [X] T004 [P] Create tests/conftest.py with shared pytest fixtures
- [X] T005 [P] Create tests/unit/ and tests/integration/ directories with __init__.py files

**Checkpoint**: Project structure ready - can run `pip install -e .`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before user story implementation

**WARNING**: No user story work can begin until this phase is complete

- [X] T006 Implement MaverickError base exception class in src/maverick/exceptions.py
- [X] T007 Implement ConfigError subclass with field and value attributes in src/maverick/exceptions.py

**Checkpoint**: Exception hierarchy ready - configuration and CLI can now handle errors consistently

---

## Phase 3: User Story 1 - Developer Installs Maverick (Priority: P1)

**Goal**: Developer can install Maverick via pip and use `maverick --help` and `maverick --version` commands

**Independent Test**: Run `pip install .` in project root, then verify `maverick --help` and `maverick --version` work

### Tests for User Story 1

- [X] T008 [P] [US1] Create test_cli.py with test for --version output in tests/unit/test_cli.py
- [X] T009 [P] [US1] Add test for --help output in tests/unit/test_cli.py
- [X] T010 [P] [US1] Add test for exit codes (0 for success, 2 for usage error) in tests/unit/test_cli.py

### Implementation for User Story 1

- [X] T011 [US1] Implement Click CLI entry point with maverick command group in src/maverick/main.py
- [X] T012 [US1] Add --version option using click.version_option() in src/maverick/main.py
- [X] T013 [US1] Add --help with descriptive help text in src/maverick/main.py
- [X] T014 [US1] Configure entry point in pyproject.toml [project.scripts] section

**Checkpoint**: User Story 1 complete - `maverick --version` and `maverick --help` work

---

## Phase 4: User Story 2 - Developer Configures Maverick for Their Project (Priority: P2)

**Goal**: Developer can create maverick.yaml in project root and Maverick loads those settings

**Independent Test**: Create `maverick.yaml` with custom settings, run Maverick command with -vv, verify settings are loaded

### Tests for User Story 2

- [X] T015 [P] [US2] Create test_config.py with test for loading defaults when no config file exists in tests/unit/test_config.py
- [X] T016 [P] [US2] Add test for loading project config from maverick.yaml in tests/unit/test_config.py
- [X] T017 [P] [US2] Add test for environment variable overrides (MAVERICK_* prefix) in tests/unit/test_config.py
- [X] T018 [P] [US2] Add test for invalid config producing ConfigError with field/value context in tests/unit/test_config.py
- [X] T019 [P] [US2] Add test for unknown keys being ignored with warning in tests/unit/test_config.py
- [X] T019a [P] [US2] Add test verifying config loader does not expose secret-like fields (api_key, token, password) from YAML files in tests/unit/test_config.py

### Implementation for User Story 2

- [X] T020 [P] [US2] Implement GitHubConfig Pydantic model in src/maverick/config.py
- [X] T021 [P] [US2] Implement NotificationConfig Pydantic model in src/maverick/config.py
- [X] T022 [P] [US2] Implement ModelConfig Pydantic model with validation (max_tokens 1-200000, temperature 0.0-1.0) in src/maverick/config.py
- [X] T023 [P] [US2] Implement ParallelConfig Pydantic model with validation (max_agents 1-10, max_tasks 1-20) in src/maverick/config.py
- [X] T024 [P] [US2] Implement AgentConfig Pydantic model for agent-specific overrides in src/maverick/config.py
- [X] T025 [US2] Implement MaverickConfig root model composing all config sections in src/maverick/config.py
- [X] T026 [US2] Implement load_config() function to load from project maverick.yaml in src/maverick/config.py
- [X] T027 [US2] Add environment variable override support with MAVERICK_ prefix and _ delimiter (e.g., MAVERICK_GITHUB_OWNER) in src/maverick/config.py
- [X] T028 [US2] Integrate config loading into CLI entry point in src/maverick/main.py
- [X] T029 [US2] Add ConfigError handling with user-friendly messages in src/maverick/main.py

**Checkpoint**: User Story 2 complete - Project config loads from maverick.yaml with env var overrides

---

## Phase 5: User Story 3 - Developer Uses User-Level Configuration (Priority: P3)

**Goal**: Developer can set personal preferences in ~/.config/maverick/config.yaml that apply across all projects

**Independent Test**: Create config at ~/.config/maverick/config.yaml, run Maverick in project without local config, verify user settings applied

### Tests for User Story 3

- [X] T030 [P] [US3] Add test for loading user config from ~/.config/maverick/config.yaml in tests/unit/test_config.py
- [X] T031 [P] [US3] Add test for project config overriding user config in tests/unit/test_config.py
- [X] T032 [P] [US3] Add test for merging partial configs (user + project) in tests/unit/test_config.py
- [X] T033 [US3] Create integration test for full config loading flow in tests/integration/test_config_loading.py

### Implementation for User Story 3

- [X] T034 [US3] Implement settings_customise_sources() for multi-source config loading in src/maverick/config.py
- [X] T035 [US3] Add user config path detection (~/.config/maverick/config.yaml) in src/maverick/config.py
- [X] T036 [US3] Implement config merging logic (defaults -> user -> project -> env) in src/maverick/config.py
- [X] T037 [US3] Add INFO log message when no project config found in src/maverick/config.py

**Checkpoint**: User Story 3 complete - Hierarchical config merging works (user -> project -> env)

---

## Phase 6: User Story 4 - Developer Adjusts Logging Verbosity (Priority: P4)

**Goal**: Developer can increase logging verbosity using -v/-vv flags or config file setting

**Independent Test**: Run `maverick -vv` and observe debug-level log messages

### Tests for User Story 4

- [X] T038 [P] [US4] Add test for default verbosity (WARNING level) in tests/unit/test_cli.py
- [X] T039 [P] [US4] Add test for -v flag (INFO level) in tests/unit/test_cli.py
- [X] T040 [P] [US4] Add test for -vv flag (DEBUG level) in tests/unit/test_cli.py
- [X] T041 [P] [US4] Add test for verbosity config file setting in tests/unit/test_cli.py

### Implementation for User Story 4

- [X] T042 [US4] Add -v/--verbose count option to CLI in src/maverick/main.py
- [X] T043 [US4] Implement logging configuration based on verbosity level in src/maverick/main.py
- [X] T044 [US4] Add verbosity field to MaverickConfig (Literal["error", "warning", "info", "debug"]) in src/maverick/config.py
- [X] T045 [US4] Implement CLI flag override for config file verbosity setting in src/maverick/main.py

**Checkpoint**: User Story 4 complete - Verbosity control via CLI flags and config

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [X] T046 [P] Add edge case handling: empty config file uses defaults with warning in src/maverick/config.py
- [X] T047 [P] Add edge case handling: invalid env var values produce clear validation error in src/maverick/config.py
- [X] T048 [P] Add edge case handling: missing user config directory works without error in src/maverick/config.py
- [X] T049 Run quickstart.md validation scenarios
- [X] T050 Verify SC-001: Developer can install and execute `maverick --help` within 1 minute
- [X] T051 Verify SC-005: Configuration loading completes in under 100ms

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational (Phase 2)
- **User Story 2 (Phase 4)**: Depends on Foundational (Phase 2), can run in parallel with US1
- **User Story 3 (Phase 5)**: Depends on User Story 2 (builds on config loading)
- **User Story 4 (Phase 6)**: Depends on User Story 1 (CLI) and User Story 2 (config), can run in parallel with US3
- **Polish (Phase 7)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: No dependencies on other stories - CLI entry point standalone
- **User Story 2 (P2)**: No dependencies on US1 - config system can be built independently
- **User Story 3 (P3)**: Depends on User Story 2 - extends config loading with user-level support
- **User Story 4 (P4)**: Depends on US1 (CLI) and US2 (config) - integrates both

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- Pydantic models before config loading functions
- Config loading before CLI integration
- Core implementation before edge cases
- Story complete before moving to next priority

### Parallel Opportunities

**Phase 1 (Setup)**:
- T002, T003, T004, T005 can run in parallel (different directories/files)

**Phase 3 (US1 Tests)**:
- T008, T009, T010 can run in parallel (same file but independent tests)

**Phase 4 (US2)**:
- T015-T019 (tests) can run in parallel
- T020-T024 (Pydantic models) can run in parallel (different classes)

**Phase 5 (US3)**:
- T030-T032 (tests) can run in parallel

**Phase 6 (US4)**:
- T038-T041 (tests) can run in parallel

**Phase 7 (Polish)**:
- T046-T048 can run in parallel (different edge cases)

---

## Parallel Example: User Story 2 Configuration Models

```bash
# Launch all Pydantic model implementations together:
Task: "Implement GitHubConfig Pydantic model in src/maverick/config.py"
Task: "Implement NotificationConfig Pydantic model in src/maverick/config.py"
Task: "Implement ModelConfig Pydantic model in src/maverick/config.py"
Task: "Implement ParallelConfig Pydantic model in src/maverick/config.py"
Task: "Implement AgentConfig Pydantic model in src/maverick/config.py"
```

---

## Implementation Strategy

### MVP First (User Stories 1 + 2 Only)

1. Complete Phase 1: Setup - Project structure
2. Complete Phase 2: Foundational - Exception hierarchy
3. Complete Phase 3: User Story 1 - CLI with --version and --help
4. **STOP and VALIDATE**: `pip install -e .` and test CLI
5. Complete Phase 4: User Story 2 - Project config loading
6. **STOP and VALIDATE**: Create maverick.yaml, verify settings load
7. Deploy/demo if ready

### Incremental Delivery

1. Setup + Foundational -> Project installable
2. Add User Story 1 -> CLI works (--version, --help)
3. Add User Story 2 -> Project config works
4. Add User Story 3 -> User config works
5. Add User Story 4 -> Verbosity control works
6. Polish -> Edge cases handled, validation complete

### Key Files Summary

| File | User Stories | Description |
|------|-------------|-------------|
| pyproject.toml | US1 | Build config, entry point |
| src/maverick/__init__.py | US1 | Version, exports |
| src/maverick/exceptions.py | Foundation | MaverickError, ConfigError |
| src/maverick/config.py | US2, US3, US4 | All Pydantic models, config loading |
| src/maverick/main.py | US1, US2, US4 | Click CLI, config integration, verbosity |
| tests/unit/test_cli.py | US1, US4 | CLI tests |
| tests/unit/test_config.py | US2, US3 | Config tests |
| tests/integration/test_config_loading.py | US3 | Config integration tests |

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verify tests fail before implementing
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Avoid: vague tasks, same file conflicts, cross-story dependencies that break independence
