# Quickstart: Fly Workflow Interface

**Feature**: 009-fly-workflow

## Overview

This spec defines the interface for the Fly Workflow - Maverick's main development workflow that orchestrates feature implementation from spec to PR. This is an **interface-only** implementation; the actual workflow execution will be implemented in Spec 26.

## Prerequisites

- Python 3.10+
- Maverick project structure with existing modules:
  - `maverick.agents.result` (AgentResult, AgentUsage)
  - `maverick.models.validation` (ValidationWorkflowResult)
  - `maverick.config` (MaverickConfig)

## Quick Start

### 1. Import the Interface Types

```python
from maverick.workflows.fly import (
    # Enum
    WorkflowStage,
    # Configuration
    FlyInputs,
    FlyConfig,
    # State/Result
    WorkflowState,
    FlyResult,
    # Progress Events
    FlyWorkflowStarted,
    FlyStageStarted,
    FlyStageCompleted,
    FlyWorkflowCompleted,
    FlyWorkflowFailed,
    # Workflow
    FlyWorkflow,
)
```

### 2. Create Workflow Inputs

```python
from pathlib import Path

# Minimal inputs (branch name only)
inputs = FlyInputs(branch_name="feature/my-feature")

# Full inputs with all options
inputs = FlyInputs(
    branch_name="feature/my-feature",
    task_file=Path("specs/my-feature/tasks.md"),
    skip_review=False,
    skip_pr=False,
    draft_pr=True,
    base_branch="main",
)
```

### 3. Create Workflow Configuration

```python
# Using defaults
config = FlyConfig()

# Custom configuration
config = FlyConfig(
    parallel_reviews=True,
    max_validation_attempts=3,
    coderabbit_enabled=False,
    auto_merge=False,
    notification_on_complete=True,
)
```

### 4. Instantiate the Workflow

```python
workflow = FlyWorkflow(config=config)
```

### 5. Execute (Interface Only - Will Raise NotImplementedError)

```python
import asyncio

async def run_workflow():
    try:
        result = await workflow.execute(inputs)
    except NotImplementedError as e:
        print(f"Expected: {e}")
        # "FlyWorkflow.execute() is not implemented.
        #  Full implementation will be provided in Spec 26..."

asyncio.run(run_workflow())
```

## Working with Types

### WorkflowStage Enum

```python
# Access stages
stage = WorkflowStage.IMPLEMENTATION
print(stage.value)  # "implementation"
print(str(stage))   # "implementation"

# Check terminal states
terminal_stages = {WorkflowStage.COMPLETE, WorkflowStage.FAILED}
is_terminal = stage in terminal_stages  # False
```

### WorkflowState

```python
from datetime import datetime
from maverick.workflows.fly import WorkflowState, WorkflowStage

# Create initial state
state = WorkflowState(
    stage=WorkflowStage.INIT,
    branch="feature/my-feature",
)

# Update state (mutable)
state.stage = WorkflowStage.IMPLEMENTATION
state.errors.append("Something went wrong")
state.completed_at = datetime.now()
```

### Progress Events

```python
from maverick.workflows.fly import (
    FlyWorkflowStarted,
    FlyStageStarted,
    FlyStageCompleted,
)

# Events are immutable dataclasses
started = FlyWorkflowStarted(inputs=inputs)
stage_started = FlyStageStarted(stage=WorkflowStage.VALIDATION)

# Pattern matching for event handling
def handle_event(event: FlyProgressEvent) -> None:
    match event:
        case FlyWorkflowStarted(inputs=inp):
            print(f"Workflow started for branch: {inp.branch_name}")
        case FlyStageStarted(stage=s):
            print(f"Stage started: {s.value}")
        case FlyStageCompleted(stage=s, result=r):
            print(f"Stage {s.value} completed")
        case FlyWorkflowCompleted(result=r):
            print(f"Success: {r.summary}")
        case FlyWorkflowFailed(error=e):
            print(f"Failed: {e}")
```

### FlyResult

```python
from maverick.agents.result import AgentUsage
from maverick.workflows.fly import FlyResult, WorkflowState, WorkflowStage

# Create result (typically done by workflow, not manually)
usage = AgentUsage(
    input_tokens=1000,
    output_tokens=500,
    total_cost_usd=0.015,
    duration_ms=5000,
)

result = FlyResult(
    success=True,
    state=state,
    summary="Fly workflow completed: 3 tasks implemented, validation passed, PR #42 created",
    token_usage=usage,
    total_cost_usd=0.015,
)

print(result.summary)
```

## Configuration Integration

FlyConfig integrates with MaverickConfig:

```python
from maverick.config import load_config

# Load config from maverick.yaml
config = load_config()

# Access fly config
fly_config = config.fly
print(f"Max validation attempts: {fly_config.max_validation_attempts}")
```

YAML configuration:

```yaml
# maverick.yaml
fly:
  parallel_reviews: true
  max_validation_attempts: 3
  coderabbit_enabled: false
  auto_merge: false
  notification_on_complete: true
```

## Testing the Interface

```python
import pytest
from maverick.workflows.fly import FlyInputs, FlyWorkflow, WorkflowStage

def test_fly_inputs_validates_branch_name():
    """Test that empty branch_name is rejected."""
    with pytest.raises(ValueError):
        FlyInputs(branch_name="")

def test_fly_inputs_defaults():
    """Test default values for optional fields."""
    inputs = FlyInputs(branch_name="test")
    assert inputs.skip_review is False
    assert inputs.skip_pr is False
    assert inputs.draft_pr is False
    assert inputs.base_branch == "main"
    assert inputs.task_file is None

def test_workflow_stage_string_representation():
    """Test enum string values."""
    assert WorkflowStage.INIT.value == "init"
    assert str(WorkflowStage.IMPLEMENTATION) == "implementation"

@pytest.mark.asyncio
async def test_fly_workflow_raises_not_implemented():
    """Test that execute raises NotImplementedError."""
    workflow = FlyWorkflow()
    inputs = FlyInputs(branch_name="test")

    with pytest.raises(NotImplementedError) as exc_info:
        await workflow.execute(inputs)

    assert "Spec 26" in str(exc_info.value)
```

## Next Steps

1. **This spec (009)**: Defines the interface types and stub implementation
2. **Spec 26**: Will implement the full workflow logic using the workflow DSL

The interface is designed to be stable - consumers can code against these types now, and the implementation will be provided later without breaking changes.
