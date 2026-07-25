"""Unit tests for ``--json`` mode on the decision paths of ``maverick review``
(T007/T011/T012, 053-assumption-review-console): ``review.answer``,
``review.waive``, ``review.bulk-waive``, and the legacy escalation-bead
approve/reject/defer flow under ``--json``.

Mocking style mirrors ``tests/unit/cli/test_review_command.py`` — patch
``BeadClient`` methods and the ``maverick.assumptions.ledger`` functions
(function-local imports in the command modules), never real ``bd``.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

from click.testing import CliRunner

from maverick.assumptions.models import (
    ASSUMPTION_LABEL,
    ASSUMPTION_REVIEW_LABEL,
    KEY_ANSWER,
    KEY_RECONCILE_STATUS,
    KEY_SEVERITY,
    KEY_STATUS,
    KEY_WAIVE_REASON,
    KEY_WAIVED_AT,
    KEY_WAIVED_BY,
    NEEDS_HUMAN_REVIEW_LABEL,
    RECONCILE_STATUS_PENDING,
    STATUS_ANSWERED,
    STATUS_OPEN,
    STATUS_WAIVED,
    AssumptionRecord,
    BulkWaiveResult,
    Severity,
)
from maverick.beads.models import BeadDetails
from maverick.cli.commands.review import review
from maverick.exceptions.beads import BeadQueryError

_LEDGER_DESCRIPTION = (
    "## Question\n\nShould retries be per bead?\n\n"
    "## Adopted Answer\n\nPer bead — matches existing scoping.\n\n"
    "## Alternatives Considered\n\n(none)\n\n"
    "## Context\n\nSource bead: src-1 — Implement the thing\n"
)


def _ledger_details(**state: str) -> BeadDetails:
    return BeadDetails(
        id="dea-1",
        title="Assumption: Should retries be per bead?",
        description=_LEDGER_DESCRIPTION,
        bead_type="task",
        status="open",
        labels=[ASSUMPTION_LABEL],
        state=state,
    )


def _legacy_details(**state: str) -> BeadDetails:
    return BeadDetails(
        id="dea-legacy",
        title="Review: legacy",
        description="legacy escalation",
        bead_type="task",
        status="open",
        labels=[ASSUMPTION_REVIEW_LABEL, NEEDS_HUMAN_REVIEW_LABEL],
        state=state,
    )


def _base_patches(show_side_effect, *, available: bool = True):
    return (
        patch(
            "maverick.beads.client.BeadClient.verify_available",
            new=AsyncMock(return_value=available),
        ),
        patch(
            "maverick.beads.client.BeadClient.show",
            new=AsyncMock(side_effect=show_side_effect),
        ),
    )


class TestAnswerJson:
    def test_success(self) -> None:
        before = _ledger_details(**{KEY_SEVERITY: "medium", KEY_STATUS: STATUS_OPEN})
        after = _ledger_details(
            **{
                KEY_SEVERITY: "medium",
                KEY_STATUS: STATUS_ANSWERED,
                KEY_ANSWER: "Per bead.",
                KEY_RECONCILE_STATUS: RECONCILE_STATUS_PENDING,
            }
        )
        verify, show = _base_patches([before, after])
        runner = CliRunner()
        with (
            verify,
            show,
            patch("maverick.assumptions.ledger.answer", new=AsyncMock()) as mock_answer,
        ):
            result = runner.invoke(review, ["dea-1", "--answer", "Per bead.", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["result"]["action"] == "answered"
        assert data["result"]["entry"]["status"] == "answered"
        assert data["result"]["entry"]["reconcile"]["status"] == "pending"
        mock_answer.assert_awaited_once()
        assert mock_answer.await_args.kwargs["answer_text"] == "Per bead."

    def test_re_answer_of_answered_entry_is_legal(self) -> None:
        before = _ledger_details(**{KEY_SEVERITY: "medium", KEY_STATUS: STATUS_ANSWERED})
        after = _ledger_details(
            **{
                KEY_SEVERITY: "medium",
                KEY_STATUS: STATUS_ANSWERED,
                KEY_ANSWER: "Updated.",
                KEY_RECONCILE_STATUS: RECONCILE_STATUS_PENDING,
            }
        )
        verify, show = _base_patches([before, after])
        runner = CliRunner()
        with (
            verify,
            show,
            patch("maverick.assumptions.ledger.answer", new=AsyncMock()) as mock_answer,
        ):
            result = runner.invoke(review, ["dea-1", "--answer", "Updated.", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["result"]["action"] == "answered"
        mock_answer.assert_awaited_once()

    def test_no_decision_flag_is_validation_error(self) -> None:
        before = _ledger_details(**{KEY_SEVERITY: "medium", KEY_STATUS: STATUS_OPEN})
        verify, show = _base_patches([before])
        runner = CliRunner()
        with verify, show:
            result = runner.invoke(review, ["dea-1", "--json"])
        assert result.exit_code != 0
        data = json.loads(result.output)
        assert data["ok"] is False
        assert data["error"]["kind"] == "validation"

    def test_empty_answer_rejected_before_write(self) -> None:
        before = _ledger_details(**{KEY_SEVERITY: "medium", KEY_STATUS: STATUS_OPEN})
        verify, show = _base_patches([before])
        runner = CliRunner()
        with (
            verify,
            show,
            patch("maverick.assumptions.ledger.answer", new=AsyncMock()) as mock_answer,
        ):
            result = runner.invoke(review, ["dea-1", "--answer", "   ", "--json"])
        assert result.exit_code != 0
        data = json.loads(result.output)
        assert data["error"]["kind"] == "validation"
        mock_answer.assert_not_called()

    def test_already_resolved_when_waived(self) -> None:
        before = _ledger_details(
            **{
                KEY_SEVERITY: "medium",
                KEY_STATUS: STATUS_WAIVED,
                KEY_WAIVED_BY: "alice",
                KEY_WAIVED_AT: "2026-01-01T00:00:00+00:00",
                KEY_WAIVE_REASON: "n/a",
            }
        )
        verify, show = _base_patches([before])
        runner = CliRunner()
        with (
            verify,
            show,
            patch("maverick.assumptions.ledger.answer", new=AsyncMock()) as mock_answer,
        ):
            result = runner.invoke(review, ["dea-1", "--answer", "Per bead.", "--json"])
        assert result.exit_code != 0
        data = json.loads(result.output)
        assert data["error"]["kind"] == "already-resolved"
        assert data["error"]["details"]["entry"]["bead_id"] == "dea-1"
        assert data["error"]["details"]["entry"]["status"] == "waived"
        mock_answer.assert_not_called()

    def test_not_found(self) -> None:
        verify, show = _base_patches(BeadQueryError("no such bead", query="show dea-x"))
        runner = CliRunner()
        with verify, show:
            result = runner.invoke(review, ["dea-x", "--answer", "text", "--json"])
        assert result.exit_code != 0
        data = json.loads(result.output)
        assert data["error"]["kind"] == "not-found"
        assert data["error"]["details"]["bead_id"] == "dea-x"


class TestWaiveJson:
    def test_success(self) -> None:
        before = _ledger_details(**{KEY_SEVERITY: "medium", KEY_STATUS: STATUS_OPEN})
        after = _ledger_details(
            **{
                KEY_SEVERITY: "medium",
                KEY_STATUS: STATUS_WAIVED,
                KEY_WAIVED_BY: "alice",
                KEY_WAIVED_AT: "2026-01-01T00:00:00+00:00",
                KEY_WAIVE_REASON: "no longer applicable",
            }
        )
        verify, show = _base_patches([before, after])
        runner = CliRunner()
        with (
            verify,
            show,
            patch(
                "maverick.cli.commands.review._resolve_git_user_name",
                return_value="alice",
            ),
            patch("maverick.assumptions.ledger.waive", new=AsyncMock()) as mock_waive,
        ):
            result = runner.invoke(review, ["dea-1", "--waive", "no longer applicable", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["result"]["action"] == "waived"
        assert data["result"]["entry"]["status"] == "waived"
        mock_waive.assert_awaited_once()

    def test_already_resolved_when_waived(self) -> None:
        before = _ledger_details(
            **{
                KEY_SEVERITY: "medium",
                KEY_STATUS: STATUS_WAIVED,
                KEY_WAIVED_BY: "alice",
                KEY_WAIVED_AT: "2026-01-01T00:00:00+00:00",
                KEY_WAIVE_REASON: "n/a",
            }
        )
        verify, show = _base_patches([before])
        runner = CliRunner()
        with (
            verify,
            show,
            patch("maverick.assumptions.ledger.waive", new=AsyncMock()) as mock_waive,
        ):
            result = runner.invoke(review, ["dea-1", "--waive", "another reason", "--json"])
        assert result.exit_code != 0
        data = json.loads(result.output)
        assert data["error"]["kind"] == "already-resolved"
        mock_waive.assert_not_called()

    def test_empty_reason_rejected_before_write(self) -> None:
        before = _ledger_details(**{KEY_SEVERITY: "medium", KEY_STATUS: STATUS_OPEN})
        verify, show = _base_patches([before])
        runner = CliRunner()
        with (
            verify,
            show,
            patch("maverick.assumptions.ledger.waive", new=AsyncMock()) as mock_waive,
        ):
            result = runner.invoke(review, ["dea-1", "--waive", "   ", "--json"])
        assert result.exit_code != 0
        data = json.loads(result.output)
        assert data["error"]["kind"] == "validation"
        mock_waive.assert_not_called()


class TestLegacyJson:
    def test_approve(self) -> None:
        details = _legacy_details(source_bead="src-1")
        verify, show = _base_patches([details])
        runner = CliRunner()
        with (
            verify,
            show,
            patch("maverick.beads.client.BeadClient.close", new=AsyncMock()) as mock_close,
        ):
            result = runner.invoke(review, ["dea-legacy", "--approve", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["result"]["action"] == "approved"
        mock_close.assert_awaited_once()

    def test_reject_creates_correction_bead(self) -> None:
        details = _legacy_details(source_bead="src-1")
        source_details = BeadDetails(
            id="src-1",
            title="Implement the thing",
            description="",
            bead_type="task",
            status="open",
            labels=[],
            parent_id="epic-1",
            state={},
        )
        verify, show = _base_patches([details, source_details])
        from maverick.beads.models import BeadCategory, BeadDefinition, BeadType, CreatedBead

        with (
            verify,
            show,
            patch("maverick.beads.client.BeadClient.close", new=AsyncMock()) as mock_close,
            patch(
                "maverick.beads.client.BeadClient.create_bead",
                new=AsyncMock(
                    return_value=CreatedBead(
                        bd_id="correction-1",
                        definition=BeadDefinition(
                            title="Correction",
                            bead_type=BeadType.TASK,
                            priority=1,
                            category=BeadCategory.VALIDATION,
                        ),
                    )
                ),
            ),
        ):
            result = CliRunner().invoke(
                review, ["dea-legacy", "--reject", "Use Dockerfile instead", "--json"]
            )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["result"]["action"] == "rejected"
        assert data["result"]["correction_bead_id"] == "correction-1"
        mock_close.assert_awaited_once()

    def test_defer(self) -> None:
        details = _legacy_details(source_bead="src-1")
        verify, show = _base_patches([details])
        runner = CliRunner()
        with verify, show:
            result = runner.invoke(review, ["dea-legacy", "--defer", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["result"]["action"] == "deferred"

    def test_no_decision_flag_is_validation_error(self) -> None:
        details = _legacy_details(source_bead="src-1")
        verify, show = _base_patches([details])
        runner = CliRunner()
        with verify, show:
            result = runner.invoke(review, ["dea-legacy", "--json"])
        assert result.exit_code != 0
        data = json.loads(result.output)
        assert data["error"]["kind"] == "validation"


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


def _waived_details(bead_id: str) -> BeadDetails:
    return BeadDetails(
        id=bead_id,
        title="Assumption: Q?",
        description=(
            "## Question\n\nQ?\n\n## Adopted Answer\n\nA.\n\n"
            "## Alternatives Considered\n\n(none)\n\n## Context\n\nSource bead: dea-0 — x\n"
        ),
        bead_type="task",
        status="closed",
        labels=[ASSUMPTION_LABEL],
        state={
            KEY_SEVERITY: "low",
            KEY_STATUS: STATUS_WAIVED,
            KEY_WAIVED_BY: "alice",
            KEY_WAIVED_AT: "2026-01-01T00:00:00+00:00",
            KEY_WAIVE_REASON: "accepted for MVP",
        },
    )


class TestBulkWaiveJson:
    def test_success_empty_failed(self) -> None:
        result_obj = BulkWaiveResult(
            waived=(_waived_record("dea-1"), _waived_record("dea-2")),
            failed={},
        )
        verify, show = _base_patches([_waived_details("dea-1"), _waived_details("dea-2")])
        runner = CliRunner()
        with (
            verify,
            show,
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
                review,
                ["--spec", "052-conditional-landing", "--waive", "accepted for MVP", "--json"],
            )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["result"]["owner_spec"] == "052-conditional-landing"
        assert data["result"]["severities"] == ["low"]
        assert {row["bead_id"] for row in data["result"]["waived"]} == {"dea-1", "dea-2"}
        assert data["result"]["failed"] == {}

    def test_zero_matches_is_success(self) -> None:
        result_obj = BulkWaiveResult(waived=(), failed={})
        verify, show = _base_patches([])
        runner = CliRunner()
        with (
            verify,
            show,
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
                review,
                ["--spec", "052-conditional-landing", "--waive", "noise", "--json"],
            )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["result"]["waived"] == []

    def test_partial_failure_exits_nonzero_but_ok_true(self) -> None:
        result_obj = BulkWaiveResult(
            waived=(_waived_record("dea-ok"),),
            failed={"dea-fails": "bd write failed"},
        )
        verify, show = _base_patches([_waived_details("dea-ok")])
        runner = CliRunner()
        with (
            verify,
            show,
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
                review,
                ["--spec", "052-conditional-landing", "--waive", "noise", "--json"],
            )
        assert result.exit_code != 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["result"]["failed"] == {"dea-fails": "bd write failed"}


class TestBdUnavailableKind:
    """`verify_available()` returning False is `bd-unavailable`, never
    `validation`.

    `json_error_handler` can't classify a check that never raises, so each
    verb translates the precondition itself — and all of them must agree
    with `review --list`, which already reported `bd-unavailable` for the
    identical condition. The skill's Preflight branches on this kind to
    tell an environment problem apart from bad user input.
    """

    def test_single_entry_answer(self) -> None:
        verify, show = _base_patches([], available=False)
        runner = CliRunner()
        with verify, show:
            result = runner.invoke(review, ["dea-1", "--answer", "x", "--json"])
        assert result.exit_code != 0
        data = json.loads(result.stdout)
        assert data["ok"] is False
        assert data["verb"] == "review.answer"
        assert data["error"]["kind"] == "bd-unavailable"

    def test_single_entry_waive_uses_waive_verb(self) -> None:
        verify, show = _base_patches([], available=False)
        runner = CliRunner()
        with verify, show:
            result = runner.invoke(review, ["dea-1", "--waive", "why", "--json"])
        data = json.loads(result.stdout)
        assert data["verb"] == "review.waive"
        assert data["error"]["kind"] == "bd-unavailable"

    def test_bulk_waive(self) -> None:
        verify, show = _base_patches([], available=False)
        runner = CliRunner()
        with verify, show:
            result = runner.invoke(review, ["--spec", "052-x", "--waive", "r", "--json"])
        assert result.exit_code != 0
        data = json.loads(result.stdout)
        assert data["verb"] == "review.bulk-waive"
        assert data["error"]["kind"] == "bd-unavailable"


class TestPostWriteReadFailsSoft:
    """A ledger write that succeeded must never be reported as a failure.

    The post-write re-read exists only to project the response row. If it
    fails, the decision is still recorded — reporting `ok: false` would
    tell the human their answer wasn't saved while the ledger says it was.
    """

    def test_answer_write_succeeds_but_reread_fails(self) -> None:
        before = _ledger_details(**{KEY_SEVERITY: "medium", KEY_STATUS: STATUS_OPEN})
        verify, show = _base_patches([before, BeadQueryError("transient bd failure")])
        runner = CliRunner()
        answer_mock = AsyncMock()
        with (
            verify,
            show,
            patch("maverick.assumptions.ledger.answer", new=answer_mock),
        ):
            result = runner.invoke(review, ["dea-1", "--answer", "Per bead.", "--json"])

        answer_mock.assert_awaited_once()
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["ok"] is True
        assert data["result"]["action"] == "answered"
        assert data["result"]["entry"] is None
        assert data["result"]["degraded"] is True

    def test_waive_write_succeeds_but_reread_fails(self) -> None:
        before = _ledger_details(**{KEY_SEVERITY: "low", KEY_STATUS: STATUS_OPEN})
        verify, show = _base_patches([before, BeadQueryError("transient bd failure")])
        runner = CliRunner()
        waive_mock = AsyncMock()
        with (
            verify,
            show,
            patch("maverick.assumptions.ledger.waive", new=waive_mock),
            patch(
                "maverick.cli.commands.review._resolve_git_user_name",
                return_value="alice",
            ),
        ):
            result = runner.invoke(review, ["dea-1", "--waive", "not applicable", "--json"])

        waive_mock.assert_awaited_once()
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["ok"] is True
        assert data["result"]["action"] == "waived"
        assert data["result"]["entry"] is None
        assert data["result"]["degraded"] is True

    def test_successful_reread_carries_no_degraded_flag(self) -> None:
        before = _ledger_details(**{KEY_SEVERITY: "medium", KEY_STATUS: STATUS_OPEN})
        after = _ledger_details(
            **{
                KEY_SEVERITY: "medium",
                KEY_STATUS: STATUS_ANSWERED,
                KEY_ANSWER: "Per bead.",
                KEY_RECONCILE_STATUS: RECONCILE_STATUS_PENDING,
            }
        )
        verify, show = _base_patches([before, after])
        runner = CliRunner()
        with (
            verify,
            show,
            patch("maverick.assumptions.ledger.answer", new=AsyncMock()),
        ):
            result = runner.invoke(review, ["dea-1", "--answer", "Per bead.", "--json"])

        data = json.loads(result.stdout)
        assert data["result"]["entry"]["bead_id"] == "dea-1"
        assert "degraded" not in data["result"]

    def test_bulk_waive_partial_projection_failure_keeps_successes(self) -> None:
        """One unreadable row must not discard the other waives."""
        result_obj = BulkWaiveResult(
            waived=(_waived_record("dea-1"), _waived_record("dea-2")),
            failed={},
        )
        verify, show = _base_patches(
            [_waived_details("dea-1"), BeadQueryError("transient bd failure")]
        )
        runner = CliRunner()
        with (
            verify,
            show,
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
                review,
                ["--spec", "052-conditional-landing", "--waive", "accepted", "--json"],
            )

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["ok"] is True
        assert [row["bead_id"] for row in data["result"]["waived"]] == ["dea-1"]
        # dea-2 WAS waived — only its row couldn't be re-read.
        assert data["result"]["unprojected"] == ["dea-2"]
        assert data["result"]["failed"] == {}
