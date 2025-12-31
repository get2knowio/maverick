"""Checkpoint store implementations.

This module provides the CheckpointStore protocol and implementations
for persisting and loading workflow checkpoints.
"""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
from typing import Protocol

from maverick.dsl.checkpoint.data import CheckpointData
from maverick.dsl.config import DEFAULTS
from maverick.utils.atomic import atomic_write_text


class CheckpointStore(Protocol):
    """Protocol for checkpoint persistence.

    All methods are async for consistency with async-first architecture.
    """

    async def save(
        self,
        workflow_id: str,
        data: CheckpointData,
    ) -> None:
        """Save checkpoint atomically."""
        ...

    async def load(
        self,
        workflow_id: str,
        checkpoint_id: str,
    ) -> CheckpointData | None:
        """Load a specific checkpoint."""
        ...

    async def load_latest(
        self,
        workflow_id: str,
    ) -> CheckpointData | None:
        """Load most recent checkpoint for a workflow."""
        ...

    async def clear(
        self,
        workflow_id: str,
    ) -> None:
        """Remove all checkpoints for a workflow."""
        ...

    async def list_checkpoints(
        self,
        workflow_id: str,
    ) -> list[str]:
        """List all checkpoint IDs for a workflow."""
        ...


class FileCheckpointStore:
    """File-based checkpoint store with atomic writes.

    Stores checkpoints as JSON files under a configurable base directory.
    Uses atomic write pattern (temp file + rename) to prevent corruption.
    """

    def __init__(self, base_path: Path | str | None = None) -> None:
        """Initialize file checkpoint store.

        Args:
            base_path: Directory for checkpoint storage.
                If None, uses DEFAULTS.CHECKPOINT_DIR.
        """
        if base_path is None:
            self._base_path = Path(DEFAULTS.CHECKPOINT_DIR)
        else:
            self._base_path = Path(base_path)
        # Clean up any orphaned temp files from previous crashes
        self._cleanup_temp_files()

    def _cleanup_temp_files(self) -> None:
        """Remove any leftover .json.tmp files from interrupted saves."""
        if self._base_path.exists():
            for tmp_file in self._base_path.rglob("*.json.tmp"):
                with contextlib.suppress(OSError):
                    tmp_file.unlink()

    async def save(
        self,
        workflow_id: str,
        data: CheckpointData,
    ) -> None:
        """Save checkpoint with atomic write.

        Note: Uses synchronous file I/O for simplicity. Checkpoint files are small
        (<10KB) and local file operations complete in microseconds, making the
        overhead of async wrappers unnecessary.
        """
        dir_path = self._base_path / workflow_id
        file_path = dir_path / f"{data.checkpoint_id}.json"
        content = json.dumps(data.to_dict(), indent=2)

        # Uses atomicwrites library for atomic file operations.
        # The library handles temp file creation and cleanup on error.
        atomic_write_text(file_path, content, mkdir=True)

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
            content = file_path.read_text()
            data = json.loads(content)
            checkpoints.append(CheckpointData.from_dict(data))

        if not checkpoints:
            return None

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
            with contextlib.suppress(OSError):
                dir_path.rmdir()

    async def list_checkpoints(
        self,
        workflow_id: str,
    ) -> list[str]:
        """List checkpoint IDs."""
        dir_path = self._base_path / workflow_id

        if not dir_path.exists():
            return []

        return [file_path.stem for file_path in dir_path.glob("*.json")]


class MemoryCheckpointStore:
    """In-memory checkpoint store for testing.

    Not suitable for production - data lost on process exit.
    """

    def __init__(self) -> None:
        """Initialize empty storage."""
        self._storage: dict[str, dict[str, CheckpointData]] = {}

    async def save(
        self,
        workflow_id: str,
        data: CheckpointData,
    ) -> None:
        """Save checkpoint to memory."""
        if workflow_id not in self._storage:
            self._storage[workflow_id] = {}
        self._storage[workflow_id][data.checkpoint_id] = data

    async def load(
        self,
        workflow_id: str,
        checkpoint_id: str,
    ) -> CheckpointData | None:
        """Load checkpoint from memory."""
        return self._storage.get(workflow_id, {}).get(checkpoint_id)

    async def load_latest(
        self,
        workflow_id: str,
    ) -> CheckpointData | None:
        """Load most recent checkpoint."""
        checkpoints = list(self._storage.get(workflow_id, {}).values())
        if not checkpoints:
            return None
        checkpoints.sort(key=lambda c: c.saved_at, reverse=True)
        return checkpoints[0]

    async def clear(
        self,
        workflow_id: str,
    ) -> None:
        """Remove all checkpoints for workflow."""
        self._storage.pop(workflow_id, None)

    async def list_checkpoints(
        self,
        workflow_id: str,
    ) -> list[str]:
        """List checkpoint IDs."""
        return list(self._storage.get(workflow_id, {}).keys())
