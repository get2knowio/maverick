# Research: Remove Dead YAML DSL Infrastructure

**Feature**: 041-remove-yaml-dsl | **Date**: 2026-03-03

## Research Tasks & Findings

### R1: Which DSL modules are actively used by Python workflow code paths?

**Decision**: 8 modules/packages are live and must be extracted.

**Rationale**: Traced every `from maverick.dsl` import in non-DSL source files. Only modules imported by files outside `src/maverick/dsl/` (or `tests/unit/dsl/`) are considered live.

**Live modules** (confirmed by grep of all source imports):

| Module | Active Consumer Files |
|--------|----------------------|
| `dsl/events.py` | `cli/workflow_executor.py`, `workflows/base.py`, `session_journal.py`, `library/actions/preflight.py`, `library/actions/beads.py` |
| `dsl/results.py` | `workflows/base.py`, `cli/workflow_executor.py` (via events rendering) |
| `dsl/types.py` | `workflows/base.py`, `workflows/generate_flight_plan/workflow.py` |
| `dsl/executor/protocol.py` | `workflows/base.py` (TYPE_CHECKING) |
| `dsl/executor/claude.py` | `cli/workflow_executor.py` |
| `dsl/executor/config.py` | `config.py`, `workflows/base.py` |
| `dsl/executor/result.py` | Used transitively via executor |
| `dsl/executor/errors.py` | `workflows/generate_flight_plan/workflow.py`, `workflows/refuel_maverick/workflow.py` |
| `dsl/checkpoint/store.py` | `cli/workflow_executor.py`, `workflows/base.py` |
| `dsl/checkpoint/data.py` | `workflows/base.py` |
| `dsl/serialization/registry/` (6 of 9 files) | `cli/common.py`, `workflows/base.py`, `library/agents/__init__.py`, `library/actions/__init__.py`, `library/generators/__init__.py`, `dsl/executor/claude.py` |

**Dead modules** (only imported within `maverick.dsl/` or by dead tests):
- `context.py` (WorkflowContext) — only used by dead step definitions and serialization executor
- `streaming.py` — only used by dead validate_step handler
- `protocols.py` — only used by dead step definitions (AgentProtocol, GeneratorProtocol)
- `context_builders.py` — only used by dead `register_all_context_builders()` in CLI

**Alternatives considered**: Keeping `WorkflowContext` since it's referenced by type aliases in `types.py`. Rejected because those type aliases (`ContextBuilder`, `Predicate`, `RollbackAction`) are themselves unused by active code — they only serve the dead decorator DSL.

### R2: Which errors in `dsl/errors.py` are used by active code?

**Decision**: 5 errors are live, 6 are dead.

**Rationale**: Searched for each error class across non-DSL source and test code.

**Live errors**:
- `DSLWorkflowError` — Raised by `workflows/base.py` (explicit workflow failure)
- `CheckpointNotFoundError` — Raised by checkpoint store
- `InputMismatchError` — Raised by checkpoint resume logic
- `ReferenceResolutionError` — Raised by registry lookup
- `DuplicateComponentError` — Raised by registry registration

**Dead errors** (only caught/raised within `maverick.dsl/`):
- `WorkflowDefinitionError`, `WorkflowParseError`, `UnsupportedVersionError` — YAML parsing only
- `WorkflowExecutionError` — YAML execution only
- `WorkflowSerializationError` — alias for dead base class
- `LoopStepExecutionError` — YAML loop handler only

### R3: Which registry components are dead?

**Decision**: `WorkflowRegistry` and `ContextBuilderRegistry` are dead. `ActionRegistry`, `AgentRegistry`, `GeneratorRegistry` are live.

**Rationale**: `WorkflowRegistry` is only populated by the dead discovery system (`load_workflows_into_registry`). `ContextBuilderRegistry` is only populated by the dead `register_all_context_builders()`. Neither is accessed during Python workflow execution.

`ComponentRegistry.workflows` and `ComponentRegistry.context_builders` attributes should be removed entirely.

### R4: Which CLI functions are dead?

**Decision**: 4 functions are dead, plus several imports.

**Rationale**: Traced call sites for each function.

- `execute_workflow_run()` in `workflow_executor.py` — defined but never called by any Click command. All commands use `execute_python_workflow()` instead.
- `format_workflow_not_found_error()` in `workflow_executor.py` — only called by dead `execute_workflow_run`.
- `execute_dsl_workflow()` in `helpers.py` — exported in `__all__` but never imported elsewhere.
- `get_discovery_result()` in `common.py` — only called by dead `execute_workflow_run`.

### R5: Is `library/builtins.py` dead?

**Decision**: Partially dead. The YAML-loading methods (`get_workflow`, `get_fragment` that call `parse_workflow`) are dead. The metadata constants and info classes may be dead too.

**Rationale**: `BuiltinWorkflowLibrary` class is never imported or instantiated by any active code. The `get_workflow()` and `get_fragment()` methods call dead `parse_workflow()`. The workflow/fragment metadata (names, descriptions, input schemas) was used by the dead discovery system.

Need to verify during implementation whether `BUILTIN_WORKFLOWS`, `BUILTIN_FRAGMENTS` constants, or the info classes are referenced by any active code. If not, the entire file can be simplified or removed.

### R6: Is the `lark` dependency only used by dead code?

**Decision**: Yes, confirmed.

**Rationale**: `grep -r "import lark\|from lark" src/` only matches `src/maverick/dsl/expressions/parser.py`. The expression parser is exclusively used by the dead YAML serialization executor's condition evaluation and expression resolution. No active Python workflow code path touches it.

### R7: Is `dsl/prerequisites/` dead?

**Decision**: Need to verify. Prerequisites checking is used by `FlyBeadsWorkflow` but may be reimplemented in the Python workflow.

**Rationale**: `FlyBeadsWorkflow` has a preflight step that checks API, git, jj, bd availability. This may call into the prerequisites system. Need to trace during implementation whether it uses `dsl/prerequisites/` or has its own implementation.

**Update after further investigation**: The `FlyBeadsWorkflow._run_preflight()` method in `workflows/fly_beads/workflow.py` calls `library/actions/preflight.py` which uses its own implementation with events. The `dsl/prerequisites/` package is only used by the dead `WorkflowFileExecutor` preflight feature. Dead.

### R8: What about `dsl/serialization/executor/handlers/` step_path.py test?

**Decision**: `test_step_path.py` (153 LOC) in `tests/unit/dsl/executor/` tests `dsl/serialization/executor/step_path.py` which is dead (part of the YAML execution engine). Despite being in the same directory as live executor tests, this test file is dead and should be deleted, not moved.

**Rationale**: `step_path.py` provides `make_prefix_callback` which is used to attribute events to nested steps in the YAML executor. The Python workflow base class handles event attribution directly.
