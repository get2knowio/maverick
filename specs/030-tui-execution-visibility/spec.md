# Feature Specification: TUI Real-Time Execution Visibility

**Feature Branch**: `030-tui-execution-visibility`
**Created**: 2026-01-12
**Status**: Draft
**Input**: User description: "TUI Real-Time Execution Visibility - Add loop/phase progress visibility and agent output streaming panel to workflow execution screen"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - View Loop Iteration Progress (Priority: P1)

As a user running a multi-phase implementation workflow, I want to see which phase is currently executing so I know the progress and can estimate completion time.

When executing a workflow with loop steps (like `implement_by_phase`), the step should visually expand to show child items for each iteration. I should see progress like "Phase 1/3: Core Data Structures" progressing to "Phase 2/3: API Implementation" with clear status indicators for each phase.

**Why this priority**: This is the core visibility problem users face today. Without knowing which iteration is running out of how many total, users cannot estimate completion time or understand workflow progress. This directly impacts user confidence and productivity.

**Independent Test**: Can be fully tested by running any workflow with a loop step and verifying the UI expands to show iteration progress. Delivers value even without agent streaming.

**Acceptance Scenarios**:

1. **Given** a workflow with a loop step containing 3 iterations, **When** the loop step begins execution, **Then** the UI expands to show all 3 iterations with pending status indicators
2. **Given** an expanded loop step with iteration 2 running, **When** iteration 2 completes successfully, **Then** iteration 2 shows completed status and iteration 3 shows running status
3. **Given** a loop step with iterations, **When** an iteration fails, **Then** the iteration shows failed status with visual distinction from completed/pending states
4. **Given** a nested loop (loop within loop), **When** the outer loop executes, **Then** the UI shows hierarchical nesting with proper indentation for inner loop iterations

---

### User Story 2 - Monitor Agent Activity in Real-Time (Priority: P2)

As a user waiting for an agent to complete work, I want to see what the agent is doing/thinking in real-time so I can verify it's on the right track and not stuck.

When a Claude agent is working (implementing code, reviewing, fixing issues), I should see a streaming panel displaying the agent's output as it's generated. This panel should show which agent/step is producing output and auto-scroll to the latest content.

**Why this priority**: While loop visibility tells users "what" is happening, agent streaming tells users "how" it's progressing. This is critical for debugging and building trust, but loop visibility provides more immediate value for progress tracking.

**Independent Test**: Can be fully tested by running any workflow with an agent step and verifying real-time text streaming appears in the panel. Delivers value even without loop iteration visibility.

**Acceptance Scenarios**:

1. **Given** a workflow step that invokes a Claude agent, **When** the agent begins generating output, **Then** the streaming panel displays text chunks within 100ms of generation
2. **Given** agent output is streaming, **When** new text is generated, **Then** the panel auto-scrolls to show the latest content
3. **Given** the streaming panel is visible, **When** I want to focus on other UI elements, **Then** I can collapse the panel and expand it later
4. **Given** multiple agent steps in sequence, **When** each agent runs, **Then** the panel clearly indicates which agent/step is currently producing output

---

### User Story 3 - Debug Failed Workflows (Priority: P3)

As a user debugging a failed workflow, I want to see the agent's output leading up to the failure so I can understand what went wrong.

When a workflow fails, I should be able to review the complete history of agent output in the streaming panel to diagnose the issue. The output should persist after completion so I can scroll back through it.

**Why this priority**: Debugging is a secondary use case that becomes important after failures occur. The streaming panel from P2 naturally enables this capability with minimal additional work.

**Independent Test**: Can be fully tested by intentionally triggering a workflow failure and verifying agent output history is reviewable in the panel.

**Acceptance Scenarios**:

1. **Given** a workflow has completed (success or failure), **When** I scroll through the streaming panel, **Then** I see the complete history of agent output from the workflow
2. **Given** a workflow step failed, **When** I review the streaming panel, **Then** I can identify which agent/step produced output before the failure
3. **Given** extensive agent output during a long workflow, **When** I scroll through the history, **Then** the panel maintains responsive scrolling performance

---

### Edge Cases

- What happens when a loop has zero iterations? (Display empty loop with "no iterations" indicator)
- How does the system handle deeply nested loops (3+ levels)? (Show up to 3 levels of nesting; collapse deeper levels with expandable indicator)
- What happens when agent output contains extremely long lines? (Wrap text within panel bounds)
- How does the system handle rapid iteration completion (sub-second iterations)? (Batch UI updates to prevent flickering; minimum 50ms between visual state changes)
- What happens if agent streaming is interrupted mid-output? (Show partial output with "interrupted" indicator)
- How does the system behave when workflow is cancelled during loop execution? (Mark current iteration as cancelled; remaining iterations as skipped)
- What happens when agent output history exceeds 100KB? (Truncate oldest content using FIFO buffer to maintain limit while preserving most recent output)

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST expand loop steps in the UI to display child items for each iteration
- **FR-002**: System MUST display iteration progress in format "[current]/[total]: [item_label]" (e.g., "Phase 1/3: Core Data Structures")
- **FR-003**: System MUST show distinct visual status indicators for each iteration state: pending, running, completed, failed, skipped, cancelled
- **FR-004**: System MUST support visualization of nested loops with proper hierarchical indentation
- **FR-005**: System MUST provide a dedicated streaming panel for agent output as a separate collapsible panel distinct from the existing log panel, allowing both to be visible simultaneously
- **FR-006**: System MUST stream agent output text to the panel in real-time as it is generated
- **FR-007**: System MUST clearly indicate which agent/step is currently producing output in the streaming panel header
- **FR-008**: System MUST auto-scroll the streaming panel to show the latest content by default
- **FR-009**: System MUST allow users to toggle the streaming panel visibility (expand/collapse), with expanded as the default state when a workflow begins
- **FR-010**: System MUST preserve agent output history for the duration of the workflow execution session
- **FR-011**: System MUST emit loop iteration events from the executor that include iteration index, total count, and item label
- **FR-012**: System MUST emit agent streaming events that include step name, agent name, and text chunk
- **FR-013**: System MUST remain responsive during agent streaming (no UI freezes)
- **FR-014**: System MUST support displaying "thinking" indicator when agent is processing but not yet streaming output

### Key Entities

- **LoopIterationProgress**: Represents the state of a single loop iteration - includes iteration index (0-based), total iterations count, item label, status (pending/running/completed/failed/skipped/cancelled), and parent loop reference for nesting
- **AgentStreamEntry**: Represents a chunk of agent output - includes timestamp, source step name, source agent name, text content, and chunk type (output/thinking/error)
- **StreamingPanelState**: Represents the streaming panel configuration - includes visibility (expanded/collapsed), auto-scroll enabled, current output source identifier

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can see iteration progress within 100ms of iteration state change
- **SC-002**: Agent output text appears in the streaming panel within 100ms of generation
- **SC-003**: UI remains responsive (no visible stutter or freeze) while streaming agent output at rates up to 100 characters per second
- **SC-004**: Users can toggle the streaming panel visibility with a single interaction
- **SC-005**: Nested loop structures up to 3 levels deep are displayed correctly with distinguishable hierarchy
- **SC-006**: 100% of loop iterations are tracked and displayed (no missing iterations)
- **SC-007**: Agent output history is preserved and scrollable for workflows producing up to 100KB of output text
- **SC-008**: Existing workflow execution functionality remains unchanged (no regressions)

## Clarifications

### Session 2026-01-12

- Q: How should the streaming panel relate to the existing log panel in the UI layout? → A: Separate collapsible panels (streaming panel distinct from log panel, both can be visible)
- Q: What should happen when agent output history exceeds the 100KB limit? → A: Truncate oldest content (FIFO buffer)
- Q: What should be the default state of the streaming panel when a workflow begins? → A: Expanded by default

## Assumptions

- The claude-agent-sdk provides async streaming events during query() calls that can be yielded to the TUI
- The existing event system (ProgressEvent pattern) can be extended with new event types without breaking changes
- Textual framework supports dynamic widget expansion/collapse and real-time text streaming
- Loop iteration count is known when the loop begins (for total count display)
- Agent names are available from the claude-agent-sdk during execution
