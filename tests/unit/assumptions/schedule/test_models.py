"""Smoke tests for maverick.assumptions.schedule.models.

Constructs one instance of every dataclass/enum in the module. Downstream
phases (evaluate.py, deliver.py) exercise these more thoroughly through
``evaluate()``/``deliver()``; this module has no dedicated test task of its
own (tasks.md T007).
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime

import pytest

from maverick.assumptions.models import Severity
from maverick.assumptions.schedule.models import (
    AutoWaiveDecision,
    BatchSummary,
    DecisionKind,
    DeliveryDecision,
    EvaluationOutcome,
    SkipDecision,
    SkipReason,
    WindowOccurrence,
)
from maverick.assumptions.schedule.state import DeliveryState


def _make_occurrence() -> WindowOccurrence:
    return WindowOccurrence(
        date=date(2026, 8, 6),
        window="09:00",
        due_at=datetime(2026, 8, 6, 9, 0, tzinfo=UTC),
    )


def _make_summary() -> BatchSummary:
    return BatchSummary(
        counts={Severity.LOW: 1, Severity.MEDIUM: 2, Severity.HIGH: 0},
        owner_specs=("054-assumption-batch-scheduler",),
        oldest_age_hours=12.5,
        review_invocation="maverick review --list --status open",
    )


class TestDecisionKind:
    def test_members(self) -> None:
        assert DecisionKind.WINDOW_BATCH == "window-batch"
        assert DecisionKind.INTERRUPT == "interrupt"
        assert DecisionKind.ESCALATION == "escalation"
        assert DecisionKind.RENOTIFY == "renotify"


class TestSkipReason:
    def test_members(self) -> None:
        assert SkipReason.MIN_BATCH_SIZE == "min-batch-size"
        assert SkipReason.QUIET_HOURS == "quiet-hours"
        assert SkipReason.ALREADY_DELIVERED == "already-delivered"
        assert SkipReason.NOT_YET_DUE == "not-yet-due"
        assert SkipReason.LOW_NEVER_PROACTIVE == "low-never-proactive"
        assert SkipReason.EMPTY_BATCH == "empty-batch"


class TestWindowOccurrence:
    def test_construction_and_identity_fields(self) -> None:
        occurrence = _make_occurrence()
        assert occurrence.date == date(2026, 8, 6)
        assert occurrence.window == "09:00"
        assert occurrence.due_at.tzinfo is not None

    def test_frozen(self) -> None:
        occurrence = _make_occurrence()
        with pytest.raises(FrozenInstanceError):
            occurrence.window = "10:00"  # type: ignore[misc]


class TestBatchSummary:
    def test_construction(self) -> None:
        summary = _make_summary()
        assert summary.counts[Severity.MEDIUM] == 2
        assert summary.owner_specs == ("054-assumption-batch-scheduler",)
        assert summary.oldest_age_hours == 12.5
        assert summary.review_invocation == "maverick review --list --status open"

    def test_counts_cannot_be_mutated(self) -> None:
        """One summary instance is shared by every DeliveryDecision in a run
        *and* by every persisted DeliveryRecord, so a mutable ``counts``
        would let one consumer silently rewrite the audit trail."""
        summary = _make_summary()

        with pytest.raises(TypeError):
            summary.counts[Severity.HIGH] = 99  # type: ignore[index]
        with pytest.raises(AttributeError):
            summary.counts.clear()  # type: ignore[attr-defined]

        assert summary.counts[Severity.HIGH] == 0

    def test_counts_snapshots_the_caller_dict(self) -> None:
        """Construction takes a plain dict (ergonomics) but detaches from it —
        mutating the caller's dict afterwards must not reach the summary."""
        source = {Severity.LOW: 1, Severity.MEDIUM: 2, Severity.HIGH: 0}
        summary = BatchSummary(
            counts=source,
            owner_specs=(),
            oldest_age_hours=0.0,
            review_invocation="maverick review --list --status open",
        )

        source[Severity.HIGH] = 7

        assert summary.counts[Severity.HIGH] == 0

    def test_to_dict_projection_unchanged(self) -> None:
        assert _make_summary().to_dict() == {
            "counts": {"low": 1, "medium": 2, "high": 0},
            "owner_specs": ["054-assumption-batch-scheduler"],
            "oldest_age_hours": 12.5,
            "review_invocation": "maverick review --list --status open",
        }

    def test_equality_still_holds_across_instances(self) -> None:
        assert _make_summary() == _make_summary()


class TestDeliveryDecision:
    def test_window_batch_carries_occurrence(self) -> None:
        occurrence = _make_occurrence()
        decision = DeliveryDecision(
            kind=DecisionKind.WINDOW_BATCH,
            entry_ids=("bd-1", "bd-2"),
            summary=_make_summary(),
            occurrence=occurrence,
            rule="window 09:00 due",
        )
        assert decision.kind == DecisionKind.WINDOW_BATCH
        assert decision.occurrence == occurrence
        assert decision.entry_ids == ("bd-1", "bd-2")

    def test_interrupt_has_no_occurrence(self) -> None:
        decision = DeliveryDecision(
            kind=DecisionKind.INTERRUPT,
            entry_ids=("bd-3",),
            summary=_make_summary(),
            occurrence=None,
            rule="high severity, outside quiet hours",
        )
        assert decision.occurrence is None


class TestSkipDecision:
    def test_construction(self) -> None:
        skip = SkipDecision(
            reason=SkipReason.MIN_BATCH_SIZE,
            occurrence=_make_occurrence(),
            entry_ids=("bd-4",),
            rule="min_batch_size=3, got 1",
        )
        assert skip.reason == SkipReason.MIN_BATCH_SIZE
        assert skip.entry_ids == ("bd-4",)


class TestAutoWaiveDecision:
    def test_construction(self) -> None:
        decision = AutoWaiveDecision(
            entry_id="bd-5",
            reason_text="auto-waived by schedule policy after 168h: stale low-severity assumption",
        )
        assert decision.entry_id == "bd-5"
        assert "auto-waived" in decision.reason_text


class TestEvaluationOutcome:
    def test_construction(self) -> None:
        state_after = DeliveryState(updated_at="2026-08-06T09:00:00Z")
        outcome = EvaluationOutcome(
            deliveries=(
                DeliveryDecision(
                    kind=DecisionKind.WINDOW_BATCH,
                    entry_ids=("bd-1",),
                    summary=_make_summary(),
                    occurrence=_make_occurrence(),
                    rule="window 09:00 due",
                ),
            ),
            skips=(
                SkipDecision(
                    reason=SkipReason.LOW_NEVER_PROACTIVE,
                    occurrence=None,
                    entry_ids=("bd-6",),
                    rule="low severity never delivers proactively",
                ),
            ),
            auto_waives=(AutoWaiveDecision(entry_id="bd-7", reason_text="stale low entry"),),
            state_after=state_after,
        )
        assert len(outcome.deliveries) == 1
        assert len(outcome.skips) == 1
        assert len(outcome.auto_waives) == 1
        assert outcome.state_after is state_after
