"""Tests for severity policy hooks in record_assumption (US2)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from maverick.assumptions.ledger import record_assumption
from maverick.assumptions.models import (
    ASSUMPTION_LABEL,
    KEY_OWNER_SPEC,
    KEY_SEVERITY,
    KEY_STATUS,
    STATUS_OPEN,
    Severity,
)
from maverick.beads.client import BeadClient
from maverick.beads.models import BeadDetails, BeadSummary, DependencyType
from maverick.payloads import AssumptionPayload


def _client() -> BeadClient:
    return BeadClient(cwd=Path("/tmp/repo"))


def _epic_details(bead_id: str = "epic-1", **state: str) -> BeadDetails:
    return BeadDetails(id=bead_id, title="Epic", bead_type="epic", status="open", state=state)


def _base_mocks(epic_state: dict[str, str]):
    async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
        if bead_id == "epic-1":
            return _epic_details(**epic_state)
        return _epic_details(bead_id)

    async def fake_children(self: BeadClient, parent_id: str) -> list:
        return []

    return fake_show, fake_children


class TestLowSeverityDeferred:
    @pytest.mark.asyncio
    async def test_low_entry_deferred_at_creation(self) -> None:
        client = _client()
        payload = AssumptionPayload(question="Q?", adopted_answer="A.", severity="low")

        fake_show, fake_children = _base_mocks({"speckit_feature": "049-assumption-ledger"})
        created = type("CreatedBead", (), {"bd_id": "dea-1"})()

        with (
            patch.object(BeadClient, "show", new=fake_show),
            patch.object(BeadClient, "children", new=fake_children),
            patch.object(BeadClient, "create_bead", new=AsyncMock(return_value=created)),
            patch.object(BeadClient, "set_state", new=AsyncMock()),
            patch.object(BeadClient, "add_dependency", new=AsyncMock()),
            patch("maverick.library.actions.beads.defer_bead", new=AsyncMock()) as mock_defer,
        ):
            record = await record_assumption(
                client, payload=payload, source_bead_id="src-1", epic_id="epic-1"
            )

        assert record is not None
        mock_defer.assert_awaited_once()
        assert mock_defer.await_args.args[0] == "dea-1"


class TestMediumSeverityNeither:
    @pytest.mark.asyncio
    async def test_medium_entry_not_deferred_no_blocks_edge(self) -> None:
        client = _client()
        payload = AssumptionPayload(question="Q?", adopted_answer="A.", severity="medium")

        fake_show, fake_children = _base_mocks({"speckit_feature": "049-assumption-ledger"})
        created = type("CreatedBead", (), {"bd_id": "dea-1"})()

        with (
            patch.object(BeadClient, "show", new=fake_show),
            patch.object(BeadClient, "children", new=fake_children),
            patch.object(BeadClient, "create_bead", new=AsyncMock(return_value=created)),
            patch.object(BeadClient, "set_state", new=AsyncMock()),
            patch.object(BeadClient, "add_dependency", new=AsyncMock()) as mock_add_dep,
            patch("maverick.library.actions.beads.defer_bead", new=AsyncMock()) as mock_defer,
        ):
            await record_assumption(
                client, payload=payload, source_bead_id="src-1", epic_id="epic-1"
            )

        mock_defer.assert_not_awaited()
        # Only the discovered-from edge was wired, no blocks edge.
        assert mock_add_dep.await_count == 1


class TestHighSeverityBlocksEdge:
    @pytest.mark.asyncio
    async def test_high_entry_wires_blocks_edge_onto_next_epic(self) -> None:
        client = _client()
        payload = AssumptionPayload(question="Q?", adopted_answer="A.", severity="high")

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            if bead_id == "epic-1":
                return _epic_details("epic-1", speckit_feature="049-assumption-ledger")
            if bead_id == "epic-2":
                return _epic_details("epic-2", speckit_feature="050-next-spec")
            return _epic_details(bead_id)

        async def fake_children(self: BeadClient, parent_id: str) -> list:
            return []

        async def fake_query(self: BeadClient, filter_expr: str) -> list[BeadSummary]:
            return [
                BeadSummary(id="epic-1", title="Epic 1", status="open", bead_type="epic"),
                BeadSummary(id="epic-2", title="Epic 2", status="open", bead_type="epic"),
            ]

        created = type("CreatedBead", (), {"bd_id": "dea-1"})()

        with (
            patch.object(BeadClient, "show", new=fake_show),
            patch.object(BeadClient, "children", new=fake_children),
            patch.object(BeadClient, "query", new=fake_query),
            patch.object(BeadClient, "create_bead", new=AsyncMock(return_value=created)),
            patch.object(BeadClient, "set_state", new=AsyncMock()),
            patch.object(BeadClient, "add_dependency", new=AsyncMock()) as mock_add_dep,
        ):
            await record_assumption(
                client, payload=payload, source_bead_id="src-1", epic_id="epic-1"
            )

        # discovered-from + blocks edge
        assert mock_add_dep.await_count == 2
        from maverick.beads.models import DependencyType

        blocks_calls = [
            c for c in mock_add_dep.await_args_list if c.args[0].dep_type == DependencyType.BLOCKS
        ]
        assert len(blocks_calls) == 1
        dep = blocks_calls[0].args[0]
        assert dep.blocker_id == "dea-1"
        assert dep.blocked_id == "epic-2"

    @pytest.mark.asyncio
    async def test_high_entry_no_next_epic_no_blocks_edge(self) -> None:
        client = _client()
        payload = AssumptionPayload(question="Q?", adopted_answer="A.", severity="high")

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            if bead_id == "epic-1":
                return _epic_details("epic-1", speckit_feature="049-assumption-ledger")
            return _epic_details(bead_id)

        async def fake_children(self: BeadClient, parent_id: str) -> list:
            return []

        async def fake_query(self: BeadClient, filter_expr: str) -> list[BeadSummary]:
            return [BeadSummary(id="epic-1", title="Epic 1", status="open", bead_type="epic")]

        created = type("CreatedBead", (), {"bd_id": "dea-1"})()

        with (
            patch.object(BeadClient, "show", new=fake_show),
            patch.object(BeadClient, "children", new=fake_children),
            patch.object(BeadClient, "query", new=fake_query),
            patch.object(BeadClient, "create_bead", new=AsyncMock(return_value=created)),
            patch.object(BeadClient, "set_state", new=AsyncMock()),
            patch.object(BeadClient, "add_dependency", new=AsyncMock()) as mock_add_dep,
        ):
            await record_assumption(
                client, payload=payload, source_bead_id="src-1", epic_id="epic-1"
            )

        # Only discovered-from edge — no next epic exists.
        assert mock_add_dep.await_count == 1

    @pytest.mark.asyncio
    async def test_high_entry_flight_plan_epic_no_blocks_edge(self) -> None:
        """Owning epic has no speckit_feature -> next_chained_epic returns None."""
        client = _client()
        payload = AssumptionPayload(question="Q?", adopted_answer="A.", severity="high")

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            if bead_id == "epic-1":
                return _epic_details("epic-1", flight_plan_name="my-plan")
            return _epic_details(bead_id)

        async def fake_children(self: BeadClient, parent_id: str) -> list:
            return []

        created = type("CreatedBead", (), {"bd_id": "dea-1"})()

        with (
            patch.object(BeadClient, "show", new=fake_show),
            patch.object(BeadClient, "children", new=fake_children),
            patch.object(BeadClient, "create_bead", new=AsyncMock(return_value=created)),
            patch.object(BeadClient, "set_state", new=AsyncMock()),
            patch.object(BeadClient, "add_dependency", new=AsyncMock()) as mock_add_dep,
        ):
            await record_assumption(
                client, payload=payload, source_bead_id="src-1", epic_id="epic-1"
            )

        assert mock_add_dep.await_count == 1


def _existing_open_entry(severity: str) -> BeadDetails:
    return BeadDetails(
        id="dea-existing",
        title="Assumption: Should retries be per bead?",
        description=(
            "## Question\n\nShould retries be per bead?\n\n## Adopted Answer\n\nPer bead.\n\n"
        ),
        bead_type="task",
        status="open",
        labels=[ASSUMPTION_LABEL, "assumption-review", "needs-human-review"],
        state={
            KEY_SEVERITY: severity,
            KEY_STATUS: STATUS_OPEN,
            KEY_OWNER_SPEC: "049-earlier-spec",
        },
    )


class TestSeverityEscalationOnDedup:
    """A later bead re-reporting the same question at a higher severity must
    strengthen enforcement rather than inherit the weaker original."""

    @pytest.mark.asyncio
    async def test_medium_re_report_escalates_low_entry(self) -> None:
        client = _client()
        existing = _existing_open_entry("low")
        payload = AssumptionPayload(
            question="Should retries be per bead?", adopted_answer="A.", severity="medium"
        )

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            if bead_id == "epic-1":
                return _epic_details("epic-1", speckit_feature="049-earlier-spec")
            return existing

        async def fake_children(self: BeadClient, parent_id: str) -> list[BeadSummary]:
            return [
                BeadSummary(
                    id="dea-existing", title=existing.title, status="open", bead_type="task"
                )
            ]

        with (
            patch.object(BeadClient, "show", new=fake_show),
            patch.object(BeadClient, "children", new=fake_children),
            patch.object(BeadClient, "create_bead", new=AsyncMock()) as mock_create,
            patch.object(BeadClient, "set_state", new=AsyncMock()) as mock_set_state,
            patch.object(BeadClient, "add_dependency", new=AsyncMock()),
        ):
            record = await record_assumption(
                client, payload=payload, source_bead_id="new-src", epic_id="epic-1"
            )

        mock_create.assert_not_awaited()
        assert record is not None
        assert record.severity is Severity.MEDIUM
        # set_state was called to bump the stored severity.
        state_dict = mock_set_state.await_args.args[1]
        assert state_dict[KEY_SEVERITY] == Severity.MEDIUM.value

    @pytest.mark.asyncio
    async def test_high_re_report_escalates_and_wires_blocks_edge(self) -> None:
        client = _client()
        existing = _existing_open_entry("medium")
        payload = AssumptionPayload(
            question="Should retries be per bead?", adopted_answer="A.", severity="high"
        )

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            if bead_id == "epic-1":
                return _epic_details("epic-1", speckit_feature="049-earlier-spec")
            if bead_id == "epic-2":
                return _epic_details("epic-2", speckit_feature="050-next-spec")
            return existing

        async def fake_children(self: BeadClient, parent_id: str) -> list[BeadSummary]:
            return [
                BeadSummary(
                    id="dea-existing", title=existing.title, status="open", bead_type="task"
                )
            ]

        async def fake_query(self: BeadClient, filter_expr: str) -> list[BeadSummary]:
            return [
                BeadSummary(id="epic-1", title="Epic 1", status="open", bead_type="epic"),
                BeadSummary(id="epic-2", title="Epic 2", status="open", bead_type="epic"),
            ]

        with (
            patch.object(BeadClient, "show", new=fake_show),
            patch.object(BeadClient, "children", new=fake_children),
            patch.object(BeadClient, "query", new=fake_query),
            patch.object(BeadClient, "create_bead", new=AsyncMock()) as mock_create,
            patch.object(BeadClient, "set_state", new=AsyncMock()) as mock_set_state,
            patch.object(BeadClient, "add_dependency", new=AsyncMock()) as mock_add_dep,
        ):
            record = await record_assumption(
                client, payload=payload, source_bead_id="new-src", epic_id="epic-1"
            )

        mock_create.assert_not_awaited()
        assert record is not None
        assert record.severity is Severity.HIGH
        state_dict = mock_set_state.await_args.args[1]
        assert state_dict[KEY_SEVERITY] == Severity.HIGH.value
        blocks = [
            c for c in mock_add_dep.await_args_list if c.args[0].dep_type == DependencyType.BLOCKS
        ]
        assert len(blocks) == 1
        assert blocks[0].args[0].blocker_id == "dea-existing"
        assert blocks[0].args[0].blocked_id == "epic-2"

    @pytest.mark.asyncio
    async def test_lower_re_report_does_not_downgrade(self) -> None:
        client = _client()
        existing = _existing_open_entry("high")
        payload = AssumptionPayload(
            question="Should retries be per bead?", adopted_answer="A.", severity="low"
        )

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            if bead_id == "epic-1":
                return _epic_details("epic-1", speckit_feature="049-earlier-spec")
            return existing

        async def fake_children(self: BeadClient, parent_id: str) -> list[BeadSummary]:
            return [
                BeadSummary(
                    id="dea-existing", title=existing.title, status="open", bead_type="task"
                )
            ]

        with (
            patch.object(BeadClient, "show", new=fake_show),
            patch.object(BeadClient, "children", new=fake_children),
            patch.object(BeadClient, "create_bead", new=AsyncMock()),
            patch.object(BeadClient, "set_state", new=AsyncMock()) as mock_set_state,
            patch.object(BeadClient, "add_dependency", new=AsyncMock()),
            patch("maverick.library.actions.beads.defer_bead", new=AsyncMock()),
        ):
            record = await record_assumption(
                client, payload=payload, source_bead_id="new-src", epic_id="epic-1"
            )

        assert record is not None
        assert record.severity is Severity.HIGH  # unchanged
        # No severity escalation → set_state not called for the existing entry.
        mock_set_state.assert_not_awaited()
