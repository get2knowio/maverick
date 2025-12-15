# Tasks: Utility MCP Tools

**Input**: Design documents from `/specs/006-utility-mcp-tools/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `src/maverick/`, `tests/` at repository root
- Reference: Existing patterns in `src/maverick/tools/github.py`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and configuration models

- [X] T001 Add ValidationConfig model to src/maverick/config.py with format_cmd, lint_cmd, typecheck_cmd, test_cmd, timeout_seconds, max_errors fields
- [X] T002 Add validation field to MaverickConfig in src/maverick/config.py referencing ValidationConfig
- [X] T003 [P] Add NotificationToolsError, GitToolsError, ValidationToolsError to src/maverick/exceptions.py
- [X] T004 [P] Create empty src/maverick/tools/notification.py module with docstring and imports
- [X] T005 [P] Create empty src/maverick/tools/git.py module with docstring and imports
- [X] T006 [P] Create empty src/maverick/tools/validation.py module with docstring and imports

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared helper functions and response utilities that ALL tools depend on

**CRITICAL**: No user story work can begin until this phase is complete

- [X] T007 Implement _success_response() helper in src/maverick/tools/notification.py following github.py pattern
- [X] T008 Implement _error_response() helper in src/maverick/tools/notification.py following github.py pattern
- [X] T009 [P] Implement _success_response() and _error_response() helpers in src/maverick/tools/git.py following github.py pattern
- [X] T010 [P] Implement _success_response() and _error_response() helpers in src/maverick/tools/validation.py following github.py pattern
- [X] T011 Implement async _send_ntfy_request() helper in src/maverick/tools/notification.py using aiohttp with retry logic (1-2 attempts, 2s timeout)
- [X] T012 Implement _verify_git_prerequisites() helper in src/maverick/tools/git.py to check git installed and inside repo
- [X] T013 [P] Implement async _run_git_command() helper in src/maverick/tools/git.py using asyncio.subprocess
- [X] T014 [P] Implement _format_commit_message() helper in src/maverick/tools/git.py for conventional commit format

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 1 - Receive Workflow Progress Notifications (Priority: P1)

**Goal**: Enable agents to send workflow stage notifications via ntfy.sh with automatic priority/tag mapping

**Independent Test**: Call `send_workflow_update` with stage="complete" and message="Done", verify notification sent with high priority and tada tag

### Implementation for User Story 1

- [X] T015 [US1] Define STAGE_MAPPING dict in src/maverick/tools/notification.py mapping stages to priority/tags
- [X] T016 [US1] Implement send_workflow_update @tool function in src/maverick/tools/notification.py with stage, message, workflow_name parameters
- [X] T017 [US1] Add graceful degradation in send_workflow_update when ntfy.sh not configured (return success with "disabled" message)
- [X] T018 [US1] Add logging for notification operations in src/maverick/tools/notification.py

**Checkpoint**: User Story 1 complete - send_workflow_update functional

---

## Phase 4: User Story 2 - Commit Changes with Conventional Commits (Priority: P1)

**Goal**: Enable agents to create git commits with conventional commit format (type, scope, breaking)

**Independent Test**: Stage a file change, call `git_commit` with type="feat", scope="api", message="add endpoint", verify commit created with "feat(api): add endpoint" message

### Implementation for User Story 2

- [X] T019 [US2] Define COMMIT_TYPES constant in src/maverick/tools/git.py with valid conventional commit types
- [X] T020 [US2] Implement git_commit @tool function in src/maverick/tools/git.py with message, type, scope, breaking parameters
- [X] T021 [US2] Add input validation in git_commit for valid commit types and non-empty message
- [X] T022 [US2] Add NOTHING_TO_COMMIT error handling when no staged changes exist
- [X] T023 [US2] Add logging for git_commit operations in src/maverick/tools/git.py

**Checkpoint**: User Story 2 complete - git_commit functional with conventional format

---

## Phase 5: User Story 3 - Run Project Validation Suite (Priority: P1)

**Goal**: Enable agents to run validation commands (format, lint, typecheck, test) and parse structured errors from output

**Independent Test**: Introduce a lint error, call `run_validation` with types=["lint"], verify failure returned with raw output; call `parse_validation_output` with output, verify structured error list

### Implementation for User Story 3

- [X] T024 [US3] Define RUFF_PATTERN and MYPY_PATTERN regex constants in src/maverick/tools/validation.py per research.md
- [X] T025 [US3] Implement async _run_command_with_timeout() helper in src/maverick/tools/validation.py using asyncio.subprocess
- [X] T026 [US3] Implement run_validation @tool function in src/maverick/tools/validation.py with types parameter
- [X] T027 [US3] Add timeout handling in run_validation that kills process and returns "timeout" status with partial output
- [X] T028 [US3] Implement parse_validation_output @tool function in src/maverick/tools/validation.py with output and type parameters
- [X] T029 [US3] Add error truncation in parse_validation_output (default 50 errors, include total_count and truncated flag)
- [X] T030 [US3] Add logging for validation operations in src/maverick/tools/validation.py

**Checkpoint**: User Story 3 complete - run_validation and parse_validation_output functional

---

## Phase 6: User Story 4 - Push Changes to Remote (Priority: P2)

**Goal**: Enable agents to push commits to remote repository with optional upstream tracking

**Independent Test**: Create a commit on a test branch, call `git_push` with set_upstream=true, verify remote branch updated

### Implementation for User Story 4

- [X] T031 [US4] Implement git_push @tool function in src/maverick/tools/git.py with set_upstream parameter
- [X] T032 [US4] Add DETACHED_HEAD error handling in git_push when in detached HEAD state
- [X] T033 [US4] Add AUTHENTICATION_REQUIRED error detection in git_push checking stderr patterns
- [X] T034 [US4] Add NETWORK_ERROR handling in git_push for connectivity failures
- [X] T035 [US4] Add logging for git_push operations in src/maverick/tools/git.py

**Checkpoint**: User Story 4 complete - git_push functional with error handling

---

## Phase 7: User Story 5 - Get Branch and Diff Information (Priority: P2)

**Goal**: Enable agents to query current git state (branch name, change statistics)

**Independent Test**: Checkout a known branch, make changes, call `git_current_branch` and `git_diff_stats`, verify accurate results

### Implementation for User Story 5

- [X] T036 [P] [US5] Implement git_current_branch @tool function in src/maverick/tools/git.py returning branch name or "(detached)"
- [X] T037 [P] [US5] Implement git_diff_stats @tool function in src/maverick/tools/git.py returning files_changed, insertions, deletions
- [X] T038 [US5] Add NOT_A_REPOSITORY error handling to git_current_branch and git_diff_stats

**Checkpoint**: User Story 5 complete - git_current_branch and git_diff_stats functional

---

## Phase 8: User Story 6 - Create Feature Branches (Priority: P2)

**Goal**: Enable agents to create and checkout new git branches from specified base

**Independent Test**: Call `git_create_branch` with name="test-branch", verify branch created and checked out

### Implementation for User Story 6

- [X] T039 [US6] Implement git_create_branch @tool function in src/maverick/tools/git.py with name and base parameters
- [X] T040 [US6] Add BRANCH_EXISTS error handling in git_create_branch
- [X] T041 [US6] Add BRANCH_NOT_FOUND error handling in git_create_branch for invalid base
- [X] T042 [US6] Add input validation for valid git branch names in git_create_branch

**Checkpoint**: User Story 6 complete - git_create_branch functional

---

## Phase 9: User Story 7 - Send Custom Notifications (Priority: P3)

**Goal**: Enable agents to send arbitrary notifications with full control over title, priority, tags

**Independent Test**: Call `send_notification` with custom title, message, priority="urgent", tags=["warning"], verify notification delivered with all parameters

### Implementation for User Story 7

- [X] T043 [US7] Define NTFY_PRIORITIES mapping in src/maverick/tools/notification.py (min=1, low=2, default=3, high=4, urgent=5)
- [X] T044 [US7] Implement send_notification @tool function in src/maverick/tools/notification.py with message, title, priority, tags parameters
- [X] T045 [US7] Add input validation in send_notification for valid priority values
- [X] T046 [US7] Add graceful degradation in send_notification when ntfy.sh not configured or unreachable

**Checkpoint**: User Story 7 complete - send_notification functional

---

## Phase 10: Factory Functions & Exports

**Purpose**: Create MCP server factory functions and update module exports

- [X] T047 Implement create_notification_tools_server() factory function in src/maverick/tools/notification.py using create_sdk_mcp_server()
- [X] T048 [P] Implement create_git_tools_server() factory function in src/maverick/tools/git.py using create_sdk_mcp_server()
- [X] T049 [P] Implement create_validation_tools_server() factory function in src/maverick/tools/validation.py using create_sdk_mcp_server()
- [X] T050 Update src/maverick/tools/__init__.py to export create_notification_tools_server, create_git_tools_server, create_validation_tools_server

**Checkpoint**: All factory functions created and exported

---

## Phase 11: Unit Tests

**Purpose**: Comprehensive unit tests for all tools with mocked external dependencies

### Notification Tool Tests

- [ ] T051 [P] Create tests/tools/test_notification.py with test fixtures for mocked aiohttp responses
- [ ] T052 [P] Add test_send_workflow_update_success in tests/tools/test_notification.py
- [ ] T053 [P] Add test_send_workflow_update_disabled in tests/tools/test_notification.py (ntfy not configured)
- [ ] T054 [P] Add test_send_workflow_update_retry in tests/tools/test_notification.py (server unreachable, retry succeeds)
- [ ] T055 [P] Add test_send_notification_success in tests/tools/test_notification.py
- [ ] T056 [P] Add test_send_notification_graceful_degradation in tests/tools/test_notification.py
- [ ] T057 [P] Add test_create_notification_tools_server in tests/tools/test_notification.py

### Git Tool Tests

- [ ] T058 [P] Create tests/tools/test_git_tools.py with test fixtures for mocked subprocess
- [ ] T059 [P] Add test_git_current_branch_success in tests/tools/test_git_tools.py
- [ ] T060 [P] Add test_git_current_branch_detached in tests/tools/test_git_tools.py
- [ ] T061 [P] Add test_git_current_branch_not_repo in tests/tools/test_git_tools.py
- [ ] T062 [P] Add test_git_create_branch_success in tests/tools/test_git_tools.py
- [ ] T063 [P] Add test_git_create_branch_exists in tests/tools/test_git_tools.py
- [ ] T064 [P] Add test_git_commit_success in tests/tools/test_git_tools.py
- [ ] T065 [P] Add test_git_commit_conventional_format in tests/tools/test_git_tools.py (type, scope, breaking)
- [ ] T066 [P] Add test_git_commit_nothing_to_commit in tests/tools/test_git_tools.py
- [ ] T067 [P] Add test_git_push_success in tests/tools/test_git_tools.py
- [ ] T068 [P] Add test_git_push_detached_head in tests/tools/test_git_tools.py
- [ ] T069 [P] Add test_git_push_auth_required in tests/tools/test_git_tools.py
- [ ] T070 [P] Add test_git_diff_stats_success in tests/tools/test_git_tools.py
- [ ] T071 [P] Add test_git_diff_stats_no_changes in tests/tools/test_git_tools.py
- [ ] T072 [P] Add test_create_git_tools_server in tests/tools/test_git_tools.py

### Validation Tool Tests

- [ ] T073 [P] Create tests/tools/test_validation.py with test fixtures for mocked subprocess
- [ ] T074 [P] Add test_run_validation_success in tests/tools/test_validation.py
- [ ] T075 [P] Add test_run_validation_failure in tests/tools/test_validation.py
- [ ] T076 [P] Add test_run_validation_timeout in tests/tools/test_validation.py
- [ ] T077 [P] Add test_parse_validation_output_ruff in tests/tools/test_validation.py
- [ ] T078 [P] Add test_parse_validation_output_mypy in tests/tools/test_validation.py
- [ ] T079 [P] Add test_parse_validation_output_truncation in tests/tools/test_validation.py
- [ ] T080 [P] Add test_create_validation_tools_server in tests/tools/test_validation.py

---

## Phase 12: Polish & Cross-Cutting Concerns

**Purpose**: Final validation and integration verification

- [ ] T081 Run ruff format and ruff check on all new files
- [ ] T082 Run mypy type checking on src/maverick/tools/ modules
- [ ] T083 Run full test suite with pytest
- [ ] T084 Verify all factory functions can be imported from maverick.tools
- [ ] T085 Run quickstart.md validation scenarios manually

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3-9)**: All depend on Foundational phase completion
  - US1, US2, US3 are all P1 priority - can run in parallel if resourced
  - US4, US5, US6 are P2 priority - depend on Foundational, not on P1 stories
  - US7 is P3 priority - can run after Foundational
- **Factory Functions (Phase 10)**: Depends on all tool implementations (US1-US7)
- **Unit Tests (Phase 11)**: Depends on Factory Functions (Phase 10)
- **Polish (Phase 12)**: Depends on Unit Tests (Phase 11)

### User Story Dependencies

- **US1 (Notifications)**: Foundational + T007, T008, T011
- **US2 (git_commit)**: Foundational + T009, T012, T013, T014
- **US3 (Validation)**: Foundational + T010
- **US4 (git_push)**: Foundational + T009, T012, T013
- **US5 (git_current_branch, git_diff_stats)**: Foundational + T009, T012, T013
- **US6 (git_create_branch)**: Foundational + T009, T012, T013
- **US7 (send_notification)**: Foundational + T007, T008, T011 (shares with US1)

### Within Each User Story

- Response helpers before tool implementations
- Input validation integrated into tool functions
- Logging added after core functionality works

### Parallel Opportunities

- T003, T004, T005, T006 can run in parallel (different files)
- T009, T010, T011, T012, T013, T014 can run in parallel (different helpers, files)
- T036, T037 can run in parallel (independent git tools)
- T048, T049 can run in parallel (different factory functions)
- All test tasks marked [P] can run in parallel (different test files)

---

## Parallel Example: Setup Phase

```bash
# Launch all module creation together:
Task: "Add NotificationToolsError, GitToolsError, ValidationToolsError to src/maverick/exceptions.py"
Task: "Create empty src/maverick/tools/notification.py module"
Task: "Create empty src/maverick/tools/git.py module"
Task: "Create empty src/maverick/tools/validation.py module"
```

## Parallel Example: Git Tools (US5)

```bash
# Launch both git query tools together:
Task: "Implement git_current_branch @tool function in src/maverick/tools/git.py"
Task: "Implement git_diff_stats @tool function in src/maverick/tools/git.py"
```

---

## Implementation Strategy

### MVP First (P1 User Stories Only)

1. Complete Phase 1: Setup (T001-T006)
2. Complete Phase 2: Foundational (T007-T014)
3. Complete Phase 3: US1 - Workflow Notifications (T015-T018)
4. Complete Phase 4: US2 - git_commit (T019-T023)
5. Complete Phase 5: US3 - Validation (T024-T030)
6. Complete Phase 10: Factory Functions (T047-T050)
7. **STOP and VALIDATE**: All P1 tools functional
8. Add tests and polish as needed

### Incremental Delivery

1. Setup + Foundational → Core infrastructure ready
2. Add US1 → Workflow notifications working (MVP notification capability)
3. Add US2 → git_commit working (MVP commit capability)
4. Add US3 → Validation working (MVP validation capability)
5. Add US4, US5, US6 → Full git tooling
6. Add US7 → Full notification customization
7. Each story adds capability without breaking previous

### Parallel Team Strategy

With multiple developers:
1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: US1 + US7 (notification tools)
   - Developer B: US2 + US4 + US5 + US6 (git tools)
   - Developer C: US3 (validation tools)
3. All converge on Phase 10 (Factory Functions) and Phase 11 (Tests)

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Follow existing patterns from `src/maverick/tools/github.py`
- Use aiohttp for notification HTTP calls (async-first)
- Use asyncio.subprocess for git and validation commands (async-first)
- Graceful degradation for notifications: never block workflow
- Commit after each task or logical group
