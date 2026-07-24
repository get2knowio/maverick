"""Tests for maverick.assumptions.ledger.record_assumption."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from maverick.assumptions.errors import AssumptionLedgerError
from maverick.assumptions.ledger import record_assumption
from maverick.assumptions.models import (
    ASSUMPTION_LABEL,
    KEY_OWNER_SPEC,
    KEY_SEVERITY,
    KEY_SEVERITY_DEFAULTED,
    KEY_SOURCE_BEAD,
    KEY_STATUS,
    STATUS_OPEN,
    Severity,
)
from maverick.beads.client import BeadClient
from maverick.beads.models import BeadDetails
from maverick.payloads import AssumptionPayload


def _client() -> BeadClient:
    return BeadClient(cwd=Path("/tmp/repo"))


def _epic_details(**state: str) -> BeadDetails:
    return BeadDetails(
        id="epic-1",
        title="Epic",
        bead_type="epic",
        status="open",
        labels=[],
        state=state,
    )


class TestOwnerSpecDerivation:
    @pytest.mark.asyncio
    async def test_speckit_feature_wins(self) -> None:
        client = _client()
        payload = AssumptionPayload(question="Q?", adopted_answer="A.")

        show_calls: list[str] = []

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            show_calls.append(bead_id)
            return _epic_details(
                speckit_feature="049-assumption-ledger", flight_plan_name="ignored"
            )

        async def fake_children(self: BeadClient, parent_id: str) -> list:
            return []

        created = type("CreatedBead", (), {"bd_id": "dea-1"})()

        with (
            patch.object(BeadClient, "show", new=fake_show),
            patch.object(BeadClient, "children", new=fake_children),
            patch.object(BeadClient, "create_bead", new=AsyncMock(return_value=created)),
            patch.object(BeadClient, "set_state", new=AsyncMock()) as mock_set_state,
            patch.object(BeadClient, "add_dependency", new=AsyncMock()) as mock_add_dep,
        ):
            record = await record_assumption(
                client, payload=payload, source_bead_id="src-1", epic_id="epic-1"
            )

        assert record is not None
        assert record.owner_spec == "049-assumption-ledger"
        set_state_kwargs = mock_set_state.await_args
        state_dict = set_state_kwargs.args[1]
        assert state_dict[KEY_OWNER_SPEC] == "049-assumption-ledger"
        mock_add_dep.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_flight_plan_name_fallback(self) -> None:
        client = _client()
        payload = AssumptionPayload(question="Q?", adopted_answer="A.")

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            return _epic_details(flight_plan_name="my-flight-plan")

        async def fake_children(self: BeadClient, parent_id: str) -> list:
            return []

        created = type("CreatedBead", (), {"bd_id": "dea-1"})()

        with (
            patch.object(BeadClient, "show", new=fake_show),
            patch.object(BeadClient, "children", new=fake_children),
            patch.object(BeadClient, "create_bead", new=AsyncMock(return_value=created)),
            patch.object(BeadClient, "set_state", new=AsyncMock()),
            patch.object(BeadClient, "add_dependency", new=AsyncMock()),
        ):
            record = await record_assumption(
                client, payload=payload, source_bead_id="src-1", epic_id="epic-1"
            )

        assert record is not None
        assert record.owner_spec == "my-flight-plan"

    @pytest.mark.asyncio
    async def test_epic_id_fallback_when_neither_key_present(self) -> None:
        client = _client()
        payload = AssumptionPayload(question="Q?", adopted_answer="A.")

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            return _epic_details()

        async def fake_children(self: BeadClient, parent_id: str) -> list:
            return []

        created = type("CreatedBead", (), {"bd_id": "dea-1"})()

        with (
            patch.object(BeadClient, "show", new=fake_show),
            patch.object(BeadClient, "children", new=fake_children),
            patch.object(BeadClient, "create_bead", new=AsyncMock(return_value=created)),
            patch.object(BeadClient, "set_state", new=AsyncMock()),
            patch.object(BeadClient, "add_dependency", new=AsyncMock()),
        ):
            record = await record_assumption(
                client, payload=payload, source_bead_id="src-1", epic_id="epic-1"
            )

        assert record is not None
        assert record.owner_spec == "epic-1"


class TestBeadShape:
    @pytest.mark.asyncio
    async def test_title_priority_assignee_parent(self) -> None:
        client = _client()
        payload = AssumptionPayload(
            question="Should retries be per bead?",
            adopted_answer="Per bead.",
            severity="high",
        )

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            return _epic_details(speckit_feature="049-assumption-ledger")

        async def fake_children(self: BeadClient, parent_id: str) -> list:
            return []

        created = type("CreatedBead", (), {"bd_id": "dea-1"})()
        create_bead_mock = AsyncMock(return_value=created)

        with (
            patch.object(BeadClient, "show", new=fake_show),
            patch.object(BeadClient, "children", new=fake_children),
            patch.object(BeadClient, "create_bead", new=create_bead_mock),
            patch.object(BeadClient, "set_state", new=AsyncMock()) as mock_set_state,
            patch.object(BeadClient, "add_dependency", new=AsyncMock()),
            patch.object(BeadClient, "query", new=AsyncMock(return_value=[])),
        ):
            record = await record_assumption(
                client, payload=payload, source_bead_id="src-1", epic_id="epic-1"
            )

        assert record is not None
        definition = create_bead_mock.await_args.args[0]
        parent_id = create_bead_mock.await_args.kwargs.get("parent_id")
        assert definition.title.startswith("Assumption:")
        assert "Should retries be per bead?" in definition.title
        assert definition.priority == 1  # high -> 1
        assert definition.assignee == "human"
        assert ASSUMPTION_LABEL in definition.labels
        assert "assumption-review" in definition.labels
        assert "needs-human-review" in definition.labels
        assert parent_id == "epic-1"

        state_dict = mock_set_state.await_args.args[1]
        assert state_dict[KEY_SEVERITY] == Severity.HIGH.value
        assert state_dict[KEY_STATUS] == STATUS_OPEN
        assert state_dict[KEY_SOURCE_BEAD] == "src-1"
        assert KEY_SEVERITY_DEFAULTED not in state_dict

    @pytest.mark.asyncio
    async def test_severity_defaulted_flag_persisted(self) -> None:
        client = _client()
        payload = AssumptionPayload(question="Q?", adopted_answer="A.", severity="bogus")

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            return _epic_details(speckit_feature="049-assumption-ledger")

        async def fake_children(self: BeadClient, parent_id: str) -> list:
            return []

        created = type("CreatedBead", (), {"bd_id": "dea-1"})()

        with (
            patch.object(BeadClient, "show", new=fake_show),
            patch.object(BeadClient, "children", new=fake_children),
            patch.object(BeadClient, "create_bead", new=AsyncMock(return_value=created)),
            patch.object(BeadClient, "set_state", new=AsyncMock()) as mock_set_state,
            patch.object(BeadClient, "add_dependency", new=AsyncMock()),
        ):
            record = await record_assumption(
                client, payload=payload, source_bead_id="src-1", epic_id="epic-1"
            )

        assert record is not None
        assert record.severity_defaulted is True
        state_dict = mock_set_state.await_args.args[1]
        assert state_dict[KEY_SEVERITY_DEFAULTED] == "true"


class TestDiscoveredFromEdge:
    @pytest.mark.asyncio
    async def test_wires_edge_from_source_to_new_entry(self) -> None:
        client = _client()
        payload = AssumptionPayload(question="Q?", adopted_answer="A.")

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            return _epic_details(speckit_feature="049-assumption-ledger")

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

        dep = mock_add_dep.await_args.args[0]
        assert dep.blocker_id == "src-1"
        assert dep.blocked_id == "dea-1"


class TestDedup:
    @pytest.mark.asyncio
    async def test_existing_open_entry_with_same_question_appends_edge_only(self) -> None:
        client = _client()
        payload = AssumptionPayload(
            question="  Should retries be   per bead?  ", adopted_answer="A."
        )

        existing_entry = BeadDetails(
            id="dea-existing",
            title="Assumption: Should retries be per bead?",
            description=(
                "## Question\n\nShould retries be per bead?\n\n"
                "## Adopted Answer\n\nPer bead.\n\n"
                "## Alternatives Considered\n\n(none)\n\n"
                "## Context\n\nSource bead: other-src — Other\n"
            ),
            bead_type="task",
            status="open",
            labels=[ASSUMPTION_LABEL, "assumption-review", "needs-human-review"],
            state={
                KEY_SEVERITY: "medium",
                KEY_STATUS: STATUS_OPEN,
                KEY_OWNER_SPEC: "049-assumption-ledger",
                KEY_SOURCE_BEAD: "other-src",
            },
        )

        from maverick.beads.models import BeadSummary

        async def fake_children(self: BeadClient, parent_id: str) -> list[BeadSummary]:
            return [
                BeadSummary(
                    id="dea-existing",
                    title=existing_entry.title,
                    status="open",
                    bead_type="task",
                )
            ]

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            if bead_id == "epic-1":
                return _epic_details(speckit_feature="049-assumption-ledger")
            return existing_entry

        create_bead_mock = AsyncMock()

        with (
            patch.object(BeadClient, "show", new=fake_show),
            patch.object(BeadClient, "children", new=fake_children),
            patch.object(BeadClient, "create_bead", new=create_bead_mock),
            patch.object(BeadClient, "set_state", new=AsyncMock()),
            patch.object(BeadClient, "add_dependency", new=AsyncMock()) as mock_add_dep,
        ):
            record = await record_assumption(
                client, payload=payload, source_bead_id="new-src", epic_id="epic-1"
            )

        create_bead_mock.assert_not_awaited()
        assert record is not None
        assert record.bead_id == "dea-existing"
        dep = mock_add_dep.await_args.args[0]
        assert dep.blocker_id == "new-src"
        assert dep.blocked_id == "dea-existing"


class TestEmptyEpicResolution:
    """``maverick fly`` without ``--epic`` passes ``epic_id=''``; the entry
    must still be recorded under the source bead's real owning epic rather
    than dropped by a ``bd show ''``."""

    @pytest.mark.asyncio
    async def test_empty_epic_resolves_source_bead_parent(self) -> None:
        client = _client()
        payload = AssumptionPayload(question="Q?", adopted_answer="A.")

        source = BeadDetails(
            id="src-1",
            title="Implement thing",
            bead_type="task",
            status="open",
            parent_id="epic-parent",
        )
        epic = BeadDetails(
            id="epic-parent",
            title="Epic",
            bead_type="epic",
            status="open",
            state={"speckit_feature": "049-assumption-ledger"},
        )

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            if bead_id == "src-1":
                return source
            if bead_id == "epic-parent":
                return epic
            raise LookupError(bead_id)

        async def fake_children(self: BeadClient, parent_id: str) -> list:
            assert parent_id == "epic-parent"
            return []

        created = type("CreatedBead", (), {"bd_id": "dea-1"})()
        create_bead_mock = AsyncMock(return_value=created)

        with (
            patch.object(BeadClient, "show", new=fake_show),
            patch.object(BeadClient, "children", new=fake_children),
            patch.object(BeadClient, "create_bead", new=create_bead_mock),
            patch.object(BeadClient, "set_state", new=AsyncMock()),
            patch.object(BeadClient, "add_dependency", new=AsyncMock()),
        ):
            record = await record_assumption(
                client, payload=payload, source_bead_id="src-1", epic_id=""
            )

        assert record is not None
        assert record.owner_spec == "049-assumption-ledger"
        assert create_bead_mock.await_args.kwargs.get("parent_id") == "epic-parent"

    @pytest.mark.asyncio
    async def test_empty_epic_no_parent_records_unparented(self) -> None:
        client = _client()
        payload = AssumptionPayload(question="Q?", adopted_answer="A.")

        source = BeadDetails(
            id="src-1", title="t", bead_type="task", status="open", parent_id=None
        )

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            return source

        created = type("CreatedBead", (), {"bd_id": "dea-1"})()
        create_bead_mock = AsyncMock(return_value=created)

        with (
            patch.object(BeadClient, "show", new=fake_show),
            patch.object(BeadClient, "create_bead", new=create_bead_mock),
            patch.object(BeadClient, "set_state", new=AsyncMock()),
            patch.object(BeadClient, "add_dependency", new=AsyncMock()),
        ):
            record = await record_assumption(
                client, payload=payload, source_bead_id="src-1", epic_id=""
            )

        assert record is not None
        # No resolvable epic → recorded unparented rather than dropped.
        assert create_bead_mock.await_args.kwargs.get("parent_id") is None


class TestErrors:
    @pytest.mark.asyncio
    async def test_bd_failure_raises_assumption_ledger_error(self) -> None:
        client = _client()
        payload = AssumptionPayload(question="Q?", adopted_answer="A.")

        from maverick.exceptions.beads import BeadQueryError

        async def failing_show(self: BeadClient, bead_id: str) -> BeadDetails:
            raise BeadQueryError("boom")

        with patch.object(BeadClient, "show", new=failing_show):
            with pytest.raises(AssumptionLedgerError):
                await record_assumption(
                    client, payload=payload, source_bead_id="src-1", epic_id="epic-1"
                )
