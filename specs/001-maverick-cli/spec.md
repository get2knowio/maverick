# Feature Specification: Maverick CLI for Local Temporal AI Workflow Orchestration

**Feature Branch**: `001-maverick-cli`  
**Created**: 2025-11-10  
**Status**: Draft  
**Input**: User description: "Define a command-line tool (“maverick”) that runs inside a development container or local repo and acts as the front door to the Temporal-based AI workflow. The CLI gathers inputs (task files, spec paths, model preferences), builds TaskDescriptors, invokes the workflow locally, streams status, and ensures it runs against the current git project (including branch switching performed by the workflow)."

## Clarifications

### Session 2025-11-10
- Q: What deterministic ordering should the CLI use when multiple task files are discovered to build/start TaskDescriptors? → A: Order by numeric feature directory prefix ascending (e.g., 001 < 002 < 010) then lexicographic task file name within each directory.
- Q: What observability signals must the CLI produce for runs and status queries? → A: Emit structured logs plus basic metrics (no tracing): counts and durations to stdout/stderr (human-readable) and JSON fields with `--json`.
- Q: Dirty working tree behavior and interactivity → A: Proceed only with explicit `--allow-dirty`; never prompt (even with `--interactive`).

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

### User Story 1 - Run workflow from a repo (Priority: P1)

A developer in a git repo runs `maverick run` to discover tasks/specs, build TaskDescriptors, start the multi-task workflow, and see live progress in the terminal.

**Why this priority**: This is the primary value path—turn a repository with specs into an automated, phase-based implementation loop with minimal setup.

**Independent Test**: From a clean git repo with valid `specs/*/tasks.md`, run `maverick run` and verify descriptors are built, a workflow is started, an ID is shown, and per-phase updates are printed until completion.

**Acceptance Scenarios**:

1. Given a git repo on a clean working tree with `specs/001-some-feature/tasks.md`, when the user runs `maverick run`, then the CLI detects repo root and current branch, discovers one task file, builds one TaskDescriptor including a `return_to_branch`, starts the workflow, prints `workflow_id` and `run_id`, and streams phase updates until done.
2. Given a repo with no discoverable tasks, when the user runs `maverick run`, then the CLI exits non-zero with a clear message and an optional `--json` output explaining that no tasks were found.

---

### User Story 2 - Targeted run and dry-run (Priority: P2)

A developer selects a specific task file or enables interactive pauses or prints descriptors without starting anything to validate inputs.

**Why this priority**: Precision and safety—developers often want to run one task at a time or validate descriptor construction before launching a long workflow.

**Independent Test**: Run `maverick run --task specs/001-some-feature/tasks.md --interactive` and separately `maverick run --task specs/001-some-feature/tasks.md --dry-run --json`.

**Acceptance Scenarios**:

1. Given a valid task file path, when the user runs with `--task <path>`, then the CLI builds exactly one TaskDescriptor for that path and starts the workflow (unless `--dry-run`).
2. Given `--dry-run --json`, when executed, then the CLI prints a machine-readable JSON array of TaskDescriptors and exits with code 0 without contacting the workflow service.

---

### User Story 3 - Check status of a workflow (Priority: P3)

A developer checks the progress of an already-started workflow by ID at any time.

**Why this priority**: Observability and resumability—developers may close the session and later inspect progress by ID.

**Independent Test**: Start a workflow, capture `workflow_id`, and run `maverick status <workflow-id>` to see task/phase and last activity.

**Acceptance Scenarios**:

1. Given a valid `workflow_id`, when `maverick status <id>` is run, then the CLI outputs current task, phase, last activity message, and overall state; with `--json`, it outputs a machine-readable status document.
2. Given an invalid `workflow_id`, when `maverick status <id>` is run, then the CLI exits non-zero with a clear error message and optional JSON error payload.

---

[Add more user stories as needed, each with an assigned priority]

### Edge Cases

- Running outside a git repository → fail with guidance
 - Dirty working tree (uncommitted changes) → abort by default; proceed only with `--allow-dirty`. No prompts are ever shown (even when `--interactive`).
- No discoverable tasks/specs → clear error message; suggest `--task` or verifying `specs/*/tasks.md`
- Temporal server not reachable → fail fast with clear remediation text
- Multiple tasks discovered → create one TaskDescriptor per task ordered by numeric spec directory prefix ascending then lexicographic task file name (stable ordering)
- Extremely large number of tasks (100+) → confirm descriptors are constructed efficiently; status output remains readable (truncate with `--compact`)
- Invalid `--task` path or outside repo root → fail with message
- Interrupted run (Ctrl+C) → CLI exits gracefully; the workflow continues remotely; status still queryable by ID

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001 (Command: run)**: Provide `maverick run` to discover tasks/specs in the current repository and start the multi-task workflow. Discovery rules:
  - Search under `specs/*/tasks.md` for active tasks (exclude `specs-completed/`).
  - If `--task <path>` is provided, run only that file (must exist within repo root).
  - If no tasks found, exit non-zero with a clear message and suggestions.

- **FR-002 (Command: status)**: Provide `maverick status <workflow-id>` to display current progress (per-task, per-phase, last activity). Support `--json` for machine-readable output.

- **FR-003 (Descriptor construction)**: Build a TaskDescriptor for each discovered task/spec with fields:
  - `task_id` (string): stable ID derived from spec directory and file name (slug).
  - `task_file` (string): absolute path to tasks file.
  - `spec_root` (string): absolute path to the spec folder (e.g., `specs/001-foo`).
  - `branch_name` (string): branch hint for the workflow. If not provided by config, derive from `task_id` as a safe slug. The CLI MUST NOT create or switch branches; it only passes the hint.
  - `return_to_branch` (string): name of the current branch when `run` is invoked.
  - `repo_root` (string): absolute path to repository root.
  - `interactive` (boolean): from `--interactive` (default false).
  - `model_prefs` (object): optional preferences collected from flags or config; may include `provider`, `model`, and `max_tokens`.

- **FR-004 (Temporal start)**: Start the existing multi-task workflow locally with an array of TaskDescriptors, capture `workflow_id` and `run_id`, and print them. On `--json`, emit a JSON object containing IDs and a summary count.

- **FR-005 (Status streaming in run)**: During `maverick run`, after starting the workflow, stream human-readable progress lines until completion or user interrupt. Include per-task current phase and last activity. Use a 2s refresh interval to keep output readable (aligns with SC-002 p95 ≤ 2s).

- **FR-006 (Interactive mode)**: `--interactive` flag must set `interactive=true` in each TaskDescriptor so the workflow pauses between phases (the workflow enforces pauses; the CLI only passes the flag).

- **FR-007 (Dry-run)**: `--dry-run` prints the TaskDescriptor array (human-readable by default; JSON when `--json`) and exits without contacting the workflow service.

- **FR-008 (Dirty tree guard)**: If working tree is dirty, show a clear warning. Proceed only if the user supplies `--allow-dirty`. Default is to abort. The CLI never prompts for confirmation, even when `--interactive` is set.

- **FR-009 (Scriptability)**: All commands must support `--json` to emit machine-readable output and exit codes suitable for CI. No interactive prompts unless explicitly requested (e.g., `--interactive`).

- **FR-010 (Performance and scale)**: Discovery and descriptor building should handle at least 200 tasks within 5 seconds on a standard devcontainer.

- **FR-011 (Safety)**: The CLI MUST NOT change branches or write to the repo aside from logs/output; branch switching remains the workflow’s responsibility.

- **FR-012 (Help and version)**: Provide `--help` and `--version` flags for each command.

- **FR-013 (Observability)**: The CLI MUST emit structured logs and core metrics; tracing is out-of-scope for this feature.
  - Logs: human-readable by default; JSON-structured when `--json` is provided. Include correlation fields where applicable (e.g., `workflow_id`, `run_id`).
  - Metrics (emit as log fields and/or summary lines):
    - `task_count` (int) – number of TaskDescriptors built
    - `discovery_ms` (int) – time to discover tasks and build descriptors
    - `workflow_start_ms` (int) – time from command start to workflow start response
    - `status_poll_latency_ms_p95` (int) – 95th percentile of status polling latency during a run
    - `errors_count` (int) – total errors encountered during command execution
  - No distributed tracing/spans in this phase.

### Key Entities *(include if feature involves data)*

- **TaskDescriptor**
  - Purpose: describes a single task/spec to be executed by the workflow
  - Fields: `task_id`, `task_file`, `spec_root`, `branch_name`, `return_to_branch`, `repo_root`, `interactive`, `model_prefs`
  - Constraints:
    - `task_file` must exist and be within `repo_root`
    - `return_to_branch` is captured from the current repo state
    - `branch_name` is a hint; no git changes performed by CLI

- **WorkflowStartResponse**
  - Fields: `workflow_id` (string), `run_id` (string), `tasks_count` (integer)

- **WorkflowStatus**
  - Fields: `state` (e.g., running, completed, failed), `current_task_id`, `current_phase`, `last_activity`, `updated_at`, `tasks` (array of per-task states)

- **OrchestrationInput**
  - Purpose: input envelope passed to the multi-task workflow
  - Fields: `task_descriptors` (array of TaskDescriptor), `repo_root` (string), `return_to_branch` (string), `interactive_mode` (boolean), `model_prefs` (object)
  - Notes:
    - Phases are determined by the workflow; the CLI does not define or override phases.

## Success Criteria *(mandatory)*

<!--
  ACTION REQUIRED: Define measurable success criteria.
  These must be technology-agnostic and measurable.
-->

### Measurable Outcomes

- **SC-001**: From a clean repo with one task, a developer can kick off a run and see the first status update within 5 seconds.
- **SC-002**: Status refreshes appear within 2 seconds of workflow progress (95th percentile) during `maverick run`.
- **SC-003**: Descriptor discovery builds 100+ TaskDescriptors in under 5 seconds in the devcontainer.
- **SC-004**: Running with a dirty working tree without `--allow-dirty` results in a clear, actionable message 100% of the time.
- **SC-005**: When the local workflow service is unavailable, the CLI surfaces a failure with remediation text within 3 seconds and exits non-zero.
- **SC-006**: On `maverick run --json`, the output includes `task_count`, `discovery_ms`, and `workflow_id`/`run_id` fields; during streaming mode, periodic lines contain `current_task_id`, `current_phase`, and a measured poll latency.

## CLI Commands and Flags

This section describes WHAT the CLI exposes to users (names, flags, behaviors). It intentionally avoids implementation details.

- `maverick run [--task <path>] [--interactive] [--dry-run] [--json] [--allow-dirty] [--compact]`
  - Default: discover tasks in `specs/*/tasks.md` and start the multi-task workflow.
  - `--task <path>`: run exactly one task file.
  - `--interactive`: set `interactive=true` in descriptors to pause between phases.
  - `--dry-run`: print descriptors and exit (no workflow calls).
  - `--json`: emit machine-readable outputs.
  - `--allow-dirty`: bypass the dirty-tree guard.
  - `--compact`: reduce verbosity of streaming status.

- `maverick status <workflow-id> [--json]`
  - Print current task, phase, last activity, and overall state for the workflow ID.
  - `--json`: emit machine-readable status.

### Deterministic Exit Codes

| Code | Meaning | Applies To |
|------|---------|------------|
| 0    | Success: run completed, status retrieved, or dry-run printed without validation issues. | All commands |
| 1    | General runtime failure: service unavailable, networking errors, unexpected exceptions during CLI execution. | `run`, `status` |
| 2    | Validation/guard failure: dirty working tree without `--allow-dirty`, invalid task path/descriptor, zero tasks discovered, malformed flag combination. | `run`, `status`, discovery helpers |
| 3    | Workflow reported failure even though the CLI call succeeded (e.g., workflow finished in `failed` state). Surfaces actionable workflow failure context to CI/CD. | `run`, `status` |
| 4–9 | Reserved for future specific conditions (e.g., explicit cancel/rollback flows) and must be documented before use. | N/A |

Commands must not invent ad-hoc codes; CI/CD tooling can rely on the table above.

## How the CLI Interacts with the Workflow

- Start: `maverick run` constructs an array of TaskDescriptors and starts the existing multi-task workflow on the local workflow service, capturing `workflow_id` and `run_id` for display.
- Status: `maverick run` then periodically queries progress and prints readable updates until completion or interrupt. `maverick status` can be used at any time with a `workflow_id` to fetch the current status.

## Task and Spec Discovery

- Primary discovery path: `specs/*/tasks.md` (active features only)
- The spec root for a task is the directory containing `tasks.md` (e.g., `specs/001-some-feature`)
- The CLI ignores `specs-completed/`
- If no tasks are discovered and `--task` is not set, the CLI exits with guidance.
- Ordering: When multiple task files are discovered, sort spec directories by zero-padded numeric prefix ascending (001 < 002 < 010) and within each directory sort task file names lexicographically; build TaskDescriptors in that sequence.

## Error Handling Notes

- Dirty repo: show a warning and refuse to proceed unless `--allow-dirty`; exit code 2. The CLI never stages/commits on the user’s behalf and does not prompt for confirmation.
- Missing/Unreachable workflow service: fail fast with a clear message and remediation (e.g., "start local service inside the devcontainer"); exit code 1.
- Invalid task path or zero tasks discovered: fail with a clear message including the expected location and repo root; exit code 2.
- Workflow reported failure: stream the workflow’s terminal failure summary and exit code 3 even though CLI connectivity succeeded.
- Unexpected runtime errors: provide a succinct error, suggest `--json` for details, and exit code 1.

## Assumptions & Dependencies

- The multi-task workflow is already implemented and accepts an array of TaskDescriptors.
- A local workflow service is available inside the devcontainer or host environment when runs are attempted.
- `specs-completed/*` are archival and not considered for discovery.
- The workflow performs branch switching and PR/CI steps; CLI only passes context.
