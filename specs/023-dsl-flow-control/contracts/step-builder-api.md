# StepBuilder Flow Control API Contract

**Branch**: `023-dsl-flow-control` | **Date**: 2025-12-20

This document defines the public API for flow control methods on `StepBuilder` and the resulting step definitions.

---

## StepBuilder Extensions

The `StepBuilder` class is extended with methods that return wrapped step definitions.

### Method Signatures

```python
class StepBuilder:
    """Extended with flow control methods."""

    # Conditional Execution
    def when(
        self,
        predicate: Callable[[WorkflowContext], bool | Awaitable[bool]],
    ) -> StepBuilder:
        """Add conditional execution to the step.

        Args:
            predicate: Callable returning bool. Receives WorkflowContext.
                If False, step is skipped with SkipMarker output.
                If raises exception, step is skipped and warning logged.
                If returns non-bool, workflow fails with TypeError.

        Returns:
            Self for method chaining.

        Example:
            yield step("deploy").python(deploy_fn).when(
                lambda ctx: ctx.inputs.get("env") == "prod"
            )
        """

    # Retry with Backoff
    def retry(
        self,
        max_attempts: int,
        backoff: float | None = None,
    ) -> StepBuilder:
        """Add retry with exponential backoff.

        Args:
            max_attempts: Maximum number of attempts (including first try).
            backoff: Base delay in seconds. Default 1.0.
                Delay formula: min(backoff * 2^(attempt-1), 60) with jitter.

        Returns:
            Self for method chaining.

        Example:
            yield step("fetch").python(fetch_data).retry(
                max_attempts=3, backoff=2.0
            )
        """

    # Error Handling
    def on_error(
        self,
        handler: Callable[[WorkflowContext, StepResult], StepDefinition],
    ) -> StepBuilder:
        """Add error handler with fallback step selection.

        Args:
            handler: Callable that receives context and failed result,
                returns a fallback StepDefinition to execute.
                If fallback succeeds, original step is treated as successful.
                If fallback fails, workflow fails.

        Returns:
            Self for method chaining.

        Example:
            yield step("primary").python(primary_fn).on_error(
                lambda ctx, err: step("fallback").python(fallback_fn)
            )
        """

    def skip_on_error(self) -> StepBuilder:
        """Convert failure to skip instead of failing workflow.

        Returns:
            Self for method chaining.

        Example:
            yield step("optional").python(opt_fn).skip_on_error()
        """

    # Rollback
    def with_rollback(
        self,
        rollback: Callable[[WorkflowContext], None | Awaitable[None]],
    ) -> StepBuilder:
        """Register rollback action for this step.

        The rollback is executed (best-effort) if the workflow fails
        AFTER this step has successfully completed.

        Args:
            rollback: Async or sync callable that compensates the step.
                Receives WorkflowContext.

        Returns:
            Self for method chaining.

        Example:
            yield step("create_branch").python(create_fn).with_rollback(
                lambda ctx: delete_branch(ctx.get_step_output("create_branch"))
            )
        """

    # Checkpointing
    def checkpoint(self) -> StepBuilder:
        """Mark this step as a checkpoint for resumability.

        After this step completes successfully, workflow state is
        persisted. The workflow can be resumed from this point.

        Returns:
            Self for method chaining.

        Example:
            yield step("expensive_compute").python(compute_fn).checkpoint()
        """
```

---

## Branching API

Branch steps use a separate builder pattern.

```python
def branch(
    name: str,
    *options: tuple[Predicate, StepDefinition],
) -> BranchStep:
    """Create a branch step that selects one option to execute.

    Args:
        name: Step name for the branch.
        *options: Variable number of (predicate, step) tuples.
            Predicates are evaluated in order; first True wins.
            If no predicate matches, workflow fails.

    Returns:
        BranchStep definition.

    Example:
        yield branch(
            "route",
            (lambda ctx: ctx.inputs["type"] == "a", step("a").python(handle_a)),
            (lambda ctx: ctx.inputs["type"] == "b", step("b").python(handle_b)),
            (lambda ctx: True, step("default").python(handle_default)),  # Catch-all
        )
    """
```

---

## Parallel API

Parallel steps use a separate builder function.

```python
def parallel(
    name: str,
    *steps: StepDefinition,
) -> ParallelStep:
    """Create a parallel step that executes multiple steps.

    Initial implementation executes sequentially but interface is
    compatible with future concurrent execution.

    Args:
        name: Step name for the parallel group.
        *steps: Variable number of steps to execute.
            All step names must be unique (validated before execution).

    Returns:
        ParallelStep definition.

    Raises:
        (At execution time) Fails if duplicate step names detected.

    Example:
        result = yield parallel(
            "reviews",
            step("lint").python(run_lint),
            step("typecheck").python(run_typecheck),
            step("test").python(run_tests),
        )
        # Access results:
        lint_output = result.get_output("lint")
    """
```

---

## Workflow Resume API

```python
class WorkflowEngine:
    """Extended with resume capability."""

    async def resume(
        self,
        workflow_func: Callable[..., Any],
        workflow_id: str,
        checkpoint_store: CheckpointStore | None = None,
        **inputs: Any,
    ) -> AsyncIterator[ProgressEvent]:
        """Resume workflow from latest checkpoint.

        Args:
            workflow_func: Decorated workflow function.
            workflow_id: Unique identifier for this workflow run.
            checkpoint_store: Store to load checkpoint from.
                Default: FileCheckpointStore at .maverick/checkpoints/
            **inputs: Workflow input arguments.
                Must match inputs at checkpoint time (hash validated).

        Yields:
            ProgressEvent objects (same as execute()).

        Raises:
            CheckpointNotFoundError: If no checkpoint exists.
            InputMismatchError: If current inputs don't match checkpoint.

        Example:
            engine = WorkflowEngine()
            async for event in engine.resume(
                my_workflow,
                workflow_id="run-123",
                data="same_as_before",
            ):
                print(event)
        """
```

---

## WorkflowError Usage

```python
from maverick.dsl import WorkflowError

@workflow("my_workflow")
def my_workflow(critical: bool):
    result = yield step("check").python(validate)

    if not result["valid"]:
        raise WorkflowError("Validation failed: data is corrupt")

    # ... continue workflow
```

---

## Method Chaining Examples

Flow control methods can be chained in any order:

```python
# Conditional + Retry
yield step("flaky_deploy").python(deploy).when(
    lambda ctx: ctx.inputs["env"] == "prod"
).retry(max_attempts=3)

# Retry + Rollback
yield step("create_resource").python(create).retry(
    max_attempts=2, backoff=1.0
).with_rollback(cleanup_resource)

# Conditional + Skip on Error
yield step("optional_cache").python(cache_data).when(
    lambda ctx: ctx.inputs.get("use_cache", True)
).skip_on_error()

# Full chain: conditional + retry + rollback + checkpoint
yield step("critical_op").python(critical_fn).when(
    lambda ctx: ctx.inputs["ready"]
).retry(max_attempts=3).with_rollback(undo_critical).checkpoint()
```

---

## Return Types

| Method | Returns |
|--------|---------|
| `.when(predicate)` | `StepBuilder` (chainable) |
| `.retry(...)` | `StepBuilder` (chainable) |
| `.on_error(handler)` | `StepBuilder` (chainable) |
| `.skip_on_error()` | `StepBuilder` (chainable) |
| `.with_rollback(action)` | `StepBuilder` (chainable) |
| `.checkpoint()` | `StepBuilder` (chainable) |
| `.python(...)` | `StepDefinition` (terminal) |
| `.agent(...)` | `StepDefinition` (terminal) |
| `.generate(...)` | `StepDefinition` (terminal) |
| `.validate(...)` | `StepDefinition` (terminal) |
| `.subworkflow(...)` | `StepDefinition` (terminal) |
| `branch(...)` | `BranchStep` (direct) |
| `parallel(...)` | `ParallelStep` (direct) |
