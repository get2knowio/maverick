"""Tests for the pure records module (protection/records.py).

See specs/056-context-file-protection/data-model.md ("BlockRecord" and
"BlockCollector") and contracts/block-event.md for the normative field
list and JSON shape this module implements.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from maverick.protection.records import (
    BlockCollector,
    BlockRecord,
    blocks_artifact_dict,
    drain_and_report,
    persist_blocks_artifact,
)


def _make_record(**overrides: object) -> BlockRecord:
    defaults: dict[str, object] = {
        "agent_role": "implement",
        "workflow": "fly-beads",
        "operation": "edit",
        "path": "CLAUDE.md",
        "layer": "pre-write",
    }
    defaults.update(overrides)
    return BlockRecord(**defaults)  # type: ignore[arg-type]


class TestBlockRecordFrozen:
    def test_mutating_a_field_raises(self) -> None:
        record = _make_record()
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            record.path = "AGENTS.md"  # type: ignore[misc]

    def test_mutating_optional_field_raises(self) -> None:
        record = _make_record()
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            record.detail = "changed"  # type: ignore[misc]


class TestBlockRecordDefaults:
    def test_optional_fields_default_to_none(self) -> None:
        record = _make_record()
        assert record.destination_path is None
        assert record.bead_id is None
        assert record.detail is None

    def test_timestamp_defaults_to_a_float(self) -> None:
        record = _make_record()
        assert isinstance(record.timestamp, float)

    def test_two_default_timestamps_are_not_required_to_match(self) -> None:
        # time.time() is monotonic-ish per call; just confirm both are floats
        # and construction doesn't raise or share mutable state.
        first = _make_record()
        second = _make_record()
        assert isinstance(first.timestamp, float)
        assert isinstance(second.timestamp, float)


class TestBlockRecordToDict:
    def test_returns_exactly_the_contract_field_set(self) -> None:
        record = _make_record()
        result = record.to_dict()
        assert set(result.keys()) == {
            "agent_role",
            "workflow",
            "operation",
            "path",
            "destination_path",
            "layer",
            "bead_id",
            "detail",
            "timestamp",
        }

    def test_values_round_trip(self) -> None:
        record = BlockRecord(
            agent_role="review",
            workflow="spec-chain",
            operation="rename",
            path="AGENTS.md",
            layer="backstop",
            destination_path="sub/AGENTS.md",
            bead_id="bd-1234",
            detail="matched default rule: basename AGENTS.md",
            timestamp=1786121809.412,
        )
        result = record.to_dict()
        assert result == {
            "agent_role": "review",
            "workflow": "spec-chain",
            "operation": "rename",
            "path": "AGENTS.md",
            "destination_path": "sub/AGENTS.md",
            "layer": "backstop",
            "bead_id": "bd-1234",
            "detail": "matched default rule: basename AGENTS.md",
            "timestamp": 1786121809.412,
        }

    def test_no_wrapping_event_key(self) -> None:
        record = _make_record()
        result = record.to_dict()
        assert "event" not in result

    def test_returns_plain_dict(self) -> None:
        record = _make_record()
        assert type(record.to_dict()) is dict


class TestBlockRecordFromDict:
    def test_round_trips_through_to_dict(self) -> None:
        record = BlockRecord(
            agent_role="implement",
            workflow="fly-beads",
            operation="rename",
            path="notes.txt",
            layer="pre-write",
            destination_path="AGENTS.md",
            bead_id="bd-1",
            detail="reason",
            timestamp=42.0,
        )
        assert BlockRecord.from_dict(record.to_dict()) == record

    def test_missing_optional_fields_default(self) -> None:
        record = BlockRecord.from_dict(
            {
                "agent_role": "implement",
                "workflow": "fly-beads",
                "operation": "edit",
                "path": "CLAUDE.md",
                "layer": "backstop",
            }
        )
        assert record.destination_path is None
        assert record.bead_id is None
        assert record.detail is None


class TestBlockCollectorAppendDrain:
    def test_drain_on_empty_collector_returns_empty_list(self) -> None:
        collector = BlockCollector()
        assert collector.drain() == []

    def test_append_then_drain_returns_appended_record(self) -> None:
        collector = BlockCollector()
        record = _make_record()
        collector.append(record)
        assert collector.drain() == [record]

    def test_multiple_appends_accumulate_before_drain(self) -> None:
        collector = BlockCollector()
        first = _make_record(path="CLAUDE.md")
        second = _make_record(path="AGENTS.md")
        third = _make_record(path=".specify/memory/constitution.md")
        collector.append(first)
        collector.append(second)
        collector.append(third)
        assert collector.drain() == [first, second, third]

    def test_drain_returns_records_in_append_order(self) -> None:
        collector = BlockCollector()
        records = [_make_record(path=f"file-{i}.md") for i in range(5)]
        for record in records:
            collector.append(record)
        assert collector.drain() == records

    def test_drain_empties_the_collector(self) -> None:
        collector = BlockCollector()
        collector.append(_make_record())
        collector.drain()
        assert collector.drain() == []

    def test_append_after_drain_is_captured_by_next_drain(self) -> None:
        collector = BlockCollector()
        collector.append(_make_record(path="CLAUDE.md"))
        collector.drain()
        second = _make_record(path="AGENTS.md")
        collector.append(second)
        assert collector.drain() == [second]


class TestBlocksArtifactDict:
    def test_shape_matches_contract(self) -> None:
        records = [_make_record(path="CLAUDE.md"), _make_record(path="AGENTS.md")]
        body = blocks_artifact_dict(run_id="abc123", workflow="fly-beads", records=records)
        assert body["schema_version"] == 1
        assert body["run_id"] == "abc123"
        assert body["workflow"] == "fly-beads"
        assert isinstance(body["generated_at"], str)
        assert body["blocks"] == [r.to_dict() for r in records]

    def test_empty_records_yields_empty_blocks_list(self) -> None:
        body = blocks_artifact_dict(run_id="abc123", workflow="fly-beads", records=[])
        assert body["blocks"] == []


class TestPersistBlocksArtifact:
    async def test_writes_file_when_records_present(self, tmp_path: Path) -> None:
        records = [_make_record(path="CLAUDE.md")]
        run_dir = tmp_path / "runs" / "abc123"
        run_dir.mkdir(parents=True)

        result = await persist_blocks_artifact(
            run_dir=run_dir, run_id="abc123", workflow="fly-beads", records=records
        )

        assert result == run_dir / "protection-blocks.json"
        assert result.is_file()
        data = json.loads(result.read_text())
        assert data["run_id"] == "abc123"
        assert data["blocks"][0]["path"] == "CLAUDE.md"

    async def test_no_file_written_when_records_empty(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "runs" / "abc123"
        run_dir.mkdir(parents=True)

        result = await persist_blocks_artifact(
            run_dir=run_dir, run_id="abc123", workflow="fly-beads", records=[]
        )

        assert result is None
        assert not (run_dir / "protection-blocks.json").exists()

    async def test_write_failure_degrades_to_none_never_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _boom(*args: object, **kwargs: object) -> None:
            raise OSError("disk full")

        monkeypatch.setattr("maverick.protection.records.atomic_write_json", _boom)
        run_dir = tmp_path / "runs" / "abc123"
        run_dir.mkdir(parents=True)

        result = await persist_blocks_artifact(
            run_dir=run_dir, run_id="abc123", workflow="fly-beads", records=[_make_record()]
        )
        assert result is None


class TestDrainAndReport:
    async def test_none_collector_is_a_no_op(self, tmp_path: Path) -> None:
        result = await drain_and_report(None, cwd=tmp_path, run_id="abc123", workflow="reconcile")
        assert result == []

    async def test_empty_collector_writes_nothing(self, tmp_path: Path) -> None:
        collector = BlockCollector()
        result = await drain_and_report(
            collector, cwd=tmp_path, run_id="abc123", workflow="reconcile"
        )
        assert result == []
        assert not (tmp_path / ".maverick" / "runs" / "abc123" / "protection-blocks.json").exists()

    async def test_drains_and_persists(self, tmp_path: Path) -> None:
        collector = BlockCollector()
        record = _make_record(path="CLAUDE.md")
        collector.append(record)

        result = await drain_and_report(
            collector, cwd=tmp_path, run_id="abc123", workflow="reconcile"
        )

        assert result == [record]
        assert collector.drain() == []
        artifact_path = tmp_path / ".maverick" / "runs" / "abc123" / "protection-blocks.json"
        assert artifact_path.is_file()
        data = json.loads(artifact_path.read_text())
        assert data["workflow"] == "reconcile"
        assert data["blocks"][0]["path"] == "CLAUDE.md"
