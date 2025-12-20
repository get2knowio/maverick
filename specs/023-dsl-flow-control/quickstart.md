# Quickstart: Workflow DSL Flow Control

**Branch**: `023-dsl-flow-control` | **Date**: 2025-12-20

This guide shows how to use flow control constructs in Maverick workflows.

---

## Prerequisites

- Maverick DSL (spec 022) installed
- Python 3.10+

```python
from maverick.dsl import (
    workflow,
    step,
    branch,
    parallel,
    WorkflowEngine,
    WorkflowError,
)
```

---

## 1. Conditional Execution with `.when()`

Skip steps based on runtime conditions.

```python
@workflow("deploy_workflow")
def deploy_workflow(env: str, skip_tests: bool = False):
    # Always run build
    build = yield step("build").python(run_build)

    # Only run tests if not skipped
    tests = yield step("test").python(run_tests).when(
        lambda ctx: not ctx.inputs["skip_tests"]
    )

    # Only deploy to prod if tests passed (or were skipped)
    yield step("deploy").python(deploy_app, args=(env,)).when(
        lambda ctx: ctx.inputs["env"] == "prod"
    )
```

**Predicate behavior:**
- Returns `True`: step executes normally
- Returns `False`: step skipped, output is `SkipMarker`
- Raises exception: step skipped, warning logged
- Returns non-bool: workflow fails with TypeError

---

## 2. Branching with `branch()`

Choose one path from multiple options.

```python
@workflow("process_order")
def process_order(order_type: str, amount: float):
    # Route based on order type
    result = yield branch(
        "route_order",
        (lambda ctx: ctx.inputs["order_type"] == "express",
         step("express").python(process_express)),

        (lambda ctx: ctx.inputs["amount"] > 1000,
         step("large").python(process_large_order)),

        (lambda ctx: True,  # Default catch-all
         step("standard").python(process_standard)),
    )

    # result.selected_step_name tells which path was taken
    yield step("confirm").python(send_confirmation, args=(result.inner_output,))
```

**Branch behavior:**
- Evaluates predicates in order
- Executes first matching option
- Fails workflow if no match (add catch-all to prevent)

---

## 3. Retry with `.retry()`

Automatically retry failed steps with exponential backoff.

```python
@workflow("fetch_data")
def fetch_data(url: str):
    # Retry up to 3 times with exponential backoff
    data = yield step("fetch").python(
        http_get, args=(url,)
    ).retry(max_attempts=3, backoff=1.0)

    # Process fetched data
    yield step("process").python(process_data, args=(data,))
```

**Retry timing with `backoff=1.0`:**
- Attempt 1: immediate
- Attempt 2: ~1 second wait
- Attempt 3: ~2 seconds wait
- (With random jitter to prevent thundering herd)

---

## 4. Error Handling

### Skip on Error

Convert failures to skips for optional steps.

```python
@workflow("with_optional")
def with_optional():
    # This step won't fail the workflow if it errors
    cache = yield step("warm_cache").python(warm_cache).skip_on_error()

    # Continue regardless
    yield step("main_work").python(do_main_work)
```

### Fallback Handler

Provide alternative logic when a step fails.

```python
@workflow("with_fallback")
def with_fallback(source: str):
    def select_fallback(ctx, failed_result):
        # Choose fallback based on error
        return step("backup").python(fetch_from_backup)

    data = yield step("primary").python(
        fetch_from_source, args=(source,)
    ).on_error(select_fallback)

    # data contains either primary or fallback result
    yield step("process").python(process, args=(data,))
```

---

## 5. Rollback Support

Register compensation actions for cleanup on failure.

```python
@workflow("create_resources")
def create_resources(name: str):
    # Create with rollback registered
    branch = yield step("create_branch").python(
        create_git_branch, args=(name,)
    ).with_rollback(
        lambda ctx: delete_git_branch(ctx.get_step_output("create_branch"))
    )

    # Another resource with rollback
    pr = yield step("create_pr").python(
        create_pull_request, args=(branch,)
    ).with_rollback(
        lambda ctx: close_pull_request(ctx.get_step_output("create_pr"))
    )

    # If this fails, rollbacks run in reverse order:
    # 1. close_pull_request
    # 2. delete_git_branch
    yield step("finalize").python(finalize_setup)
```

**Rollback behavior:**
- Only run if workflow fails AFTER step succeeded
- Execute in reverse order of registration
- Continue on rollback errors (best-effort)
- All errors collected in `WorkflowResult.rollback_errors`

---

## 6. Parallel Execution

Run multiple steps together (currently sequential, future: concurrent).

```python
@workflow("validate_all")
def validate_all():
    # Run all validations
    results = yield parallel(
        "validations",
        step("lint").python(run_lint),
        step("typecheck").python(run_typecheck),
        step("test").python(run_tests),
    )

    # Access individual results
    lint_passed = results.child_results[0].success
    test_output = results.get_output("test")

    if not all(r.success for r in results.child_results):
        raise WorkflowError("Validation failed")
```

---

## 7. Checkpointing and Resume

Save progress for long-running workflows.

```python
@workflow("data_pipeline")
def data_pipeline(source: str):
    # Expensive step - checkpoint after
    raw_data = yield step("extract").python(
        extract_data, args=(source,)
    ).checkpoint()

    # If we crash here, we can resume after extract
    transformed = yield step("transform").python(
        transform_data, args=(raw_data,)
    ).checkpoint()

    # Final load
    yield step("load").python(load_to_warehouse, args=(transformed,))
```

### Running with Resume

```python
import uuid

async def run_with_resume():
    engine = WorkflowEngine()
    workflow_id = str(uuid.uuid4())

    try:
        # First attempt
        async for event in engine.execute(
            data_pipeline,
            workflow_id=workflow_id,
            source="s3://data/input",
        ):
            print(event)
    except Exception:
        # Resume from last checkpoint
        async for event in engine.resume(
            data_pipeline,
            workflow_id=workflow_id,
            source="s3://data/input",  # Must match original
        ):
            print(event)
```

---

## 8. Explicit Workflow Failure

Fail with a clear reason using `WorkflowError`.

```python
@workflow("validated_process")
def validated_process(data: dict):
    result = yield step("validate").python(validate_input, args=(data,))

    if not result["valid"]:
        raise WorkflowError(f"Invalid input: {result['errors']}")

    yield step("process").python(process_data, args=(data,))
```

---

## 9. Combining Flow Control

Chain multiple flow control methods.

```python
@workflow("robust_workflow")
def robust_workflow(env: str):
    # Conditional + Retry + Rollback + Checkpoint
    resource = yield step("create").python(create_resource).when(
        lambda ctx: ctx.inputs["env"] == "prod"
    ).retry(
        max_attempts=3, backoff=2.0
    ).with_rollback(
        lambda ctx: cleanup_resource(ctx.get_step_output("create"))
    ).checkpoint()

    # Skip on error with condition
    yield step("optional").python(optional_work).when(
        lambda ctx: resource is not None
    ).skip_on_error()

    yield step("finalize").python(finalize)
```

---

## 10. Checking Skipped Steps

Detect when steps were skipped.

```python
from maverick.dsl.results import SkipMarker

@workflow("check_skips")
def check_skips(run_optional: bool):
    result = yield step("optional").python(optional_work).when(
        lambda ctx: ctx.inputs["run_optional"]
    )

    # Check if skipped
    if isinstance(result, SkipMarker):
        print(f"Step was skipped: {result.reason}")
    else:
        print(f"Step ran with output: {result}")

    # Or use context helper
    yield step("next").python(next_work)
```

---

## Quick Reference

| Construct | Syntax | Purpose |
|-----------|--------|---------|
| Conditional | `.when(predicate)` | Skip step if False |
| Retry | `.retry(max, backoff)` | Retry with backoff |
| Skip on error | `.skip_on_error()` | Convert failure to skip |
| Error handler | `.on_error(handler)` | Fallback on failure |
| Rollback | `.with_rollback(fn)` | Compensate on workflow failure |
| Checkpoint | `.checkpoint()` | Enable resume from here |
| Branch | `branch(name, ...)` | Select one of N paths |
| Parallel | `parallel(name, ...)` | Run multiple steps |
| Explicit fail | `raise WorkflowError(...)` | Fail with reason |
