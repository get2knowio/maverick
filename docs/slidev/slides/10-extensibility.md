---
layout: section
---

# Part 10: Extensibility

Customize Maverick with your own agents, workflows, and tools

---
layout: default
---

# Component Registry System

## Central Registry Facade

<div v-click>

All extensible components are registered through a unified registry:

```python
from maverick.dsl.discovery.registry import registry

# Register custom components
registry.actions.register("action_name", callable)
registry.agents.register("agent_name", AgentClass)
registry.generators.register("gen_name", GeneratorClass)
registry.context_builders.register("builder", fn)
registry.workflows.register("workflow", definition)
```

</div>

<div v-click class="mt-6">

## Discovery Precedence

Components are discovered in this order (higher precedence overrides lower):

1. **Project**: `.maverick/workflows/` - Project-specific customizations
2. **User**: `~/.config/maverick/workflows/` - User-wide customizations
3. **Built-in**: Packaged with Maverick - Default implementations

</div>

<div v-click class="mt-6 p-4 bg-blue-50 dark:bg-blue-900 rounded">

**Example**: Create `.maverick/workflows/my_workflow.yaml` to override built-in workflow

</div>

---
layout: default
---

# Creating Custom Agents

## Step-by-Step Agent Creation

<div v-click>

Inherit from `MaverickAgent` base class:

```python
from maverick.agents.base import MaverickAgent
from maverick.agents.result import AgentResult
from maverick.agents.context import AgentContext

class MyCustomAgent(MaverickAgent[AgentContext, AgentResult]):
    """Custom agent for specialized tasks."""

    def __init__(self):
        super().__init__(
            name="my_custom_agent",
            system_prompt="You are a specialized agent for...",
            allowed_tools=["Read", "Write", "Edit"],  # Principle of least privilege
            model="claude-sonnet-4-5-20250929",  # Optional, defaults to latest
        )

    async def execute(self, context: AgentContext) -> AgentResult:
        """Execute the agent's task."""
        messages = []
        async for msg in self.query(
            prompt=f"Process: {context.inputs}",
            cwd=context.cwd,
        ):
            messages.append(msg)

        return AgentResult.success_result(
            output=self._extract_all_text(messages),
            usage=self._extract_usage(messages),
        )
```

</div>

---
layout: default
---

# Creating Custom Agents (continued)

## Register Your Agent

<div v-click>

Use the decorator pattern for automatic registration:

```python
from maverick.agents.registry import register

@register("my_custom_agent")
class MyCustomAgent(MaverickAgent[AgentContext, AgentResult]):
    def __init__(self):
        super().__init__(
            name="my_custom_agent",
            system_prompt="You are a specialized agent for...",
            allowed_tools=["Read", "Write", "Edit", "Bash"],
        )

    async def execute(self, context: AgentContext) -> AgentResult:
        # Implementation here
        ...
```

</div>

<div v-click class="mt-6">

Or register explicitly:

```python
from maverick.agents.registry import registry

registry.register("my_custom_agent", MyCustomAgent)
```

</div>

<div v-click class="mt-6">

## Use in Workflows

```python
# Instantiate and use
agent = registry.create("my_custom_agent")
result = await agent.execute(context)
```

</div>

---
layout: two-cols-header
---

# Creating Custom Workflows

::left::

<div v-click>

## Python Approach

Decorator-based workflow definition:

```python
from maverick.dsl.decorator import workflow
from maverick.dsl.builder import step
from maverick.agents.registry import registry

@workflow(
    name="my_workflow",
    description="Custom workflow"
)
async def my_workflow(ctx):
    # Step 1: Initialize
    yield step("init").python(
        action=init_action,
        args=(ctx.inputs,)
    )

    # Step 2: Process with agent
    agent = registry.create("my_custom_agent")
    result = yield step("process").agent(
        agent=agent,
        context={"data": ctx.get_step_output("init")},
    )

    # Step 3: Generate summary
    summary = yield step("finalize").generate(
        generator=SummaryGenerator(),
        context={"result": result},
    )

    return {"summary": summary}
```

</div>

::right::

<div v-click>

## YAML Approach

Declarative workflow definition:

```yaml
version: "1.0"
name: my_workflow
description: Custom workflow

inputs:
  data_file:
    type: string
    required: true

steps:
  - name: init
    type: python
    action: init_action
    args:
      - inputs.data_file

  - name: process
    type: agent
    agent: my_custom_agent
    context:
      data: steps.init.output

  - name: finalize
    type: generate
    generator: summary_generator
    context:
      result: steps.process.output

outputs:
  summary: steps.finalize.output
```

</div>

---
layout: default
---

# Advanced Workflow Features

## Flow Control & Error Handling

<div class="grid grid-cols-2 gap-4">

<div v-click>

### Conditional Execution

```python
yield step("deploy").when(
    lambda ctx: ctx.inputs["env"] == "prod"
).python(action=deploy_to_prod)
```

</div>

<div v-click>

### Retry with Backoff

```python
yield step("api_call").retry(
    max_attempts=3,
    backoff=2.0  # Exponential backoff
).python(action=call_api)
```

</div>

<div v-click>

### Error Handling

```python
yield step("risky").on_error(
    handler=lambda ctx, err: step("fallback").python(safe_action)
).python(action=risky_action)
```

</div>

<div v-click>

### Rollback on Failure

```python
yield step("deploy").with_rollback(
    rollback=lambda ctx: undeploy()
).python(action=deploy)
```

</div>

</div>

<div v-click class="mt-6">

## Parallel Execution

```python
from maverick.dsl.builder import parallel

yield parallel(
    "reviews",
    step("lint").python(run_lint),
    step("typecheck").python(run_typecheck),
    step("test").python(run_tests),
)
```

</div>

---
layout: default
---

# Custom Context Builders

## Build Agent Context Dynamically

<div v-click>

Context builders prepare input for agents:

```python
from maverick.dsl.context import WorkflowContext

async def my_context_builder(ctx: WorkflowContext) -> dict:
    """Build context for an agent from workflow state."""
    return {
        "files": await get_changed_files(ctx.cwd),
        "previous_result": ctx.get_step_output("previous_step"),
        "config": ctx.config.model_dump(),
    }

# Register it
from maverick.dsl.discovery.registry import registry
registry.context_builders.register("my_builder", my_context_builder)
```

</div>

<div v-click class="mt-6">

## Use in Workflow Steps

```python
yield step("analyze").agent(
    agent=MyAgent(),
    context=my_context_builder,  # Pass the builder directly
)
```

</div>

<div v-click class="mt-6 p-4 bg-yellow-50 dark:bg-yellow-900 rounded">

**Note**: Context builders are async functions that receive `WorkflowContext` and return a dict

</div>

---
layout: default
---

# Fragment Override System

## Override Built-in Fragments

<div v-click>

Fragments are reusable sub-workflows that follow the same precedence rules:

```
PROJECT (.maverick/workflows/fragments/)
  ↓ overrides
USER (~/.config/maverick/workflows/fragments/)
  ↓ overrides
BUILTIN (maverick.library.fragments/)
```

</div>

<div v-click class="mt-6">

### Example: Customize Validation

Create `.maverick/workflows/fragments/validate_and_fix.yaml`:

```yaml
version: "1.0"
name: validate_and_fix
description: Custom validation with retry

inputs:
  stages:
    type: list
    default: ["format", "lint", "test", "custom_check"]

steps:
  - name: run_validation
    type: validate
    stages: inputs.stages
    retry: 5  # More retries than built-in
    on_failure:
      name: auto_fix
      type: python
      action: my_custom_fix_action
```

</div>

<div v-click class="mt-4 p-4 bg-green-50 dark:bg-green-900 rounded">

**All workflows using `validate_and_fix` fragment now use your custom version!**

</div>

---
layout: default
---

# Workflow Discovery & Testing

## List Available Workflows

<div v-click>

```bash
# List all discovered workflows
maverick workflow list

# Output shows source:
# - my_workflow (project)
# - fly (builtin, overridden by project)
# - refuel (builtin)
```

</div>

<div v-click class="mt-6">

## Inspect Workflow Details

```bash
# Show workflow definition and inputs
maverick workflow show my_workflow

# Visualize workflow graph
maverick workflow viz my_workflow --format ascii
```

</div>

<div v-click class="mt-6">

## Test Your Workflow

```bash
# Dry run (preview without executing)
maverick workflow run my_workflow \
  -i data_file=test.json \
  --dry-run

# Run with verbose output
maverick -vv workflow run my_workflow \
  -i data_file=test.json
```

</div>

---
layout: default
---

# Best Practices for Extensibility

<div class="grid grid-cols-2 gap-4">

<div v-click>

## Agent Development

- **Type Safety**: Use Generic types for context/result
- **Tool Permissions**: Minimal allowed_tools (principle of least privilege)
- **Error Handling**: Wrap SDK errors in MaverickError hierarchy
- **Testing**: Write unit tests for execute() method
- **Documentation**: Clear docstrings with Args/Returns/Raises

</div>

<div v-click>

## Workflow Development

- **Naming**: Use descriptive, kebab-case names
- **Validation**: Define clear input types with validation
- **Composability**: Break into reusable fragments
- **Error Recovery**: Use retry/on_error/rollback
- **Documentation**: Comment complex steps and decisions

</div>

<div v-click>

## Testing Strategy

```python
# Test agent in isolation
async def test_my_agent():
    agent = MyCustomAgent()
    context = AgentContext(cwd="/tmp", inputs={})
    result = await agent.execute(context)
    assert result.success
```

</div>

<div v-click>

## Deployment

```
project-root/
├── .maverick/
│   └── workflows/
│       ├── my_workflow.yaml
│       └── fragments/
│           └── custom_fragment.yaml
└── maverick.yaml  # Project config
```

</div>

</div>

<div v-click class="mt-6 p-4 bg-blue-50 dark:bg-blue-900 rounded">

**Tip**: Start by overriding fragments, then build custom workflows as patterns emerge

</div>
