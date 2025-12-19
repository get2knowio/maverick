# Quickstart: Core Workflow DSL

**Feature Branch**: `022-workflow-dsl`
**Date**: 2025-12-19

This guide demonstrates how to define and execute workflows using the Maverick Workflow DSL.

---

## Installation

The Workflow DSL is part of the `maverick` package. No additional installation required.

```python
from maverick.dsl import workflow, step, WorkflowEngine
```

---

## Basic Workflow

### 1. Define a Workflow

A workflow is a Python generator function decorated with `@workflow`:

```python
from maverick.dsl import workflow, step

@workflow(name="hello-world", description="A simple example workflow")
def hello_workflow(name: str):
    """Greet someone with multiple steps."""

    # Step 1: Format greeting
    greeting = yield step("format_greeting").python(
        action=lambda n: f"Hello, {n}!",
        args=(name,),
    )

    # Step 2: Make uppercase
    uppercase = yield step("uppercase").python(
        action=str.upper,
        args=(greeting,),
    )

    # Return final result
    return {"greeting": greeting, "uppercase": uppercase}
```

### 2. Execute the Workflow

Use `WorkflowEngine` to execute and observe progress:

```python
import asyncio
from maverick.dsl import WorkflowEngine

async def main():
    engine = WorkflowEngine()

    # Execute workflow, consuming progress events
    async for event in engine.execute(hello_workflow, name="Alice"):
        print(f"[{type(event).__name__}] {event}")

    # Get final result
    result = engine.get_result()
    print(f"\nSuccess: {result.success}")
    print(f"Output: {result.final_output}")

asyncio.run(main())
```

**Output**:
```
[WorkflowStarted] WorkflowStarted(workflow_name='hello-world', ...)
[StepStarted] StepStarted(step_name='format_greeting', step_type=StepType.PYTHON, ...)
[StepCompleted] StepCompleted(step_name='format_greeting', success=True, duration_ms=1, ...)
[StepStarted] StepStarted(step_name='uppercase', step_type=StepType.PYTHON, ...)
[StepCompleted] StepCompleted(step_name='uppercase', success=True, duration_ms=0, ...)
[WorkflowCompleted] WorkflowCompleted(workflow_name='hello-world', success=True, ...)

Success: True
Output: {'greeting': 'Hello, Alice!', 'uppercase': 'HELLO, ALICE!'}
```

---

## Step Types

### Python Step

Execute any Python callable:

```python
def process_data(data: str) -> dict:
    return {"processed": data.strip().lower()}

@workflow(name="python-example", description="Python step example")
def python_example(raw_data: str):
    # Sync function
    result = yield step("process").python(
        action=process_data,
        args=(raw_data,),
    )

    # Lambda
    length = yield step("count").python(
        action=lambda d: len(d["processed"]),
        args=(result,),
    )

    return {"result": result, "length": length}
```

### Agent Step

Invoke a MaverickAgent:

```python
from maverick.agents import ImplementerAgent

@workflow(name="agent-example", description="Agent step example")
def agent_example(task_description: str):
    # With static context
    result = yield step("implement").agent(
        agent=ImplementerAgent(),
        context={"task": task_description},
    )

    return result.output
```

### Agent Step with Context Builder

Build context dynamically from prior step results:

```python
from maverick.agents import ImplementerAgent, ReviewerAgent

@workflow(name="context-builder-example", description="Context builder example")
def context_builder_example(spec_path: str):
    # First step
    impl = yield step("implement").agent(
        agent=ImplementerAgent(),
        context={"spec": spec_path},
    )

    # Context builder - receives full WorkflowContext
    async def build_review_context(ctx):
        return {
            "files_changed": ctx.results["implement"].output.files,
            "original_spec": ctx.inputs["spec_path"],
        }

    # Use context builder
    review = yield step("review").agent(
        agent=ReviewerAgent(),
        context=build_review_context,
    )

    return {"implementation": impl, "review": review}
```

### Generate Step

Invoke a GeneratorAgent for text generation:

```python
from maverick.agents.generators import PRDescriptionGenerator

@workflow(name="generate-example", description="Generate step example")
def generate_example(commits: list[str]):
    pr_body = yield step("generate_pr").generate(
        generator=PRDescriptionGenerator(),
        context={"commits": commits, "branch": "feature-123"},
    )

    return pr_body  # Generated string
```

### Validate Step

Run validation with retry logic:

```python
from maverick.agents import FixerAgent

@workflow(name="validate-example", description="Validate step example")
def validate_example():
    # Basic validation
    yield step("lint").validate(stages=["lint"])

    # Validation with retry and on-failure
    yield step("full_validation").validate(
        stages=["format", "lint", "test"],
        retry=3,
        on_failure=step("fix").agent(
            agent=FixerAgent(),
            context=lambda ctx: {"errors": ctx.results["full_validation"].output.errors},
        ),
    )

    return "Validation passed!"
```

### Sub-Workflow Step

Execute another workflow as a step:

```python
@workflow(name="sub-workflow", description="Helper workflow")
def helper_workflow(data: str):
    result = yield step("process").python(action=str.upper, args=(data,))
    return result

@workflow(name="parent-workflow", description="Parent workflow")
def parent_workflow(input_data: str):
    # Execute sub-workflow
    sub_result = yield step("run_helper").subworkflow(
        workflow=helper_workflow,
        inputs={"data": input_data},
    )

    # sub_result is SubWorkflowInvocationResult
    # Access sub_result.final_output or sub_result.workflow_result
    return sub_result.final_output
```

---

## Accessing Prior Step Results

Use `WorkflowContext` in context builders:

```python
@workflow(name="access-results", description="Access prior results")
def access_results_example(input_value: str):
    first = yield step("first").python(action=str.upper, args=(input_value,))

    # Context builder can access prior results
    async def build_context(ctx):
        first_output = ctx.results["first"].output  # "HELLO"
        original_input = ctx.inputs["input_value"]   # "hello"
        return {
            "first_result": first_output,
            "original": original_input,
        }

    second = yield step("second").agent(
        agent=MyAgent(),
        context=build_context,
    )

    return second
```

---

## Error Handling

### Step Failures

When a step fails, the workflow stops immediately:

```python
@workflow(name="error-example", description="Error handling example")
def error_example():
    def failing_action():
        raise ValueError("Something went wrong!")

    # This step will fail
    yield step("will_fail").python(action=failing_action)

    # This step never executes
    yield step("never_reached").python(action=lambda: "success")


async def main():
    engine = WorkflowEngine()
    async for event in engine.execute(error_example):
        pass

    result = engine.get_result()
    print(f"Success: {result.success}")           # False
    print(f"Error: {result.failed_step.error}")   # "Step 'will_fail' failed: Something went wrong!"
```

### Validation Retry

Validation steps can retry with on-failure handlers:

```python
@workflow(name="retry-example", description="Retry example")
def retry_example():
    # retry=3 means: try once, then retry up to 3 times if failed
    # on_failure runs before each retry
    yield step("validate").validate(
        stages=["lint", "test"],
        retry=3,
        on_failure=step("auto_fix").agent(
            agent=AutoFixerAgent(),
            context={"mode": "aggressive"},
        ),
    )
```

---

## Progress Events for TUI

Use progress events to update a TUI:

```python
from maverick.dsl import (
    WorkflowEngine,
    WorkflowStarted,
    StepStarted,
    StepCompleted,
    WorkflowCompleted,
)

async def run_with_tui(workflow_func, **inputs):
    engine = WorkflowEngine()

    async for event in engine.execute(workflow_func, **inputs):
        match event:
            case WorkflowStarted(workflow_name=name):
                tui.show_header(f"Running: {name}")

            case StepStarted(step_name=name, step_type=stype):
                tui.show_step_running(name, stype)

            case StepCompleted(step_name=name, success=ok, duration_ms=ms):
                tui.show_step_done(name, ok, ms)

            case WorkflowCompleted(success=ok, total_duration_ms=ms):
                tui.show_footer(ok, ms)

    return engine.get_result()
```

---

## Best Practices

### 1. Use Descriptive Step Names

```python
# Good
yield step("parse_task_file").python(...)
yield step("implement_feature").agent(...)
yield step("run_validation").validate(...)

# Avoid
yield step("step1").python(...)
yield step("s").agent(...)
```

### 2. Keep Context Builders Simple

```python
# Good - simple extraction
async def build_context(ctx):
    return {"diff": ctx.results["get_diff"].output}

# Avoid - complex logic in context builder
async def build_context(ctx):
    # Don't do heavy processing here
    files = await parse_all_files(ctx.results["scan"].output)
    analyzed = await analyze_complexity(files)
    return {"files": analyzed}

# Better - use a separate step
yield step("analyze").python(action=analyze_files, args=(scan_result,))
```

### 3. Handle Validation Failures Gracefully

```python
# Configure appropriate retry counts
yield step("validate").validate(
    stages=["format", "lint"],  # Quick checks
    retry=2,                     # Few retries
)

yield step("test").validate(
    stages=["test"],             # Slow tests
    retry=1,                     # Minimal retries
)
```

### 4. Use Explicit Returns

```python
# Good - explicit return value
@workflow(name="explicit", description="...")
def explicit_workflow(data: str):
    result = yield step("process").python(...)
    return {"processed": result, "input": data}

# Less clear - implicit last step output
@workflow(name="implicit", description="...")
def implicit_workflow(data: str):
    yield step("process").python(...)
    # Returns last step's output implicitly
```

---

## Complete Example

```python
from maverick.dsl import workflow, step, WorkflowEngine
from maverick.agents import ImplementerAgent, CodeReviewerAgent, FixerAgent

@workflow(name="feature-implementation", description="Implement and validate a feature")
async def implement_feature(spec_path: str, branch_name: str):
    """Complete feature implementation workflow."""

    # Step 1: Parse the specification
    spec = yield step("parse_spec").python(
        action=parse_spec_file,
        args=(spec_path,),
    )

    # Step 2: Implement the feature
    implementation = yield step("implement").agent(
        agent=ImplementerAgent(),
        context={"spec": spec, "branch": branch_name},
    )

    # Step 3: Code review with context builder
    async def review_context(ctx):
        return {
            "files": ctx.results["implement"].output.files,
            "spec": ctx.results["parse_spec"].output,
        }

    review = yield step("review").agent(
        agent=CodeReviewerAgent(),
        context=review_context,
    )

    # Step 4: Validation with auto-fix
    yield step("validate").validate(
        stages=["format", "lint", "typecheck", "test"],
        retry=3,
        on_failure=step("fix").agent(
            agent=FixerAgent(),
            context=lambda ctx: {"errors": ctx.results["validate"].output.errors},
        ),
    )

    # Return structured result
    return {
        "spec": spec,
        "implementation": implementation,
        "review": review,
        "validated": True,
    }


async def main():
    engine = WorkflowEngine()

    async for event in engine.execute(
        implement_feature,
        spec_path="specs/feature.md",
        branch_name="feature-123",
    ):
        print(f"Progress: {type(event).__name__}")

    result = engine.get_result()

    if result.success:
        print(f"Feature implemented successfully!")
        print(f"Output: {result.final_output}")
    else:
        print(f"Workflow failed at step: {result.failed_step.name}")
        print(f"Error: {result.failed_step.error}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

---

## Next Steps

- See [data-model.md](./data-model.md) for entity definitions
- See [contracts/public-api.md](./contracts/public-api.md) for complete API reference
- See [research.md](./research.md) for design rationale
