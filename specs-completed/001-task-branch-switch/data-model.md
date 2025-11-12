# Data Model: Per-Task Branch Switching

## TaskDescriptor (existing core model)
- **Fields (existing)**: `task_id: str`, `spec_path: Path`, `explicit_branch: str | None`, `phases: list[str]`
- **New/Updated Semantics**:
  - `spec_path` must reside under `specs/<slug>/` for automatic branch derivation.
  - `explicit_branch`, when provided, overrides slug derivation but must match `^[A-Za-z0-9._/-]+$` to remain git-safe.
- **Invariants**:
  - Either `explicit_branch` is set **or** `spec_path.parent.name` supplies a slug.
  - Descriptor validation records the resolved branch name for downstream use.

## BranchExecutionContext (new)
Captures per-task branch orchestration state persisted in workflow history.

| Field | Type | Description |
|-------|------|-------------|
| `resolved_branch` | `str` | Final branch name selected for the task.
| `checkout_status` | `Literal["pending", "complete", "failed"]` | Status of the latest checkout attempt.
| `checkout_message` | `str | None` | Human-readable note or failure reason.
| `last_checkout_at` | `datetime | None` | Workflow time when checkout succeeded.
| `cleanup_status` | `Literal["pending", "complete", "failed"]` | Status for `checkout_main`/`delete_task_branch` sequence.
| `cleanup_message` | `str | None` | Additional context about cleanup results.

**Invariants**:
- `checkout_status == "complete"` requires `resolved_branch` and `last_checkout_at` to be populated.
- `cleanup_status != "pending"` requires `checkout_status == "complete"` (cleanup runs only after checkout success).

## Activity Inputs & Outputs

### `derive_task_branch`
- **Input**: `task_descriptor: TaskDescriptor`
- **Output**: `BranchSelection`

`BranchSelection`
- `branch_name: str`
- `source: Literal["explicit", "spec-slug"]`
- `log_message: str`

### `checkout_task_branch`
- **Input**: `branch_name: str`
- **Output**: `CheckoutResult`

`CheckoutResult`
- `branch_name: str`
- `changed: bool` (whether a checkout occurred)
- `status: Literal["success", "already-active"]`
- `git_head: str` (short SHA after checkout)
- `logs: list[str]` (sanitized git CLI summaries)

### `checkout_main`
- **Input**: `main_branch: str = "main"`
- **Output**: `MainCheckoutResult`

`MainCheckoutResult`
- `status: Literal["success", "already-on-main"]`
- `git_head: str`
- `pull_fast_forwarded: bool`
- `logs: list[str]`

### `delete_task_branch`
- **Input**: `branch_name: str`
- **Output**: `DeletionResult`

`DeletionResult`
- `status: Literal["deleted", "missing"]`
- `reason: str`
- `logs: list[str]`

**Shared Validation Rules**:
- All branch names validated with git-safe slug regex before command execution.
- Activity outputs must remain JSON-serializable with deterministic ordering.
- Logs trimmed to reasonable length (≤1 KiB each) to protect workflow history size.
