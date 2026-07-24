"""Tests for `maverick.library.actions.beads.adopt_remediation_bead` (R6
adoption primitive fallback — no `bd update --parent` exists)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from maverick.beads.client import BeadClient
from maverick.beads.models import DependencyType
from maverick.library.actions.beads import adopt_remediation_bead
from maverick.workflows.spec_chain.constants import KEY_ADOPTED_BY_EPIC


def _client() -> BeadClient:
    return BeadClient(cwd=Path("/tmp/repo"))


class TestAdoptRemediationBead:
    @pytest.mark.asyncio
    async def test_wires_discovered_from_edge_epic_to_bead(self) -> None:
        client = _client()
        with (
            patch.object(BeadClient, "add_dependency", new=AsyncMock()) as mock_add_dep,
            patch.object(BeadClient, "set_state", new=AsyncMock()),
        ):
            await adopt_remediation_bead(client, bead_id="dea-1", epic_id="epic-1")

        dep = mock_add_dep.await_args.args[0]
        assert dep.blocker_id == "epic-1"
        assert dep.blocked_id == "dea-1"
        assert dep.dep_type == DependencyType.DISCOVERED_FROM

    @pytest.mark.asyncio
    async def test_stamps_adopted_by_epic_state(self) -> None:
        client = _client()
        with (
            patch.object(BeadClient, "add_dependency", new=AsyncMock()),
            patch.object(BeadClient, "set_state", new=AsyncMock()) as mock_set_state,
        ):
            await adopt_remediation_bead(client, bead_id="dea-1", epic_id="epic-1")

        bead_id_arg = mock_set_state.await_args.args[0]
        state_dict = mock_set_state.await_args.args[1]
        assert bead_id_arg == "dea-1"
        assert state_dict[KEY_ADOPTED_BY_EPIC] == "epic-1"

    @pytest.mark.asyncio
    async def test_dependency_failure_propagates(self) -> None:
        client = _client()
        with patch.object(
            BeadClient, "add_dependency", new=AsyncMock(side_effect=RuntimeError("boom"))
        ):
            with pytest.raises(RuntimeError):
                await adopt_remediation_bead(client, bead_id="dea-1", epic_id="epic-1")

    @pytest.mark.asyncio
    async def test_set_state_failure_propagates(self) -> None:
        client = _client()
        with (
            patch.object(BeadClient, "add_dependency", new=AsyncMock()),
            patch.object(BeadClient, "set_state", new=AsyncMock(side_effect=RuntimeError("boom"))),
        ):
            with pytest.raises(RuntimeError):
                await adopt_remediation_bead(client, bead_id="dea-1", epic_id="epic-1")
