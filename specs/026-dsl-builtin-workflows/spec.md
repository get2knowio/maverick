# Feature Specification: DSL-Based Built-in Workflow Implementation

**Feature Branch**: `026-dsl-builtin-workflows`
**Created**: 2025-12-20
**Status**: Draft
**Input**: User description: "This is spec id 026: Create a spec for implementing all built-in workflows using the DSL. This spec implements the interfaces defined in Specs 8-10 using the DSL from Specs 22-24. All workflows follow the orchestration patterns from Spec 20."

## Clarifications

### Session 2025-12-20

- Q: Should fly workflow support dry-run mode for parity with refuel? → A: Yes, add dry_run to fly workflow
- Q: How should workflows handle API credentials and secrets? → A: Credentials injected via MaverickConfig; never logged in step results or progress events
- Q: What should be explicitly out of scope for this spec? → A: New DSL features, new agent types, workflow marketplace (all separate spec concerns)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Execute Fly Workflow via DSL (Priority: P1)

A developer wants to implement a feature from specification to pull request using the fly workflow. They provide a branch name and optional task file, and the DSL-based workflow orchestrates implementation, validation with fixes, code review, and PR creation, all while emitting progress events for TUI display.

**Why this priority**: The fly workflow is the primary automation capability and demonstrates the full power of the DSL by combining multiple step types (python, agent, generate, validate, sub-workflow).

**Independent Test**: Can be fully tested by executing the fly workflow with a mock task file and verifying each stage completes in order, produces the expected step results, and returns a FlyResult with all fields populated.

**Acceptance Scenarios**:

1. **Given** valid FlyInputs with branch_name and task_file, **When** the fly workflow executes, **Then** it creates a branch, runs implementation, validates with fixes, commits, reviews (if not skipped), and creates a PR (if not skipped).
2. **Given** skip_review=True, **When** the fly workflow executes, **Then** the code review stage is skipped and the workflow proceeds directly to PR creation.
3. **Given** validation fails after max_attempts, **When** the workflow continues, **Then** the PR is created as a draft and the validation failure is recorded.
4. **Given** dry_run=True, **When** the fly workflow executes, **Then** all stages are planned and logged but no branches, commits, or PRs are created.

---

### User Story 2 - Execute Refuel Workflow for Batch Issue Processing (Priority: P1)

A developer wants to process multiple tech-debt issues in a single workflow run. They configure the refuel workflow with a label filter and limit, and it processes each issue by creating a branch, running fixes, validating, and creating individual PRs.

**Why this priority**: The refuel workflow demonstrates the DSL's ability to handle iteration over collections and sub-workflow composition.

**Independent Test**: Can be fully tested by providing mock GitHub issues and verifying the workflow creates the expected branches, invokes sub-workflows for each issue, and aggregates results correctly.

**Acceptance Scenarios**:

1. **Given** 3 issues matching the label filter, **When** the refuel workflow executes, **Then** each issue is processed via the process_single_issue sub-workflow and results are aggregated.
2. **Given** dry_run=True, **When** the refuel workflow executes, **Then** issues are listed but no branches, commits, or PRs are created.
3. **Given** one issue fails during processing, **When** the workflow continues, **Then** remaining issues are still processed and the final result reflects the failure count.

---

### User Story 3 - Reuse Workflow Fragments Across Main Workflows (Priority: P1)

A workflow author wants to leverage common patterns (validation loops, commit/push, PR creation) without duplicating code. The DSL provides reusable fragments that can be invoked as sub-workflows.

**Why this priority**: Fragment reuse is essential for maintainability and demonstrates the DSL's sub-workflow composition capability.

**Independent Test**: Can be fully tested by invoking each fragment directly as a sub-workflow and verifying it produces the expected outputs and step results.

**Acceptance Scenarios**:

1. **Given** the validate_and_fix fragment with max_attempts=3, **When** validation fails twice then succeeds, **Then** the fragment runs the fix agent twice and returns a successful validation result.
2. **Given** the commit_and_push fragment with a diff, **When** executed, **Then** it generates a commit message, commits, and pushes.
3. **Given** the create_pr_with_summary fragment with title and context, **When** executed, **Then** it generates a PR body and creates the PR.

---

### User Story 4 - Execute Standalone Review Workflow (Priority: P2)

A developer wants to run code review on their current changes or an existing PR without running the full fly workflow. The review workflow provides this focused capability.

**Why this priority**: The standalone review workflow enables incremental adoption and demonstrates conditional step execution.

**Independent Test**: Can be fully tested by executing the review workflow with and without a PR number and verifying the correct diff is gathered and review results are returned.

**Acceptance Scenarios**:

1. **Given** a PR number, **When** the review workflow executes, **Then** it fetches the PR diff from GitHub and runs the review agent.
2. **Given** no PR number and base_branch="main", **When** the review workflow executes, **Then** it uses git diff against the base branch.
3. **Given** include_coderabbit=True and CodeRabbit is configured, **When** the review workflow executes, **Then** it runs both agent review and CodeRabbit and merges results.

---

### User Story 5 - Execute Validate and Quick-Fix Workflows (Priority: P2)

A developer wants to run validation with optional fixes, or quickly fix a single issue. The standalone validate and quick_fix workflows provide these targeted capabilities.

**Why this priority**: These workflows demonstrate focused automation and sub-workflow reuse.

**Independent Test**: Can be fully tested by executing each workflow and verifying the expected step sequence and results.

**Acceptance Scenarios**:

1. **Given** fix=True, **When** the validate workflow executes, **Then** it invokes the validate_and_fix fragment with the configured max_attempts.
2. **Given** fix=False, **When** the validate workflow executes, **Then** it runs validation once without the fix loop.
3. **Given** an issue_number, **When** the quick_fix workflow executes, **Then** it fetches the issue and invokes process_single_issue to create a fix PR.

---

### Edge Cases

- When branch creation fails due to name conflict, the workflow fails with a clear error indicating the branch already exists.
- When the fix agent produces no changes after max_attempts, the workflow marks validation as failed and continues (PR created as draft if applicable).
- When GitHub API returns rate limit errors, the step fails with a clear error and the workflow stops.
- When a sub-workflow fails, the parent workflow fails and reports the sub-workflow's error in its result.
- When no issues match the label filter in refuel, the workflow returns success with issues_found=0.
- When notification sending fails, the workflow logs a warning but does not fail the overall workflow.
- When CodeRabbit is unavailable, the review step skips CodeRabbit and returns only the agent review.

## Requirements *(mandatory)*

### Functional Requirements

#### Workflow Fragment Implementation

- **FR-001**: System MUST implement the `validate_and_fix` fragment as a DSL workflow with inputs: stages (list), max_attempts (int), accepting a fixer agent for fix steps.
- **FR-002**: The `validate_and_fix` fragment MUST execute validation, check results, and if failed with attempts remaining, build fix context, invoke the fixer agent, and retry validation.
- **FR-003**: The `validate_and_fix` fragment MUST return the final validation result, indicating success or failure with error details.
- **FR-004**: System MUST implement the `commit_and_push` fragment as a DSL workflow with inputs: diff (optional str), scope (optional str).
- **FR-005**: The `commit_and_push` fragment MUST generate a commit message using a generator agent, execute git commit, and execute git push.
- **FR-006**: System MUST implement the `create_pr_with_summary` fragment as a DSL workflow with inputs: title (str), base_branch (str), draft (bool), context (dict).
- **FR-007**: The `create_pr_with_summary` fragment MUST generate a PR body using a generator agent and create the PR via GitHub runner.

#### Fly Workflow Implementation

- **FR-008**: System MUST implement the `fly` workflow as a DSL workflow with inputs: branch_name (str), task_file (Path, optional), skip_review (bool), skip_pr (bool), draft_pr (bool), base_branch (str), dry_run (bool).
- **FR-008a**: When dry_run=True, the fly workflow MUST log planned operations for each stage without executing branches, commits, agent invocations, or PRs.
- **FR-009**: The fly workflow MUST execute the INIT stage: create or checkout branch, build implementation context from task file.
- **FR-010**: The fly workflow MUST execute the IMPLEMENTATION stage: invoke the implementer agent with the prepared context.
- **FR-011**: The fly workflow MUST execute the VALIDATION stage: invoke the validate_and_fix sub-workflow with configured max_attempts.
- **FR-012**: The fly workflow MUST execute the COMMIT stage: invoke the commit_and_push sub-workflow with scope extracted from branch name.
- **FR-013**: The fly workflow MUST conditionally execute the CODE_REVIEW stage when skip_review=False: build review context, invoke reviewer agent, optionally run CodeRabbit.
- **FR-014**: The fly workflow MUST conditionally execute the PR_CREATION stage when skip_pr=False: invoke create_pr_with_summary sub-workflow.
- **FR-015**: The fly workflow MUST return a FlyResult containing success status, branch name, PR URL, implementation result, validation result, and review result.
- **FR-016**: The fly workflow MUST emit progress events for each stage transition compatible with TUI consumption.

#### Refuel Workflow Implementation

- **FR-017**: System MUST implement the `refuel` workflow as a DSL workflow with inputs: label (str), limit (int), parallel (bool), dry_run (bool).
- **FR-018**: The refuel workflow MUST fetch issues from GitHub matching the label filter, limited to the specified count.
- **FR-019**: The refuel workflow MUST support dry_run mode that lists issues without processing them.
- **FR-020**: The refuel workflow MUST iterate over fetched issues and invoke the process_single_issue sub-workflow for each.
- **FR-021**: The refuel workflow MUST handle sub-workflow failures gracefully, recording failed status for that issue and continuing with remaining issues.
- **FR-022**: The refuel workflow MUST return to main branch after processing all issues.
- **FR-023**: The refuel workflow MUST aggregate results and return a RefuelResult with success status, issue counts, and per-issue results.

#### Process Single Issue Sub-Workflow

- **FR-024**: System MUST implement the `process_single_issue` workflow as a DSL workflow with input: issue (GitHubIssue).
- **FR-025**: The process_single_issue workflow MUST create an issue-specific branch following the pattern from RefuelConfig.branch_prefix.
- **FR-026**: The process_single_issue workflow MUST build issue context and invoke the issue fixer agent.
- **FR-027**: The process_single_issue workflow MUST invoke validate_and_fix and commit_and_push sub-workflows.
- **FR-028**: The process_single_issue workflow MUST invoke create_pr_with_summary to create a PR linking to the issue.
- **FR-029**: The process_single_issue workflow MUST return an IssueProcessingResult with status, branch, and PR URL.

#### Review Workflow Implementation

- **FR-030**: System MUST update the existing `review` workflow YAML to complete review orchestration with inputs: pr_number (int, optional), base_branch (str), include_coderabbit (bool).
- **FR-031**: The review workflow MUST gather diff from either PR (if pr_number provided) or git diff against base_branch.
- **FR-032**: The review workflow MUST build review context and invoke the reviewer agent.
- **FR-033**: The review workflow MUST conditionally run CodeRabbit when include_coderabbit=True and CodeRabbit is configured.
- **FR-034**: The review workflow MUST merge review results from agent and CodeRabbit (if applicable) and return a ReviewResult.

#### Validate Workflow Implementation

- **FR-035**: System MUST update the existing `validate` workflow YAML with inputs: fix (bool), max_attempts (int).
- **FR-036**: When fix=True, the validate workflow MUST invoke the validate_and_fix sub-workflow.
- **FR-037**: When fix=False, the validate workflow MUST run validation once without the fix loop.

#### Quick-Fix Workflow Implementation

- **FR-038**: System MUST update the existing `quick_fix` workflow YAML to complete single-issue flow with input: issue_number (int).
- **FR-039**: The quick_fix workflow MUST fetch the issue from GitHub and invoke process_single_issue.

#### Cross-Cutting Requirements

- **FR-040**: All workflows MUST emit progress events suitable for TUI display at each stage/step transition.
- **FR-041**: All workflows MUST support checkpointing for resumability at key stages.
- **FR-042**: All workflows MUST include comprehensive docstrings describing purpose, inputs, outputs, and step sequence.
- **FR-043**: All workflows MUST follow the Python-orchestrated pattern from Spec 20, using agents for judgment tasks and Python for deterministic operations.
- **FR-044**: All workflows MUST use existing interface types from Specs 8-10 (FlyInputs, FlyResult, RefuelInputs, RefuelResult, ValidationResult, etc.).
- **FR-045**: All step names MUST be unique within each workflow execution.
- **FR-046**: All workflows MUST handle errors gracefully, recording failures in results without crashing the entire workflow.
- **FR-047**: Workflow fragments MUST be overridable following the precedence rules from Spec 25 (project > user > built-in).
- **FR-048**: All workflows MUST receive credentials via MaverickConfig injection; credentials MUST NOT appear in step results, progress events, or logs.

### Key Entities

- **Workflow Fragment**: A reusable sub-workflow implementing a common pattern (validate_and_fix, commit_and_push, create_pr_with_summary). Invoked by main workflows via sub_workflow steps.
- **Main Workflow**: A top-level workflow (fly, refuel, review, validate, quick_fix) that orchestrates stages using the DSL and composes fragments.
- **Step Result**: Per-step execution record containing success/failure, output, duration, and error details.
- **Workflow Result**: Per-workflow execution record containing overall success, step results, total duration, and final output (FlyResult, RefuelResult, etc.).
- **Progress Event**: Typed event emitted during workflow execution for TUI consumption (StageStarted, StageCompleted, etc.).
- **Context Builder**: Callable that constructs context for agent/generate steps from workflow inputs and prior step results.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All five main workflows (fly, refuel, review, validate, quick_fix) can be listed via CLI and executed with documented inputs.
- **SC-002**: All three workflow fragments (validate_and_fix, commit_and_push, create_pr_with_summary) can be invoked as sub-workflows and produce correct outputs.
- **SC-003**: Fly workflow completes a full feature implementation cycle (branch, implement, validate, commit, review, PR) using the DSL.
- **SC-004**: Refuel workflow processes multiple issues in sequence, creating individual PRs for each, using the DSL.
- **SC-005**: Workflows emit progress events at each stage transition, observable in TUI or via event subscription.
- **SC-006**: Workflows can be resumed from checkpoints after interruption, continuing from the last checkpointed stage.
- **SC-007**: Token usage is reduced by 40-60% compared to non-orchestrated implementations by using Python for deterministic operations. Measurement: Compare Claude API token counts for equivalent fly workflow execution between DSL-based (this spec) and pure-agent approaches (Spec 9 baseline). Measure across 3 representative task files of varying complexity.
- **SC-008**: 100% line coverage (measured by pytest-cov) for all Python actions in `src/maverick/library/actions/` and context builders in `src/maverick/dsl/context_builders.py`. YAML workflow definitions validated via integration tests covering all step paths.
- **SC-009**: All workflows follow the interface contracts from Specs 8-10 (return types, input validation, progress events).
- **SC-010**: Workflow fragments are overridable via project workflows directory, enabling customization without modifying built-ins.

## Assumptions

- All runner components (GitRunner, ValidationRunner, GithubRunner, CodeRabbitRunner) are implemented and injectable per Spec 20.
- All agent types (ImplementerAgent, CodeReviewerAgent, IssueFixerAgent, fixer agent) are implemented per Specs 3-4.
- All generator agents (commit_message_generator, pr_description_generator) are implemented per Spec 19.
- The workflow DSL (Specs 22-24) is fully implemented, including step types, flow control, and checkpointing.
- The workflow library infrastructure (Spec 25) is implemented, including discovery, precedence, and registration.
- Configuration types (FlyConfig, RefuelConfig, etc.) are integrated into MaverickConfig.
- Context builders (build_implementation_context, build_review_context, build_issue_context, build_fix_context) are implemented as pure Python functions.
- Helper functions (extract_scope, merge_reviews, send_notification) are implemented.

## Dependencies

This specification depends on and implements interfaces from:

| Spec | Title | Relationship |
|------|-------|--------------|
| 008 | Validation Workflow | Implements ValidationWorkflow interface using DSL |
| 009 | Fly Workflow Interface | Implements FlyWorkflow.execute() using DSL |
| 010 | Refuel Workflow Interface | Implements RefuelWorkflow.execute() using DSL |
| 020 | Workflow Refactor | Follows Python-orchestrated patterns |
| 022 | Core Workflow DSL | Uses @workflow, step(), step types |
| 023 | DSL Flow Control | Uses conditionals, retry, loops, checkpoints |
| 024 | Workflow Serialization | Workflows are serializable to YAML |
| 025 | Built-in Workflow Library | Workflows are discoverable and overridable |

## Out of Scope

The following are explicitly excluded from this specification:

- **New DSL step types or flow control primitives**: This spec uses existing DSL features from Specs 22-24; extensions belong in separate specs.
- **New agent types**: All agents (Implementer, CodeReviewer, IssueFixer, generators) are assumed implemented per Specs 3-4 and 19.
- **Workflow marketplace or sharing**: Distribution mechanisms for community workflows are a future concern.
- **GUI/visual workflow editor**: This spec focuses on CLI/TUI execution; visual authoring tools are out of scope.
- **Custom workflow authoring documentation**: Focus is on implementing built-in workflows; user documentation for custom workflows belongs elsewhere.
