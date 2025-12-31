# CheckpointStore API Contract

**Branch**: `023-dsl-flow-control` | **Date**: 2025-12-20

This document defines the CheckpointStore protocol and FileCheckpointStore implementation.

---

## CheckpointStore Protocol

```python
from typing import Protocol

class CheckpointStore(Protocol):
    """Protocol for workflow checkpoint persistence.

    All methods are async for consistency with the async-first architecture.
    Implementations must handle concurrent access safely.
    """

    async def save(
        self,
        workflow_id: str,
        data: CheckpointData,
    ) -> None:
        """Save checkpoint atomically.

        If a checkpoint with the same checkpoint_id exists for this
        workflow_id, it is overwritten.

        Args:
            workflow_id: Unique identifier for the workflow run.
                Typically generated at workflow start time.
            data: Checkpoint data to persist.

        Raises:
            IOError: If the save operation fails.

        Postconditions:
            - Checkpoint is persisted durably
            - Partial writes are not visible (atomic)
        """
        ...

    async def load(
        self,
        workflow_id: str,
        checkpoint_id: str,
    ) -> CheckpointData | None:
        """Load a specific checkpoint.

        Args:
            workflow_id: Unique identifier for the workflow run.
            checkpoint_id: Identifier of the checkpoint to load.

        Returns:
            CheckpointData if found, None if not found.

        Raises:
            IOError: If the load operation fails (not including not-found).
            ValueError: If checkpoint data is corrupted/invalid.
        """
        ...

    async def load_latest(
        self,
        workflow_id: str,
    ) -> CheckpointData | None:
        """Load the most recent checkpoint for a workflow.

        Determines recency by saved_at timestamp.

        Args:
            workflow_id: Unique identifier for the workflow run.

        Returns:
            Most recent CheckpointData if any exist, None otherwise.

        Raises:
            IOError: If the load operation fails.
            ValueError: If checkpoint data is corrupted/invalid.
        """
        ...

    async def clear(
        self,
        workflow_id: str,
    ) -> None:
        """Remove all checkpoints for a workflow run.

        Typically called after successful workflow completion.

        Args:
            workflow_id: Unique identifier for the workflow run.

        Raises:
            IOError: If the clear operation fails.

        Postconditions:
            - All checkpoints for workflow_id are removed
            - Subsequent load/load_latest return None
        """
        ...

    async def list_checkpoints(
        self,
        workflow_id: str,
    ) -> list[str]:
        """List all checkpoint IDs for a workflow.

        Args:
            workflow_id: Unique identifier for the workflow run.

        Returns:
            List of checkpoint_id strings, empty if none exist.
        """
        ...
```

---

## FileCheckpointStore Implementation

```python
from pathlib import Path
import json
import os
import tempfile
from datetime import datetime, timezone


class FileCheckpointStore:
    """File-based checkpoint store with atomic writes.

    Stores checkpoints as JSON files under a configurable base directory.
    Uses atomic write pattern (temp file + rename) to prevent corruption.

    Directory Structure:
        {base_path}/{workflow_id}/{checkpoint_id}.json

    Default base_path: .maverick/checkpoints/
    """

    def __init__(
        self,
        base_path: Path | str | None = None,
    ) -> None:
        """Initialize file checkpoint store.

        Args:
            base_path: Directory for checkpoint storage.
                Default: .maverick/checkpoints/ relative to cwd.
        """
        if base_path is None:
            base_path = Path(".maverick/checkpoints")
        self._base_path = Path(base_path)

    async def save(
        self,
        workflow_id: str,
        data: CheckpointData,
    ) -> None:
        """Save checkpoint with atomic write."""
        dir_path = self._base_path / workflow_id
        dir_path.mkdir(parents=True, exist_ok=True)

        file_path = dir_path / f"{data.checkpoint_id}.json"
        content = json.dumps(data.to_dict(), indent=2)

        # Atomic write: temp file then rename
        fd, tmp_path = tempfile.mkstemp(
            dir=str(dir_path),
            suffix=".json.tmp",
        )
        try:
            with os.fdopen(fd, "w") as f:
                f.write(content)
            os.rename(tmp_path, str(file_path))
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    async def load(
        self,
        workflow_id: str,
        checkpoint_id: str,
    ) -> CheckpointData | None:
        """Load checkpoint from file."""
        file_path = self._base_path / workflow_id / f"{checkpoint_id}.json"

        if not file_path.exists():
            return None

        content = file_path.read_text()
        data = json.loads(content)
        return CheckpointData.from_dict(data)

    async def load_latest(
        self,
        workflow_id: str,
    ) -> CheckpointData | None:
        """Load most recent checkpoint by saved_at timestamp."""
        dir_path = self._base_path / workflow_id

        if not dir_path.exists():
            return None

        checkpoints: list[CheckpointData] = []
        for file_path in dir_path.glob("*.json"):
            if file_path.suffix == ".json":
                content = file_path.read_text()
                data = json.loads(content)
                checkpoints.append(CheckpointData.from_dict(data))

        if not checkpoints:
            return None

        # Sort by saved_at descending, return most recent
        checkpoints.sort(key=lambda c: c.saved_at, reverse=True)
        return checkpoints[0]

    async def clear(
        self,
        workflow_id: str,
    ) -> None:
        """Remove all checkpoints for workflow."""
        dir_path = self._base_path / workflow_id

        if dir_path.exists():
            for file_path in dir_path.glob("*.json"):
                file_path.unlink()
            # Remove directory if empty
            try:
                dir_path.rmdir()
            except OSError:
                pass  # Directory not empty or other issue

    async def list_checkpoints(
        self,
        workflow_id: str,
    ) -> list[str]:
        """List checkpoint IDs."""
        dir_path = self._base_path / workflow_id

        if not dir_path.exists():
            return []

        return [
            file_path.stem  # filename without .json
            for file_path in dir_path.glob("*.json")
        ]
```

---

## MemoryCheckpointStore (Testing)

```python
class MemoryCheckpointStore:
    """In-memory checkpoint store for testing.

    Not suitable for production use - data lost on process exit.
    """

    def __init__(self) -> None:
        # workflow_id -> checkpoint_id -> CheckpointData
        self._storage: dict[str, dict[str, CheckpointData]] = {}

    async def save(
        self,
        workflow_id: str,
        data: CheckpointData,
    ) -> None:
        if workflow_id not in self._storage:
            self._storage[workflow_id] = {}
        self._storage[workflow_id][data.checkpoint_id] = data

    async def load(
        self,
        workflow_id: str,
        checkpoint_id: str,
    ) -> CheckpointData | None:
        return self._storage.get(workflow_id, {}).get(checkpoint_id)

    async def load_latest(
        self,
        workflow_id: str,
    ) -> CheckpointData | None:
        checkpoints = list(self._storage.get(workflow_id, {}).values())
        if not checkpoints:
            return None
        checkpoints.sort(key=lambda c: c.saved_at, reverse=True)
        return checkpoints[0]

    async def clear(
        self,
        workflow_id: str,
    ) -> None:
        self._storage.pop(workflow_id, None)

    async def list_checkpoints(
        self,
        workflow_id: str,
    ) -> list[str]:
        return list(self._storage.get(workflow_id, {}).keys())
```

---

## Checkpoint Data JSON Format

```json
{
  "checkpoint_id": "expensive_compute",
  "workflow_name": "data_pipeline",
  "inputs_hash": "a1b2c3d4e5f67890",
  "step_results": [
    {
      "name": "fetch_data",
      "step_type": "python",
      "success": true,
      "output": {"rows": 1000},
      "duration_ms": 5234,
      "error": null
    },
    {
      "name": "expensive_compute",
      "step_type": "python",
      "success": true,
      "output": {"computed": true},
      "duration_ms": 120000,
      "error": null
    }
  ],
  "saved_at": "2025-12-20T15:30:00Z"
}
```

---

## Error Types

```python
class CheckpointNotFoundError(MaverickError):
    """Raised when resuming from a non-existent checkpoint."""

    def __init__(self, workflow_id: str, checkpoint_id: str | None = None):
        self.workflow_id = workflow_id
        self.checkpoint_id = checkpoint_id
        msg = f"No checkpoint found for workflow '{workflow_id}'"
        if checkpoint_id:
            msg += f" at '{checkpoint_id}'"
        super().__init__(msg)


class InputMismatchError(MaverickError):
    """Raised when resume inputs don't match checkpoint inputs."""

    def __init__(
        self,
        expected_hash: str,
        actual_hash: str,
    ):
        self.expected_hash = expected_hash
        self.actual_hash = actual_hash
        super().__init__(
            f"Input hash mismatch: checkpoint has '{expected_hash}', "
            f"current inputs have '{actual_hash}'"
        )
```

---

## Usage Examples

### Basic Checkpoint/Resume

```python
from maverick.dsl import workflow, step, WorkflowEngine
from maverick.dsl.checkpoint import FileCheckpointStore

@workflow("long_running")
def long_running(data: str):
    # First phase - expensive
    result = yield step("expensive").python(expensive_compute, args=(data,)).checkpoint()

    # Second phase - also expensive
    final = yield step("transform").python(transform, args=(result,))

    return final


# First run (may fail partway through)
engine = WorkflowEngine()
async for event in engine.execute(long_running, data="input"):
    print(event)

# Resume from checkpoint
async for event in engine.resume(
    long_running,
    workflow_id="run-123",
    data="input",  # Must match original
):
    print(event)
```

### Custom Checkpoint Store

```python
store = FileCheckpointStore(base_path="/var/maverick/checkpoints")
engine = WorkflowEngine(checkpoint_store=store)
```
