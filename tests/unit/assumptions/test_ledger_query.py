"""Tests for open_blocking_entries / open_high_entries_before."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from maverick.assumptions.ledger import open_blocking_entries, open_high_entries_before
from maverick.assumptions.models import (
    ASSUMPTION_LABEL,
    ASSUMPTION_REVIEW_LABEL,
    KEY_OWNER_SPEC,
    KEY_SEVERITY,
    KEY_STATUS,
    NEEDS_HUMAN_REVIEW_LABEL,
    STATUS_ANSWERED,
    STATUS_OPEN,
    Severity,
)
from maverick.beads.client import BeadClient
from maverick.beads.models import BeadDetails, BeadSummary


def _client() -> BeadClient:
    return BeadClient(cwd=Path("/tmp/repo"))


def _summary(bead_id: str, status: str = "open") -> BeadSummary:
    return BeadSummary(id=bead_id, title=bead_id, status=status, bead_type="task")


def _entry(
    bead_id: str, severity: str, status: str = STATUS_OPEN, owner_spec: str = ""
) -> BeadDetails:
    return BeadDetails(
        id=bead_id,
        title=f"Assumption: {bead_id}",
        description="## Question\n\nQ?\n\n",
        bead_type="task",
        status="closed" if status != STATUS_OPEN else "open",
        labels=[ASSUMPTION_LABEL, ASSUMPTION_REVIEW_LABEL, NEEDS_HUMAN_REVIEW_LABEL],
        state={KEY_SEVERITY: severity, KEY_STATUS: status, KEY_OWNER_SPEC: owner_spec},
    )


def _legacy_entry(bead_id: str) -> BeadDetails:
    return BeadDetails(
        id=bead_id,
        title="Review: legacy",
        description="legacy escalation",
        bead_type="task",
        status="open",
        labels=[ASSUMPTION_REVIEW_LABEL, NEEDS_HUMAN_REVIEW_LABEL],
        state={"source_bead": "b-1", "flight_plan": "legacy-plan"},
    )


class TestOpenBlockingEntries:
    @pytest.mark.asyncio
    async def test_includes_open_medium_and_high_excludes_low(self) -> None:
        client = _client()
        entries = {
            "dea-low": _entry("dea-low", "low"),
            "dea-med": _entry("dea-med", "medium"),
            "dea-high": _entry("dea-high", "high"),
        }

        async def fake_query(self: BeadClient, filter_expr: str) -> list[BeadSummary]:
            return [_summary(k) for k in entries]

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            return entries[bead_id]

        with (
            patch.object(BeadClient, "query", new=fake_query),
            patch.object(BeadClient, "show", new=fake_show),
        ):
            result = await open_blocking_entries(client)

        ids = {r.bead_id for r in result}
        assert ids == {"dea-med", "dea-high"}

    @pytest.mark.asyncio
    async def test_excludes_answered_and_waived(self) -> None:
        client = _client()
        entries = {
            "dea-open": _entry("dea-open", "medium", status=STATUS_OPEN),
            "dea-answered": _entry("dea-answered", "medium", status=STATUS_ANSWERED),
        }

        async def fake_query(self: BeadClient, filter_expr: str) -> list[BeadSummary]:
            return [_summary(k) for k in entries]

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            return entries[bead_id]

        with (
            patch.object(BeadClient, "query", new=fake_query),
            patch.object(BeadClient, "show", new=fake_show),
        ):
            result = await open_blocking_entries(client)

        ids = {r.bead_id for r in result}
        assert ids == {"dea-open"}

    @pytest.mark.asyncio
    async def test_legacy_escalation_bead_surfaced_as_medium(self) -> None:
        client = _client()

        async def fake_query(self: BeadClient, filter_expr: str) -> list[BeadSummary]:
            return [_summary("legacy-1")]

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            return _legacy_entry("legacy-1")

        with (
            patch.object(BeadClient, "query", new=fake_query),
            patch.object(BeadClient, "show", new=fake_show),
        ):
            result = await open_blocking_entries(client)

        assert len(result) == 1
        assert result[0].severity == Severity.MEDIUM
        assert result[0].is_legacy is True


class TestOpenHighEntriesBefore:
    @pytest.mark.asyncio
    async def test_only_high_entries_owned_by_earlier_specs(self) -> None:
        client = _client()
        entries = {
            "dea-earlier-high": _entry("dea-earlier-high", "high", owner_spec="048-earlier-spec"),
            "dea-earlier-med": _entry("dea-earlier-med", "medium", owner_spec="048-earlier-spec"),
            "dea-later-high": _entry("dea-later-high", "high", owner_spec="050-later-spec"),
        }

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            if bead_id == "epic-1":
                return BeadDetails(
                    id="epic-1",
                    title="Epic",
                    bead_type="epic",
                    status="open",
                    state={"speckit_feature": "049-assumption-ledger"},
                )
            return entries[bead_id]

        async def fake_query(self: BeadClient, filter_expr: str) -> list[BeadSummary]:
            return [_summary(k) for k in entries]

        with (
            patch.object(BeadClient, "show", new=fake_show),
            patch.object(BeadClient, "query", new=fake_query),
        ):
            result = await open_high_entries_before(client, epic_id="epic-1")

        ids = {r.bead_id for r in result}
        assert ids == {"dea-earlier-high"}

    @pytest.mark.asyncio
    async def test_flight_plan_epic_returns_empty(self) -> None:
        client = _client()

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            return BeadDetails(
                id="epic-1",
                title="Epic",
                bead_type="epic",
                status="open",
                state={"flight_plan_name": "my-plan"},
            )

        with patch.object(BeadClient, "show", new=fake_show):
            result = await open_high_entries_before(client, epic_id="epic-1")

        assert result == ()
