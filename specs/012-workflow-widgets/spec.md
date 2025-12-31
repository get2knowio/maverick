# Feature Specification: Workflow Visualization Widgets

**Feature Branch**: `012-workflow-widgets`
**Created**: 2025-12-12
**Status**: Draft
**Input**: User description: "Create a spec for Textual widgets specific to workflow visualization in Maverick"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Monitoring Workflow Progress (Priority: P1)

A developer runs a Maverick workflow and watches the progress display. They see each stage as a row in a vertical list with the stage name, a status icon (pending circle, spinning indicator for active, checkmark for complete, X for error), and duration once completed. Clicking or pressing Enter on a stage expands it to reveal detailed information.

**Why this priority**: Workflow progress visualization is the primary interface for understanding what Maverick is doing. Without this, users have no visibility into the automation running on their behalf.

**Independent Test**: Can be fully tested by mounting the WorkflowProgress widget with mock stage data and verifying status icons, durations, and expansion behavior work correctly.

**Acceptance Scenarios**:

1. **Given** a workflow with 5 stages, **When** the WorkflowProgress widget mounts, **Then** all 5 stages display vertically with their names and pending status icons
2. **Given** a stage transitions to active, **When** the widget updates, **Then** that stage shows an animated spinner icon
3. **Given** a stage completes successfully, **When** the widget updates, **Then** that stage shows a checkmark icon and elapsed duration (e.g., "12s")
4. **Given** a stage fails, **When** the widget updates, **Then** that stage shows a failed icon in red
5. **Given** a completed stage is focused, **When** the user presses Enter, **Then** the stage expands to show detail text

---

### User Story 2 - Viewing Agent Output (Priority: P1)

A developer wants to see what agents are doing and thinking during workflow execution. They view the AgentOutput widget which displays streaming messages from agents. Code blocks within messages have syntax highlighting. Tool calls appear as collapsible sections. The display auto-scrolls as new content arrives, but the user can scroll up to read previous output, which locks auto-scroll until they scroll back to the bottom.

**Why this priority**: Agent transparency is essential for understanding what Maverick is doing, debugging issues, and building trust in the AI automation.

**Independent Test**: Can be fully tested by streaming mock agent messages to the AgentOutput widget and verifying rendering, syntax highlighting, tool call collapse/expand, and scroll behavior.

**Acceptance Scenarios**:

1. **Given** the AgentOutput widget is mounted, **When** agent messages stream in, **Then** they appear with timestamps and agent identifiers
2. **Given** a message contains a code block, **When** it renders, **Then** syntax highlighting is applied based on language annotation
3. **Given** a message contains a tool call, **When** it renders, **Then** the tool call appears as a collapsible section (collapsed by default)
4. **Given** new messages arrive, **When** the user is at the bottom of the scroll area, **Then** the view auto-scrolls to show the latest content
5. **Given** the user manually scrolls up, **When** new messages arrive, **Then** auto-scroll is paused and a "scroll to bottom" indicator appears
6. **Given** the user presses Ctrl+F in the widget, **When** they type a search term, **Then** matching text is highlighted and the user can navigate between matches

---

### User Story 3 - Reviewing Code Review Findings (Priority: P1)

A developer completes a code review stage and examines the findings. The ReviewFindings widget groups findings by severity (errors first, then warnings, then suggestions). Each finding shows the file path and line number as a clickable link. Clicking shows the code context. Findings can be expanded to see full details. The user can dismiss findings or create GitHub issues from them in bulk.

**Why this priority**: Code review is a core workflow stage. Presenting findings clearly with actionable options (view context, dismiss, create issue) makes the review stage usable.

**Independent Test**: Can be fully tested by mounting the ReviewFindings widget with mock finding data and verifying grouping, expansion, navigation, and bulk action buttons work.

**Acceptance Scenarios**:

1. **Given** findings exist at multiple severities, **When** the widget renders, **Then** findings are grouped with errors at top, warnings next, suggestions last
2. **Given** a finding has a file location, **When** the file:line link is clicked, **Then** a context panel shows surrounding code lines
3. **Given** a finding row is focused, **When** the user presses Enter, **Then** the finding expands to show full details (description, suggested fix)
4. **Given** multiple findings are selected, **When** the user triggers bulk dismiss, **Then** all selected findings are removed from the list
5. **Given** findings are selected, **When** the user triggers create issue, **Then** a confirmation dialog shows and issues are created on confirmation

---

### User Story 4 - Checking Validation Status (Priority: P2)

A developer runs the validation stage (format, lint, build, test) and watches compact status indicators. Each validation step shows its name and a pass/fail icon. Failed steps can be expanded to show error details. Each failed step has a re-run button to retry that validation step.

**Why this priority**: Validation feedback helps developers understand what needs fixing, but is secondary to the core workflow and output viewing.

**Independent Test**: Can be fully tested by mounting the ValidationStatus widget with mock validation results and verifying pass/fail indicators, error expansion, and re-run button functionality.

**Acceptance Scenarios**:

1. **Given** validation runs with 4 steps, **When** the widget renders, **Then** all steps show in a compact row with name and status icon
2. **Given** a step passes, **When** it renders, **Then** a green checkmark appears next to the step name
3. **Given** a step fails, **When** it renders, **Then** a red X appears and the step is expandable
4. **Given** a failed step is expanded, **When** viewing, **Then** error output and details are visible
5. **Given** a failed step is shown, **When** the re-run button is activated, **Then** that specific validation step re-executes

---

### User Story 5 - Viewing Pull Request Summary (Priority: P2)

A developer completes a workflow that creates or updates a pull request. The PRSummary widget shows the PR title, a preview of the description, inline status checks (CI passing/failing), and a link to open the PR in the browser.

**Why this priority**: PR visibility completes the workflow loop, letting users verify the output, but the core workflow stages are more critical.

**Independent Test**: Can be fully tested by mounting the PRSummary widget with mock PR data and verifying title, description preview, status checks, and link activation work.

**Acceptance Scenarios**:

1. **Given** a PR exists, **When** the PRSummary widget mounts, **Then** the PR title and number are displayed prominently
2. **Given** the PR has a description, **When** viewing, **Then** a truncated preview appears with option to expand
3. **Given** the PR has status checks, **When** viewing, **Then** check names and pass/fail icons display inline
4. **Given** the PR link is focused, **When** the user activates it, **Then** the PR opens in the default browser

---

### User Story 6 - Handling Loading and Empty States (Priority: P2)

A developer views any widget before data is available (loading) or when no data exists (empty). Each widget displays an appropriate state: loading shows a spinner or skeleton, empty shows a helpful message explaining why there's no data and what action might populate it.

**Why this priority**: Polish states prevent user confusion, but core functionality takes precedence.

**Independent Test**: Can be fully tested by mounting each widget with no data and verifying loading/empty states render correctly.

**Acceptance Scenarios**:

1. **Given** WorkflowProgress is loading, **When** it renders, **Then** a loading skeleton or message appears
2. **Given** AgentOutput has no messages, **When** it renders, **Then** an empty state says "No agent output yet. Output will appear when workflow runs."
3. **Given** ReviewFindings has no findings, **When** it renders, **Then** an empty state says "No review findings. All clear!"
4. **Given** ValidationStatus is loading, **When** it renders, **Then** step placeholders with loading indicators appear

---

### User Story 7 - Keyboard Navigation (Priority: P3)

A developer navigates within widgets using only the keyboard. Arrow keys move between items, Enter expands/collapses or activates, Tab moves between interactive elements, and each widget supports logical focus flow.

**Why this priority**: Accessibility and keyboard power-user support are important but supplement mouse/basic interaction.

**Independent Test**: Can be fully tested by mounting widgets and verifying all interactions can be performed via keyboard alone.

**Acceptance Scenarios**:

1. **Given** WorkflowProgress has focus, **When** arrow down is pressed, **Then** focus moves to the next stage
2. **Given** AgentOutput has focus, **When** Page Up/Down is pressed, **Then** the log scrolls by a page
3. **Given** ReviewFindings has focus, **When** Tab is pressed, **Then** focus cycles through findings and action buttons
4. **Given** any widget has focusable items, **When** focus enters the widget, **Then** the first item is focused by default

---

### Edge Cases

- What happens when workflow has 0 stages?
  - WorkflowProgress displays an empty state message
- What happens when agent output exceeds 1000 messages?
  - Oldest messages are discarded to maintain performance; a "truncated" indicator appears at the top
- What happens when a file location in findings points to a deleted file?
  - The link is styled as broken (strikethrough) and clicking shows an error tooltip
- What happens when status checks are still pending?
  - A spinning indicator shows next to the check name
- What happens when the PR was closed or merged?
  - The PRSummary shows the appropriate state (merged icon, closed icon)
- What happens when re-run button is pressed while validation is already running?
  - The button is disabled with a "running" indicator
- What happens when widget receives data faster than it can render?
  - Updates are batched to maintain 60fps rendering target

## Requirements *(mandatory)*

### Functional Requirements

#### WorkflowProgress Widget

- **FR-001**: Widget MUST display workflow stages as a vertical list
- **FR-002**: Widget MUST show stage name and status icon for each stage
- **FR-003**: Widget MUST support four status states: pending, active, completed, failed
- **FR-004**: Widget MUST display elapsed duration for completed stages
- **FR-005**: Widget MUST support expanding stages to show detail content
- **FR-006**: Widget MUST animate the active stage indicator (spinner)
- **FR-007**: Widget MUST update reactively when stage data changes

#### AgentOutput Widget

- **FR-008**: Widget MUST display streaming agent messages with timestamps
- **FR-009**: Widget MUST identify the source agent for each message
- **FR-010**: Widget MUST apply syntax highlighting to code blocks
- **FR-011**: Widget MUST render tool calls as collapsible sections
- **FR-012**: Widget MUST auto-scroll when user is at the bottom
- **FR-013**: Widget MUST pause auto-scroll when user scrolls up manually
- **FR-014**: Widget MUST show a "scroll to bottom" indicator when auto-scroll is paused
- **FR-015**: Widget MUST provide search functionality with match highlighting
- **FR-016**: Widget MUST support filtering by agent name or message type

#### ReviewFindings Widget

- **FR-017**: Widget MUST group findings by severity (error, warning, suggestion)
- **FR-018**: Widget MUST display findings within each group in a list
- **FR-019**: Widget MUST show file path and line number as clickable links
- **FR-020**: Widget MUST display code context when a file link is activated
- **FR-021**: Widget MUST support expanding findings to show full details
- **FR-022**: Widget MUST support selecting multiple findings
- **FR-023**: Widget MUST provide bulk dismiss action for selected findings
- **FR-024**: Widget MUST provide bulk create-issue action for selected findings

#### ValidationStatus Widget

- **FR-025**: Widget MUST display validation steps in a compact horizontal or vertical layout
- **FR-026**: Widget MUST show step name and pass/fail indicator
- **FR-027**: Widget MUST support expanding failed steps to show error details
- **FR-028**: Widget MUST provide a re-run button for failed steps
- **FR-029**: Widget MUST disable re-run button while validation is in progress

#### PRSummary Widget

- **FR-030**: Widget MUST display PR title and number
- **FR-031**: Widget MUST show truncated description with expand option
- **FR-032**: Widget MUST display status checks with pass/fail/pending indicators
- **FR-033**: Widget MUST provide a link to open PR in browser
- **FR-034**: Widget MUST indicate PR state (open, merged, closed)

#### Common Widget Requirements

- **FR-035**: All widgets MUST display appropriate loading states when data is unavailable
- **FR-036**: All widgets MUST display helpful empty states when no data exists
- **FR-037**: All widgets MUST support reactive updates when underlying data changes
- **FR-038**: All widgets MUST be navigable via keyboard
- **FR-039**: All widgets MUST follow the Maverick theming conventions (colors, spacing)

### Key Entities

- **WorkflowStage**: Represents a single stage in a workflow with name, status (pending/active/completed/error), start time, end time, and optional detail content
- **AgentMessage**: A message from an agent containing timestamp, agent identifier, message type (text/code/tool_call), and content
- **ReviewFinding**: A code review finding with severity (error/warning/suggestion), file location, line number, description, suggested fix, and selection state
- **ValidationStep**: A validation operation with name, status (pending/running/passed/failed), and optional error output
- **PRInfo**: Pull request metadata including number, title, description, state (open/merged/closed), and status checks

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can identify the current workflow stage and its status within 1 second of viewing WorkflowProgress
- **SC-002**: Agent output renders within 100 milliseconds of receiving new messages
- **SC-003**: Users can expand a code review finding and view code context within 2 clicks or keypresses
- **SC-004**: Users can dismiss or create issues for multiple findings in a single action (less than 5 seconds for 10 findings)
- **SC-005**: Users can identify overall validation status (all pass, some fail) within 1 second
- **SC-006**: Users can access the PR link and open in browser within 2 interactions
- **SC-007**: All widgets render correctly within the layout constraints defined in spec 011
- **SC-008**: Keyboard-only users can perform all widget interactions without mouse
- **SC-009**: Loading states appear within 200 milliseconds of widget mount
- **SC-010**: Empty states clearly communicate the reason and potential action to the user

## Clarifications

### Session 2025-12-16

- Q: What is the maximum buffer size for AgentOutput messages? → A: 1000 messages
- Q: Should widgets use mutable internal state or immutable snapshots? → A: Immutable snapshots with reactive binding
- Q: Should widgets emit performance metrics? → A: Out of scope for initial implementation
- Q: Are additional widget types beyond the 5 specified in scope? → A: No, only the 5 specified widgets
- Q: What is the maximum number of review findings to handle? → A: 200 findings maximum
- Q: Should search support navigation between matches (F3/Shift+F3)? → A: Out of scope for initial implementation; highlighting only
- Q: Should broken file links show an error tooltip? → A: No, strikethrough styling only for initial implementation; tooltip is a polish item

## Assumptions

- Widgets will be used within the TUI layout defined in spec 011-tui-layout-theming
- Widgets receive immutable data snapshots and re-render reactively (no mutable internal state management)
- The Textual framework provides reactive primitives for data binding and updates
- Syntax highlighting will use a library compatible with Textual rendering
- Browser opening will use the system default browser via standard OS mechanisms
- Tool call sections will show tool name and arguments; full input/output may be truncated for display
- The search functionality in AgentOutput uses simple substring matching; advanced regex search is out of scope
- Widget performance metrics/observability is out of scope for initial implementation
- Only the 5 specified widgets (WorkflowProgress, AgentOutput, ReviewFindings, ValidationStatus, PRSummary) are in scope; additional widget types are out of scope
- ReviewFindings widget should handle up to 200 findings performantly (no list virtualization required)
- Bulk actions (dismiss, create issue) operate on currently visible/selected findings only
- Widget styling will inherit from the Maverick theme stylesheet (maverick.tcss)
