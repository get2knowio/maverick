"""Tests for ``ledger.report_entries()`` — the land frontier/report reader.

Covers research R1: a repo-wide, all-status materialization of every
ledger entry (plus legacy ``assumption-review`` beads), with per-entry
answer/waiver/reconcile state keys and the ``pending_reconcile`` flag
sourced from :func:`maverick.assumptions.ledger.answered_unreconciled_entries`.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from maverick.assumptions.ledger import report_entries
from maverick.assumptions.models import (
    ASSUMPTION_LABEL,
    ASSUMPTION_REVIEW_LABEL,
    KEY_ANSWER,
    KEY_OWNER_SPEC,
    KEY_RECONCILE_CHANGE_ID,
    KEY_RECONCILE_REASON,
    KEY_RECONCILE_STATUS,
    KEY_RECONCILED_ANSWER,
    KEY_SEVERITY,
    KEY_STATUS,
    KEY_WAIVE_REASON,
    KEY_WAIVED_AT,
    KEY_WAIVED_BY,
    NEEDS_HUMAN_REVIEW_LABEL,
    STATUS_ANSWERED,
    STATUS_OPEN,
    STATUS_WAIVED,
    Severity,
)
from maverick.beads.client import BeadClient
from maverick.beads.models import BeadDetails, BeadSummary


def _client() -> BeadClient:
    return BeadClient(cwd=Path("/tmp/repo"))


def _summary(bead_id: str, status: str = "open") -> BeadSummary:
    return BeadSummary(id=bead_id, title=bead_id, status=status, bead_type="task")


def _entry(
    bead_id: str,
    *,
    status: str = STATUS_OPEN,
    severity: str = "medium",
    bd_status: str | None = None,
    owner_spec: str = "052-conditional-landing",
    extra_state: dict[str, str] | None = None,
) -> BeadDetails:
    state = {KEY_SEVERITY: severity, KEY_STATUS: status, KEY_OWNER_SPEC: owner_spec}
    if extra_state:
        state.update(extra_state)
    return BeadDetails(
        id=bead_id,
        title=f"Assumption: {bead_id}",
        description="## Question\n\nQ?\n\n## Adopted Answer\n\nOriginal answer.\n\n",
        bead_type="task",
        status=bd_status or ("closed" if status != STATUS_OPEN else "open"),
        labels=[ASSUMPTION_LABEL],
        state=state,
    )


def _legacy_entry(bead_id: str, *, bd_status: str = "open") -> BeadDetails:
    return BeadDetails(
        id=bead_id,
        title="Review: legacy",
        description="legacy escalation",
        bead_type="task",
        status=bd_status,
        labels=[ASSUMPTION_REVIEW_LABEL, NEEDS_HUMAN_REVIEW_LABEL],
        state={"source_bead": "b-1", "flight_plan": "legacy-plan"},
    )


def _patched(entries: dict[str, BeadDetails], *, pending_ids: frozenset[str] = frozenset()):
    async def fake_query(self: BeadClient, filter_expr: str) -> list[BeadSummary]:
        return [_summary(k, status=entries[k].status) for k in entries]

    async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
        return entries[bead_id]

    async def fake_answered_unreconciled(client: BeadClient):
        from maverick.assumptions.ledger import _record_from_details

        return tuple(_record_from_details(entries[bid]) for bid in pending_ids)

    return (
        patch.object(BeadClient, "query", new=fake_query),
        patch.object(BeadClient, "show", new=fake_show),
        patch(
            "maverick.assumptions.ledger.answered_unreconciled_entries",
            new=fake_answered_unreconciled,
        ),
    )


class TestReportEntriesAllStatus:
    @pytest.mark.asyncio
    async def test_includes_closed_answered_and_waived_entries(self) -> None:
        entries = {
            "dea-open": _entry("dea-open", status=STATUS_OPEN),
            "dea-answered": _entry("dea-answered", status=STATUS_ANSWERED),
            "dea-waived": _entry("dea-waived", status=STATUS_WAIVED),
        }
        p1, p2, p3 = _patched(entries)
        with p1, p2, p3:
            result = await report_entries(_client())

        ids = {e.record.bead_id for e in result}
        assert ids == {"dea-open", "dea-answered", "dea-waived"}
        by_id = {e.record.bead_id: e for e in result}
        assert by_id["dea-open"].bucket == "open"
        assert by_id["dea-answered"].bucket == "resolved"
        assert by_id["dea-waived"].bucket == "waived"

    @pytest.mark.asyncio
    async def test_open_low_severity_is_included(self) -> None:
        """Unlike open_blocking_entries, the frontier reader is severity-agnostic."""
        entries = {"dea-low": _entry("dea-low", status=STATUS_OPEN, severity="low")}
        p1, p2, p3 = _patched(entries)
        with p1, p2, p3:
            result = await report_entries(_client())

        assert len(result) == 1
        assert result[0].record.severity == Severity.LOW


class TestReportEntriesLegacySynthesis:
    @pytest.mark.asyncio
    async def test_open_legacy_bead_surfaced_as_medium_open(self) -> None:
        entries = {"legacy-1": _legacy_entry("legacy-1", bd_status="open")}
        p1, p2, p3 = _patched(entries)
        with p1, p2, p3:
            result = await report_entries(_client())

        assert len(result) == 1
        assert result[0].record.is_legacy is True
        assert result[0].record.severity == Severity.MEDIUM
        assert result[0].bucket == "open"

    @pytest.mark.asyncio
    async def test_closed_legacy_bead_is_excluded(self) -> None:
        """A legacy bead has no resolved/waived state distinction once closed
        (``_legacy_record_from_details`` always synthesizes status=open) —
        including a closed one would misreport it as still-open forever, so
        it's dropped once closed (matches open_blocking_entries' pre-existing
        open-only semantics for legacy beads).
        """
        entries = {"legacy-1": _legacy_entry("legacy-1", bd_status="closed")}
        p1, p2, p3 = _patched(entries)
        with p1, p2, p3:
            result = await report_entries(_client())

        assert result == ()


class TestReportEntriesStateMaterialization:
    @pytest.mark.asyncio
    async def test_materializes_answer_waiver_and_reconcile_state(self) -> None:
        entries = {
            "dea-answered": _entry(
                "dea-answered",
                status=STATUS_ANSWERED,
                extra_state={KEY_ANSWER: "Yes, per bead."},
            ),
            "dea-waived": _entry(
                "dea-waived",
                status=STATUS_WAIVED,
                extra_state={
                    KEY_WAIVED_BY: "alice",
                    KEY_WAIVED_AT: "2026-07-24T14:00:00Z",
                    KEY_WAIVE_REASON: "not applicable",
                },
            ),
            "dea-reconciled": _entry(
                "dea-reconciled",
                status=STATUS_ANSWERED,
                extra_state={
                    KEY_ANSWER: "Changed answer.",
                    KEY_RECONCILE_STATUS: "reconciled",
                    KEY_RECONCILED_ANSWER: "changed answer.",
                    KEY_RECONCILE_CHANGE_ID: "rlvk123",
                    KEY_RECONCILE_REASON: "",
                },
            ),
        }
        p1, p2, p3 = _patched(entries)
        with p1, p2, p3:
            result = await report_entries(_client())

        by_id = {e.record.bead_id: e for e in result}
        assert by_id["dea-answered"].final_answer == "Yes, per bead."
        assert by_id["dea-waived"].waived_by == "alice"
        assert by_id["dea-waived"].waived_at == "2026-07-24T14:00:00Z"
        assert by_id["dea-waived"].waive_reason == "not applicable"
        assert by_id["dea-reconciled"].reconcile_status == "reconciled"
        assert by_id["dea-reconciled"].reconciled_answer == "changed answer."
        assert by_id["dea-reconciled"].reconcile_change_id == "rlvk123"

    @pytest.mark.asyncio
    async def test_missing_state_keys_default_to_none(self) -> None:
        entries = {"dea-open": _entry("dea-open", status=STATUS_OPEN)}
        p1, p2, p3 = _patched(entries)
        with p1, p2, p3:
            result = await report_entries(_client())

        entry = result[0]
        assert entry.final_answer is None
        assert entry.waived_by is None
        assert entry.reconcile_status is None
        assert entry.reconcile_change_id is None


class TestReportEntriesPendingReconcile:
    @pytest.mark.asyncio
    async def test_pending_reconcile_sourced_from_answered_unreconciled_entries(self) -> None:
        entries = {
            "dea-pending": _entry(
                "dea-pending", status=STATUS_ANSWERED, extra_state={KEY_ANSWER: "Changed."}
            ),
            "dea-stable": _entry(
                "dea-stable", status=STATUS_ANSWERED, extra_state={KEY_ANSWER: "Original answer."}
            ),
        }
        p1, p2, p3 = _patched(entries, pending_ids=frozenset({"dea-pending"}))
        with p1, p2, p3:
            result = await report_entries(_client())

        by_id = {e.record.bead_id: e for e in result}
        assert by_id["dea-pending"].pending_reconcile is True
        assert by_id["dea-stable"].pending_reconcile is False

    @pytest.mark.asyncio
    async def test_legacy_beads_are_never_pending_reconcile(self) -> None:
        entries = {"legacy-1": _legacy_entry("legacy-1", bd_status="open")}
        p1, p2, p3 = _patched(entries)
        with p1, p2, p3:
            result = await report_entries(_client())

        assert result[0].pending_reconcile is False
