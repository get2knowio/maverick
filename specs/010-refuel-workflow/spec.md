# Feature Specification: Refuel Workflow Interface

**Feature Branch**: `010-refuel-workflow`
**Created**: 2025-12-15
**Status**: Draft
**Input**: User description: "Create a spec for the 'refuel' workflow INTERFACE in Maverick - defining the contract without full implementation. This spec defines the interface and data structures only. The full implementation will be done in Spec 26 using the workflow DSL."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Configure and Execute Refuel Workflow (Priority: P1)

A developer wants to process tech-debt issues from their GitHub repository automatically. They configure the refuel workflow with their desired parameters (label filter, issue limit, parallel processing) and execute it to have issues automatically fixed, validated, and PRs created.

**Why this priority**: This is the core value proposition - automating the tedious process of fixing tech-debt issues one by one. Without this capability, the entire workflow has no purpose.

**Independent Test**: Can be fully tested by providing RefuelInputs to the workflow and verifying it returns a RefuelResult with the expected structure containing issue processing outcomes.

**Acceptance Scenarios**:

1. **Given** a configured RefuelInputs with default values, **When** the workflow is executed, **Then** the system returns a RefuelResult with success status and issue counts.
2. **Given** RefuelInputs with a custom label "bug-fix", **When** the workflow is executed, **Then** only issues with the "bug-fix" label are considered for processing.
3. **Given** RefuelInputs with limit=3, **When** the workflow is executed, **Then** no more than 3 issues are processed regardless of how many match the label.

---

### User Story 2 - Monitor Processing Progress (Priority: P2)

A developer wants to see real-time progress as issues are being processed. They observe progress events (RefuelStarted, IssueProcessingStarted, IssueProcessingCompleted, RefuelCompleted) to understand which issues are being worked on and their outcomes.

**Why this priority**: Progress visibility is essential for long-running workflows. Users need feedback to understand system activity and estimate completion time.

**Independent Test**: Can be tested by subscribing to the workflow's progress events and verifying each event type is emitted at the appropriate stage with correct data.

**Acceptance Scenarios**:

1. **Given** a workflow execution starts, **When** issues are found, **Then** a RefuelStarted event is emitted with the input configuration and issue count.
2. **Given** processing begins on an issue, **When** the IssueFixerAgent starts, **Then** an IssueProcessingStarted event is emitted with the issue details, index, and total count.
3. **Given** an issue processing completes (success or failure), **When** the result is determined, **Then** an IssueProcessingCompleted event is emitted with the full IssueProcessingResult.
4. **Given** all issues have been processed, **When** the workflow ends, **Then** a RefuelCompleted event is emitted with the aggregate RefuelResult.

---

### User Story 3 - Preview Issues Without Processing (Priority: P2)

A developer wants to see which issues would be processed before committing to actual changes. They use dry-run mode to list matching issues without creating branches, running agents, or creating PRs.

**Why this priority**: Dry-run capability prevents accidental bulk operations and allows users to validate their configuration before execution.

**Independent Test**: Can be tested by executing with dry_run=True and verifying no branches are created, no PRs are opened, and issues are returned with SKIPPED status.

**Acceptance Scenarios**:

1. **Given** RefuelInputs with dry_run=True, **When** the workflow executes, **Then** issues are listed but no branches are created.
2. **Given** RefuelInputs with dry_run=True, **When** the workflow completes, **Then** all issues in results have status=SKIPPED with no branch or pr_url.
3. **Given** RefuelInputs with dry_run=True, **When** the workflow completes, **Then** issues_processed count is 0 and issues_found reflects the matching issues count.

---

### User Story 4 - Process Issues in Parallel (Priority: P3)

A developer with many tech-debt issues wants to speed up processing by handling multiple issues concurrently. They enable parallel mode to process issues simultaneously within configured concurrency limits.

**Why this priority**: Parallel processing is an optimization feature. Sequential processing works correctly and must be proven before parallel execution.

**Independent Test**: Can be tested by executing with parallel=True and verifying multiple issues are processed concurrently (overlapping timestamps in results) while respecting max_parallel configuration.

**Acceptance Scenarios**:

1. **Given** RefuelInputs with parallel=True and 5 issues, **When** max_parallel=3 in configuration, **Then** at most 3 issues are processed concurrently.
2. **Given** parallel processing enabled, **When** one issue processing fails, **Then** other parallel issues continue processing unaffected.
3. **Given** parallel=False (default), **When** multiple issues exist, **Then** issues are processed sequentially one at a time.

---

### User Story 5 - Track Processing Results and Costs (Priority: P3)

A developer wants to understand the cost and token usage of the refuel workflow. They review the RefuelResult to see total duration, cost breakdown, and per-issue token usage.

**Why this priority**: Cost tracking is important for budget management but is secondary to core functionality.

**Independent Test**: Can be tested by executing the workflow and verifying RefuelResult contains accurate total_duration_ms, total_cost_usd, and per-issue AgentUsage values.

**Acceptance Scenarios**:

1. **Given** a completed workflow execution, **When** examining RefuelResult, **Then** total_duration_ms reflects the actual processing time.
2. **Given** multiple issues processed, **When** examining results, **Then** each IssueProcessingResult contains agent_usage with input/output token counts.
3. **Given** a completed workflow, **When** examining total_cost_usd, **Then** it represents the sum of all agent execution costs.

---

### Edge Cases

- What happens when no issues match the specified label? The workflow returns success=True with issues_found=0 and empty results list.
- What happens when an issue is already assigned to another user? If skip_if_assigned=True (default), the issue is skipped with status=SKIPPED.
- What happens when the IssueFixerAgent fails to fix an issue? The issue is marked with status=FAILED, error is populated, and processing continues to the next issue.
- What happens when validation fails after an issue fix? The issue is marked with status=FAILED with validation error details, no PR is created.
- What happens when GitHub API rate limiting occurs? The workflow reports the error in the affected issue's result and continues with remaining issues.
- What happens when branch creation fails (e.g., branch already exists)? The issue is marked FAILED with appropriate error message.

## Requirements *(mandatory)*

### Functional Requirements

**Data Structures**:

- **FR-001**: System MUST define a GitHubIssue dataclass with fields: number (int), title (str), body (Optional[str]), labels (list[str]), assignee (Optional[str]), url (str).
- **FR-002**: System MUST define a RefuelInputs dataclass with fields: label (str, default="tech-debt"), limit (int, default=5), parallel (bool, default=False), dry_run (bool, default=False), auto_assign (bool, default=True).
- **FR-003**: System MUST define an IssueStatus enum with values: PENDING, IN_PROGRESS, FIXED, FAILED, SKIPPED.
- **FR-004**: System MUST define an IssueProcessingResult dataclass with fields: issue (GitHubIssue), status (IssueStatus), branch (Optional[str]), pr_url (Optional[str]), error (Optional[str]), duration_ms (int), agent_usage (AgentUsage).
- **FR-005**: System MUST define a RefuelResult dataclass with fields: success (bool), issues_found (int), issues_processed (int), issues_fixed (int), issues_failed (int), issues_skipped (int), results (list[IssueProcessingResult]), total_duration_ms (int), total_cost_usd (float).

**Progress Events**:

- **FR-006**: System MUST define a RefuelStarted event dataclass containing inputs (RefuelInputs) and issues_found (int).
- **FR-007**: System MUST define an IssueProcessingStarted event dataclass containing issue (GitHubIssue), index (int, 1-based), and total (int).
- **FR-008**: System MUST define an IssueProcessingCompleted event dataclass containing result (IssueProcessingResult).
- **FR-009**: System MUST define a RefuelCompleted event dataclass containing result (RefuelResult).

**Workflow Interface**:

- **FR-010**: System MUST define a RefuelWorkflow class with an async execute(inputs: RefuelInputs) method that returns AsyncGenerator[RefuelProgressEvent, None], yielding progress events in sequence: RefuelStarted, then IssueProcessingStarted/IssueProcessingCompleted pairs for each issue, and finally RefuelCompleted containing the aggregate RefuelResult.
- **FR-011**: The execute method MUST raise NotImplementedError with a message containing 'Spec 26' to indicate full implementation is deferred.
- **FR-012**: The execute method MUST include a docstring describing the intended per-issue processing flow: (1) Create branch, (2) Run IssueFixerAgent, (3) Run validation, (4) Commit with conventional message, (5) Push and create PR linking to issue, (6) Optionally close issue on PR merge.

**Event Ordering**:

The execute() method MUST emit events in this order:
1. RefuelStarted - once at workflow start with inputs and discovered issue count
2. IssueProcessingStarted - before processing each issue (1-based index)
3. IssueProcessingCompleted - after each issue completes (success or failure)
4. RefuelCompleted - once at workflow end with aggregate RefuelResult

**Configuration**:

- **FR-013**: System MUST define a RefuelConfig dataclass with fields: default_label (str, default="tech-debt"), branch_prefix (str, default="fix/issue-"), link_pr_to_issue (bool, default=True), close_on_merge (bool, default=False), skip_if_assigned (bool, default=True), max_parallel (int, default=3).
- **FR-014**: RefuelConfig MUST be integrated into MaverickConfig as a nested configuration section under the 'refuel' key.

**Type Safety**:

- **FR-015**: All dataclasses MUST use frozen=True and slots=True for immutability and memory efficiency.
- **FR-016**: All dataclasses MUST use Python type hints with Optional[] for nullable fields.

### Key Entities

- **GitHubIssue**: Minimal representation of a GitHub issue - contains number, title, body, labels, assignee, and URL.
- **RefuelInputs**: Configuration for a single workflow execution - specifies what issues to process and how.
- **RefuelResult**: Aggregate outcome of workflow execution - summarizes success/failure counts and contains per-issue results.
- **IssueProcessingResult**: Outcome of processing a single issue - includes status, created branch, PR URL, errors, and metrics.
- **IssueStatus**: Lifecycle state of an issue during processing - tracks progression from PENDING through completion.
- **RefuelConfig**: Persistent configuration for the refuel workflow - defines defaults and behavior policies.
- **Progress Events**: Real-time notifications emitted during workflow execution - enables TUI updates and logging.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All data structures (RefuelInputs, RefuelResult, IssueProcessingResult, IssueStatus, RefuelConfig) can be instantiated with default values and serialize correctly.
- **SC-002**: The RefuelWorkflow.execute() method signature matches the interface contract and raises NotImplementedError when called.
- **SC-003**: All progress event dataclasses can be instantiated with their required fields and used for type-safe event handling.
- **SC-004**: RefuelConfig integrates into MaverickConfig and can be loaded from YAML configuration files.
- **SC-005**: 100% of public interfaces have complete type annotations that pass mypy strict mode.
- **SC-006**: All dataclasses enforce immutability (frozen=True) - attempting to modify fields raises an error.
- **SC-007**: The execute method returns an AsyncGenerator yielding progress events, consumable via `async for event in workflow.execute(inputs)`.

## Assumptions

- **A-001**: GitHubIssue dataclass is defined locally in this spec with minimal fields; may be superseded by a richer type in a future spec.
- **A-002**: AgentUsage dataclass exists in the base agent module (002-base-agent) and will be imported.
- **A-003**: MaverickConfig exists and supports nested configuration sections.
- **A-004**: The full implementation in Spec 26 will use these exact interfaces without modification.
- **A-005**: Branch naming follows the pattern: {branch_prefix}{issue_number} (e.g., "fix/issue-123").
- **A-006**: Default limit of 5 balances workflow duration with reasonable coverage for typical tech-debt batches.
- **A-007**: Default max_parallel of 3 prevents overwhelming CI resources while providing meaningful parallelization.

## Clarifications

### Session 2025-12-15

- Q: How should the spec handle dependency on external types (GitHubIssue, TokenUsage)? → A: Import from existing modules; use `AgentUsage` (not `TokenUsage`).
- Q: What is the primary progress event delivery mechanism? → A: Async generator (`async for event in workflow.execute(...)`).
- Q: Should this spec define GitHubIssue or declare it as a hard prerequisite? → A: Define minimal GitHubIssue locally (number, title, body, labels, assignee, url).

## Out of Scope

- Full workflow implementation (deferred to Spec 26)
- GitHub API integration details
- IssueFixerAgent implementation
- Validation workflow integration
- TUI integration for progress display
- Retry/recovery logic for failed issues
- Issue assignment/claim logic implementation
