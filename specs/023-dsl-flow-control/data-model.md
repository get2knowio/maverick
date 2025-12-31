# Data Model: Workflow DSL Flow Control

**Branch**: `023-dsl-flow-control` | **Date**: 2025-12-20

This document defines the data structures for flow control constructs in the Maverick Workflow DSL.

---

## Entity Overview

| Entity | Description | Persistence |
|--------|-------------|-------------|
| SkipMarker | Marker output for skipped steps | In-memory |
| BranchOption | Predicate + step pair for branching | In-memory |
| BranchResult | Output of a branch step | In-memory |
| ParallelResult | Composite output from parallel steps | In-memory |
| RollbackAction | Callable registered for compensation | In-memory |
| RollbackError | Error from a failed rollback action | In-memory |
| CheckpointData | Persisted checkpoint state | JSON file |
| CheckpointStore | Protocol for checkpoint persistence | N/A (interface) |
| WorkflowError | Exception for explicit workflow failure | N/A (exception) |

---

## 1. SkipMarker

Marker value indicating a step was skipped (not executed) due to a runtime condition.

```python
@dataclass(frozen=True, slots=True)
class SkipMarker:
    """Marker indicating step was skipped.

    Attributes:
        reason: Why the step was skipped.
            - "predicate_false": .when() predicate returned False
            - "predicate_exception": .when() predicate raised exception
            - "error_skipped": .skip_on_error() converted failure to skip
    """

    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"skipped": True, "reason": self.reason}
```

### Usage

```python
# Check if step was skipped
result = context.get_step_output("optional_step")
if isinstance(result, SkipMarker):
    print(f"Step skipped: {result.reason}")
```

---

## 2. BranchOption

A single option within a branch step: a predicate function paired with the step to execute if the predicate is true.

```python
@dataclass(frozen=True, slots=True)
class BranchOption:
    """Single branch option in a branch step.

    Attributes:
        predicate: Callable that returns bool (sync or async).
            Receives WorkflowContext.
        step: StepDefinition to execute if predicate is True.
    """

    predicate: Predicate
    step: StepDefinition

    def to_dict(self) -> dict[str, Any]:
        return {
            "predicate": getattr(self.predicate, "__name__", "<lambda>"),
            "step": self.step.to_dict(),
        }
```

### Type Alias

```python
Predicate = Callable[[WorkflowContext], bool | Awaitable[bool]]
```

---

## 3. BranchResult

Output produced by a successful branch step, indicating which option was selected and its output.

```python
@dataclass(frozen=True, slots=True)
class BranchResult:
    """Output of a branch step execution.

    Attributes:
        selected_index: Zero-based index of the selected branch option.
        selected_step_name: Name of the step that was executed.
        inner_output: Output from the executed step.
    """

    selected_index: int
    selected_step_name: str
    inner_output: Any

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected_index": self.selected_index,
            "selected_step_name": self.selected_step_name,
            "inner_output": str(self.inner_output),
        }
```

---

## 4. ParallelResult

Composite output from a parallel step, containing results from all child steps.

```python
@dataclass(frozen=True, slots=True)
class ParallelResult:
    """Output of a parallel step execution.

    Attributes:
        child_results: Tuple of StepResult objects in input order.
    """

    child_results: tuple[StepResult, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "child_count": len(self.child_results),
            "children": [r.to_dict() for r in self.child_results],
            "all_success": all(r.success for r in self.child_results),
        }

    def __getitem__(self, index: int) -> StepResult:
        """Access child result by index."""
        return self.child_results[index]

    def get_output(self, step_name: str) -> Any:
        """Get child step output by name."""
        for result in self.child_results:
            if result.name == step_name:
                return result.output
        raise KeyError(f"Child step '{step_name}' not found")
```

---

## 5. RollbackAction

Type alias for rollback action callables.

```python
RollbackAction = Callable[[WorkflowContext], None | Awaitable[None]]
```

### Rollback Registration

```python
@dataclass(frozen=True, slots=True)
class RollbackRegistration:
    """A registered rollback action for a completed step.

    Attributes:
        step_name: Name of the step this rollback compensates.
        action: Callable to execute during rollback.
    """

    step_name: str
    action: RollbackAction
```

---

## 6. RollbackError

Captures an error that occurred during rollback execution.

```python
@dataclass(frozen=True, slots=True)
class RollbackError:
    """Error from a failed rollback action.

    Attributes:
        step_name: Name of the step whose rollback failed.
        error: Human-readable error message.
    """

    step_name: str
    error: str

    def to_dict(self) -> dict[str, Any]:
        return {"step_name": self.step_name, "error": self.error}
```

---

## 7. CheckpointData

Persisted state at a checkpoint, sufficient to resume workflow execution.

```python
@dataclass(frozen=True, slots=True)
class CheckpointData:
    """Data persisted at a workflow checkpoint.

    Attributes:
        checkpoint_id: Unique identifier for this checkpoint (step name).
        workflow_name: Name of the workflow being checkpointed.
        inputs_hash: SHA-256 hash (first 16 chars) of serialized inputs.
        step_results: Tuple of serialized StepResult dicts.
        saved_at: ISO 8601 timestamp of checkpoint creation.
    """

    checkpoint_id: str
    workflow_name: str
    inputs_hash: str
    step_results: tuple[dict[str, Any], ...]
    saved_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "workflow_name": self.workflow_name,
            "inputs_hash": self.inputs_hash,
            "step_results": list(self.step_results),
            "saved_at": self.saved_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CheckpointData:
        """Deserialize from dictionary."""
        return cls(
            checkpoint_id=data["checkpoint_id"],
            workflow_name=data["workflow_name"],
            inputs_hash=data["inputs_hash"],
            step_results=tuple(data["step_results"]),
            saved_at=data["saved_at"],
        )
```

### Storage Path

```
.maverick/checkpoints/{workflow_name}/{checkpoint_id}.json
```

---

## 8. CheckpointStore

Protocol for checkpoint persistence operations.

```python
from typing import Protocol

class CheckpointStore(Protocol):
    """Protocol for checkpoint persistence.

    Implementations must be async and support atomic operations.
    """

    async def save(
        self,
        workflow_id: str,
        data: CheckpointData,
    ) -> None:
        """Save checkpoint atomically.

        Args:
            workflow_id: Unique workflow run identifier.
            data: Checkpoint data to persist.

        Raises:
            IOError: If save fails.
        """
        ...

    async def load(
        self,
        workflow_id: str,
        checkpoint_id: str,
    ) -> CheckpointData | None:
        """Load checkpoint if it exists.

        Args:
            workflow_id: Unique workflow run identifier.
            checkpoint_id: Checkpoint to load.

        Returns:
            CheckpointData if found, None otherwise.
        """
        ...

    async def load_latest(
        self,
        workflow_id: str,
    ) -> CheckpointData | None:
        """Load most recent checkpoint for a workflow.

        Args:
            workflow_id: Unique workflow run identifier.

        Returns:
            Most recent CheckpointData if any exist, None otherwise.
        """
        ...

    async def clear(
        self,
        workflow_id: str,
    ) -> None:
        """Remove all checkpoints for a workflow.

        Args:
            workflow_id: Unique workflow run identifier.
        """
        ...
```

---

## 9. WorkflowError

Exception for explicit workflow failure with a human-readable reason.

```python
class WorkflowError(MaverickError):
    """Explicit workflow failure raised by workflow code.

    Use this to signal that a workflow should stop with a specific
    error reason, distinct from step failures.

    Attributes:
        reason: Human-readable explanation of why the workflow failed.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"Workflow failed: {reason}")
```

---

## Extended Types (types.py additions)

```python
# Add to StepType enum
class StepType(str, Enum):
    PYTHON = "python"
    AGENT = "agent"
    GENERATE = "generate"
    VALIDATE = "validate"
    SUBWORKFLOW = "subworkflow"
    BRANCH = "branch"      # NEW
    PARALLEL = "parallel"  # NEW

# Type aliases
Predicate = Callable[["WorkflowContext"], bool | Awaitable[bool]]
RollbackAction = Callable[["WorkflowContext"], None | Awaitable[None]]
```

---

## WorkflowContext Extensions

```python
@dataclass
class WorkflowContext:
    """Extended workflow context with rollback tracking."""

    inputs: dict[str, Any]
    results: dict[str, StepResult] = field(default_factory=dict)
    config: Any = None
    _pending_rollbacks: list[RollbackRegistration] = field(default_factory=list)

    def register_rollback(self, step_name: str, action: RollbackAction) -> None:
        """Register a rollback action for a completed step."""
        self._pending_rollbacks.append(
            RollbackRegistration(step_name=step_name, action=action)
        )

    def get_step_output(self, step_name: str, default: Any = None) -> Any:
        """Get step output, returning default if step not found.

        Changed from raising KeyError to returning None (FR-009a).
        """
        if step_name not in self.results:
            return default
        return self.results[step_name].output

    def is_step_skipped(self, step_name: str) -> bool:
        """Check if a step was skipped."""
        output = self.get_step_output(step_name)
        return isinstance(output, SkipMarker)
```

---

## WorkflowResult Extensions

```python
@dataclass(frozen=True, slots=True)
class WorkflowResult:
    """Extended workflow result with rollback errors."""

    workflow_name: str
    success: bool
    step_results: tuple[StepResult, ...]
    total_duration_ms: int
    final_output: Any
    rollback_errors: tuple[RollbackError, ...] = ()  # NEW

    @property
    def had_rollback_failures(self) -> bool:
        """True if any rollback actions failed."""
        return len(self.rollback_errors) > 0
```

---

## Validation Rules

### SkipMarker
- `reason` must be one of the defined constants

### BranchOption
- `predicate` must be callable
- `step` must be a valid StepDefinition

### CheckpointData
- `checkpoint_id` must not be empty
- `workflow_name` must not be empty
- `inputs_hash` must be 16 characters (hex)
- `saved_at` must be valid ISO 8601 format

### Parallel Steps (FR-014a)
- All child step names must be unique
- Validated before any child step executes

---

## State Transitions

### Step Execution with Conditions

```
[Step Yielded] -> [Evaluate Predicate]
                       |
            true/exception -> [Skip: return SkipMarker]
                       |
                     false -> [Execute Inner Step]
                                    |
                               [Return Result]
```

### Rollback Execution

```
[Workflow Failed] -> [Get Pending Rollbacks]
                          |
                     [Reverse Order]
                          |
                  [Execute Each Best-Effort]
                          |
                  [Collect All Errors]
                          |
                  [Return WorkflowResult with rollback_errors]
```

### Checkpoint Resume

```
[Resume Requested] -> [Load Checkpoint]
                           |
                      [Validate Input Hash]
                           |
                    hash mismatch -> [Fail with InputMismatchError]
                           |
                       match -> [Restore Step Results]
                                    |
                               [Continue Execution]
```
