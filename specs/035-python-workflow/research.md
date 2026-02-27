# Research: Python-Native Workflow Definitions

**Feature Branch**: `035-python-workflow`
**Date**: 2026-02-26

## R-001: PythonWorkflow Base Class — Event Emission Pattern

**Context**: `PythonWorkflow.execute()` must return `AsyncGenerator[ProgressEvent, None]`. The workflow author calls helper methods like `emit_step_started()` to emit events. How do these helpers make events available to the generator?

**Decision**: Internal `asyncio.Queue` — helpers push events; `execute()` wrapper yields them.

**Rationale**: The `WorkflowFileExecutor` already uses an `asyncio.Queue` to bridge handler background tasks with the event-yielding generator (see `executor.py` lines 407-440). This pattern is proven in the codebase. The base class `execute()` template method:
1. Calls the subclass's `_run(inputs)` coroutine in a background task
2. Yields events from the queue as they arrive
3. On completion, yields `WorkflowCompleted` with the aggregated `WorkflowResult`

This avoids requiring subclasses to manage the generator protocol themselves — they just call `await self.emit_step_started("name")` and the base class handles the rest.

**Alternatives considered**:
- **Direct generator in subclass**: Subclass `execute()` directly yields events. Rejected because it forces workflow authors to interleave `yield` statements with business logic, making code harder to read and test. Also makes step tracking error-prone (authors must remember to track results manually).
- **Callback-based**: Pass an `event_callback` to `execute()`. Rejected because the spec mandates `AsyncGenerator` return type (FR-001), and callbacks would require a separate mechanism to collect the final `WorkflowResult`.

---

## R-002: PythonWorkflow — Step Result Tracking

**Context**: `PythonWorkflow` must track step results and produce a `WorkflowResult` upon completion (FR-005). How should step results be accumulated?

**Decision**: The base class maintains `_step_results: list[StepResult]` and `_step_start_times: dict[str, float]`. The `emit_step_started()` records the start time; `emit_step_completed()` creates a `StepResult` and appends it. `emit_step_failed()` creates a failure `StepResult`. The final `WorkflowResult` aggregates these.

**Rationale**: This mirrors how `WorkflowFileExecutor` builds its result (via `WorkflowContext.results`). Reusing `StepResult` and `WorkflowResult` ensures type compatibility with the CLI renderer and session journal.

**Alternatives considered**:
- **Reuse `WorkflowContext` directly**: Rejected because `WorkflowContext` carries DSL-specific concerns (expression evaluation, iteration context) that don't apply to Python workflows. A lighter internal tracking mechanism is simpler.
- **Return `WorkflowResult` from `_run()`**: Rejected because step tracking should be automatic via the emit helpers, not manual.

---

## R-003: PythonWorkflow — ComponentRegistry vs Direct Imports

**Context**: Spec clarification says "Registry for runtime dispatch + direct imports for type safety and IDE navigation" (A-002). How do Python workflows access actions?

**Decision**: Python workflows receive `ComponentRegistry` at construction. For type-safe action invocation, workflow code imports action functions directly and calls them. The registry is available via `self.registry` for dynamic dispatch when needed (e.g., looking up agents by name for `StepExecutor`).

**Rationale**: Direct imports give full IDE support (autocompletion, go-to-definition, type checking) — the primary motivation for Python workflows. The registry remains available for cases where dynamic lookup is needed (agent dispatch, user-configured component overrides).

**Alternatives considered**:
- **Registry-only**: All action calls go through `self.registry.actions.get("name")`. Rejected because it loses type safety and IDE navigation — the exact problem Python workflows solve.
- **No registry**: Remove registry dependency entirely. Rejected because agent dispatch and dynamic component resolution still need it (e.g., `StepExecutor` looks up agents by name).

---

## R-004: CLI Integration — Direct Instantiation vs Discovery

**Context**: CLI commands must instantiate Python workflows directly (FR-008). How does this interact with the existing workflow discovery system?

**Decision**: CLI commands for opinionated workflows (`fly`, `refuel speckit`) directly import and instantiate the Python workflow class. They bypass workflow discovery entirely. A new `execute_python_workflow()` helper in `workflow_executor.py` consumes the async generator and renders events using the same Rich output logic. YAML discovery remains untouched for user-authored workflows.

**Rationale**: Direct instantiation is simpler, faster, and provides compile-time verification that the workflow class exists. Discovery was designed for user-authored YAML workflows that live in configurable locations — opinionated workflows have a fixed location in source code.

**Alternatives considered**:
- **Register Python workflows in discovery**: Add a `PythonWorkflowSource` to the discovery system. Rejected because it adds indirection without benefit — opinionated workflows are always known at compile time.
- **Hybrid**: Use discovery but prefer Python over YAML. Rejected as unnecessarily complex precedence logic.

---

## R-005: PythonWorkflow — StepExecutor Integration

**Context**: Agent steps in Python workflows need `StepExecutor` for Claude SDK interactions. How is this provided?

**Decision**: `PythonWorkflow` accepts an optional `StepExecutor` at construction time (injectable for testing). The base class provides `self.step_executor` for subclasses to use when calling agent steps. The CLI creates a `ClaudeStepExecutor` and passes it when instantiating the workflow — same as `WorkflowFileExecutor` does in `create_execution_context()`.

**Rationale**: Follows the dependency injection principle (Constitution III). The `StepExecutor` protocol (Spec 032) is provider-agnostic, so tests can mock it without Claude SDK dependencies.

**Alternatives considered**:
- **Create `StepExecutor` inside `PythonWorkflow`**: Rejected because it violates DI and makes testing harder.
- **Pass `StepExecutor` to `execute()`**: Rejected because the executor is a workflow-level dependency, not a per-execution parameter.

---

## R-006: PythonWorkflow — StepConfig Resolution

**Context**: Python workflows need `resolve_step_config(step_name)` (FR-003). How does this work without the 4-layer YAML executor infrastructure?

**Decision**: `PythonWorkflow.resolve_step_config(step_name)` calls the existing `resolve_step_config()` function from `maverick.dsl.executor.config` with:
- `inline_config=None` (Python workflows don't have YAML inline config)
- `project_step_config=self.config.steps.get(step_name)` (from `MaverickConfig`)
- `agent_config=None` (resolved separately when dispatching agent steps)
- `global_model=self.config.model` (from `MaverickConfig`)
- `step_type` inferred from context or explicitly passed

**Rationale**: Reuses the exact same resolution function, ensuring identical behavior between YAML and Python workflows. The only difference is that inline config (YAML `config:` field) is always `None` for Python workflows — configuration is in `maverick.yaml`.

**Alternatives considered**:
- **Custom resolution logic**: Rejected because it would diverge from YAML behavior and duplicate code.
- **Add inline config support**: Allow `resolve_step_config(step_name, overrides={...})` for programmatic overrides. Considered future enhancement but not needed for MVP.

---

## R-007: PythonWorkflow — Checkpoint Strategy

**Context**: Python workflows must checkpoint at per-bead granularity (FR-012, clarification). How do checkpoints work without the YAML executor's automatic step-based checkpointing?

**Decision**: `PythonWorkflow` provides `save_checkpoint(checkpoint_id, data)` and `load_checkpoint()` helper methods that delegate to `CheckpointStore`. The `FlyBeadsWorkflow` calls `save_checkpoint()` after each bead completes successfully. On resume, `load_checkpoint()` returns the last saved state, and the workflow skips already-completed beads.

Checkpoint data is a dict containing:
- `completed_bead_ids: list[str]` — beads already processed
- `workspace_path: str` — workspace location for resume
- `epic_id: str` — current epic context

**Rationale**: Per-bead checkpointing is coarser than per-step (the YAML executor checkpoints per-step), but matches the spec requirement and the natural granularity of the fly-beads workflow. The bead loop is the outermost unit of work — partial bead state is not useful since failed beads are rolled back.

**Alternatives considered**:
- **Per-step checkpointing**: Checkpoint after every step within each bead iteration. Rejected because it's unnecessary complexity — if a step fails mid-bead, the bead is rolled back (jj restore) and retried from scratch.
- **No checkpointing**: Rely on bead status (via `bd` CLI) for resume. Rejected because workspace state would be lost on crash.

---

## R-008: PythonWorkflow — Rollback Strategy

**Context**: Python workflows support workspace-level rollback (FR-011, clarification). How do rollbacks work?

**Decision**: `PythonWorkflow` provides `register_rollback(name, action)` where `action` is an async callable. Rollbacks are stored in a stack. On unhandled exception or cancellation (`asyncio.CancelledError`), the base class executes rollbacks in reverse order, emitting `RollbackStarted`/`RollbackCompleted` events.

For `FlyBeadsWorkflow`, the primary rollback is workspace teardown:
```python
self.register_rollback("workspace_teardown", workspace_manager.teardown)
```

Within the bead loop, per-bead rollback uses jj operation restore (not the rollback stack):
```python
await jj_restore_operation(snapshot_id, cwd=workspace_path)
```

**Rationale**: Two-tier rollback matches the YAML workflow behavior: workspace-level rollback on workflow failure, jj operation restore on per-bead failure. The rollback stack handles workflow-level cleanup; jj handles bead-level undo.

**Alternatives considered**:
- **Single rollback mechanism**: Use the stack for both levels. Rejected because per-bead jj restores are not "rollbacks" in the workflow sense — they're part of the normal bead loop control flow.

---

## R-009: CLI `execute_python_workflow()` — Event Rendering

**Context**: The CLI currently uses `execute_workflow_run()` which tightly couples YAML discovery, `WorkflowFileExecutor`, and event rendering. How do Python workflows plug in?

**Decision**: Extract the event rendering logic from `execute_workflow_run()` into a shared `render_workflow_events()` function. Create a new `execute_python_workflow()` function that:
1. Instantiates the Python workflow class with config, registry, checkpoint store, step executor
2. Calls `workflow.execute(inputs)`
3. Passes events to `render_workflow_events()` (shared with YAML path)
4. Handles session journal recording

The fly and refuel CLI commands call `execute_python_workflow()` instead of `execute_workflow_run()`.

**Rationale**: Sharing the rendering logic ensures identical CLI output. The Python workflow path is simpler (no discovery, no YAML parsing, no semantic validation) but produces the same user-visible output.

**Alternatives considered**:
- **Wrap Python workflow in `WorkflowFile`**: Create a YAML-compatible wrapper. Rejected as unnecessary indirection that defeats the purpose of Python workflows.
- **Duplicate rendering logic**: Copy the event rendering into a new function. Rejected due to DRY principle.

---

## R-010: YAML Workflow Backward Compatibility

**Context**: Existing YAML workflows must continue to function (FR-009). What changes (if any) affect the YAML path?

**Decision**: Zero changes to the YAML execution path. `WorkflowFileExecutor`, `WorkflowFile`, all step handlers, the discovery system, and `execute_workflow_run()` remain exactly as they are. The built-in YAML files (`fly-beads.yaml`, `refuel-speckit.yaml`) remain in `src/maverick/library/workflows/` for reference but are no longer the primary execution path for CLI commands.

User-authored YAML workflows in `.maverick/workflows/` and `~/.config/maverick/workflows/` continue to be discovered and executed via `WorkflowFileExecutor`.

**Rationale**: Minimizing changes to the YAML path eliminates regression risk. The Python workflow infrastructure is additive — it doesn't modify existing code paths.

**Alternatives considered**:
- **Remove YAML workflows**: Delete the YAML files. Rejected because users may have extended them, and they serve as reference documentation.
- **Deprecation warnings**: Emit warnings when YAML opinionated workflows are used. Rejected as premature — YAML is still the path for user-authored workflows.

---

## R-011: PythonWorkflow — `_run()` vs `execute()` Method Design

**Context**: How should the subclass implement its workflow logic?

**Decision**: The base class defines `execute()` as a final method (the async generator that yields events). Subclasses implement `async def _run(self, inputs: dict[str, Any]) -> Any` which contains the workflow business logic. The `_run()` method uses `self.emit_*()` helpers to emit events and returns the final output value.

```python
class PythonWorkflow(ABC):
    async def execute(self, inputs: dict[str, Any]) -> AsyncGenerator[ProgressEvent, None]:
        """Final method — manages event queue and result aggregation."""
        ...  # Template method pattern

    @abstractmethod
    async def _run(self, inputs: dict[str, Any]) -> Any:
        """Subclasses implement workflow logic here."""
        ...
```

**Rationale**: Template method pattern keeps the complex generator/queue/result-aggregation logic in the base class. Subclass authors focus purely on business logic. This also makes the `WorkflowCompleted` event emission automatic — subclass authors can't forget it.

**Alternatives considered**:
- **Subclass implements `execute()` directly**: Forces authors to manage the generator protocol. Rejected for complexity.
- **Decorator-based**: Wrap `_run()` with a decorator. Rejected as less discoverable than a clear abstract method.

---

## R-012: PythonWorkflow — Error Handling in `_run()`

**Context**: What happens when `_run()` raises an unhandled exception?

**Decision**: The base class `execute()` wraps the `_run()` call in try/except. On exception:
1. Emit `StepFailed` if a step was in progress (step_started but no step_completed)
2. Execute rollbacks in reverse order (emitting rollback events)
3. Emit `WorkflowCompleted` with `success=False` and the error
4. Re-raise the exception after all events are yielded

On `asyncio.CancelledError`:
1. Same as above but with a cancellation-specific error message
2. Re-raise `CancelledError` after cleanup

**Rationale**: Mirrors the `WorkflowFileExecutor` behavior (executor.py lines 596-629). The rollback/event emission ensures the CLI sees proper lifecycle events even on failure. Re-raising ensures the caller knows the workflow failed.

**Alternatives considered**:
- **Swallow exceptions**: Return `WorkflowResult(success=False)` without re-raising. Rejected because the CLI needs to distinguish between "workflow completed with failures" and "workflow crashed."
