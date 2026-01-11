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


# =============================================================================
# Nested Checkpoint Tests (checkpoint inside loop)
# =============================================================================


@pytest.fixture
def loop_workflow_yaml() -> str:
    """Workflow with checkpoint inside a loop for testing nested resume."""
    return """
version: "1.0"
name: test-loop-checkpoint
description: Test workflow with checkpoint inside loop

inputs:
  items:
    type: array
    required: true

steps:
  - name: before_loop
    type: python
    action: mock_before_loop
    kwargs:
      data: "init"

  - name: process_items
    type: loop
    for_each: ${{ inputs.items }}
    steps:
      - name: process_item
        type: python
        action: mock_process_item
        kwargs:
          item: ${{ item }}
          index: ${{ index }}

      - name: validate_item
        type: python
        action: mock_validate_item
        kwargs:
          item: ${{ item }}

      - name: item_checkpoint
        type: checkpoint
        checkpoint_id: "item_${{ index }}_complete"

  - name: after_loop
    type: python
    action: mock_after_loop
    kwargs:
      data: "finalize"
"""


def mock_before_loop(data: str) -> str:
    """Mock action before loop."""
    return f"before_{data}"


def mock_process_item(item: str, index: int) -> str:
    """Mock action to process an item."""
    return f"processed_{item}_{index}"


def mock_validate_item(item: str) -> str:
    """Mock action to validate an item."""
    return f"validated_{item}"


def mock_after_loop(data: str) -> str:
    """Mock action after loop."""
    return f"after_{data}"


@pytest.mark.asyncio
async def test_checkpoint_inside_loop_saves_state(
    checkpoint_dir: Path,
    loop_workflow_yaml: str,
) -> None:
    """Test that checkpoints inside loops save correct state."""
    workflow = parse_workflow(loop_workflow_yaml)

    registry = ComponentRegistry()
    registry.actions.register("mock_before_loop", mock_before_loop)
    registry.actions.register("mock_process_item", mock_process_item)
    registry.actions.register("mock_validate_item", mock_validate_item)
    registry.actions.register("mock_after_loop", mock_after_loop)

    checkpoint_store = FileCheckpointStore(base_path=checkpoint_dir)
    executor = WorkflowFileExecutor(
        registry=registry,
        checkpoint_store=checkpoint_store,
    )

    inputs = {"items": ["a", "b", "c"]}
    async for _event in executor.execute(workflow, inputs=inputs):
        pass

    result = executor.get_result()
    assert result.success

    # Verify checkpoints were saved for each iteration
    checkpoints = await checkpoint_store.list_checkpoints("test-loop-checkpoint")
    assert "item_0_complete" in checkpoints
    assert "item_1_complete" in checkpoints
    assert "item_2_complete" in checkpoints


@pytest.mark.asyncio
async def test_resume_from_nested_checkpoint_in_loop(
    checkpoint_dir: Path,
    loop_workflow_yaml: str,
) -> None:
    """Test resuming from a checkpoint inside a loop iteration.

    This test manually creates a checkpoint at iteration 1 to simulate
    a crashed execution, then resumes and verifies that iteration 2 runs.
    """
    from datetime import UTC, datetime

    from maverick.dsl.checkpoint.data import CheckpointData, compute_inputs_hash

    workflow = parse_workflow(loop_workflow_yaml)

    # Track which actions were called
    calls: list[str] = []

    def tracked_before_loop(data: str) -> str:
        calls.append("before_loop")
        return f"before_{data}"

    def tracked_process_item(item: str, index: int) -> str:
        calls.append(f"process_{item}_{index}")
        return f"processed_{item}_{index}"

    def tracked_validate_item(item: str) -> str:
        calls.append(f"validate_{item}")
        return f"validated_{item}"

    def tracked_after_loop(data: str) -> str:
        calls.append("after_loop")
        return f"after_{data}"

    registry = ComponentRegistry()
    registry.actions.register("mock_before_loop", tracked_before_loop)
    registry.actions.register("mock_process_item", tracked_process_item)
    registry.actions.register("mock_validate_item", tracked_validate_item)
    registry.actions.register("mock_after_loop", tracked_after_loop)

    checkpoint_store = FileCheckpointStore(base_path=checkpoint_dir)
    inputs = {"items": ["a", "b", "c"]}

    # Manually create a checkpoint at iteration 1 (simulating a crash after iteration 1)
    # This checkpoint represents: before_loop ran, iterations 0 and 1 completed
    checkpoint_data = CheckpointData(
        checkpoint_id="item_1_complete",
        workflow_name="test-loop-checkpoint",
        inputs_hash=compute_inputs_hash(inputs),
        step_results=({"name": "before_loop", "output": "before_init"},),
        saved_at=datetime.now(UTC).isoformat(),
    )
    await checkpoint_store.save("test-loop-checkpoint", checkpoint_data)

    # Resume from checkpoint after iteration 1
    executor = WorkflowFileExecutor(
        registry=registry,
        checkpoint_store=checkpoint_store,
    )

    async for _event in executor.execute(
        workflow,
        inputs=inputs,
        resume_from_checkpoint=True,
    ):
        pass

    result = executor.get_result()
    assert result.success

    # Verify only actions after checkpoint were called
    # before_loop should NOT be called (before loop, state restored)
    # process_a, validate_a should NOT be called (iteration 0, before checkpoint)
    # process_b, validate_b should NOT be called (iteration 1, completed in checkpoint)
    # process_c, validate_c SHOULD be called (iteration 2, after checkpoint)
    # after_loop SHOULD be called (after loop)
    assert "before_loop" not in calls
    assert "process_a_0" not in calls
    assert "validate_a" not in calls
    assert "process_b_1" not in calls
    assert "validate_b" not in calls
    assert "process_c_2" in calls
    assert "validate_c" in calls
    assert "after_loop" in calls


@pytest.mark.asyncio
async def test_resume_from_middle_iteration(
    checkpoint_dir: Path,
) -> None:
    """Test resuming from a checkpoint in the middle of loop iterations.

    This test manually creates a checkpoint at iteration 2 to simulate
    a crashed execution, then resumes and verifies iterations 3 and 4 run.
    """
    from datetime import UTC, datetime

    from maverick.dsl.checkpoint.data import CheckpointData, compute_inputs_hash

    # Create a workflow with 5 iterations
    workflow_yaml = """
version: "1.0"
name: test-middle-checkpoint
description: Test workflow with checkpoint in middle iteration

inputs:
  items:
    type: array
    required: true

steps:
  - name: init
    type: python
    action: mock_init
    kwargs:
      data: "start"

  - name: process_items
    type: loop
    for_each: ${{ inputs.items }}
    max_concurrency: 1
    steps:
      - name: process
        type: python
        action: mock_process
        kwargs:
          item: ${{ item }}
          index: ${{ index }}

      - name: checkpoint
        type: checkpoint
        checkpoint_id: "iter_${{ index }}_done"

  - name: finalize
    type: python
    action: mock_finalize
    kwargs:
      data: "end"
"""
    workflow = parse_workflow(workflow_yaml)

    calls: list[str] = []

    def tracked_init(data: str) -> str:
        calls.append("init")
        return f"init_{data}"

    def tracked_process(item: str, index: int) -> str:
        calls.append(f"process_{index}")
        return f"processed_{item}"

    def tracked_finalize(data: str) -> str:
        calls.append("finalize")
        return f"final_{data}"

    registry = ComponentRegistry()
    registry.actions.register("mock_init", tracked_init)
    registry.actions.register("mock_process", tracked_process)
    registry.actions.register("mock_finalize", tracked_finalize)

    checkpoint_store = FileCheckpointStore(base_path=checkpoint_dir)
    inputs = {"items": ["a", "b", "c", "d", "e"]}

    # Manually create a checkpoint at iteration 2 (simulating a crash after iteration 2)
    # This checkpoint represents: init ran, iterations 0, 1, 2 completed
    checkpoint_data = CheckpointData(
        checkpoint_id="iter_2_done",
        workflow_name="test-middle-checkpoint",
        inputs_hash=compute_inputs_hash(inputs),
        step_results=({"name": "init", "output": "init_start"},),
        saved_at=datetime.now(UTC).isoformat(),
    )
    await checkpoint_store.save("test-middle-checkpoint", checkpoint_data)

    # Resume from checkpoint after iteration 2
    executor = WorkflowFileExecutor(
        registry=registry,
        checkpoint_store=checkpoint_store,
    )

    async for _event in executor.execute(
        workflow,
        inputs=inputs,
        resume_from_checkpoint=True,
    ):
        pass

    assert executor.get_result().success

    # Should only execute iterations 3, 4 and finalize
    # (resume from after iteration 2)
    assert "init" not in calls
    assert "process_0" not in calls
    assert "process_1" not in calls
    assert "process_2" not in calls
    assert "process_3" in calls
    assert "process_4" in calls
    assert "finalize" in calls
