"""Regression test: standalone (unparented, `source_ref`-keyed) ledger
entries flow through the existing spec-049 readers unchanged.

Pins the compatibility invariant from
specs/050-headless-spec-chain/contracts/ledger-and-beads.md: `maverick
brief` (`per_spec_counts`), `maverick review` (label lookup), and the
land gate (`open_blocking_entries`) key on labels + state keys only, not
the parent edge — so standalone entries participate in all three exactly
like parented ones.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

from click.testing import CliRunner

from maverick.assumptions.ledger import open_blocking_entries
from maverick.assumptions.models import (
    ASSUMPTION_LABEL,
    ASSUMPTION_REVIEW_LABEL,
    KEY_OWNER_SPEC,
    KEY_SEVERITY,
    KEY_SOURCE_REF,
    KEY_STATUS,
    NEEDS_HUMAN_REVIEW_LABEL,
    STATUS_OPEN,
    Severity,
)
from maverick.assumptions.report import per_spec_counts
from maverick.beads.client import BeadClient
from maverick.beads.models import BeadDetails, BeadSummary
from maverick.cli.commands.review import review

_STANDALONE_DESCRIPTION = (
    "## Question\n\nShould exports include archived widgets?\n\n"
    "## Adopted Answer\n\nNo, exclude archived widgets by default.\n\n"
    "## Alternatives Considered\n\n- Include all widgets\n\n"
    "## Context\n\nSource bead: spec-chain:clarify — spec-chain:clarify\n"
)


def _standalone_entry(**state: str) -> BeadDetails:
    return BeadDetails(
        id="dea-standalone",
        title="Assumption: Should exports include archived widgets?",
        description=_STANDALONE_DESCRIPTION,
        bead_type="task",
        status="open",
        parent_id=None,
        labels=[ASSUMPTION_LABEL, ASSUMPTION_REVIEW_LABEL, NEEDS_HUMAN_REVIEW_LABEL],
        state=state,
    )


class TestPerSpecCountsUnaffectedByMissingParent:
    async def test_standalone_entry_is_counted_under_its_owner_spec(self) -> None:
        client = BeadClient(cwd=Path("/tmp/repo"))
        entry = _standalone_entry(
            **{
                KEY_SEVERITY: "medium",
                KEY_STATUS: STATUS_OPEN,
                KEY_OWNER_SPEC: "050-headless-spec-chain",
                KEY_SOURCE_REF: "spec-chain:clarify",
            }
        )

        async def fake_query(self: BeadClient, expr: str) -> list[BeadSummary]:
            if "epic" in expr:
                return []  # no epic exists yet for this spec
            return [
                BeadSummary(
                    id="dea-standalone", title=entry.title, status="open", bead_type="task"
                )
            ]

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            return entry

        with (
            patch.object(BeadClient, "query", new=fake_query),
            patch.object(BeadClient, "show", new=fake_show),
        ):
            counts = await per_spec_counts(client)

        by_spec = {row.owner_spec: row for row in counts}
        assert "050-headless-spec-chain" in by_spec
        assert by_spec["050-headless-spec-chain"].open[Severity.MEDIUM] == 1


class TestOpenBlockingEntriesUnaffectedByMissingParent:
    async def test_standalone_medium_entry_blocks(self) -> None:
        client = BeadClient(cwd=Path("/tmp/repo"))
        entry = _standalone_entry(
            **{
                KEY_SEVERITY: "medium",
                KEY_STATUS: STATUS_OPEN,
                KEY_OWNER_SPEC: "050-headless-spec-chain",
                KEY_SOURCE_REF: "spec-chain:clarify",
            }
        )

        async def fake_query(self: BeadClient, expr: str) -> list[BeadSummary]:
            return [
                BeadSummary(
                    id="dea-standalone", title=entry.title, status="open", bead_type="task"
                )
            ]

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            return entry

        with (
            patch.object(BeadClient, "query", new=fake_query),
            patch.object(BeadClient, "show", new=fake_show),
        ):
            blocking = await open_blocking_entries(client)

        assert len(blocking) == 1
        assert blocking[0].bead_id == "dea-standalone"
        assert blocking[0].owner_spec == "050-headless-spec-chain"

    async def test_standalone_low_entry_does_not_block(self) -> None:
        client = BeadClient(cwd=Path("/tmp/repo"))
        entry = _standalone_entry(
            **{
                KEY_SEVERITY: "low",
                KEY_STATUS: STATUS_OPEN,
                KEY_OWNER_SPEC: "050-headless-spec-chain",
                KEY_SOURCE_REF: "spec-chain:clarify",
            }
        )

        async def fake_query(self: BeadClient, expr: str) -> list[BeadSummary]:
            return [
                BeadSummary(
                    id="dea-standalone", title=entry.title, status="open", bead_type="task"
                )
            ]

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            return entry

        with (
            patch.object(BeadClient, "query", new=fake_query),
            patch.object(BeadClient, "show", new=fake_show),
        ):
            blocking = await open_blocking_entries(client)

        assert blocking == ()


class TestReviewLabelLookupUnaffectedByMissingParent:
    def test_answer_flow_works_on_standalone_entry(self) -> None:
        runner = CliRunner()
        entry = _standalone_entry(
            **{
                KEY_SEVERITY: "medium",
                KEY_STATUS: STATUS_OPEN,
                KEY_OWNER_SPEC: "050-headless-spec-chain",
                KEY_SOURCE_REF: "spec-chain:clarify",
            }
        )

        with (
            patch(
                "maverick.beads.client.BeadClient.verify_available",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "maverick.beads.client.BeadClient.show",
                new=AsyncMock(return_value=entry),
            ),
            patch("maverick.assumptions.ledger.answer", new=AsyncMock()) as mock_answer,
        ):
            result = runner.invoke(
                review, ["dea-standalone", "--answer", "No, exclude archived widgets."]
            )

        assert result.exit_code == 0
        mock_answer.assert_awaited_once()
        assert "answered and closed" in result.output
