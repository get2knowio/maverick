# Feature Specification: Validation Workflow

**Feature Branch**: `008-validation-workflow`
**Created**: 2025-12-12
**Status**: Draft
**Input**: User description: "Create a spec for the validation workflow in Maverick - a reusable workflow for running project validation with auto-fix capabilities."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Run Validation Workflow (Priority: P1)

A developer wants to validate their project changes before committing or creating a pull request. They run the validation workflow which executes format, lint, build, and test stages in sequence, automatically attempting to fix any issues that arise.

**Why this priority**: This is the core functionality - without the ability to run validation stages and attempt fixes, the workflow has no value.

**Independent Test**: Can be fully tested by running the workflow against a project with intentional issues (formatting errors, lint warnings) and verifying stages execute in order with fix attempts.

**Acceptance Scenarios**:

1. **Given** a project with configured validation stages, **When** the user initiates the validation workflow, **Then** each stage executes in configured order (format → lint → build → test)
2. **Given** a stage fails with fixable issues, **When** the workflow detects the failure, **Then** it invokes the fix agent to attempt repairs before retrying
3. **Given** a stage passes, **When** the workflow proceeds, **Then** it moves to the next stage without delay
4. **Given** all stages pass, **When** the workflow completes, **Then** it reports overall success with per-stage results

---

### User Story 2 - View Progress Updates (Priority: P2)

A developer wants real-time visibility into the validation process. As stages execute, they see progress updates showing current stage, pass/fail status, and fix attempts in progress.

**Why this priority**: Progress visibility enables developers to understand what's happening and estimate completion time, but the workflow can function without it.

**Independent Test**: Can be tested by running validation and observing streamed progress events appear in sequence with accurate stage and status information.

**Acceptance Scenarios**:

1. **Given** a validation workflow is running, **When** a stage begins, **Then** a progress update is emitted indicating the stage name and "in progress" status
2. **Given** a stage fails and fix is attempted, **When** the fix agent is invoked, **Then** progress updates indicate fix attempt number and activity
3. **Given** the workflow completes, **When** results are finalized, **Then** a summary update shows all stage outcomes

---

### User Story 3 - Configure Validation Stages (Priority: P2)

A developer wants to customize which validation stages run and how they behave. They configure stage names, commands, fixability, and maximum fix attempts to match their project's tooling.

**Why this priority**: Configuration enables the workflow to work across different project types, but default configurations provide immediate value.

**Independent Test**: Can be tested by providing custom stage configuration and verifying the workflow uses the specified commands and settings.

**Acceptance Scenarios**:

1. **Given** custom stage configuration, **When** the workflow runs, **Then** it uses the specified commands instead of defaults
2. **Given** a stage marked as not fixable, **When** that stage fails, **Then** the workflow reports failure without invoking fix agent
3. **Given** max fix attempts set to 3, **When** a stage fails repeatedly, **Then** the workflow stops after 3 fix attempts for that stage

---

### User Story 4 - Dry-Run Mode (Priority: P3)

A developer wants to preview what the validation workflow would do without actually running commands. They enable dry-run mode to see the planned execution sequence.

**Why this priority**: Dry-run is useful for verification but not essential for the core validation functionality.

**Independent Test**: Can be tested by running with dry-run enabled and verifying no actual commands execute while the plan is reported.

**Acceptance Scenarios**:

1. **Given** dry-run mode is enabled, **When** the workflow runs, **Then** no validation commands are actually executed
2. **Given** dry-run mode is enabled, **When** the workflow completes, **Then** it reports what commands would have run in what order

---

### User Story 5 - Cancel Workflow (Priority: P3)

A developer realizes they need to stop a running validation workflow. They request cancellation and the workflow terminates gracefully, reporting partial results.

**Why this priority**: Cancellation improves user control but most workflows will run to completion.

**Independent Test**: Can be tested by initiating cancellation mid-workflow and verifying graceful termination with partial results.

**Acceptance Scenarios**:

1. **Given** a validation workflow is running, **When** the user requests cancellation, **Then** the workflow stops at the earliest safe point
2. **Given** cancellation completes, **When** results are reported, **Then** partial results show which stages completed before cancellation

---

### Edge Cases

- When a stage command is not found or fails to start, the stage is immediately marked as failed (no fix attempts) and the workflow continues to the next stage
- When the fix agent produces no changes, it counts as a fix attempt and the stage is retried (uniform behavior with other fix attempts)
- Stages are never re-run; each stage executes once (with fix retries if applicable), and the workflow reports the final state of all stages
- When max_fix_attempts is set to 0, the stage is treated as non-fixable (fix agent is not invoked)
- When the same error persists across all fix attempts, the stage is marked FAILED after exhausting max_fix_attempts, and the workflow continues to the next stage
- When cancellation is requested during a fix attempt, the current fix attempt completes, then the workflow stops at the next cancellation check point (before the retry or next stage)

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST execute validation stages in a configurable sequential order
- **FR-002**: System MUST support at least four stage types: format, lint, build, and test
- **FR-003**: System MUST allow each stage to be configured with a custom command to execute
- **FR-004**: System MUST allow each stage to be marked as fixable or non-fixable
- **FR-005**: System MUST allow each stage to have a configurable maximum number of fix attempts
- **FR-006**: System MUST invoke a fix agent when a fixable stage fails, passing the error output
- **FR-007**: System MUST re-run a failed stage after each fix attempt
- **FR-008**: System MUST continue to the next stage after a stage passes
- **FR-009**: System MUST stop processing a stage after max fix attempts are exhausted
- **FR-010**: System MUST emit progress updates as async events for TUI consumption
- **FR-011**: System MUST support dry-run mode that reports planned actions without execution
- **FR-012**: System MUST be cancellable at any point during execution
- **FR-013**: System MUST provide default stage commands for common project types (starting with Python)
- **FR-014**: System MUST produce a structured result containing overall success/failure status
- **FR-015**: System MUST produce per-stage results indicating passed, failed, or fixed status
- **FR-016**: System MUST track and report the number of fix attempts made per stage
- **FR-017**: System MUST capture and report final error messages for failed stages
- **FR-018**: System MUST gracefully handle stage command execution failures (command not found, timeout)

### Key Entities

- **ValidationWorkflow**: The orchestrator that manages the validation process. Holds configuration, executes stages, coordinates fix attempts, and produces results.
- **ValidationStage**: A single validation step. Contains name, command, fixability flag, and max fix attempts.
- **StageResult**: The outcome of running a single stage. Contains status (passed/failed/fixed), number of fix attempts, and error messages if failed.
- **ValidationResult**: The complete outcome of the workflow. Contains overall success/failure, collection of per-stage results, and summary statistics.
- **ProgressUpdate**: An event emitted during workflow execution. Contains current stage, status, and contextual information for display.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Developers can run a complete validation cycle (format, lint, build, test) with a single command invocation
- **SC-002**: 80% of fixable issues (formatting, simple lint errors) are automatically resolved without manual intervention
- **SC-003**: Progress updates are emitted within 1 second of stage status changes for responsive TUI display
- **SC-004**: Workflow completes or reports failure within configured timeouts - no indefinite hangs
- **SC-005**: Cancellation takes effect within 5 seconds of being requested
- **SC-006**: Validation results provide sufficient detail for developers to understand what passed, failed, and was fixed
- **SC-007**: Workflow can be configured for any project type by providing appropriate stage commands

## Clarifications

### Session 2025-12-15

- Q: What should happen when a stage command is not found or fails to start? → A: Fail stage immediately, continue to next stage (fail-fast, complete picture)
- Q: How should the fix agent be provided to the ValidationWorkflow? → A: Follow existing pattern for agent injection into workflows (constructor injection)
- Q: Should the workflow re-run previously passed stages if a later stage fails? → A: No re-runs - each stage runs once, workflow reports final state
- Q: What should happen when the fix agent produces no changes? → A: Count as fix attempt, retry stage (simple, uniform behavior)
- Q: What should happen when max_fix_attempts is set to 0? → A: Treat as non-fixable, skip fix agent (0 means "don't fix")

## Assumptions

- The fix agent is provided via constructor injection following existing workflow patterns (the agent that attempts to fix issues is external to this workflow)
- Stage commands are available in the execution environment (e.g., `cargo` for Rust projects)
- The TUI or calling code will consume progress updates via async iteration
- Default stage commands assume standard tooling for each supported project type
- Fix attempts are sequential (not parallel) for a given stage
- Stages do not depend on previous stage outputs (each stage validates independently)
