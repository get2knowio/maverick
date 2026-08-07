"""Unit tests for ``maverick review --list [--json]`` (T006/T010,
053-assumption-review-console).

Mocks ``BeadClient.verify_available`` and
``maverick.assumptions.ledger.report_entries`` — the same mocking style as
``tests/unit/cli/test_review_command.py`` — so no real ``bd`` invocation
occurs.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

from click.testing import CliRunner

from maverick.assumptions.models import (
    STATUS_ANSWERED,
    STATUS_OPEN,
    STATUS_WAIVED,
    AssumptionRecord,
    AssumptionReportEntry,
    Severity,
)
from maverick.cli.commands.review import review


def _entry(
    bead_id: str,
    *,
    owner_spec: str,
    severity: Severity,
    status: str = STATUS_OPEN,
    pending_reconcile: bool = False,
    question: str = "Q?",
    created_at: str | None = None,
    waived_by: str = "alice",
    auto_resolved: bool = False,
) -> AssumptionReportEntry:
    record = AssumptionRecord(
        bead_id=bead_id,
        question=question,
        adopted_answer="A.",
        alternatives=(),
        severity=severity,
        severity_defaulted=False,
        status=status,
        owner_spec=owner_spec,
        source_bead="src-1",
        change_ids=(),
        is_legacy=False,
        created_at=created_at,
    )
    return AssumptionReportEntry(
        record=record,
        final_answer="A." if status == STATUS_ANSWERED else None,
        waived_by=waived_by if status == STATUS_WAIVED else None,
        waived_at="2026-01-01T00:00:00+00:00" if status == STATUS_WAIVED else None,
        waive_reason="n/a" if status == STATUS_WAIVED else None,
        reconcile_status=None,
        reconciled_answer=None,
        reconcile_change_id=None,
        reconcile_reason=None,
        pending_reconcile=pending_reconcile,
        auto_resolved=auto_resolved,
    )


def _patched(entries: tuple[AssumptionReportEntry, ...], *, available: bool = True):
    return (
        patch(
            "maverick.beads.client.BeadClient.verify_available",
            new=AsyncMock(return_value=available),
        ),
        patch(
            "maverick.assumptions.ledger.report_entries",
            new=AsyncMock(return_value=entries),
        ),
    )


class TestDefaultStatusFilter:
    def test_default_selects_open_only(self) -> None:
        entries = (
            _entry("dea-1", owner_spec="049-spec", severity=Severity.MEDIUM, status=STATUS_OPEN),
            _entry(
                "dea-2", owner_spec="049-spec", severity=Severity.MEDIUM, status=STATUS_ANSWERED
            ),
            _entry("dea-3", owner_spec="049-spec", severity=Severity.MEDIUM, status=STATUS_WAIVED),
        )
        verify, sweep = _patched(entries)
        runner = CliRunner()
        with verify, sweep:
            result = runner.invoke(review, ["--list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        ids = [row["bead_id"] for row in data["result"]["entries"]]
        assert ids == ["dea-1"]


class TestRepeatableOptions:
    def test_status_option_repeatable_or_within_option(self) -> None:
        entries = (
            _entry("dea-1", owner_spec="049-spec", severity=Severity.MEDIUM, status=STATUS_OPEN),
            _entry(
                "dea-2", owner_spec="049-spec", severity=Severity.MEDIUM, status=STATUS_ANSWERED
            ),
            _entry("dea-3", owner_spec="049-spec", severity=Severity.MEDIUM, status=STATUS_WAIVED),
        )
        verify, sweep = _patched(entries)
        runner = CliRunner()
        with verify, sweep:
            result = runner.invoke(
                review,
                ["--list", "--status", "open", "--status", "answered", "--json"],
            )
        assert result.exit_code == 0
        data = json.loads(result.output)
        ids = {row["bead_id"] for row in data["result"]["entries"]}
        assert ids == {"dea-1", "dea-2"}

    def test_spec_and_severity_and_across_options(self) -> None:
        entries = (
            _entry("dea-1", owner_spec="049-spec", severity=Severity.HIGH, status=STATUS_OPEN),
            _entry("dea-2", owner_spec="049-spec", severity=Severity.LOW, status=STATUS_OPEN),
            _entry("dea-3", owner_spec="050-spec", severity=Severity.HIGH, status=STATUS_OPEN),
        )
        verify, sweep = _patched(entries)
        runner = CliRunner()
        with verify, sweep:
            result = runner.invoke(
                review,
                [
                    "--list",
                    "--spec",
                    "049-spec",
                    "--severity",
                    "high",
                    "--json",
                ],
            )
        assert result.exit_code == 0
        data = json.loads(result.output)
        ids = [row["bead_id"] for row in data["result"]["entries"]]
        assert ids == ["dea-1"]

    def test_severity_option_repeatable_or_within_option(self) -> None:
        entries = (
            _entry("dea-1", owner_spec="049-spec", severity=Severity.HIGH, status=STATUS_OPEN),
            _entry("dea-2", owner_spec="049-spec", severity=Severity.LOW, status=STATUS_OPEN),
            _entry("dea-3", owner_spec="049-spec", severity=Severity.MEDIUM, status=STATUS_OPEN),
        )
        verify, sweep = _patched(entries)
        runner = CliRunner()
        with verify, sweep:
            result = runner.invoke(
                review,
                ["--list", "--severity", "high", "--severity", "low", "--json"],
            )
        assert result.exit_code == 0
        data = json.loads(result.output)
        ids = {row["bead_id"] for row in data["result"]["entries"]}
        assert ids == {"dea-1", "dea-2"}


class TestCanonicalOrdering:
    def test_owner_spec_asc_then_severity_desc_then_stable(self) -> None:
        # Deliberately constructed out of final order.
        entries = (
            _entry("dea-a", owner_spec="050-spec", severity=Severity.LOW, status=STATUS_OPEN),
            _entry("dea-b", owner_spec="049-spec", severity=Severity.LOW, status=STATUS_OPEN),
            _entry("dea-c", owner_spec="049-spec", severity=Severity.HIGH, status=STATUS_OPEN),
            _entry("dea-d", owner_spec="049-spec", severity=Severity.HIGH, status=STATUS_OPEN),
        )
        verify, sweep = _patched(entries)
        runner = CliRunner()
        with verify, sweep:
            result = runner.invoke(review, ["--list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        ids = [row["bead_id"] for row in data["result"]["entries"]]
        # 049-spec before 050-spec; within 049-spec, high (c, d — stable
        # order preserved) before low (b).
        assert ids == ["dea-c", "dea-d", "dea-b", "dea-a"]


class TestCounts:
    def test_counts_reflect_filtered_selection(self) -> None:
        entries = (
            _entry("dea-1", owner_spec="049-spec", severity=Severity.HIGH, status=STATUS_OPEN),
            _entry(
                "dea-2",
                owner_spec="049-spec",
                severity=Severity.MEDIUM,
                status=STATUS_OPEN,
                pending_reconcile=True,
            ),
            _entry("dea-3", owner_spec="050-spec", severity=Severity.LOW, status=STATUS_ANSWERED),
        )
        verify, sweep = _patched(entries)
        runner = CliRunner()
        with verify, sweep:
            result = runner.invoke(
                review, ["--list", "--status", "open", "--status", "answered", "--json"]
            )
        assert result.exit_code == 0
        data = json.loads(result.output)
        counts = data["result"]["counts"]
        assert counts["total"] == 3
        assert counts["by_status"] == {"open": 2, "answered": 1, "waived": 0}
        assert counts["by_severity"] == {"low": 1, "medium": 1, "high": 1}
        assert counts["pending_reconcile"] == 1

    def test_auto_resolved_entry_counts_in_waived_bucket(self) -> None:
        """055 T030 regression/proof: an auto-resolved entry
        (``waived_by="maverick-resolver"``, ``auto_resolved=True``) counts
        in the "waived" bucket in `_build_counts` exactly like any human
        waive — no special-casing needed, since counting keys off
        ``entry.record.status`` (equivalently ``entry.bucket``), which is
        ``STATUS_WAIVED`` regardless of who waived it."""
        entries = (
            _entry(
                "dea-1",
                owner_spec="055-spec",
                severity=Severity.LOW,
                status=STATUS_WAIVED,
                waived_by="maverick-resolver",
                auto_resolved=True,
            ),
        )
        verify, sweep = _patched(entries)
        runner = CliRunner()
        with verify, sweep:
            result = runner.invoke(review, ["--list", "--status", "waived", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        counts = data["result"]["counts"]
        assert counts["by_status"]["waived"] == 1
        row = data["result"]["entries"][0]
        assert row["bucket"] == "waived"
        assert row["auto_resolved"] is True


class TestCreatedAt:
    def test_created_at_present_value_flows_into_row(self) -> None:
        entries = (
            _entry(
                "dea-1",
                owner_spec="049-spec",
                severity=Severity.MEDIUM,
                status=STATUS_OPEN,
                created_at="2026-07-24T14:00:00+00:00",
            ),
        )
        verify, sweep = _patched(entries)
        runner = CliRunner()
        with verify, sweep:
            result = runner.invoke(review, ["--list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        row = data["result"]["entries"][0]
        assert row["created_at"] == "2026-07-24T14:00:00+00:00"

    def test_created_at_absent_is_none_in_row(self) -> None:
        entries = (
            _entry(
                "dea-1",
                owner_spec="049-spec",
                severity=Severity.MEDIUM,
                status=STATUS_OPEN,
                created_at=None,
            ),
        )
        verify, sweep = _patched(entries)
        runner = CliRunner()
        with verify, sweep:
            result = runner.invoke(review, ["--list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        row = data["result"]["entries"][0]
        assert row["created_at"] is None


class TestEmptyQueue:
    def test_empty_queue_is_ok_true_empty_entries(self) -> None:
        verify, sweep = _patched(())
        runner = CliRunner()
        with verify, sweep:
            result = runner.invoke(review, ["--list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["result"]["entries"] == []
        assert data["result"]["counts"]["total"] == 0


class TestBdUnavailable:
    def test_bd_unavailable_json(self) -> None:
        verify, sweep = _patched((), available=False)
        runner = CliRunner()
        with verify, sweep:
            result = runner.invoke(review, ["--list", "--json"])
        assert result.exit_code != 0
        data = json.loads(result.output)
        assert data["ok"] is False
        assert data["error"]["kind"] == "bd-unavailable"

    def test_bd_unavailable_human(self) -> None:
        verify, sweep = _patched((), available=False)
        runner = CliRunner()
        with verify, sweep:
            result = runner.invoke(review, ["--list"])
        assert result.exit_code != 0


class TestMutualExclusion:
    def test_list_and_bead_id_json(self) -> None:
        runner = CliRunner()
        result = runner.invoke(review, ["dea-1", "--list", "--json"])
        assert result.exit_code != 0
        data = json.loads(result.output)
        assert data["ok"] is False
        assert data["error"]["kind"] == "validation"

    def test_list_and_bead_id_human(self) -> None:
        runner = CliRunner()
        result = runner.invoke(review, ["dea-1", "--list"])
        assert result.exit_code != 0
        assert "mutually exclusive" in result.output.lower()

    def test_list_and_answer_flag(self) -> None:
        runner = CliRunner()
        result = runner.invoke(review, ["--list", "--answer", "text", "--json"])
        assert result.exit_code != 0
        data = json.loads(result.output)
        assert data["error"]["kind"] == "validation"

    def test_list_and_waive_flag(self) -> None:
        runner = CliRunner()
        result = runner.invoke(review, ["--list", "--waive", "reason", "--json"])
        assert result.exit_code != 0

    def test_list_and_approve_flag(self) -> None:
        runner = CliRunner()
        result = runner.invoke(review, ["--list", "--approve", "--json"])
        assert result.exit_code != 0

    def test_list_and_reject_flag(self) -> None:
        runner = CliRunner()
        result = runner.invoke(review, ["--list", "--reject", "guidance", "--json"])
        assert result.exit_code != 0

    def test_list_and_defer_flag(self) -> None:
        runner = CliRunner()
        result = runner.invoke(review, ["--list", "--defer", "--json"])
        assert result.exit_code != 0


class TestHumanModeRendering:
    def test_renders_table_without_crashing(self) -> None:
        entries = (
            _entry("dea-1", owner_spec="049-spec", severity=Severity.HIGH, status=STATUS_OPEN),
        )
        verify, sweep = _patched(entries)
        runner = CliRunner()
        with verify, sweep:
            result = runner.invoke(review, ["--list"])
        assert result.exit_code == 0
        assert "dea-1" in result.output

    def test_renders_empty_without_crashing(self) -> None:
        verify, sweep = _patched(())
        runner = CliRunner()
        with verify, sweep:
            result = runner.invoke(review, ["--list"])
        assert result.exit_code == 0
