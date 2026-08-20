"""Unit tests for `maverick.workspace.journal`'s `ApplicationRecord`
read/write/clear cycle.

Covers T041: the record is written before an application and cleared after,
the write is atomic (temp + rename), and it carries `schema_version`. See
specs/057-isolated-bead-workspaces/contracts/isolation-primitive.md (C2, C4
step 3/6, C5) and research.md R8 for the behavioral contract, and
data-model.md's `ApplicationRecord` section for the field shapes.

Pure file I/O against a bare `tmp_path` checkout directory — no real jj repo
needed here; `journal.py`'s record functions take a plain `Path`.

As of this writing, `src/maverick/workspace/journal.py` is an empty stub
(only a module docstring) — every test below is expected to fail on import
(TDD red phase) until a later phase in this same feature implements it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from maverick.workspace import journal
from maverick.workspace.journal import ApplicationRecord

_JOURNAL_RELPATH = Path(".maverick") / "runs" / "isolation-journal.json"


def _make_record(
    *,
    run_id: str = "run-t041",
    workflow: str = "fly",
    unit_key: str = "bd-1",
    operation: str = "fold-back",
    restore_operation_id: str = "abc123def456",
    workspace_path: str = "/home/user/.maverick/workspaces/repo/fly/bd-1",
    started_at: datetime | None = None,
) -> ApplicationRecord:
    return ApplicationRecord(
        schema_version=1,
        run_id=run_id,
        workflow=workflow,
        unit_key=unit_key,
        operation=operation,
        restore_operation_id=restore_operation_id,
        workspace_path=workspace_path,
        started_at=started_at or datetime(2026, 8, 20, 12, 0, 0, tzinfo=UTC),
    )


class TestWriteReadRoundTrip:
    async def test_write_then_read_round_trips_full_record(self, tmp_path: Path) -> None:
        record = _make_record()

        await journal.write_record(tmp_path, record)
        loaded = await journal.read_record(tmp_path)

        assert loaded is not None
        assert loaded == record
        assert loaded.schema_version == 1
        assert loaded.run_id == "run-t041"
        assert loaded.workflow == "fly"
        assert loaded.unit_key == "bd-1"
        assert loaded.operation == "fold-back"
        assert loaded.restore_operation_id == "abc123def456"
        assert loaded.workspace_path == "/home/user/.maverick/workspaces/repo/fly/bd-1"
        assert loaded.started_at == datetime(2026, 8, 20, 12, 0, 0, tzinfo=UTC)

    async def test_write_record_lands_at_expected_path(self, tmp_path: Path) -> None:
        record = _make_record()

        await journal.write_record(tmp_path, record)

        assert (tmp_path / _JOURNAL_RELPATH).is_file()

    async def test_round_trip_preserves_undo_operation(self, tmp_path: Path) -> None:
        record = _make_record(operation="undo", unit_key="bd-2")

        await journal.write_record(tmp_path, record)
        loaded = await journal.read_record(tmp_path)

        assert loaded is not None
        assert loaded.operation == "undo"
        assert loaded.unit_key == "bd-2"


class TestReadMissing:
    async def test_read_record_returns_none_when_no_journal_file(self, tmp_path: Path) -> None:
        result = await journal.read_record(tmp_path)
        assert result is None

    async def test_read_record_returns_none_when_runs_dir_absent(self, tmp_path: Path) -> None:
        # No `.maverick/` directory at all — must not raise.
        assert not (tmp_path / ".maverick").exists()
        result = await journal.read_record(tmp_path)
        assert result is None


class TestClearRecord:
    async def test_clear_record_removes_file(self, tmp_path: Path) -> None:
        record = _make_record()
        await journal.write_record(tmp_path, record)
        assert (tmp_path / _JOURNAL_RELPATH).is_file()

        await journal.clear_record(tmp_path)

        assert not (tmp_path / _JOURNAL_RELPATH).exists()
        assert await journal.read_record(tmp_path) is None

    async def test_clear_record_on_absent_file_is_idempotent(self, tmp_path: Path) -> None:
        assert not (tmp_path / _JOURNAL_RELPATH).exists()

        # Must not raise.
        await journal.clear_record(tmp_path)
        await journal.clear_record(tmp_path)

        assert not (tmp_path / _JOURNAL_RELPATH).exists()


class TestAtomicWrite:
    async def test_write_leaves_no_temp_file_behind(self, tmp_path: Path) -> None:
        """After a successful write, the runs directory contains only the
        final `isolation-journal.json` — no leftover `.tmp`/partial file
        from the temp-then-rename mechanism (data-model.md: "Atomic write
        (temp + rename), same as `notify/state.py`")."""
        record = _make_record()

        await journal.write_record(tmp_path, record)

        runs_dir = tmp_path / ".maverick" / "runs"
        entries = sorted(p.name for p in runs_dir.iterdir())
        assert entries == ["isolation-journal.json"]

    async def test_repeated_writes_leave_no_temp_files(self, tmp_path: Path) -> None:
        for i in range(3):
            record = _make_record(unit_key=f"bd-{i}")
            await journal.write_record(tmp_path, record)

        runs_dir = tmp_path / ".maverick" / "runs"
        entries = sorted(p.name for p in runs_dir.iterdir())
        assert entries == ["isolation-journal.json"]

    async def test_write_creates_parent_directories(self, tmp_path: Path) -> None:
        assert not (tmp_path / ".maverick").exists()
        record = _make_record()

        await journal.write_record(tmp_path, record)

        assert (tmp_path / _JOURNAL_RELPATH).is_file()


class TestToDict:
    def test_to_dict_round_trips_all_fields(self) -> None:
        record = _make_record()
        d = record.to_dict()

        assert d == {
            "schema_version": 1,
            "run_id": "run-t041",
            "workflow": "fly",
            "unit_key": "bd-1",
            "operation": "fold-back",
            "restore_operation_id": "abc123def456",
            "workspace_path": "/home/user/.maverick/workspaces/repo/fly/bd-1",
            "started_at": "2026-08-20T12:00:00+00:00",
        }
