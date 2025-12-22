"""Integration tests for checkpoint and resume functionality."""

from __future__ import annotations

from pathlib import Path

import pytest

from maverick.dsl.checkpoint.store import FileCheckpointStore
from maverick.dsl.serialization import ComponentRegistry, WorkflowFileExecutor
from maverick.dsl.serialization.parser import parse_workflow


@pytest.fixture
def checkpoint_dir(tmp_path: Path) -> Path:
    """Create temporary checkpoint directory."""
    checkpoint_path = tmp_path / "checkpoints"
    checkpoint_path.mkdir(parents=True, exist_ok=True)
    return checkpoint_path


@pytest.fixture
def simple_workflow_yaml() -> str:
    """Simple workflow with checkpoint for testing."""
    return """
version: "1.0"
name: test-checkpoint
description: Test workflow with checkpoint

inputs:
  value:
    type: string
    required: true

steps:
  - name: step1
    type: python
    action: mock_action_1
    kwargs:
      input: ${{ inputs.value }}

  - name: checkpoint1
    type: checkpoint
    checkpoint_id: after_step1

  - name: step2
    type: python
    action: mock_action_2
    kwargs:
      input: ${{ steps.step1.output }}

  - name: step3
    type: python
    action: mock_action_3
    kwargs:
      input: ${{ steps.step2.output }}
"""


def mock_action_1(input: str) -> str:
    """Mock action for testing."""
    return f"step1_result_{input}"


def mock_action_2(input: str) -> str:
    """Mock action for testing."""
    return f"step2_result_{input}"


def mock_action_3(input: str) -> str:
    """Mock action for testing."""
    return f"step3_result_{input}"


@pytest.mark.asyncio
async def test_checkpoint_saves_state(
    checkpoint_dir: Path,
    simple_workflow_yaml: str,
) -> None:
    """Test that checkpoint saves workflow state."""
    # Parse workflow
    workflow = parse_workflow(simple_workflow_yaml)

    # Create registry and register test actions
    registry = ComponentRegistry()
    registry.actions.register("mock_action_1", mock_action_1)
    registry.actions.register("mock_action_2", mock_action_2)
    registry.actions.register("mock_action_3", mock_action_3)

    # Create executor with checkpoint store
    checkpoint_store = FileCheckpointStore(base_path=checkpoint_dir)
    executor = WorkflowFileExecutor(
        registry=registry,
        checkpoint_store=checkpoint_store,
    )

    # Execute workflow
    inputs = {"value": "test"}
    events = []
    async for event in executor.execute(workflow, inputs=inputs):
        events.append(event)

    # Verify workflow completed successfully
    result = executor.get_result()
    assert result.success

    # Verify checkpoint was saved
    checkpoints = await checkpoint_store.list_checkpoints("test-checkpoint")
    assert "after_step1" in checkpoints

    # Load checkpoint and verify data
    checkpoint_data = await checkpoint_store.load("test-checkpoint", "after_step1")
    assert checkpoint_data is not None
    assert checkpoint_data.workflow_name == "test-checkpoint"
    assert checkpoint_data.checkpoint_id == "after_step1"

    # Verify step results are saved
    step_names = [sr["name"] for sr in checkpoint_data.step_results]
    assert "step1" in step_names


@pytest.mark.asyncio
async def test_resume_from_checkpoint(
    checkpoint_dir: Path,
    simple_workflow_yaml: str,
) -> None:
    """Test resuming workflow from checkpoint."""
    # Parse workflow
    workflow = parse_workflow(simple_workflow_yaml)

    # Create registry and register test actions
    registry = ComponentRegistry()

    # Track which actions were called
    calls = []

    def tracked_action_1(input: str) -> str:
        calls.append("action_1")
        return f"step1_result_{input}"

    def tracked_action_2(input: str) -> str:
        calls.append("action_2")
        return f"step2_result_{input}"

    def tracked_action_3(input: str) -> str:
        calls.append("action_3")
        return f"step3_result_{input}"

    registry.actions.register("mock_action_1", tracked_action_1)
    registry.actions.register("mock_action_2", tracked_action_2)
    registry.actions.register("mock_action_3", tracked_action_3)

    # Create executor with checkpoint store
    checkpoint_store = FileCheckpointStore(base_path=checkpoint_dir)

    # First execution: run until checkpoint
    executor1 = WorkflowFileExecutor(
        registry=registry,
        checkpoint_store=checkpoint_store,
    )

    inputs = {"value": "test"}
    async for _event in executor1.execute(workflow, inputs=inputs):
        pass

    result1 = executor1.get_result()
    assert result1.success

    # Verify all actions were called in first execution
    assert calls == ["action_1", "action_2", "action_3"]

    # Reset calls tracker
    calls.clear()

    # Second execution: resume from checkpoint
    executor2 = WorkflowFileExecutor(
        registry=registry,
        checkpoint_store=checkpoint_store,
    )

    async for _event in executor2.execute(
        workflow,
        inputs=inputs,
        resume_from_checkpoint=True,
    ):
        pass

    result2 = executor2.get_result()
    assert result2.success

    # Verify only actions after checkpoint were called
    # action_1 should NOT be called (before checkpoint)
    # action_2 and action_3 should be called (after checkpoint)
    assert "action_1" not in calls
    assert "action_2" in calls
    assert "action_3" in calls


@pytest.mark.asyncio
async def test_resume_with_mismatched_inputs_fails(
    checkpoint_dir: Path,
    simple_workflow_yaml: str,
) -> None:
    """Test that resuming with different inputs fails validation."""
    # Parse workflow
    workflow = parse_workflow(simple_workflow_yaml)

    # Create registry and register test actions
    registry = ComponentRegistry()
    registry.actions.register("mock_action_1", mock_action_1)
    registry.actions.register("mock_action_2", mock_action_2)
    registry.actions.register("mock_action_3", mock_action_3)

    # Create executor with checkpoint store
    checkpoint_store = FileCheckpointStore(base_path=checkpoint_dir)

    # First execution with inputs "test"
    executor1 = WorkflowFileExecutor(
        registry=registry,
        checkpoint_store=checkpoint_store,
    )

    inputs1 = {"value": "test"}
    async for _event in executor1.execute(workflow, inputs=inputs1):
        pass

    result1 = executor1.get_result()
    assert result1.success

    # Second execution with different inputs "different"
    executor2 = WorkflowFileExecutor(
        registry=registry,
        checkpoint_store=checkpoint_store,
    )

    inputs2 = {"value": "different"}

    # Should raise ValueError due to input mismatch
    with pytest.raises(ValueError, match="Cannot resume workflow.*inputs differ"):
        async for _event in executor2.execute(
            workflow,
            inputs=inputs2,
            resume_from_checkpoint=True,
        ):
            pass


@pytest.mark.asyncio
async def test_checkpoint_persists_to_file(
    checkpoint_dir: Path,
    simple_workflow_yaml: str,
) -> None:
    """Test that checkpoint data is persisted to filesystem."""
    # Parse workflow
    workflow = parse_workflow(simple_workflow_yaml)

    # Create registry and register test actions
    registry = ComponentRegistry()
    registry.actions.register("mock_action_1", mock_action_1)
    registry.actions.register("mock_action_2", mock_action_2)
    registry.actions.register("mock_action_3", mock_action_3)

    # Create executor with checkpoint store
    checkpoint_store = FileCheckpointStore(base_path=checkpoint_dir)
    executor = WorkflowFileExecutor(
        registry=registry,
        checkpoint_store=checkpoint_store,
    )

    # Execute workflow
    inputs = {"value": "test"}
    async for _event in executor.execute(workflow, inputs=inputs):
        pass

    # Verify checkpoint file exists
    checkpoint_file = checkpoint_dir / "test-checkpoint" / "after_step1.json"
    assert checkpoint_file.exists()

    # Verify file contains valid JSON
    import json

    checkpoint_data = json.loads(checkpoint_file.read_text())
    assert checkpoint_data["checkpoint_id"] == "after_step1"
    assert checkpoint_data["workflow_name"] == "test-checkpoint"
    assert "inputs_hash" in checkpoint_data
    assert "step_results" in checkpoint_data
    assert "saved_at" in checkpoint_data
