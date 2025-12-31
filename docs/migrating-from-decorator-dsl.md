# Migrating from Decorator DSL to YAML Workflows

**Date**: December 2025
**Status**: Decorator DSL deprecated and removed

## Overview

As of December 2025, Maverick has consolidated to a single workflow authoring method: **YAML-based workflows**. The Python decorator DSL (`@workflow`, `step()` builder) has been deprecated and removed from the codebase.

This guide provides migration patterns for converting existing decorator-based workflows to YAML format.

---

## Why YAML-Only?

The consolidation to YAML workflows provides several benefits:

### User Experience
- **Discoverability**: Automatic workflow discovery from project, user, and built-in locations
- **Shareability**: Version-controlled, human-readable workflow definitions
- **No Python Required**: Non-developers can author and modify workflows
- **Validation**: Schema validation and error reporting at load time
- **Visualization**: Automatic ASCII/Mermaid diagram generation

### Development & Maintenance
- **Reduced Complexity**: Eliminated ~8,500 lines of code and 43 Python files
- **Battle-Tested**: All 6 built-in workflows use YAML; zero production decorator workflows existed
- **Consistent Execution**: Single execution engine path (WorkflowFileExecutor)
- **Better Testing**: YAML workflows are easier to test and validate

---

## Migration Patterns

### Pattern 1: Basic Workflow with Python Steps

#### Before (Decorator DSL)

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

    return {"greeting": greeting, "uppercase": uppercase}
```

#### After (YAML Workflow)

**File: `hello-world.yaml`**

```yaml
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

**File: `custom_actions.py` (if needed)**

```python
from maverick.dsl.serialization import ComponentRegistry

# Extract lambda to named function
def format_greeting(name: str) -> str:
    return f"Hello, {name}!"

# Register custom action
registry = ComponentRegistry()
registry.register_action("format_greeting", format_greeting)
# Note: str.upper is built-in and doesn't need registration
```

**Key Changes**:
1. Lambda `lambda n: f"Hello, {n}!"` → Named function `format_greeting`
2. Step result variables → Expression syntax `${{ steps.step_name.output }}`
3. Workflow inputs → Structured `inputs` section with type declarations
4. Return dict → `outputs` section with expressions

---

### Pattern 2: Agent Steps with Context Builders

#### Before (Decorator DSL)

```python
from maverick.dsl import workflow, step
from maverick.agents import ImplementerAgent, CodeReviewerAgent

@workflow(name="implement-and-review", description="Implement and review")
def implement_and_review(spec_path: str):
    # Implementation step
    impl = yield step("implement").agent(
        agent=ImplementerAgent(),
        context={"spec": spec_path},
    )

    # Context builder for review
    async def build_review_context(ctx):
        return {
            "files_changed": ctx.results["implement"].output.files,
            "original_spec": ctx.inputs["spec_path"],
        }

    # Review step
    review = yield step("review").agent(
        agent=CodeReviewerAgent(),
        context=build_review_context,
    )

    return {"implementation": impl, "review": review}
```

#### After (YAML Workflow)

**File: `implement-and-review.yaml`**

```yaml
version: "1.0"
name: implement-and-review
description: Implement and review

inputs:
  spec_path:
    type: string
    required: true
    description: Path to specification file

steps:
  - name: implement
    type: agent
    agent: implementer
    context:
      spec: ${{ inputs.spec_path }}

  - name: review
    type: agent
    agent: reviewer
    context_builder: build_review_context

outputs:
  implementation: ${{ steps.implement.output }}
  review: ${{ steps.review.output }}
```

**File: `context_builders.py`**

```python
from maverick.dsl.context import WorkflowContext
from maverick.dsl.serialization import ComponentRegistry
from maverick.agents import ImplementerAgent, CodeReviewerAgent

# Register agents
registry = ComponentRegistry()
registry.register_agent("implementer", ImplementerAgent)
registry.register_agent("reviewer", CodeReviewerAgent)

# Register context builder
async def build_review_context(ctx: WorkflowContext) -> dict:
    return {
        "files_changed": ctx.results["implement"].output.files,
        "original_spec": ctx.inputs["spec_path"],
    }

registry.register_context_builder("build_review_context", build_review_context)
```

**Key Changes**:
1. Agent instances → Registered agent names
2. Context builders → Registered and referenced by name
3. Inline async functions → Separate module with registration

---

### Pattern 3: Conditional Execution

#### Before (Decorator DSL)

```python
from maverick.dsl import workflow, step

@workflow(name="conditional-example")
def conditional_workflow(check: bool):
    result = yield step("check").conditional(
        predicate=lambda: check,
        step=step("true_branch").python(action=lambda: "true", args=()),
        else_step=step("false_branch").python(action=lambda: "false", args=()),
    )
    return result
```

#### After (YAML Workflow)

**File: `conditional-example.yaml`**

```yaml
version: "1.0"
name: conditional-example
description: Conditional execution example

inputs:
  check:
    type: boolean
    required: true

steps:
  - name: true_branch
    type: python
    action: return_true
    when: ${{ inputs.check }}

  - name: false_branch
    type: python
    action: return_false
    when: ${{ !inputs.check }}

outputs:
  result: ${{ steps.true_branch.output || steps.false_branch.output }}
```

**File: `actions.py`**

```python
registry.register_action("return_true", lambda: "true")
registry.register_action("return_false", lambda: "false")
```

**Key Changes**:
1. `ConditionalStep` → `when` field on individual steps
2. `else_step` → Separate step with negated condition
3. Actually simpler and more explicit in YAML!

---

### Pattern 4: Validation with Retry

#### Before (Decorator DSL)

```python
from maverick.dsl import workflow, step
from maverick.agents import FixerAgent

@workflow(name="validate-and-fix")
def validate_and_fix():
    yield step("validate").validate(
        stages=["format", "lint", "test"],
        retry=3,
        on_failure=step("fix").agent(
            agent=FixerAgent(),
            context=lambda ctx: {"errors": ctx.results["validate"].output.errors},
        ),
    )
    return "Validation passed!"
```

#### After (YAML Workflow)

**File: `validate-and-fix.yaml`**

```yaml
version: "1.0"
name: validate-and-fix
description: Validate with auto-fix retry

steps:
  - name: validate
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

**File: `fix_context.py`**

```python
from maverick.agents import FixerAgent

registry.register_agent("fixer", FixerAgent)

async def build_fix_context(ctx):
    return {"errors": ctx.results["validate"].output.errors}

registry.register_context_builder("build_fix_context", build_fix_context)
```

**Key Changes**:
1. Nested `on_failure` step → Inline step definition in YAML
2. Lambda context builder → Registered context builder function

---

### Pattern 5: Parallel Execution

#### Before (Decorator DSL)

```python
from maverick.dsl import workflow, step
from maverick.dsl.builder import parallel

@workflow(name="parallel-example")
def parallel_example():
    results = yield parallel(
        "all_checks",
        step("lint").python(action=run_lint),
        step("typecheck").python(action=run_typecheck),
        step("test").python(action=run_tests),
    )
    return results
```

#### After (YAML Workflow)

**File: `parallel-example.yaml`**

```yaml
version: "1.0"
name: parallel-example
description: Run checks in parallel

steps:
  - name: all_checks
    type: parallel
    steps:
      - name: lint
        type: python
        action: run_lint

      - name: typecheck
        type: python
        action: run_typecheck

      - name: test
        type: python
        action: run_tests

outputs:
  results: ${{ steps.all_checks.output }}
```

**File: `check_actions.py`**

```python
def run_lint():
    # Implementation
    pass

def run_typecheck():
    # Implementation
    pass

def run_tests():
    # Implementation
    pass

registry.register_action("run_lint", run_lint)
registry.register_action("run_typecheck", run_typecheck)
registry.register_action("run_tests", run_tests)
```

---

### Pattern 6: Sub-Workflows

#### Before (Decorator DSL)

```python
from maverick.dsl import workflow, step

@workflow(name="helper")
def helper_workflow(data: str):
    result = yield step("process").python(action=str.upper, args=(data,))
    return result

@workflow(name="parent")
def parent_workflow(input_data: str):
    sub_result = yield step("run_helper").subworkflow(
        workflow=helper_workflow,
        inputs={"data": input_data},
    )
    return sub_result.final_output
```

#### After (YAML Workflow)

**File: `helper.yaml`**

```yaml
version: "1.0"
name: helper
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

**File: `parent.yaml`**

```yaml
version: "1.0"
name: parent
description: Parent workflow

inputs:
  input_data:
    type: string
    required: true

steps:
  - name: run_helper
    type: subworkflow
    workflow: helper  # References helper.yaml
    inputs:
      data: ${{ inputs.input_data }}

outputs:
  final_result: ${{ steps.run_helper.output }}
```

**Key Changes**:
1. Two Python functions → Two separate YAML files
2. Workflow reference by function → Reference by name (filename)
3. Result access `.final_output` → Expression syntax

---

## Common Migration Challenges

### Challenge 1: Extracting Lambdas

**Problem**: Decorator DSL often used inline lambdas for simple transformations.

**Solution**: Extract to named functions and register them.

```python
# Before: Inline lambda
action=lambda x: x.strip().lower()

# After: Named function
def normalize_string(x: str) -> str:
    return x.strip().lower()

registry.register_action("normalize_string", normalize_string)
```

### Challenge 2: Dynamic Step Generation

**Problem**: Decorator DSL allowed dynamic step creation in loops.

**Solution**: Use YAML templates or generate YAML programmatically.

```python
# Before: Dynamic steps
@workflow(name="dynamic")
def dynamic_workflow(items: list):
    for item in items:
        yield step(f"process_{item}").python(action=process, args=(item,))

# After: Generate YAML workflow definition
def create_workflow_for_items(items: list) -> str:
    steps = [
        {
            "name": f"process_{item}",
            "type": "python",
            "action": "process_item",
            "args": [f"${{{{ inputs.items[{i}] }}}}"]
        }
        for i, item in enumerate(items)
    ]

    workflow_dict = {
        "version": "1.0",
        "name": "dynamic",
        "inputs": {"items": {"type": "list", "required": True}},
        "steps": steps
    }

    return WorkflowFile.from_dict(workflow_dict).to_yaml()
```

### Challenge 3: Complex Context Builders

**Problem**: Decorator DSL allowed complex inline context builders with local state.

**Solution**: Extract to module-level functions and pass necessary data via registry or inputs.

```python
# Before: Context builder with closure
local_state = {"counter": 0}

async def build_context(ctx):
    local_state["counter"] += 1
    return {"count": local_state["counter"]}

# After: Use workflow state or external state management
async def build_context(ctx):
    # Access workflow-managed state
    count = ctx.get_metadata("counter", 0) + 1
    ctx.set_metadata("counter", count)
    return {"count": count}
```

---

## Execution Changes

### Decorator DSL Execution

```python
from maverick.dsl import WorkflowEngine

engine = WorkflowEngine()
async for event in engine.execute(my_workflow, input_data="test"):
    print(event)
result = engine.get_result()
```

### YAML Workflow Execution

```python
from maverick.dsl.serialization import WorkflowFile, WorkflowFileExecutor

# Load workflow
with open("workflow.yaml") as f:
    workflow = WorkflowFile.from_yaml(f.read())

# Execute
executor = WorkflowFileExecutor(registry=registry)
async for event in executor.execute(workflow, inputs={"input_data": "test"}):
    print(event)
result = executor.get_result()
```

### CLI Execution (Recommended)

The simplest approach is to use the Maverick CLI:

```bash
# Place workflow in one of the discovery locations:
# - .maverick/workflows/my-workflow.yaml (project)
# - ~/.config/maverick/workflows/my-workflow.yaml (user)

# Execute by name
maverick workflow run my-workflow -i input_data=test

# List available workflows
maverick workflow list

# Visualize workflow
maverick workflow viz my-workflow --format ascii
```

---

## Migration Checklist

- [ ] **Inventory**: List all decorator-based workflows in your codebase
- [ ] **Extract Lambdas**: Convert inline lambdas to named functions
- [ ] **Create YAML Files**: Convert each `@workflow` to a `.yaml` file
- [ ] **Register Components**: Create registration modules for actions, agents, generators, context builders
- [ ] **Update Tests**: Migrate test code to use `WorkflowFileExecutor`
- [ ] **Update Documentation**: Replace decorator examples with YAML examples
- [ ] **Update CI/CD**: Use `maverick workflow run` commands instead of Python execution
- [ ] **Validate**: Test each migrated workflow thoroughly

---

## Example: Complete Migration

### Before (Single File)

```python
# workflows/feature_impl.py
from maverick.dsl import workflow, step
from maverick.agents import ImplementerAgent, CodeReviewerAgent

@workflow(name="feature-implementation")
def feature_impl(spec_path: str):
    # Parse spec
    spec = yield step("parse").python(
        action=lambda p: parse_spec_file(p),
        args=(spec_path,)
    )

    # Implement
    impl = yield step("implement").agent(
        agent=ImplementerAgent(),
        context={"spec": spec}
    )

    # Review
    review = yield step("review").agent(
        agent=CodeReviewerAgent(),
        context=lambda ctx: {"files": ctx.results["implement"].output.files}
    )

    return {"implementation": impl, "review": review}
```

### After (Organized Structure)

```
.maverick/
└── workflows/
    ├── feature-implementation.yaml
    └── support/
        ├── __init__.py
        ├── actions.py
        └── context_builders.py
```

**File: `.maverick/workflows/feature-implementation.yaml`**

```yaml
version: "1.0"
name: feature-implementation
description: Full feature implementation workflow

inputs:
  spec_path:
    type: string
    required: true
    description: Path to feature specification

steps:
  - name: parse
    type: python
    action: parse_spec_file
    args:
      - ${{ inputs.spec_path }}

  - name: implement
    type: agent
    agent: implementer
    context:
      spec: ${{ steps.parse.output }}

  - name: review
    type: agent
    agent: reviewer
    context_builder: build_review_context

outputs:
  implementation: ${{ steps.implement.output }}
  review: ${{ steps.review.output }}
```

**File: `.maverick/workflows/support/actions.py`**

```python
def parse_spec_file(path: str) -> dict:
    """Parse specification file."""
    with open(path) as f:
        # Parse implementation
        return {"content": f.read()}
```

**File: `.maverick/workflows/support/context_builders.py`**

```python
from maverick.dsl.context import WorkflowContext

async def build_review_context(ctx: WorkflowContext) -> dict:
    """Build context for code review step."""
    return {"files": ctx.results["implement"].output.files}
```

**File: `.maverick/workflows/support/__init__.py`**

```python
"""Support modules for custom workflows."""
from maverick.dsl.serialization import registry
from maverick.agents import ImplementerAgent, CodeReviewerAgent

from .actions import parse_spec_file
from .context_builders import build_review_context

# Register all components
registry.register_action("parse_spec_file", parse_spec_file)
registry.register_agent("implementer", ImplementerAgent)
registry.register_agent("reviewer", CodeReviewerAgent)
registry.register_context_builder("build_review_context", build_review_context)
```

**Usage**:

```bash
# Execute via CLI (automatically discovers and registers components)
maverick workflow run feature-implementation -i spec_path=specs/my-feature.md
```

---

## Benefits of YAML Approach

### Before (Decorator DSL)
- Required Python knowledge to author workflows
- No automatic discovery mechanism
- Limited shareability (Python code)
- No schema validation until execution
- Hard to visualize workflow structure
- Mixed workflow definition with business logic

### After (YAML Workflows)
- Declarative, readable syntax accessible to non-developers
- Automatic discovery from project/user/built-in locations
- Easy to version control and share
- Schema validation at load time with clear error messages
- Built-in visualization (ASCII, Mermaid diagrams)
- Clean separation: YAML for structure, Python for logic

---

## Deferred Features

The following decorator DSL features are not yet supported in YAML workflows but are tracked for future implementation:

1. **`RetryStep` wrapper** - Use `retry` field on validate steps (partial support)
2. **`ErrorHandlerStep` wrapper** - Use `on_failure` field (partial support)
3. **Dynamic step conditions** - Complex predicates (GitHub issue: TBD)

If you require these features, please open a GitHub issue with your use case.

---

## Getting Help

- **Documentation**: See `specs/022-workflow-dsl/quickstart.md` for YAML workflow examples
- **Built-in Examples**: Explore workflows in `src/maverick/library/workflows/`
- **CLI Help**: Run `maverick workflow --help`
- **GitHub Issues**: Report migration challenges or request features

---

## Summary

The migration from decorator DSL to YAML workflows is straightforward:

1. Convert workflow structure to YAML format
2. Extract lambdas to named functions
3. Register components (actions, agents, builders)
4. Update execution code to use `WorkflowFileExecutor` or CLI

The YAML approach provides better discoverability, shareability, and user experience while reducing maintenance burden. All built-in Maverick workflows demonstrate best practices for YAML workflow authoring.
