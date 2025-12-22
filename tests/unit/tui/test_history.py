"""Unit tests for workflow history persistence.

Tests cover:
- T087: WorkflowHistoryStore.load() returns empty list for missing file
- T088: WorkflowHistoryStore.add() saves entry and maintains FIFO eviction
- T089: WorkflowHistoryStore.get_recent(10) returns newest first
- T090: WorkflowHistoryEntry.display_status, display_timestamp
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from maverick.tui.history import (
    WorkflowHistoryEntry,
    WorkflowHistoryStore,
)

# =============================================================================
# WorkflowHistoryEntry Tests
# =============================================================================


class TestWorkflowHistoryEntry:
    """Tests for WorkflowHistoryEntry dataclass."""

    def test_create_factory_method(self) -> None:
        """Test creating entry with factory method."""
        entry = WorkflowHistoryEntry.create(
            workflow_type="fly",
            branch_name="feature/test",
            final_status="completed",
            stages_completed=["setup", "implementation"],
            finding_counts={"error": 0, "warning": 2, "suggestion": 5},
            pr_link="https://github.com/test/repo/pull/123",
        )

        assert entry.workflow_type == "fly"
        assert entry.branch_name == "feature/test"
        assert entry.final_status == "completed"
        assert entry.stages_completed == ("setup", "implementation")
        assert entry.finding_counts == {"error": 0, "warning": 2, "suggestion": 5}
        assert entry.pr_link == "https://github.com/test/repo/pull/123"
        assert entry.id  # UUID should be generated
        assert entry.timestamp  # ISO timestamp should be generated

    def test_create_without_pr_link(self) -> None:
        """Test creating entry without PR link."""
        entry = WorkflowHistoryEntry.create(
            workflow_type="refuel",
            branch_name="fix/bug",
            final_status="failed",
            stages_completed=["setup"],
            finding_counts={"error": 1, "warning": 0, "suggestion": 0},
        )

        assert entry.pr_link is None

    def test_display_status_completed(self) -> None:
        """Test display_status for completed workflow (T090)."""
        entry = WorkflowHistoryEntry.create(
            workflow_type="fly",
            branch_name="test",
            final_status="completed",
            stages_completed=[],
            finding_counts={},
        )

        assert entry.display_status == "✓ Completed"

    def test_display_status_failed(self) -> None:
        """Test display_status for failed workflow (T090)."""
        entry = WorkflowHistoryEntry.create(
            workflow_type="fly",
            branch_name="test",
            final_status="failed",
            stages_completed=[],
            finding_counts={},
        )

        assert entry.display_status == "✗ Failed"

    def test_display_timestamp(self) -> None:
        """Test display_timestamp formatting (T090)."""
        entry = WorkflowHistoryEntry(
            id="test-id",
            workflow_type="fly",
            branch_name="test",
            timestamp="2025-01-15T14:30:45.123456",
            final_status="completed",
            stages_completed=(),
            finding_counts={},
        )

        assert entry.display_timestamp == "2025-01-15 14:30"

    def test_to_dict_serialization(self) -> None:
        """Test conversion to dictionary for JSON serialization."""
        entry = WorkflowHistoryEntry.create(
            workflow_type="fly",
            branch_name="feature/test",
            final_status="completed",
            stages_completed=["setup", "implementation"],
            finding_counts={"error": 0, "warning": 2, "suggestion": 5},
            pr_link="https://github.com/test/repo/pull/123",
        )

        data = entry.to_dict()

        assert data["id"] == entry.id
        assert data["workflow_type"] == "fly"
        assert data["branch_name"] == "feature/test"
        assert data["timestamp"] == entry.timestamp
        assert data["final_status"] == "completed"
        assert data["stages_completed"] == ["setup", "implementation"]
        assert data["finding_counts"] == {"error": 0, "warning": 2, "suggestion": 5}
        assert data["pr_link"] == "https://github.com/test/repo/pull/123"

    def test_from_dict_deserialization(self) -> None:
        """Test creation from dictionary (JSON deserialization)."""
        data = {
            "id": "test-id-123",
            "workflow_type": "refuel",
            "branch_name": "fix/bug",
            "timestamp": "2025-01-15T14:30:45",
            "final_status": "failed",
            "stages_completed": ["setup", "discovery"],
            "finding_counts": {"error": 1, "warning": 0, "suggestion": 0},
            "pr_link": None,
        }

        entry = WorkflowHistoryEntry.from_dict(data)

        assert entry.id == "test-id-123"
        assert entry.workflow_type == "refuel"
        assert entry.branch_name == "fix/bug"
        assert entry.timestamp == "2025-01-15T14:30:45"
        assert entry.final_status == "failed"
        assert entry.stages_completed == ("setup", "discovery")
        assert entry.finding_counts == {"error": 1, "warning": 0, "suggestion": 0}
        assert entry.pr_link is None

    def test_frozen_immutable(self) -> None:
        """Test that entry is immutable (frozen dataclass)."""
        entry = WorkflowHistoryEntry.create(
            workflow_type="fly",
            branch_name="test",
            final_status="completed",
            stages_completed=[],
            finding_counts={},
        )

        with pytest.raises(AttributeError):
            entry.workflow_type = "refuel"  # type: ignore


# =============================================================================
# WorkflowHistoryStore Tests
# =============================================================================


class TestWorkflowHistoryStoreLoad:
    """Tests for WorkflowHistoryStore.load() method."""

    def test_load_missing_file_returns_empty_list(self) -> None:
        """Test load returns empty list for missing file (T087)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "nonexistent.json"
            store = WorkflowHistoryStore(path=path)

            entries = store.load()

            assert entries == []

    def test_load_empty_file_returns_empty_list(self) -> None:
        """Test load handles empty file gracefully (T087)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "history.json"
            path.write_text("[]", encoding="utf-8")
            store = WorkflowHistoryStore(path=path)

            entries = store.load()

            assert entries == []

    def test_load_invalid_json_returns_empty_list(self) -> None:
        """Test load returns empty list for corrupted JSON (T087)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "history.json"
            path.write_text("{ invalid json", encoding="utf-8")
            store = WorkflowHistoryStore(path=path)

            entries = store.load()

            assert entries == []

    def test_load_non_list_returns_empty_list(self) -> None:
        """Test load returns empty list when JSON is not a list (T087)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "history.json"
            path.write_text('{"not": "a list"}', encoding="utf-8")
            store = WorkflowHistoryStore(path=path)

            entries = store.load()

            assert entries == []

    def test_load_valid_entries(self) -> None:
        """Test load parses valid entries correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "history.json"
            data = [
                {
                    "id": "entry-1",
                    "workflow_type": "fly",
                    "branch_name": "feature/a",
                    "timestamp": "2025-01-15T10:00:00",
                    "final_status": "completed",
                    "stages_completed": ["setup"],
                    "finding_counts": {"error": 0, "warning": 1, "suggestion": 2},
                    "pr_link": "https://github.com/test/repo/pull/1",
                },
                {
                    "id": "entry-2",
                    "workflow_type": "refuel",
                    "branch_name": "fix/b",
                    "timestamp": "2025-01-15T11:00:00",
                    "final_status": "failed",
                    "stages_completed": [],
                    "finding_counts": {"error": 1, "warning": 0, "suggestion": 0},
                    "pr_link": None,
                },
            ]
            path.write_text(json.dumps(data), encoding="utf-8")
            store = WorkflowHistoryStore(path=path)

            entries = store.load()

            assert len(entries) == 2
            assert entries[0].id == "entry-1"
            assert entries[0].workflow_type == "fly"
            assert entries[1].id == "entry-2"
            assert entries[1].workflow_type == "refuel"

    def test_load_skips_malformed_entries(self) -> None:
        """Test load skips entries with missing required fields (T087)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "history.json"
            data = [
                {
                    "id": "valid-entry",
                    "workflow_type": "fly",
                    "branch_name": "test",
                    "timestamp": "2025-01-15T10:00:00",
                    "final_status": "completed",
                    "stages_completed": [],
                    "finding_counts": {},
                },
                {
                    "id": "malformed-entry",
                    # Missing required fields
                },
                {
                    "id": "another-valid-entry",
                    "workflow_type": "refuel",
                    "branch_name": "test2",
                    "timestamp": "2025-01-15T11:00:00",
                    "final_status": "failed",
                    "stages_completed": [],
                    "finding_counts": {},
                },
            ]
            path.write_text(json.dumps(data), encoding="utf-8")
            store = WorkflowHistoryStore(path=path)

            entries = store.load()

            # Should have loaded only the 2 valid entries
            assert len(entries) == 2
            assert entries[0].id == "valid-entry"
            assert entries[1].id == "another-valid-entry"


class TestWorkflowHistoryStoreSave:
    """Tests for WorkflowHistoryStore.save() method."""

    def test_save_creates_parent_directory(self) -> None:
        """Test save creates parent directory if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "subdir" / "history.json"
            store = WorkflowHistoryStore(path=path)

            entry = WorkflowHistoryEntry.create(
                workflow_type="fly",
                branch_name="test",
                final_status="completed",
                stages_completed=[],
                finding_counts={},
            )

            store.save([entry])

            assert path.exists()
            assert path.parent.exists()

    def test_save_writes_valid_json(self) -> None:
        """Test save writes valid JSON to disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "history.json"
            store = WorkflowHistoryStore(path=path)

            entry = WorkflowHistoryEntry.create(
                workflow_type="fly",
                branch_name="test",
                final_status="completed",
                stages_completed=["setup", "implementation"],
                finding_counts={"error": 0, "warning": 1, "suggestion": 2},
                pr_link="https://github.com/test/repo/pull/1",
            )

            store.save([entry])

            # Verify file contents
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)

            assert len(data) == 1
            assert data[0]["id"] == entry.id
            assert data[0]["workflow_type"] == "fly"

    def test_save_applies_fifo_eviction(self) -> None:
        """Test save applies FIFO eviction at max_entries limit (T088)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "history.json"
            store = WorkflowHistoryStore(path=path, max_entries=3)

            # Create 5 entries (exceeds max of 3)
            entries = [
                WorkflowHistoryEntry.create(
                    workflow_type="fly",
                    branch_name=f"branch-{i}",
                    final_status="completed",
                    stages_completed=[],
                    finding_counts={},
                )
                for i in range(5)
            ]

            store.save(entries)

            # Verify only the last 3 entries were saved
            loaded = store.load()
            assert len(loaded) == 3
            assert loaded[0].branch_name == "branch-2"
            assert loaded[1].branch_name == "branch-3"
            assert loaded[2].branch_name == "branch-4"

    def test_save_overwrites_existing_file(self) -> None:
        """Test save overwrites existing file atomically."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "history.json"
            store = WorkflowHistoryStore(path=path)

            # Write initial data
            entry1 = WorkflowHistoryEntry.create(
                workflow_type="fly",
                branch_name="initial",
                final_status="completed",
                stages_completed=[],
                finding_counts={},
            )
            store.save([entry1])

            # Overwrite with new data
            entry2 = WorkflowHistoryEntry.create(
                workflow_type="refuel",
                branch_name="updated",
                final_status="failed",
                stages_completed=[],
                finding_counts={},
            )
            store.save([entry2])

            # Verify only the new data exists
            loaded = store.load()
            assert len(loaded) == 1
            assert loaded[0].branch_name == "updated"


class TestWorkflowHistoryStoreAdd:
    """Tests for WorkflowHistoryStore.add() method."""

    def test_add_appends_new_entry(self) -> None:
        """Test add appends new entry to existing history (T088)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "history.json"
            store = WorkflowHistoryStore(path=path)

            # Add first entry
            entry1 = WorkflowHistoryEntry.create(
                workflow_type="fly",
                branch_name="first",
                final_status="completed",
                stages_completed=[],
                finding_counts={},
            )
            store.add(entry1)

            # Add second entry
            entry2 = WorkflowHistoryEntry.create(
                workflow_type="refuel",
                branch_name="second",
                final_status="completed",
                stages_completed=[],
                finding_counts={},
            )
            store.add(entry2)

            # Verify both entries exist
            loaded = store.load()
            assert len(loaded) == 2
            assert loaded[0].branch_name == "first"
            assert loaded[1].branch_name == "second"

    def test_add_enforces_fifo_eviction(self) -> None:
        """Test add enforces FIFO eviction at max_entries (T088)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "history.json"
            store = WorkflowHistoryStore(path=path, max_entries=3)

            # Add 5 entries one by one
            for i in range(5):
                entry = WorkflowHistoryEntry.create(
                    workflow_type="fly",
                    branch_name=f"branch-{i}",
                    final_status="completed",
                    stages_completed=[],
                    finding_counts={},
                )
                store.add(entry)

            # Verify only the last 3 entries were kept
            loaded = store.load()
            assert len(loaded) == 3
            assert loaded[0].branch_name == "branch-2"
            assert loaded[1].branch_name == "branch-3"
            assert loaded[2].branch_name == "branch-4"

    def test_add_to_empty_history(self) -> None:
        """Test add works when history file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "history.json"
            store = WorkflowHistoryStore(path=path)

            entry = WorkflowHistoryEntry.create(
                workflow_type="fly",
                branch_name="first",
                final_status="completed",
                stages_completed=[],
                finding_counts={},
            )
            store.add(entry)

            loaded = store.load()
            assert len(loaded) == 1
            assert loaded[0].branch_name == "first"


class TestWorkflowHistoryStoreGetRecent:
    """Tests for WorkflowHistoryStore.get_recent() method."""

    def test_get_recent_returns_newest_first(self) -> None:
        """Test get_recent returns entries in reverse order (newest first) (T089)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "history.json"
            store = WorkflowHistoryStore(path=path)

            # Add entries in chronological order
            for i in range(5):
                entry = WorkflowHistoryEntry.create(
                    workflow_type="fly",
                    branch_name=f"branch-{i}",
                    final_status="completed",
                    stages_completed=[],
                    finding_counts={},
                )
                store.add(entry)

            # Get recent entries
            recent = store.get_recent(10)

            # Should be in reverse order (newest first)
            assert len(recent) == 5
            assert recent[0].branch_name == "branch-4"  # Most recent
            assert recent[1].branch_name == "branch-3"
            assert recent[2].branch_name == "branch-2"
            assert recent[3].branch_name == "branch-1"
            assert recent[4].branch_name == "branch-0"  # Oldest

    def test_get_recent_limits_count(self) -> None:
        """Test get_recent respects the count limit (T089)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "history.json"
            store = WorkflowHistoryStore(path=path)

            # Add 10 entries
            for i in range(10):
                entry = WorkflowHistoryEntry.create(
                    workflow_type="fly",
                    branch_name=f"branch-{i}",
                    final_status="completed",
                    stages_completed=[],
                    finding_counts={},
                )
                store.add(entry)

            # Get only 3 most recent
            recent = store.get_recent(3)

            assert len(recent) == 3
            assert recent[0].branch_name == "branch-9"  # Most recent
            assert recent[1].branch_name == "branch-8"
            assert recent[2].branch_name == "branch-7"

    def test_get_recent_empty_history(self) -> None:
        """Test get_recent returns empty list for empty history."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "history.json"
            store = WorkflowHistoryStore(path=path)

            recent = store.get_recent(10)

            assert recent == []

    def test_get_recent_default_count(self) -> None:
        """Test get_recent uses default count of 10."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "history.json"
            store = WorkflowHistoryStore(path=path)

            # Add 15 entries
            for i in range(15):
                entry = WorkflowHistoryEntry.create(
                    workflow_type="fly",
                    branch_name=f"branch-{i}",
                    final_status="completed",
                    stages_completed=[],
                    finding_counts={},
                )
                store.add(entry)

            # Get recent without specifying count (should default to 10)
            recent = store.get_recent()

            assert len(recent) == 10
            assert recent[0].branch_name == "branch-14"  # Most recent


class TestWorkflowHistoryStoreClear:
    """Tests for WorkflowHistoryStore.clear() method."""

    def test_clear_deletes_history_file(self) -> None:
        """Test clear deletes the history file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "history.json"
            store = WorkflowHistoryStore(path=path)

            # Add an entry
            entry = WorkflowHistoryEntry.create(
                workflow_type="fly",
                branch_name="test",
                final_status="completed",
                stages_completed=[],
                finding_counts={},
            )
            store.add(entry)

            assert path.exists()

            # Clear history
            store.clear()

            assert not path.exists()

    def test_clear_on_nonexistent_file(self) -> None:
        """Test clear handles non-existent file gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "nonexistent.json"
            store = WorkflowHistoryStore(path=path)

            # Should not raise an error
            store.clear()

            assert not path.exists()
