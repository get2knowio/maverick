# Tasks: GitHub MCP Tools Integration

**Input**: Design documents from `/specs/005-github-mcp-tools/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/github-tools.yaml

**Tests**: Unit tests are included as specified in plan.md (SC-001: 100% coverage of success and error paths).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `src/maverick/`, `tests/` at repository root (as per plan.md)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and module structure

- [X] T001 Create tools module structure with `src/maverick/tools/__init__.py` exporting `create_github_tools_server`
- [X] T002 Add `GitHubToolsError` exception to `src/maverick/exceptions.py`
- [X] T003 [P] Create test directory structure `tests/unit/tools/__init__.py` and `tests/integration/tools/__init__.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**:warning: CRITICAL**: No user story work can begin until this phase is complete

- [X] T004 Implement prerequisite verification (gh CLI, auth, git repo) in `src/maverick/tools/github.py`
- [X] T005 Implement `_run_gh_command()` async subprocess helper in `src/maverick/tools/github.py` (or import from `utils/github.py` if exists)
- [X] T006 [P] Implement `_parse_rate_limit_wait()` helper for extracting retry-after from errors in `src/maverick/tools/github.py`
- [X] T007 [P] Implement MCP response formatting helpers (`_success_response()`, `_error_response()`) in `src/maverick/tools/github.py`
- [X] T008 Implement `create_github_tools_server()` factory function skeleton in `src/maverick/tools/github.py`
- [X] T009 [P] Add unit tests for prerequisite verification in `tests/unit/tools/test_github.py`
- [X] T010 [P] Add unit tests for helper functions in `tests/unit/tools/test_github.py`

**Checkpoint**: Foundation ready - MCP server factory exists, helpers work, user story implementation can begin

---

## Phase 3: User Story 1 - Create Pull Request (Priority: P1) :dart: MVP

**Goal**: Enable agents to create pull requests via `github_create_pr` tool for FlyWorkflow output

**Independent Test**: Call tool with valid branch parameters and verify PR is created with correct title/body/state

### Unit Tests for User Story 1

- [X] T011 [P] [US1] Add unit test for `github_create_pr` success case in `tests/unit/tools/test_github.py`
- [X] T012 [P] [US1] Add unit test for `github_create_pr` draft PR case in `tests/unit/tools/test_github.py`
- [X] T013 [P] [US1] Add unit test for `github_create_pr` branch not found error in `tests/unit/tools/test_github.py`

### Implementation for User Story 1

- [X] T014 [US1] Implement `github_create_pr` tool with `@tool` decorator in `src/maverick/tools/github.py`
- [X] T015 [US1] Register `github_create_pr` in `create_github_tools_server()` in `src/maverick/tools/github.py`
- [X] T016 [US1] Add logging for PR creation operations in `src/maverick/tools/github.py`

**Checkpoint**: User Story 1 complete - agents can create PRs

---

## Phase 4: User Story 2 - List and Retrieve Issues (Priority: P1)

**Goal**: Enable RefuelWorkflow to discover open issues with labels and get issue details

**Independent Test**: Call `github_list_issues` with label filter, then `github_get_issue` on returned issue numbers

### Unit Tests for User Story 2

- [X] T017 [P] [US2] Add unit test for `github_list_issues` with label filter in `tests/unit/tools/test_github.py`
- [X] T018 [P] [US2] Add unit test for `github_list_issues` with state and limit in `tests/unit/tools/test_github.py`
- [X] T019 [P] [US2] Add unit test for `github_get_issue` success case in `tests/unit/tools/test_github.py`
- [X] T020 [P] [US2] Add unit test for `github_get_issue` not found error in `tests/unit/tools/test_github.py`

### Implementation for User Story 2

- [X] T021 [US2] Implement `github_list_issues` tool with `@tool` decorator in `src/maverick/tools/github.py`
- [X] T022 [US2] Implement `github_get_issue` tool with `@tool` decorator in `src/maverick/tools/github.py`
- [X] T023 [US2] Register both tools in `create_github_tools_server()` in `src/maverick/tools/github.py`
- [X] T024 [US2] Add logging for issue operations in `src/maverick/tools/github.py`

**Checkpoint**: User Story 2 complete - agents can discover and retrieve issues

---

## Phase 5: User Story 3 - Check PR Status (Priority: P2)

**Goal**: Enable agents to verify PR merge readiness (checks, reviews, conflicts)

**Independent Test**: Call `github_pr_status` on a known PR and verify checks/reviews/mergeable state returned

### Unit Tests for User Story 3

- [X] T025 [P] [US3] Add unit test for `github_pr_status` ready-to-merge case in `tests/unit/tools/test_github.py`
- [X] T026 [P] [US3] Add unit test for `github_pr_status` failing checks case in `tests/unit/tools/test_github.py`
- [X] T027 [P] [US3] Add unit test for `github_pr_status` merge conflicts case in `tests/unit/tools/test_github.py`

### Implementation for User Story 3

- [X] T028 [US3] Implement `github_pr_status` tool with `@tool` decorator in `src/maverick/tools/github.py`
- [X] T029 [US3] Register tool in `create_github_tools_server()` in `src/maverick/tools/github.py`
- [X] T030 [US3] Add logging for PR status checks in `src/maverick/tools/github.py`

**Checkpoint**: User Story 3 complete - agents can check PR merge readiness

---

## Phase 6: User Story 4 - Get PR Diff (Priority: P2)

**Goal**: Enable code review workflows to retrieve PR diffs with truncation handling

**Independent Test**: Call `github_get_pr_diff` on a PR and verify diff content returned (with truncation if large)

### Unit Tests for User Story 4

- [X] T031 [P] [US4] Add unit test for `github_get_pr_diff` normal diff in `tests/unit/tools/test_github.py`
- [X] T032 [P] [US4] Add unit test for `github_get_pr_diff` truncated diff case in `tests/unit/tools/test_github.py`
- [X] T033 [P] [US4] Add unit test for `github_get_pr_diff` not found error in `tests/unit/tools/test_github.py`

### Implementation for User Story 4

- [X] T034 [US4] Implement `github_get_pr_diff` tool with truncation logic in `src/maverick/tools/github.py`
- [X] T035 [US4] Register tool in `create_github_tools_server()` in `src/maverick/tools/github.py`
- [X] T036 [US4] Add logging for diff retrieval in `src/maverick/tools/github.py`

**Checkpoint**: User Story 4 complete - agents can retrieve PR diffs for review

---

## Phase 7: User Story 5 - Manage Issue Labels (Priority: P3)

**Goal**: Enable workflows to add labels to issues/PRs for status tracking

**Independent Test**: Call `github_add_labels` on a test issue and verify labels are added

### Unit Tests for User Story 5

- [X] T037 [P] [US5] Add unit test for `github_add_labels` success case in `tests/unit/tools/test_github.py`
- [X] T038 [P] [US5] Add unit test for `github_add_labels` with new label creation in `tests/unit/tools/test_github.py`

### Implementation for User Story 5

- [X] T039 [US5] Implement `github_add_labels` tool with `@tool` decorator in `src/maverick/tools/github.py`
- [X] T040 [US5] Register tool in `create_github_tools_server()` in `src/maverick/tools/github.py`
- [X] T041 [US5] Add logging for label operations in `src/maverick/tools/github.py`

**Checkpoint**: User Story 5 complete - agents can add labels

---

## Phase 8: User Story 6 - Close Issues (Priority: P3)

**Goal**: Enable RefuelWorkflow to close resolved issues with optional comment

**Independent Test**: Call `github_close_issue` on a test issue and verify it is closed

### Unit Tests for User Story 6

- [X] T042 [P] [US6] Add unit test for `github_close_issue` with comment in `tests/unit/tools/test_github.py`
- [X] T043 [P] [US6] Add unit test for `github_close_issue` without comment in `tests/unit/tools/test_github.py`
- [X] T044 [P] [US6] Add unit test for `github_close_issue` idempotent (already closed) in `tests/unit/tools/test_github.py`

### Implementation for User Story 6

- [X] T045 [US6] Implement `github_close_issue` tool with `@tool` decorator in `src/maverick/tools/github.py`
- [X] T046 [US6] Register tool in `create_github_tools_server()` in `src/maverick/tools/github.py`
- [X] T047 [US6] Add logging for issue close operations in `src/maverick/tools/github.py`

**Checkpoint**: User Story 6 complete - agents can close issues

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Error handling, rate limiting, type safety, performance, integration tests

- [X] T048 [P] Add unit tests for rate limit error handling across all tools in `tests/unit/tools/test_github.py`
- [X] T049 [P] Add unit tests for network error handling in `tests/unit/tools/test_github.py`
- [X] T050 [P] Add unit tests for auth error handling in `tests/unit/tools/test_github.py`
- [X] T051 [P] Run mypy type checking on `src/maverick/tools/github.py` and fix any errors (FR-014)
- [X] T052 Add integration test for full tool workflow in `tests/integration/tools/test_github.py`
- [X] T053 [P] Add performance benchmark test asserting tool execution <5s in `tests/integration/tools/test_github.py` (SC-002)
- [X] T054 Run quickstart.md validation to verify all examples work
- [X] T055 Update `src/maverick/tools/__init__.py` exports and verify import from `maverick.tools.github`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3-8)**: All depend on Foundational phase completion
  - US1 (P1) and US2 (P1) can run in parallel
  - US3 (P2) and US4 (P2) can run in parallel after P1 stories
  - US5 (P3) and US6 (P3) can run in parallel after P2 stories
  - Or sequentially in priority order (P1 -> P2 -> P3)
- **Polish (Phase 9)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational - No dependencies on other stories
- **User Story 2 (P1)**: Can start after Foundational - No dependencies on other stories
- **User Story 3 (P2)**: Can start after Foundational - No dependencies on other stories
- **User Story 4 (P2)**: Can start after Foundational - No dependencies on other stories
- **User Story 5 (P3)**: Can start after Foundational - No dependencies on other stories
- **User Story 6 (P3)**: Can start after Foundational - No dependencies on other stories

### Within Each User Story

- Unit tests written first (TDD - tests should fail before implementation)
- Tool implementation
- Registration in factory
- Logging added
- Story complete before moving to next priority

### Parallel Opportunities

**Phase 1 (Setup)**:
- T001, T002, T003 can all run in parallel (different files)

**Phase 2 (Foundational)**:
- T006, T007, T009, T010 can run in parallel

**User Story Tests** (each phase):
- All test tasks within a story marked [P] can run in parallel

**Cross-Story Parallelism**:
- US1 and US2 are both P1 priority and can run in parallel
- US3 and US4 are both P2 priority and can run in parallel
- US5 and US6 are both P3 priority and can run in parallel

---

## Parallel Example: Foundational Phase

```bash
# Launch parallel tasks in Foundational phase:
Task: "Implement _parse_rate_limit_wait() helper in src/maverick/tools/github.py"
Task: "Implement MCP response formatting helpers in src/maverick/tools/github.py"
Task: "Add unit tests for prerequisite verification in tests/unit/tools/test_github.py"
Task: "Add unit tests for helper functions in tests/unit/tools/test_github.py"
```

## Parallel Example: User Story 1

```bash
# Launch all tests for User Story 1 together:
Task: "Add unit test for github_create_pr success case in tests/unit/tools/test_github.py"
Task: "Add unit test for github_create_pr draft PR case in tests/unit/tools/test_github.py"
Task: "Add unit test for github_create_pr branch not found error in tests/unit/tools/test_github.py"
```

## Parallel Example: P1 User Stories

```bash
# Launch User Story 1 and User Story 2 in parallel (both P1):
Task: "User Story 1 - Create Pull Request"
Task: "User Story 2 - List and Retrieve Issues"
```

---

## Implementation Strategy

### MVP First (User Stories 1 + 2 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1 (Create PR) - FlyWorkflow can create PRs
4. Complete Phase 4: User Story 2 (List/Get Issues) - RefuelWorkflow can discover issues
5. **STOP and VALIDATE**: Test US1 and US2 independently
6. Deploy/demo if ready - Core workflows (Fly + Refuel) are functional

### Incremental Delivery

1. Complete Setup + Foundational -> Foundation ready
2. Add US1 + US2 -> Test independently -> Deploy/Demo (MVP!)
3. Add US3 + US4 -> Test independently -> Deploy/Demo (PR status + diff)
4. Add US5 + US6 -> Test independently -> Deploy/Demo (Labels + close)
5. Each story adds value without breaking previous stories

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1 (Create PR)
   - Developer B: User Story 2 (List/Get Issues)
3. Then:
   - Developer A: User Story 3 (PR Status)
   - Developer B: User Story 4 (PR Diff)
4. Finally:
   - Developer A: User Story 5 (Labels)
   - Developer B: User Story 6 (Close Issue)
5. All stories integrate independently into the factory

---

## Notes

- [P] tasks = different files or independent sections, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story is independently completable and testable
- All 7 tools map to 6 user stories (US2 has 2 tools: list + get)
- Total: 55 tasks (T001-T055)
- Verify tests fail before implementing (TDD)
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- All tools share the same MCP response format and error handling patterns
