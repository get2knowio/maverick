# Feature Specification: Fly Workflow Interface

**Feature Branch**: `009-fly-workflow`
**Created**: 2025-12-15
**Status**: Draft
**Input**: User description: "Create a spec for the 'fly' workflow INTERFACE in Maverick - defining the contract without full implementation."

**Note**: This spec defines the interface, stages, and data structures only. The full implementation will be done in Spec 26 using the workflow DSL.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Execute Complete Fly Workflow (Priority: P1)

A developer wants to run the complete fly workflow to implement a feature from spec to PR. They invoke the workflow with a branch name and optional task file, and the workflow orchestrates implementation, validation, code review, and PR creation stages in sequence.

**Why this priority**: This is the core use case - without the ability to execute the full workflow sequence, the interface provides no value.

**Independent Test**: Can be fully tested by instantiating a FlyWorkflow with valid inputs and verifying the execute() method exists with correct signature and raises NotImplementedError referencing Spec 26.

**Acceptance Scenarios**:

1. **Given** a FlyWorkflow is instantiated with valid FlyInputs, **When** execute() is called, **Then** it raises NotImplementedError with message referencing Spec 26 for implementation
2. **Given** FlyInputs with only branch_name provided, **When** the workflow is created, **Then** other fields use documented defaults (skip_review=False, skip_pr=False, draft_pr=False, base_branch="main")
3. **Given** FlyInputs with all optional fields provided, **When** the workflow is created, **Then** all fields are accessible with provided values

---

### User Story 2 - Track Workflow State (Priority: P1)

A developer or TUI needs to track the current state of the fly workflow. The workflow maintains a WorkflowState object that reflects the current stage, accumulated results, and any errors encountered.

**Why this priority**: State tracking is essential for TUI display and debugging - the interface must define how state is represented.

**Independent Test**: Can be tested by creating WorkflowState instances and verifying all required fields exist with correct types and defaults.

**Acceptance Scenarios**:

1. **Given** a new WorkflowState is created, **When** inspected, **Then** it has all required fields: stage, branch, task_file, implementation_result, validation_result, review_results, pr_url, errors, started_at, completed_at
2. **Given** WorkflowState is initialized, **When** stage changes occur (interface only), **Then** the stage field can hold any valid WorkflowStage enum value
3. **Given** errors occur during workflow, **When** stored in WorkflowState, **Then** errors list accumulates string error messages without losing previous entries

---

### User Story 3 - Receive Progress Events (Priority: P2)

A TUI application needs to display real-time progress as the fly workflow executes. The workflow emits typed progress events that indicate stage transitions and completion status.

**Why this priority**: Progress events enable responsive TUI display but the core workflow can function without consumers.

**Independent Test**: Can be tested by verifying progress event dataclass definitions exist with correct fields and types.

**Acceptance Scenarios**:

1. **Given** FlyWorkflowStarted event is created, **When** inspected, **Then** it contains the FlyInputs that triggered the workflow
2. **Given** FlyStageStarted/Completed events are created, **When** inspected, **Then** they contain the WorkflowStage enum value
3. **Given** FlyWorkflowCompleted event is created, **When** inspected, **Then** it contains the FlyResult
4. **Given** FlyWorkflowFailed event is created, **When** inspected, **Then** it contains error string and current WorkflowState

---

### User Story 4 - Configure Workflow Behavior (Priority: P2)

A developer wants to customize fly workflow behavior through configuration. They set options like parallel_reviews, max_validation_attempts, and notification preferences in FlyConfig.

**Why this priority**: Configuration enables workflow customization but reasonable defaults allow immediate use.

**Independent Test**: Can be tested by creating FlyConfig instances and verifying defaults match specification.

**Acceptance Scenarios**:

1. **Given** FlyConfig is created with no arguments, **When** inspected, **Then** defaults are: parallel_reviews=True, max_validation_attempts=3, coderabbit_enabled=False, auto_merge=False, notification_on_complete=True
2. **Given** FlyConfig with custom values, **When** stored in MaverickConfig, **Then** values are accessible via config.fly namespace

---

### User Story 5 - Retrieve Workflow Result (Priority: P1)

After workflow execution completes, the developer needs a structured result containing success status, final state, cost information, and a human-readable summary.

**Why this priority**: The result is the primary output of workflow execution - consumers must know how to interpret completion.

**Independent Test**: Can be tested by creating FlyResult instances and verifying all fields are present with correct types.

**Acceptance Scenarios**:

1. **Given** FlyResult is created, **When** inspected, **Then** it has: success (bool), state (WorkflowState), summary (str), token_usage (TokenUsage), total_cost_usd (float)
2. **Given** a successful workflow, **When** FlyResult.success is True, **Then** summary contains human-readable description of completed stages
3. **Given** a failed workflow, **When** FlyResult.success is False, **Then** state.errors contains reasons for failure

---

### Edge Cases

- When branch_name is empty string, FlyInputs validation should reject it with appropriate error
- When task_file path doesn't exist at validation time, the interface accepts it (validation occurs at runtime in Spec 26, raising `ConfigError` with descriptive message)
- When WorkflowStage enum is extended in future, existing code using the interface should not break
- When progress events are not consumed, the workflow interface doesn't block (async generator pattern)
- When multiple errors occur, WorkflowState.errors accumulates all of them chronologically

## Requirements *(mandatory)*

### Functional Requirements

#### Workflow Stage Enum

- **FR-001**: System MUST define WorkflowStage enum with values: INIT, IMPLEMENTATION, VALIDATION, CODE_REVIEW, CONVENTION_UPDATE, PR_CREATION, COMPLETE, FAILED
- **FR-002**: Each WorkflowStage value MUST have a string representation for display purposes

#### Input Definition

- **FR-003**: System MUST define FlyInputs dataclass with required field: branch_name (str, non-empty)
- **FR-004**: System MUST define FlyInputs with optional fields: task_file (Path | None), skip_review (bool=False), skip_pr (bool=False), draft_pr (bool=False), base_branch (str="main")
- **FR-005**: FlyInputs MUST validate that branch_name is not empty

#### State Management

- **FR-006**: System MUST define WorkflowState dataclass with stage (WorkflowStage), branch (str), task_file (Path | None)
- **FR-007**: WorkflowState MUST include result fields: implementation_result (AgentResult | None), validation_result (ValidationWorkflowResult | None), review_results (list[AgentResult])
- **FR-008**: WorkflowState MUST include: pr_url (str | None), errors (list[str]), started_at (datetime), completed_at (datetime | None)

#### Result Definition

- **FR-009**: System MUST define FlyResult dataclass with: success (bool), state (WorkflowState), summary (str)
- **FR-010**: FlyResult MUST include usage tracking: token_usage (AgentUsage), total_cost_usd (float)
- **FR-011**: FlyResult.summary MUST be human-readable text summarizing workflow outcome

#### Progress Events

- **FR-012**: System MUST define FlyWorkflowStarted event containing inputs (FlyInputs)
- **FR-013**: System MUST define FlyStageStarted event containing stage (WorkflowStage)
- **FR-014**: System MUST define FlyStageCompleted event containing stage (WorkflowStage) and result (Any)
- **FR-015**: System MUST define FlyWorkflowCompleted event containing result (FlyResult)
- **FR-016**: System MUST define FlyWorkflowFailed event containing error (str) and state (WorkflowState)

#### Workflow Class

- **FR-017**: System MUST define FlyWorkflow class with constructor accepting config (FlyConfig | None)
- **FR-018**: FlyWorkflow MUST have async execute(inputs: FlyInputs) -> FlyResult method
- **FR-019**: FlyWorkflow.execute() MUST raise NotImplementedError with message referencing Spec 26
- **FR-020**: FlyWorkflow.execute() MUST have detailed docstring describing each stage's intended behavior

#### Configuration

- **FR-021**: System MUST define FlyConfig with: parallel_reviews (bool=True), max_validation_attempts (int=3)
- **FR-022**: FlyConfig MUST include: coderabbit_enabled (bool=False), auto_merge (bool=False), notification_on_complete (bool=True)
- **FR-023**: FlyConfig MUST be integratable into MaverickConfig as fly: FlyConfig field

### Key Entities

- **WorkflowStage**: Enum representing the eight possible stages of the fly workflow. Each stage represents a distinct phase with specific responsibilities.
- **FlyInputs**: Input dataclass containing all parameters needed to start a fly workflow execution. Validated on construction.
- **WorkflowState**: Mutable state container tracking current stage, accumulated results, and errors throughout workflow execution.
- **FlyResult**: Immutable result object returned after workflow completion. Contains success status, final state, summary, and cost information.
- **FlyConfig**: Configuration model for customizing fly workflow behavior. Integrated into MaverickConfig hierarchy.
- **FlyWorkflow**: Main workflow class with stub execute() method. Will be fully implemented in Spec 26.
- **Progress Events**: Set of typed event dataclasses (FlyWorkflowStarted, FlyStageStarted, FlyStageCompleted, FlyWorkflowCompleted, FlyWorkflowFailed) for TUI consumption.
- **AgentUsage**: Existing type from maverick.agents.result module tracking input_tokens, output_tokens, total_cost_usd, and duration_ms.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All 8 WorkflowStage enum values are defined and accessible
- **SC-002**: FlyInputs correctly validates and rejects empty branch_name
- **SC-003**: WorkflowState contains all 10 specified fields with correct types
- **SC-004**: FlyResult provides human-readable summary for any workflow outcome
- **SC-005**: All 5 progress event types are defined with correct field signatures
- **SC-006**: FlyWorkflow.execute() raises NotImplementedError mentioning Spec 26
- **SC-007**: FlyConfig defaults match specification exactly
- **SC-008**: All interface types are importable from maverick.workflows.fly module
- **SC-009**: Interface types integrate with existing maverick.agents.result.AgentResult and maverick.models.validation.ValidationWorkflowResult
- **SC-010**: Full test coverage (100%) for all dataclass validation and enum definitions

## Stage Descriptions (for FlyWorkflow docstring)

The following describes the intended behavior of each stage when implemented in Spec 26:

### INIT Stage
Parse command-line arguments, validate inputs, create or checkout the feature branch, and load the task specification file if provided. Syncs branch with origin/main.

### IMPLEMENTATION Stage
Execute the ImplementerAgent on tasks defined in tasks.md. Tasks marked with "P:" prefix are executed in parallel. Each task completion results in atomic commits.

### VALIDATION Stage
Run the ValidationWorkflow (format, lint, typecheck, test) with auto-fix capabilities. Retries up to max_validation_attempts with fix agent for fixable issues.

### CODE_REVIEW Stage
Run parallel code reviews if enabled. Optionally integrates CodeRabbit CLI for enhanced review. Collects review comments and suggestions.

### CONVENTION_UPDATE Stage
Analyze implementation findings and review feedback. Suggest updates to CLAUDE.md if significant learnings or patterns were discovered.

### PR_CREATION Stage
Generate pull request body from implementation results and review findings. Create or update PR via GitHub CLI. Optionally marks PR as draft.

### COMPLETE Stage
Terminal state indicating successful workflow completion. All stages passed and PR is ready (created or updated).

### FAILED Stage
Terminal state indicating workflow failure. WorkflowState.errors contains reasons for failure.

## Assumptions

- AgentUsage type will be imported from maverick.agents.result module
- AgentResult type exists in maverick.agents.result module
- ValidationWorkflowResult type exists in maverick.models.validation module
- The workflow DSL for full implementation will be designed in Spec 26
- Progress events follow the same async generator pattern as ValidationWorkflow
- Configuration follows existing MaverickConfig/Pydantic patterns
