# Feature Specification: TUI Interactive Screens

**Feature Branch**: `013-tui-interactive-screens`
**Created**: 2025-12-12
**Status**: Draft
**Input**: User description: "Create a spec for the interactive screens in Maverick's Textual TUI"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Launching a Fly Workflow (Priority: P1)

A developer opens Maverick and navigates to the FlyScreen to start a feature implementation workflow. They enter a branch name (with real-time validation showing if the name is valid or conflicts with existing branches), optionally select a specific task file, and press Start. The screen transitions to show live workflow progress with the WorkflowProgress widget displaying stages and the AgentOutput panel streaming agent activity. When the code review stage completes, the screen automatically transitions to the ReviewScreen.

**Why this priority**: The Fly workflow is the primary use case for Maverick. Without a working FlyScreen, users cannot execute the main feature implementation workflow.

**Independent Test**: Can be fully tested by navigating to FlyScreen, entering a valid branch name, starting the workflow with mock data, and verifying the progress display and transition to ReviewScreen.

**Acceptance Scenarios**:

1. **Given** the user is on HomeScreen, **When** they select "Fly", **Then** they navigate to FlyScreen with an empty branch name input focused
2. **Given** the user is on FlyScreen, **When** they enter an invalid branch name (spaces, special chars), **Then** validation error appears inline and Start button is disabled
3. **Given** the user enters a valid branch name, **When** the branch already exists remotely, **Then** a warning indicator shows "Branch exists - will continue existing work"
4. **Given** the user has entered a valid branch name, **When** they click Start, **Then** the workflow begins and progress indicators activate
5. **Given** a workflow is running, **When** code review completes, **Then** the screen transitions to ReviewScreen with findings loaded

---

### User Story 2 - Reviewing Code Findings (Priority: P1)

A developer is automatically transitioned to ReviewScreen after code review completes, or navigates there manually to review findings from a previous workflow. The ReviewFindings widget displays grouped findings (errors, warnings, suggestions). The user can click a finding to see the file diff in a side panel, expand findings for full details, approve the review, request changes, dismiss individual findings, or trigger automatic fixes for specific findings.

**Why this priority**: Code review is a critical stage in every Fly workflow. The ReviewScreen provides the interactive interface for users to act on review findings.

**Independent Test**: Can be fully tested by mounting ReviewScreen with mock findings, verifying finding display/grouping, side panel diff display, and all action buttons function correctly.

**Acceptance Scenarios**:

1. **Given** findings exist at multiple severities, **When** ReviewScreen loads, **Then** findings display grouped with errors first, then warnings, then suggestions
2. **Given** a finding is selected, **When** the user clicks it, **Then** the side panel shows the relevant file diff with the finding location highlighted
3. **Given** findings are displayed, **When** the user clicks "Approve", **Then** a confirmation dialog appears and approval is submitted on confirm
4. **Given** findings are displayed, **When** the user triggers "Fix All", **Then** the system attempts to auto-fix all findings and shows success/failure results per finding
5. **Given** the user wants to leave feedback, **When** they click "Request Changes", **Then** a text input appears for comments before submitting

---

### User Story 3 - Processing Issues with RefuelScreen (Priority: P1)

A developer opens RefuelScreen to process tech debt issues. They enter a label filter (e.g., "tech-debt"), set a limit on how many issues to process, toggle between parallel and sequential processing, and see a list of matching issues with selection checkboxes. After selecting issues and starting, they monitor progress. On completion, a results summary shows which issues were fixed, which failed, and any PRs created.

**Why this priority**: RefuelWorkflow is the secondary workflow and RefuelScreen is required for users to select and process tech debt issues.

**Independent Test**: Can be fully tested by mounting RefuelScreen, entering a label filter, viewing the issue list, selecting issues, starting execution, and verifying the results summary displays.

**Acceptance Scenarios**:

1. **Given** the user is on HomeScreen, **When** they select "Refuel", **Then** they navigate to RefuelScreen with label filter input focused
2. **Given** the user enters a label filter, **When** they press Enter or click Search, **Then** matching GitHub issues display as a selectable list
3. **Given** issues are displayed, **When** the user toggles checkboxes, **Then** selected issues are highlighted and count updates
4. **Given** issues are selected, **When** the user toggles parallel/sequential, **Then** the mode indicator updates
5. **Given** the user starts processing, **When** execution completes, **Then** a results summary shows success/failure per issue and links to PRs

---

### User Story 4 - Configuring Application Settings (Priority: P2)

A developer navigates to SettingsScreen to configure Maverick. They see a form-based interface with sections for GitHub settings, notification preferences, and agent configuration. They can test their GitHub connection, send a test notification, modify settings, and save or cancel changes. Unsaved changes prompt a confirmation dialog on navigation away.

**Why this priority**: Settings configuration is necessary for customization but not required for basic workflow execution.

**Independent Test**: Can be fully tested by navigating to SettingsScreen, modifying a setting, testing GitHub connection, and verifying save/cancel behavior.

**Acceptance Scenarios**:

1. **Given** the user is on any screen, **When** they navigate to Settings, **Then** SettingsScreen displays with current configuration values loaded
2. **Given** the user is on SettingsScreen, **When** they click "Test GitHub Connection", **Then** a test runs and shows success/failure status
3. **Given** the user is on SettingsScreen, **When** they click "Test Notification", **Then** a test notification is sent and confirmation shown
4. **Given** the user has modified settings, **When** they click Save, **Then** settings are persisted and a success message appears
5. **Given** the user has unsaved changes, **When** they try to navigate away, **Then** a confirmation dialog prompts "Discard changes?"

---

### User Story 5 - Navigating Between Screens (Priority: P1)

A developer moves fluidly between screens using navigation controls. From HomeScreen they can access Fly, Refuel, or Settings. From any screen, they can press Escape or click a back button to return to the previous screen. Modal dialogs for confirmations and errors overlay the current screen without losing context.

**Why this priority**: Screen navigation is foundational - all other functionality depends on users being able to navigate the application.

**Independent Test**: Can be fully tested by navigating through all screens using keyboard and mouse, verifying back navigation and modal behavior.

**Acceptance Scenarios**:

1. **Given** the user is on HomeScreen, **When** they select Fly/Refuel/Settings, **Then** they navigate to the corresponding screen
2. **Given** the user is on any non-Home screen, **When** they press Escape, **Then** they return to the previous screen
3. **Given** the user is on any screen, **When** a confirmation is needed, **Then** a modal dialog overlays the screen with confirm/cancel options
4. **Given** a modal is displayed, **When** the user presses Escape, **Then** the modal closes (equivalent to cancel)
5. **Given** an error occurs, **When** the error modal displays, **Then** the user sees error details and can dismiss with Enter or click

---

### User Story 6 - Cancelling Active Workflows (Priority: P2)

A developer starts a workflow but needs to cancel it mid-execution. They click the Cancel button which triggers a confirmation dialog. Upon confirmation, the workflow gracefully stops, cleanup occurs, and the user sees a summary of what was completed before cancellation.

**Why this priority**: Cancellation provides user control over long-running operations but is secondary to starting and completing workflows.

**Independent Test**: Can be fully tested by starting a mock workflow, triggering cancel, confirming, and verifying graceful shutdown and summary display.

**Acceptance Scenarios**:

1. **Given** a workflow is running, **When** the user clicks Cancel, **Then** a confirmation dialog asks "Cancel workflow? Progress will be lost."
2. **Given** the cancel confirmation appears, **When** the user confirms, **Then** the workflow stops gracefully
3. **Given** cancellation is confirmed, **When** the workflow stops, **Then** a summary shows which stages completed before cancellation
4. **Given** the cancel confirmation appears, **When** the user declines, **Then** the workflow continues and the dialog closes

---

### User Story 7 - Viewing Workflow History (Priority: P3)

A developer returns to Maverick and wants to review results from a previous workflow run. From HomeScreen they see recent workflow entries. Selecting one navigates to a read-only view of that workflow's results including the ReviewScreen findings if applicable.

**Why this priority**: Workflow history improves the user experience for returning users but is not essential for core workflow execution.

**Independent Test**: Can be fully tested by populating mock history data and verifying navigation to historical workflow views.

**Acceptance Scenarios**:

1. **Given** the user has run workflows previously, **When** they view HomeScreen, **Then** recent workflow runs display with name, date, and status
2. **Given** recent workflows are displayed, **When** the user selects one, **Then** they navigate to a read-only results view
3. **Given** a historical workflow had review findings, **When** viewing, **Then** the findings display (without action buttons since already processed)

---

### Edge Cases

- What happens when the user enters a branch name with only whitespace?
  - The input shows an error "Branch name cannot be empty" and Start is disabled
- What happens when GitHub API fails during issue fetch on RefuelScreen?
  - An error modal displays with the failure message and a Retry button
- What happens when the user attempts to start a workflow while one is already running?
  - The Start button is disabled and shows "Workflow in progress" tooltip
- What happens when screen transitions occur during a modal display?
  - The modal follows the user to the new screen if still relevant, or auto-dismisses if not
- What happens when the SettingsScreen cannot load current configuration?
  - Default values display with a warning banner "Could not load saved settings"
- What happens when network connectivity is lost mid-workflow?
  - A non-blocking warning appears; the workflow continues if possible or pauses. When connectivity is restored, the workflow auto-resumes immediately with a notification confirming resumption
- What happens when the ReviewScreen receives new findings while user is reviewing?
  - A non-blocking notification banner appears at the top of the screen: "New findings available"
  - A Refresh button is provided; clicking it reloads findings while preserving current selection if still valid
  - New findings are polled every 30 seconds during active review session

## Requirements *(mandatory)*

### Functional Requirements

#### HomeScreen

- **FR-001**: Screen MUST display application title and welcome message
- **FR-002**: Screen MUST provide navigation options for Fly, Refuel, and Settings workflows
- **FR-003**: Screen MUST display a list of recent workflow runs with name, timestamp, and status
- **FR-004**: Screen MUST support keyboard navigation between options (arrow keys, Enter to select)

#### FlyScreen

- **FR-005**: Screen MUST provide a text input for branch name with real-time validation
- **FR-006**: Screen MUST validate branch names against git naming rules (no spaces, valid characters)
- **FR-007**: Screen MUST check for existing branches and display appropriate indicator
- **FR-008**: Screen MUST provide an optional file selector for choosing a specific task file
- **FR-009**: Screen MUST provide Start and Cancel buttons
- **FR-010**: Screen MUST disable Start button when validation fails or workflow is running
- **FR-011**: Screen MUST display WorkflowProgress widget showing stage status during execution
- **FR-012**: Screen MUST display AgentOutput panel for streaming agent messages
- **FR-013**: Screen MUST automatically transition to ReviewScreen when code review stage completes

#### RefuelScreen

- **FR-014**: Screen MUST provide a text input for label filter
- **FR-015**: Screen MUST provide a numeric selector for issue limit (1-10 range)
- **FR-016**: Screen MUST provide a toggle switch for parallel vs sequential processing
- **FR-017**: Screen MUST display a list of matching GitHub issues with selection checkboxes
- **FR-018**: Screen MUST show issue title, number, and labels in the issue list
- **FR-019**: Screen MUST provide a Start button that activates when at least one issue is selected
- **FR-020**: Screen MUST display progress indicators during execution
- **FR-021**: Screen MUST display a results summary showing success/failure per issue on completion

#### ReviewScreen

- **FR-022**: Screen MUST integrate the ReviewFindings widget for displaying findings
- **FR-023**: Screen MUST display a side panel showing file diffs when a finding is selected
- **FR-024**: Screen MUST highlight the relevant code location in the diff panel
- **FR-025**: Screen MUST provide an Approve button to approve the review
- **FR-026**: Screen MUST provide a Request Changes button with text input for comments
- **FR-027**: Screen MUST provide a Dismiss action for individual findings
- **FR-028**: Screen MUST provide a Fix All action to trigger automatic fixes for all review findings
- **FR-029**: Screen MUST display fix results (success/failure per finding) after fix attempt completes

#### SettingsScreen

- **FR-030**: Screen MUST display configuration options in a form-based layout
- **FR-031**: Screen MUST organize settings into logical sections (GitHub, Notifications, Agents)
- **FR-032**: Screen MUST provide a Test GitHub Connection button with status feedback
- **FR-033**: Screen MUST provide a Test Notification button with confirmation feedback
- **FR-034**: Screen MUST provide Save and Cancel buttons
- **FR-035**: Screen MUST track unsaved changes and prompt before navigation away
- **FR-036**: Screen MUST validate setting values and show inline errors

#### Screen Navigation

- **FR-037**: System MUST support navigation from HomeScreen to Fly, Refuel, and Settings screens
- **FR-038**: System MUST support automatic transition from FlyScreen to ReviewScreen
- **FR-039**: System MUST support Escape key to navigate back or close modals
- **FR-040**: System MUST provide a visual back button as alternative to Escape

#### Modal Dialogs

- **FR-041**: System MUST support confirmation dialogs with configurable title, message, and button labels
- **FR-042**: System MUST support error dialogs with error details and dismiss action
- **FR-043**: System MUST trap focus within modal while displayed
- **FR-044**: System MUST support Escape to dismiss modals (as cancel)
- **FR-045**: System MUST dim or blur background content when modal is active

### Key Entities

- **Screen**: A distinct full-page view with its own layout, widgets, and navigation behavior (HomeScreen, FlyScreen, RefuelScreen, ReviewScreen, SettingsScreen)
- **ScreenState**: The current data and UI state for a screen including form values, selection state, and workflow progress
- **ModalDialog**: An overlay component for confirmations and error display with title, message content, and action buttons
- **NavigationContext**: Tracks screen history for back navigation and manages screen transitions
- **WorkflowSession**: Active workflow execution state including current stage, agent outputs, and results
- **WorkflowHistoryEntry**: Persisted record of a completed workflow containing: workflow type, branch name, timestamp, final status, stages completed, finding counts by severity, and PR link (if created)

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can navigate from HomeScreen to any workflow screen in 2 or fewer interactions
- **SC-002**: Branch name validation feedback appears within 200 milliseconds of keystroke
- **SC-003**: Users can start a Fly workflow within 30 seconds of launching the application
- **SC-004**: Issue list populates within 3 seconds of entering a label filter on RefuelScreen
- **SC-005**: Users can select issues and start RefuelWorkflow within 1 minute
- **SC-006**: File diff panel loads and highlights finding location within 1 second of selection
- **SC-007**: All review actions (approve, request changes, dismiss, fix) complete with feedback within 2 seconds
- **SC-008**: Settings changes save successfully with confirmation within 1 second
- **SC-009**: Modal dialogs appear within 100 milliseconds of trigger action
- **SC-010**: Back navigation (Escape) responds within 100 milliseconds
- **SC-011**: Screen transitions complete within 300 milliseconds with no visual glitches
- **SC-012**: 100% of screen interactions are achievable via keyboard alone

## Clarifications

### Session 2025-12-17

- Q: How should workflow history be persisted? → A: Simple JSON file in ~/.config/maverick/history.json
- Q: What should happen when network connectivity is restored after a workflow pause? → A: Auto-resume immediately when connectivity restored
- Q: How many workflow history entries should be retained? → A: Last 50 entries (balanced retention)
- Q: What scope should the automatic fix action have? → A: Fix all issues found in review
- Q: What data should each workflow history entry store? → A: Core metadata plus outcome summary (stages completed, finding counts, PR link)

## Assumptions

- Workflow history is persisted as a JSON file at ~/.config/maverick/history.json with FIFO eviction at 50 entries
- Screens build upon the layout and theming infrastructure defined in spec 011-tui-layout-theming
- Screens integrate widgets defined in spec 012-workflow-widgets (WorkflowProgress, AgentOutput, ReviewFindings, etc.)
- Git operations for branch name validation use local repository checks; remote checks may have slight delay
- GitHub issue fetching uses the GitHub CLI (gh) which must be authenticated
- File diffs are generated from git diff output parsed for display
- Automatic fixes triggered from ReviewScreen use agent-based fixing to address all findings from the review
- Settings persistence uses the existing Maverick configuration system (Pydantic models, file-based storage)
- Workflow history is stored locally and persists across application restarts
- Screen navigation follows a stack-based model where Escape pops the current screen
