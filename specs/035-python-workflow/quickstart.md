# Quickstart: Authoring Python Workflows

**Feature Branch**: `035-python-workflow`
**Date**: 2026-02-26

## Overview

Python workflows replace the YAML DSL for Maverick's opinionated workflows. They use native Python control flow (loops, conditionals, try/except) with full IDE support (autocompletion, type checking, go-to-definition).

## Creating a New Python Workflow

### Step 1: Create the Package

```
src/maverick/workflows/my_workflow/
├── __init__.py
├── workflow.py
└── constants.py       # Optional: step names, defaults
```

### Step 2: Implement the Workflow

```python
# src/maverick/workflows/my_workflow/workflow.py
from __future__ import annotations

from typing import Any

from maverick.workflows.base import PythonWorkflow


class MyWorkflow(PythonWorkflow):
    """One-line description of what this workflow does."""

    async def _run(self, inputs: dict[str, Any]) -> Any:
        # Step 1: Do something
        await self.emit_step_started("step_one")
        try:
            result = await some_action(inputs["param"])
            await self.emit_step_completed("step_one", output=result)
        except Exception as e:
            await self.emit_step_failed("step_one", error=str(e))
            raise

        # Step 2: Do something else
        await self.emit_step_started("step_two")
        final = await another_action(result)
        await self.emit_step_completed("step_two", output=final)

        return {"result": final}
```

### Step 3: Export from Package

```python
# src/maverick/workflows/my_workflow/__init__.py
from __future__ import annotations

from maverick.workflows.my_workflow.workflow import MyWorkflow

__all__ = ["MyWorkflow"]
```

## Using Actions

Import actions directly for type safety:

```python
from maverick.library.actions.preflight import run_preflight_checks
from maverick.library.actions.workspace import create_fly_workspace
from maverick.library.actions.jj import jj_commit_bead, jj_snapshot_operation

async def _run(self, inputs: dict[str, Any]) -> Any:
    # Direct import gives IDE autocompletion and type checking
    preflight = await run_preflight_checks(
        check_api=True,
        check_git=True,
        check_jj=True,
    )
    await self.emit_step_completed("preflight", output=preflight)
```

The `self.registry` is also available for dynamic dispatch:

```python
# Dynamic lookup (e.g., user-configured components)
action = self.registry.actions.get("my_action")
result = await action(**kwargs)
```

## Configuration Resolution

Use `resolve_step_config()` to get merged configuration:

```python
async def _run(self, inputs: dict[str, Any]) -> Any:
    # Resolves: built-in defaults + maverick.yaml overrides
    config = self.resolve_step_config("implement")

    # Use config for agent steps
    result = await self.step_executor.execute(
        step_name="implement",
        agent_name="implementer",
        prompt=context,
        config=config,
    )
```

Configuration in `maverick.yaml`:

```yaml
steps:
  implement:
    mode: agent
    autonomy: consultant
    timeout: 600
  review:
    model_id: claude-sonnet-4-5-20250514
```

## Progress Events

Emit structured events for CLI rendering:

```python
# Step lifecycle
await self.emit_step_started("my_step")
await self.emit_step_completed("my_step", output=result)
await self.emit_step_failed("my_step", error="something broke")

# Informational output
await self.emit_output("my_step", "Processing item 3/10...", level="info")
await self.emit_output("my_step", "All items processed", level="success")
await self.emit_output("my_step", "Skipping optional check", level="warning")
```

## Rollback Registration

Register cleanup actions that run on workflow failure:

```python
async def _run(self, inputs: dict[str, Any]) -> Any:
    workspace = await create_fly_workspace(...)
    await self.emit_step_completed("create_workspace", output=workspace)

    # Register rollback — runs if workflow fails after this point
    self.register_rollback(
        "workspace_teardown",
        lambda: workspace_manager.teardown(),
    )

    # If anything below raises, workspace_teardown runs automatically
    await self.emit_step_started("implement")
    ...
```

## Checkpointing

Save and restore state for long-running workflows:

```python
async def _run(self, inputs: dict[str, Any]) -> Any:
    # Load existing checkpoint (if resuming)
    checkpoint = await self.load_checkpoint()
    completed_beads = checkpoint.get("completed_beads", []) if checkpoint else []

    for bead in all_beads:
        if bead["id"] in completed_beads:
            continue  # Skip already-completed beads

        # Process bead...
        await self._process_bead(bead)

        # Save checkpoint after each bead
        completed_beads.append(bead["id"])
        await self.save_checkpoint({
            "completed_beads": completed_beads,
            "workspace_path": str(workspace_path),
        })
```

## Testing

Test with standard pytest — no YAML fixtures or registry bootstrapping:

```python
# tests/unit/workflows/test_my_workflow.py
from __future__ import annotations

import pytest

from maverick.workflows.my_workflow import MyWorkflow


@pytest.fixture
def workflow(mock_config, mock_registry):
    """Create workflow with mock dependencies."""
    return MyWorkflow(
        config=mock_config,
        registry=mock_registry,
        workflow_name="test-workflow",
    )


@pytest.mark.asyncio
async def test_happy_path(workflow):
    """Workflow completes successfully with expected events."""
    events = []
    async for event in workflow.execute({"param": "value"}):
        events.append(event)

    # Final event is WorkflowCompleted
    assert events[-1].success is True

    # Check step events
    step_names = [e.step_name for e in events if hasattr(e, "step_name")]
    assert "step_one" in step_names
    assert "step_two" in step_names


@pytest.mark.asyncio
async def test_step_failure(workflow):
    """Workflow handles step failure gracefully."""
    events = []
    with pytest.raises(SomeError):
        async for event in workflow.execute({"param": "bad_value"}):
            events.append(event)

    # Workflow emits failure event
    assert events[-1].success is False


@pytest.mark.asyncio
async def test_config_resolution(workflow):
    """Step config merges defaults with overrides."""
    config = workflow.resolve_step_config("review")
    assert config.mode is not None
```

## CLI Integration

Wire a Python workflow to a CLI command:

```python
# src/maverick/cli/commands/my_command.py
from __future__ import annotations

import click

from maverick.cli.context import async_command
from maverick.cli.workflow_executor import (
    PythonWorkflowRunConfig,
    execute_python_workflow,
)
from maverick.workflows.my_workflow import MyWorkflow


@click.command()
@async_command
async def my_command(ctx: click.Context, param: str) -> None:
    """Run my workflow."""
    await execute_python_workflow(
        ctx,
        PythonWorkflowRunConfig(
            workflow_class=MyWorkflow,
            inputs={"param": param},
        ),
    )
```

## File Structure Convention

Follow the package-per-workflow pattern from Constitution Appendix A:

```
src/maverick/workflows/
├── __init__.py              # Re-exports all public workflow classes
├── base.py                  # PythonWorkflow ABC
├── my_workflow/
│   ├── __init__.py          # Export MyWorkflow
│   ├── workflow.py          # MyWorkflow(PythonWorkflow)
│   └── constants.py         # Step names, defaults (optional)
```

Keep each `workflow.py` under ~500 LOC. If it grows beyond that, split into helper modules within the package.
