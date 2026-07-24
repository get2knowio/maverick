"""Unit tests for the ``maverick review`` command's ledger display and
answer/waive flows (T029/T032). Legacy escalation-bead behavior
(approve/reject/defer) is exercised implicitly by not setting the
``assumption`` label.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from click.testing import CliRunner

from maverick.assumptions.models import (
    ASSUMPTION_LABEL,
    ASSUMPTION_REVIEW_LABEL,
    KEY_CHANGE_IDS,
    KEY_OWNER_SPEC,
    KEY_SEVERITY,
    KEY_SEVERITY_DEFAULTED,
    KEY_SOURCE_BEAD,
    NEEDS_HUMAN_REVIEW_LABEL,
)
from maverick.beads.models import BeadDetails
from maverick.cli.commands.review import review

_LEDGER_DESCRIPTION = (
    "## Question\n\nShould retries be per bead?\n\n"
    "## Adopted Answer\n\nPer bead — matches existing scoping.\n\n"
    "## Alternatives Considered\n\n- Per run\n- Configurable\n\n"
    "## Context\n\nSource bead: src-1 — Implement the thing\n"
)


def _ledger_details(**state: str) -> BeadDetails:
    return BeadDetails(
        id="dea-1",
        title="Assumption: Should retries be per bead?",
        description=_LEDGER_DESCRIPTION,
        bead_type="task",
        status="open",
        labels=[ASSUMPTION_LABEL, ASSUMPTION_REVIEW_LABEL, NEEDS_HUMAN_REVIEW_LABEL],
        state=state,
    )


def _patch_client(details: BeadDetails):
    return (
        patch(
            "maverick.beads.client.BeadClient.verify_available",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "maverick.beads.client.BeadClient.show",
            new=AsyncMock(return_value=details),
        ),
    )


class TestLedgerDisplay:
    def test_shows_question_answer_alternatives_severity_spec_stamps_source(self) -> None:
        runner = CliRunner()
        details = _ledger_details(
            **{
                KEY_SEVERITY: "high",
                KEY_OWNER_SPEC: "049-assumption-ledger",
                KEY_SOURCE_BEAD: "src-1",
                KEY_CHANGE_IDS: "abc123",
            }
        )
        verify, show = _patch_client(details)
        with verify, show:
            result = runner.invoke(review, ["dea-1", "--waive", "not needed"])
        assert "Should retries be per bead?" in result.output
        assert "Per bead — matches existing scoping." in result.output
        assert "Per run" in result.output
        assert "high" in result.output
        assert "049-assumption-ledger" in result.output
        assert "abc123" in result.output
        assert "src-1" in result.output

    def test_defaulted_severity_marker(self) -> None:
        runner = CliRunner()
        details = _ledger_details(**{KEY_SEVERITY: "medium", KEY_SEVERITY_DEFAULTED: "true"})
        verify, show = _patch_client(details)
        with verify, show:
            result = runner.invoke(review, ["dea-1", "--waive", "n/a"])
        assert "(defaulted)" in result.output

    def test_unstamped_entry_shows_unstamped(self) -> None:
        runner = CliRunner()
        details = _ledger_details(**{KEY_SEVERITY: "medium"})
        verify, show = _patch_client(details)
        with verify, show:
            result = runner.invoke(review, ["dea-1", "--waive", "n/a"])
        assert "unstamped" in result.output


class TestAnswerFlow:
    def test_answer_records_and_closes(self) -> None:
        runner = CliRunner()
        details = _ledger_details(**{KEY_SEVERITY: "medium"})
        verify, show = _patch_client(details)
        with (
            verify,
            show,
            patch("maverick.assumptions.ledger.answer", new=AsyncMock()) as mock_answer,
        ):
            result = runner.invoke(review, ["dea-1", "--answer", "Per bead."])
        assert result.exit_code == 0
        mock_answer.assert_awaited_once()
        assert mock_answer.await_args.kwargs["answer_text"] == "Per bead."
        assert "answered and closed" in result.output

    def test_empty_answer_rejected(self) -> None:
        runner = CliRunner()
        details = _ledger_details(**{KEY_SEVERITY: "medium"})
        verify, show = _patch_client(details)
        with verify, show:
            result = runner.invoke(review, ["dea-1", "--answer", "   "])
        assert result.exit_code != 0
        assert "must not be empty" in result.output


class TestWaiveFlow:
    def test_waive_records_who_when_why_and_closes(self) -> None:
        runner = CliRunner()
        details = _ledger_details(**{KEY_SEVERITY: "medium"})
        verify, show = _patch_client(details)
        with (
            verify,
            show,
            patch(
                "maverick.cli.commands.review._resolve_git_user_name",
                return_value="alice",
            ),
            patch("maverick.assumptions.ledger.waive", new=AsyncMock()) as mock_waive,
        ):
            result = runner.invoke(review, ["dea-1", "--waive", "no longer applicable"])
        assert result.exit_code == 0
        mock_waive.assert_awaited_once()
        assert mock_waive.await_args.kwargs["reason"] == "no longer applicable"
        assert mock_waive.await_args.kwargs["waived_by"] == "alice"
        assert "waived by alice" in result.output

    def test_empty_reason_rejected(self) -> None:
        runner = CliRunner()
        details = _ledger_details(**{KEY_SEVERITY: "medium"})
        verify, show = _patch_client(details)
        with verify, show:
            result = runner.invoke(review, ["dea-1", "--waive", "   "])
        assert result.exit_code != 0
        assert "must not be empty" in result.output


class TestMutualExclusion:
    def test_answer_and_waive_together_rejected(self) -> None:
        runner = CliRunner()
        result = runner.invoke(review, ["dea-1", "--answer", "A.", "--waive", "not needed"])
        assert result.exit_code != 0
        assert "mutually exclusive" in result.output


class TestLegacyBeadsUnaffected:
    def test_legacy_escalation_bead_keeps_approve_flow(self) -> None:
        """A bead without the `assumption` label keeps today's behavior."""
        runner = CliRunner()
        legacy_details = BeadDetails(
            id="dea-legacy",
            title="Review: legacy",
            description="legacy escalation",
            bead_type="task",
            status="open",
            labels=[ASSUMPTION_REVIEW_LABEL, NEEDS_HUMAN_REVIEW_LABEL],
            state={"source_bead": "b-1"},
        )
        verify, show = _patch_client(legacy_details)
        with (
            verify,
            show,
            patch(
                "maverick.beads.client.BeadClient.close",
                new=AsyncMock(),
            ) as mock_close,
        ):
            result = runner.invoke(review, ["dea-legacy", "--approve"])
        assert result.exit_code == 0
        mock_close.assert_awaited_once()
        assert "closed as approved" in result.output
