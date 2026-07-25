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
    STATUS_WAIVED,
    AssumptionRecord,
    BulkWaiveResult,
    Severity,
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


def _waived_record(bead_id: str, question: str = "Q?") -> AssumptionRecord:
    return AssumptionRecord(
        bead_id=bead_id,
        question=question,
        adopted_answer="A.",
        alternatives=(),
        severity=Severity.LOW,
        severity_defaulted=False,
        status=STATUS_WAIVED,
        owner_spec="052-conditional-landing",
        source_bead="dea-0",
        change_ids=(),
        is_legacy=False,
    )


class TestBulkWaiveCli:
    def test_spec_and_waive_waives_matching_entries(self) -> None:
        runner = CliRunner()
        result_obj = BulkWaiveResult(
            waived=(_waived_record("dea-1", "Q1?"), _waived_record("dea-2", "Q2?")),
            failed={},
        )
        with (
            patch(
                "maverick.beads.client.BeadClient.verify_available",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "maverick.cli.commands.review._resolve_git_user_name",
                return_value="Paul O'Fallon",
            ),
            patch(
                "maverick.assumptions.ledger.bulk_waive",
                new=AsyncMock(return_value=result_obj),
            ) as mock_bulk_waive,
        ):
            result = runner.invoke(
                review,
                ["--spec", "052-conditional-landing", "--waive", "accepted for MVP"],
            )
        assert result.exit_code == 0
        assert mock_bulk_waive.await_args.kwargs["owner_spec"] == "052-conditional-landing"
        assert mock_bulk_waive.await_args.kwargs["reason"] == "accepted for MVP"
        assert mock_bulk_waive.await_args.kwargs["waived_by"] == "Paul O'Fallon"
        # Default severity filter is low only.
        assert set(mock_bulk_waive.await_args.kwargs["severities"]) == {Severity.LOW}
        assert "dea-1" in result.output
        assert "dea-2" in result.output
        assert "052-conditional-landing" in result.output

    def test_severity_option_is_repeatable(self) -> None:
        runner = CliRunner()
        result_obj = BulkWaiveResult(waived=(), failed={})
        with (
            patch(
                "maverick.beads.client.BeadClient.verify_available",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "maverick.cli.commands.review._resolve_git_user_name",
                return_value="alice",
            ),
            patch(
                "maverick.assumptions.ledger.bulk_waive",
                new=AsyncMock(return_value=result_obj),
            ) as mock_bulk_waive,
        ):
            result = runner.invoke(
                review,
                [
                    "--spec",
                    "052-conditional-landing",
                    "--waive",
                    "noise",
                    "--severity",
                    "low",
                    "--severity",
                    "medium",
                ],
            )
        assert result.exit_code == 0
        assert set(mock_bulk_waive.await_args.kwargs["severities"]) == {
            Severity.LOW,
            Severity.MEDIUM,
        }

    def test_bead_id_and_spec_mutually_exclusive(self) -> None:
        runner = CliRunner()
        result = runner.invoke(
            review, ["dea-1", "--spec", "052-conditional-landing", "--waive", "x"]
        )
        assert result.exit_code != 0
        assert "mutually exclusive" in result.output.lower()

    def test_spec_without_waive_errors(self) -> None:
        runner = CliRunner()
        result = runner.invoke(review, ["--spec", "052-conditional-landing"])
        assert result.exit_code != 0

    def test_spec_with_answer_errors(self) -> None:
        runner = CliRunner()
        result = runner.invoke(review, ["--spec", "052-conditional-landing", "--answer", "Yes."])
        assert result.exit_code != 0

    def test_neither_bead_id_nor_spec_errors(self) -> None:
        runner = CliRunner()
        result = runner.invoke(review, [])
        assert result.exit_code != 0

    def test_zero_matches_exits_zero_with_message(self) -> None:
        runner = CliRunner()
        result_obj = BulkWaiveResult(waived=(), failed={})
        with (
            patch(
                "maverick.beads.client.BeadClient.verify_available",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "maverick.cli.commands.review._resolve_git_user_name",
                return_value="alice",
            ),
            patch(
                "maverick.assumptions.ledger.bulk_waive",
                new=AsyncMock(return_value=result_obj),
            ),
        ):
            result = runner.invoke(
                review, ["--spec", "052-conditional-landing", "--waive", "noise"]
            )
        assert result.exit_code == 0
        assert "no open" in result.output.lower() or "nothing" in result.output.lower()

    def test_partial_failure_exits_nonzero_listing_failures(self) -> None:
        runner = CliRunner()
        result_obj = BulkWaiveResult(
            waived=(_waived_record("dea-ok"),),
            failed={"dea-fails": "bd write failed"},
        )
        with (
            patch(
                "maverick.beads.client.BeadClient.verify_available",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "maverick.cli.commands.review._resolve_git_user_name",
                return_value="alice",
            ),
            patch(
                "maverick.assumptions.ledger.bulk_waive",
                new=AsyncMock(return_value=result_obj),
            ),
        ):
            result = runner.invoke(
                review, ["--spec", "052-conditional-landing", "--waive", "noise"]
            )
        assert result.exit_code != 0
        assert "dea-fails" in result.output
        assert "bd write failed" in result.output

    def test_bd_unavailable_errors(self) -> None:
        runner = CliRunner()
        with patch(
            "maverick.beads.client.BeadClient.verify_available",
            new=AsyncMock(return_value=False),
        ):
            result = runner.invoke(
                review, ["--spec", "052-conditional-landing", "--waive", "noise"]
            )
        assert result.exit_code != 0
