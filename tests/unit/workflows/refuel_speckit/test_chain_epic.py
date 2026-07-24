"""Tests for SpeckitRefuelWorkflow._chain_epic — deterministic tail
selection by speckit_feature NNN prefix, and assumption blocks-edge
wiring (research R8 / T024).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from maverick.assumptions.models import (
    ASSUMPTION_LABEL,
    KEY_OWNER_SPEC,
    KEY_SEVERITY,
    KEY_STATUS,
    STATUS_OPEN,
)
from maverick.beads.models import BeadDependency, BeadDetails, BeadSummary, DependencyType
from maverick.workflows.refuel_speckit.workflow import SpeckitRefuelWorkflow
from tests.unit.workflows.refuel_speckit.conftest import make_mock_bead_client


def _epic_summary(bead_id: str) -> BeadSummary:
    return BeadSummary(id=bead_id, title=bead_id, status="open", priority=1, bead_type="epic")


def _epic_details(bead_id: str, speckit_feature: str = "") -> BeadDetails:
    state = {"speckit_feature": speckit_feature} if speckit_feature else {}
    return BeadDetails(id=bead_id, title=bead_id, bead_type="epic", state=state)


class TestDeterministicTailSelection:
    @pytest.mark.asyncio
    async def test_sorts_by_nnn_prefix_not_query_order(self) -> None:
        """Existing epics come back in an arbitrary bd order; the tail must
        still be the highest NNN prefix, not the last list element."""
        workflow = SpeckitRefuelWorkflow(config=MagicMock())
        client = make_mock_bead_client(
            existing_epics=[_epic_summary("epic-050"), _epic_summary("epic-010")],
            epic_details_by_id={
                "epic-050": _epic_details("epic-050", "050-later-spec"),
                "epic-010": _epic_details("epic-010", "010-earlier-spec"),
                "new-epic": _epic_details("new-epic", "051-new-spec"),
            },
        )

        tail = await workflow._chain_epic(client, "new-epic")

        assert tail == "epic-050"
        chain_calls = [
            c for c in client.add_dependency.call_args_list if c.args[0].blocked_id == "new-epic"
        ]
        blocks_only = [c for c in chain_calls if c.args[0].dep_type == DependencyType.BLOCKS]
        # One is the tail-chain edge (default BLOCKS dep_type).
        assert any(c.args[0].blocker_id == "epic-050" for c in blocks_only)

    @pytest.mark.asyncio
    async def test_unprefixed_epics_sort_after_prefixed(self) -> None:
        workflow = SpeckitRefuelWorkflow(config=MagicMock())
        client = make_mock_bead_client(
            existing_epics=[_epic_summary("flight-epic"), _epic_summary("epic-010")],
            epic_details_by_id={
                "flight-epic": _epic_details("flight-epic"),  # no speckit_feature
                "epic-010": _epic_details("epic-010", "010-spec"),
                "new-epic": _epic_details("new-epic", "011-new-spec"),
            },
        )

        tail = await workflow._chain_epic(client, "new-epic")

        assert tail == "flight-epic"

    @pytest.mark.asyncio
    async def test_no_existing_epics_returns_none_tail(self) -> None:
        workflow = SpeckitRefuelWorkflow(config=MagicMock())
        client = make_mock_bead_client(
            existing_epics=[],
            epic_details_by_id={"new-epic": _epic_details("new-epic", "001-new-spec")},
        )

        tail = await workflow._chain_epic(client, "new-epic")

        assert tail is None


class TestAssumptionBlocksEdgeWiring:
    @pytest.mark.asyncio
    async def test_wires_blocks_edge_from_open_high_entry_of_earlier_spec(self) -> None:
        workflow = SpeckitRefuelWorkflow(config=MagicMock())
        earlier_entry = BeadDetails(
            id="dea-1",
            title="Assumption: earlier",
            description="## Question\n\nQ?\n\n",
            bead_type="task",
            status="open",
            labels=[ASSUMPTION_LABEL],
            state={
                KEY_SEVERITY: "high",
                KEY_STATUS: STATUS_OPEN,
                KEY_OWNER_SPEC: "010-earlier-spec",
            },
        )
        client = make_mock_bead_client(
            existing_epics=[],
            epic_details_by_id={"new-epic": _epic_details("new-epic", "011-new-spec")},
        )

        async def _query(filter_expr: str) -> list[BeadSummary]:
            if filter_expr.startswith("type=task"):
                return [BeadSummary(id="dea-1", title="dea-1", status="open", bead_type="task")]
            return []

        client.query.side_effect = _query

        async def _show(bead_id: str) -> BeadDetails:
            if bead_id == "new-epic":
                return _epic_details("new-epic", "011-new-spec")
            if bead_id == "dea-1":
                return earlier_entry
            raise LookupError(bead_id)

        client.show.side_effect = _show

        await workflow._chain_epic(client, "new-epic")

        blocks_calls = [
            c
            for c in client.add_dependency.call_args_list
            if c.args[0].dep_type == DependencyType.BLOCKS and c.args[0].blocked_id == "new-epic"
        ]
        assert len(blocks_calls) == 1
        assert blocks_calls[0].args[0].blocker_id == "dea-1"

    @pytest.mark.asyncio
    async def test_no_open_high_entries_no_blocks_edge(self) -> None:
        workflow = SpeckitRefuelWorkflow(config=MagicMock())
        client = make_mock_bead_client(
            existing_epics=[],
            epic_details_by_id={"new-epic": _epic_details("new-epic", "011-new-spec")},
        )
        client.query.side_effect = lambda filter_expr: []

        await workflow._chain_epic(client, "new-epic")

        assert client.add_dependency.call_count == 0


class TestBeadDependencyDefaultType:
    def test_default_dep_type_is_blocks(self) -> None:
        dep = BeadDependency(blocker_id="a", blocked_id="b")
        assert dep.dep_type == DependencyType.BLOCKS
