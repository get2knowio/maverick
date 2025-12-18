# Tasks: Textual TUI Layout and Theming

**Input**: Design documents from `/specs/011-tui-layout-theming/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Not explicitly requested in spec - test tasks omitted per task generation rules.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `src/maverick/tui/` module extends existing codebase
- **Tests**: `tests/unit/tui/` and `tests/integration/tui/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and TUI directory structure

- [X] T001 Create TUI directory structure: `src/maverick/tui/screens/` and `src/maverick/tui/widgets/`
- [X] T002 [P] Create screens package init in `src/maverick/tui/screens/__init__.py` with public exports
- [X] T003 [P] Create widgets package init in `src/maverick/tui/widgets/__init__.py` with public exports

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core TUI infrastructure that MUST be complete before ANY user story can be implemented

**CRITICAL**: No user story work can begin until this phase is complete

- [X] T004 Create data models (StageStatus, ScreenState, LogEntry, ThemeColors, etc.) in `src/maverick/tui/models.py`
- [X] T005 Create stylesheet with theme colors and layout rules in `src/maverick/tui/maverick.tcss`
- [X] T006 [P] Create StageIndicator widget with status icons (pending ○, active ◉, completed ✓, failed ✗) in `src/maverick/tui/widgets/stage_indicator.py`
- [X] T007 [P] Create LogPanel widget with RichLog, 1000-line buffer, and toggle visibility in `src/maverick/tui/widgets/log_panel.py`
- [X] T008 Update TUI package init with public exports (MaverickApp, screens, widgets) in `src/maverick/tui/__init__.py`

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 1 - Launching the Application (Priority: P1) MVP

**Goal**: User launches Maverick and sees a well-organized interface with header, sidebar, main content, and footer

**Independent Test**: Launch app and verify main layout renders with all structural components visible

### Implementation for User Story 1

- [X] T009 [US1] Create MaverickApp class with CSS_PATH, TITLE, ENABLE_COMMAND_PALETTE, and BINDINGS in `src/maverick/tui/app.py`
- [X] T010 [US1] Implement MaverickApp.compose() yielding Header, main container (Horizontal with sidebar + content area), LogPanel, Footer in `src/maverick/tui/app.py`
- [X] T011 [US1] Implement MaverickApp.on_mount() to push initial HomeScreen in `src/maverick/tui/app.py`
- [X] T012 [US1] Implement action_toggle_log(), action_pop_screen(), action_quit() in `src/maverick/tui/app.py`
- [X] T013 [US1] Implement add_log() convenience method delegating to LogPanel in `src/maverick/tui/app.py`
- [X] T014 [P] [US1] Create Sidebar widget in navigation mode with menu items (Home, Workflows, Settings) in `src/maverick/tui/widgets/sidebar.py`
- [X] T015 [US1] Create basic HomeScreen with welcome message placeholder in `src/maverick/tui/screens/home.py`

**Checkpoint**: User Story 1 complete - app launches with visible header, sidebar, content, footer, and footer shows keybindings

---

## Phase 4: User Story 2 - Navigating Between Screens (Priority: P1)

**Goal**: User can navigate between views using keyboard shortcuts and command palette

**Independent Test**: Navigate through all screens using keyboard shortcuts; verify each screen displays correctly

### Implementation for User Story 2

- [X] T016 [P] [US2] Create WorkflowScreen placeholder in `src/maverick/tui/screens/workflow.py`
- [X] T017 [P] [US2] Create ReviewScreen placeholder in `src/maverick/tui/screens/review.py`
- [X] T018 [P] [US2] Create ConfigScreen placeholder in `src/maverick/tui/screens/config.py`
- [X] T019 [US2] Add screen navigation actions to HomeScreen (select workflow pushes WorkflowScreen) in `src/maverick/tui/screens/home.py`
- [X] T020 [US2] Implement command palette command provider for Maverick commands in `src/maverick/tui/app.py`
- [X] T021 [US2] Add action_show_help() keybinding handler in `src/maverick/tui/app.py`
- [X] T022 [US2] Update screens/__init__.py with all screen exports in `src/maverick/tui/screens/__init__.py`

**Checkpoint**: User Story 2 complete - all 4 screens navigable, Escape goes back, Ctrl+P opens command palette

---

## Phase 5: User Story 3 - Monitoring Workflow Progress (Priority: P1)

**Goal**: User starts a workflow and monitors progress with visual indicators in sidebar

**Independent Test**: Start mock workflow; verify stage progress indicators update correctly (checkmarks, spinners)

### Implementation for User Story 3

- [X] T023 [US3] Implement Sidebar.set_workflow_mode() to switch from navigation to workflow stages display in `src/maverick/tui/widgets/sidebar.py`
- [X] T024 [US3] Implement Sidebar.update_stage_status() to update individual stage indicators in `src/maverick/tui/widgets/sidebar.py`
- [X] T025 [US3] Implement WorkflowScreen with stage indicators, workflow name, and elapsed time display in `src/maverick/tui/screens/workflow.py`
- [X] T026 [US3] Implement WorkflowScreen.update_stage() and show_stage_error() methods in `src/maverick/tui/screens/workflow.py`
- [X] T027 [US3] Implement MaverickApp.start_timer() and stop_timer() for elapsed time tracking in `src/maverick/tui/app.py`
- [X] T028 [US3] Add Header subtitle showing current workflow name and elapsed time in `src/maverick/tui/app.py`

**Checkpoint**: User Story 3 complete - workflow stages show in sidebar with status icons; elapsed time updates

---

## Phase 6: User Story 4 - Viewing Agent Output Logs (Priority: P2)

**Goal**: User can expand/collapse log panel to view streaming agent output

**Independent Test**: Toggle log panel with Ctrl+L; verify agent output streams correctly

### Implementation for User Story 4

- [X] T029 [US4] Enhance LogPanel.add_log() with timestamp, source prefix, and level-based coloring in `src/maverick/tui/widgets/log_panel.py`
- [X] T030 [US4] Implement LogPanel auto-scroll behavior in `src/maverick/tui/widgets/log_panel.py`
- [X] T031 [US4] Add log panel CSS styles for visible/hidden states with <200ms toggle response in `src/maverick/tui/maverick.tcss`
- [X] T032 [US4] Verify log buffer respects 1000-line limit per clarifications in `src/maverick/tui/widgets/log_panel.py`

**Checkpoint**: User Story 4 complete - log panel toggles with Ctrl+L, shows timestamped colored output

---

## Phase 7: User Story 5 - Reviewing Code Review Results (Priority: P2)

**Goal**: User views organized code review results with severity-based coloring

**Independent Test**: Navigate to review screen with mock data; verify results display with correct colors

### Implementation for User Story 5

- [X] T033 [US5] Implement ReviewScreen.compose() with issue list and detail view layout in `src/maverick/tui/screens/review.py`
- [X] T034 [US5] Implement ReviewScreen.load_issues() to populate issue list in `src/maverick/tui/screens/review.py`
- [X] T035 [US5] Implement ReviewScreen.filter_by_severity() for filtering by error/warning/info in `src/maverick/tui/screens/review.py`
- [X] T036 [US5] Implement issue navigation (n/p for next/previous) with highlight in `src/maverick/tui/screens/review.py`
- [X] T037 [US5] Add severity-based CSS styling (error=red, warning=yellow, info=blue) in `src/maverick/tui/maverick.tcss`

**Checkpoint**: User Story 5 complete - review screen shows organized issues with severity colors

---

## Phase 8: User Story 6 - Configuring Application Settings (Priority: P3)

**Goal**: User can access settings screen and modify configuration values

**Independent Test**: Navigate to config screen; verify settings display and can be modified

### Implementation for User Story 6

- [X] T038 [US6] Implement ConfigScreen.compose() with options list layout in `src/maverick/tui/screens/config.py`
- [X] T039 [US6] Implement ConfigScreen.load_config() to load current MaverickConfig values in `src/maverick/tui/screens/config.py`
- [X] T040 [US6] Implement ConfigScreen.edit_option() for inline editing in `src/maverick/tui/screens/config.py`
- [X] T041 [US6] Implement ConfigScreen.save_option() and cancel_edit() in `src/maverick/tui/screens/config.py`
- [X] T042 [US6] Add keyboard shortcut (Ctrl+,) to navigate to ConfigScreen from any screen in `src/maverick/tui/app.py`

**Checkpoint**: User Story 6 complete - settings accessible and editable

---

## Phase 9: User Story 7 - Selecting Recent Workflows (Priority: P3)

**Goal**: User can view and select recent workflows from home screen

**Independent Test**: View home screen; verify 10 most recent workflows appear and are selectable

### Implementation for User Story 7

- [X] T043 [P] [US7] Create WorkflowList widget displaying recent workflow entries in `src/maverick/tui/widgets/workflow_list.py`
- [X] T044 [US7] Implement WorkflowList.set_workflows() and select() methods in `src/maverick/tui/widgets/workflow_list.py`
- [X] T045 [US7] Enhance HomeScreen with WorkflowList integration in `src/maverick/tui/screens/home.py`
- [X] T046 [US7] Implement HomeScreen.refresh_recent_workflows() loading 10 most recent in `src/maverick/tui/screens/home.py`
- [X] T047 [US7] Add workflow list CSS styles with hover and selected states in `src/maverick/tui/maverick.tcss`

**Checkpoint**: User Story 7 complete - home screen shows recent workflows with selection

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: Edge cases, validation, and improvements across all stories

- [X] T048 Implement minimum terminal size warning overlay (80x24) in `src/maverick/tui/app.py`
- [X] T049 Add terminal resize handler showing warning when below minimum in `src/maverick/tui/app.py`
- [X] T050 [P] Verify all status colors are distinguishable and WCAG AA compliant in `src/maverick/tui/maverick.tcss`
- [X] T051 [P] Ensure unbound key presses do not crash or display errors in `src/maverick/tui/app.py`
- [X] T052 Run quickstart.md validation scenarios to verify all patterns work correctly
- [X] T053 Update widgets/__init__.py with final exports in `src/maverick/tui/widgets/__init__.py`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3-9)**: All depend on Foundational phase completion
  - US1 (P1): Foundation only
  - US2 (P1): Depends on US1 (needs app structure)
  - US3 (P1): Depends on US1, US2 (needs screens and sidebar)
  - US4 (P2): Depends on US1 (needs LogPanel in app)
  - US5 (P2): Depends on US2 (needs ReviewScreen navigation)
  - US6 (P3): Depends on US2 (needs ConfigScreen navigation)
  - US7 (P3): Depends on US1 (needs HomeScreen)
- **Polish (Phase 10)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Foundation only - MVP starting point
- **User Story 2 (P1)**: Depends on US1 - extends app with navigation
- **User Story 3 (P1)**: Depends on US1, US2 - workflow progress display
- **User Story 4 (P2)**: Depends on US1 - log panel functionality
- **User Story 5 (P2)**: Depends on US2 - review screen content
- **User Story 6 (P3)**: Depends on US2 - config screen content
- **User Story 7 (P3)**: Depends on US1 - home screen enhancement

### Within Each User Story

- Models/infrastructure tasks before widget tasks
- Widgets before screens that use them
- Core implementation before integrations
- CSS updates can parallel with Python code

### Parallel Opportunities

- T002, T003 can run in parallel (package init files)
- T006, T007 can run in parallel (independent widgets)
- T016, T017, T018 can run in parallel (placeholder screens)
- T043 can run in parallel with other US7 tasks (independent widget)
- T050, T051 can run in parallel (independent polish tasks)

---

## Parallel Example: Phase 2 Foundational

```bash
# After T004, T005 complete (models and CSS):
Task: "Create StageIndicator widget in src/maverick/tui/widgets/stage_indicator.py"
Task: "Create LogPanel widget in src/maverick/tui/widgets/log_panel.py"
```

## Parallel Example: User Story 2

```bash
# All placeholder screens can be created in parallel:
Task: "Create WorkflowScreen placeholder in src/maverick/tui/screens/workflow.py"
Task: "Create ReviewScreen placeholder in src/maverick/tui/screens/review.py"
Task: "Create ConfigScreen placeholder in src/maverick/tui/screens/config.py"
```

---

## Implementation Strategy

### MVP First (User Stories 1-3)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1 - Basic app launch
4. Complete Phase 4: User Story 2 - Screen navigation
5. Complete Phase 5: User Story 3 - Workflow monitoring
6. **STOP and VALIDATE**: Core TUI functional with all navigation and workflow display

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add US1 → App launches with layout → Demo
3. Add US2 → All screens navigable → Demo
4. Add US3 → Workflow progress visible → Demo (Core MVP!)
5. Add US4 → Log panel working → Demo
6. Add US5 → Review results display → Demo
7. Add US6 → Settings editable → Demo
8. Add US7 → Recent workflows → Demo (Full Feature!)
9. Complete Polish → Production ready

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Performance targets: <200ms log toggle, <1s stage update (SC-004, SC-003)
- Minimum terminal: 80x24 (clarification)
- Log buffer: 1000 lines (clarification)
