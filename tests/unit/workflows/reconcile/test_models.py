"""Tests for reconcile workflow value objects (data-model.md §2-3)."""

from __future__ import annotations

import pytest

from maverick.assumptions.models import Severity
from maverick.workflows.reconcile.models import (
    AnswerOutcome,
    ChangedAnswer,
    ReconcileReport,
    ReconcileStage,
)


class TestReconcileStage:
    def test_values_match_lowercase_identifier_names(self) -> None:
        assert ReconcileStage.PENDING == "pending"
        assert ReconcileStage.SNAPSHOTTED == "snapshotted"
        assert ReconcileStage.CORRECTED == "corrected"
        assert ReconcileStage.CONFLICTS_RESOLVED == "conflicts_resolved"
        assert ReconcileStage.SEMANTIC_DONE == "semantic_done"
        assert ReconcileStage.GATED == "gated"
        assert ReconcileStage.TERMINAL == "terminal"

    def test_all_members_present(self) -> None:
        assert {member.name for member in ReconcileStage} == {
            "PENDING",
            "SNAPSHOTTED",
            "CORRECTED",
            "CONFLICTS_RESOLVED",
            "SEMANTIC_DONE",
            "GATED",
            "TERMINAL",
        }


class TestChangedAnswer:
    def test_construction_with_resolvable_target(self) -> None:
        changed = ChangedAnswer(
            entry_id="bd-123",
            question="Which auth provider?",
            adopted_answer="OAuth",
            human_answer="SAML",
            severity=Severity.MEDIUM,
            owner_spec="051-reconcile-changed-answers",
            stamped_change_ids=("abc123", "def456"),
            target_change_id="abc123",
            stack_index=0,
        )
        assert changed.entry_id == "bd-123"
        assert changed.question == "Which auth provider?"
        assert changed.adopted_answer == "OAuth"
        assert changed.human_answer == "SAML"
        assert changed.severity is Severity.MEDIUM
        assert changed.owner_spec == "051-reconcile-changed-answers"
        assert changed.stamped_change_ids == ("abc123", "def456")
        assert changed.target_change_id == "abc123"
        assert changed.stack_index == 0

    def test_construction_with_unlocatable_target(self) -> None:
        changed = ChangedAnswer(
            entry_id="bd-999",
            question="Q",
            adopted_answer="A",
            human_answer="B",
            severity=Severity.HIGH,
            owner_spec="051-reconcile-changed-answers",
            stamped_change_ids=("zzz999",),
            target_change_id=None,
            stack_index=3,
        )
        assert changed.target_change_id is None

    def test_is_frozen(self) -> None:
        changed = ChangedAnswer(
            entry_id="bd-1",
            question="Q",
            adopted_answer="A",
            human_answer="B",
            severity=Severity.LOW,
            owner_spec="spec",
            stamped_change_ids=(),
            target_change_id=None,
            stack_index=0,
        )
        with pytest.raises(AttributeError):
            changed.entry_id = "changed"  # type: ignore[misc]


class TestAnswerOutcome:
    def test_construction_reconciled(self) -> None:
        outcome = AnswerOutcome(
            entry_id="bd-1",
            status="reconciled",
            stage_reached=ReconcileStage.TERMINAL,
            reason="",
            target_change_id="abc123",
            escalation_bead_id=None,
            gate_passed=True,
            no_change_required=False,
        )
        assert outcome.entry_id == "bd-1"
        assert outcome.status == "reconciled"
        assert outcome.stage_reached is ReconcileStage.TERMINAL
        assert outcome.target_change_id == "abc123"
        assert outcome.gate_passed is True
        assert outcome.no_change_required is False

    def test_construction_skipped(self) -> None:
        outcome = AnswerOutcome(
            entry_id="bd-2",
            status="skipped",
            stage_reached=ReconcileStage.PENDING,
            reason="unlocatable target change id",
        )
        assert outcome.status == "skipped"
        assert outcome.reason == "unlocatable target change id"
        assert outcome.target_change_id is None
        assert outcome.gate_passed is None
        assert outcome.no_change_required is False

    def test_construction_needs_interactive_review(self) -> None:
        outcome = AnswerOutcome(
            entry_id="bd-3",
            status="needs_interactive_review",
            stage_reached=ReconcileStage.GATED,
            reason="gate failed after rollback",
            escalation_bead_id="bd-999",
            gate_passed=False,
        )
        assert outcome.status == "needs_interactive_review"
        assert outcome.escalation_bead_id == "bd-999"
        assert outcome.gate_passed is False

    def test_defaults(self) -> None:
        outcome = AnswerOutcome(
            entry_id="bd-4",
            status="reconciled",
            stage_reached=ReconcileStage.TERMINAL,
        )
        assert outcome.reason == ""
        assert outcome.target_change_id is None
        assert outcome.escalation_bead_id is None
        assert outcome.gate_passed is None
        assert outcome.no_change_required is False


class TestReconcileReport:
    def _outcome(self, status: str, entry_id: str = "bd-1") -> AnswerOutcome:
        return AnswerOutcome(
            entry_id=entry_id,
            status=status,  # type: ignore[arg-type]
            stage_reached=ReconcileStage.TERMINAL,
        )

    def test_construction(self) -> None:
        report = ReconcileReport(
            run_id="abcd1234",
            outcomes=(self._outcome("reconciled"),),
            dry_run=False,
            started_at="2026-07-24T00:00:00Z",
            finished_at="2026-07-24T00:01:00Z",
        )
        assert report.run_id == "abcd1234"
        assert len(report.outcomes) == 1
        assert report.dry_run is False
        assert report.started_at == "2026-07-24T00:00:00Z"
        assert report.finished_at == "2026-07-24T00:01:00Z"

    def test_exit_success_true_when_empty(self) -> None:
        report = ReconcileReport(
            run_id="run1",
            outcomes=(),
            dry_run=False,
            started_at="t0",
            finished_at="t1",
        )
        assert report.exit_success is True

    def test_exit_success_true_when_all_reconciled(self) -> None:
        report = ReconcileReport(
            run_id="run2",
            outcomes=(
                self._outcome("reconciled", "bd-1"),
                self._outcome("reconciled", "bd-2"),
            ),
            dry_run=False,
            started_at="t0",
            finished_at="t1",
        )
        assert report.exit_success is True

    def test_exit_success_false_when_one_not_reconciled(self) -> None:
        report = ReconcileReport(
            run_id="run3",
            outcomes=(
                self._outcome("reconciled", "bd-1"),
                self._outcome("skipped", "bd-2"),
            ),
            dry_run=False,
            started_at="t0",
            finished_at="t1",
        )
        assert report.exit_success is False

    def test_exit_success_false_when_needs_interactive_review(self) -> None:
        report = ReconcileReport(
            run_id="run4",
            outcomes=(self._outcome("needs_interactive_review", "bd-1"),),
            dry_run=True,
            started_at="t0",
            finished_at="t1",
        )
        assert report.exit_success is False

    def test_to_dict_shape(self) -> None:
        outcome = AnswerOutcome(
            entry_id="bd-1",
            status="needs_interactive_review",
            stage_reached=ReconcileStage.GATED,
            reason="gate failed",
            target_change_id=None,
            escalation_bead_id="bd-999",
            gate_passed=False,
            no_change_required=False,
        )
        report = ReconcileReport(
            run_id="run5",
            outcomes=(outcome,),
            dry_run=False,
            started_at="t0",
            finished_at="t1",
        )

        result = report.to_dict()

        assert result == {
            "run_id": "run5",
            "outcomes": [
                {
                    "entry_id": "bd-1",
                    "status": "needs_interactive_review",
                    "reason": "gate failed",
                    "stage_reached": "gated",
                    "target_change_id": None,
                    "escalation_bead_id": "bd-999",
                    "gate_passed": False,
                    "no_change_required": False,
                }
            ],
            "dry_run": False,
            "started_at": "t0",
            "finished_at": "t1",
            "exit_success": False,
        }

    def test_to_dict_empty_outcomes(self) -> None:
        report = ReconcileReport(
            run_id="run6",
            outcomes=(),
            dry_run=False,
            started_at="t0",
            finished_at="t1",
        )
        result = report.to_dict()
        assert result["outcomes"] == []
        assert result["exit_success"] is True
