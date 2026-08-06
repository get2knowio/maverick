"""Severity-tier evaluation tests (tasks.md T011).

Covers: medium batches only at windows, low counted-but-silent
(clarification Q5), legacy entries batching like medium (FR-019, research
R9), and structural exclusion of entries resolved before their window
(FR-014).

Direct ``evaluate(entries, schedule, state, now)`` calls with injected
aware local datetimes only — no freezegun, no ``datetime.now`` mocking.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from maverick.assumptions.models import (
    STATUS_ANSWERED,
    STATUS_OPEN,
    STATUS_WAIVED,
    AssumptionRecord,
    AssumptionReportEntry,
    Severity,
)
from maverick.assumptions.schedule.evaluate import evaluate
from maverick.assumptions.schedule.models import DecisionKind, SkipReason
from maverick.assumptions.schedule.state import DeliveryState
from maverick.config import AssumptionScheduleConfig, QuietHoursConfig

NY = ZoneInfo("America/New_York")


def _config(
    *, windows: list[str] | None = None, min_batch_size: int = 1
) -> AssumptionScheduleConfig:
    return AssumptionScheduleConfig(
        windows=windows if windows is not None else ["09:00"],
        min_batch_size=min_batch_size,
    )


def _state() -> DeliveryState:
    return DeliveryState(updated_at="2026-08-01T00:00:00Z")


def _entry(
    bead_id: str,
    *,
    severity: Severity = Severity.MEDIUM,
    status: str = STATUS_OPEN,
    owner_spec: str = "054-assumption-batch-scheduler",
    created_at: str | None = None,
    is_legacy: bool = False,
) -> AssumptionReportEntry:
    return AssumptionReportEntry(
        record=AssumptionRecord(
            bead_id=bead_id,
            question="Q?",
            adopted_answer="A.",
            alternatives=(),
            severity=severity,
            severity_defaulted=False,
            status=status,
            owner_spec=owner_spec,
            source_bead="mav-source",
            change_ids=(),
            is_legacy=is_legacy,
            created_at=created_at,
        ),
        final_answer="Yes." if status == STATUS_ANSWERED else None,
        waived_by="alice" if status == STATUS_WAIVED else None,
        waived_at="2026-07-24T14:00:00Z" if status == STATUS_WAIVED else None,
        waive_reason="n/a" if status == STATUS_WAIVED else None,
        reconcile_status=None,
        reconciled_answer=None,
        reconcile_change_id=None,
        reconcile_reason=None,
        pending_reconcile=False,
    )


_NOON = datetime(2026, 8, 6, 9, 0, tzinfo=NY)


class TestMediumBatchesOnly:
    def test_medium_entries_deliver_at_window(self) -> None:
        schedule = _config()
        entries = (_entry("mav-1", severity=Severity.MEDIUM),)

        outcome = evaluate(entries, schedule, _state(), _NOON)

        assert len(outcome.deliveries) == 1
        delivery = outcome.deliveries[0]
        assert delivery.kind == DecisionKind.WINDOW_BATCH
        assert delivery.entry_ids == ("mav-1",)

    def test_high_entries_do_not_drive_window_batching(self) -> None:
        """A high-severity entry never itself triggers or blocks a window
        *batch* decision — the window occurrence still records empty (no
        medium entries pending it). It is delivered separately, as an
        interrupt (T020, ``TestHighSeverityInterrupt`` below) — not folded
        into window-batch accounting."""
        schedule = _config()
        entries = (_entry("mav-hi", severity=Severity.HIGH),)

        outcome = evaluate(entries, schedule, _state(), _NOON)

        assert not any(d.kind == DecisionKind.WINDOW_BATCH for d in outcome.deliveries)
        window_skips = [s for s in outcome.skips if s.reason == SkipReason.EMPTY_BATCH]
        assert len(window_skips) == 1
        assert window_skips[0].entry_ids == ()


class TestLowNeverProactive:
    def test_low_only_yields_low_never_proactive_skip(self) -> None:
        schedule = _config()
        entries = (
            _entry("mav-lo1", severity=Severity.LOW),
            _entry("mav-lo2", severity=Severity.LOW),
        )

        outcome = evaluate(entries, schedule, _state(), _NOON)

        assert outcome.deliveries == ()
        skip = outcome.skips[0]
        assert skip.reason == SkipReason.LOW_NEVER_PROACTIVE
        assert set(skip.entry_ids) == {"mav-lo1", "mav-lo2"}

    def test_low_entries_never_deliver_even_across_many_windows(self) -> None:
        schedule = _config(windows=["09:00", "17:00"])
        entries = (_entry("mav-lo1", severity=Severity.LOW),)

        first = evaluate(entries, schedule, _state(), datetime(2026, 8, 6, 9, 0, tzinfo=NY))
        second = evaluate(
            entries, schedule, first.state_after, datetime(2026, 8, 6, 17, 0, tzinfo=NY)
        )

        assert first.deliveries == ()
        assert second.deliveries == ()

    def test_low_counted_in_batch_summary_when_medium_batch_delivers(self) -> None:
        """A mixed ledger (medium + low + high) yields a window batch *and*
        a separate high-severity interrupt (T020) — the batch's summary
        still counts every severity (clarification Q5), but the batch's
        covered ``entry_ids`` never include the high entry (no cross-talk;
        see also ``TestMixedLedgerNoCrossTalk`` below)."""
        schedule = _config()
        entries = (
            _entry("mav-med", severity=Severity.MEDIUM),
            _entry("mav-lo1", severity=Severity.LOW),
            _entry("mav-lo2", severity=Severity.LOW),
            _entry("mav-hi", severity=Severity.HIGH),
        )

        outcome = evaluate(entries, schedule, _state(), _NOON)

        by_kind = {d.kind: d for d in outcome.deliveries}
        assert set(by_kind) == {DecisionKind.WINDOW_BATCH, DecisionKind.INTERRUPT}

        batch = by_kind[DecisionKind.WINDOW_BATCH]
        summary = batch.summary
        assert summary.counts[Severity.MEDIUM] == 1
        assert summary.counts[Severity.LOW] == 2
        assert summary.counts[Severity.HIGH] == 1
        # Low entries are informational only — never part of what's covered.
        assert batch.entry_ids == ("mav-med",)

        interrupt = by_kind[DecisionKind.INTERRUPT]
        assert interrupt.entry_ids == ("mav-hi",)


class TestLegacyEntriesBatchLikeMedium:
    def test_legacy_entry_participates_in_min_batch_and_delivery(self) -> None:
        """report_entries() already synthesizes legacy severity as MEDIUM
        (FR-019, research R9) — evaluate() needs no special-casing, only
        this pinned behavior."""
        schedule = _config(min_batch_size=2)
        legacy = _entry("mav-legacy", severity=Severity.MEDIUM, is_legacy=True)
        medium = _entry("mav-2", severity=Severity.MEDIUM)

        outcome = evaluate((legacy, medium), schedule, _state(), _NOON)

        assert len(outcome.deliveries) == 1
        assert set(outcome.deliveries[0].entry_ids) == {"mav-legacy", "mav-2"}

    def test_lone_legacy_entry_below_min_batch_rolls_forward(self) -> None:
        schedule = _config(min_batch_size=2)
        legacy = _entry("mav-legacy", severity=Severity.MEDIUM, is_legacy=True)

        outcome = evaluate((legacy,), schedule, _state(), _NOON)

        assert outcome.deliveries == ()
        skip = outcome.skips[0]
        assert skip.reason == SkipReason.MIN_BATCH_SIZE
        assert skip.entry_ids == ("mav-legacy",)


class TestResolvedBeforeWindowExcludedStructurally:
    def test_answered_entry_excluded_from_batch(self) -> None:
        schedule = _config()
        answered = _entry("mav-answered", severity=Severity.MEDIUM, status=STATUS_ANSWERED)

        outcome = evaluate((answered,), schedule, _state(), _NOON)

        assert outcome.deliveries == ()
        skip = outcome.skips[0]
        assert skip.reason == SkipReason.EMPTY_BATCH
        assert skip.entry_ids == ()

    def test_waived_entry_excluded_from_batch(self) -> None:
        schedule = _config()
        waived = _entry("mav-waived", severity=Severity.MEDIUM, status=STATUS_WAIVED)

        outcome = evaluate((waived,), schedule, _state(), _NOON)

        assert outcome.deliveries == ()
        assert outcome.skips[0].reason == SkipReason.EMPTY_BATCH

    def test_batch_resolved_between_accumulation_and_delivery_is_empty(self) -> None:
        """FR-014: entries resolved between accumulation and the delivery
        window must be excluded — a batch whose entries are all resolved by
        the time the window fires delivers nothing."""
        schedule = _config(min_batch_size=1)
        # By the time the window is (re-)evaluated, the entry was answered.
        resolved_by_window_time = (
            _entry("mav-1", severity=Severity.MEDIUM, status=STATUS_ANSWERED),
        )

        outcome = evaluate(resolved_by_window_time, schedule, _state(), _NOON)

        assert outcome.deliveries == ()
        assert outcome.skips[0].reason == SkipReason.EMPTY_BATCH

    def test_mixed_open_and_resolved_only_open_counted(self) -> None:
        schedule = _config(min_batch_size=1)
        entries = (
            _entry("mav-open", severity=Severity.MEDIUM, status=STATUS_OPEN),
            _entry("mav-answered", severity=Severity.MEDIUM, status=STATUS_ANSWERED),
            _entry("mav-waived", severity=Severity.MEDIUM, status=STATUS_WAIVED),
        )

        outcome = evaluate(entries, schedule, _state(), _NOON)

        assert len(outcome.deliveries) == 1
        assert outcome.deliveries[0].entry_ids == ("mav-open",)
        assert outcome.deliveries[0].summary.counts[Severity.MEDIUM] == 1


class TestHighSeverityInterrupt:
    """T019/US2: high-severity entries deliver as interrupts at the next
    permissible evaluation, independent of review windows (FR-002, FR-004,
    spec.md US2 acceptance scenarios 1-3)."""

    def test_high_entry_delivers_interrupt_outside_windows(self) -> None:
        """US2 scenario 1: a high entry delivers at the next evaluation —
        it does not wait for the 17:00 window."""
        schedule = _config(windows=["09:00", "17:00"])
        entries = (_entry("mav-hi", severity=Severity.HIGH),)
        mid_afternoon = datetime(2026, 8, 6, 14, 23, tzinfo=NY)

        outcome = evaluate(entries, schedule, _state(), mid_afternoon)

        interrupts = [d for d in outcome.deliveries if d.kind == DecisionKind.INTERRUPT]
        assert len(interrupts) == 1
        assert interrupts[0].entry_ids == ("mav-hi",)
        assert interrupts[0].occurrence is None

    def test_interrupt_delivered_at_set_and_suppresses_redelivery(self) -> None:
        schedule = _config()
        entries = (_entry("mav-hi", severity=Severity.HIGH),)

        first = evaluate(entries, schedule, _state(), _NOON)

        assert any(d.kind == DecisionKind.INTERRUPT for d in first.deliveries)
        tracked = first.state_after.entry_tracking["mav-hi"]
        assert tracked.interrupt_delivered_at is not None

        one_hour_later = _NOON + timedelta(hours=1)
        second = evaluate(entries, schedule, first.state_after, one_hour_later)

        assert not any(d.kind == DecisionKind.INTERRUPT for d in second.deliveries)
        assert not any(s.reason == SkipReason.QUIET_HOURS for s in second.skips)

    def test_quiet_hours_high_overrides_quiet_true_delivers(self) -> None:
        """US2 scenario 2: default policy delivers through quiet hours."""
        schedule = AssumptionScheduleConfig(
            windows=["09:00"],
            quiet_hours=QuietHoursConfig(start="22:00", end="07:00"),
            high_overrides_quiet=True,
        )
        entries = (_entry("mav-hi", severity=Severity.HIGH),)
        during_quiet = datetime(2026, 8, 6, 23, 30, tzinfo=NY)

        outcome = evaluate(entries, schedule, _state(), during_quiet)

        interrupts = [d for d in outcome.deliveries if d.kind == DecisionKind.INTERRUPT]
        assert len(interrupts) == 1
        assert interrupts[0].entry_ids == ("mav-hi",)

    def test_quiet_hours_absolute_holds_then_delivers_after_quiet_ends(self) -> None:
        """US2 scenario 3: an explicit absolute-quiet-hours policy holds the
        interrupt, then delivers it at the first post-quiet evaluation."""
        schedule = AssumptionScheduleConfig(
            windows=["09:00"],
            quiet_hours=QuietHoursConfig(start="22:00", end="07:00"),
            high_overrides_quiet=False,
        )
        entries = (_entry("mav-hi", severity=Severity.HIGH),)
        during_quiet = datetime(2026, 8, 6, 23, 30, tzinfo=NY)

        held = evaluate(entries, schedule, _state(), during_quiet)

        assert not any(d.kind == DecisionKind.INTERRUPT for d in held.deliveries)
        quiet_skips = [s for s in held.skips if s.reason == SkipReason.QUIET_HOURS]
        assert len(quiet_skips) == 1
        assert quiet_skips[0].entry_ids == ("mav-hi",)
        # Not marked delivered — still due at the next evaluation.
        assert held.state_after.entry_tracking["mav-hi"].interrupt_delivered_at is None

        after_quiet = datetime(2026, 8, 7, 7, 30, tzinfo=NY)
        delivered = evaluate(entries, schedule, held.state_after, after_quiet)

        interrupts = [d for d in delivered.deliveries if d.kind == DecisionKind.INTERRUPT]
        assert len(interrupts) == 1
        assert interrupts[0].entry_ids == ("mav-hi",)

    def test_multiple_simultaneous_high_entries_coalesce_into_one_interrupt(self) -> None:
        schedule = _config()
        entries = (
            _entry("mav-hi1", severity=Severity.HIGH),
            _entry("mav-hi2", severity=Severity.HIGH),
        )

        outcome = evaluate(entries, schedule, _state(), _NOON)

        interrupts = [d for d in outcome.deliveries if d.kind == DecisionKind.INTERRUPT]
        assert len(interrupts) == 1
        assert set(interrupts[0].entry_ids) == {"mav-hi1", "mav-hi2"}
        # Combined summary: both high entries reflected in the shared count.
        assert interrupts[0].summary.counts[Severity.HIGH] == 2

        both_tracked = outcome.state_after.entry_tracking
        assert both_tracked["mav-hi1"].interrupt_delivered_at is not None
        assert both_tracked["mav-hi2"].interrupt_delivered_at is not None


class TestMixedLedgerNoCrossTalk:
    """Checkpoint (tasks.md Phase 4): a mixed ledger produces one batch
    delivery plus one interrupt delivery, with no cross-talk between the
    two mechanisms' idempotence state."""

    def test_one_medium_and_one_high_produce_batch_and_interrupt(self) -> None:
        schedule = _config()
        entries = (
            _entry("mav-med", severity=Severity.MEDIUM),
            _entry("mav-hi", severity=Severity.HIGH),
        )

        outcome = evaluate(entries, schedule, _state(), _NOON)

        assert len(outcome.deliveries) == 2
        by_kind = {d.kind: d for d in outcome.deliveries}
        batch = by_kind[DecisionKind.WINDOW_BATCH]
        interrupt = by_kind[DecisionKind.INTERRUPT]

        assert batch.entry_ids == ("mav-med",)
        assert interrupt.entry_ids == ("mav-hi",)

        # No cross-talk: the window's idempotence record covers only the
        # medium entry...
        window_key = "2026-08-06/09:00"
        assert outcome.state_after.window_decisions[window_key].entry_ids == ["mav-med"]

        # ...and the high entry's interrupt tracking is independent of the
        # medium entry's (which never gets an interrupt marker at all).
        tracking = outcome.state_after.entry_tracking
        assert tracking["mav-hi"].interrupt_delivered_at is not None
        assert tracking["mav-med"].interrupt_delivered_at is None
