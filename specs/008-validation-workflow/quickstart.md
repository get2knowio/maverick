# Quickstart: Validation Workflow

**Feature**: 008-validation-workflow
**Date**: 2025-12-15

## Overview

The ValidationWorkflow provides a reusable orchestration layer for running project validation stages (format, lint, build, test) with automatic fix attempts. It yields async progress updates for TUI consumption and supports cancellation.

## Basic Usage

### Running Default Python Validation

```python
from maverick.workflows.validation import ValidationWorkflow
from maverick.models.validation import DEFAULT_PYTHON_STAGES

# Create workflow with default stages
workflow = ValidationWorkflow(stages=DEFAULT_PYTHON_STAGES)

# Run and consume progress updates
async for progress in workflow.run():
    print(f"{progress.stage}: {progress.status.value}")
    if progress.message:
        print(f"  {progress.message}")

# Get final result
result = workflow.get_result()
print(f"Success: {result.success}")
print(f"Summary: {result.summary}")
```

### With Fix Agent

```python
from maverick.agents.issue_fixer import IssueFixerAgent
from maverick.workflows.validation import ValidationWorkflow
from maverick.models.validation import DEFAULT_PYTHON_STAGES

# Create a fix agent (or use any MaverickAgent that can fix code)
fix_agent = IssueFixerAgent()

# Create workflow with fix agent
workflow = ValidationWorkflow(
    stages=DEFAULT_PYTHON_STAGES,
    fix_agent=fix_agent,
)

# When a fixable stage fails, workflow will invoke fix_agent
async for progress in workflow.run():
    if progress.fix_attempt > 0:
        print(f"Fix attempt #{progress.fix_attempt} for {progress.stage}")
```

### Custom Stage Configuration

```python
from maverick.models.validation import ValidationStage, ValidationWorkflowConfig
from maverick.workflows.validation import ValidationWorkflow

# Define custom stages
custom_stages = [
    ValidationStage(
        name="format",
        command=["black", "."],
        fixable=True,
        max_fix_attempts=2,
    ),
    ValidationStage(
        name="lint",
        command=["pylint", "src/"],
        fixable=True,
        max_fix_attempts=3,
    ),
    ValidationStage(
        name="test",
        command=["pytest", "-v"],
        fixable=False,  # Tests typically can't be auto-fixed
        max_fix_attempts=0,
    ),
]

# Configure workflow
config = ValidationWorkflowConfig(
    cwd=Path("/path/to/project"),
    dry_run=False,
    stop_on_failure=True,  # Stop at first failure
)

workflow = ValidationWorkflow(stages=custom_stages, config=config)
```

### Dry-Run Mode

```python
from maverick.models.validation import ValidationWorkflowConfig

config = ValidationWorkflowConfig(dry_run=True)
workflow = ValidationWorkflow(stages=DEFAULT_PYTHON_STAGES, config=config)

# No commands are executed - only reports what would run
async for progress in workflow.run():
    print(f"Would run: {progress.message}")
```

### Cancellation

```python
import asyncio

async def run_with_timeout():
    workflow = ValidationWorkflow(stages=DEFAULT_PYTHON_STAGES)

    async def consume():
        async for progress in workflow.run():
            print(f"{progress.stage}: {progress.status.value}")

    # Start consumption
    task = asyncio.create_task(consume())

    # Cancel after 30 seconds
    await asyncio.sleep(30)
    workflow.cancel()

    # Wait for graceful shutdown
    await task

    result = workflow.get_result()
    if result.cancelled:
        print("Workflow was cancelled")
        print(f"Completed {result.passed_count} stages before cancellation")
```

## Integration with TUI

```python
from textual.app import App
from textual.widgets import Static

class ValidationScreen(App):
    async def run_validation(self):
        workflow = ValidationWorkflow(stages=DEFAULT_PYTHON_STAGES)

        async for progress in workflow.run():
            # Update TUI with progress
            self.update_stage_status(progress.stage, progress.status)

            if progress.status == StageStatus.IN_PROGRESS:
                self.show_spinner(progress.stage)
            elif progress.status == StageStatus.PASSED:
                self.show_checkmark(progress.stage)
            elif progress.status == StageStatus.FIXED:
                self.show_checkmark(progress.stage, fixed=True)
            elif progress.status == StageStatus.FAILED:
                self.show_error(progress.stage, progress.message)

        result = workflow.get_result()
        self.show_summary(result.summary)
```

## Result Inspection

```python
result = workflow.get_result()

# Overall status
print(f"Success: {result.success}")
print(f"Duration: {result.total_duration_ms}ms")

# Per-stage breakdown
for stage_result in result.stage_results:
    status_emoji = {
        StageStatus.PASSED: "✓",
        StageStatus.FIXED: "✓*",
        StageStatus.FAILED: "✗",
        StageStatus.CANCELLED: "⊘",
    }.get(stage_result.status, "?")

    print(f"  {status_emoji} {stage_result.stage_name}")
    if stage_result.fix_attempts > 0:
        print(f"    Fix attempts: {stage_result.fix_attempts}")
    if stage_result.error_message:
        print(f"    Error: {stage_result.error_message}")

# Summary statistics
print(f"\nSummary: {result.summary}")
print(f"  Passed: {result.passed_count}")
print(f"  Failed: {result.failed_count}")
print(f"  Fixed: {result.fixed_count}")
```

## Error Handling

```python
from maverick.exceptions import WorkflowError

try:
    async for progress in workflow.run():
        handle_progress(progress)
except WorkflowError as e:
    print(f"Workflow error: {e.message}")
    # Partial results may still be available
    if hasattr(workflow, '_result') and workflow._result:
        result = workflow.get_result()
        print(f"Partial results: {result.passed_count} stages completed")
```

## Testing Workflows

```python
import pytest
from unittest.mock import AsyncMock, MagicMock

@pytest.mark.asyncio
async def test_validation_workflow_passes():
    """Test that workflow reports success when all stages pass."""
    stages = [
        ValidationStage(name="test", command=["true"], fixable=False),
    ]

    workflow = ValidationWorkflow(stages=stages)

    progress_events = []
    async for progress in workflow.run():
        progress_events.append(progress)

    result = workflow.get_result()
    assert result.success
    assert result.passed_count == 1

@pytest.mark.asyncio
async def test_workflow_with_mock_fix_agent():
    """Test fix agent integration."""
    mock_agent = MagicMock()
    mock_agent.execute = AsyncMock(return_value=...)

    workflow = ValidationWorkflow(
        stages=DEFAULT_PYTHON_STAGES,
        fix_agent=mock_agent,
    )

    # ... test fix agent is called on failures
```

## Key Classes Reference

| Class | Purpose |
|-------|---------|
| `ValidationWorkflow` | Main orchestrator - call `run()` to execute |
| `ValidationStage` | Stage configuration (name, command, fixability) |
| `ValidationWorkflowConfig` | Workflow options (dry_run, cwd) |
| `ProgressUpdate` | Event yielded during execution |
| `StageResult` | Outcome of a single stage |
| `ValidationWorkflowResult` | Aggregate result of all stages |
| `StageStatus` | Enum: PENDING, IN_PROGRESS, PASSED, FAILED, FIXED, CANCELLED |

## File Locations

- **Workflow**: `src/maverick/workflows/validation.py`
- **Models**: `src/maverick/models/validation.py`
- **Tests**: `tests/unit/workflows/test_validation.py`
