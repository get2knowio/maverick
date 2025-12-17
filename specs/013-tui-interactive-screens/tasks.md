# Tasks: TUI Interactive Screens

**Input**: Design documents from `/specs/013-tui-interactive-screens/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Test tasks are included per Maverick's Test-First principle (constitution principle V).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `src/maverick/`, `tests/unit/` at repository root
- Extends existing TUI structure in `src/maverick/tui/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and foundational components needed by all screens

- [X] T001 Create MaverickScreen base class with navigation and modal support in src/maverick/tui/screens/base.py
- [X] T002 [P] Create data models for screen states in src/maverick/tui/models.py (extend existing)
- [X] T003 [P] Create WorkflowHistoryEntry and WorkflowHistoryStore in src/maverick/tui/history.py

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Modal dialogs and form widgets that MUST be complete before ANY user story can be implemented

**CRITICAL**: No user story work can begin until this phase is complete

- [X] T004 [P] Create ConfirmDialog modal widget in src/maverick/tui/widgets/modal.py
- [X] T005 [P] Create ErrorDialog modal widget in src/maverick/tui/widgets/modal.py
- [X] T006 [P] Create InputDialog modal widget in src/maverick/tui/widgets/modal.py
- [X] T007 [P] Create BranchInputField form widget in src/maverick/tui/widgets/form.py
- [X] T008 [P] Create NumericField form widget in src/maverick/tui/widgets/form.py
- [X] T009 [P] Create ToggleField form widget in src/maverick/tui/widgets/form.py
- [X] T010 [P] Create SelectField form widget in src/maverick/tui/widgets/form.py
- [X] T011 [P] Create test fixtures and mocks for modal and form widgets in tests/unit/tui/widgets/test_modal.py
- [X] T012 [P] Create test fixtures and mocks for form widgets in tests/unit/tui/widgets/test_form.py
- [X] T013 Update MaverickApp with navigation context in src/maverick/tui/app.py
- [X] T014 Extend maverick.tcss with styles for new widgets and screens in src/maverick/tui/maverick.tcss

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 5 - Navigating Between Screens (Priority: P1)

**Goal**: Enable fluid navigation between screens using keyboard and mouse, with modal dialog support

**Independent Test**: Navigate through all screens using keyboard and mouse, verify back navigation and modal behavior

**Why First**: Screen navigation is foundational - all other functionality depends on users being able to navigate the application

### Tests for User Story 5

- [X] T015 [P] [US5] Test screen navigation from HomeScreen to Fly/Refuel/Settings in tests/unit/tui/screens/test_navigation.py
- [X] T016 [P] [US5] Test Escape key back navigation in tests/unit/tui/screens/test_navigation.py
- [X] T017 [P] [US5] Test modal dialog overlay behavior in tests/unit/tui/widgets/test_modal.py

### Implementation for User Story 5

- [X] T018 [US5] Implement navigation methods in MaverickScreen base class in src/maverick/tui/screens/base.py
- [X] T019 [US5] Update HomeScreen with navigation to Fly/Refuel/Settings in src/maverick/tui/screens/home.py
- [X] T020 [US5] Add keyboard bindings (Escape, Enter, arrow keys) for navigation in src/maverick/tui/screens/base.py
- [X] T021 [US5] Implement modal focus trapping and background dimming in src/maverick/tui/widgets/modal.py

**Checkpoint**: At this point, User Story 5 should be fully functional and testable independently

---

## Phase 4: User Story 1 - Launching a Fly Workflow (Priority: P1)

**Goal**: Enable developers to configure and start a Fly workflow with branch name validation and live progress display

**Independent Test**: Navigate to FlyScreen, enter a valid branch name, start the workflow with mock data, verify progress display and transition to ReviewScreen

### Tests for User Story 1

- [X] T022 [P] [US1] Test branch name validation (empty, invalid chars, valid) in tests/unit/tui/screens/test_fly.py
- [X] T023 [P] [US1] Test FlyScreen state management in tests/unit/tui/screens/test_fly.py
- [X] T024 [P] [US1] Test workflow start and screen transition in tests/unit/tui/screens/test_fly.py

### Implementation for User Story 1

- [X] T025 [US1] Create FlyScreen class structure with compose layout in src/maverick/tui/screens/fly.py
- [X] T026 [US1] Implement branch name validation with real-time feedback (<200ms) in src/maverick/tui/screens/fly.py
- [X] T027 [US1] Implement branch existence check (local and remote) in src/maverick/tui/screens/fly.py
- [X] T028 [US1] Implement optional task file selector in src/maverick/tui/screens/fly.py
- [X] T029 [US1] Implement Start/Cancel button handlers in src/maverick/tui/screens/fly.py
- [X] T030 [US1] Implement workflow start with WorkflowProgress widget integration in src/maverick/tui/screens/fly.py
- [X] T031 [US1] Implement automatic transition to ReviewScreen on code review completion in src/maverick/tui/screens/fly.py
- [X] T032 [US1] Add FlyScreen to screen exports in src/maverick/tui/screens/__init__.py

**Checkpoint**: At this point, User Story 1 should be fully functional and testable independently

---

## Phase 5: User Story 2 - Reviewing Code Findings (Priority: P1)

**Goal**: Enable developers to review and act on code review findings with approve, request changes, dismiss, and fix all actions

**Independent Test**: Mount ReviewScreen with mock findings, verify finding display/grouping, side panel diff display, and all action buttons function correctly

### Tests for User Story 2

- [X] T033 [P] [US2] Test ReviewScreen finding display and grouping in tests/unit/tui/screens/test_review.py
- [X] T034 [P] [US2] Test ReviewScreen action handlers (approve, request changes, dismiss, fix all) in tests/unit/tui/screens/test_review.py
- [X] T035 [P] [US2] Test side panel diff display in tests/unit/tui/screens/test_review.py

### Implementation for User Story 2

- [X] T036 [US2] Enhance ReviewScreen with action state management in src/maverick/tui/screens/review.py
- [X] T037 [US2] Implement Approve action with confirmation dialog in src/maverick/tui/screens/review.py
- [X] T038 [US2] Implement Request Changes action with input dialog for comments in src/maverick/tui/screens/review.py
- [X] T039 [US2] Implement Dismiss action for individual findings in src/maverick/tui/screens/review.py
- [X] T040 [US2] Implement Fix All action with confirmation and result display in src/maverick/tui/screens/review.py
- [X] T040a [US2] Integrate Fix All action with IssueFixerAgent execution - invoke agent with findings, handle async results, update UI with per-finding success/failure in src/maverick/tui/screens/review.py
- [X] T041 [US2] Implement side panel for file diff display with finding location highlighting in src/maverick/tui/screens/review.py
- [X] T042 [US2] Add keyboard bindings for review actions (a=approve, r=request changes, d=dismiss, f=fix) in src/maverick/tui/screens/review.py
- [X] T042a [US2] Implement real-time finding update notification - watch for new findings during review, display "New findings available" banner with refresh button in src/maverick/tui/screens/review.py

**Checkpoint**: At this point, User Stories 1 AND 2 should both work independently

---

## Phase 6: User Story 3 - Processing Issues with RefuelScreen (Priority: P1)

**Goal**: Enable developers to select and process tech debt issues with label filtering, issue selection, and results summary

**Independent Test**: Mount RefuelScreen, enter a label filter, view the issue list, select issues, start execution, and verify the results summary displays

### Tests for User Story 3

- [X] T043 [P] [US3] Test RefuelScreen label filter and issue fetching in tests/unit/tui/screens/test_refuel.py
- [X] T044 [P] [US3] Test issue selection and count updates in tests/unit/tui/screens/test_refuel.py
- [X] T045 [P] [US3] Test processing mode toggle (parallel/sequential) in tests/unit/tui/screens/test_refuel.py
- [X] T046 [P] [US3] Test results summary display in tests/unit/tui/screens/test_refuel.py

### Implementation for User Story 3

- [X] T047 [P] [US3] Create IssueListItem widget in src/maverick/tui/widgets/issue_list.py
- [X] T048 [P] [US3] Create IssueList widget with selection support in src/maverick/tui/widgets/issue_list.py
- [X] T049 [P] [US3] Create ResultSummary widget for displaying processing results in src/maverick/tui/widgets/result_summary.py
- [X] T050 [US3] Create RefuelScreen class structure with compose layout in src/maverick/tui/screens/refuel.py
- [X] T051 [US3] Implement label filter input and issue fetching via gh CLI in src/maverick/tui/screens/refuel.py
- [X] T052 [US3] Implement issue limit selector (1-10) in src/maverick/tui/screens/refuel.py
- [X] T053 [US3] Implement parallel/sequential toggle in src/maverick/tui/screens/refuel.py
- [X] T054 [US3] Implement issue selection with checkboxes and vim-style navigation in src/maverick/tui/screens/refuel.py
- [X] T055 [US3] Implement Start button with selected issue validation in src/maverick/tui/screens/refuel.py
- [X] T056 [US3] Implement workflow execution with progress indicators in src/maverick/tui/screens/refuel.py
- [X] T057 [US3] Implement results summary with success/failure per issue and PR links in src/maverick/tui/screens/refuel.py
- [X] T058 [US3] Add RefuelScreen to screen exports in src/maverick/tui/screens/__init__.py
- [X] T059 [P] [US3] Create tests for IssueList widget in tests/unit/tui/widgets/test_issue_list.py

**Checkpoint**: At this point, User Stories 1, 2, AND 3 should all work independently

---

## Phase 7: User Story 4 - Configuring Application Settings (Priority: P2)

**Goal**: Enable developers to configure Maverick settings with form-based interface, test connections, and save/cancel support

**Independent Test**: Navigate to SettingsScreen, modify a setting, test GitHub connection, and verify save/cancel behavior

### Tests for User Story 4

- [X] T060 [P] [US4] Test SettingsScreen setting load and display in tests/unit/tui/screens/test_settings.py
- [X] T061 [P] [US4] Test unsaved changes tracking and navigation confirmation in tests/unit/tui/screens/test_settings.py
- [X] T062 [P] [US4] Test setting validation in tests/unit/tui/screens/test_settings.py
- [X] T063 [P] [US4] Test GitHub connection test action in tests/unit/tui/screens/test_settings.py
- [X] T064 [P] [US4] Test notification test action in tests/unit/tui/screens/test_settings.py

### Implementation for User Story 4

- [X] T065 [P] [US4] Create SettingsSection widget in src/maverick/tui/widgets/settings.py
- [X] T066 [P] [US4] Create SettingField widget variants (string, bool, int, choice) in src/maverick/tui/widgets/settings.py
- [X] T067 [US4] Create SettingsScreen class structure with compose layout in src/maverick/tui/screens/settings.py
- [X] T068 [US4] Implement settings load from Maverick config in src/maverick/tui/screens/settings.py
- [X] T069 [US4] Implement settings sections (GitHub, Notifications, Agents) in src/maverick/tui/screens/settings.py
- [X] T070 [US4] Implement Test GitHub Connection button with status feedback in src/maverick/tui/screens/settings.py
- [X] T071 [US4] Implement Test Notification button with confirmation in src/maverick/tui/screens/settings.py
- [X] T072 [US4] Implement unsaved changes tracking in src/maverick/tui/screens/settings.py
- [X] T073 [US4] Implement Save/Cancel with validation in src/maverick/tui/screens/settings.py
- [X] T074 [US4] Implement navigation confirmation dialog for unsaved changes in src/maverick/tui/screens/settings.py
- [X] T075 [US4] Add SettingsScreen to screen exports (replace config.py) in src/maverick/tui/screens/__init__.py
- [X] T076 [P] [US4] Create tests for settings widgets in tests/unit/tui/widgets/test_settings.py

**Checkpoint**: At this point, User Stories 1-4 should all work independently

---

## Phase 8: User Story 6 - Cancelling Active Workflows (Priority: P2)

**Goal**: Enable developers to cancel running workflows with confirmation and graceful shutdown summary

**Independent Test**: Start a mock workflow, trigger cancel, confirm, and verify graceful shutdown and summary display

### Tests for User Story 6

- [X] T077 [P] [US6] Test cancel confirmation dialog in tests/unit/tui/screens/test_workflow_cancel.py
- [X] T078 [P] [US6] Test graceful shutdown on cancel in tests/unit/tui/screens/test_workflow_cancel.py
- [X] T079 [P] [US6] Test cancellation summary display in tests/unit/tui/screens/test_workflow_cancel.py

### Implementation for User Story 6

- [X] T080 [US6] Implement Cancel button in FlyScreen during workflow execution in src/maverick/tui/screens/fly.py
- [X] T081 [US6] Implement Cancel button in RefuelScreen during workflow execution in src/maverick/tui/screens/refuel.py
- [X] T082 [US6] Implement cancel confirmation dialog with "Progress will be lost" warning in src/maverick/tui/screens/base.py
- [X] T083 [US6] Implement graceful workflow shutdown on cancel confirmation in src/maverick/tui/screens/fly.py
- [X] T084 [US6] Implement graceful workflow shutdown on cancel confirmation in src/maverick/tui/screens/refuel.py
- [X] T085 [US6] Implement cancellation summary showing stages completed before cancellation in src/maverick/tui/screens/fly.py
- [X] T086 [US6] Implement cancellation summary showing issues processed before cancellation in src/maverick/tui/screens/refuel.py

**Checkpoint**: At this point, User Stories 1-6 should all work independently

---

## Phase 9: User Story 7 - Viewing Workflow History (Priority: P3)

**Goal**: Enable developers to view recent workflow runs and navigate to historical workflow results

**Independent Test**: Populate mock history data and verify navigation to historical workflow views

### Tests for User Story 7

- [X] T087 [P] [US7] Test workflow history load and display in tests/unit/tui/screens/test_home.py
- [X] T088 [P] [US7] Test workflow history entry selection in tests/unit/tui/screens/test_home.py
- [X] T089 [P] [US7] Test historical workflow view navigation in tests/unit/tui/screens/test_home.py
- [X] T090 [P] [US7] Test WorkflowHistoryStore FIFO eviction in tests/unit/tui/test_history.py

### Implementation for User Story 7

- [X] T091 [US7] Enhance HomeScreen with history display using WorkflowList widget in src/maverick/tui/screens/home.py
- [X] T092 [US7] Implement history loading from WorkflowHistoryStore in src/maverick/tui/screens/home.py
- [X] T093 [US7] Implement workflow history entry selection and highlighting in src/maverick/tui/screens/home.py
- [X] T094 [US7] Implement navigation to read-only historical workflow view in src/maverick/tui/screens/home.py
- [X] T095 [US7] Create HistoricalReviewScreen for viewing past findings (read-only) in src/maverick/tui/screens/history_review.py
- [X] T096 [US7] Implement workflow history recording on workflow completion in src/maverick/tui/screens/fly.py
- [X] T097 [US7] Implement workflow history recording on workflow completion in src/maverick/tui/screens/refuel.py

**Checkpoint**: All user stories should now be independently functional

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [ ] T098 [P] Add comprehensive CSS styles for all screens in src/maverick/tui/maverick.tcss
- [ ] T099 [P] Add keyboard shortcut help footer to all screens in src/maverick/tui/screens/base.py
- [ ] T100 [P] Ensure 100% keyboard accessibility across all screens in src/maverick/tui/screens/
- [ ] T101 [P] Add loading spinners and progress indicators for async operations in src/maverick/tui/widgets/
- [ ] T101a [P] Implement network connectivity monitor with retry logic for GitHub API and git operations in src/maverick/tui/utils/connectivity.py
- [ ] T101b Implement workflow pause/resume on connectivity loss/restore in src/maverick/tui/screens/fly.py and src/maverick/tui/screens/refuel.py
- [ ] T102 Performance optimization for screen transitions (<300ms target) in src/maverick/tui/app.py
- [ ] T103 [P] Update screen exports and __all__ in src/maverick/tui/screens/__init__.py
- [ ] T104 [P] Update widget exports and __all__ in src/maverick/tui/widgets/__init__.py
- [ ] T105 Run quickstart.md validation scenarios

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Story 5 (Phase 3)**: Depends on Foundational - navigation must work first
- **User Stories 1-4, 6-7 (Phases 4-9)**: All depend on User Story 5 completion
  - User stories can then proceed in parallel (if staffed)
  - Or sequentially in priority order (P1 → P2 → P3)
- **Polish (Final Phase)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 5 (P1)**: Navigation - MUST be completed first (all screens depend on navigation)
- **User Story 1 (P1)**: FlyScreen - Can start after US5
- **User Story 2 (P1)**: ReviewScreen - Can start after US5 (US1 transitions to it but can be tested independently)
- **User Story 3 (P1)**: RefuelScreen - Can start after US5
- **User Story 4 (P2)**: SettingsScreen - Can start after US5
- **User Story 6 (P2)**: Cancel workflows - Depends on US1 and US3 having basic workflow start
- **User Story 7 (P3)**: History - Can start after US5 (integrates with US1/US3 on completion)

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- Base screen structure before specific features
- State management before UI updates
- Core implementation before integration
- Story complete before moving to next priority

### Parallel Opportunities

- All Setup tasks can run in parallel (T001-T003)
- All Foundational tasks marked [P] can run in parallel (T004-T014)
- Once US5 completes, US1, US2, US3, US4 can start in parallel
- All tests for a user story marked [P] can run in parallel
- Different user stories can be worked on in parallel by different team members

---

## Parallel Example: User Story 3 (RefuelScreen)

```bash
# Launch all tests for User Story 3 together:
Task: "Test RefuelScreen label filter and issue fetching in tests/unit/tui/screens/test_refuel.py"
Task: "Test issue selection and count updates in tests/unit/tui/screens/test_refuel.py"
Task: "Test processing mode toggle in tests/unit/tui/screens/test_refuel.py"
Task: "Test results summary display in tests/unit/tui/screens/test_refuel.py"

# Launch all widgets for User Story 3 together:
Task: "Create IssueListItem widget in src/maverick/tui/widgets/issue_list.py"
Task: "Create IssueList widget with selection support in src/maverick/tui/widgets/issue_list.py"
Task: "Create ResultSummary widget in src/maverick/tui/widgets/result_summary.py"
```

---

## Implementation Strategy

### MVP First (User Stories 5 + 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 5 (Navigation)
4. Complete Phase 4: User Story 1 (FlyScreen)
5. **STOP and VALIDATE**: Test navigation and FlyScreen independently
6. Deploy/demo if ready

### Incremental Delivery

1. Complete Setup + Foundational + US5 → Navigation ready
2. Add User Story 1 → Test independently → Deploy/Demo (MVP!)
3. Add User Story 2 → Test independently → Deploy/Demo (Review actions)
4. Add User Story 3 → Test independently → Deploy/Demo (RefuelScreen)
5. Add User Story 4 → Test independently → Deploy/Demo (Settings)
6. Add User Story 6 → Test independently → Deploy/Demo (Cancellation)
7. Add User Story 7 → Test independently → Deploy/Demo (History)
8. Each story adds value without breaking previous stories

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational + US5 together
2. Once US5 is done:
   - Developer A: User Story 1 (FlyScreen)
   - Developer B: User Story 2 (ReviewScreen enhancements)
   - Developer C: User Story 3 (RefuelScreen)
   - Developer D: User Story 4 (SettingsScreen)
3. Stories complete and integrate independently
4. US6 and US7 can be picked up after their dependencies complete

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verify tests fail before implementing
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Avoid: vague tasks, same file conflicts, cross-story dependencies that break independence
- US5 (Navigation) is strategically first because it is foundational for all screens
