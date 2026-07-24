"""Tests for maverick.assumptions.report.per_spec_counts."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from maverick.assumptions.models import (
    ASSUMPTION_LABEL,
    ASSUMPTION_REVIEW_LABEL,
    KEY_OWNER_SPEC,
    KEY_SEVERITY,
    KEY_STATUS,
    NEEDS_HUMAN_REVIEW_LABEL,
    STATUS_ANSWERED,
    STATUS_OPEN,
    STATUS_WAIVED,
    Severity,
)
from maverick.assumptions.report import per_spec_counts
from maverick.beads.client import BeadClient
from maverick.beads.models import BeadDetails, BeadSummary


def _client() -> BeadClient:
    return BeadClient(cwd=Path("/tmp/repo"))


def _epic_summary(bead_id: str) -> BeadSummary:
    return BeadSummary(id=bead_id, title=bead_id, status="open", bead_type="epic")


def _epic_details(bead_id: str, speckit_feature: str = "") -> BeadDetails:
    state = {"speckit_feature": speckit_feature} if speckit_feature else {}
    return BeadDetails(id=bead_id, title=bead_id, bead_type="epic", state=state)


def _entry(
    bead_id: str,
    severity: str,
    status: str,
    owner_spec: str,
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


def _legacy(bead_id: str, flight_plan: str = "legacy-plan") -> BeadDetails:
    return BeadDetails(
        id=bead_id,
        title="Review: legacy",
        bead_type="task",
        status="open",
        labels=[ASSUMPTION_REVIEW_LABEL, NEEDS_HUMAN_REVIEW_LABEL],
        state={"source_bead": "b-1", "flight_plan": flight_plan},
    )


class TestPerSpecCounts:
    @pytest.mark.asyncio
    async def test_groups_by_owner_spec_severity_x_status_matrix(self) -> None:
        client = _client()
        epics = {"epic-1": _epic_details("epic-1", "049-assumption-ledger")}
        entries = {
            "dea-1": _entry("dea-1", "high", STATUS_OPEN, "049-assumption-ledger"),
            "dea-2": _entry("dea-2", "medium", STATUS_ANSWERED, "049-assumption-ledger"),
            "dea-3": _entry("dea-3", "low", STATUS_WAIVED, "049-assumption-ledger"),
        }

        async def fake_query(self: BeadClient, filter_expr: str) -> list[BeadSummary]:
            if filter_expr.startswith("type=epic"):
                return [_epic_summary(k) for k in epics]
            return [BeadSummary(id=k, title=k, status="open", bead_type="task") for k in entries]

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            if bead_id in epics:
                return epics[bead_id]
            return entries[bead_id]

        with (
            patch.object(BeadClient, "query", new=fake_query),
            patch.object(BeadClient, "show", new=fake_show),
        ):
            result = await per_spec_counts(client)

        assert len(result) == 1
        row = result[0]
        assert row.owner_spec == "049-assumption-ledger"
        assert row.open[Severity.HIGH] == 1
        assert row.answered[Severity.MEDIUM] == 1
        assert row.waived[Severity.LOW] == 1
        assert row.legacy_open == 0

    @pytest.mark.asyncio
    async def test_legacy_bucket_counted_separately(self) -> None:
        client = _client()
        epics = {"epic-1": _epic_details("epic-1", "049-assumption-ledger")}
        legacy = {"legacy-1": _legacy("legacy-1", flight_plan="049-assumption-ledger")}

        async def fake_query(self: BeadClient, filter_expr: str) -> list[BeadSummary]:
            if filter_expr.startswith("type=epic"):
                return [_epic_summary(k) for k in epics]
            return [BeadSummary(id=k, title=k, status="open", bead_type="task") for k in legacy]

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            if bead_id in epics:
                return epics[bead_id]
            return legacy[bead_id]

        with (
            patch.object(BeadClient, "query", new=fake_query),
            patch.object(BeadClient, "show", new=fake_show),
        ):
            result = await per_spec_counts(client)

        assert len(result) == 1
        assert result[0].legacy_open == 1

    @pytest.mark.asyncio
    async def test_epic_with_zero_entries_renders_zero_row(self) -> None:
        client = _client()
        epics = {
            "epic-1": _epic_details("epic-1", "048-has-entries"),
            "epic-2": _epic_details("epic-2", "049-no-entries"),
        }
        entries = {"dea-1": _entry("dea-1", "medium", STATUS_OPEN, "048-has-entries")}

        async def fake_query(self: BeadClient, filter_expr: str) -> list[BeadSummary]:
            if filter_expr.startswith("type=epic"):
                return [_epic_summary(k) for k in epics]
            return [BeadSummary(id=k, title=k, status="open", bead_type="task") for k in entries]

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            if bead_id in epics:
                return epics[bead_id]
            return entries[bead_id]

        with (
            patch.object(BeadClient, "query", new=fake_query),
            patch.object(BeadClient, "show", new=fake_show),
        ):
            result = await per_spec_counts(client)

        specs = {r.owner_spec for r in result}
        assert specs == {"048-has-entries", "049-no-entries"}
        zero_row = next(r for r in result if r.owner_spec == "049-no-entries")
        assert all(v == 0 for v in zero_row.open.values())
        assert all(v == 0 for v in zero_row.answered.values())
        assert all(v == 0 for v in zero_row.waived.values())
        assert zero_row.legacy_open == 0

    @pytest.mark.asyncio
    async def test_deterministic_ordering_by_owner_spec(self) -> None:
        client = _client()
        epics = {
            "epic-b": _epic_details("epic-b", "050-b-spec"),
            "epic-a": _epic_details("epic-a", "010-a-spec"),
        }

        async def fake_query(self: BeadClient, filter_expr: str) -> list[BeadSummary]:
            if filter_expr.startswith("type=epic"):
                return [_epic_summary(k) for k in epics]
            return []

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            return epics[bead_id]

        with (
            patch.object(BeadClient, "query", new=fake_query),
            patch.object(BeadClient, "show", new=fake_show),
        ):
            result = await per_spec_counts(client)

        assert [r.owner_spec for r in result] == ["010-a-spec", "050-b-spec"]
