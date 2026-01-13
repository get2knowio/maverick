# Tasks: TUI Real-Time Execution Visibility

**Input**: Design documents from `/specs/030-tui-execution-visibility/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, quickstart.md

**Tests**: Tests are included per Constitution Principle V (Test-First).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add shared enums and base types needed by all user stories

- [X] T001 [P] Add IterationStatus enum with 6 states (PENDING, RUNNING, COMPLETED, FAILED, SKIPPED, CANCELLED) in src/maverick/tui/models/enums.py
- [X] T002 [P] Add StreamChunkType enum with 3 states (OUTPUT, THINKING, ERROR) in src/maverick/tui/models/enums.py

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Add event types to DSL layer that all user stories depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T003 [P] Add LoopIterationStarted event dataclass in src/maverick/dsl/events.py
- [X] T004 [P] Add LoopIterationCompleted event dataclass in src/maverick/dsl/events.py
- [X] T005 [P] Add AgentStreamChunk event dataclass in src/maverick/dsl/events.py
- [X] T006 Update ProgressEvent type union to include new event types in src/maverick/dsl/events.py

**Checkpoint**: Foundation ready - event types exist and are part of ProgressEvent union

---

## Phase 3: User Story 1 - View Loop Iteration Progress (Priority: P1) 🎯 MVP

**Goal**: Expand loop steps in the UI to show each iteration with progress indicator and distinct status icons

**Independent Test**: Run any workflow with a loop step and verify the UI expands to show iteration progress with status indicators

### Tests for User Story 1 ⚠️

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T007 [P] [US1] Unit test for LoopIterationStarted/Completed events in tests/unit/dsl/test_events.py
- [X] T008 [P] [US1] Unit test for LoopIterationItem and LoopIterationState in tests/unit/tui/test_iteration_progress.py
- [X] T009 [P] [US1] Unit test for IterationProgress widget rendering in tests/unit/tui/test_iteration_progress.py

### Implementation for User Story 1

- [X] T010 [P] [US1] Add LoopIterationItem dataclass with display_text property, started_at, and completed_at timestamps in src/maverick/tui/models/widget_state.py
- [X] T011 [P] [US1] Add LoopIterationState dataclass with iteration tracking methods in src/maverick/tui/models/widget_state.py
- [X] T012 [US1] Create IterationProgress widget with STATUS_ICONS, compose method, and empty state display ("No iterations" indicator when total_iterations=0) in src/maverick/tui/widgets/iteration_progress.py
- [X] T013 [US1] Modify loop_step.py handler to emit LoopIterationStarted at iteration start in src/maverick/dsl/serialization/executor/handlers/loop_step.py
- [X] T014 [US1] Modify loop_step.py handler to emit LoopIterationCompleted at iteration end in src/maverick/dsl/serialization/executor/handlers/loop_step.py
- [X] T015 [US1] Add _extract_item_label helper function for loop item display in src/maverick/dsl/serialization/executor/handlers/loop_step.py
- [X] T016 [US1] Add _handle_iteration_started event handler in WorkflowExecutionScreen in src/maverick/tui/screens/workflow_execution.py
- [X] T017 [US1] Add _handle_iteration_completed event handler in WorkflowExecutionScreen in src/maverick/tui/screens/workflow_execution.py
- [X] T018 [US1] Add _loop_states dict and iteration widget mounting in WorkflowExecutionScreen in src/maverick/tui/screens/workflow_execution.py
- [X] T019 [US1] Add CSS styles for iteration status colors (.iteration-pending, .iteration-running, etc.) in src/maverick/tui/maverick.tcss
- [X] T020 [US1] Add nested loop support with nesting_level tracking, indentation (up to 3 levels), and collapsed indicator for levels 4+ with expandable toggle in src/maverick/tui/widgets/iteration_progress.py

**Checkpoint**: Loop iteration progress visible with status icons - User Story 1 fully functional and testable independently

---

## Phase 4: User Story 2 - Monitor Agent Activity in Real-Time (Priority: P2)

**Goal**: Add a collapsible streaming panel that displays agent output in real-time during workflow execution

**Independent Test**: Run any workflow with an agent step and verify real-time text streaming appears in the panel

### Tests for User Story 2 ⚠️

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T021 [P] [US2] Unit test for AgentStreamChunk event creation in tests/unit/dsl/test_events.py
- [X] T022 [P] [US2] Unit test for AgentStreamEntry and StreamingPanelState in tests/unit/tui/test_streaming_panel.py
- [X] T023 [P] [US2] Unit test for AgentStreamingPanel widget in tests/unit/tui/test_streaming_panel.py

### Implementation for User Story 2

- [X] T024 [P] [US2] Add AgentStreamEntry frozen dataclass with size_bytes property in src/maverick/tui/models/widget_state.py
- [X] T025 [P] [US2] Add StreamingPanelState dataclass with add_entry FIFO eviction in src/maverick/tui/models/widget_state.py
- [X] T026 [US2] Create AgentStreamingPanel widget with header, content, toggle_visibility, and thinking indicator (animated or italic text for THINKING chunks) in src/maverick/tui/widgets/agent_streaming_panel.py
- [X] T027 [US2] Modify agent_step.py handler to emit AgentStreamChunk events during agent execution in src/maverick/dsl/serialization/executor/handlers/agent_step.py
- [X] T028 [US2] Add thinking indicator emission at agent start in src/maverick/dsl/serialization/executor/handlers/agent_step.py
- [X] T029 [US2] Add _handle_stream_chunk event handler in WorkflowExecutionScreen in src/maverick/tui/screens/workflow_execution.py
- [X] T030 [US2] Add _streaming_state and streaming panel mounting in WorkflowExecutionScreen in src/maverick/tui/screens/workflow_execution.py
- [X] T031 [US2] Add CSS styles for streaming panel (with text-wrap and overflow handling for long lines), and chunk types (.chunk-output, .chunk-thinking with italic/muted styling, .chunk-error) in src/maverick/tui/maverick.tcss
- [X] T032 [US2] Add keyboard shortcut 's' to toggle streaming panel visibility in src/maverick/tui/screens/workflow_execution.py
- [X] T033 [US2] Ensure streaming panel is expanded by default when workflow begins in src/maverick/tui/screens/workflow_execution.py

**Checkpoint**: Agent output streams in real-time with collapsible panel - User Story 2 fully functional and testable independently

---

## Phase 5: User Story 3 - Debug Failed Workflows (Priority: P3)

**Goal**: Preserve agent output history for the session to enable post-failure debugging

**Independent Test**: Intentionally trigger a workflow failure and verify agent output history is reviewable in the panel

### Tests for User Story 3 ⚠️

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T034 [P] [US3] Unit test for StreamingPanelState FIFO buffer at 100KB limit in tests/unit/tui/test_streaming_panel.py
- [X] T035 [P] [US3] Unit test for history scrolling with 100KB of content in tests/unit/tui/test_streaming_panel.py

### Implementation for User Story 3

- [X] T036 [US3] Ensure entries persist after workflow completion (no clear on complete) in src/maverick/tui/screens/workflow_execution.py
- [X] T037 [US3] Add scroll support for reviewing history in AgentStreamingPanel in src/maverick/tui/widgets/agent_streaming_panel.py
- [X] T038 [US3] Add auto-scroll toggle to allow manual scrolling through history in src/maverick/tui/widgets/agent_streaming_panel.py
- [X] T039 [US3] Verify FIFO truncation works correctly at 100KB boundary in src/maverick/tui/models/widget_state.py

**Checkpoint**: Agent output history preserved and scrollable after completion - User Story 3 fully functional

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [X] T040 [P] Add integration test for loop event emission end-to-end in tests/integration/dsl/test_loop_events.py
- [X] T041 [P] Add test for WorkflowExecutionScreen event handlers in tests/unit/test_workflow_execution_events.py
- [X] T042 Ensure 50ms debounce for rapid UI updates to prevent flickering in src/maverick/tui/screens/workflow_execution.py
- [X] T043 Add keyboard shortcut 'l' for log panel toggle (parallel to 's' for streaming) in src/maverick/tui/screens/workflow_execution.py
- [X] T044 Run make check to verify lint, typecheck, and tests pass
- [X] T045 Run quickstart.md validation scenarios manually (automated tests cover these scenarios; manual validation recommended for final UI review)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3+)**: All depend on Foundational phase completion
  - User stories can then proceed in parallel (if staffed)
  - Or sequentially in priority order (P1 → P2 → P3)
- **Polish (Phase 6)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 2 (P2)**: Can start after Foundational (Phase 2) - No dependencies on other stories (uses AgentStreamChunk from Foundation)
- **User Story 3 (P3)**: Depends on User Story 2 (extends StreamingPanelState with history preservation)

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- State models before widgets
- Event emission (executor) before event handling (TUI)
- Widgets before screen integration
- Core implementation before polish

### Parallel Opportunities

- All Setup tasks (T001-T002) can run in parallel
- All Foundational event tasks (T003-T005) can run in parallel (T006 depends on them)
- All tests within a user story marked [P] can run in parallel
- State models within a story marked [P] can run in parallel
- User Stories 1 and 2 can run in parallel if team capacity allows
- User Story 3 depends on User Story 2

---

## Parallel Example: User Story 1

```bash
# Launch all tests for User Story 1 together:
Task: "Unit test for LoopIterationStarted/Completed events in tests/unit/dsl/test_events.py"
Task: "Unit test for LoopIterationItem and LoopIterationState in tests/unit/tui/test_iteration_progress.py"
Task: "Unit test for IterationProgress widget rendering in tests/unit/tui/test_iteration_progress.py"

# Launch state models for User Story 1 together:
Task: "Add LoopIterationItem dataclass in src/maverick/tui/models/widget_state.py"
Task: "Add LoopIterationState dataclass in src/maverick/tui/models/widget_state.py"
```

---

## Parallel Example: User Story 2

```bash
# Launch all tests for User Story 2 together:
Task: "Unit test for AgentStreamChunk event creation in tests/unit/dsl/test_events.py"
Task: "Unit test for AgentStreamEntry and StreamingPanelState in tests/unit/tui/test_streaming_panel.py"
Task: "Unit test for AgentStreamingPanel widget in tests/unit/tui/test_streaming_panel.py"

# Launch state models for User Story 2 together:
Task: "Add AgentStreamEntry frozen dataclass in src/maverick/tui/models/widget_state.py"
Task: "Add StreamingPanelState dataclass in src/maverick/tui/models/widget_state.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T002)
2. Complete Phase 2: Foundational (T003-T006)
3. Complete Phase 3: User Story 1 (T007-T020)
4. **STOP and VALIDATE**: Test loop iteration visibility independently
5. Deploy/demo if ready

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently → Deploy/Demo (MVP!)
3. Add User Story 2 → Test independently → Deploy/Demo
4. Add User Story 3 → Test independently → Deploy/Demo
5. Each story adds value without breaking previous stories

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1 (loop iteration visibility)
   - Developer B: User Story 2 (agent streaming panel)
3. User Story 3 starts after User Story 2 completes (extends streaming panel)

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verify tests fail before implementing
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Performance: 50ms minimum between UI updates to prevent flickering (per spec SC-003)
- Buffer limit: 100KB FIFO for agent output history (per spec FR-010, SC-007)
