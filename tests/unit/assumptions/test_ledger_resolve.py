"""Tests for maverick.assumptions.ledger.answer / waive."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from maverick.assumptions.errors import AssumptionLedgerError
from maverick.assumptions.ledger import answer, waive
from maverick.assumptions.models import (
    KEY_ANSWER,
    KEY_STATUS,
    KEY_WAIVE_REASON,
    KEY_WAIVED_AT,
    KEY_WAIVED_BY,
    STATUS_ANSWERED,
    STATUS_WAIVED,
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
