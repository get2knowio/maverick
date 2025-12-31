# Feature Specification: Textual TUI Layout and Theming

**Feature Branch**: `011-tui-layout-theming`
**Created**: 2025-12-12
**Status**: Draft
**Input**: User description: "Create a spec for the core Textual TUI layout and theming for Maverick"

## Clarifications

### Session 2025-12-16

- Q: How many recent workflows should be displayed on the home screen? → A: 10 most recent workflows
- Q: What is the log panel buffer size limit? → A: 1,000 lines
- Q: What is the minimum supported terminal size? → A: 80×24 (standard terminal)
- Q: What should the sidebar display when no workflow is active? → A: Navigation menu (Home, Workflows, Settings, etc.)
- Q: What keybinding toggles the log panel? → A: Ctrl+L

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Launching the Application (Priority: P1)

A developer launches Maverick from the command line to begin a development workflow. They see a well-organized interface with a header identifying the application, a sidebar showing available options, a main content area, and a footer with helpful keybindings.

**Why this priority**: The initial application launch and main layout are foundational - without a working application shell, no other features can function.

**Independent Test**: Can be fully tested by launching the application and verifying the main layout renders with all structural components visible (header, sidebar, main content, footer).

**Acceptance Scenarios**:

1. **Given** the user runs the maverick command, **When** the application starts, **Then** the main layout displays with header, sidebar, main content area, and footer visible
2. **Given** the application is running, **When** the user views the header, **Then** they see the application name "Maverick" and current status information
3. **Given** the application is running, **When** the user views the footer, **Then** they see available keybindings for common actions

---

### User Story 2 - Navigating Between Screens (Priority: P1)

A developer navigates between different views in the application - starting from the home screen, selecting a workflow, viewing progress, and accessing settings. Navigation is consistent and intuitive.

**Why this priority**: Screen navigation is essential for all user flows and must work reliably for any workflow to be usable.

**Independent Test**: Can be fully tested by navigating through all screens using keyboard shortcuts and verifying each screen displays correctly.

**Acceptance Scenarios**:

1. **Given** the user is on any screen, **When** they press Escape, **Then** they return to the previous screen or cancel the current action
2. **Given** the user is on any screen, **When** they press Ctrl+P, **Then** the command palette opens allowing quick navigation
3. **Given** the user is on the home screen, **When** they select a workflow option, **Then** they navigate to the workflow screen

---

### User Story 3 - Monitoring Workflow Progress (Priority: P1)

A developer starts a workflow and monitors its progress. The sidebar shows workflow stages with visual indicators (checkmarks for completed, spinner for active), and the main content area displays relevant details for the current stage.

**Why this priority**: Workflow monitoring is the primary use case for Maverick - users need real-time visibility into what the system is doing.

**Independent Test**: Can be fully tested by starting a mock workflow and verifying stage progress indicators update correctly.

**Acceptance Scenarios**:

1. **Given** a workflow is running, **When** a stage completes, **Then** the sidebar shows a checkmark next to that stage
2. **Given** a workflow is running, **When** a stage is active, **Then** the sidebar shows a spinner animation next to that stage
3. **Given** a workflow is running, **When** the user views elapsed time in the header, **Then** they see the current duration updating

---

### User Story 4 - Viewing Agent Output Logs (Priority: P2)

A developer wants to see detailed output from agents during workflow execution. They can expand or collapse a log panel to view streaming agent output without leaving the current screen.

**Why this priority**: Detailed logs are important for debugging and understanding agent behavior, but not required for basic workflow execution.

**Independent Test**: Can be fully tested by toggling the log panel visibility and verifying agent output streams correctly.

**Acceptance Scenarios**:

1. **Given** the log panel is collapsed, **When** the user presses Ctrl+L, **Then** the log panel expands showing agent output
2. **Given** the log panel is expanded, **When** agents produce output, **Then** the output appears in real-time in the log panel
3. **Given** the log panel is expanded, **When** the user presses Ctrl+L, **Then** the log panel collapses freeing screen space

---

### User Story 5 - Reviewing Code Review Results (Priority: P2)

A developer completes a workflow that includes code review and views the results in a dedicated review screen. The results are organized clearly showing issues, suggestions, and their locations.

**Why this priority**: Code review display enhances the workflow experience but builds on the core layout infrastructure.

**Independent Test**: Can be fully tested by navigating to the review screen with mock data and verifying results display correctly.

**Acceptance Scenarios**:

1. **Given** code review results exist, **When** the user navigates to the review screen, **Then** they see organized review findings
2. **Given** review results are displayed, **When** the user views an issue, **Then** they see the issue severity indicated by color (red for error, yellow for warning)

---

### User Story 6 - Configuring Application Settings (Priority: P3)

A developer accesses the settings screen to configure application preferences. The settings are organized logically and changes are reflected immediately.

**Why this priority**: Settings configuration is needed for customization but is not required for basic application functionality.

**Independent Test**: Can be fully tested by navigating to the config screen and verifying settings display and can be modified.

**Acceptance Scenarios**:

1. **Given** the user is on any screen, **When** they press Ctrl+, (comma), **Then** they navigate to the config screen
2. **Given** the user is on the config screen, **When** they modify a setting, **Then** the change is immediately reflected in the interface

---

### User Story 7 - Selecting Recent Workflows (Priority: P3)

A developer returns to the application and wants to quickly access a recently-run workflow from the home screen.

**Why this priority**: Recent workflow access improves convenience but is not essential for core functionality.

**Independent Test**: Can be fully tested by viewing the home screen and verifying recent workflow entries appear.

**Acceptance Scenarios**:

1. **Given** the user has run workflows previously, **When** they view the home screen, **Then** they see a list of the 10 most recent workflow runs (ordered by last run date)
2. **Given** recent workflows are displayed, **When** the user selects one, **Then** they see details about that workflow run

---

### Edge Cases

- What happens when the terminal window is resized below the minimum supported size (80×24)?
  - The layout should display a minimum size warning overlay until the terminal is resized to at least 80×24
- What happens when a workflow stage fails?
  - The stage indicator should show an error state (red) and the workflow should continue if possible
- What happens when agent output exceeds the log panel buffer (1,000 lines)?
  - Older output should scroll off while maintaining performance
- What happens when the user presses an unbound key?
  - No action should occur; the application should not crash or display errors

## Requirements *(mandatory)*

### Functional Requirements

#### Application Structure

- **FR-001**: System MUST provide a MaverickApp class as the main application entry point
- **FR-002**: System MUST display a header component showing the application name, current workflow name (if any), and elapsed time
- **FR-003**: System MUST display a sidebar component that shows navigation menu (Home, Workflows, Settings) when no workflow is active, and workflow stages with status indicators during workflow execution
- **FR-004**: System MUST display a main content area that changes based on the current screen context
- **FR-005**: System MUST display a collapsible log panel for streaming agent output
- **FR-006**: System MUST display a footer component showing available keybindings and current status

#### Screen Navigation

- **FR-007**: System MUST provide a HomeScreen for workflow selection and displaying recent runs
- **FR-008**: System MUST provide a WorkflowScreen for displaying active workflow progress
- **FR-009**: System MUST provide a ReviewScreen for displaying code review results
- **FR-010**: System MUST provide a ConfigScreen for editing application settings
- **FR-011**: System MUST support navigation via keyboard shortcuts
- **FR-012**: System MUST provide a command palette accessible via Ctrl+P
- **FR-013**: System MUST support Escape key to go back or cancel current action

#### Theming and Visual Design

- **FR-014**: System MUST use a dark mode theme by default with syntax-highlighting-friendly colors
- **FR-015**: System MUST define status colors: success (green), warning (yellow), error (red), info (blue)
- **FR-016**: System MUST define an accent color for highlighting active/selected elements
- **FR-017**: System MUST apply consistent spacing and borders throughout the interface
- **FR-018**: System MUST store theme definitions in a stylesheet file (maverick.tcss)

#### Workflow Progress Indicators

- **FR-019**: System MUST display a checkmark indicator for completed workflow stages
- **FR-020**: System MUST display a spinner animation for the currently active stage
- **FR-021**: System MUST display pending stages without special indicators
- **FR-022**: System MUST display an error indicator for failed stages

### Key Entities

- **Screen**: A distinct view in the application (Home, Workflow, Review, Config) with its own layout and content
- **WorkflowStage**: A step in a workflow with name, status (pending, active, completed, failed), and optional timing information
- **LogEntry**: A single line of agent output with timestamp, source agent, and message content
- **ThemeColors**: Color definitions for status states, accents, borders, and backgrounds

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can identify the current workflow and elapsed time within 2 seconds of viewing the header
- **SC-002**: Users can navigate between any two screens in 3 or fewer keystrokes
- **SC-003**: Workflow stage status changes are visually reflected within 1 second of state change
- **SC-004**: Log panel toggle responds within 200 milliseconds of user input
- **SC-005**: The application renders correctly on terminal sizes from 80x24 to fullscreen
- **SC-006**: Status colors are distinguishable and provide clear visual hierarchy
- **SC-007**: Users can access the command palette and execute a command within 5 seconds
- **SC-008**: All keybinding hints displayed in the footer accurately reflect available actions

## Assumptions

- The application will run in modern terminal emulators that support 256 colors or true color
- Users have basic familiarity with keyboard-driven terminal applications
- The Textual framework provides the underlying rendering and event handling infrastructure
- Widget implementations (specific content within each screen) will be developed in subsequent specifications
- The default keybindings follow common terminal application conventions (Escape to cancel, Ctrl+P for palette, Ctrl+L for log panel toggle)
