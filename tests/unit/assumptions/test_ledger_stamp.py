"""Tests for maverick.assumptions.ledger.stamp_change_id."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from maverick.assumptions.ledger import stamp_change_id
from maverick.assumptions.models import KEY_CHANGE_IDS
from maverick.beads.client import BeadClient
from maverick.beads.models import BeadDetails


def _client() -> BeadClient:
    return BeadClient(cwd=Path("/tmp/repo"))


def _details(bead_id: str, change_ids: str = "") -> BeadDetails:
    state = {KEY_CHANGE_IDS: change_ids} if change_ids else {}
    return BeadDetails(
        id=bead_id, title="Assumption", bead_type="task", status="open", state=state
    )


class TestStampChangeId:
    @pytest.mark.asyncio
    async def test_appends_to_comma_joined_state(self) -> None:
        client = _client()

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            return _details(bead_id, change_ids="abc123")

        with (
            patch.object(BeadClient, "show", new=fake_show),
            patch.object(BeadClient, "set_state", new=AsyncMock()) as mock_set_state,
        ):
            result = await stamp_change_id(client, entry_ids=["dea-1"], change_id="def456")

        assert result.stamped == ("dea-1",)
        assert result.failed == {}
        state_dict = mock_set_state.await_args.args[1]
        assert state_dict[KEY_CHANGE_IDS] == "abc123,def456"

    @pytest.mark.asyncio
    async def test_first_stamp_on_unstamped_entry(self) -> None:
        client = _client()

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            return _details(bead_id)

        with (
            patch.object(BeadClient, "show", new=fake_show),
            patch.object(BeadClient, "set_state", new=AsyncMock()) as mock_set_state,
        ):
            result = await stamp_change_id(client, entry_ids=["dea-1"], change_id="abc123")

        assert result.stamped == ("dea-1",)
        state_dict = mock_set_state.await_args.args[1]
        assert state_dict[KEY_CHANGE_IDS] == "abc123"

    @pytest.mark.asyncio
    async def test_idempotent_per_entry_and_change_id(self) -> None:
        client = _client()

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            return _details(bead_id, change_ids="abc123")

        with (
            patch.object(BeadClient, "show", new=fake_show),
            patch.object(BeadClient, "set_state", new=AsyncMock()) as mock_set_state,
        ):
            result = await stamp_change_id(client, entry_ids=["dea-1"], change_id="abc123")

        assert result.stamped == ("dea-1",)
        mock_set_state.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_partial_failure_reported_never_raises(self) -> None:
        client = _client()

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            if bead_id == "dea-bad":
                raise RuntimeError("bd show failed")
            return _details(bead_id)

        with (
            patch.object(BeadClient, "show", new=fake_show),
            patch.object(BeadClient, "set_state", new=AsyncMock()),
        ):
            result = await stamp_change_id(
                client, entry_ids=["dea-1", "dea-bad"], change_id="abc123"
            )

        assert result.stamped == ("dea-1",)
        assert "dea-bad" in result.failed

    @pytest.mark.asyncio
    async def test_multiple_entries_all_stamped(self) -> None:
        client = _client()

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            return _details(bead_id)

        with (
            patch.object(BeadClient, "show", new=fake_show),
            patch.object(BeadClient, "set_state", new=AsyncMock()),
        ):
            result = await stamp_change_id(
                client, entry_ids=["dea-1", "dea-2"], change_id="abc123"
            )

        assert set(result.stamped) == {"dea-1", "dea-2"}
        assert result.change_id == "abc123"
