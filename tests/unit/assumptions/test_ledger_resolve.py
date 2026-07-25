"""Tests for maverick.assumptions.ledger.answer / waive / bulk_waive."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from maverick.assumptions.errors import AssumptionLedgerError
from maverick.assumptions.ledger import answer, bulk_waive, waive
from maverick.assumptions.models import (
    KEY_ANSWER,
    KEY_STATUS,
    KEY_WAIVE_REASON,
    KEY_WAIVED_AT,
    KEY_WAIVED_BY,
    STATUS_ANSWERED,
    STATUS_OPEN,
    STATUS_WAIVED,
    AssumptionRecord,
    AssumptionReportEntry,
    Severity,
)
from maverick.beads.client import BeadClient
from maverick.beads.models import BeadDetails, ClosedBead


def _client() -> BeadClient:
    return BeadClient(cwd=Path("/tmp/repo"))


def _details(status: str = "open", **state: str) -> BeadDetails:
    return BeadDetails(
        id="dea-1",
        title="Assumption: Q?",
        description="## Question\n\nQ?\n\n## Adopted Answer\n\nA.\n",
        bead_type="task",
        status=status,
        state=state,
    )


class TestAnswer:
    @pytest.mark.asyncio
    async def test_requires_non_empty_text(self) -> None:
        client = _client()
        with pytest.raises(AssumptionLedgerError):
            await answer(client, bead_id="dea-1", answer_text="")

    @pytest.mark.asyncio
    async def test_rejects_whitespace_only(self) -> None:
        client = _client()
        with pytest.raises(AssumptionLedgerError):
            await answer(client, bead_id="dea-1", answer_text="   ")

    @pytest.mark.asyncio
    async def test_sets_state_and_closes_bead(self) -> None:
        client = _client()

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            return _details(status="closed", **{KEY_STATUS: STATUS_ANSWERED, KEY_ANSWER: "Yes."})

        with (
            patch.object(BeadClient, "set_state", new=AsyncMock()) as mock_set_state,
            patch.object(
                BeadClient,
                "close",
                new=AsyncMock(return_value=ClosedBead(id="dea-1", status="closed")),
            ) as mock_close,
            patch.object(BeadClient, "show", new=fake_show),
        ):
            record = await answer(client, bead_id="dea-1", answer_text="Yes.")

        state_dict = mock_set_state.await_args.args[1]
        assert state_dict[KEY_ANSWER] == "Yes."
        assert state_dict[KEY_STATUS] == STATUS_ANSWERED
        mock_close.assert_awaited_once()
        assert record.status == STATUS_ANSWERED


class TestWaive:
    @pytest.mark.asyncio
    async def test_requires_non_empty_reason(self) -> None:
        client = _client()
        with pytest.raises(AssumptionLedgerError):
            await waive(client, bead_id="dea-1", reason="", waived_by="alice")

    @pytest.mark.asyncio
    async def test_records_who_when_why_and_closes(self) -> None:
        client = _client()

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            return _details(
                status="closed",
                **{
                    KEY_STATUS: STATUS_WAIVED,
                    KEY_WAIVED_BY: "alice",
                    KEY_WAIVE_REASON: "not applicable",
                },
            )

        with (
            patch.object(BeadClient, "set_state", new=AsyncMock()) as mock_set_state,
            patch.object(
                BeadClient,
                "close",
                new=AsyncMock(return_value=ClosedBead(id="dea-1", status="closed")),
            ) as mock_close,
            patch.object(BeadClient, "show", new=fake_show),
        ):
            record = await waive(
                client, bead_id="dea-1", reason="not applicable", waived_by="alice"
            )

        state_dict = mock_set_state.await_args.args[1]
        assert state_dict[KEY_WAIVED_BY] == "alice"
        assert state_dict[KEY_WAIVE_REASON] == "not applicable"
        assert KEY_WAIVED_AT in state_dict
        assert state_dict[KEY_STATUS] == STATUS_WAIVED
        mock_close.assert_awaited_once()
        assert record.status == STATUS_WAIVED


def _report_entry(
    bead_id: str,
    *,
    severity: Severity = Severity.LOW,
    status: str = STATUS_OPEN,
    owner_spec: str = "052-conditional-landing",
    is_legacy: bool = False,
) -> AssumptionReportEntry:
    record = AssumptionRecord(
        bead_id=bead_id,
        question=f"Q for {bead_id}?",
        adopted_answer="A.",
        alternatives=(),
        severity=severity,
        severity_defaulted=False,
        status=status,
        owner_spec=owner_spec,
        source_bead="dea-0",
        change_ids=(),
        is_legacy=is_legacy,
    )
    return AssumptionReportEntry(
        record=record,
        final_answer=None,
        waived_by=None,
        waived_at=None,
        waive_reason=None,
        reconcile_status=None,
        reconciled_answer=None,
        reconcile_change_id=None,
        reconcile_reason=None,
        pending_reconcile=False,
    )


def _waived_record(bead_id: str) -> AssumptionRecord:
    return AssumptionRecord(
        bead_id=bead_id,
        question="Q?",
        adopted_answer="A.",
        alternatives=(),
        severity=Severity.LOW,
        severity_defaulted=False,
        status=STATUS_WAIVED,
        owner_spec="052-conditional-landing",
        source_bead="dea-0",
        change_ids=(),
        is_legacy=False,
    )


class TestBulkWaive:
    @pytest.mark.asyncio
    async def test_defaults_to_low_severity_only(self) -> None:
        entries = (
            _report_entry("dea-low", severity=Severity.LOW),
            _report_entry("dea-med", severity=Severity.MEDIUM),
        )
        client = _client()
        with (
            patch(
                "maverick.assumptions.ledger.report_entries",
                new=AsyncMock(return_value=entries),
            ),
            patch(
                "maverick.assumptions.ledger.waive",
                new=AsyncMock(side_effect=lambda _c, *, bead_id, **_kw: _waived_record(bead_id)),
            ) as mock_waive,
        ):
            result = await bulk_waive(
                client,
                owner_spec="052-conditional-landing",
                severities=frozenset({Severity.LOW}),
                reason="accepted for MVP",
                waived_by="Paul",
            )

        mock_waive.assert_awaited_once()
        assert mock_waive.await_args.kwargs["bead_id"] == "dea-low"
        assert result.waived == (_waived_record("dea-low"),)
        assert result.failed == {}

    @pytest.mark.asyncio
    async def test_legacy_entry_included_only_when_medium_selected(self) -> None:
        entries = (
            _report_entry("dea-low", severity=Severity.LOW),
            _report_entry("legacy-1", severity=Severity.MEDIUM, is_legacy=True),
        )
        client = _client()
        with (
            patch(
                "maverick.assumptions.ledger.report_entries",
                new=AsyncMock(return_value=entries),
            ),
            patch(
                "maverick.assumptions.ledger.waive",
                new=AsyncMock(side_effect=lambda _c, *, bead_id, **_kw: _waived_record(bead_id)),
            ) as mock_waive,
        ):
            result = await bulk_waive(
                client,
                owner_spec="052-conditional-landing",
                severities=frozenset({Severity.MEDIUM}),
                reason="noise",
                waived_by="Paul",
            )

        assert mock_waive.await_args.kwargs["bead_id"] == "legacy-1"
        assert {r.bead_id for r in result.waived} == {"legacy-1"}

    @pytest.mark.asyncio
    async def test_selects_open_entries_only(self) -> None:
        entries = (
            _report_entry("dea-open", severity=Severity.LOW, status=STATUS_OPEN),
            _report_entry("dea-answered", severity=Severity.LOW, status=STATUS_ANSWERED),
            _report_entry("dea-waived-already", severity=Severity.LOW, status=STATUS_WAIVED),
        )
        client = _client()
        with (
            patch(
                "maverick.assumptions.ledger.report_entries",
                new=AsyncMock(return_value=entries),
            ),
            patch(
                "maverick.assumptions.ledger.waive",
                new=AsyncMock(side_effect=lambda _c, *, bead_id, **_kw: _waived_record(bead_id)),
            ) as mock_waive,
        ):
            result = await bulk_waive(
                client,
                owner_spec="052-conditional-landing",
                severities=frozenset({Severity.LOW}),
                reason="noise",
                waived_by="Paul",
            )

        mock_waive.assert_awaited_once()
        assert {r.bead_id for r in result.waived} == {"dea-open"}

    @pytest.mark.asyncio
    async def test_only_matches_given_owner_spec(self) -> None:
        entries = (
            _report_entry("dea-mine", severity=Severity.LOW, owner_spec="052-conditional-landing"),
            _report_entry("dea-other", severity=Severity.LOW, owner_spec="051-other-spec"),
        )
        client = _client()
        with (
            patch(
                "maverick.assumptions.ledger.report_entries",
                new=AsyncMock(return_value=entries),
            ),
            patch(
                "maverick.assumptions.ledger.waive",
                new=AsyncMock(side_effect=lambda _c, *, bead_id, **_kw: _waived_record(bead_id)),
            ),
        ):
            result = await bulk_waive(
                client,
                owner_spec="052-conditional-landing",
                severities=frozenset({Severity.LOW}),
                reason="noise",
                waived_by="Paul",
            )

        assert {r.bead_id for r in result.waived} == {"dea-mine"}

    @pytest.mark.asyncio
    async def test_per_entry_waiver_metadata_shared_reason_and_waiver(self) -> None:
        entries = (
            _report_entry("dea-1", severity=Severity.LOW),
            _report_entry("dea-2", severity=Severity.LOW),
        )
        client = _client()
        with (
            patch(
                "maverick.assumptions.ledger.report_entries",
                new=AsyncMock(return_value=entries),
            ),
            patch(
                "maverick.assumptions.ledger.waive",
                new=AsyncMock(side_effect=lambda _c, *, bead_id, **_kw: _waived_record(bead_id)),
            ) as mock_waive,
        ):
            await bulk_waive(
                client,
                owner_spec="052-conditional-landing",
                severities=frozenset({Severity.LOW}),
                reason="accepted for MVP",
                waived_by="Paul O'Fallon",
            )

        for call in mock_waive.await_args_list:
            assert call.kwargs["reason"] == "accepted for MVP"
            assert call.kwargs["waived_by"] == "Paul O'Fallon"

    @pytest.mark.asyncio
    async def test_zero_matches_returns_empty(self) -> None:
        client = _client()
        with (
            patch(
                "maverick.assumptions.ledger.report_entries",
                new=AsyncMock(return_value=()),
            ),
            patch("maverick.assumptions.ledger.waive", new=AsyncMock()) as mock_waive,
        ):
            result = await bulk_waive(
                client,
                owner_spec="052-conditional-landing",
                severities=frozenset({Severity.LOW}),
                reason="noise",
                waived_by="Paul",
            )

        assert result.waived == ()
        assert result.failed == {}
        mock_waive.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_partial_failure_aggregation(self) -> None:
        entries = (
            _report_entry("dea-ok", severity=Severity.LOW),
            _report_entry("dea-fails", severity=Severity.LOW),
        )
        client = _client()

        async def fake_waive(_c: BeadClient, *, bead_id: str, **_kw: str) -> AssumptionRecord:
            if bead_id == "dea-fails":
                raise AssumptionLedgerError("bd write failed")
            return _waived_record(bead_id)

        with (
            patch(
                "maverick.assumptions.ledger.report_entries",
                new=AsyncMock(return_value=entries),
            ),
            patch("maverick.assumptions.ledger.waive", new=fake_waive),
        ):
            result = await bulk_waive(
                client,
                owner_spec="052-conditional-landing",
                severities=frozenset({Severity.LOW}),
                reason="noise",
                waived_by="Paul",
            )

        assert {r.bead_id for r in result.waived} == {"dea-ok"}
        assert result.failed == {"dea-fails": "bd write failed"}
