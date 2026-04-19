"""Tests for refuel_report audit artifact.

Mirrors the fly_report pattern — a structured record written per refuel
run to .maverick/runs/<run_id>/refuel-report.json, regardless of
success or failure.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from maverick.workflows.refuel_maverick.refuel_report import (
    RefuelReport,
    write_refuel_report,
)


def _make_report(**overrides: object) -> RefuelReport:
    defaults: dict[str, object] = {
        "plan_name": "sample-plan",
        "flight_plan_path": "/abs/path/flight.md",
        "run_id": "abc12345",
        "outcome": "refueled",
        "started_at": "2026-04-19T10:00:00+00:00",
        "completed_at": "2026-04-19T10:15:00+00:00",
        "duration_seconds": 900.0,
        "skip_briefing": False,
        "phases_completed": ["parse_flight_plan", "gather_context", "decompose"],
        "work_units_count": 12,
        "fix_rounds": 1,
        "epic_id": "epic-42",
        "work_bead_ids": ["bead-1", "bead-2"],
        "error": None,
    }
    defaults.update(overrides)
    return RefuelReport(**defaults)  # type: ignore[arg-type]


class TestRefuelReport:
    def test_is_frozen(self) -> None:
        """RefuelReport instances must not be mutable after construction."""
        report = _make_report()
        with pytest.raises(AttributeError):
            report.outcome = "failed"  # type: ignore[misc]

    def test_to_dict_round_trips(self) -> None:
        report = _make_report()
        d = report.to_dict()
        assert d["plan_name"] == "sample-plan"
        assert d["outcome"] == "refueled"
        assert d["work_units_count"] == 12
        assert d["epic_id"] == "epic-42"
        assert d["error"] is None


class TestWriteRefuelReport:
    @pytest.mark.asyncio
    async def test_writes_json_to_run_dir(self, tmp_path: Path) -> None:
        run_dir = tmp_path / ".maverick" / "runs" / "abc12345"
        report = _make_report()

        written_path = await write_refuel_report(report, run_dir)

        assert written_path == run_dir / "refuel-report.json"
        assert written_path.exists()
        data = json.loads(written_path.read_text(encoding="utf-8"))
        assert data["plan_name"] == "sample-plan"
        assert data["phases_completed"] == [
            "parse_flight_plan",
            "gather_context",
            "decompose",
        ]

    @pytest.mark.asyncio
    async def test_creates_run_dir_if_missing(self, tmp_path: Path) -> None:
        """The writer should mkdir parents so failure path (no run_dir yet) still records."""
        run_dir = tmp_path / "does_not_exist" / "runs" / "deadbeef"
        report = _make_report(run_id="deadbeef", outcome="failed", error="boom")

        await write_refuel_report(report, run_dir)

        assert run_dir.exists()
        data = json.loads((run_dir / "refuel-report.json").read_text())
        assert data["outcome"] == "failed"
        assert data["error"] == "boom"

    @pytest.mark.asyncio
    async def test_failure_report_records_partial_state(self, tmp_path: Path) -> None:
        """A failed run still captures whatever state was collected."""
        run_dir = tmp_path / "runs" / "run1"
        report = _make_report(
            outcome="failed",
            error="decomposition timed out",
            work_units_count=0,
            fix_rounds=0,
            epic_id=None,
            work_bead_ids=[],
            phases_completed=["parse_flight_plan", "gather_context"],
        )

        await write_refuel_report(report, run_dir)

        data = json.loads((run_dir / "refuel-report.json").read_text())
        assert data["outcome"] == "failed"
        assert data["error"] == "decomposition timed out"
        assert data["phases_completed"] == ["parse_flight_plan", "gather_context"]
        assert data["epic_id"] is None
