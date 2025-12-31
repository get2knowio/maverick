# Research: Workflow DSL Flow Control

**Branch**: `023-dsl-flow-control` | **Date**: 2025-12-20

## Research Questions

1. Generator-based workflow patterns for conditional execution
2. Checkpoint/resume patterns for Python workflows
3. Rollback/compensation patterns
4. Retry with backoff implementation

---

## 1. Generator-Based Conditional Execution

### Decision
Use **wrapper step classes** that compose with existing step definitions. The wrapper implements `StepDefinition` and delegates to the inner step when conditions are met.

### Rationale
- Maintains the existing generator-based execution model
- Wrappers are composable (can chain `.when().retry().with_rollback()`)
- No changes to the core engine loop for basic conditions
- Consistent with Python's decorator pattern (wrapping adds behavior)
- The existing `StepDefinition` protocol is clean and extensible

### Pattern

```python
@dataclass(frozen=True, slots=True)
class ConditionalStep(StepDefinition):
    """Wrapper that adds conditional execution to any step."""

    inner: StepDefinition
    predicate: Callable[[WorkflowContext], bool | Awaitable[bool]]

    async def execute(self, context: WorkflowContext) -> StepResult:
        try:
            result = self.predicate(context)
            if asyncio.iscoroutine(result):
                result = await result
            if not isinstance(result, bool):
                # FR-005b: non-boolean returns fail workflow
                raise TypeError(f"Predicate must return bool, got {type(result)}")
            if not result:
                # Return skip marker result
                return StepResult(
                    name=self.name,
                    step_type=self.step_type,
                    success=True,
                    output=SkipMarker(reason="predicate_false"),
                    duration_ms=0,
                )
        except TypeError:
            raise  # Re-raise type errors
        except Exception as e:
            # FR-005a: exceptions treated as false, log warning
            logger.warning(f"Predicate for step '{self.name}' raised {e}, skipping")
            return StepResult(
                name=self.name,
                step_type=self.step_type,
                success=True,
                output=SkipMarker(reason="predicate_exception"),
                duration_ms=0,
            )
        return await self.inner.execute(context)
```

### Alternatives Considered

| Alternative | Why Rejected |
|-------------|--------------|
| Engine-level condition checking | Couples conditions to engine, less composable |
| Separate conditional step type | Duplicates logic for each step type |
| Generator filter pattern | Doesn't work well with yield-based step execution |

---

## 2. Checkpoint/Resume Patterns

### Decision
Use a **CheckpointStore protocol** with a **FileCheckpointStore** default implementation. Checkpoint data stored as JSON with atomic writes.

### Rationale
- Protocol allows in-memory stores for testing
- JSON is human-readable and debuggable
- Atomic writes (write to temp, rename) prevent corruption
- Input hash allows detecting stale checkpoints (FR-025a/b)
- Follows existing Maverick patterns (config, stores)

### Pattern

```python
from typing import Protocol

class CheckpointStore(Protocol):
    """Protocol for checkpoint persistence."""

    async def save(self, workflow_id: str, checkpoint_id: str, data: CheckpointData) -> None:
        """Save checkpoint atomically."""
        ...

    async def load(self, workflow_id: str, checkpoint_id: str) -> CheckpointData | None:
        """Load checkpoint or return None if not found."""
        ...

    async def clear(self, workflow_id: str) -> None:
        """Remove all checkpoints for a workflow."""
        ...


@dataclass(frozen=True, slots=True)
class CheckpointData:
    """Data persisted at a checkpoint."""

    checkpoint_id: str
    step_name: str
    inputs_hash: str
    step_results: tuple[dict[str, Any], ...]  # Serialized StepResults
    saved_at: str  # ISO timestamp
```

### Atomic File Write Pattern

```python
import os
import tempfile

async def _atomic_write(path: Path, content: str) -> None:
    """Write atomically: temp file + rename."""
    dir_path = path.parent
    dir_path.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(dir=str(dir_path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.rename(tmp_path, str(path))
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise
```

### Input Hash Pattern

```python
import hashlib
import json

def compute_inputs_hash(inputs: dict[str, Any]) -> str:
    """Compute deterministic hash of workflow inputs."""
    # Sort keys for determinism
    serialized = json.dumps(inputs, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()[:16]
```

### Alternatives Considered

| Alternative | Why Rejected |
|-------------|--------------|
| Pickle for serialization | Security concerns, version fragility |
| SQLite for storage | Over-engineering for local checkpoints |
| No atomic writes | Risk of corrupted checkpoints |
| Full inputs stored | Wastes space; hash sufficient for validation |

---

## 3. Rollback/Compensation Patterns

### Decision
Use the **Saga pattern** with reverse-order compensation. Track eligible rollbacks in `WorkflowContext`, execute best-effort on failure.

### Rationale
- Saga is the established pattern for distributed/async compensation
- Reverse order matches intuitive undo semantics
- Best-effort execution (continue on failure) per FR-019a
- Collecting all errors allows user to see full rollback status

### Pattern

```python
# In WorkflowContext
@dataclass
class WorkflowContext:
    inputs: dict[str, Any]
    results: dict[str, StepResult] = field(default_factory=dict)
    config: Any = None
    _pending_rollbacks: list[tuple[str, RollbackAction]] = field(default_factory=list)

    def register_rollback(self, step_name: str, action: RollbackAction) -> None:
        """Register a rollback action for a completed step."""
        self._pending_rollbacks.append((step_name, action))

# In WorkflowEngine.execute() - after step failure
async def _execute_rollbacks(
    self,
    context: WorkflowContext,
) -> list[RollbackError]:
    """Execute rollbacks in reverse order, collecting all errors."""
    errors = []
    for step_name, action in reversed(context._pending_rollbacks):
        try:
            result = action(context)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            errors.append(RollbackError(step_name=step_name, error=str(e)))
    return errors
```

### Alternatives Considered

| Alternative | Why Rejected |
|-------------|--------------|
| Stop on first rollback failure | User loses visibility into remaining rollbacks |
| Forward-order rollbacks | Doesn't match undo semantics |
| Two-phase commit | Over-engineering; not needed for local workflows |

---

## 4. Retry with Backoff

### Decision
Use **custom retry wrapper** with exponential backoff and optional jitter. No external library dependency.

### Rationale
- Simple implementation (30-40 lines)
- No additional dependency (constitution principle: simplicity)
- Full control over backoff parameters
- Consistent with existing step wrapper pattern

### Pattern

```python
import asyncio
import random

@dataclass(frozen=True, slots=True)
class RetryStep(StepDefinition):
    """Wrapper that retries a step on failure."""

    inner: StepDefinition
    max_attempts: int
    backoff_base: float = 1.0  # Base delay in seconds
    backoff_max: float = 60.0  # Max delay cap
    jitter: bool = True  # Add random jitter

    async def execute(self, context: WorkflowContext) -> StepResult:
        last_result: StepResult | None = None

        for attempt in range(1, self.max_attempts + 1):
            result = await self.inner.execute(context)

            if result.success:
                return result

            last_result = result

            if attempt < self.max_attempts:
                delay = min(self.backoff_base * (2 ** (attempt - 1)), self.backoff_max)
                if self.jitter:
                    delay *= (0.5 + random.random())
                await asyncio.sleep(delay)

        return last_result  # Return final failed result
```

### Exponential Backoff Formula
- Delay = min(base * 2^(attempt-1), max_delay)
- With jitter: Delay * random(0.5, 1.5)
- Default: 1s, 2s, 4s, 8s... capped at 60s

### Alternatives Considered

| Alternative | Why Rejected |
|-------------|--------------|
| `tenacity` library | Additional dependency; overkill for simple needs |
| `backoff` library | Less flexible configuration |
| Linear backoff | Exponential handles transient failures better |
| No jitter | Thundering herd problem in parallel retries |

---

## 5. Branch Step Design

### Decision
Branch step evaluates predicates in order and executes the first matching option. Fail if no match (FR-008).

### Pattern

```python
@dataclass(frozen=True, slots=True)
class BranchOption:
    """A single branch option: predicate + step to execute."""
    predicate: Callable[[WorkflowContext], bool | Awaitable[bool]]
    step: StepDefinition

@dataclass(frozen=True, slots=True)
class BranchStep(StepDefinition):
    """Step that selects and executes one of multiple options."""

    options: tuple[BranchOption, ...]

    async def execute(self, context: WorkflowContext) -> StepResult:
        for i, option in enumerate(self.options):
            try:
                result = option.predicate(context)
                if asyncio.iscoroutine(result):
                    result = await result
                if result:
                    inner_result = await option.step.execute(context)
                    return StepResult(
                        name=self.name,
                        step_type=self.step_type,
                        success=inner_result.success,
                        output=BranchResult(
                            selected_index=i,
                            selected_step_name=option.step.name,
                            inner_output=inner_result.output,
                        ),
                        duration_ms=inner_result.duration_ms,
                        error=inner_result.error,
                    )
            except Exception:
                continue  # Try next branch

        # No matching branch - fail workflow (FR-008)
        return StepResult(
            name=self.name,
            step_type=self.step_type,
            success=False,
            output=None,
            duration_ms=0,
            error="No branch predicate matched",
        )
```

---

## 6. Parallel Interface Design

### Decision
Initial implementation executes sequentially but exposes parallel-compatible interface. Child step names must be unique.

### Pattern

```python
@dataclass(frozen=True, slots=True)
class ParallelStep(StepDefinition):
    """Step that executes multiple steps (initially sequential)."""

    children: tuple[StepDefinition, ...]

    async def execute(self, context: WorkflowContext) -> StepResult:
        # FR-014a: validate unique names before execution
        names = [child.name for child in self.children]
        if len(names) != len(set(names)):
            return StepResult(
                name=self.name,
                step_type=self.step_type,
                success=False,
                output=None,
                duration_ms=0,
                error="Parallel step contains duplicate child step names",
            )

        child_results: list[StepResult] = []
        for child in self.children:
            result = await child.execute(context)
            child_results.append(result)
            if not result.success:
                break  # Fail fast

        all_success = all(r.success for r in child_results)
        return StepResult(
            name=self.name,
            step_type=StepType.PARALLEL,
            success=all_success,
            output=ParallelResult(child_results=tuple(child_results)),
            duration_ms=sum(r.duration_ms for r in child_results),
            error=child_results[-1].error if not all_success else None,
        )
```

---

## 7. Missing Result Handling (FR-009a)

### Decision
Extend `WorkflowContext.get_step_output()` to return `None` for missing steps instead of raising `KeyError`.

### Pattern

```python
def get_step_output(self, step_name: str, default: Any = None) -> Any:
    """Get step output, returning default (None) if step not found."""
    if step_name not in self.results:
        return default
    return self.results[step_name].output
```

This is a breaking change from the current implementation which raises `KeyError`. The spec explicitly requires this behavior (FR-009a).

---

## Summary of Decisions

| Topic | Decision |
|-------|----------|
| Conditional execution | Wrapper step class composing with inner step |
| Checkpoint storage | Protocol + FileCheckpointStore with JSON + atomic writes |
| Input validation | SHA-256 hash of serialized inputs |
| Rollback execution | Saga pattern, reverse order, best-effort, collect errors |
| Retry mechanism | Custom exponential backoff with jitter, no external deps |
| Branch execution | First-match wins, fail if no match |
| Parallel interface | Sequential execution, validate unique names before running |
| Missing step results | Return None instead of KeyError |
