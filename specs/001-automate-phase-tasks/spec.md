# Feature Specification: Temporal Phase Automation for tasks.md

**Feature Branch**: `001-automate-phase-tasks`  
**Created**: 2025-11-08  
**Status**: Draft  
**Input**: User description: "Create a spec that lets a Temporal workflow process Speckit-generated tasks.md files phase-by-phase using AI-backed activities."

## Clarifications
### Session 2025-11-08
- Q: How should the workflow behave if the current `tasks.md` diverges from the stored checkpoint hash when resuming? → A: Treat the current `tasks.md` as authoritative, refresh checkpoints, and continue automatically.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Orchestrate sequential phase runs (Priority: P1)

A workflow operator triggers the Temporal readiness workflow so that every phase in a Speckit-generated `tasks.md` executes in order, with each phase's tasks handed to an AI-powered activity that calls the `speckit.implement` command.

**Why this priority**: Enables automated progress through the plan without manual intervention; this is the core value of the feature.

**Independent Test**: Start a workflow run with a sample `tasks.md`; verify that phases 1..N execute sequentially, and each phase produces a completion report once the activity finishes.

**Acceptance Scenarios**:

1. **Given** a `tasks.md` containing at least one phase with open tasks, **When** the workflow is started, **Then** the workflow calls the phase activity with the correct phase identifier and metadata.
2. **Given** an activity completes successfully, **When** control returns to the workflow, **Then** the corresponding tasks in `tasks.md` show `- [X]` and the workflow emits a structured result for that phase.

---

### User Story 2 - Resume after a failed phase (Priority: P2)

An automation engineer needs to resume the workflow after a specific phase previously failed, ensuring completed phases are skipped and the workflow restarts at the first incomplete phase.

**Why this priority**: Supports operational resilience and reduces wasted AI usage by avoiding re-running successful work.

**Independent Test**: Induce a failure in Phase 2 while Phase 1 completes; re-run the workflow and confirm it recognizes Phase 1 as complete, restarts at Phase 2, and updates checkpoints accordingly.

**Acceptance Scenarios**:

1. **Given** checkpoints indicate Phase 1 is completed, **When** the workflow restarts, **Then** Phase 1 is skipped and Phase 2 activity is invoked first.
2. **Given** the activity detects tasks already marked `- [X]`, **When** `speckit.implement` is invoked, **Then** it receives flags telling it to skip completed tasks.

---

### User Story 3 - Review AI execution outcomes (Priority: P3)

A delivery lead reviews machine-readable execution logs to understand what the AI changed in each phase and whether additional manual intervention is required.

**Why this priority**: Provides auditability and confidence that automated changes align with expectations.

**Independent Test**: Complete at least one phase and confirm the workflow stores a JSON result containing the phase name, execution status, log location, and summary lines from the AI run.

**Acceptance Scenarios**:

1. **Given** an activity finishes, **When** the workflow records results, **Then** structured data includes status, timestamps, captured stdout/stderr paths, and any remediation messages.
2. **Given** the workflow completes all phases, **When** a stakeholder inspects stored results, **Then** they can tell which phases succeeded, failed, or were skipped without reading raw logs.

---

### Edge Cases

- `tasks.md` is missing phase headings (`## Phase`), so the workflow must fail fast with a descriptive error and no activities run.
- A phase heading exists with zero task bullets; the activity returns a "nothing to do" result and the workflow marks the phase as completed without invoking AI.
- `speckit.implement` returns partial updates (some tasks completed, others untouched); the activity must capture the tool output, re-read `tasks.md`, and fail the phase if any tasks remain unchecked.
- `tasks.md` already marks all tasks complete at workflow start; workflow exits immediately with an "already complete" status.
- Network or CLI failures occur mid-run; the workflow records the failure reason, persists partial logs, and waits for manual resume.
- CLI output may include non-UTF-8 bytes; activities must decode stdout/stderr using UTF-8 with `errors="replace"` and surface sanitized copies alongside raw artifacts for debugging.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The workflow MUST accept either the absolute path to `tasks.md` or the full file content as an input parameter and validate accessibility before starting execution.
- **FR-002**: The parsing activity MUST extract every heading that matches the pattern `## Phase <ordinal>: <label>` in document order and associate all subsequent task bullets (`- [ ] T### description` or `- [X] T### description`) until the next phase heading or EOF.
- **FR-003**: For each parsed phase, the workflow MUST invoke a generic `run_phase` Temporal activity with arguments: full `tasks.md` content, phase name string, phase identifier (e.g., `Phase 2`), task list, execution context (repository path, working branch, target AI model, agent profile), and any checkpoint metadata.
- **FR-004**: The `run_phase` activity MUST call the OpenCode CLI (`speckit.implement`) using the provided model/agent parameters, instructing it to operate only on the supplied task identifiers, and MUST capture stdout, stderr, exit code, and generated artifacts using tolerant decoding (`errors="replace"`) so automation never crashes on unexpected bytes.
- **FR-005**: After `speckit.implement` finishes, the activity MUST reload `tasks.md`, confirm every task for that phase is marked with `- [X]`, and produce an error if any remain unchecked.
- **FR-006**: The activity MUST return a `PhaseResult` payload containing phase metadata, task IDs touched, success/failure status, timestamps, log file paths, and a summary of AI output in machine-readable JSON.
- **FR-007**: The workflow MUST persist a checkpoint after each successful phase containing the last completed phase name, cumulative results, and a hash of the updated `tasks.md`, enabling idempotent retries and skip-ahead behavior on resume.
- **FR-008**: On workflow restart, logic MUST compare checkpoints with current `tasks.md`; previously completed phases are skipped automatically, and phases with unchecked tasks are queued next. If the document checksum differs from the stored checkpoint, the workflow treats the live `tasks.md` as authoritative, refreshes checkpoint data to match, and continues processing from the earliest incomplete phase.
- **FR-009**: Activities MUST accept configurable timeout, retry policy, and backoff values suitable for long-running AI operations (default timeout ≥ 30 minutes) and surface retriable vs. non-retriable errors separately; overrides MUST be provided through workflow inputs and propagated to Temporal activity options and CLI flags.
- **FR-010**: The workflow MUST expose extension hooks to adjust AI parameters per phase (e.g., allow overriding model or agent profile through workflow input overrides or metadata in the phase heading) and MUST document an accepted metadata format (e.g., `## Phase 2: Implement run_phase [model=gpt-4o-mini agent=review]`) that downstream activities respect.
- **FR-011**: The workflow MUST log high-level progress using `workflow.logger` (phase start, completion, failure) without embedding non-deterministic parsing logic inside the workflow code; all heavy operations remain inside activities.
- **FR-012**: Upon completion, the workflow MUST emit an aggregate execution report summarizing per-phase outcomes and providing references for downstream workflows (batch mode, interactive resume).

### Key Entities *(include if feature involves data)*

- **PhaseDefinition**: Represents a parsed phase, including `phase_id`, human-readable `title`, ordered list of `TaskItem`s, optional execution hints (model overrides, agent directives), and raw markdown slice.
- **TaskItem**: A single checklist entry with fields for `task_id` (e.g., `T004`), `description`, `is_complete`, and any tags detected in the markdown bullet.
- **PhaseExecutionHints**: Encapsulates optional overrides parsed from phase metadata (model choice, agent profile, timeout/backoff tweaks) and validates that only supported keys are present.
- **PhaseExecutionContext**: Runtime inputs for the activity such as repository path, branch, AI model, agent profile, retries, environment variables, and checkpoint tokens.
- **PhaseResult**: Machine-readable response containing `phase_id`, status (`success`, `failed`, `skipped`), list of completed task IDs, verification hash of `tasks.md`, stdout/stderr capture locations, duration, and optional remediation notes.
- **WorkflowCheckpoint**: Accumulates ordered `PhaseResult`s, last processed phase index, and checksum of `tasks.md` to detect drift before resuming execution.
- **ResumeState**: Tracks the earliest incomplete phase, detected document drift, and the checkpoint hash used to resume execution so workflows can reconcile live `tasks.md` content with stored results.

### Assumptions & Dependencies

- `speckit.implement` is available on the worker host via the OpenCode CLI and can be invoked non-interactively with model/agent flags.
- Workers have write access to the repository so AI-generated changes and `tasks.md` updates can be committed outside of the workflow scope.
- The top-level orchestration workflow (batch/interactive/resume modes) will call this feature by providing the latest `tasks.md` content and desired AI configuration.
- Checkpoint persistence can leverage Temporal workflow state or an external durable store already approved for the project; this spec assumes in-workflow state is sufficient.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In a dry-run test with three phases and nine tasks, the workflow completes all phases sequentially on the first attempt with 100% of targeted tasks marked `- [X]` afterward.
- **SC-002**: When a phase failure is simulated, a subsequent resume run skips all previously completed phases and restarts within one workflow task (≤ 5 minutes) of submission.
- **SC-003**: Stakeholders can retrieve a JSON execution report per phase containing status, timestamps, and log references without accessing raw CLI output, and report retrieval succeeds within two minutes of phase completion.
- **SC-004**: Activity invocations handle long-running AI calls without exceeding configured timeouts in 95% of runs, and retries are limited to the policy defined in workflow inputs with clear differentiation of retriable vs. terminal errors.
