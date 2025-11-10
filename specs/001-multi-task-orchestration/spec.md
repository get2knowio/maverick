# Feature Specification: Multi-Task Orchestration Workflow

**Feature Branch**: `001-multi-task-orchestration`  
**Created**: 2025-11-08  
**Status**: Draft  
**Input**: User description: "Orchestrate multiple task files with optional interactive pauses in Temporal"

## Clarifications

### Session 2025-11-08

- Q: Should the workflow stop immediately on ANY task failure (including validation failures like phase discovery) or only on activity/infrastructure failures? → A: Stop immediately on ANY task failure regardless of failure type (tasks and files are order dependent)
- Q: When interactive mode is enabled, should the workflow pause after "major phases" only, or after every phase regardless of task structure? → A: Pause after EVERY phase when interactive=true (consistent behavior for all phase counts)
- Q: How should completed task results be stored during workflow execution - in Temporal workflow state or external storage? → A: Store all task results in Temporal workflow state (simple, deterministic, no external dependencies)
- Q: What logging/observability strategy should the workflow use for tracking execution of multi-task batches? → A: Log only at task/phase boundaries and failure points (balanced observability and performance)
- Q: Should the orchestration workflow call existing phase workflows as activities, child workflows, or create new duplicate implementations? → A: Call existing phase workflows directly as child workflows (no activities, pure workflow composition)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Automated Batch Task Processing (Priority: P1)

As a developer, I want to submit a list of task files and have the system automatically process all of them sequentially, so that I can implement multiple features without manual intervention between tasks.

**Why this priority**: This is the core value proposition - automating the end-to-end implementation of multiple tasks. Without this, the feature provides no value.

**Independent Test**: Can be fully tested by submitting a list of 2-3 task files, waiting for completion, and verifying that all task files were processed through all phases (init, implement, review/fix, PR/CI/merge) and that results are returned for each task.

**Acceptance Scenarios**:

1. **Given** a list of 3 valid task files, **When** I start the workflow with interactive=false, **Then** all 3 tasks are processed sequentially through all phases without pausing
2. **Given** task file A completes successfully and task file B is next in queue, **When** task A finishes, **Then** task B begins processing immediately
3. **Given** all tasks in the list have been processed, **When** the workflow completes, **Then** I receive a summary showing the status (success/failure) of each task
4. **Given** a task reaches its retry limit during any phase, **When** retries are exhausted, **Then** the task is marked as failed and the workflow stops immediately, returning partial results
5. **Given** a task file list with 5 tasks where task 3 fails after retries, **When** the failure occurs, **Then** the workflow stops and returns results for tasks 1-2 (completed) and task 3 (failed), with tasks 4-5 marked as unprocessed

---

### User Story 2 - Interactive Approval Gates (Priority: P2)

As a developer, I want to pause the workflow before or after major phases and wait for my approval, so that I can review progress and make decisions before proceeding.

**Why this priority**: Adds human oversight capability for high-risk changes or learning scenarios, but the system is still valuable without it (fully automated mode).

**Independent Test**: Can be fully tested by submitting a single task file with interactive=true, verifying the workflow pauses at expected checkpoints, sending approval signals, and confirming the workflow resumes and completes.

**Acceptance Scenarios**:

1. **Given** interactive mode is enabled, **When** a task completes any phase, **Then** the workflow pauses and waits for a "continue" signal before starting the next phase
2. **Given** the workflow is paused at a checkpoint, **When** I send a "continue" signal, **Then** the workflow resumes and proceeds to the next phase
3. **Given** interactive mode is enabled with a task containing 6 custom phases, **When** each phase completes, **Then** the workflow pauses after all 6 phases (not just "major" ones)
4. **Given** a workflow is paused waiting for approval, **When** I query the workflow status, **Then** I can see which task and phase it's waiting on
5. **Given** interactive mode is enabled with 3 tasks, **When** I approve each checkpoint, **Then** all 3 tasks are processed with pauses between major phases

---

### User Story 3 - Resume After Interruption (Priority: P2)

As a developer, I want the workflow to automatically resume from where it left off after a worker restart or temporary failure, so that I don't lose progress on long-running batch operations.

**Why this priority**: Critical for production reliability and long-running workflows, but not required for initial MVP testing in development environments.

**Independent Test**: Can be fully tested by starting a workflow with 3 tasks, simulating a worker restart after task 1 completes, and verifying the workflow resumes with task 2 without re-processing task 1.

**Acceptance Scenarios**:

1. **Given** a workflow has completed tasks 1 and 2 and is processing task 3, **When** the worker restarts, **Then** the workflow resumes with task 3 without re-running tasks 1 or 2
2. **Given** a workflow is paused waiting for approval on task 2, **When** the worker restarts, **Then** the workflow remains paused at the same checkpoint
3. **Given** a task was in the middle of a review/fix iteration, **When** the worker restarts, **Then** the workflow resumes from the last completed iteration without duplicating work
4. **Given** the workflow has processed 5 tasks successfully, **When** I query workflow history, **Then** I can see the complete timeline including which steps were replayed after restarts

---

### User Story 4 - Phase Discovery and Dynamic Processing (Priority: P3)

As a developer, I want the workflow to automatically discover and process all phases defined in each task file, so that I can use tasks with varying numbers of phases without changing the orchestrator.

**Why this priority**: Adds flexibility for future use cases with custom phase structures, but standard 4-phase tasks are sufficient for MVP.

**Independent Test**: Can be fully tested by submitting task files with 2, 3, 4, and 5 phases each, and verifying that all phases in each task are processed correctly without hardcoded assumptions.

**Acceptance Scenarios**:

1. **Given** a task file with 2 phases (init, implement), **When** the workflow processes it, **Then** only those 2 phases are executed
2. **Given** a task file with 6 custom phases, **When** the workflow processes it, **Then** all 6 phases are executed in order
3. **Given** a mix of tasks with 2, 4, and 5 phases, **When** the workflow processes the list, **Then** each task executes its own phase count correctly
4. **Given** a task file's phase list is modified after workflow start but before that task begins, **When** the task is processed, **Then** the updated phase list is used

---

### Edge Cases

- What happens when a task file path is invalid or the file doesn't exist? (System logs error, marks task as failed, stops immediately and returns partial results due to order dependency)
- What happens when an empty task list is provided? (Workflow completes immediately with empty results)
- What happens when a task file is valid but contains no phases? (Task is marked as failed with descriptive error, workflow stops immediately and returns partial results)
- What happens when the workflow receives a "continue" signal while not paused? (Signal is ignored or queued for next pause, no error)
- What happens when interactive mode is enabled but no signal is received for an extended period? (Workflow remains paused indefinitely unless timeout is configured separately)
- What happens when a worker restart occurs during an activity execution? (Temporal's built-in retry logic handles activity resume; workflow state ensures idempotency)
- What happens when multiple signals are sent while paused? (Only the first valid signal resumes execution; additional signals are ignored)
- What happens when retry limit is reached during PR/CI phase and CI keeps failing? (Task marked as failed after retry limit, workflow stops immediately and returns partial results)
- What happens when two tasks in the list reference the same branch name? (Second task fails during initialization with branch conflict error, workflow stops immediately and returns partial results)
- What happens when a child workflow execution times out before exhausting retry attempts? (Timeout is treated as a failure; if retries remain, the child workflow is retried; if timeout occurs on final retry, task is marked as failed and workflow stops immediately with partial results)

## Requirements *(mandatory)*

### Functional Requirements

#### Input/Output

- **FR-001**: Workflow MUST accept an array of task file paths as input
- **FR-002**: Workflow MUST accept an interactive mode boolean flag (default: false)
- **FR-003**: Workflow MUST accept a retry limit integer (default: 3, range: 1-10)
- **FR-004**: Workflow MUST return an aggregated result containing: total tasks processed, successful tasks count, failed tasks count, and per-task results (task file path, status, completion time, failure reason if applicable)

#### Task Processing Loop

- **FR-005**: Workflow MUST process tasks sequentially in the order provided in the input array
- **FR-006**: For each task, workflow MUST execute phases by calling existing phase workflows as child workflows (pure workflow composition, no activity layer)
- **FR-007**: Workflow MUST invoke child workflows using `workflow.execute_child_workflow()` with appropriate phase workflow names and parameters; MUST specify `result_type` parameter for child workflow calls returning dataclasses to ensure proper deserialization (per Constitution IV Type Safety Requirements); MUST configure execution timeout (e.g., 30 minutes per phase workflow) and handle timeout errors explicitly
- **FR-008**: Workflow MUST pass the task file path and relevant phase-specific parameters to each child workflow
- **FR-009**: Workflow MUST record the completion status (success/failure) of each phase for each task based on child workflow results
- **FR-010**: Workflow MUST continue to the next task after the current task completes successfully; if a task fails after retry limit, workflow MUST stop immediately and return partial results

#### Interactive Mode Behavior

- **FR-011**: When interactive mode is enabled, workflow MUST pause after EVERY phase completes and before the next phase begins (applies uniformly to all discovered phases regardless of task structure)
- **FR-012**: Workflow MUST define and listen for a signal named `continue_to_next_phase` to resume from a pause
- **FR-013**: When paused, workflow MUST expose the current task index, task file path, and last completed phase in queryable state
- **FR-014**: Workflow MUST support an optional signal named `skip_current_task` to mark the current task as skipped and proceed to the next task
- **FR-015**: When interactive mode is disabled, workflow MUST proceed through all phases without pausing

#### Progress Tracking and Resumability

- **FR-016**: Workflow MUST maintain a progress record showing: which tasks have been completed, which phases of the current task have been completed, current task index
- **FR-017**: Workflow MUST use Temporal workflow state to persist progress AND all completed task results, ensuring deterministic replay after worker restarts with full result history
- **FR-018**: Workflow MUST NOT re-execute already-completed tasks or phases when replayed after a restart
- **FR-019**: Workflow MUST maintain a list of completed task indices and their complete TaskResult objects in workflow state (no external storage dependencies)

#### Retry and Limit Handling

- **FR-020**: Each child workflow call MUST be configured with the workflow-level retry limit using Temporal's child workflow retry policy with exponential backoff (starting at 1 second, max interval 60 seconds); non-retryable errors (e.g., validation failures) MUST fail immediately without retry
- **FR-021**: When a child workflow exhausts its retry limit, workflow MUST mark that phase as failed
- **FR-022**: When a phase fails after retry limit is reached, workflow MUST mark the entire task as failed
- **FR-023**: Workflow MUST record the specific phase and retry count where failure occurred
- **FR-024**: Workflow MUST NOT retry an entire task; only individual child workflow calls are retried per Temporal's retry policy
- **FR-025**: Phase workflows (called as children) handle internal retry logic independently; orchestration workflow respects child workflow final outcomes

#### Phase Discovery

- **FR-026**: Workflow MUST call the task parsing activity to discover the list of phases defined in each task file (activity is appropriate here as this is a simple, synchronous parse operation)
- **FR-027**: Workflow MUST support processing tasks with a variable number of phases (minimum 1, no maximum)
- **FR-028**: Workflow MUST execute discovered phases by invoking the corresponding child workflows in the order they appear in the task file
- **FR-029**: If phase discovery fails or returns an empty list, workflow MUST mark the task as failed and stop immediately, returning partial results (consistent with fail-fast behavior for order-dependent tasks)

#### Observability

- **FR-035**: Workflow MUST log using `workflow.logger` at the following checkpoints: workflow start (with task count), task start (with task index and file path), phase start (with phase name), phase completion (with status and duration), task completion (with overall status), workflow completion (with summary statistics)
- **FR-036**: Workflow MUST log all failure events including: task failure reason, phase where failure occurred, retry count exhausted, early termination indicator
- **FR-037**: All log entries MUST include workflow context: workflow_id, run_id, current_task_index (when applicable)
- **FR-038**: Workflow MUST NOT log activity-internal operations; detailed operation logs are the responsibility of individual activities

#### Result Aggregation

- **FR-039**: Workflow MUST collect results from each task into a final aggregated result structure stored entirely in Temporal workflow state
- **FR-040**: Per-task results MUST include: task file path, overall status (success/failed/skipped/unprocessed), list of phase results (phase name, status, duration), total task duration, failure reason (if failed)
- **FR-041**: Aggregated result MUST be returned when the workflow completes (including early termination due to failure), constructed from accumulated workflow state
- **FR-042**: Workflow MUST calculate summary statistics: total tasks, successful count, failed count, skipped count, unprocessed count, total duration
- **FR-043**: When workflow terminates early due to task failure, aggregated result MUST include a list of unprocessed task file paths and indicate early termination

### Key Entities

- **OrchestrationInput**: Represents the input to the orchestration workflow
  - Attributes: task_file_paths (array of strings), interactive_mode (boolean), retry_limit (integer)
  
- **TaskProgress**: Represents the progress state of a single task
  - Attributes: task_index (integer), task_file_path (string), current_phase (string), completed_phases (array of strings), status (pending/in_progress/completed/failed/skipped)
  
- **PhaseResult**: Represents the outcome of executing a single phase
  - Attributes: phase_name (string), status (success/failed), duration_seconds (integer), error_message (string, optional), retry_count (integer)
  
- **TaskResult**: Represents the complete outcome of processing one task
  - Attributes: task_file_path (string), overall_status (success/failed/skipped), phase_results (array of PhaseResult), total_duration_seconds (integer), failure_reason (string, optional)
  
- **OrchestrationResult**: Represents the final output of the workflow
  - Attributes: total_tasks (integer), successful_tasks (integer), failed_tasks (integer), skipped_tasks (integer), unprocessed_tasks (integer), task_results (array of TaskResult), unprocessed_task_paths (array of strings), early_termination (boolean), total_duration_seconds (integer)

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Workflow successfully processes a batch of 10 task files end-to-end without human intervention when interactive mode is disabled
- **SC-002**: Workflow correctly pauses at each phase boundary and resumes upon receiving continue signals when interactive mode is enabled
- **SC-003**: Workflow resumes from the correct task and phase after a simulated worker restart, without re-executing completed work
- **SC-004**: When a task fails after reaching retry limit, the workflow immediately stops and returns partial results showing completed tasks, the failed task, and unprocessed tasks
- **SC-005**: Workflow completes processing of a 10-task batch in under 4 hours (assuming each task takes ~20 minutes), demonstrating acceptable throughput
- **SC-006**: Workflow accurately reports success/failure statistics, including unprocessed task count when early termination occurs
- **SC-007**: Workflow handles task files with varying phase counts (2 to 6 phases) without errors or hardcoded phase assumptions
- **SC-008**: When queried during execution, workflow state correctly reflects current task index, current phase, and list of completed tasks
- **SC-009**: 95% of retry-eligible failures (transient errors) are resolved within the configured retry limit without manual intervention
- **SC-010**: Workflow produces complete audit trail showing which tasks completed, which failed, at which phase failures occurred, and total processing time per task

## Assumptions

1. **Task file format**: Task files follow a standardized markdown format with a parseable phase list (specific format defined by task initialization spec)
2. **Workflow availability**: All referenced phase workflows are already implemented and registered with the Temporal worker as callable workflows (not activities); the orchestration workflow calls them as child workflows. Currently, all phases are handled by the `AutomatePhaseTasksWorkflow` which accepts phase-specific parameters and delegates to appropriate activities internally.
3. **Temporal infrastructure**: A Temporal cluster is running and accessible, with workers registered for the orchestration task queue; Temporal event history can accommodate all task results and child workflow executions without hitting size limits (workflow state storage is sufficient)
4. **File system access**: Activities have access to read task files from the file system or repository
5. **Sequential processing**: Tasks are processed one at a time to avoid branch conflicts and resource contention (parallel processing is out of scope)
6. **Signal delivery**: Temporal signals are delivered reliably and workflow can block waiting for signals indefinitely
7. **Deterministic workflow**: All non-deterministic operations (file I/O, network calls, CLI commands) are delegated to child workflows and their internal activities
8. **Retry policy**: Child workflow retry policy is configured in the orchestration workflow's child workflow invocation parameters with exponential backoff
9. **Timeout configuration**: Child workflows have appropriate timeouts configured (e.g., 30 minutes for implementation phase workflow)
10. **Error propagation**: Child workflows throw exceptions for failures, which are caught and handled by the orchestration workflow logic
11. **Phase naming**: Phases in task files use consistent naming (e.g., "initialize", "implement", "review_fix", "pr_ci_merge") or a discoverable format
12. **Idempotency**: All activities are idempotent and safe to retry without side effects

## Dependencies

1. **Existing Temporal workflows**: This orchestration workflow depends on the lower-level phase workflows being implemented and callable as child workflows:
   - Task initialization workflow
   - AI implementation workflow
   - Review and fix loop workflow
   - PR/CI/merge workflow (with internal CI retry logic)
   - Each phase workflow MUST be registered with the Temporal worker and accessible via workflow name
   
2. **Task file parsing**: Requires an activity that can parse task markdown files and extract phase definitions (simple synchronous operation, not a workflow)

3. **Temporal SDK**: Depends on Temporal Python SDK for workflow execution, signals, queries, and activity orchestration

4. **Workflow state management**: Relies on Temporal's built-in state persistence and replay mechanisms for determinism

## Out of Scope

1. **Parallel task processing**: Tasks are processed sequentially only; parallel execution of multiple tasks is not supported
2. **Dynamic task addition**: The task list is fixed at workflow start; adding tasks to a running workflow is not supported
3. **Phase-level retry configuration**: Retry limits are set at the workflow level and apply uniformly to all activities; per-phase retry limits are not supported
4. **Custom signal names**: Signal names are fixed (`continue_to_next_phase`, `skip_current_task`); user-defined signal names are not supported
5. **Pause timeout enforcement**: While workflows can pause indefinitely, automatic timeout handling for unresponsive users is out of scope
6. **Rollback on failure**: If a task fails, there is no automatic rollback of previous tasks; manual cleanup is required
7. **Conditional phase execution**: All discovered phases are executed; conditional skipping of phases based on task content is not supported
8. **Real-time progress notifications**: External notification systems (email, Slack, webhooks) are not integrated; users must query workflow state
9. **Task prioritization**: Tasks are processed in array order only; dynamic re-prioritization is not supported
10. **Multi-repository support**: All tasks are assumed to operate on the same repository; cross-repository orchestration is not supported

## Notes

### Failure Handling Strategy

When a task fails after exhausting all retry attempts, the workflow will immediately stop processing and return partial results. This fail-fast approach ensures that:
- Issues are addressed promptly before continuing to subsequent tasks
- Resources are not wasted on processing tasks that may be affected by the same underlying problem
- Users can fix the root cause and restart the workflow from the beginning with corrected configurations
- The workflow maintains a clear "all or nothing" semantic for batch operations

The returned partial result will include:
- All successfully completed tasks up to the point of failure
- The failed task with detailed error information (phase, retry count, error message)
- List of unprocessed tasks (not yet attempted)
- A clear indication that the workflow terminated early due to failure

This behavior applies regardless of interactive mode setting.

### Signal Design

The workflow will use Temporal signals for interactive control:
- `continue_to_next_phase`: Resumes workflow from a pause point, proceeding to the next phase or task
- `skip_current_task`: Marks the current task as skipped and moves to the next task in the list

Signals are idempotent and can be sent multiple times without adverse effects (only the first signal while paused takes effect).

### Progress Query

The workflow will expose a query named `get_progress` that returns:
```
{
  "current_task_index": 2,
  "total_tasks": 5,
  "current_task_file": "tasks/feature-003.md",
  "current_phase": "review_fix",
  "completed_tasks": [0, 1],
  "is_paused": true,
  "waiting_for": "continue_to_next_phase"
}
```

This allows external systems or CLIs to monitor workflow progress
