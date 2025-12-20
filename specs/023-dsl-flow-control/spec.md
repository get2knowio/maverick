# Feature Specification: Workflow DSL Flow Control

**Feature Branch**: `023-dsl-flow-control`  
**Created**: 2025-12-14  
**Status**: Draft  
**Input**: User description: "this is spec 023: Create a spec for flow control constructs in the Maverick workflow DSL."

## Clarifications

### Session 2025-12-20

- Q: When a `.when(predicate)` predicate raises an exception or returns a non-boolean value, how should the system behave? → A: Treat exceptions as false (skip step) and log a warning; fail on non-boolean returns.
- Q: When a branch predicate references a prior step result that doesn't exist (e.g., because that step was skipped), how should the system behave? → A: Treat missing step results as `None`; predicates can handle defensively.
- Q: When a workflow resumes from a checkpoint but required inputs have changed since the checkpoint was saved, how should the system behave? → A: Detect input changes and fail with a clear mismatch error.
- Q: When a rollback action fails during the rollback phase, should the system continue attempting remaining rollbacks or stop immediately? → A: Continue all rollbacks; collect and report all errors at the end.
- Q: When a `.parallel([...])` construct contains duplicate step names, when should this be detected and how should it be handled? → A: Fail immediately when the parallel step is yielded (before execution).

## User Scenarios & Testing *(mandatory)*

<!--
  IMPORTANT: User stories should be PRIORITIZED as user journeys ordered by importance.
  Each user story/journey must be INDEPENDENTLY TESTABLE - meaning if you implement just ONE of them,
  you should still have a viable MVP (Minimum Viable Product) that delivers value.
  
  Assign priorities (P1, P2, P3, etc.) to each story, where P1 is the most critical.
  Think of each story as a standalone slice of functionality that can be:
  - Developed independently
  - Tested independently
  - Deployed independently
  - Demonstrated to users independently
-->

### User Story 1 - Control flow with conditions and branches (Priority: P1)

As a workflow author, I can conditionally execute steps and route between alternative steps so I can model real-world decisions (skip, choose, fallback) without leaving the workflow DSL.

**Why this priority**: Conditions and branching are the most common control-flow needs and enable practical workflows without complex workarounds.

**Independent Test**: Can be fully tested by defining a workflow that conditionally runs one step, branches between two steps, and verifies only the expected steps executed and the outputs match the chosen path.

**Acceptance Scenarios**:

1. **Given** a workflow using standard Python `if` statements around yielded steps, **When** the condition is false, **Then** the step is not executed and no step result is recorded for it.
2. **Given** a step decorated with `.when(predicate)`, **When** the predicate evaluates to false at runtime, **Then** the step is skipped, recorded as skipped, and workflow execution continues.
3. **Given** a branch step with multiple (predicate, step) options, **When** more than one predicate is true, **Then** the first matching option in declaration order is selected and only that option’s step is executed.

---

### User Story 2 - Reliability controls: retry, skip, fallback, rollback (Priority: P2)

As a workflow author, I can retry steps, handle step failures with fallbacks, skip optional failures, and register rollbacks so I can build workflows that complete safely and predictably even when operations are flaky.

**Why this priority**: Reliability patterns reduce workflow brittleness and prevent partial side effects when failures occur.

**Independent Test**: Can be fully tested by running a workflow with a flaky step retried to success, an optional step skipped on error, and a rollback registered and invoked after a later failure.

**Acceptance Scenarios**:

1. **Given** a step configured with `.retry(max_attempts=N)`, **When** the step fails fewer than N times and then succeeds, **Then** the step eventually succeeds and the workflow continues.
2. **Given** a step configured with `.on_error(handler=...)`, **When** the step fails, **Then** the handler selects a fallback step and the fallback’s outcome determines whether the workflow continues.
3. **Given** a step configured with `.with_rollback(rollback=...)`, **When** the workflow later fails after that step succeeded, **Then** rollback actions run in reverse execution order on a best-effort basis.

---

### User Story 3 - Advanced control flow: loops, parallel interface, checkpoints/resume (Priority: P3)

As a workflow author, I can iterate over collections, express a parallel-review interface, and checkpoint/resume workflows so I can process large sets of items, prepare for concurrency, and recover from interruptions.

**Why this priority**: These constructs enable scalability and long-running workflows while keeping authoring ergonomic.

**Independent Test**: Can be fully tested by yielding multiple steps in a Python loop, executing a parallel interface step that returns multiple outputs, and resuming a workflow from a saved checkpoint.

**Acceptance Scenarios**:

1. **Given** a workflow that yields steps in a Python `for` loop, **When** executed on a list of inputs, **Then** it executes one step per item and records a step result per executed step.
2. **Given** a workflow that yields a `.parallel([...])` construct, **When** it completes, **Then** it returns results in the same order as provided to the parallel construct and exposes per-child step outcomes.
3. **Given** a workflow with a checkpoint-marked step and a configured checkpoint store, **When** the workflow is resumed from the latest checkpoint, **Then** it continues execution after that checkpoint using restored context/results.

---

### Edge Cases

- A `.when(...)` predicate raises an exception → step is skipped (treated as false) and a warning is logged.
- A `.when(...)` predicate returns a non-boolean value → workflow fails with a type error.
- A branch step has no matching branch option.
- A branch predicate depends on a prior step result that does not exist (e.g., due to conditional skip) → missing results are treated as `None`; predicates should handle defensively.
- A retry-enabled step exhausts all attempts without succeeding.
- A rollback action fails while rolling back after workflow failure → continue executing remaining rollbacks; collect and report all rollback errors at the end.
- A workflow resumes from a checkpoint but required inputs have changed since the checkpoint was saved → resume fails with a clear input mismatch error.
- A `.parallel([...])` construct contains duplicate step names → fail immediately when the parallel step is yielded (before any child step executes).

## Requirements *(mandatory)*

### Functional Requirements

#### Natural Python control flow

- **FR-001**: Workflow definitions MUST allow authors to use standard Python control flow (`if`, `for`, `try/except`, early `return`) around yielded steps.
- **FR-002**: The workflow execution engine MUST support yielding an arbitrary number of steps (including in loops) and MUST preserve execution order based on yield order.

#### Conditional step execution

- **FR-003**: The step DSL MUST support conditional execution via `.when(predicate)` on any step definition.
- **FR-004**: When a `.when(predicate)` condition evaluates to false, the step MUST be treated as skipped: the underlying operation MUST NOT run, and the workflow MUST continue to the next yielded step.
- **FR-005**: When a step is skipped via `.when(...)`, the workflow MUST still record a step result with `success=true` and a standardized skipped marker output so skipped steps can be distinguished from executed steps.
- **FR-005a**: When a `.when(predicate)` raises an exception, the step MUST be treated as skipped (predicate evaluated to false), a warning MUST be logged, and execution MUST continue.
- **FR-005b**: When a `.when(predicate)` returns a non-boolean value, the workflow MUST fail immediately with a type error indicating the predicate must return a boolean.

#### Branching

- **FR-006**: The step DSL MUST support branching via `.branch((predicate, step), ...)` to choose exactly one step to execute from a list of options.
- **FR-007**: Branching MUST evaluate options in the declared order and select the first option whose predicate evaluates to true.
- **FR-008**: If no branch predicate evaluates to true, the branch step MUST fail the workflow with a clear error.
- **FR-009**: A branch step MUST return an output that includes (at minimum) the selected option identity and the selected step's output.
- **FR-009a**: When a predicate (in `.when(...)` or `.branch(...)`) accesses a step result that does not exist (e.g., the step was skipped or never executed), the result lookup MUST return `None` rather than raising an error; predicates are responsible for handling missing results defensively.

#### Retry and loops

- **FR-010**: The step DSL MUST support retrying any step via `.retry(max_attempts, backoff=None)` (or equivalent parameters) that re-attempts the step on failure up to the configured maximum attempts.
- **FR-011**: Retry MUST apply to step failures (unsuccessful step results); if all attempts fail, the final outcome MUST be a failed step result.
- **FR-012**: Workflows that yield steps in loops MUST enforce unique step names per execution; duplicate step names yielded at runtime MUST fail with a clear error message.

#### Parallel interface (future-facing)

- **FR-013**: The step DSL MUST expose a `.parallel(steps)` interface that accepts a collection of step definitions and returns a composite output containing per-step outcomes in a stable, input-order-preserving structure.
- **FR-014**: The initial release MAY execute `.parallel(...)` steps sequentially, but the interface and results MUST be compatible with future concurrent execution without changing user-facing behavior.
- **FR-014a**: When a `.parallel([...])` construct is yielded, the execution engine MUST validate that all child step names are unique and MUST fail immediately with a clear error if duplicates are detected (before any child step executes).

#### Step-level error handling

- **FR-015**: The step DSL MUST support step-level error handling via `.on_error(handler)` that runs when the step fails.
- **FR-016**: A step-level error handler MUST receive the workflow context and the failing step’s error information and MUST be able to select a fallback step to run; if the fallback succeeds, the original step MUST be treated as successful and return the fallback output; if the fallback fails, the workflow MUST fail.
- **FR-017**: The step DSL MUST support `.skip_on_error()` (or equivalent) to convert a step failure into a skipped step result and continue execution.

#### Rollback support

- **FR-018**: The step DSL MUST support `.with_rollback(rollback)` to register a rollback action for a step that is eligible to run if the workflow later fails after the step has successfully completed.
- **FR-019**: When a workflow run ends unsuccessfully, the execution engine MUST attempt rollbacks for all eligible steps in reverse execution order (best-effort), and the workflow result MUST surface rollback failures in its error reporting.
- **FR-019a**: If a rollback action fails, the execution engine MUST continue attempting remaining rollbacks rather than stopping; all rollback errors MUST be collected and included in the final workflow result.

#### Early exit and failure exit

- **FR-020**: A workflow function MAY return early to stop execution; early return MUST result in a completed workflow result without executing further steps.
- **FR-021**: The workflow DSL MUST provide a `WorkflowError` mechanism that workflow code can raise to explicitly exit with failure and a human-readable error reason.

#### Checkpointing and resumability

- **FR-022**: The step DSL MUST support marking steps as checkpoints via `.checkpoint()` to indicate resumable points in workflow execution.
- **FR-023**: The workflow runtime MUST support resuming execution from a checkpoint via `Workflow.resume(checkpoint_id)` (or equivalent interface), continuing after the checkpoint and restoring previously recorded results.
- **FR-024**: The system MUST provide a `CheckpointStore` interface with operations to save, load, and clear checkpoint data for a workflow run.
- **FR-025**: The default checkpoint store MUST persist checkpoints as JSON files under `.maverick/checkpoints/` (or equivalent documented path) so resumability works without additional configuration.
- **FR-025a**: Checkpoint data MUST include a hash of the workflow inputs at the time of checkpointing.
- **FR-025b**: When resuming from a checkpoint, the runtime MUST compare the current workflow inputs against the stored input hash and MUST fail with a clear mismatch error if they differ.

### Assumptions

- This spec extends the core workflow DSL defined in `specs/022-workflow-dsl/spec.md` and focuses on flow-control conveniences and resumability.
- Step failures are represented as unsuccessful step results; workflow-level `try/except` is intended for errors raised by workflow code (including `WorkflowError`), not for ordinary step failures.

### Key Entities *(include if feature involves data)*

- **Conditional Step**: A step definition that is only executed when a runtime predicate evaluates to true; otherwise it is skipped.
- **Skip Result**: A standardized marker output indicating a step was skipped (not executed) due to a runtime condition or skip-on-error policy.
- **Branch Step**: A step definition that selects and executes exactly one of multiple candidate steps based on runtime predicates.
- **Branch Result**: Output of a branch step, including which option was selected and the selected step’s output.
- **Retry Wrapper**: A step wrapper that re-attempts a step on failure up to a configured maximum attempts, with optional backoff between attempts.
- **Parallel Interface Step**: A step definition that accepts multiple child steps and returns a stable, ordered composite result for those child steps.
- **Parallel Result**: Output of a parallel interface step, including per-child outputs and per-child success/failure outcomes.
- **Rollback Action**: A compensating action registered for a step that may run if the workflow later fails after the step completed.
- **WorkflowError**: A structured failure signal raised by workflow code to end a workflow run with a human-readable reason.
- **Checkpoint**: A marked point in execution after which the workflow can be resumed.
- **Checkpoint Data**: Persisted data sufficient to resume a workflow, including checkpoint identifier, step name, saved inputs, and saved step results.
- **CheckpointStore**: Persistence interface for saving, loading, and clearing checkpoints for a workflow run.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A workflow author can express conditional execution, branching, and retries in a workflow without writing custom control-flow plumbing around step results.
- **SC-002**: For workflows using `.when(...)` and `.branch(...)`, execution follows declared predicate logic deterministically (same inputs/results produce the same executed step set and ordering).
- **SC-003**: For a retry-enabled step, the system attempts execution no more than the configured maximum and records a single final step result that reflects the final outcome.
- **SC-004**: A workflow with checkpointing can be resumed from the latest checkpoint and complete successfully without re-running steps prior to that checkpoint (unless explicitly requested by the author).
