"""Input history persistence for workflow inputs.

This module provides storage and retrieval of previous workflow inputs
to enable quick re-runs with previous values.

Feature: TUI Dramatic Improvement - Input History & Defaults
Date: 2026-01-12
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from maverick.utils.atomic import atomic_write_json

__all__ = [
    "INPUT_HISTORY_PATH",
    "MAX_HISTORY_PER_WORKFLOW",
    "InputHistoryEntry",
    "InputHistoryStore",
]

INPUT_HISTORY_PATH = Path.home() / ".config" / "maverick" / "input-history.json"
MAX_HISTORY_PER_WORKFLOW = 5  # Keep last 5 input sets per workflow


@dataclass(frozen=True, slots=True)
class InputHistoryEntry:
    """A saved set of workflow inputs.

    Attributes:
        workflow_name: Name of the workflow.
        inputs: The input values that were used.
        timestamp: When the inputs were saved (ISO 8601).
        label: Optional user-provided label for this input set.
    """

    workflow_name: str
    inputs: dict[str, Any]
    timestamp: str
    label: str | None = None

    @classmethod
    def create(
        cls,
        workflow_name: str,
        inputs: dict[str, Any],
        label: str | None = None,
    ) -> InputHistoryEntry:
        """Create a new history entry with current timestamp.

        Args:
            workflow_name: Name of the workflow.
            inputs: Input values to save.
            label: Optional label for this entry.

        Returns:
            New InputHistoryEntry instance.
        """
        return cls(
            workflow_name=workflow_name,
            inputs=inputs,
            timestamp=datetime.now().isoformat(),
            label=label,
        )

    @property
    def display_timestamp(self) -> str:
        """Human-readable timestamp."""
        try:
            dt = datetime.fromisoformat(self.timestamp)
            return dt.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            return self.timestamp

    @property
    def display_label(self) -> str:
        """Display label or fallback to timestamp."""
        if self.label:
            return self.label
        return f"Inputs from {self.display_timestamp}"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "workflow_name": self.workflow_name,
            "inputs": self.inputs,
            "timestamp": self.timestamp,
            "label": self.label,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InputHistoryEntry:
        """Create from dictionary (JSON deserialization)."""
        return cls(
            workflow_name=data["workflow_name"],
            inputs=data["inputs"],
            timestamp=data["timestamp"],
            label=data.get("label"),
        )


@dataclass
class InputHistoryStore:
    """Persistent storage for workflow input history.

    Stores previous input values per workflow to enable quick re-runs
    with previous configurations.

    Example:
        store = InputHistoryStore()

        # Save inputs after workflow run
        store.save_inputs("feature", {"spec_path": "./specs/my-feature"})

        # Get last inputs for a workflow
        last = store.get_last_inputs("feature")
        if last:
            print(f"Last inputs: {last.inputs}")

        # Get all history for a workflow
        history = store.get_history("feature")
    """

    path: Path = field(default_factory=lambda: INPUT_HISTORY_PATH)
    max_per_workflow: int = MAX_HISTORY_PER_WORKFLOW
    _cache: dict[str, list[InputHistoryEntry]] | None = field(default=None, repr=False)

    def _load(self) -> dict[str, list[InputHistoryEntry]]:
        """Load history from disk.

        Returns:
            Dictionary mapping workflow name to list of history entries.
        """
        if self._cache is not None:
            return self._cache

        if not self.path.exists():
            self._cache = {}
            return self._cache

        try:
            with self.path.open("r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                self._cache = {}
                return self._cache

            self._cache = {}
            for workflow_name, entries in data.items():
                if isinstance(entries, list):
                    self._cache[workflow_name] = [
                        InputHistoryEntry.from_dict(e)
                        for e in entries
                        if isinstance(e, dict)
                    ]

            return self._cache

        except (json.JSONDecodeError, OSError):
            self._cache = {}
            return self._cache

    def _save(self) -> None:
        """Save history to disk."""
        if self._cache is None:
            return

        data = {
            workflow: [entry.to_dict() for entry in entries]
            for workflow, entries in self._cache.items()
        }
        atomic_write_json(self.path, data, indent=2, ensure_ascii=False, mkdir=True)

    def save_inputs(
        self,
        workflow_name: str,
        inputs: dict[str, Any],
        label: str | None = None,
    ) -> InputHistoryEntry:
        """Save a set of workflow inputs.

        Creates a new history entry and applies FIFO eviction
        if the workflow exceeds max_per_workflow entries.

        Args:
            workflow_name: Name of the workflow.
            inputs: Input values to save.
            label: Optional label for this entry.

        Returns:
            The created InputHistoryEntry.
        """
        history = self._load()

        entry = InputHistoryEntry.create(workflow_name, inputs, label)

        if workflow_name not in history:
            history[workflow_name] = []

        # Check for duplicate inputs (don't save exact same inputs twice)
        existing_inputs = [e.inputs for e in history[workflow_name]]
        if inputs not in existing_inputs:
            history[workflow_name].append(entry)

            # Apply FIFO eviction
            if len(history[workflow_name]) > self.max_per_workflow:
                history[workflow_name] = history[workflow_name][
                    -self.max_per_workflow :
                ]

            self._save()

        return entry

    def get_last_inputs(self, workflow_name: str) -> InputHistoryEntry | None:
        """Get the most recent inputs for a workflow.

        Args:
            workflow_name: Name of the workflow.

        Returns:
            Most recent InputHistoryEntry, or None if no history.
        """
        history = self._load()
        entries = history.get(workflow_name, [])
        return entries[-1] if entries else None

    def get_history(
        self,
        workflow_name: str,
        limit: int | None = None,
    ) -> list[InputHistoryEntry]:
        """Get input history for a workflow.

        Args:
            workflow_name: Name of the workflow.
            limit: Maximum number of entries to return (newest first).

        Returns:
            List of InputHistoryEntry, newest first.
        """
        history = self._load()
        entries = history.get(workflow_name, [])

        # Return newest first
        result = list(reversed(entries))

        if limit is not None:
            return result[:limit]
        return result

    def get_all_workflows(self) -> list[str]:
        """Get list of workflows with saved history.

        Returns:
            List of workflow names that have saved input history.
        """
        history = self._load()
        return list(history.keys())

    def clear_workflow(self, workflow_name: str) -> None:
        """Clear all history for a specific workflow.

        Args:
            workflow_name: Name of the workflow to clear.
        """
        history = self._load()
        if workflow_name in history:
            del history[workflow_name]
            self._save()

    def clear_all(self) -> None:
        """Clear all input history."""
        self._cache = {}
        if self.path.exists():
            self.path.unlink()

    def has_history(self, workflow_name: str) -> bool:
        """Check if a workflow has saved input history.

        Args:
            workflow_name: Name of the workflow.

        Returns:
            True if the workflow has saved history.
        """
        history = self._load()
        return workflow_name in history and len(history[workflow_name]) > 0


# Global store instance (singleton pattern)
_input_history_store: InputHistoryStore | None = None


def get_input_history_store() -> InputHistoryStore:
    """Get the global input history store instance.

    Returns:
        The global InputHistoryStore singleton.
    """
    global _input_history_store
    if _input_history_store is None:
        _input_history_store = InputHistoryStore()
    return _input_history_store
