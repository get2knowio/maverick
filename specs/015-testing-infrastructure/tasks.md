# Tasks: Testing Infrastructure

**Input**: Design documents from `/specs/015-testing-infrastructure/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

**Tests**: This feature IS the testing infrastructure, so test examples are included as part of implementation tasks (FR-024).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4)
- Include exact file paths in descriptions

## Path Conventions

- **Project structure**: `src/maverick/`, `tests/` at repository root
- **New directories**: `tests/fixtures/`, `tests/utils/`, `tests/tui/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and test directory structure

- [X] T001 Create tests/fixtures/ directory with __init__.py
- [X] T002 Create tests/utils/ directory with __init__.py
- [X] T003 Create tests/tui/ directory with __init__.py for dedicated TUI tests
- [X] T004 [P] Create tests/unit/config/ directory with __init__.py for configuration tests

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core fixture infrastructure that ALL user stories depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T005 Implement MockMessage class in tests/fixtures/agents.py
- [X] T006 Implement MockSDKClient class with response queue in tests/fixtures/agents.py (depends on T005)
- [X] T007 [P] Implement mock_text_message factory fixture in tests/fixtures/agents.py
- [X] T008 [P] Implement mock_result_message factory fixture in tests/fixtures/agents.py
- [X] T009 [P] Implement mock_sdk_client fixture in tests/fixtures/agents.py
- [X] T010 Update tests/conftest.py to register fixture plugins from tests/fixtures/

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Run Unit Tests Locally (Priority: P1) 🎯 MVP

**Goal**: Developers can run unit tests locally to verify changes don't break existing functionality

**Independent Test**: Run `pytest tests/unit/` and verify tests execute successfully with meaningful coverage output

### Implementation for User Story 1

- [X] T011 [P] [US1] Create sample MaverickConfig fixtures in tests/fixtures/config.py (FR-002)
- [X] T012 [P] [US1] Create sample agent response fixtures in tests/fixtures/responses.py (FR-004)
- [X] T013 [US1] Implement AsyncGeneratorCapture utility in tests/utils/async_helpers.py (FR-005)
- [X] T014 [US1] Implement AgentResultAssertion helpers in tests/utils/assertions.py (FR-006)
- [X] T015 [US1] Implement MCPToolValidator utility in tests/utils/mcp.py (FR-007)
- [X] T016 [US1] Configure pytest-asyncio 30-second default timeout in pyproject.toml (FR-026)
- [X] T017 [US1] Create example agent unit test in tests/unit/agents/test_base_example.py (FR-024)
- [X] T018 [US1] Create example tool unit test in tests/unit/tools/test_git_example.py (FR-024)
- [X] T019 [US1] Create example config unit test in tests/unit/config/test_config_example.py (FR-024)

**Checkpoint**: Developers can run `pytest tests/unit/` with full fixture support and example patterns

---

## Phase 4: User Story 4 - Write Tests Using Fixtures (Priority: P2)

**Goal**: Developers can use reusable test fixtures to quickly write comprehensive tests without boilerplate

**Independent Test**: Create a new test file that imports fixtures and verify they provide expected mock objects

### Implementation for User Story 4

- [X] T020 [US4] Implement MockGitHubCLI, CommandResponse, and CommandCall classes in tests/fixtures/github.py (FR-003)
- [X] T021 [US4] Implement mock_github_cli fixture in tests/fixtures/github.py (FR-003)
- [X] T022 [US4] Implement cli_runner fixture in tests/conftest.py for Click testing
- [X] T023 [US4] Add fixture usage documentation to tests/fixtures/__init__.py
- [X] T024 [US4] Create example fixture usage test in tests/unit/test_fixture_examples.py demonstrating all fixtures; verify test setup requires <20 lines of boilerplate (SC-005)

**Checkpoint**: All reusable fixtures available and documented with usage examples

---

## Phase 5: User Story 2 - Run Integration Tests (Priority: P2)

**Goal**: Developers can run integration tests to verify workflows, TUI, and CLI work correctly when combined

**Independent Test**: Run `pytest tests/integration/` and `pytest tests/tui/` and verify workflows execute end-to-end with mocked agents

### Implementation for User Story 2

- [X] T025 [P] [US2] Implement TestWorkflowRunner utility in tests/utils/workflow_helpers.py (FR-014)
- [X] T026 [US2] Create example workflow integration test in tests/integration/workflows/test_validation_example.py (FR-024)
- [X] T027 [P] [US2] Create TUI test app base class in tests/tui/conftest.py (FR-015)
- [X] T028 [US2] Create example TUI screen test using pilot in tests/tui/screens/test_home_example.py (FR-024)
- [X] T029 [US2] Create example CLI command test using CliRunner in tests/integration/cli/test_commands_example.py (FR-024)
- [X] T030 [US2] Ensure tests/integration/ directory structure matches plan (FR-012)

**Checkpoint**: Integration and TUI tests run successfully with mocked components

---

## Phase 6: User Story 3 - Continuous Integration Validation (Priority: P3)

**Goal**: CI automatically validates code quality on every PR

**Independent Test**: Push a branch or open a PR and observe GitHub Actions workflow execution and results

### Implementation for User Story 3

- [X] T031 [US3] Create .github/workflows/test.yml with CI workflow structure (FR-017, FR-023)
- [X] T032 [US3] Configure lint job with ruff check in CI workflow (FR-019)
- [X] T033 [US3] Configure type-check job with mypy in CI workflow (FR-020)
- [X] T034 [US3] Configure test job with Python matrix (3.10, 3.11, 3.12) in CI workflow (FR-018)
- [X] T035 [US3] Add pytest coverage enforcement (80% threshold) to CI workflow (FR-021, FR-022)
- [X] T036 [US3] Configure JUnit XML reporting for GitHub check annotations (FR-025)
- [X] T037 [US3] Add dorny/test-reporter for inline PR failure annotations (FR-025)
- [X] T038 [US3] Consolidate CI: remove plugin validation from .github/workflows/ci.yml (now covered by test.yml) or add job dependency to avoid duplicate checkouts

**Checkpoint**: CI runs automatically on PR with lint, type check, and tests across Python versions

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final validation and documentation

- [X] T039 Verify test directory structure: all dirs have __init__.py; tests/unit/agents/, tests/unit/tools/, tests/unit/workflows/ exist per FR-008, FR-009, FR-010
- [X] T040 Run full test suite and verify 80% coverage threshold
- [X] T041 Verify example tests demonstrate patterns for all component types (FR-024)
- [X] T042 Update tests/conftest.py with final fixture exports
- [X] T043 Run quickstart.md validation scenarios

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup - BLOCKS all user stories
- **User Stories (Phase 3-6)**: All depend on Foundational phase completion
  - US1 (Phase 3): Can start after Phase 2
  - US4 (Phase 4): Can start after Phase 2 (in parallel with US1)
  - US2 (Phase 5): Can start after Phase 2 (in parallel with US1/US4)
  - US3 (Phase 6): Can start after Phase 2 (in parallel with others)
- **Polish (Phase 7)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: No dependencies on other stories - core unit test infrastructure
- **User Story 4 (P2)**: No dependencies on other stories - extends fixtures from US1
- **User Story 2 (P2)**: May use fixtures from US1/US4 but independently testable
- **User Story 3 (P3)**: No dependencies on other stories - CI configuration is standalone

### Within Each User Story

- Models/utilities before example tests
- Core utilities before dependent utilities
- Fixtures must be complete before example tests that use them

### Parallel Opportunities

- All Setup tasks (T001-T004) can run in parallel
- Foundational fixture factories (T007, T008, T009) can run in parallel after T005-T006
- User Story 1: T011, T012 can run in parallel; T017, T018 can run in parallel after utilities
- User Story 4: T020-T024 are sequential (same file dependencies)
- User Story 2: T025, T027 can run in parallel
- All user stories can be worked on in parallel after Phase 2 completes

---

## Parallel Example: Phase 2 Foundational

```bash
# After T005-T006 (sequential - MockMessage then MockSDKClient):
Task: "Implement mock_text_message factory fixture in tests/fixtures/agents.py"
Task: "Implement mock_result_message factory fixture in tests/fixtures/agents.py"
Task: "Implement mock_sdk_client fixture in tests/fixtures/agents.py"
```

## Parallel Example: User Story 1 Models

```bash
# These create independent files:
Task: "Create sample MaverickConfig fixtures in tests/fixtures/config.py"
Task: "Create sample agent response fixtures in tests/fixtures/responses.py"
```

## Parallel Example: User Story 2 Integration

```bash
# These create independent files:
Task: "Implement TestWorkflowRunner utility in tests/utils/workflow_helpers.py"
Task: "Create TUI test app base class in tests/tui/conftest.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T004)
2. Complete Phase 2: Foundational (T005-T010)
3. Complete Phase 3: User Story 1 (T011-T019)
4. Complete Phase 4: User Story 4 (T020-T024)
5. **STOP and VALIDATE**: Run `pytest tests/unit/` - should work with all fixtures
6. Developers can now run unit tests locally

### Incremental Delivery

1. Complete Setup + Foundational (T001-T010) → Core fixtures available
2. Add User Story 1 (T011-T019) → Unit test infrastructure complete (MVP!)
3. Add User Story 4 (T020-T024) → All fixtures available for comprehensive testing
4. Add User Story 2 (T025-T030) → Integration and TUI testing patterns established
5. Add User Story 3 (T031-T038) → CI automatically validates all PRs
6. Polish (T039-T043) → Final validation complete

### Full Implementation

With single developer (sequential):
1. Phase 1 (T001-T004) → Phase 2 (T005-T010) → Phase 3 (T011-T019) → Phase 4 (T020-T024) → Phase 5 (T025-T030) → Phase 6 (T031-T038) → Phase 7 (T039-T043)

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Test examples (FR-024) are spread across user stories to demonstrate patterns
- Existing test structure in tests/unit/ is preserved; new fixtures enhance it
- CI workflow (test.yml) is separate from existing ci.yml to avoid disruption
- Coverage threshold (80%) aligns with existing project standards
