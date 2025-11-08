# Data Model

## PhaseDefinition
- **Purpose**: Parsed representation of a `tasks.md` phase.
- **Fields**:
  - `phase_id: str` (e.g., `"phase-2"`): normalized identifier derived from ordinal.
  - `ordinal: int`: numeric order extracted from heading.
  - `title: str`: human-readable label (e.g., `"Implement resume flow"`).
  - `tasks: list[TaskItem]`: ordered tasks belonging to this phase.
  - `execution_hints: PhaseExecutionHints | None`: optional metadata parsed from heading/body (model overrides, agent profile, flags).
  - `raw_markdown: str`: slice of markdown covering the heading and associated bullets.
- **Invariants**:
  - `ordinal` MUST be ≥ 1 and match `phase_id`.
  - `tasks` MAY be empty, but `execution_hints` MUST NOT require tasks (edge case satisfied by returning "nothing to do").
  - Title MUST be non-empty after trimming.
- **Relationships**:
  - Aggregates multiple `TaskItem` entries.
  - Provides input to `PhaseExecutionContext`.

## TaskItem
- **Purpose**: Represents an individual checklist entry.
- **Fields**:
  - `task_id: str` (e.g., `"T004"`): extracted token following Speckit convention.
  - `description: str`: remaining bullet text without checkbox or task ID.
  - `is_complete: bool`: true if checkbox is `[X]` or `[x]`.
  - `tags: list[str]`: optional inline tags (e.g., `#refactor`).
- **Invariants**:
  - `task_id` MUST match regex `^T\d{3,}$` when present; fallback ID `None` indicates malformed bullet and triggers validation error before workflow proceeds.
  - `description` MUST be non-empty once whitespace removed.
- **Relationships**:
  - Belongs to exactly one `PhaseDefinition`.

## PhaseExecutionHints
- **Purpose**: Captures optional overrides discovered in headings or metadata blocks.
- **Fields**:
  - `model: str | None`: override AI model (e.g., `"gpt-4.1"`).
  - `agent_profile: str | None`: override agent persona.
  - `extra_env: dict[str, str]`: environment variable overrides to inject into CLI call.
- **Invariants**:
  - Keys in `extra_env` MUST be uppercase and ASCII.
- **Relationships**:
  - Referenced by `PhaseExecutionContext`.

## PhaseExecutionContext
- **Purpose**: Activity input describing execution parameters.
- **Fields**:
  - `repo_path: Path`: absolute path to repository root.
  - `branch: str`: checked-out branch for modifications.
  - `tasks_md_path: Path | None`: optional path if file accessible locally.
  - `tasks_md_content: str | None`: file content when supplied inline.
  - `phase: PhaseDefinition`: phase to execute.
  - `checkpoint: WorkflowCheckpoint | None`: most recent checkpoint snapshot.
  - `timeout_minutes: int`: configured timeout per FR-009 (default ≥ 30).
  - `retry_policy: RetryPolicy`: Temporal retry parameters (max attempts, backoff, non-retriable errors).
  - `hints: PhaseExecutionHints | None`: overrides effective for this phase.
- **Invariants**:
  - Exactly one of `tasks_md_path` or `tasks_md_content` MUST be provided.
  - `timeout_minutes` MUST be ≥ 30.
  - `repo_path` MUST exist and be writable (validated before enqueueing activity).

## PhaseResult
- **Purpose**: Machine-readable activity output summarizing phase execution.
- **Fields**:
  - `phase_id: str`
  - `status: PhaseResultStatus` where `PhaseResultStatus = Literal["success", "failed", "skipped"]`
  - `completed_task_ids: list[str]`
  - `started_at: datetime`
  - `finished_at: datetime`
  - `duration_ms: int`
  - `tasks_md_hash: str` (hex-encoded `blake2b` digest)
  - `stdout_path: Path | None`
  - `stderr_path: Path | None`
  - `artifact_paths: list[Path]`
  - `summary: list[str]`: curated lines from CLI output or remediation messages.
  - `error: str | None`: populated when `status == "failed"`.
- **Invariants**:
  - `finished_at` MUST be ≥ `started_at`.
  - `duration_ms` MUST equal `(finished_at - started_at).total_seconds() * 1000` rounded to int.
  - `error` MUST be present when status is `"failed"`.
- **Relationships**:
  - Appended to `WorkflowCheckpoint.results`.

## WorkflowCheckpoint
- **Purpose**: Persisted workflow state enabling resume behavior.
- **Fields**:
  - `last_completed_phase_index: int`
  - `results: list[PhaseResult]`
  - `tasks_md_hash: str`
  - `updated_at: datetime`
- **Invariants**:
  - `last_completed_phase_index` MUST equal `len(results) - 1` when results non-empty; `-1` indicates no phases run.
  - `tasks_md_hash` MUST reflect the same digest used in the most recent `PhaseResult`.
- **Relationships**:
  - Stored directly in workflow state and passed into subsequent activities.

## ResumeState
- **Purpose**: Internal workflow helper struct summarizing resume decisions.
- **Fields**:
  - `starting_phase_index: int`
  - `phases_to_run: list[PhaseDefinition]`
  - `skipped_phase_ids: list[str]`
  - `checkpoint: WorkflowCheckpoint | None`
- **Invariants**:
  - `starting_phase_index` MUST point to the first phase in `phases_to_run` when list non-empty.
- **Relationships**:
  - Derived from parsed phases and checkpoint for deterministic workflow branching.
