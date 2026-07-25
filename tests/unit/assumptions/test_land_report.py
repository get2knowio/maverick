"""Tests for maverick.assumptions.land_report — pure frontier/classify logic.

Covers data-model.md's ``frontier(entries) -> LandFrontier`` and
``classify(entries) -> LandVerification`` rules (research R3): the land
gate evaluates every open entry of any severity (incl. legacy) plus
answered entries pending reconciliation; a successful land is classified
verified / conditionally-verified based on whether any entry was waived.
"""

from __future__ import annotations

from pathlib import Path

from maverick.assumptions.land_report import classify, frontier
from maverick.assumptions.models import (
    STATUS_ANSWERED,
    STATUS_OPEN,
    STATUS_WAIVED,
    AssumptionRecord,
    AssumptionReportEntry,
    LandVerification,
    Severity,
)


def _record(
    *,
    bead_id: str = "dea-1",
    status: str = STATUS_OPEN,
    severity: Severity = Severity.LOW,
    is_legacy: bool = False,
    owner_spec: str = "052-conditional-landing",
    change_ids: tuple[str, ...] = (),
) -> AssumptionRecord:
    return AssumptionRecord(
        bead_id=bead_id,
        question="Q?",
        adopted_answer="A.",
        alternatives=(),
        severity=severity,
        severity_defaulted=False,
        status=status,
        owner_spec=owner_spec,
        source_bead="dea-0",
        change_ids=change_ids,
        is_legacy=is_legacy,
    )


def _entry(
    *,
    bead_id: str = "dea-1",
    status: str = STATUS_OPEN,
    severity: Severity = Severity.LOW,
    is_legacy: bool = False,
    pending_reconcile: bool = False,
    reconcile_status: str | None = None,
    owner_spec: str = "052-conditional-landing",
    change_ids: tuple[str, ...] = (),
    reconcile_change_id: str | None = None,
) -> AssumptionReportEntry:
    return AssumptionReportEntry(
        record=_record(
            bead_id=bead_id,
            status=status,
            severity=severity,
            is_legacy=is_legacy,
            owner_spec=owner_spec,
            change_ids=change_ids,
        ),
        final_answer="Yes." if status == STATUS_ANSWERED else None,
        waived_by="alice" if status == STATUS_WAIVED else None,
        waived_at="2026-07-24T14:00:00Z" if status == STATUS_WAIVED else None,
        waive_reason="n/a" if status == STATUS_WAIVED else None,
        reconcile_status=reconcile_status,
        reconciled_answer=None,
        reconcile_change_id=reconcile_change_id,
        reconcile_reason=None,
        pending_reconcile=pending_reconcile,
    )


class TestFrontier:
    def test_open_low_severity_is_in_open_entries(self) -> None:
        entry = _entry(status=STATUS_OPEN, severity=Severity.LOW)
        result = frontier((entry,))
        assert result.open_entries == (entry,)
        assert result.is_empty is False

    def test_open_medium_and_high_are_in_open_entries(self) -> None:
        med = _entry(bead_id="dea-med", status=STATUS_OPEN, severity=Severity.MEDIUM)
        high = _entry(bead_id="dea-high", status=STATUS_OPEN, severity=Severity.HIGH)
        result = frontier((med, high))
        assert set(result.open_entries) == {med, high}

    def test_open_legacy_entry_is_in_open_entries(self) -> None:
        entry = _entry(status=STATUS_OPEN, severity=Severity.MEDIUM, is_legacy=True)
        result = frontier((entry,))
        assert result.open_entries == (entry,)

    def test_pending_reconcile_entry_is_in_pending_entries_not_open(self) -> None:
        entry = _entry(status=STATUS_ANSWERED, pending_reconcile=True)
        result = frontier((entry,))
        assert result.pending_reconcile_entries == (entry,)
        assert result.open_entries == ()
        assert result.is_empty is False

    def test_terminal_reconciled_entry_does_not_block(self) -> None:
        entry = _entry(
            status=STATUS_ANSWERED, pending_reconcile=False, reconcile_status="reconciled"
        )
        result = frontier((entry,))
        assert result.is_empty is True

    def test_waived_entry_does_not_block(self) -> None:
        entry = _entry(status=STATUS_WAIVED)
        result = frontier((entry,))
        assert result.is_empty is True

    def test_answered_entry_does_not_block(self) -> None:
        entry = _entry(status=STATUS_ANSWERED)
        result = frontier((entry,))
        assert result.is_empty is True

    def test_zero_entries_is_empty(self) -> None:
        result = frontier(())
        assert result.is_empty is True


class TestClassify:
    def test_open_low_severity_blocks(self) -> None:
        entry = _entry(status=STATUS_OPEN, severity=Severity.LOW)
        assert classify((entry,)) == LandVerification.BLOCKED

    def test_pending_reconcile_blocks(self) -> None:
        entry = _entry(status=STATUS_ANSWERED, pending_reconcile=True)
        assert classify((entry,)) == LandVerification.BLOCKED

    def test_terminal_reconcile_states_do_not_block(self) -> None:
        entry = _entry(
            status=STATUS_ANSWERED, pending_reconcile=False, reconcile_status="reconciled"
        )
        assert classify((entry,)) == LandVerification.VERIFIED

    def test_waived_only_is_conditionally_verified(self) -> None:
        answered = _entry(bead_id="dea-answered", status=STATUS_ANSWERED)
        waived = _entry(bead_id="dea-waived", status=STATUS_WAIVED)
        assert classify((answered, waived)) == LandVerification.CONDITIONALLY_VERIFIED

    def test_all_answered_is_verified(self) -> None:
        e1 = _entry(bead_id="dea-1", status=STATUS_ANSWERED)
        e2 = _entry(bead_id="dea-2", status=STATUS_ANSWERED)
        assert classify((e1, e2)) == LandVerification.VERIFIED

    def test_zero_entries_is_verified(self) -> None:
        assert classify(()) == LandVerification.VERIFIED

    def test_blocked_takes_priority_over_waived(self) -> None:
        open_entry = _entry(bead_id="dea-open", status=STATUS_OPEN)
        waived = _entry(bead_id="dea-waived", status=STATUS_WAIVED)
        assert classify((open_entry, waived)) == LandVerification.BLOCKED


class TestBuildReportSchema:
    def test_schema_version_and_top_level_fields(self) -> None:
        from maverick.assumptions.land_report import build_report

        report = build_report((), LandVerification.VERIFIED, run_id="a1b2c3d4", dry_run=False)
        data = report.to_dict()
        assert data["schema_version"] == 1
        assert data["run_id"] == "a1b2c3d4"
        assert data["dry_run"] is False
        assert data["verification"] == "verified"
        assert data["degraded"] is False
        assert "created_at" in data

    def test_totals_aggregate_across_specs(self) -> None:
        from maverick.assumptions.land_report import build_report

        entries = (
            _entry(bead_id="dea-1", status=STATUS_ANSWERED, owner_spec="spec-a"),
            _entry(bead_id="dea-2", status=STATUS_WAIVED, owner_spec="spec-a"),
            _entry(bead_id="dea-3", status=STATUS_OPEN, owner_spec="spec-b"),
            _entry(
                bead_id="dea-4",
                status=STATUS_ANSWERED,
                pending_reconcile=True,
                owner_spec="spec-b",
            ),
        )
        report = build_report(entries, LandVerification.BLOCKED, run_id="r1", dry_run=False)
        data = report.to_dict()
        assert data["totals"] == {"resolved": 2, "waived": 1, "open": 1, "pending_reconcile": 1}

    def test_specs_grouped_and_sorted_with_per_spec_counts(self) -> None:
        from maverick.assumptions.land_report import build_report

        entries = (
            _entry(bead_id="dea-b", status=STATUS_ANSWERED, owner_spec="spec-b"),
            _entry(bead_id="dea-a", status=STATUS_WAIVED, owner_spec="spec-a"),
        )
        report = build_report(
            entries, LandVerification.CONDITIONALLY_VERIFIED, run_id="r1", dry_run=False
        )
        data = report.to_dict()
        assert [s["owner_spec"] for s in data["specs"]] == ["spec-a", "spec-b"]
        spec_a = data["specs"][0]
        assert spec_a["counts"] == {"resolved": 0, "waived": 1, "open": 0, "pending_reconcile": 0}

    def test_waiver_only_present_on_waived_rows(self) -> None:
        from maverick.assumptions.land_report import build_report

        entries = (
            _entry(bead_id="dea-waived", status=STATUS_WAIVED),
            _entry(bead_id="dea-open", status=STATUS_OPEN),
        )
        report = build_report(entries, LandVerification.BLOCKED, run_id="r1", dry_run=False)
        data = report.to_dict()
        rows = {e["bead_id"]: e for e in data["specs"][0]["entries"]}
        assert rows["dea-waived"]["waiver"] == {
            "by": "alice",
            "at": "2026-07-24T14:00:00Z",
            "reason": "n/a",
        }
        assert rows["dea-open"]["waiver"] is None

    def test_affected_change_ids_includes_reconcile_correction(self) -> None:
        from maverick.assumptions.land_report import build_report

        entry = _entry(
            bead_id="dea-1",
            status=STATUS_ANSWERED,
            change_ids=("zzkw",),
            reconcile_change_id="rlvk",
        )
        report = build_report((entry,), LandVerification.VERIFIED, run_id="r1", dry_run=False)
        data = report.to_dict()
        row = data["specs"][0]["entries"][0]
        assert row["affected_change_ids"] == ["zzkw", "rlvk"]

    def test_legacy_annotation(self) -> None:
        from maverick.assumptions.land_report import build_report

        entry = _entry(
            bead_id="dea-1", status=STATUS_OPEN, is_legacy=True, severity=Severity.MEDIUM
        )
        report = build_report((entry,), LandVerification.BLOCKED, run_id="r1", dry_run=False)
        row = report.to_dict()["specs"][0]["entries"][0]
        assert "legacy" in row["annotations"]

    def test_needs_interactive_review_annotation(self) -> None:
        from maverick.assumptions.land_report import build_report

        entry = _entry(
            bead_id="dea-1",
            status=STATUS_ANSWERED,
            reconcile_status="needs-interactive-review",
        )
        report = build_report((entry,), LandVerification.VERIFIED, run_id="r1", dry_run=False)
        row = report.to_dict()["specs"][0]["entries"][0]
        assert "reconcile: needs-interactive-review" in row["annotations"]

    def test_pending_reconcile_annotation(self) -> None:
        from maverick.assumptions.land_report import build_report

        entry = _entry(bead_id="dea-1", status=STATUS_ANSWERED, pending_reconcile=True)
        report = build_report((entry,), LandVerification.BLOCKED, run_id="r1", dry_run=False)
        row = report.to_dict()["specs"][0]["entries"][0]
        assert "pending reconcile" in row["annotations"]

    def test_degraded_flag_and_omitted_verification(self) -> None:
        from maverick.assumptions.land_report import build_report

        report = build_report((), None, run_id="r1", dry_run=False, degraded=True)
        data = report.to_dict()
        assert data["degraded"] is True
        assert "verification" not in data

    def test_zero_entries_produces_empty_specs(self) -> None:
        from maverick.assumptions.land_report import build_report

        report = build_report((), LandVerification.VERIFIED, run_id="r1", dry_run=False)
        data = report.to_dict()
        assert data["specs"] == []
        assert data["totals"] == {"resolved": 0, "waived": 0, "open": 0, "pending_reconcile": 0}


class TestRenderMarkdown:
    def test_classification_banner_and_run_id(self) -> None:
        from maverick.assumptions.land_report import build_report, render_markdown

        report = build_report((), LandVerification.VERIFIED, run_id="a1b2c3d4", dry_run=False)
        md = render_markdown(report)
        assert "a1b2c3d4" in md
        assert "Verified" in md

    def test_dry_run_marker(self) -> None:
        from maverick.assumptions.land_report import build_report, render_markdown

        report = build_report((), LandVerification.BLOCKED, run_id="r1", dry_run=True)
        md = render_markdown(report)
        assert "DRY RUN" in md

    def test_per_spec_sections_present(self) -> None:
        from maverick.assumptions.land_report import build_report, render_markdown

        entries = (
            _entry(bead_id="dea-1", status=STATUS_ANSWERED, owner_spec="052-conditional-landing"),
        )
        report = build_report(entries, LandVerification.VERIFIED, run_id="r1", dry_run=False)
        md = render_markdown(report)
        assert "052-conditional-landing" in md

    def test_omits_empty_buckets(self) -> None:
        from maverick.assumptions.land_report import build_report, render_markdown

        entries = (_entry(bead_id="dea-1", status=STATUS_ANSWERED),)
        report = build_report(entries, LandVerification.VERIFIED, run_id="r1", dry_run=False)
        md = render_markdown(report)
        assert "Waived" not in md
        assert "Open" not in md
        assert "Resolved" in md

    def test_waived_row_includes_who_when_why(self) -> None:
        from maverick.assumptions.land_report import build_report, render_markdown

        entries = (_entry(bead_id="dea-1", status=STATUS_WAIVED),)
        report = build_report(
            entries, LandVerification.CONDITIONALLY_VERIFIED, run_id="r1", dry_run=False
        )
        md = render_markdown(report)
        assert "alice" in md
        assert "n/a" in md

    def test_zero_entries_prints_no_assumptions_adopted(self) -> None:
        from maverick.assumptions.land_report import build_report, render_markdown

        report = build_report((), LandVerification.VERIFIED, run_id="r1", dry_run=False)
        md = render_markdown(report)
        assert "No assumptions adopted" in md

    def test_footer_references_maverick_land(self) -> None:
        from maverick.assumptions.land_report import build_report, render_markdown

        report = build_report((), LandVerification.VERIFIED, run_id="r1", dry_run=False)
        md = render_markdown(report)
        assert "maverick land" in md.lower()


class TestPersistReport:
    def test_writes_json_and_markdown_atomically(self, tmp_path: Path) -> None:
        from maverick.assumptions.land_report import build_report, persist_report

        report = build_report((), LandVerification.VERIFIED, run_id="a1b2c3d4", dry_run=False)
        json_path, md_path = persist_report(report, cwd=tmp_path)

        assert json_path == tmp_path / ".maverick" / "runs" / "a1b2c3d4" / "land-report.json"
        assert md_path == tmp_path / ".maverick" / "runs" / "a1b2c3d4" / "land-report.md"
        assert json_path.is_file()
        assert md_path.is_file()

        import json as _json

        data = _json.loads(json_path.read_text(encoding="utf-8"))
        assert data["run_id"] == "a1b2c3d4"
