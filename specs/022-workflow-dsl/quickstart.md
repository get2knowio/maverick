# Quickstart: Core Workflow DSL

**Feature Branch**: `022-workflow-dsl`
**Date**: 2025-12-19
**Updated**: December 2025 (YAML-based DSL only)

> **Important**: As of December 2025, Maverick uses **YAML-based workflows exclusively**. The Python decorator DSL (`@workflow`) has been deprecated and removed. All examples in this guide use the YAML format. If you have existing decorator-based workflows, see `docs/migrating-from-decorator-dsl.md` for migration guidance.

This guide demonstrates how to define and execute workflows using the Maverick YAML-based Workflow DSL.

---

## Installation

The Workflow DSL is part of the `maverick` package. No additional installation required.

```python
from maverick.dsl.serialization import WorkflowFile, WorkflowFileExecutor, ComponentRegistry
```

---

## Basic Workflow

### 1. Define a Workflow

A workflow is defined in YAML format:

```yaml
# hello-world.yaml
version: "1.0"
name: hello-world
description: A simple example workflow

inputs:
  name:
    type: string
    required: true
    description: The name to greet

steps:
  - name: format_greeting
    type: python
    action: format_greeting
    args:
      - ${{ inputs.name }}

  - name: uppercase
    type: python
    action: str.upper
    args:
      - ${{ steps.format_greeting.output }}

outputs:
  greeting: ${{ steps.format_greeting.output }}
  uppercase: ${{ steps.uppercase.output }}
```

### 2. Register Required Actions

Register any custom Python functions used by the workflow:

```python
from maverick.dsl.serialization import ComponentRegistry

# Create registry
registry = ComponentRegistry()

# Register custom action (replaces lambda)
def format_greeting(name: str) -> str:
    return f"Hello, {name}!"

registry.register_action("format_greeting", format_greeting)
# Note: str.upper is a built-in and doesn't need registration
```

### 3. Execute the Workflow

Use `WorkflowFileExecutor` to execute and observe progress:

```python
import asyncio
from maverick.dsl.serialization import WorkflowFile, WorkflowFileExecutor

async def main():
    # Load workflow from YAML
    with open("hello-world.yaml") as f:
        workflow = WorkflowFile.from_yaml(f.read())

    # Create executor with registry
    executor = WorkflowFileExecutor(registry=registry)

    # Execute workflow, consuming progress events
    async for event in executor.execute(workflow, inputs={"name": "Alice"}):
        print(f"[{type(event).__name__}] {event}")

    # Get final result
    result = executor.get_result()
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

```yaml
# python-example.yaml
version: "1.0"
name: python-example
description: Python step example

inputs:
  raw_data:
    type: string
    required: true

steps:
  - name: process
    type: python
    action: process_data
    args:
      - ${{ inputs.raw_data }}

  - name: count
    type: python
    action: get_length
    args:
      - ${{ steps.process.output }}

outputs:
  result: ${{ steps.process.output }}
  length: ${{ steps.count.output }}
```

```python
# Register actions
def process_data(data: str) -> dict:
    return {"processed": data.strip().lower()}

def get_length(d: dict) -> int:
    return len(d["processed"])

registry.register_action("process_data", process_data)
registry.register_action("get_length", get_length)
```

### Agent Step

Invoke a MaverickAgent:

```yaml
# agent-example.yaml
version: "1.0"
name: agent-example
description: Agent step example

inputs:
  task_description:
    type: string
    required: true

steps:
  - name: implement
    type: agent
    agent: implementer  # Registered agent name
    context:
      task: ${{ inputs.task_description }}

outputs:
  result: ${{ steps.implement.output }}
```

```python
# Register agent
from maverick.agents import ImplementerAgent

registry.register_agent("implementer", ImplementerAgent)
```

### Agent Step with Context Builder

Build context dynamically from prior step results:

```yaml
# context-builder-example.yaml
version: "1.0"
name: context-builder-example
description: Context builder example

inputs:
  spec_path:
    type: string
    required: true

steps:
  - name: implement
    type: agent
    agent: implementer
    context:
      spec: ${{ inputs.spec_path }}

  - name: review
    type: agent
    agent: reviewer
    context_builder: build_review_context  # Registered context builder

outputs:
  implementation: ${{ steps.implement.output }}
  review: ${{ steps.review.output }}
```

```python
# Register context builder
from maverick.dsl.context import WorkflowContext

async def build_review_context(ctx: WorkflowContext) -> dict:
    return {
        "files_changed": ctx.results["implement"].output.files,
        "original_spec": ctx.inputs["spec_path"],
    }

registry.register_context_builder("build_review_context", build_review_context)
```

### Generate Step

Invoke a GeneratorAgent for text generation:

```yaml
# generate-example.yaml
version: "1.0"
name: generate-example
description: Generate step example

inputs:
  commits:
    type: list
    required: true
  branch:
    type: string
    default: "feature-123"

steps:
  - name: generate_pr
    type: generate
    generator: pr_description  # Registered generator
    context:
      commits: ${{ inputs.commits }}
      branch: ${{ inputs.branch }}

outputs:
  pr_body: ${{ steps.generate_pr.output }}
```

```python
# Register generator
from maverick.agents.generators import PRDescriptionGenerator

registry.register_generator("pr_description", PRDescriptionGenerator)
```

### Validate Step

Run validation with retry logic:

```yaml
# validate-example.yaml
version: "1.0"
name: validate-example
description: Validate step example

steps:
  # Basic validation
  - name: lint
    type: validate
    stages:
      - lint

  # Validation with retry and on-failure
  - name: full_validation
    type: validate
    stages:
      - format
      - lint
      - test
    retry: 3
    on_failure:
      name: fix
      type: agent
      agent: fixer
      context_builder: build_fix_context

outputs:
  message: "Validation passed!"
```

```python
# Register components
from maverick.agents import FixerAgent

registry.register_agent("fixer", FixerAgent)

async def build_fix_context(ctx: WorkflowContext) -> dict:
    return {"errors": ctx.results["full_validation"].output.errors}

registry.register_context_builder("build_fix_context", build_fix_context)
```

### Sub-Workflow Step

Execute another workflow as a step:

```yaml
# helper-workflow.yaml
version: "1.0"
name: helper-workflow
description: Helper workflow

inputs:
  data:
    type: string
    required: true

steps:
  - name: process
    type: python
    action: str.upper
    args:
      - ${{ inputs.data }}

outputs:
  result: ${{ steps.process.output }}
```

```yaml
# parent-workflow.yaml
version: "1.0"
name: parent-workflow
description: Parent workflow

inputs:
  input_data:
    type: string
    required: true

steps:
  - name: run_helper
    type: subworkflow
    workflow: helper-workflow  # References helper-workflow.yaml
    inputs:
      data: ${{ inputs.input_data }}

outputs:
  final_result: ${{ steps.run_helper.output }}
```

---

## Accessing Prior Step Results

### Using Expression Syntax

Access prior results directly in YAML using expression syntax:

```yaml
# access-results-example.yaml
version: "1.0"
name: access-results-example
description: Access prior results

inputs:
  input_value:
    type: string
    required: true

steps:
  - name: first
    type: python
    action: str.upper
    args:
      - ${{ inputs.input_value }}

  # Access prior step output directly
  - name: second
    type: agent
    agent: my_agent
    context:
      first_result: ${{ steps.first.output }}
      original: ${{ inputs.input_value }}

outputs:
  result: ${{ steps.second.output }}
```

### Using Context Builders

For more complex context construction, use registered context builders:

```python
from maverick.dsl.context import WorkflowContext

async def build_context(ctx: WorkflowContext) -> dict:
    first_output = ctx.results["first"].output  # "HELLO"
    original_input = ctx.inputs["input_value"]   # "hello"
    return {
        "first_result": first_output,
        "original": original_input,
    }

registry.register_context_builder("my_context_builder", build_context)
```

```yaml
steps:
  - name: second
    type: agent
    agent: my_agent
    context_builder: my_context_builder  # Use registered builder
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
