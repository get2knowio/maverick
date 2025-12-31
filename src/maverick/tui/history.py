"""Workflow history persistence for Maverick TUI."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from maverick.utils.atomic import atomic_write_json

__all__ = [
    "HISTORY_PATH",
    "MAX_ENTRIES",
    "WorkflowHistoryEntry",
    "WorkflowHistoryStore",
]

HISTORY_PATH = Path.home() / ".config" / "maverick" / "history.json"
MAX_ENTRIES = 50


@dataclass(frozen=True, slots=True)
class WorkflowHistoryEntry:
    """Persisted record of a completed workflow.

    Stored in ~/.config/maverick/history.json with FIFO eviction at 50 entries.

    Attributes:
        id: Unique identifier (UUID).
        workflow_type: "fly" or "refuel".
        branch_name: Git branch name for the workflow.
        timestamp: When the workflow started (ISO 8601).
        final_status: "completed" or "failed".
        stages_completed: List of stage names that completed successfully.
        finding_counts: Count of findings by severity.
        pr_link: URL to the created PR (if any).
    """

    id: str
    workflow_type: str  # Literal["fly", "refuel"]
    branch_name: str
    timestamp: str  # ISO 8601 format
    final_status: str  # Literal["completed", "failed"]
    stages_completed: tuple[str, ...]
    finding_counts: dict[str, int]  # {"error": int, "warning": int, "suggestion": int}
    pr_link: str | None = None

    @classmethod
    def create(
        cls,
        workflow_type: str,
        branch_name: str,
        final_status: str,
        stages_completed: list[str],
        finding_counts: dict[str, int],
        pr_link: str | None = None,
    ) -> WorkflowHistoryEntry:
        """Factory method to create a new entry with auto-generated ID and timestamp."""
        return cls(
            id=str(uuid.uuid4()),
            workflow_type=workflow_type,
            branch_name=branch_name,
            timestamp=datetime.now().isoformat(),
            final_status=final_status,
            stages_completed=tuple(stages_completed),
            finding_counts=finding_counts,
            pr_link=pr_link,
        )

    @property
    def display_status(self) -> str:
        """Human-readable status with icon."""
        if self.final_status == "completed":
            return "✓ Completed"
        return "✗ Failed"

    @property
    def display_timestamp(self) -> str:
        """Human-readable timestamp."""
        dt = datetime.fromisoformat(self.timestamp)
        return dt.strftime("%Y-%m-%d %H:%M")

    def to_dict(self) -> dict[str, Any]:
        """Convert entry to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "workflow_type": self.workflow_type,
            "branch_name": self.branch_name,
            "timestamp": self.timestamp,
            "final_status": self.final_status,
            "stages_completed": list(self.stages_completed),
            "finding_counts": self.finding_counts,
            "pr_link": self.pr_link,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowHistoryEntry:
        """Create entry from dictionary (JSON deserialization)."""
        return cls(
            id=data["id"],
            workflow_type=data["workflow_type"],
            branch_name=data["branch_name"],
            timestamp=data["timestamp"],
            final_status=data["final_status"],
            stages_completed=tuple(data["stages_completed"]),
            finding_counts=data["finding_counts"],
            pr_link=data.get("pr_link"),
        )


class WorkflowHistoryStore:
    """Persistent storage for workflow history.

    Manages the workflow history JSON file with FIFO eviction.
    """

    def __init__(
        self,
        path: Path = HISTORY_PATH,
        max_entries: int = MAX_ENTRIES,
    ) -> None:
        """Initialize the history store.

        Args:
            path: Path to the history JSON file.
            max_entries: Maximum number of entries to keep (FIFO eviction).
        """
        self.path = path
        self.max_entries = max_entries

    def load(self) -> list[WorkflowHistoryEntry]:
        """Load history entries from disk.

        Returns:
            List of history entries, newest first. Empty list if file doesn't exist
            or contains invalid JSON.
        """
        if not self.path.exists():
            return []

        try:
            with self.path.open("r", encoding="utf-8") as f:
                data = json.load(f)

            # Validate that data is a list
            if not isinstance(data, list):
                return []

            # Parse entries, skipping any invalid ones
            entries = []
            for item in data:
                try:
                    entries.append(WorkflowHistoryEntry.from_dict(item))
                except (KeyError, TypeError, ValueError):
                    # Skip malformed entries
                    continue

            return entries

        except (json.JSONDecodeError, OSError):
            # File is corrupted or unreadable, return empty list
            return []

    def save(self, entries: list[WorkflowHistoryEntry]) -> None:
        """Save history entries to disk with FIFO eviction.

        Keeps only the most recent max_entries entries. Creates parent directories
        if they don't exist.

        Args:
            entries: List of entries to save.
        """
        # Apply FIFO eviction: keep only the most recent max_entries
        entries_to_save = entries[-self.max_entries :]

        # Convert to JSON-serializable format
        data = [entry.to_dict() for entry in entries_to_save]

        # Write atomically using atomicwrites library.
        # The library handles temp file creation, cleanup on error,
        # and atomic rename on success.
        atomic_write_json(self.path, data, indent=2, ensure_ascii=False, mkdir=True)

    def add(self, entry: WorkflowHistoryEntry) -> None:
        """Add a new history entry.

        Appends the entry and applies FIFO eviction if necessary.

        Args:
            entry: The history entry to add.
        """
        entries = self.load()
        entries.append(entry)
        self.save(entries)

    def clear(self) -> None:
        """Clear all history entries.

        Deletes the history file if it exists.
        """
        if self.path.exists():
            self.path.unlink()

    def get_recent(self, count: int = 10) -> list[WorkflowHistoryEntry]:
        """Get most recent entries (newest first).

        Args:
            count: Maximum number of entries to return.

        Returns:
            List of most recent entries, newest first.
        """
        entries = self.load()
        # Return newest first (reverse order)
        return list(reversed(entries[-count:]))
