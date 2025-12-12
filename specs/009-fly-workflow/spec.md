# Feature Specification: FlyWorkflow - Spec-Based Development Workflow

**Feature Branch**: `009-fly-workflow`
**Created**: 2025-12-12
**Status**: Draft
**Input**: User description: "Create a spec for the fly workflow in Maverick - the main spec-based development workflow."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Execute Complete Development Cycle (Priority: P1)

A developer has a feature specification with a tasks.md file ready for implementation. They invoke the FlyWorkflow with the spec directory path. The workflow orchestrates the entire development cycle: creating a branch, implementing tasks, running validation, executing code review, and creating a pull request - all without manual intervention.

**Why this priority**: This is the core value proposition - automating the full development cycle from spec to PR. Without this end-to-end orchestration, the workflow provides no value beyond running individual agents manually.

**Independent Test**: Can be fully tested by providing a spec directory with tasks.md and verifying the workflow produces a branch with commits, passes validation, and creates a PR with comprehensive summary.

**Acceptance Scenarios**:

1. **Given** a spec directory containing tasks.md, **When** the user starts FlyWorkflow, **Then** the workflow creates/checks out a feature branch and begins implementation.
2. **Given** tasks are executed successfully, **When** implementation completes, **Then** the workflow automatically proceeds to validation.
3. **Given** validation passes, **When** code review begins, **Then** parallel review agents execute and produce findings.
4. **Given** all stages complete successfully, **When** PR creation runs, **Then** a pull request is created with a comprehensive summary including implementation details, validation results, and review findings.

---

### User Story 2 - Track and Resume Interrupted Workflows (Priority: P1)

A developer's workflow is interrupted (network issue, system restart, manual cancellation). When they reinvoke the workflow, it detects the previous state and resumes from the last completed stage rather than starting over.

**Why this priority**: Long-running workflows (hours for large features) must be resilient to interruption. Losing progress and restarting from scratch would be unacceptable.

**Independent Test**: Can be tested by running a workflow, stopping it mid-stage, then restarting and verifying it resumes from the correct stage with preserved state.

**Acceptance Scenarios**:

1. **Given** a workflow was interrupted after IMPLEMENTATION completed, **When** the workflow is restarted with the same spec, **Then** it resumes from VALIDATION stage.
2. **Given** a workflow state file exists for the spec, **When** the workflow initializes, **Then** it loads the previous state and offers to resume or restart.
3. **Given** a resume is requested, **When** the workflow continues, **Then** all previous stage results are preserved and available to subsequent stages.

---

### User Story 3 - View Real-Time Progress Updates (Priority: P2)

A developer wants visibility into workflow progress. As stages execute, they receive real-time updates showing current stage, sub-tasks, and status. The TUI can display this information to keep users informed during long operations.

**Why this priority**: Progress visibility is essential for user confidence and enables informed decisions about interruption or continuation, but the workflow can complete without it.

**Independent Test**: Can be tested by running a workflow and verifying progress events are emitted for each stage transition, sub-task, and status change.

**Acceptance Scenarios**:

1. **Given** a workflow is running, **When** a stage begins, **Then** a progress event is emitted with stage name and "in progress" status.
2. **Given** implementation is running, **When** individual tasks complete, **Then** progress events indicate task completion and remaining work.
3. **Given** validation is running with fix attempts, **When** fixes are attempted, **Then** progress events indicate fix attempt number and outcome.
4. **Given** the workflow completes, **When** the final event is emitted, **Then** it includes overall success/failure and summary statistics.

---

### User Story 4 - Skip Stages for Quick Iterations (Priority: P2)

A developer wants to skip certain stages during rapid iteration. They configure the workflow to skip code review for quick local testing, or skip convention update when making minor changes.

**Why this priority**: Flexibility in stage execution enables faster iteration cycles, though full workflow execution is the recommended default.

**Independent Test**: Can be tested by configuring skip stages and verifying those stages are bypassed while others execute normally.

**Acceptance Scenarios**:

1. **Given** CODE_REVIEW is in skip_stages, **When** the workflow runs, **Then** it proceeds directly from VALIDATION to CONVENTION_UPDATE.
2. **Given** multiple stages are skipped, **When** the workflow completes, **Then** skipped stages are marked as "skipped" in results rather than absent.
3. **Given** all optional stages are skipped, **When** the workflow runs, **Then** only INIT, IMPLEMENTATION, and PR_CREATION execute.

---

### User Story 5 - Configure Parallel Execution (Priority: P3)

A developer wants to control the level of parallelism for tasks and reviews. They configure the maximum number of parallel agents to balance speed against resource usage.

**Why this priority**: Parallelism tuning is an optimization that doesn't affect core functionality but improves performance for large features.

**Independent Test**: Can be tested by configuring parallel count and verifying no more than the specified number of agents run concurrently.

**Acceptance Scenarios**:

1. **Given** parallel_agent_count is set to 3, **When** tasks marked for parallel execution run, **Then** at most 3 tasks execute concurrently.
2. **Given** parallel_agent_count is set to 1, **When** parallel tasks run, **Then** they execute sequentially.
3. **Given** multiple code reviewers are configured, **When** CODE_REVIEW runs, **Then** reviewers execute in parallel up to the configured limit.

---

### User Story 6 - Receive Completion Notifications (Priority: P3)

A developer starts a long-running workflow and wants to be notified when it completes. They configure notifications via their preferred channel (system notification, push notification via ntfy, etc.).

**Why this priority**: Notifications are a convenience feature for unattended workflows but don't affect core functionality.

**Independent Test**: Can be tested by configuring notification settings and verifying notifications are sent on workflow completion.

**Acceptance Scenarios**:

1. **Given** notifications are enabled, **When** the workflow completes successfully, **Then** a success notification is sent with PR URL.
2. **Given** notifications are enabled, **When** the workflow fails, **Then** a failure notification is sent with error summary.
3. **Given** ntfy topic is configured, **When** notification is triggered, **Then** it is sent via the ntfy service.

---

### Edge Cases

- What happens when the spec directory doesn't contain tasks.md?
- How does the workflow handle when the feature branch already exists with commits?
- What happens if validation passes but code review finds critical issues?
- How does the workflow handle when GitHub CLI is not authenticated?
- What happens if PR creation fails (permission denied, branch protection)?
- How does the workflow behave when resuming from a corrupted state file?
- What happens if the same workflow is started twice concurrently for the same spec?
- How are parallel tasks handled when one fails and others are still running?

## Requirements *(mandatory)*

### Functional Requirements - Workflow Orchestration

- **FR-001**: System MUST provide a `FlyWorkflow` class that orchestrates the complete development cycle.
- **FR-002**: FlyWorkflow MUST support six sequential stages: INIT, IMPLEMENTATION, VALIDATION, CODE_REVIEW, CONVENTION_UPDATE, PR_CREATION.
- **FR-003**: FlyWorkflow MUST maintain workflow state across all stages using a `WorkflowState` dataclass.
- **FR-004**: FlyWorkflow MUST persist state to disk after each stage completion for resume capability.
- **FR-005**: FlyWorkflow MUST detect and load existing state on startup, offering resume or restart options.
- **FR-006**: FlyWorkflow MUST emit progress updates as an async generator for TUI consumption.
- **FR-007**: FlyWorkflow MUST be cancellable at any point, persisting current state before termination.

### Functional Requirements - INIT Stage

- **FR-008**: INIT stage MUST parse workflow arguments including spec directory path and configuration options.
- **FR-009**: INIT stage MUST validate that the spec directory contains required files (at minimum, tasks.md).
- **FR-010**: INIT stage MUST create a new feature branch or checkout existing branch matching the spec.
- **FR-011**: INIT stage MUST sync the branch with origin/main to ensure a clean starting point.
- **FR-012**: INIT stage MUST load and parse the task file to determine implementation scope.

### Functional Requirements - IMPLEMENTATION Stage

- **FR-013**: IMPLEMENTATION stage MUST invoke the ImplementerAgent with the parsed tasks.
- **FR-014**: IMPLEMENTATION stage MUST support parallel execution of tasks marked with "P:" prefix.
- **FR-015**: IMPLEMENTATION stage MUST respect the configured parallel_agent_count for concurrent tasks.
- **FR-016**: IMPLEMENTATION stage MUST track completion status of each task.
- **FR-017**: IMPLEMENTATION stage MUST continue with remaining tasks if individual tasks fail (fail-gracefully).
- **FR-018**: IMPLEMENTATION stage MUST collect all task results and artifacts for subsequent stages.

### Functional Requirements - VALIDATION Stage

- **FR-019**: VALIDATION stage MUST invoke the ValidationWorkflow with appropriate stage configuration.
- **FR-020**: VALIDATION stage MUST support auto-fix mode where the fix agent attempts to resolve failures.
- **FR-021**: VALIDATION stage MUST track validation attempts and fix iterations.
- **FR-022**: VALIDATION stage MUST capture final validation results including any remaining failures.

### Functional Requirements - CODE_REVIEW Stage

- **FR-023**: CODE_REVIEW stage MUST invoke parallel code review agents.
- **FR-024**: CODE_REVIEW stage MUST support multiple reviewers: CodeReviewerAgent (required) and CodeRabbit (optional).
- **FR-025**: CODE_REVIEW stage MUST aggregate findings from all reviewers into a unified report.
- **FR-026**: CODE_REVIEW stage MUST categorize findings by severity (critical, warning, suggestion).

### Functional Requirements - CONVENTION_UPDATE Stage

- **FR-027**: CONVENTION_UPDATE stage MUST analyze code review findings for patterns worth documenting.
- **FR-028**: CONVENTION_UPDATE stage MUST suggest updates to CLAUDE.md when significant learnings are identified.
- **FR-029**: CONVENTION_UPDATE stage MUST require explicit user approval before modifying CLAUDE.md.
- **FR-030**: CONVENTION_UPDATE stage MUST skip automatically when no significant learnings are identified.

### Functional Requirements - PR_CREATION Stage

- **FR-031**: PR_CREATION stage MUST generate a comprehensive PR body including: summary, implementation details, validation results, and review findings.
- **FR-032**: PR_CREATION stage MUST create a new PR or update existing PR for the feature branch.
- **FR-033**: PR_CREATION stage MUST use GitHub CLI (gh) for PR operations.
- **FR-034**: PR_CREATION stage MUST return the PR URL in the workflow result.
- **FR-035**: PR_CREATION stage MUST support auto-merge configuration when all checks pass.

### Functional Requirements - Configuration

- **FR-036**: System MUST accept configuration for skip_stages (list of stages to bypass).
- **FR-037**: System MUST accept configuration for parallel_agent_count (default: 3).
- **FR-038**: System MUST accept configuration for auto_merge (default: false).
- **FR-039**: System MUST accept configuration for notifications (enabled, channel, topic).

### Key Entities

- **FlyWorkflow**: The main orchestrator class. Manages stage execution, state persistence, progress reporting, and error handling. Receives configuration and dependencies via constructor.
- **WorkflowState**: Dataclass tracking workflow execution state. Contains current stage (enum), branch name, task file path, stage results (dict mapping stage to result), errors encountered (list), and PR URL when created.
- **WorkflowStage**: Enum defining the six workflow stages: INIT, IMPLEMENTATION, VALIDATION, CODE_REVIEW, CONVENTION_UPDATE, PR_CREATION.
- **StageResult**: Dataclass for individual stage outcomes. Contains stage name, status (completed/failed/skipped), output data, errors, and duration.
- **FlyWorkflowConfig**: Pydantic model for workflow configuration. Contains skip_stages (list), parallel_agent_count (int), auto_merge (bool), notifications (NotificationConfig).
- **ProgressUpdate**: Event emitted during workflow execution. Contains current stage, status, message, progress percentage (if calculable), and metadata.
- **NotificationConfig**: Configuration for completion notifications. Contains enabled flag, channel type (system/ntfy), and ntfy topic if applicable.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Developers can execute a complete development cycle from spec to PR with a single workflow invocation.
- **SC-002**: Workflow can be interrupted and resumed from any completed stage without data loss or duplicate work.
- **SC-003**: Progress updates are emitted within 2 seconds of significant state changes for responsive TUI display.
- **SC-004**: Parallel task execution achieves at least 50% speedup compared to sequential execution for parallelizable tasks.
- **SC-005**: Complete workflow execution for a typical 5-task feature completes within 30 minutes under normal conditions.
- **SC-006**: PR summaries generated by the workflow contain sufficient detail for reviewers to understand changes without reading all code.
- **SC-007**: 95% of workflows that pass validation also pass CI checks after PR creation.
- **SC-008**: Workflow state files are human-readable (JSON) for debugging and manual inspection.

## Assumptions

- The ImplementerAgent exists and can execute tasks from a task file (from feature 004-implementer-issue-fixer-agents).
- The ValidationWorkflow exists and can run validation stages with auto-fix (from feature 008-validation-workflow).
- The CodeReviewerAgent exists and can produce structured review findings (planned future feature).
- GitHub CLI (gh) is installed and authenticated for PR operations.
- CodeRabbit CLI is optional and the workflow degrades gracefully if unavailable.
- The TUI or calling code will consume progress updates via async iteration.
- State files are stored in the spec directory (e.g., specs/009-fly-workflow/.workflow-state.json).
- Branch naming follows the convention: {number}-{short-name} matching the spec directory.
- CLAUDE.md exists at the repository root for convention updates.
- Notification services (ntfy) require external configuration by the user.

## Dependencies

- Feature 002-base-agent: MaverickAgent base class for agent interactions
- Feature 004-implementer-issue-fixer-agents: ImplementerAgent for task execution
- Feature 008-validation-workflow: ValidationWorkflow for validation with auto-fix
- Claude Agent SDK: Core AI interaction capability
- Pydantic: Configuration and state model validation
- GitHub CLI: PR creation and management
- Git CLI: Branch operations
- CodeRabbit CLI: Optional enhanced code review
- ntfy: Optional push notifications
