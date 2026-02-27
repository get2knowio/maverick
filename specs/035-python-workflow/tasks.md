# Tasks: Python-Native Workflow Definitions

**Input**: Design documents from `/specs/035-python-workflow/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Included per Constitution Principle IV (Test-First) and FR-010 (directly testable with standard pytest patterns).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story. US2 (Step Config Resolution) and US3 (Progress Events) are addressed in the Foundational phase because the PythonWorkflow ABC is a blocking prerequisite for all concrete workflow stories.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Source**: `src/maverick/` at repository root
- **Tests**: `tests/unit/` at repository root

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create package directories, __init__.py files, and step name constants for the new workflow packages.

- [X] T001 Create package directories and __init__.py files for `src/maverick/workflows/fly_beads/`, `src/maverick/workflows/refuel_speckit/`, and verify `tests/unit/workflows/__init__.py` exists
- [X] T002 [P] Create step name constants (PREFLIGHT, CREATE_WORKSPACE, SELECT_BEAD, IMPLEMENT, SYNC_DEPS, VALIDATE, REVIEW, COMMIT) and default config values (MAX_BEADS=30, WORKFLOW_NAME="fly-beads") in `src/maverick/workflows/fly_beads/constants.py`
- [X] T003 [P] Create step name constants (CHECKOUT, PARSE_SPEC, EXTRACT_DEPS, ENRICH_BEADS, CREATE_BEADS, WIRE_DEPS, COMMIT, MERGE) and default config values (WORKFLOW_NAME="refuel-speckit") in `src/maverick/workflows/refuel_speckit/constants.py`

---

## Phase 2: Foundational (PythonWorkflow ABC — Blocking Prerequisite)

**Purpose**: Implement the PythonWorkflow abstract base class with all infrastructure features: event emission (US3), step config resolution (US2), rollback, and checkpointing. This MUST be complete before any concrete workflow can be implemented.

**Covers**: US2 (Step Config Resolution) + US3 (Progress Events) — these are features of the ABC itself, not standalone deliverables.

**⚠️ CRITICAL**: No concrete workflow implementation (US1) can begin until this phase is complete.

### Tests (write FIRST — must FAIL before implementation)

- [X] T004 Create shared test fixtures (mock MaverickConfig with steps overrides, mock ComponentRegistry, MemoryCheckpointStore, mock StepExecutor, concrete PythonWorkflow test subclass) in `tests/unit/workflows/conftest.py`
- [X] T005 Write tests for PythonWorkflow ABC covering: constructor validation (config/registry required), event queue initialization, emit_step_started/emit_step_completed/emit_step_failed/emit_output behavior, execute() template method (yields WorkflowStarted then step events then WorkflowCompleted), step result tracking (StepResult creation with duration), resolve_step_config() delegation with defaults and overrides, register_rollback() reverse-order execution on failure, save_checkpoint()/load_checkpoint() delegation, cancellation handling (asyncio.CancelledError triggers rollback) in `tests/unit/workflows/test_python_workflow_base.py`

### Implementation

- [X] T006 Implement PythonWorkflow ABC constructor (config, registry, checkpoint_store, step_executor, workflow_name), define `PythonRollbackAction = Callable[[], Awaitable[None]]` type alias (do NOT reuse DSL's `RollbackAction` which requires `WorkflowContext`), internal state (_event_queue as asyncio.Queue[ProgressEvent | None], _step_results list, _step_start_times dict, _current_step, _rollback_stack as list of (name, PythonRollbackAction) tuples, result: WorkflowResult | None), and emit_step_started/emit_step_completed/emit_step_failed/emit_output helpers that push StepStarted/StepCompleted/StepOutput events to the queue. Set step_path to `{workflow_name}.{step_name}` on all events. Import StepConfig from `maverick.dsl.executor.config` (NOT from `maverick.dsl.executor`). In `src/maverick/workflows/base.py`
- [X] T007 Implement execute() template method: emit WorkflowStarted, run _run(inputs) as asyncio.Task, yield ProgressEvents from queue, on _run completion aggregate WorkflowResult into self.result then emit WorkflowCompleted (note: WorkflowCompleted does NOT embed WorkflowResult — it only has workflow_name/success/total_duration_ms/timestamp; the result is stored on self.result for callers to access after iteration), on exception emit StepFailed for current step then execute rollbacks in reverse order then emit WorkflowCompleted(success=False) and store failure result in self.result, on CancelledError same cleanup then re-raise in `src/maverick/workflows/base.py`
- [X] T008 Implement resolve_step_config(step_name, step_type) delegating to maverick.dsl.executor.config.resolve_step_config() with inline_config=None, project_step_config=self.config.steps.get(step_name), agent_config=None, global_model=self.config.model, step_type defaulting to StepType.PYTHON in `src/maverick/workflows/base.py`
- [X] T009 Implement register_rollback(name, action) appending (name, PythonRollbackAction) tuple to _rollback_stack, save_checkpoint(data) delegating to checkpoint_store.save(self._workflow_name, data) and emitting CheckpointSaved(step_name=self._current_step or "checkpoint", workflow_id=self._workflow_name) event, load_checkpoint() delegating to checkpoint_store.load_latest(self._workflow_name), and step result tracking (create StepResult via factory methods StepResult.create_success/create_failure in emit_step_completed/emit_step_failed, append to _step_results) in `src/maverick/workflows/base.py`

**Checkpoint**: PythonWorkflow ABC complete — all T005 tests pass. Config resolution (US2) and event emission (US3) independently testable.

---

## Phase 3: User Story 1 — Opinionated Workflows Defined in Python (Priority: P1) 🎯 MVP

**Goal**: Implement concrete FlyBeadsWorkflow and RefuelSpeckitWorkflow classes that replicate the behavior of their YAML counterparts using native Python control flow.

**Independent Test**: Instantiate each workflow with mock dependencies, call execute() with test inputs, collect yielded ProgressEvents, assert WorkflowCompleted contains expected WorkflowResult with step results and final output.

### Tests (write FIRST — must FAIL before implementation)

- [X] T010 [P] [US1] Write tests for FlyBeadsWorkflow covering: happy path (preflight → workspace → bead loop → summary), bead failure with jj restore rollback, workspace-level rollback on unhandled exception, checkpoint save after each bead and resume skipping completed beads, dry-run mode (no side effects), skip-review mode, max_beads limit, epic_id filtering in `tests/unit/workflows/test_fly_beads_workflow.py`
- [X] T011 [P] [US1] Write tests for RefuelSpeckitWorkflow covering: happy path (checkout → parse → extract deps → enrich → create beads → wire deps → commit → merge), parse error handling, dry-run mode (preview bead definitions without creating), empty tasks.md handling in `tests/unit/workflows/test_refuel_speckit_workflow.py`

### Implementation

- [X] T012 [P] [US1] Implement FlyBeadsWorkflow._run() with: preflight checks (run_preflight_checks action), workspace creation (create_fly_workspace action + register_rollback for teardown), bead loop (select_next_bead → jj_snapshot_operation → implement via step_executor → sync_deps → validate_and_fix → review_and_fix → jj_commit_bead, with save_checkpoint after each bead), per-bead rollback on failure (jj_restore_operation), summary output in `src/maverick/workflows/fly_beads/workflow.py`
- [X] T013 [P] [US1] Implement RefuelSpeckitWorkflow._run() with: checkout spec branch, parse tasks.md, extract dependencies (agent step via step_executor), enrich beads (agent step), create beads via bd CLI actions, wire dependencies, commit, merge spec branch, return summary output in `src/maverick/workflows/refuel_speckit/workflow.py`

**Checkpoint**: Both concrete workflows pass all tests. FlyBeadsWorkflow and RefuelSpeckitWorkflow are fully functional as Python classes with mock dependencies.

---

## Phase 4: User Story 5 — CLI Commands Route to Python Workflows (Priority: P2)

**Goal**: CLI commands (`maverick fly`, `maverick refuel speckit`) instantiate Python workflow classes directly instead of discovering YAML files. Event rendering is shared between YAML and Python execution paths.

**Independent Test**: Invoke CLI command with test arguments, verify correct Python workflow class is instantiated with resolved MaverickConfig, and events are rendered identically to YAML workflow output.

### Implementation

- [X] T014 [US5] Extract render_workflow_events(events, console, session_journal) as shared async function from the inline event dispatch loop (~lines 303-469) in execute_workflow_run(). IMPORTANT: The current loop does NOT handle StepOutput events — add StepOutput rendering (format by level: info/success/warning/error) to the extracted function since Python workflows depend on emit_output(). Update execute_workflow_run() to call the extracted function in `src/maverick/cli/workflow_executor.py`
- [X] T015 [US5] Implement PythonWorkflowRunConfig dataclass (workflow_class, inputs, session_log_path, restart) and execute_python_workflow(ctx, run_config) that creates MaverickConfig/ComponentRegistry/FileCheckpointStore/StepExecutor, instantiates workflow, calls execute(inputs), passes events to render_workflow_events(), accesses workflow.result after iteration for the final WorkflowResult, handles session journal recording in `src/maverick/cli/workflow_executor.py`
- [X] T016 [P] [US5] Modify fly command to import FlyBeadsWorkflow, build PythonWorkflowRunConfig with CLI options (epic, max_beads, dry_run, skip_review), and call execute_python_workflow() instead of execute_workflow_run() in `src/maverick/cli/commands/fly/_group.py`
- [X] T017 [P] [US5] Modify refuel speckit command to import RefuelSpeckitWorkflow, build PythonWorkflowRunConfig with CLI arguments (spec, dry_run), and call execute_python_workflow() instead of execute_workflow_run() in `src/maverick/cli/commands/refuel/speckit.py`
- [X] T018 [US5] Update re-exports: add PythonWorkflow, FlyBeadsWorkflow, RefuelSpeckitWorkflow to __all__ and import them from their packages in `src/maverick/workflows/__init__.py`

**Checkpoint**: `maverick fly` and `maverick refuel speckit` execute Python workflows. CLI output is identical to previous YAML-based execution.

---

## Phase 5: User Story 4 — YAML Workflows Remain Functional (Priority: P2)

**Goal**: Verify that existing YAML workflows (user-authored in `.maverick/workflows/` and `~/.config/maverick/workflows/`) continue to be discovered and executed without modification via WorkflowFileExecutor.

**Independent Test**: Run existing YAML workflows through WorkflowFileExecutor after Python workflow infrastructure is added, verifying identical behavior.

- [X] T019 [US4] Write regression tests verifying: YAML workflow discovery still finds workflows in .maverick/workflows/ and ~/.config/maverick/workflows/, WorkflowFileExecutor still executes YAML workflows with correct event emission, execute_workflow_run() still works for non-opinionated workflow names, built-in YAML files (fly-beads.yaml, refuel-speckit.yaml) still exist in src/maverick/library/workflows/ for reference in `tests/unit/workflows/test_yaml_backward_compat.py`

**Checkpoint**: All YAML workflow functionality verified. No regressions from Python workflow infrastructure addition.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final validation across all stories and cleanup.

- [X] T020 Run `make check` (lint, typecheck, test) and fix all failures across all new and modified files
- [X] T021 Validate quickstart.md scenarios: create a minimal PythonWorkflow subclass per quickstart instructions, verify it executes correctly with mock dependencies, verify all code examples in quickstart.md are accurate

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Foundational (ABC must be complete)
- **US5 (Phase 4)**: Depends on US1 (workflows must exist to route to)
- **US4 (Phase 5)**: Can start after Foundational — independent of US1/US5
- **Polish (Phase 6)**: Depends on all phases being complete

### User Story Dependencies

- **US2 (Step Config) + US3 (Progress Events)**: Addressed in Foundational phase — no dependencies on other stories
- **US1 (Concrete Workflows)**: Depends on Foundational (US2+US3 features of ABC)
- **US5 (CLI Integration)**: Depends on US1 (needs workflow classes to instantiate)
- **US4 (YAML Compat)**: Independent — can run in parallel with US1/US5 after Foundational

### Within Each Phase

- Tests MUST be written and FAIL before implementation (TDD)
- Sequential tasks in same file: T006 → T007 → T008 → T009 (all in base.py)
- Parallel tasks in different files: T002‖T003, T010‖T011, T012‖T013, T016‖T017

### Parallel Opportunities

- **Phase 1**: T002 and T003 can run in parallel (different files)
- **Phase 2**: T004 and T005 can run in parallel (conftest.py and test file). T006-T009 are sequential (same file, incremental).
- **Phase 3**: T010‖T011 (parallel test writing). T012‖T013 (parallel implementation, different packages).
- **Phase 4**: T016‖T017 (parallel CLI modifications, different files). T014 → T015 sequential (extract then build on extracted function).
- **Phase 5**: Single task, no parallelism needed.
- **US1 and US4 can proceed in parallel** after Foundational phase completes.

---

## Parallel Example: Phase 3 (US1)

```bash
# Launch both test files in parallel (different files, no dependencies):
Task: "Write tests for FlyBeadsWorkflow in tests/unit/workflows/test_fly_beads_workflow.py"
Task: "Write tests for RefuelSpeckitWorkflow in tests/unit/workflows/test_refuel_speckit_workflow.py"

# After tests written, launch both implementations in parallel:
Task: "Implement FlyBeadsWorkflow._run() in src/maverick/workflows/fly_beads/workflow.py"
Task: "Implement RefuelSpeckitWorkflow._run() in src/maverick/workflows/refuel_speckit/workflow.py"
```

---

## Implementation Strategy

### MVP First (Foundational + US1 Only)

1. Complete Phase 1: Setup (package structure)
2. Complete Phase 2: Foundational (PythonWorkflow ABC with US2+US3 features)
3. Complete Phase 3: US1 (FlyBeadsWorkflow + RefuelSpeckitWorkflow)
4. **STOP and VALIDATE**: Both workflows pass all tests with mock dependencies
5. This delivers the core value proposition: Python-native workflow definitions with full IDE support

### Incremental Delivery

1. Setup + Foundational → PythonWorkflow ABC ready, config resolution and event emission verified
2. Add US1 → Concrete workflows tested in isolation → MVP complete
3. Add US5 → CLI commands route to Python workflows → End-to-end functional
4. Add US4 → YAML backward compatibility verified → No regressions
5. Polish → All checks pass, quickstart validated → Release ready

### Key Implementation Notes

- **RollbackAction type**: The existing `RollbackAction` in `dsl/types.py` takes `WorkflowContext`, which Python workflows don't have. Define `PythonRollbackAction = Callable[[], Awaitable[None]]` in `base.py`. Do NOT reuse the DSL's `RollbackAction`.
- **WorkflowResult communication**: `WorkflowCompleted` event does NOT embed a `WorkflowResult`. The `execute()` template stores the aggregated result as `self.result`. Callers access `workflow.result` after iterating the generator.
- **step_path field**: YAML events use `step_path` for nested paths (e.g., `workflow.step`). Python workflow events should set `step_path` to `{workflow_name}.{step_name}` for consistency.
- **Event rendering extraction (T014)**: The inline event dispatch in `workflow_executor.py` (~lines 303-469) does NOT handle `StepOutput`, `LoopIteration*`, or `CheckpointSaved` events. The extracted `render_workflow_events()` MUST add `StepOutput` handling at minimum since Python workflows depend on `emit_output()`. Test before and after to verify.
- **StepConfig import path**: `StepConfig` is NOT exported from `maverick.dsl.executor.__init__` — only the alias `StepExecutorConfig` is. Import directly from `maverick.dsl.executor.config`.
- **Action imports**: FlyBeadsWorkflow and RefuelSpeckitWorkflow import action functions directly (e.g., `from maverick.library.actions.preflight import run_preflight_checks`) for type safety, while using `self.registry` only for dynamic dispatch (agent lookup).

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verify tests fail before implementing (TDD)
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- US2 and US3 are addressed in Phase 2 (Foundational) because they are features of the PythonWorkflow ABC itself, which is a blocking prerequisite for all concrete workflow stories
