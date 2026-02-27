# Data Model: Python-Native Workflow Definitions

**Feature Branch**: `035-python-workflow`
**Date**: 2026-02-26

## Entity Diagram

```
                        ┌─────────────────────┐
                        │   PythonWorkflow     │ (ABC)
                        │─────────────────────│
                        │ config: MaverickConfig│
                        │ registry: ComponentR.│
                        │ checkpoint_store: CS  │
                        │ step_executor: SE?    │
                        │─────────────────────│
                        │ execute(inputs)       │ → AsyncGenerator[ProgressEvent]
                        │ _run(inputs)          │ → Any (abstract)
                        │ resolve_step_config() │ → StepConfig
                        │ emit_step_started()   │
                        │ emit_step_completed() │
                        │ emit_step_failed()    │
                        │ register_rollback()   │
                        │ save_checkpoint()     │
                        │ load_checkpoint()     │
                        └──────────┬──────────┘
                                   │ extends
                    ┌──────────────┴──────────────┐
                    │                              │
         ┌──────────────────┐          ┌───────────────────────┐
         │ FlyBeadsWorkflow │          │ RefuelSpeckitWorkflow  │
         │──────────────────│          │───────────────────────│
         │ workspace_mgr    │          │ (no extra state)       │
         │──────────────────│          │───────────────────────│
         │ _run(inputs)     │          │ _run(inputs)           │
         └──────────────────┘          └───────────────────────┘
```

## Entities

### PythonWorkflow (Abstract Base Class)

**Location**: `src/maverick/workflows/base.py`
**Responsibility**: Template for all Python-native workflows. Manages event emission, step tracking, rollback, and checkpoint lifecycle.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `config` | `MaverickConfig` | required | Project configuration (injected) |
| `registry` | `ComponentRegistry` | required | Component registry for action/agent dispatch |
| `checkpoint_store` | `CheckpointStore \| None` | `None` | Optional checkpoint persistence |
| `step_executor` | `StepExecutor \| None` | `None` | Optional agent step executor |
| `_event_queue` | `asyncio.Queue[ProgressEvent \| None]` | auto | Internal event queue (None = sentinel) |
| `_step_results` | `list[StepResult]` | `[]` | Accumulated step results |
| `_step_start_times` | `dict[str, float]` | `{}` | Step start timestamps for duration calc |
| `_current_step` | `str \| None` | `None` | Currently executing step name (for error tracking) |
| `_rollback_stack` | `list[tuple[str, PythonRollbackAction]]` | `[]` | Registered rollback actions (name + async callable) |
| `_workflow_name` | `str` | required | Workflow identifier (set by subclass) |

**New Type**:
- `PythonRollbackAction = Callable[[], Awaitable[None]]` — defined in `base.py`. Does NOT reuse the DSL's `RollbackAction` which requires `WorkflowContext`.

**Validation Rules**:
- `config` must not be `None`
- `registry` must not be `None`
- `_workflow_name` must be set by subclass (abstract property or constructor arg)

**Methods**:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `result` | `WorkflowResult \| None` | `None` | Populated after `execute()` generator completes; callers access this for the final result |

**Methods**:

| Method | Signature | Description |
|--------|-----------|-------------|
| `execute` | `(inputs: dict[str, Any]) -> AsyncGenerator[ProgressEvent, None]` | Template method — yields events from queue while `_run()` executes. Stores aggregated `WorkflowResult` in `self.result` after completion. Note: `WorkflowCompleted` event signals completion but does NOT embed the result (it only has workflow_name/success/total_duration_ms/timestamp). |
| `_run` | `(inputs: dict[str, Any]) -> Any` | Abstract — subclass implements workflow logic |
| `resolve_step_config` | `(step_name: str, step_type: StepType = StepType.PYTHON) -> StepConfig` | Delegates to `maverick.dsl.executor.config.resolve_step_config()` |
| `emit_step_started` | `(name: str, step_type: StepType = StepType.PYTHON) -> None` | Emits `StepStarted`, records start time |
| `emit_step_completed` | `(name: str, output: Any = None, step_type: StepType = StepType.PYTHON) -> None` | Emits `StepCompleted`, creates `StepResult`, appends to results |
| `emit_step_failed` | `(name: str, error: str, step_type: StepType = StepType.PYTHON) -> None` | Emits `StepCompleted(success=False)`, creates failure `StepResult` |
| `emit_output` | `(step_name: str, message: str, level: str = "info") -> None` | Emits `StepOutput` for informational messages |
| `register_rollback` | `(name: str, action: RollbackAction) -> None` | Pushes rollback to stack |
| `save_checkpoint` | `(data: dict[str, Any]) -> None` | Delegates to `CheckpointStore.save()` |
| `load_checkpoint` | `() -> dict[str, Any] \| None` | Delegates to `CheckpointStore.load_latest()` |

---

### FlyBeadsWorkflow

**Location**: `src/maverick/workflows/fly_beads/workflow.py`
**Responsibility**: Bead-driven development workflow — iterates ready beads until done.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| (inherits all PythonWorkflow fields) | | | |

**`_run()` Inputs**:

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `epic_id` | `str` | No | `""` | Filter beads by epic |
| `max_beads` | `int` | No | `30` | Max beads to process |
| `dry_run` | `bool` | No | `False` | Preview mode |
| `skip_review` | `bool` | No | `False` | Skip code review |

**`_run()` Output**:

```python
{
    "epic_id": str,
    "workspace_path": str,
    "beads_processed": int,
    "beads_succeeded": int,
    "beads_failed": int,
    "beads_skipped": int,
}
```

**State Transitions** (per bead):

```
SELECTED → IMPLEMENTING → VALIDATING → REVIEWING → COMMITTING → COMPLETED
    │            │              │            │            │
    └────────────┴──────────────┴────────────┴────────────┘
                              ↓
                       ROLLED_BACK (jj restore)
```

---

### RefuelSpeckitWorkflow

**Location**: `src/maverick/workflows/refuel_speckit/workflow.py`
**Responsibility**: Generate beads from a SpecKit specification.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| (inherits all PythonWorkflow fields) | | | |

**`_run()` Inputs**:

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `spec` | `str` | Yes | — | Spec identifier (branch name / directory) |
| `dry_run` | `bool` | No | `False` | Preview bead definitions |

**`_run()` Output**:

```python
{
    "epic": dict,              # Epic bead info
    "work_beads": list[dict],  # Created work beads
    "dependencies": list[dict], # Wired dependencies
    "errors": list[str],       # Any errors encountered
    "commit": str | None,      # Commit hash (if not dry_run)
    "merge": str | None,       # Merge result (if not dry_run)
}
```

**State Transitions** (linear):

```
CHECKOUT_BRANCH → PARSE_SPEC → EXTRACT_DEPS → ENRICH_BEADS
    → CREATE_BEADS → WIRE_DEPS → COMMIT → MERGE → DONE
```

---

## Reused Entities (No Changes)

These existing entities are reused as-is — no modifications needed.

| Entity | Location | Usage |
|--------|----------|-------|
| `WorkflowResult` | `maverick.dsl.results` | Final aggregated result from `execute()` |
| `StepResult` | `maverick.dsl.results` | Per-step result (created by emit helpers) |
| `ProgressEvent` | `maverick.dsl.events` | Union type of all event types |
| `StepStarted` | `maverick.dsl.events` | Emitted by `emit_step_started()` |
| `StepCompleted` | `maverick.dsl.events` | Emitted by `emit_step_completed()` / `emit_step_failed()` |
| `StepOutput` | `maverick.dsl.events` | Emitted by `emit_output()` |
| `WorkflowStarted` | `maverick.dsl.events` | Emitted by `execute()` template method |
| `WorkflowCompleted` | `maverick.dsl.events` | Emitted by `execute()` template method |
| `RollbackStarted` | `maverick.dsl.events` | Emitted during rollback execution |
| `RollbackCompleted` | `maverick.dsl.events` | Emitted after rollback completes |
| `CheckpointSaved` | `maverick.dsl.events` | Emitted by `save_checkpoint()` |
| `StepConfig` | `maverick.dsl.executor.config` | Resolved per-step configuration (import directly from this module, NOT from `maverick.dsl.executor`) |
| `MaverickConfig` | `maverick.config` | Project configuration model |
| `ComponentRegistry` | `maverick.dsl.serialization.registry` | Component dispatch registry |
| `CheckpointStore` | `maverick.dsl.checkpoint.store` | Checkpoint persistence protocol |
| `StepExecutor` | `maverick.dsl.executor.protocol` | Agent step execution protocol |
| `StepType` | `maverick.dsl.types` | Step type enumeration (PYTHON, AGENT, etc.) |

## Relationships

```
PythonWorkflow ──uses──→ MaverickConfig (1:1, injected)
PythonWorkflow ──uses──→ ComponentRegistry (1:1, injected)
PythonWorkflow ──uses──→ CheckpointStore (0..1, optional)
PythonWorkflow ──uses──→ StepExecutor (0..1, optional)
PythonWorkflow ──produces──→ ProgressEvent (1:N, via event queue)
PythonWorkflow ──produces──→ StepResult (1:N, tracked internally)
PythonWorkflow ──produces──→ WorkflowResult (1:1, final output)
PythonWorkflow ──calls──→ resolve_step_config() (N times, per step)

FlyBeadsWorkflow ──calls──→ library.actions.* (many, direct imports)
FlyBeadsWorkflow ──calls──→ StepExecutor.execute() (per agent step)

RefuelSpeckitWorkflow ──calls──→ library.actions.beads.* (direct imports)
RefuelSpeckitWorkflow ──calls──→ StepExecutor.execute() (for enrichment)
```
