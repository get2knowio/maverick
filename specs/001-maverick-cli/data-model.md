# Data Model: Maverick CLI

Date: 2025-11-10
Feature: Maverick CLI (Temporal orchestration front door)

## Entities

### TaskDescriptor (Workflow Model Reused)
Purpose: Existing workflow model reused; CLI populates fields and adds transient context values externally.

Base Fields (workflow-defined):
- task_id (string): Stable slug from spec directory + file name.
- task_file (string): Absolute path to tasks.md.
- spec_root (string): Absolute path to the spec directory containing the task.
- branch_name (string | null): Optional branch hint; derived from task_id when not provided.

CLI-Sourced Context (not persisted in model, passed separately):
- return_to_branch (string): Current git branch at invocation time.
- repo_root (string): Absolute repository root.
- interactive (boolean): From `--interactive`.
- model_prefs (object | null): Optional; keys: provider (string), model (string), max_tokens (int).

Invariants (enforced before workflow start):
- task_file MUST exist and be under repo_root.
- spec_root MUST be parent of task_file.
- return_to_branch MUST be non-empty.
- If branch_name provided, MUST be a safe git branch string ([-._a-z0-9]+ after normalization).

### OrchestrationInput (Workflow Invocation)
Adapter from CLI → Workflow input.

Relevant Fields:
- task_descriptors (array<TaskDescriptor>): From discovery ordering.
- interactive_mode (boolean)
- repo_path (string)
- branch (string): Starting branch for context; workflow handles switching.
- default_model (string | null)
- default_agent_profile (string | null)
- retry_limit (int)

Validation:
- task_descriptors MUST be non-empty unless `--dry-run`.
- repo_path MUST equal repo_root.

### WorkflowStartResponse (CLI Output)
Fields:
- workflow_id (string)
- run_id (string)
- task_count (int)
- discovery_ms (int)
- workflow_start_ms (int)

### WorkflowStatus (CLI Output)
Fields:
- state (string: running|completed|failed|paused)
- current_task_id (string | null)
- current_phase (string | null)
- last_activity (string | null, ISO8601 timestamp of the most recent workflow or task event; null until the first event)
- updated_at (string, ISO8601)
- tasks (array<TaskProgress>)

### TaskProgress
Fields:
- task_id (string)
- status (string: pending|running|success|failed|skipped)
- last_message (object | null): when present, the object includes `text` (string, max 1024 chars; longer messages are truncated with ellipsis), `level` (Literal["error","warn","info","debug"]), and `timestamp` (string, ISO8601). When absent, no message has been emitted for this task.

## State Transitions

### WorkflowStatus.state transitions

| From    | To         | Trigger                  | Terminal? | Notes |
|---------|------------|--------------------------|-----------|-------|
| running | completed  | Workflow finished normally (automatic) | Yes | `completed` is terminal; no further transitions allowed. |
| running | failed     | Unhandled workflow error or forced cancellation (automatic) | Yes | `failed` is terminal; retry requires a new run. |
| running | paused     | User-issued pause via CLI/workflow signal | No | Captures state snapshot and halts polling loops. |
| paused  | running    | User resume (CLI resumes polling) | No | Only transition out of `paused` unless failure occurs during resume. |
| paused  | failed     | Workflow reports failure while paused/resuming (automatic) | Yes | Indicates pause could not be recovered; CLI must surface reason. |

All transitions are atomic and monotonic; there is no path from a terminal state back to `running` or `paused`, and `completed` cannot later move to `cancelled` or `rolled-back` without starting a new workflow.

### TaskProgress.status transitions

| From   | To       | Trigger                       | Terminal? | Notes |
|--------|----------|-------------------------------|-----------|-------|
| pending| running  | Workflow begins executing task (automatic) | No | Only entry point to `running`. |
| running| success  | Task finished with pass status (automatic) | Yes | Terminal success; cannot revert. |
| running| failed   | Task raised error/verification failure (automatic) | Yes | Terminal failure; retries create a new workflow attempt. |
| pending| skipped  | User marked skip or workflow auto-skip due to gating (user/automatic) | Yes | Skipped tasks never re-enter pipeline in the same run. |

Invalid transitions (e.g., running → pending, success → running) must never be emitted; the workflow enforces monotonic progress.

## Notes
- CLI output uses human-readable logs by default; JSON mode mirrors these structures. After discovery and at completion the CLI prints a short summary block with labeled values and units, e.g.:

```
=== Maverick Run Summary ===
task_count: 4
discovery_ms: 180
workflow_start_ms: 95
status_poll_latency_ms_p95: 220 (optional)
errors_count: 0
```

  The same keys (task_count, discovery_ms, workflow_start_ms, status_poll_latency_ms_p95 when available, errors_count) are preserved verbatim in `--json` output for contract stability.
