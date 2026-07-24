"""Tests for maverick.assumptions.ledger.record_standalone_assumption (R5)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from maverick.assumptions.errors import AssumptionLedgerError
from maverick.assumptions.ledger import record_standalone_assumption
from maverick.assumptions.models import (
    ASSUMPTION_LABEL,
    KEY_OWNER_SPEC,
    KEY_SEVERITY,
    KEY_SEVERITY_DEFAULTED,
    KEY_SOURCE_REF,
    KEY_STATUS,
    STATUS_OPEN,
    Severity,
)
from maverick.beads.client import BeadClient
from maverick.beads.models import BeadDetails, BeadSummary
from maverick.payloads import AssumptionPayload


def _client() -> BeadClient:
    return BeadClient(cwd=Path("/tmp/repo"))


class TestBeadShape:
    @pytest.mark.asyncio
    async def test_created_unparented_with_source_ref_state_key(self) -> None:
        client = _client()
        payload = AssumptionPayload(
            question="Should exports include archived widgets?",
            adopted_answer="No, exclude archived widgets.",
            severity="high",
        )
        created = type("CreatedBead", (), {"bd_id": "dea-1"})()
        create_bead_mock = AsyncMock(return_value=created)

        with (
            patch.object(BeadClient, "query", new=AsyncMock(return_value=[])),
            patch.object(BeadClient, "create_bead", new=create_bead_mock),
            patch.object(BeadClient, "set_state", new=AsyncMock()) as mock_set_state,
        ):
            record = await record_standalone_assumption(
                client,
                payload=payload,
                owner_spec="050-headless-spec-chain",
                source_ref="spec-chain:clarify",
            )

        assert record is not None
        assert record.bead_id == "dea-1"
        definition = create_bead_mock.await_args.args[0]
        parent_id = create_bead_mock.await_args.kwargs.get("parent_id")
        assert parent_id is None
        assert ASSUMPTION_LABEL in definition.labels
        assert "assumption-review" in definition.labels
        assert "needs-human-review" in definition.labels
        assert definition.assignee == "human"

        state_dict = mock_set_state.await_args.args[1]
        assert state_dict[KEY_SEVERITY] == Severity.HIGH.value
        assert state_dict[KEY_STATUS] == STATUS_OPEN
        assert state_dict[KEY_OWNER_SPEC] == "050-headless-spec-chain"
        assert state_dict[KEY_SOURCE_REF] == "spec-chain:clarify"
        assert "source_bead" not in state_dict

    @pytest.mark.asyncio
    async def test_severity_defaulted_flag_persisted(self) -> None:
        client = _client()
        payload = AssumptionPayload(question="Q?", adopted_answer="A.", severity="bogus")
        created = type("CreatedBead", (), {"bd_id": "dea-1"})()

        with (
            patch.object(BeadClient, "query", new=AsyncMock(return_value=[])),
            patch.object(BeadClient, "create_bead", new=AsyncMock(return_value=created)),
            patch.object(BeadClient, "set_state", new=AsyncMock()) as mock_set_state,
        ):
            record = await record_standalone_assumption(
                client,
                payload=payload,
                owner_spec="050-headless-spec-chain",
                source_ref="spec-chain:clarify",
            )

        assert record is not None
        assert record.severity_defaulted is True
        state_dict = mock_set_state.await_args.args[1]
        assert state_dict[KEY_SEVERITY_DEFAULTED] == "true"

    @pytest.mark.asyncio
    async def test_low_severity_is_deferred(self) -> None:
        client = _client()
        payload = AssumptionPayload(question="Q?", adopted_answer="A.", severity="low")
        created = type("CreatedBead", (), {"bd_id": "dea-1"})()

        with (
            patch.object(BeadClient, "query", new=AsyncMock(return_value=[])),
            patch.object(BeadClient, "create_bead", new=AsyncMock(return_value=created)),
            patch.object(BeadClient, "set_state", new=AsyncMock()),
            patch("maverick.library.actions.beads.defer_bead", new=AsyncMock()) as mock_defer,
        ):
            await record_standalone_assumption(
                client,
                payload=payload,
                owner_spec="050-headless-spec-chain",
                source_ref="spec-chain:clarify",
            )

        mock_defer.assert_awaited_once()
        assert mock_defer.await_args.args[0] == "dea-1"


class TestDedup:
    @pytest.mark.asyncio
    async def test_existing_open_entry_same_owner_spec_and_question_merges(self) -> None:
        client = _client()
        payload = AssumptionPayload(
            question="  Should exports include archived widgets?  ",
            adopted_answer="No.",
            severity="low",
        )

        existing_entry = BeadDetails(
            id="dea-existing",
            title="Assumption: Should exports include archived widgets?",
            description=(
                "## Question\n\nShould exports include archived widgets?\n\n"
                "## Adopted Answer\n\nNo.\n\n"
                "## Alternatives Considered\n\n(none)\n\n"
                "## Context\n\nSource bead: spec-chain:clarify — spec-chain:clarify\n"
            ),
            bead_type="task",
            status="open",
            labels=[ASSUMPTION_LABEL, "assumption-review", "needs-human-review"],
            state={
                KEY_SEVERITY: "medium",
                KEY_STATUS: STATUS_OPEN,
                KEY_OWNER_SPEC: "050-headless-spec-chain",
                KEY_SOURCE_REF: "spec-chain:clarify",
            },
        )

        async def fake_query(self: BeadClient, expr: str) -> list[BeadSummary]:
            return [
                BeadSummary(
                    id="dea-existing",
                    title=existing_entry.title,
                    status="open",
                    bead_type="task",
                )
            ]

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            return existing_entry

        create_bead_mock = AsyncMock()

        with (
            patch.object(BeadClient, "query", new=fake_query),
            patch.object(BeadClient, "show", new=fake_show),
            patch.object(BeadClient, "create_bead", new=create_bead_mock),
            patch.object(BeadClient, "set_state", new=AsyncMock()),
        ):
            record = await record_standalone_assumption(
                client,
                payload=payload,
                owner_spec="050-headless-spec-chain",
                source_ref="spec-chain:clarify",
            )

        create_bead_mock.assert_not_awaited()
        assert record is not None
        assert record.bead_id == "dea-existing"

    @pytest.mark.asyncio
    async def test_different_owner_spec_does_not_dedup(self) -> None:
        client = _client()
        payload = AssumptionPayload(question="Same question?", adopted_answer="A.")

        other_spec_entry = BeadDetails(
            id="dea-other",
            title="Assumption: Same question?",
            description=(
                "## Question\n\nSame question?\n\n"
                "## Adopted Answer\n\nOther answer.\n\n"
                "## Alternatives Considered\n\n(none)\n\n"
                "## Context\n\nSource bead: x — x\n"
            ),
            bead_type="task",
            status="open",
            labels=[ASSUMPTION_LABEL],
            state={
                KEY_SEVERITY: "low",
                KEY_STATUS: STATUS_OPEN,
                KEY_OWNER_SPEC: "051-other-feature",
            },
        )

        async def fake_query(self: BeadClient, expr: str) -> list[BeadSummary]:
            return [
                BeadSummary(
                    id="dea-other", title=other_spec_entry.title, status="open", bead_type="task"
                )
            ]

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            return other_spec_entry

        created = type("CreatedBead", (), {"bd_id": "dea-new"})()
        create_bead_mock = AsyncMock(return_value=created)

        with (
            patch.object(BeadClient, "query", new=fake_query),
            patch.object(BeadClient, "show", new=fake_show),
            patch.object(BeadClient, "create_bead", new=create_bead_mock),
            patch.object(BeadClient, "set_state", new=AsyncMock()),
        ):
            record = await record_standalone_assumption(
                client,
                payload=payload,
                owner_spec="050-headless-spec-chain",
                source_ref="spec-chain:clarify",
            )

        create_bead_mock.assert_awaited_once()
        assert record is not None
        assert record.bead_id == "dea-new"

    @pytest.mark.asyncio
    async def test_severity_escalation_on_merge(self) -> None:
        client = _client()
        payload = AssumptionPayload(
            question="Should exports include archived widgets?",
            adopted_answer="No.",
            severity="high",
        )

        existing_entry = BeadDetails(
            id="dea-existing",
            title="Assumption: Should exports include archived widgets?",
            description=(
                "## Question\n\nShould exports include archived widgets?\n\n"
                "## Adopted Answer\n\nNo.\n\n"
                "## Alternatives Considered\n\n(none)\n\n"
                "## Context\n\nSource bead: x — x\n"
            ),
            bead_type="task",
            status="open",
            labels=[ASSUMPTION_LABEL],
            state={
                KEY_SEVERITY: "low",
                KEY_STATUS: STATUS_OPEN,
                KEY_OWNER_SPEC: "050-headless-spec-chain",
            },
        )

        async def fake_query(self: BeadClient, expr: str) -> list[BeadSummary]:
            return [
                BeadSummary(
                    id="dea-existing", title=existing_entry.title, status="open", bead_type="task"
                )
            ]

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            return existing_entry

        with (
            patch.object(BeadClient, "query", new=fake_query),
            patch.object(BeadClient, "show", new=fake_show),
            patch.object(BeadClient, "create_bead", new=AsyncMock()),
            patch.object(BeadClient, "set_state", new=AsyncMock()) as mock_set_state,
        ):
            record = await record_standalone_assumption(
                client,
                payload=payload,
                owner_spec="050-headless-spec-chain",
                source_ref="spec-chain:clarify",
            )

        assert record is not None
        assert record.severity is Severity.HIGH
        state_dict = mock_set_state.await_args.args[1]
        assert state_dict[KEY_SEVERITY] == Severity.HIGH.value


class TestErrors:
    @pytest.mark.asyncio
    async def test_bd_failure_raises_assumption_ledger_error(self) -> None:
        client = _client()
        payload = AssumptionPayload(question="Q?", adopted_answer="A.")

        from maverick.exceptions.beads import BeadQueryError

        async def failing_query(self: BeadClient, expr: str) -> list:
            raise BeadQueryError("boom")

        with patch.object(BeadClient, "query", new=failing_query):
            with pytest.raises(AssumptionLedgerError):
                await record_standalone_assumption(
                    client,
                    payload=payload,
                    owner_spec="050-headless-spec-chain",
                    source_ref="spec-chain:clarify",
                )
