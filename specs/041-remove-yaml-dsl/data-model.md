# Data Model: Remove Dead YAML DSL Infrastructure

**Feature**: 041-remove-yaml-dsl | **Date**: 2026-03-03

## Entity Mapping (Old → New Locations)

This document defines the complete import mapping for the extraction. Each entry specifies the source file, destination, and any transformations required.

### Module: `maverick.types` (new)

**Source**: `src/maverick/dsl/types.py` (81 LOC)

**Entities to keep**:
```python
class StepType(str, Enum):      # PYTHON, AGENT, GENERATE, VALIDATE, etc.
class StepMode(str, Enum):       # DETERMINISTIC, AGENT
class AutonomyLevel(str, Enum):  # OPERATOR, COLLABORATOR, CONSULTANT, APPROVER
```

**Entities to remove** (dead type aliases, depend on dead `WorkflowContext`):
```python
ContextBuilder = Callable[[WorkflowContext], Awaitable[dict[str, Any]]]  # REMOVE
Predicate = Callable[[WorkflowContext], bool | Awaitable[bool]]          # REMOVE
RollbackAction = Callable[[WorkflowContext], None | Awaitable[None]]     # REMOVE
```

**Internal imports to update**: Remove `from maverick.dsl.context import WorkflowContext` (TYPE_CHECKING).

---

### Module: `maverick.constants` (new)

**Source**: `src/maverick/dsl/config.py` (119 LOC)

**Transformation**: Unwrap `DSLDefaults` frozen dataclass into module-level constants.

```python
# Old: DEFAULTS.CHECKPOINT_DIR
# New: CHECKPOINT_DIR

CHECKPOINT_DIR: str = ".maverick/checkpoints"
COMMAND_TIMEOUT: float = 30.0
DEFAULT_RETRY_ATTEMPTS: int = 3
DEFAULT_RETRY_DELAY: float = 1.0
RETRY_BACKOFF_MAX: float = 60.0
RETRY_JITTER_MIN: float = 0.5
MAX_STEP_OUTPUT_SIZE: int = 10_000
MAX_CONTEXT_SIZE: int = 50_000
```

**Dead constants** (do not extract):
- `ASCII_DIAGRAM_WIDTH`, `ASCII_DIAGRAM_BORDER_WIDTH`, `ASCII_DIAGRAM_PADDING` — visualization only
- `PROJECT_STRUCTURE_MAX_DEPTH` — context builders only (verify during implementation)
- `DEFAULT_ISSUE_LIMIT`, `DEFAULT_RECENT_COMMIT_LIMIT` — context builders only (verify)

---

### Module: `maverick.events` (new)

**Source**: `src/maverick/dsl/events.py` (518 LOC)

**All entities preserved** (no removals):
```python
@dataclass(frozen=True)
class WorkflowStarted / WorkflowCompleted
class StepStarted / StepCompleted
class StepOutput                    # Generic step output with level
class OutputLevel(str, Enum)        # INFO, SUCCESS, WARNING, ERROR
class AgentStreamChunk              # Streaming output/thinking/error
class CheckpointSaved
class RollbackStarted / RollbackCompleted
class LoopIterationStarted / LoopIterationCompleted / LoopConditionChecked
class ValidationStarted / ValidationCompleted / ValidationFailed
class PreflightStarted / PreflightCheckPassed / PreflightCheckFailed / PreflightCompleted

ProgressEvent = Union[...]          # Type alias for all event types
```

**Internal imports to update**:
- `from maverick.dsl.types import StepType` → `from maverick.types import StepType`

---

### Module: `maverick.results` (new)

**Source**: `src/maverick/dsl/results.py` (371 LOC)

**All entities preserved**:
```python
@dataclass(frozen=True)
class StepResult         # name, step_type, success, output, duration_ms, error
class WorkflowResult     # workflow_name, success, step_results, total_duration_ms
class BranchResult       # selected_option, output
class ParallelResult     # results (tuple of StepResult)
class SubWorkflowInvocationResult  # workflow_name, output
class RollbackError      # step_name, error
class SkipMarker         # reason
```

**Internal imports to update**:
- `from maverick.dsl.types import StepType` → `from maverick.types import StepType`

---

### Package: `maverick.executor` (new)

**Source**: `src/maverick/dsl/executor/` (1,181 LOC across 6 files)

| File | Entities | Internal Import Updates |
|------|----------|----------------------|
| `__init__.py` | Exports `StepExecutor`, `ClaudeStepExecutor` | Update from-imports |
| `protocol.py` (85 LOC) | `StepExecutor` Protocol, `EventCallback` type alias | `maverick.executor.config.StepConfig`, `maverick.executor.result.ExecutorResult` |
| `claude.py` (521 LOC) | `ClaudeStepExecutor` class | `maverick.events.*`, `maverick.executor.config.*`, `maverick.executor.result.*`, `maverick.registry.ComponentRegistry` |
| `config.py` (433 LOC) | `StepConfig` (Pydantic), `RetryPolicy`, `resolve_step_config()` | `maverick.types.StepMode`, `maverick.types.AutonomyLevel` |
| `result.py` (69 LOC) | `ExecutorResult`, `UsageMetadata` dataclasses | `maverick.events.AgentStreamChunk` |
| `errors.py` (35 LOC) | `ExecutorError`, `OutputSchemaValidationError` | `maverick.exceptions.MaverickError` (already correct) |

---

### Package: `maverick.checkpoint` (new)

**Source**: `src/maverick/dsl/checkpoint/` (333 LOC across 3 files)

| File | Entities | Internal Import Updates |
|------|----------|----------------------|
| `__init__.py` | Re-exports | Update from-imports |
| `store.py` (224 LOC) | `CheckpointStore` Protocol, `FileCheckpointStore`, `MemoryCheckpointStore` | `maverick.constants.CHECKPOINT_DIR` (was `DEFAULTS.CHECKPOINT_DIR`) |
| `data.py` (87 LOC) | `CheckpointData`, `compute_inputs_hash()` | Minimal deps (hashlib, json) |

---

### Package: `maverick.registry` (new)

**Source**: `src/maverick/dsl/serialization/registry/` (partial, ~870 LOC from 7 of 9 files)

| File | Entities | Status |
|------|----------|--------|
| `__init__.py` | Re-exports | **Rewrite** — remove dead exports |
| `component_registry.py` (80 LOC) | `ComponentRegistry` | **Edit** — remove `workflows`, `context_builders` attrs |
| `protocol.py` (57 LOC) | `AgentType`, `ActionType`, `GeneratorType` | **Move** — remove `WorkflowType`, `ContextBuilderType` |
| `validation.py` (274 LOC) | `validate_agent_class`, `validate_callable`, etc. | **Move** — remove `validate_context_builder` |
| `actions.py` (227 LOC) | `ActionRegistry` | **Move as-is** |
| `agents.py` (241 LOC) | `AgentRegistry` | **Move as-is** |
| `generators.py` (242 LOC) | `GeneratorRegistry` | **Move as-is** |
| `workflows.py` (166 LOC) | `WorkflowRegistry` | **DELETE** |
| `context_builders.py` (185 LOC) | `ContextBuilderRegistry` | **DELETE** |

**ComponentRegistry cleanup**:
```python
# OLD
class ComponentRegistry:
    actions: ActionRegistry
    agents: AgentRegistry
    generators: GeneratorRegistry
    workflows: WorkflowRegistry           # REMOVE
    context_builders: ContextBuilderRegistry  # REMOVE

# NEW
class ComponentRegistry:
    actions: ActionRegistry
    agents: AgentRegistry
    generators: GeneratorRegistry
```

---

### Error Hierarchy Updates (`maverick.exceptions.workflow`)

**Source**: `src/maverick/dsl/errors.py` (524 LOC) — extract 5 classes, delete rest.

```python
# Add to src/maverick/exceptions/workflow.py:

class WorkflowStepError(WorkflowError):
    """Explicit workflow step failure (renamed from DSLWorkflowError)."""

class CheckpointNotFoundError(WorkflowError):
    """No checkpoint found for resume."""

class InputMismatchError(WorkflowError):
    """Checkpoint input hash mismatch on resume."""

class ReferenceResolutionError(WorkflowError):
    """Unknown component reference in registry."""

class DuplicateComponentError(WorkflowError):
    """Duplicate component registration."""
```

**Note**: `WorkflowError` already exists in `maverick.exceptions.workflow`. These new classes extend it.

---

## Relationship Diagram

```
maverick.types ←── maverick.events
                ←── maverick.results
                ←── maverick.executor.config

maverick.events ←── maverick.executor.claude
                ←── maverick.executor.result
                ←── maverick.workflows.base
                ←── maverick.cli.workflow_executor
                ←── maverick.session_journal
                ←── maverick.library.actions.*

maverick.results ←── maverick.workflows.base

maverick.executor ←── maverick.workflows.base
                  ←── maverick.cli.workflow_executor

maverick.checkpoint ←── maverick.workflows.base
                    ←── maverick.cli.workflow_executor

maverick.registry ←── maverick.executor.claude
                  ←── maverick.workflows.base
                  ←── maverick.cli.common
                  ←── maverick.library.agents
                  ←── maverick.library.actions
                  ←── maverick.library.generators

maverick.constants ←── maverick.checkpoint.store
                   ←── maverick.executor.config (if referenced)
```

No circular dependencies in the new layout.
