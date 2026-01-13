"""Unit tests for input history persistence module.

This test module covers:
- InputHistoryEntry creation and properties
- InputHistoryStore storage and retrieval
- FIFO eviction behavior
- Persistence to disk

Feature: 030-tui-execution-visibility
Date: 2026-01-12
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from maverick.tui.input_history import (
    MAX_HISTORY_PER_WORKFLOW,
    InputHistoryEntry,
    InputHistoryStore,
)


class TestInputHistoryEntry:
    """Tests for InputHistoryEntry dataclass."""

    def test_creation_with_all_fields(self) -> None:
        """Test creating InputHistoryEntry with all fields."""
        entry = InputHistoryEntry(
            workflow_name="feature",
            inputs={"spec_path": "./specs/test"},
            timestamp="2026-01-12T10:30:00",
            label="Test run",
        )

        assert entry.workflow_name == "feature"
        assert entry.inputs == {"spec_path": "./specs/test"}
        assert entry.timestamp == "2026-01-12T10:30:00"
        assert entry.label == "Test run"

    def test_creation_without_label(self) -> None:
        """Test creating InputHistoryEntry without label."""
        entry = InputHistoryEntry(
            workflow_name="feature",
            inputs={"key": "value"},
            timestamp="2026-01-12T10:30:00",
        )

        assert entry.label is None

    def test_create_class_method(self) -> None:
        """Test create() class method generates timestamp."""
        entry = InputHistoryEntry.create(
            workflow_name="feature",
            inputs={"key": "value"},
            label="My label",
        )

        assert entry.workflow_name == "feature"
        assert entry.inputs == {"key": "value"}
        assert entry.label == "My label"
        # Timestamp should be valid ISO format
        datetime.fromisoformat(entry.timestamp)

    def test_create_without_label(self) -> None:
        """Test create() without label."""
        entry = InputHistoryEntry.create(
            workflow_name="feature", inputs={"key": "value"}
        )

        assert entry.label is None

    def test_display_timestamp(self) -> None:
        """Test display_timestamp property formats correctly."""
        entry = InputHistoryEntry(
            workflow_name="feature",
            inputs={},
            timestamp="2026-01-12T10:30:00",
        )

        assert entry.display_timestamp == "2026-01-12 10:30"

    def test_display_timestamp_invalid(self) -> None:
        """Test display_timestamp with invalid timestamp."""
        entry = InputHistoryEntry(
            workflow_name="feature",
            inputs={},
            timestamp="invalid-timestamp",
        )

        # Should return original string on parse failure
        assert entry.display_timestamp == "invalid-timestamp"

    def test_display_label_with_label(self) -> None:
        """Test display_label when label is set."""
        entry = InputHistoryEntry(
            workflow_name="feature",
            inputs={},
            timestamp="2026-01-12T10:30:00",
            label="My custom label",
        )

        assert entry.display_label == "My custom label"

    def test_display_label_without_label(self) -> None:
        """Test display_label falls back to timestamp."""
        entry = InputHistoryEntry(
            workflow_name="feature",
            inputs={},
            timestamp="2026-01-12T10:30:00",
        )

        assert "2026-01-12 10:30" in entry.display_label
        assert "Inputs from" in entry.display_label

    def test_to_dict(self) -> None:
        """Test to_dict serialization."""
        entry = InputHistoryEntry(
            workflow_name="feature",
            inputs={"key": "value"},
            timestamp="2026-01-12T10:30:00",
            label="Test",
        )

        data = entry.to_dict()

        assert data["workflow_name"] == "feature"
        assert data["inputs"] == {"key": "value"}
        assert data["timestamp"] == "2026-01-12T10:30:00"
        assert data["label"] == "Test"

    def test_from_dict(self) -> None:
        """Test from_dict deserialization."""
        data = {
            "workflow_name": "feature",
            "inputs": {"key": "value"},
            "timestamp": "2026-01-12T10:30:00",
            "label": "Test",
        }

        entry = InputHistoryEntry.from_dict(data)

        assert entry.workflow_name == "feature"
        assert entry.inputs == {"key": "value"}
        assert entry.timestamp == "2026-01-12T10:30:00"
        assert entry.label == "Test"

    def test_from_dict_without_label(self) -> None:
        """Test from_dict when label is missing."""
        data = {
            "workflow_name": "feature",
            "inputs": {"key": "value"},
            "timestamp": "2026-01-12T10:30:00",
        }

        entry = InputHistoryEntry.from_dict(data)

        assert entry.label is None

    def test_entry_is_frozen(self) -> None:
        """Test that InputHistoryEntry is immutable."""
        entry = InputHistoryEntry(
            workflow_name="feature",
            inputs={},
            timestamp="2026-01-12T10:30:00",
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            entry.workflow_name = "modified"  # type: ignore[misc]


class TestInputHistoryStore:
    """Tests for InputHistoryStore."""

    @pytest.fixture
    def temp_store(self, tmp_path: Path) -> InputHistoryStore:
        """Create a store with temporary path."""
        return InputHistoryStore(path=tmp_path / "history.json")

    def test_creation_with_default_path(self) -> None:
        """Test store creation with default path."""
        store = InputHistoryStore()
        assert store.max_per_workflow == MAX_HISTORY_PER_WORKFLOW

    def test_creation_with_custom_path(self, tmp_path: Path) -> None:
        """Test store creation with custom path."""
        custom_path = tmp_path / "custom.json"
        store = InputHistoryStore(path=custom_path)

        assert store.path == custom_path

    def test_save_inputs_creates_entry(self, temp_store: InputHistoryStore) -> None:
        """Test save_inputs creates a new entry."""
        entry = temp_store.save_inputs("feature", {"spec_path": "./specs/test"})

        assert entry.workflow_name == "feature"
        assert entry.inputs == {"spec_path": "./specs/test"}

    def test_save_inputs_with_label(self, temp_store: InputHistoryStore) -> None:
        """Test save_inputs with label."""
        entry = temp_store.save_inputs("feature", {"key": "value"}, label="My inputs")

        assert entry.label == "My inputs"

    def test_save_inputs_persists_to_disk(self, temp_store: InputHistoryStore) -> None:
        """Test save_inputs persists to disk."""
        temp_store.save_inputs("feature", {"key": "value"})

        # File should exist
        assert temp_store.path.exists()

        # Load and verify
        with temp_store.path.open("r") as f:
            data = json.load(f)

        assert "feature" in data
        assert len(data["feature"]) == 1

    def test_get_last_inputs(self, temp_store: InputHistoryStore) -> None:
        """Test get_last_inputs returns most recent."""
        temp_store.save_inputs("feature", {"run": 1})
        temp_store.save_inputs("feature", {"run": 2})
        temp_store.save_inputs("feature", {"run": 3})

        last = temp_store.get_last_inputs("feature")

        assert last is not None
        assert last.inputs == {"run": 3}

    def test_get_last_inputs_no_history(self, temp_store: InputHistoryStore) -> None:
        """Test get_last_inputs returns None for unknown workflow."""
        result = temp_store.get_last_inputs("unknown")
        assert result is None

    def test_get_history_newest_first(self, temp_store: InputHistoryStore) -> None:
        """Test get_history returns entries newest first."""
        temp_store.save_inputs("feature", {"run": 1})
        temp_store.save_inputs("feature", {"run": 2})
        temp_store.save_inputs("feature", {"run": 3})

        history = temp_store.get_history("feature")

        assert len(history) == 3
        assert history[0].inputs == {"run": 3}  # Newest first
        assert history[1].inputs == {"run": 2}
        assert history[2].inputs == {"run": 1}

    def test_get_history_with_limit(self, temp_store: InputHistoryStore) -> None:
        """Test get_history respects limit parameter."""
        for i in range(5):
            temp_store.save_inputs("feature", {"run": i})

        history = temp_store.get_history("feature", limit=2)

        assert len(history) == 2
        # Should be newest 2
        assert history[0].inputs == {"run": 4}
        assert history[1].inputs == {"run": 3}

    def test_get_history_unknown_workflow(self, temp_store: InputHistoryStore) -> None:
        """Test get_history returns empty for unknown workflow."""
        history = temp_store.get_history("unknown")
        assert history == []

    def test_fifo_eviction(self, tmp_path: Path) -> None:
        """Test FIFO eviction when exceeding max entries."""
        store = InputHistoryStore(path=tmp_path / "history.json", max_per_workflow=3)

        # Save 5 entries (should keep only last 3)
        for i in range(5):
            store.save_inputs("feature", {"run": i})

        history = store.get_history("feature")

        assert len(history) == 3
        # Should have newest 3
        assert history[0].inputs == {"run": 4}
        assert history[1].inputs == {"run": 3}
        assert history[2].inputs == {"run": 2}

    def test_duplicate_inputs_not_saved(self, temp_store: InputHistoryStore) -> None:
        """Test duplicate inputs are not saved twice."""
        temp_store.save_inputs("feature", {"key": "value"})
        temp_store.save_inputs("feature", {"key": "value"})  # Duplicate

        history = temp_store.get_history("feature")

        assert len(history) == 1

    def test_get_all_workflows(self, temp_store: InputHistoryStore) -> None:
        """Test get_all_workflows returns all workflow names."""
        temp_store.save_inputs("feature", {"key": "value"})
        temp_store.save_inputs("refuel", {"key": "value"})
        temp_store.save_inputs("validate", {"key": "value"})

        workflows = temp_store.get_all_workflows()

        assert set(workflows) == {"feature", "refuel", "validate"}

    def test_get_all_workflows_empty(self, temp_store: InputHistoryStore) -> None:
        """Test get_all_workflows returns empty when no history."""
        workflows = temp_store.get_all_workflows()
        assert workflows == []

    def test_clear_workflow(self, temp_store: InputHistoryStore) -> None:
        """Test clear_workflow removes workflow history."""
        temp_store.save_inputs("feature", {"key": "value"})
        temp_store.save_inputs("refuel", {"key": "value"})

        temp_store.clear_workflow("feature")

        assert not temp_store.has_history("feature")
        assert temp_store.has_history("refuel")

    def test_clear_workflow_unknown(self, temp_store: InputHistoryStore) -> None:
        """Test clear_workflow handles unknown workflow gracefully."""
        # Should not raise
        temp_store.clear_workflow("unknown")

    def test_clear_all(self, temp_store: InputHistoryStore) -> None:
        """Test clear_all removes all history."""
        temp_store.save_inputs("feature", {"key": "value"})
        temp_store.save_inputs("refuel", {"key": "value"})

        temp_store.clear_all()

        assert temp_store.get_all_workflows() == []
        assert not temp_store.path.exists()

    def test_has_history(self, temp_store: InputHistoryStore) -> None:
        """Test has_history returns correct boolean."""
        assert not temp_store.has_history("feature")

        temp_store.save_inputs("feature", {"key": "value"})

        assert temp_store.has_history("feature")
        assert not temp_store.has_history("unknown")

    def test_load_invalid_json(self, tmp_path: Path) -> None:
        """Test loading with invalid JSON file."""
        path = tmp_path / "invalid.json"
        path.write_text("not valid json")

        store = InputHistoryStore(path=path)

        # Should handle gracefully
        assert store.get_all_workflows() == []

    def test_load_invalid_structure(self, tmp_path: Path) -> None:
        """Test loading with invalid data structure."""
        path = tmp_path / "invalid.json"
        path.write_text('["not", "a", "dict"]')

        store = InputHistoryStore(path=path)

        # Should handle gracefully
        assert store.get_all_workflows() == []

    def test_cache_behavior(self, temp_store: InputHistoryStore) -> None:
        """Test cache is used after first load."""
        temp_store.save_inputs("feature", {"key": "value"})

        # First load
        temp_store.get_all_workflows()

        # Manually corrupt the file
        temp_store.path.write_text('{"broken": "data"}')

        # Should still return cached data
        history = temp_store.get_history("feature")
        assert len(history) == 1

    def test_multiple_workflows(self, temp_store: InputHistoryStore) -> None:
        """Test storing inputs for multiple workflows."""
        temp_store.save_inputs("feature", {"spec": "spec1"})
        temp_store.save_inputs("refuel", {"label": "bug"})
        temp_store.save_inputs("feature", {"spec": "spec2"})

        feature_history = temp_store.get_history("feature")
        refuel_history = temp_store.get_history("refuel")

        assert len(feature_history) == 2
        assert len(refuel_history) == 1
