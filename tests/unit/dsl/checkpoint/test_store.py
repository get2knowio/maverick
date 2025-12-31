"""Tests for CheckpointStore implementations."""

from __future__ import annotations

from maverick.dsl.checkpoint.data import CheckpointData
from maverick.dsl.checkpoint.store import (
    FileCheckpointStore,
    MemoryCheckpointStore,
)


class TestFileCheckpointStore:
    """Tests for FileCheckpointStore class."""

    # T076: FileCheckpointStore save/load/clear
    async def test_save_and_load(self, tmp_path) -> None:
        """Should save and load checkpoint data."""
        store = FileCheckpointStore(base_path=tmp_path)
        data = CheckpointData(
            checkpoint_id="cp1",
            workflow_name="wf1",
            inputs_hash="hash123",
            step_results=(
                {"name": "step1", "output": "result1"},
                {"name": "step2", "output": "result2"},
            ),
            saved_at="2024-01-01T12:00:00Z",
        )
        await store.save("workflow_1", data)
        loaded = await store.load("workflow_1", "cp1")
        assert loaded is not None
        assert loaded.checkpoint_id == "cp1"
        assert loaded.workflow_name == "wf1"
        assert loaded.inputs_hash == "hash123"
        assert loaded.step_results == (
            {"name": "step1", "output": "result1"},
            {"name": "step2", "output": "result2"},
        )
        assert loaded.saved_at == "2024-01-01T12:00:00Z"

    async def test_load_nonexistent(self, tmp_path) -> None:
        """Should return None for nonexistent checkpoint."""
        store = FileCheckpointStore(base_path=tmp_path)
        loaded = await store.load("nonexistent_workflow", "nonexistent_cp")
        assert loaded is None

    async def test_clear(self, tmp_path) -> None:
        """Should remove all checkpoints for workflow."""
        store = FileCheckpointStore(base_path=tmp_path)
        data1 = CheckpointData(
            checkpoint_id="cp1",
            workflow_name="wf1",
            inputs_hash="hash123",
            step_results=(),
            saved_at="2024-01-01T12:00:00Z",
        )
        data2 = CheckpointData(
            checkpoint_id="cp2",
            workflow_name="wf1",
            inputs_hash="hash123",
            step_results=(),
            saved_at="2024-01-01T13:00:00Z",
        )
        await store.save("workflow_1", data1)
        await store.save("workflow_1", data2)

        # Verify saved
        checkpoints = await store.list_checkpoints("workflow_1")
        assert len(checkpoints) == 2
        assert "cp1" in checkpoints
        assert "cp2" in checkpoints

        # Clear and verify empty
        await store.clear("workflow_1")
        checkpoints = await store.list_checkpoints("workflow_1")
        assert len(checkpoints) == 0
        assert await store.load("workflow_1", "cp1") is None
        assert await store.load("workflow_1", "cp2") is None


class TestMemoryCheckpointStore:
    """Tests for MemoryCheckpointStore class."""

    # T077: MemoryCheckpointStore operations
    async def test_save_and_load(self) -> None:
        """Should save and load checkpoint data."""
        store = MemoryCheckpointStore()
        data = CheckpointData(
            checkpoint_id="cp1",
            workflow_name="wf1",
            inputs_hash="hash123",
            step_results=({"name": "step1", "output": "result1"},),
            saved_at="2024-01-01T12:00:00Z",
        )
        await store.save("workflow_1", data)
        loaded = await store.load("workflow_1", "cp1")
        assert loaded is not None
        assert loaded.checkpoint_id == "cp1"
        assert loaded.workflow_name == "wf1"
        assert loaded.inputs_hash == "hash123"
        assert loaded.step_results == ({"name": "step1", "output": "result1"},)
        assert loaded.saved_at == "2024-01-01T12:00:00Z"

    async def test_load_latest(self) -> None:
        """Should return most recent checkpoint."""
        store = MemoryCheckpointStore()
        data1 = CheckpointData(
            checkpoint_id="cp1",
            workflow_name="wf1",
            inputs_hash="hash123",
            step_results=(),
            saved_at="2024-01-01T00:00:00Z",
        )
        data2 = CheckpointData(
            checkpoint_id="cp2",
            workflow_name="wf1",
            inputs_hash="hash123",
            step_results=(),
            saved_at="2024-01-02T00:00:00Z",
        )
        data3 = CheckpointData(
            checkpoint_id="cp3",
            workflow_name="wf1",
            inputs_hash="hash123",
            step_results=(),
            saved_at="2024-01-01T12:00:00Z",
        )
        await store.save("workflow_1", data1)
        await store.save("workflow_1", data2)
        await store.save("workflow_1", data3)

        latest = await store.load_latest("workflow_1")
        assert latest is not None
        assert latest.checkpoint_id == "cp2"
        assert latest.saved_at == "2024-01-02T00:00:00Z"

    async def test_clear(self) -> None:
        """Should remove all checkpoints for workflow."""
        store = MemoryCheckpointStore()
        data1 = CheckpointData(
            checkpoint_id="cp1",
            workflow_name="wf1",
            inputs_hash="hash123",
            step_results=(),
            saved_at="2024-01-01T12:00:00Z",
        )
        data2 = CheckpointData(
            checkpoint_id="cp2",
            workflow_name="wf1",
            inputs_hash="hash123",
            step_results=(),
            saved_at="2024-01-01T13:00:00Z",
        )
        await store.save("workflow_1", data1)
        await store.save("workflow_1", data2)

        # Verify saved
        checkpoints = await store.list_checkpoints("workflow_1")
        assert len(checkpoints) == 2
        assert "cp1" in checkpoints
        assert "cp2" in checkpoints

        # Clear and verify empty
        await store.clear("workflow_1")
        checkpoints = await store.list_checkpoints("workflow_1")
        assert len(checkpoints) == 0
        assert await store.load("workflow_1", "cp1") is None
        assert await store.load("workflow_1", "cp2") is None
