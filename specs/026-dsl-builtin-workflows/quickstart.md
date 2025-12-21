# Quickstart: DSL-Based Built-in Workflows

**Spec**: 026-dsl-builtin-workflows
**Date**: 2025-12-20

This guide provides step-by-step instructions for implementing and testing the DSL-based built-in workflows.

## Prerequisites

1. **Maverick installed**: `pip install -e .` from repo root
2. **Dependencies available**:
   - GitHub CLI (`gh`) authenticated
   - Git configured with user.name and user.email
   - Python 3.10+
3. **Prior specs implemented**:
   - Spec 22-24: DSL infrastructure
   - Spec 25: Built-in workflow library
   - Spec 3-4: Agent implementations
   - Spec 19: Generator agents

## Implementation Order

Follow this order to ensure dependencies are available:

### Phase 1: Core Infrastructure

1. **Extend ComponentRegistry** (`src/maverick/dsl/serialization/registry.py`)
   ```python
   # Add agents and context_builders registries
   class ComponentRegistry:
       agents: TypedRegistry[type[MaverickAgent]]
       context_builders: TypedRegistry[ContextBuilder]
   ```

2. **Implement executor step types** (`src/maverick/dsl/serialization/executor.py`)
   - AgentStep execution
   - GenerateStep execution
   - ValidateStep execution
   - BranchStep execution
   - ParallelStep execution

### Phase 2: Python Actions

3. **Create actions module** (`src/maverick/library/actions/`)
   ```
   actions/
   ├── __init__.py          # register_all_actions()
   ├── git.py               # git_commit, git_push, create_git_branch
   ├── github.py            # fetch_github_issues, fetch_github_issue, create_github_pr
   ├── validation.py        # run_fix_retry_loop, generate_validation_report
   ├── workspace.py         # init_workspace
   ├── review.py            # gather_pr_context, run_coderabbit_review, combine_review_results
   └── refuel.py            # process_selected_issues, generate_refuel_summary
   ```

4. **Implement each action** following contracts in `specs/026-dsl-builtin-workflows/contracts/actions.py`

### Phase 3: Context Builders

5. **Create context builders** (`src/maverick/dsl/context_builders.py`)
   - `implementation_context`: Gather task file, project structure, conventions
   - `review_context`: Gather diff, changed files, conventions
   - `issue_fix_context`: Gather issue details, related files
   - `commit_message_context`: Gather diff, file stats, recent commits
   - `pr_body_context`: Gather commits, diff stats, validation results
   - `pr_title_context`: Gather commits, branch name, task summary

### Phase 4: Workflow Updates

6. **Update fly.yaml** to add:
   - `dry_run` input
   - Dry-run conditional steps
   - Checkpoint steps at key stages

7. **Create process_single_issue.yaml** for refuel sub-workflow

8. **Update existing workflow classes** (`src/maverick/workflows/`)
   - `FlyWorkflow`: Add DSL execution wrapper
   - `RefuelWorkflow`: Add DSL execution wrapper

### Phase 5: Testing

9. **Unit tests for actions** (`tests/unit/library/actions/`)
   - Mock external dependencies (git, gh)
   - Test each action in isolation

10. **Integration tests** (`tests/integration/test_builtin_workflows.py`)
    - Execute workflows with mocked runners
    - Verify step sequence and results

## Quick Validation

### Test Action Registration

```python
from maverick.library.actions import register_all_actions
from maverick.dsl.serialization.registry import ComponentRegistry

registry = ComponentRegistry()
register_all_actions(registry)

# Verify actions registered
assert registry.actions.has("init_workspace")
assert registry.actions.has("git_commit")
assert registry.actions.has("create_github_pr")
```

### Test Workflow Loading

```python
from maverick.dsl.discovery import DefaultWorkflowDiscovery

discovery = DefaultWorkflowDiscovery()
workflows = discovery.discover_all()

# Verify built-in workflows discovered
assert "fly" in [w.name for w in workflows]
assert "refuel" in [w.name for w in workflows]
assert "validate-and-fix" in [w.name for w in workflows]
```

### Test Workflow Execution (Dry Run)

```bash
# Execute fly workflow in dry-run mode
maverick workflow run fly \
  -i branch_name=test-branch \
  -i dry_run=true

# Expected: Logs planned operations, no actual changes
```

### Test Fragment Invocation

```python
import asyncio
from maverick.dsl.serialization import parse_workflow, ComponentRegistry
from maverick.dsl.serialization.executor import WorkflowFileExecutor

# Load validate-and-fix fragment
with open("src/maverick/library/fragments/validate_and_fix.yaml") as f:
    workflow = parse_workflow(f.read())

# Execute with mock registry
registry = ComponentRegistry()
# ... register mock actions ...

executor = WorkflowFileExecutor(registry=registry)

async def test():
    async for event in executor.execute(workflow, inputs={"max_attempts": 1}):
        print(event)

asyncio.run(test())
```

## Common Patterns

### Adding a New Action

```python
# 1. Define in actions module
async def my_action(arg1: str, arg2: int = 10) -> dict[str, Any]:
    """Do something."""
    # Implementation
    return {"result": "value"}

# 2. Register in __init__.py
def register_all_actions(registry: ComponentRegistry) -> None:
    registry.actions.register("my_action", my_action)

# 3. Use in YAML
# - name: my_step
#   type: python
#   action: my_action
#   kwargs:
#     arg1: ${{ inputs.some_value }}
#     arg2: 20
```

### Adding a Context Builder

```python
# 1. Define context builder
async def my_context(ctx: WorkflowContext) -> dict[str, Any]:
    """Build context for my agent."""
    # Gather data from files, git, etc.
    return {
        "key1": "value1",
        "key2": ctx.inputs.get("some_input"),
    }

# 2. Register
registry.context_builders.register("my_context", my_context)

# 3. Use in YAML
# - name: my_agent_step
#   type: agent
#   agent: my_agent
#   context: my_context
```

### Testing with Mocks

```python
import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_git_commit_action():
    with patch("maverick.library.actions.git.run_git") as mock_git:
        mock_git.return_value = AsyncMock(
            return_value=("abc123", "", 0)
        )

        from maverick.library.actions.git import git_commit
        result = await git_commit(message="test commit")

        assert result["success"]
        assert result["commit_sha"] == "abc123"
```

## Troubleshooting

### Action Not Found

```
ReferenceResolutionError: action 'my_action' not found
Available: ['init_workspace', 'git_commit', ...]
```

**Solution**: Ensure action is registered in `register_all_actions()`.

### Context Builder Not Found

```
ReferenceResolutionError: context_builder 'my_context' not found
```

**Solution**: Register context builder in ComponentRegistry before execution.

### Agent Step NotImplemented

```
NotImplementedError: Agent execution not yet implemented for agent 'implementer'
```

**Solution**: Implement `_execute_agent_step()` in WorkflowFileExecutor per research.md.

### Expression Evaluation Error

```
Error evaluating condition for step 'my_step': name 'inputs' is not defined
```

**Solution**: Ensure expression uses correct syntax: `${{ inputs.my_var }}`, not `${{ my_var }}`.

## Next Steps

After completing implementation:

1. Run full test suite: `PYTHONPATH=src pytest tests/`
2. Validate type safety: `mypy src/maverick/library/actions/`
3. Lint code: `ruff check src/maverick/library/actions/`
4. Execute fly workflow on a real feature branch
5. Update CLAUDE.md with new technology entries
