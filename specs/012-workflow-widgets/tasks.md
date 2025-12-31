# Tasks: Workflow Visualization Widgets

**Input**: Design documents from `/specs/012-workflow-widgets/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Tests are included as this is a TUI feature requiring TDD with pytest + Textual's pilot fixture.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `src/maverick/tui/`, `tests/unit/tui/` at repository root

---

## Phase 1: Setup (Shared Infrastructure) ✅ COMPLETE

**Purpose**: Project initialization and data model foundation

- [X] T001 Extend enums in src/maverick/tui/models.py with MessageType, FindingSeverity, ValidationStepStatus, PRState, CheckStatus
- [X] T002 [P] Add ToolCallInfo dataclass to src/maverick/tui/models.py
- [X] T003 [P] Add CodeLocation dataclass to src/maverick/tui/models.py
- [X] T004 [P] Add StatusCheck dataclass to src/maverick/tui/models.py

---

## Phase 2: Foundational (Core Data Models) ✅ COMPLETE

**Purpose**: Core data models that ALL user stories depend on

**CRITICAL**: No widget implementation can begin until this phase is complete

- [X] T005 Add WorkflowStage dataclass with duration_seconds and duration_display properties to src/maverick/tui/models.py
- [X] T006 [P] Add AgentMessage dataclass to src/maverick/tui/models.py
- [X] T007 [P] Add ReviewFinding and ReviewFindingItem dataclasses to src/maverick/tui/models.py
- [X] T008 [P] Add CodeContext dataclass to src/maverick/tui/models.py
- [X] T009 [P] Add ValidationStep dataclass to src/maverick/tui/models.py
- [X] T010 [P] Add PRInfo dataclass with description_preview property to src/maverick/tui/models.py
- [X] T011 Add WorkflowProgressState dataclass with current_stage and is_empty properties to src/maverick/tui/models.py
- [X] T012 [P] Add AgentOutputState mutable dataclass with add_message method to src/maverick/tui/models.py
- [X] T013 [P] Add ReviewFindingsState dataclass with findings_by_severity property to src/maverick/tui/models.py
- [X] T014 [P] Add ValidationStatusState dataclass with all_passed, has_failures, is_running properties to src/maverick/tui/models.py
- [X] T015 [P] Add PRSummaryState dataclass to src/maverick/tui/models.py
- [X] T016 Add unit tests for all new data models in tests/unit/tui/test_models.py
- [X] T017 Export all new models from src/maverick/tui/models.py __all__

**Checkpoint**: Foundation ready - widget implementation can now begin

---

## Phase 3: User Story 1 - Monitoring Workflow Progress (Priority: P1) ✅ COMPLETE

**Goal**: Developers see each workflow stage with status icons, durations, and expandable details

**Independent Test**: Mount WorkflowProgress widget with mock stage data and verify status icons, durations, and expansion behavior

### Tests for User Story 1

- [X] T018 [P] [US1] Create test file tests/unit/tui/widgets/test_workflow_progress.py with test app fixture
- [X] T019 [P] [US1] Test WorkflowProgress displays all stages vertically with names and pending status icons
- [X] T020 [P] [US1] Test WorkflowProgress shows animated spinner icon for active stage
- [X] T021 [P] [US1] Test WorkflowProgress shows checkmark and duration for completed stages
- [X] T022 [P] [US1] Test WorkflowProgress shows error icon in red for failed stages
- [X] T023 [P] [US1] Test WorkflowProgress expands stage on Enter key to show detail content
- [X] T024 [P] [US1] Test WorkflowProgress displays loading state when loading=True
- [X] T025 [P] [US1] Test WorkflowProgress displays empty state when no stages

### Implementation for User Story 1

- [X] T026 [US1] Create WorkflowProgress widget in src/maverick/tui/widgets/workflow_progress.py with reactive stages property
- [X] T027 [US1] Implement compose() method with vertical stage list using Collapsible for each stage
- [X] T028 [US1] Implement status icon rendering (pending circle, active spinner, completed checkmark, error X)
- [X] T029 [US1] Implement duration display for completed stages using WorkflowStage.duration_display
- [X] T030 [US1] Implement update_stages() and update_stage_status() methods per WorkflowProgressProtocol
- [X] T031 [US1] Implement expand_stage() and collapse_stage() methods with StageExpanded/StageCollapsed messages
- [X] T032 [US1] Implement loading and empty state rendering
- [X] T033 [US1] Add CSS styles for workflow-progress in src/maverick/tui/maverick.tcss

**Checkpoint**: WorkflowProgress widget fully functional with all status states (30 tests passing)

---

## Phase 4: User Story 2 - Viewing Agent Output (Priority: P1) ✅ COMPLETE

**Goal**: Developers see streaming agent messages with syntax highlighting, collapsible tool calls, and search

**Independent Test**: Stream mock agent messages and verify rendering, syntax highlighting, tool call collapse/expand, scroll behavior

### Tests for User Story 2

- [X] T034 [P] [US2] Create test file tests/unit/tui/widgets/test_agent_output.py with test app fixture
- [X] T035 [P] [US2] Test AgentOutput displays messages with timestamps and agent identifiers
- [X] T036 [P] [US2] Test AgentOutput applies syntax highlighting to code blocks using Rich Syntax
- [X] T037 [P] [US2] Test AgentOutput renders tool calls as collapsible sections (collapsed by default)
- [X] T038 [P] [US2] Test AgentOutput auto-scrolls when user is at bottom
- [X] T039 [P] [US2] Test AgentOutput pauses auto-scroll when user scrolls up
- [X] T040 [P] [US2] Test AgentOutput shows "scroll to bottom" indicator when auto-scroll paused
- [X] T041 [P] [US2] Test AgentOutput search highlights matching text on Ctrl+F
- [X] T042 [P] [US2] Test AgentOutput filters by agent name
- [X] T043 [P] [US2] Test AgentOutput displays empty state when no messages
- [X] T044 [P] [US2] Test AgentOutput truncates oldest messages when buffer exceeds 1000

### Implementation for User Story 2

- [X] T045 [US2] Create AgentOutput widget in src/maverick/tui/widgets/agent_output.py extending ScrollableContainer
- [X] T046 [US2] Implement message rendering with timestamps, agent identifiers using RichLog
- [X] T047 [US2] Implement syntax highlighting for code blocks using Rich Syntax renderable
- [X] T048 [US2] Implement tool call rendering as Collapsible sections
- [X] T049 [US2] Implement auto-scroll logic with scroll position detection (scroll_y, max_scroll_y)
- [X] T050 [US2] Implement scroll-to-bottom indicator when auto-scroll paused
- [X] T051 [US2] Implement search functionality with Ctrl+F binding and Input widget
- [X] T052 [US2] Implement agent filter with set_agent_filter() method
- [X] T053 [US2] Implement add_message(), clear_messages(), scroll_to_bottom() methods per AgentOutputProtocol
- [X] T054 [US2] Implement message buffer limit (1000) with truncation indicator
- [X] T055 [US2] Implement empty state rendering
- [X] T056 [US2] Add CSS styles for agent-output in src/maverick/tui/maverick.tcss

**Checkpoint**: AgentOutput widget fully functional with streaming, syntax highlighting, search (31 tests passing)

---

## Phase 5: User Story 3 - Reviewing Code Review Findings (Priority: P1) ✅ COMPLETE

**Goal**: Developers see findings grouped by severity with clickable file links, expansion, selection, and bulk actions

**Independent Test**: Mount ReviewFindings with mock finding data and verify grouping, expansion, navigation, bulk actions

### Tests for User Story 3

- [X] T057 [P] [US3] Create test file tests/unit/tui/widgets/test_review_findings.py with test app fixture
- [X] T058 [P] [US3] Test ReviewFindings groups findings by severity (errors first, warnings, suggestions)
- [X] T059 [P] [US3] Test ReviewFindings shows file:line as clickable link emitting FileLocationClicked message
- [X] T060 [P] [US3] Test ReviewFindings expands finding on Enter to show full details
- [X] T061 [P] [US3] Test ReviewFindings allows multi-select with checkboxes
- [X] T062 [P] [US3] Test ReviewFindings bulk dismiss removes selected findings
- [X] T063 [P] [US3] Test ReviewFindings bulk create issue emits BulkCreateIssueRequested message
- [X] T064 [P] [US3] Test ReviewFindings displays empty state "No review findings. All clear!"

### Implementation for User Story 3

- [X] T065 [US3] Create ReviewFindings widget in src/maverick/tui/widgets/review_findings.py
- [X] T066 [US3] Implement compose() with severity-grouped sections (error, warning, suggestion)
- [X] T067 [US3] Implement finding row with checkbox, severity icon, title, file:line link
- [X] T068 [US3] Implement file location click handler emitting FileLocationClicked message
- [X] T069 [US3] Implement finding expansion with Collapsible showing description and suggested_fix
- [X] T070 [US3] Implement multi-select with select_finding(), select_all(), deselect_all() methods
- [X] T071 [US3] Implement bulk dismiss button emitting BulkDismissRequested message
- [X] T072 [US3] Implement bulk create issue button emitting BulkCreateIssueRequested message
- [X] T073 [US3] Implement update_findings() and show_code_context() methods per ReviewFindingsProtocol
- [X] T074 [US3] Implement empty state rendering
- [X] T075 [US3] Add CSS styles for review-findings in src/maverick/tui/maverick.tcss

**Checkpoint**: ReviewFindings widget fully functional with grouping, selection, bulk actions (34 tests passing)

---

## Phase 6: User Story 4 - Checking Validation Status (Priority: P2) ✅ COMPLETE

**Goal**: Developers see compact validation step indicators with pass/fail, expandable errors, re-run buttons

**Independent Test**: Mount ValidationStatus with mock validation results and verify indicators, expansion, re-run

### Tests for User Story 4

- [X] T076 [P] [US4] Create test file tests/unit/tui/widgets/test_validation_status.py with test app fixture
- [X] T077 [P] [US4] Test ValidationStatus displays all steps in compact row with name and status icon
- [X] T078 [P] [US4] Test ValidationStatus shows green checkmark for passed steps
- [X] T079 [P] [US4] Test ValidationStatus shows red X for failed steps (expandable)
- [X] T080 [P] [US4] Test ValidationStatus shows expanded error output for failed step
- [X] T081 [P] [US4] Test ValidationStatus re-run button emits RerunRequested message
- [X] T082 [P] [US4] Test ValidationStatus disables re-run button while running
- [X] T083 [P] [US4] Test ValidationStatus displays loading state when loading=True

### Implementation for User Story 4

- [X] T084 [US4] Create ValidationStatus widget in src/maverick/tui/widgets/validation_status.py
- [X] T085 [US4] Implement compose() with horizontal/compact step layout
- [X] T086 [US4] Implement status icons (pending gray, running spinner, passed green, failed red)
- [X] T087 [US4] Implement failed step expansion with Collapsible showing error_output
- [X] T088 [US4] Implement re-run button with disabled state during running
- [X] T089 [US4] Implement update_steps(), update_step_status(), expand_step(), collapse_step() methods
- [X] T090 [US4] Implement set_rerun_enabled() method for button state control
- [X] T091 [US4] Implement loading state rendering
- [X] T092 [US4] Add CSS styles for validation-status in src/maverick/tui/maverick.tcss

**Checkpoint**: ValidationStatus widget fully functional with compact display and re-run (27 tests passing)

---

## Phase 7: User Story 5 - Viewing Pull Request Summary (Priority: P2) ✅ COMPLETE

**Goal**: Developers see PR title, description preview, status checks, and link to open in browser

**Independent Test**: Mount PRSummary with mock PR data and verify title, description, checks, link activation

### Tests for User Story 5

- [X] T093 [P] [US5] Create test file tests/unit/tui/widgets/test_pr_summary.py with test app fixture
- [X] T094 [P] [US5] Test PRSummary displays PR title and number prominently
- [X] T095 [P] [US5] Test PRSummary shows truncated description preview with expand option
- [X] T096 [P] [US5] Test PRSummary displays status checks with pass/fail/pending icons
- [X] T097 [P] [US5] Test PRSummary opens browser on link activation via webbrowser.open
- [X] T098 [P] [US5] Test PRSummary shows PR state icon (open, merged, closed)
- [X] T099 [P] [US5] Test PRSummary displays loading state when loading=True
- [X] T100 [P] [US5] Test PRSummary displays empty state when no PR

### Implementation for User Story 5

- [X] T101 [US5] Create PRSummary widget in src/maverick/tui/widgets/pr_summary.py
- [X] T102 [US5] Implement compose() with PR title, number, state icon, description, checks, link
- [X] T103 [US5] Implement description truncation with expand_description()/collapse_description() methods
- [X] T104 [US5] Implement status check display with pass/fail/pending icons
- [X] T105 [US5] Implement open_pr_in_browser() using webbrowser.open()
- [X] T106 [US5] Implement update_pr() and set_loading() methods per PRSummaryProtocol
- [X] T107 [US5] Implement loading and empty state rendering
- [X] T108 [US5] Add CSS styles for pr-summary in src/maverick/tui/maverick.tcss

**Checkpoint**: PRSummary widget fully functional with PR display and browser opening (20 tests passing)

---

## Phase 8: User Story 6 - Handling Loading and Empty States (Priority: P2) ✅ COMPLETE

**Goal**: All widgets display appropriate loading/empty states

**Independent Test**: Mount each widget with no data and verify loading/empty states render correctly

### Tests for User Story 6

- [X] T109 [P] [US6] Test all widgets display consistent loading skeleton/spinner
- [X] T110 [P] [US6] Test WorkflowProgress empty state shows "No workflow stages"
- [X] T111 [P] [US6] Test AgentOutput empty state shows "No agent output yet. Output will appear when workflow runs."
- [X] T112 [P] [US6] Test ReviewFindings empty state shows "No review findings. All clear!"
- [X] T113 [P] [US6] Test ValidationStatus empty state shows "No validation steps"
- [X] T114 [P] [US6] Test PRSummary empty state shows "No pull request"

### Implementation for User Story 6

- [X] T115 [US6] Verify all widgets have consistent loading state component (spinner/skeleton)
- [X] T116 [US6] Verify all widgets have consistent empty state styling (centered, muted text)
- [X] T117 [US6] Add .loading and .empty-state CSS classes if not already present in src/maverick/tui/maverick.tcss

**Checkpoint**: All widgets handle loading/empty states gracefully (31 empty/loading tests passing)

---

## Phase 9: User Story 7 - Keyboard Navigation (Priority: P3) ✅ COMPLETE

**Goal**: All widgets are fully navigable via keyboard

**Independent Test**: Mount widgets and verify all interactions can be performed via keyboard alone

### Tests for User Story 7

- [X] T118 [P] [US7] Test WorkflowProgress arrow down moves focus to next stage
- [X] T119 [P] [US7] Test AgentOutput Page Up/Down scrolls by page
- [X] T120 [P] [US7] Test ReviewFindings Tab cycles through findings and action buttons
- [X] T121 [P] [US7] Test all widgets focus first item when widget receives focus

### Implementation for User Story 7

- [X] T122 [US7] Add BINDINGS for arrow key navigation in WorkflowProgress
- [X] T123 [US7] Add BINDINGS for Page Up/Down in AgentOutput
- [X] T124 [US7] Add BINDINGS for Tab navigation in ReviewFindings
- [X] T125 [US7] Ensure can_focus=True and focus handling in all widgets
- [X] T126 [US7] Verify logical focus flow in ValidationStatus and PRSummary

**Checkpoint**: All widgets fully accessible via keyboard ✓

---

## Phase 10: Polish & Cross-Cutting Concerns ✅ COMPLETE

**Purpose**: Integration, exports, and final cleanup

- [X] T127 Export WorkflowProgress from src/maverick/tui/widgets/__init__.py
- [X] T128 [P] Export AgentOutput from src/maverick/tui/widgets/__init__.py
- [X] T129 [P] Export ReviewFindings from src/maverick/tui/widgets/__init__.py
- [X] T130 [P] Export ValidationStatus from src/maverick/tui/widgets/__init__.py
- [X] T131 [P] Export PRSummary from src/maverick/tui/widgets/__init__.py
- [X] T132 Add widget Textual messages (StageExpanded, BulkDismissRequested, etc.) as Message subclasses
- [X] T133 Run full test suite to verify all tests pass (236 passed)
- [X] T134 Run ruff format and ruff check on all new files
- [X] T135 Run mypy on all new files for type safety verification
- [X] T136 Run quickstart.md validation scenarios

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all widget work
- **User Stories (Phase 3-9)**: All depend on Foundational phase completion
  - US1 (WorkflowProgress), US2 (AgentOutput), US3 (ReviewFindings) can proceed in parallel
  - US4 (ValidationStatus), US5 (PRSummary) can proceed in parallel
  - US6 (Loading/Empty states) depends on all widget implementations
  - US7 (Keyboard navigation) depends on all widget implementations
- **Polish (Phase 10)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational - No dependencies on other stories
- **User Story 2 (P1)**: Can start after Foundational - No dependencies on other stories
- **User Story 3 (P1)**: Can start after Foundational - No dependencies on other stories
- **User Story 4 (P2)**: Can start after Foundational - No dependencies on other stories
- **User Story 5 (P2)**: Can start after Foundational - No dependencies on other stories
- **User Story 6 (P2)**: Depends on US1-US5 implementations to verify states
- **User Story 7 (P3)**: Depends on US1-US5 implementations to add keyboard support

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- Widget structure (compose) before methods
- Core methods before event handling
- CSS styles after widget implementation

### Parallel Opportunities

- All Setup tasks T002-T004 marked [P] can run in parallel
- All Foundational entity tasks T006-T010 marked [P] can run in parallel
- All Foundational state tasks T012-T015 marked [P] can run in parallel
- All tests for a user story marked [P] can run in parallel
- User Stories 1-3 (P1 priority) can be worked on in parallel
- User Stories 4-5 (P2 priority) can be worked on in parallel

---

## Parallel Example: User Story 1

```bash
# Launch all tests for User Story 1 together:
Task: "Test WorkflowProgress displays all stages vertically"
Task: "Test WorkflowProgress shows animated spinner icon"
Task: "Test WorkflowProgress shows checkmark and duration"
...
```

---

## Parallel Example: Foundational Phase

```bash
# Launch all entity dataclasses together:
Task: "Add AgentMessage dataclass to src/maverick/tui/models.py"
Task: "Add ReviewFinding and ReviewFindingItem dataclasses to src/maverick/tui/models.py"
Task: "Add CodeContext dataclass to src/maverick/tui/models.py"
Task: "Add ValidationStep dataclass to src/maverick/tui/models.py"
Task: "Add PRInfo dataclass to src/maverick/tui/models.py"
```

---

## Implementation Strategy

### MVP First (User Stories 1-3 Only)

1. Complete Phase 1: Setup (enums and basic dataclasses)
2. Complete Phase 2: Foundational (all data models)
3. Complete Phase 3: User Story 1 (WorkflowProgress)
4. **STOP and VALIDATE**: Test WorkflowProgress independently
5. Complete Phase 4: User Story 2 (AgentOutput)
6. Complete Phase 5: User Story 3 (ReviewFindings)
7. Deploy/demo core workflow visualization

### Incremental Delivery

1. Complete Setup + Foundational -> Foundation ready
2. Add User Story 1 -> Test independently -> WorkflowProgress MVP
3. Add User Story 2 -> Test independently -> AgentOutput added
4. Add User Story 3 -> Test independently -> ReviewFindings added
5. Add User Stories 4-5 -> ValidationStatus + PRSummary
6. Add User Stories 6-7 -> Loading states + Keyboard navigation
7. Polish phase for integration and cleanup

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each widget should be independently completable and testable
- Verify tests fail before implementing (TDD)
- Commit after each task or logical group
- Stop at any checkpoint to validate widget independently
- Avoid: vague tasks, same file conflicts, cross-widget dependencies that break independence
