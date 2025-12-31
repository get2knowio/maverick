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
from maverick.dsl.serialization.registry import component_registry

# Register custom components
component_registry.actions.register("action_name", callable)
component_registry.agents.register("agent_name", AgentClass)
component_registry.generators.register("gen_name", GeneratorClass)
component_registry.context_builders.register("builder_name", fn)
component_registry.workflows.register("workflow_name", definition)
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

<div v-click>

Inherit from `MaverickAgent` base class:

```python
from maverick.agents.base import MaverickAgent
from maverick.agents.result import AgentResult

class MyCustomAgent(MaverickAgent[AgentContext, AgentResult]):
    def __init__(self):
        super().__init__(
            name="my_custom_agent",
            system_prompt="You are a specialized agent...",
            allowed_tools=["Read", "Write", "Edit"],
        )

    async def execute(self, context: AgentContext) -> AgentResult:
        messages = [m async for m in self.query(f"Process: {context.inputs}")]
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

<div class="grid grid-cols-2 gap-4">

<div v-click>

## Register with Decorator

```python
from maverick.agents.registry import register

@register("my_custom_agent")
class MyCustomAgent(MaverickAgent):
    ...
```

Or explicitly:

```python
registry.register("my_custom_agent", MyCustomAgent)
```

</div>

<div v-click>

## Use in Workflows

```yaml
steps:
  - name: analyze
    type: agent
    agent: my_custom_agent
    context:
      data: ${{ steps.load.output }}
```

Or in Python:

```python
agent = registry.create("my_custom_agent")
result = await agent.execute(context)
```

</div>

</div>

---
layout: default
---

# Creating Custom Workflows

<div class="grid grid-cols-2 gap-4">

<div v-click>

## YAML Workflow Definition

```yaml
# .maverick/workflows/my-workflow.yaml
version: "1.0"
name: my-workflow
inputs:
  data_file: { type: string, required: true }

steps:
  - name: init
    type: python
    action: init_action
    args: [${{ inputs.data_file }}]

  - name: process
    type: agent
    agent: my_custom_agent
    context: { data: ${{ steps.init.output }} }

outputs:
  result: ${{ steps.process.output }}
```

</div>

<div v-click>

## Execute via CLI

```bash
maverick workflow run my-workflow \
  -i data_file=data.json
```

## Discovery Locations

1. **Project**: `.maverick/workflows/`
2. **User**: `~/.config/maverick/workflows/`
3. **Built-in**: Packaged defaults

<div class="mt-2 p-2 bg-blue-500/20 border border-blue-500 rounded text-xs">
Project overrides User overrides Built-in
</div>

</div>

</div>

---
layout: default
---

# Advanced Workflow Features

<div class="grid grid-cols-2 gap-4">

<div v-click>

### Conditional + Retry

```yaml
- name: deploy
  type: python
  action: deploy
  when: ${{ inputs.env == "prod" }}
  retry: 3
```

### Error Handling

```yaml
- name: risky
  action: risky_op
  on_failure:
    action: safe_fallback
  rollback:
    action: undo_op
```

</div>

<div v-click>

### Parallel Execution

```yaml
- name: all_checks
  type: parallel
  steps:
    - name: lint
      action: run_lint
    - name: typecheck
      action: run_typecheck
    - name: test
      action: run_tests
```

</div>

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
from maverick.dsl.serialization.registry import component_registry
component_registry.context_builders.register("my_builder", my_context_builder)
```

</div>

<div v-click class="mt-6">

## Use in Workflow Steps

```yaml
steps:
  - name: analyze
    type: agent
    agent: my_agent
    context_builder: my_context_builder  # Reference by name
```

</div>

<div v-click class="mt-6 p-4 bg-yellow-50 dark:bg-yellow-900 rounded">

**Note**: Context builders are registered async functions that receive `WorkflowContext` and return a dict

</div>

---
layout: default
---

# Fragment Override System

<div class="grid grid-cols-2 gap-4">

<div v-click>

## Precedence Order

```
PROJECT (.maverick/workflows/fragments/)
  ↓ overrides
USER (~/.config/maverick/workflows/fragments/)
  ↓ overrides
BUILTIN (maverick.library.fragments/)
```

</div>

<div v-click>

## Example: Custom Validation

```yaml
# .maverick/workflows/fragments/validate_and_fix.yaml
version: "1.0"
name: validate_and_fix
inputs:
  stages: { type: list, default: [format, lint, test] }

steps:
  - name: validate
    type: validate
    stages: inputs.stages
    retry: 5
    on_failure:
      name: fix
      type: python
      action: my_custom_fix
```

</div>

</div>

<div v-click class="mt-4 p-2 bg-green-500/20 border border-green-500 rounded text-sm">
All workflows using `validate_and_fix` fragment now use your custom version!
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
# Test workflow execution
async def test_my_workflow():
    workflow = WorkflowFile.from_yaml(yaml_content)
    executor = WorkflowFileExecutor(registry=registry)

    async for event in executor.execute(workflow, inputs={"data": "test"}):
        pass

    result = executor.get_result()
    assert result.success
```

</div>

<div v-click>

## Project Structure

```
project-root/
├── .maverick/
│   └── workflows/
│       ├── my-workflow.yaml
│       ├── fragments/
│       │   └── custom-fragment.yaml
│       └── support/
│           ├── actions.py       # Custom actions
│           └── context_builders.py
└── maverick.yaml  # Project config
```

</div>

</div>

<div v-click class="mt-6 p-4 bg-blue-50 dark:bg-blue-900 rounded">

**Tip**: Start by overriding fragments, then build custom workflows as patterns emerge

</div>
