"""Window-occurrence evaluation tests (tasks.md T010).

Covers occurrence due/not-yet-due, delayed-cron delivery, idempotence
(already-delivered), min-batch-size roll-forward, midnight-spanning
quiet-hours shifting (research R8), DST spring-forward gap / fall-back
non-double-delivery (research R6), and the empty-batch decision (FR-014).

All calls are direct ``evaluate(entries, schedule, state, now)`` invocations
with injected aware local datetimes — no freezegun, no ``datetime.now``
mocking (plan.md Constitution Check, Principle III).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from maverick.assumptions.models import (
    STATUS_ANSWERED,
    STATUS_OPEN,
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
    *,
    windows: list[str] | None = None,
    quiet_hours: QuietHoursConfig | None = None,
    min_batch_size: int = 1,
    max_entry_age_hours: int = 24,
) -> AssumptionScheduleConfig:
    return AssumptionScheduleConfig(
        windows=windows if windows is not None else ["09:00"],
        quiet_hours=quiet_hours,
        min_batch_size=min_batch_size,
        max_entry_age_hours=max_entry_age_hours,
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
        waived_by=None,
        waived_at=None,
        waive_reason=None,
        reconcile_status=None,
        reconciled_answer=None,
        reconcile_change_id=None,
        reconcile_reason=None,
        pending_reconcile=False,
    )


class TestOccurrenceDueness:
    def test_not_yet_due_before_window_time(self) -> None:
        schedule = _config(windows=["09:00"])
        now = datetime(2026, 8, 6, 8, 59, tzinfo=NY)

        outcome = evaluate((), schedule, _state(), now)

        assert outcome.deliveries == ()
        assert len(outcome.skips) == 1
        skip = outcome.skips[0]
        assert skip.reason == SkipReason.NOT_YET_DUE
        assert skip.occurrence is not None
        assert skip.occurrence.date == date(2026, 8, 6)
        assert skip.occurrence.window == "09:00"
        assert "2026-08-06/09:00" not in outcome.state_after.window_decisions

    def test_due_at_exact_window_time_delivers(self) -> None:
        schedule = _config(windows=["09:00"])
        entries = (_entry("mav-1"),)
        now = datetime(2026, 8, 6, 9, 0, tzinfo=NY)

        outcome = evaluate(entries, schedule, _state(), now)

        assert len(outcome.deliveries) == 1
        delivery = outcome.deliveries[0]
        assert delivery.kind == DecisionKind.WINDOW_BATCH
        assert delivery.entry_ids == ("mav-1",)
        key = "2026-08-06/09:00"
        assert outcome.state_after.window_decisions[key].outcome == "delivered"
        assert len(outcome.state_after.deliveries) == 1
        assert outcome.state_after.deliveries[0].kind == "window-batch"


class TestDelayedCron:
    def test_delivers_when_evaluated_well_after_window_time(self) -> None:
        """A machine asleep at 09:00 still delivers whenever it wakes up (FR-020)."""
        schedule = _config(windows=["09:00"])
        entries = (_entry("mav-1"),)
        now = datetime(2026, 8, 6, 14, 30, tzinfo=NY)

        outcome = evaluate(entries, schedule, _state(), now)

        assert len(outcome.deliveries) == 1
        assert outcome.deliveries[0].occurrence is not None
        assert outcome.deliveries[0].occurrence.due_at.time() == time(9, 0)


class TestAlreadyDelivered:
    def test_rerun_within_same_window_skips(self) -> None:
        schedule = _config(windows=["09:00"])
        entries = (_entry("mav-1"),)
        first_now = datetime(2026, 8, 6, 9, 5, tzinfo=NY)

        first = evaluate(entries, schedule, _state(), first_now)
        second = evaluate(entries, schedule, first.state_after, first_now + timedelta(minutes=5))

        assert second.deliveries == ()
        assert len(second.skips) == 1
        skip = second.skips[0]
        assert skip.reason == SkipReason.ALREADY_DELIVERED
        assert skip.entry_ids == ("mav-1",)
        # Idempotent: the decided record itself doesn't change either.
        key = "2026-08-06/09:00"
        assert first.state_after.window_decisions[key] == second.state_after.window_decisions[key]
        assert len(second.state_after.deliveries) == 1


class TestMinBatchSize:
    def test_skip_rolls_entries_forward_to_next_window(self) -> None:
        schedule = _config(windows=["09:00", "17:00"], min_batch_size=2)
        entries_at_first_window = (_entry("mav-1"),)

        first = evaluate(
            entries_at_first_window, schedule, _state(), datetime(2026, 8, 6, 9, 0, tzinfo=NY)
        )

        assert first.deliveries == ()
        min_skip = next(s for s in first.skips if s.reason == SkipReason.MIN_BATCH_SIZE)
        assert min_skip.entry_ids == ("mav-1",)
        key_0900 = "2026-08-06/09:00"
        assert first.state_after.window_decisions[key_0900].outcome == "skipped-min-batch"

        # A second entry accumulates; the same original entry rolls forward
        # into the 17:00 batch alongside it.
        entries_at_second_window = (_entry("mav-1"), _entry("mav-2"))
        second = evaluate(
            entries_at_second_window,
            schedule,
            first.state_after,
            datetime(2026, 8, 6, 17, 0, tzinfo=NY),
        )

        assert len(second.deliveries) == 1
        assert set(second.deliveries[0].entry_ids) == {"mav-1", "mav-2"}
        key_1700 = "2026-08-06/17:00"
        assert second.state_after.window_decisions[key_1700].outcome == "delivered"
        # The original 09:00 occurrence stays settled as skipped-min-batch —
        # it is never reconsidered.
        assert second.state_after.window_decisions[key_0900].outcome == "skipped-min-batch"


class TestEmptyBatch:
    def test_no_open_entries_records_empty_decision(self) -> None:
        schedule = _config(windows=["09:00"])
        now = datetime(2026, 8, 6, 9, 0, tzinfo=NY)

        outcome = evaluate((), schedule, _state(), now)

        assert outcome.deliveries == ()
        skip = outcome.skips[0]
        assert skip.reason == SkipReason.EMPTY_BATCH
        assert skip.entry_ids == ()
        key = "2026-08-06/09:00"
        record = outcome.state_after.window_decisions[key]
        assert record.outcome == "empty"
        assert record.entry_ids == []


class TestQuietHoursShift:
    def test_window_inside_quiet_hours_shifts_and_still_delivers_once(self) -> None:
        schedule = _config(
            windows=["23:00"], quiet_hours=QuietHoursConfig(start="22:00", end="07:00")
        )
        entries = (_entry("mav-1"),)

        # Seed continuity: settle the *previous* day's (08-05) occurrence
        # first, exactly as a daily-running cron would have — so the
        # scenario below is isolated to the single 08-06 occurrence under
        # test rather than also tripping the 08-05 catch-up.
        seeded = evaluate(entries, schedule, _state(), datetime(2026, 8, 6, 7, 30, tzinfo=NY))
        assert len(seeded.deliveries) == 1
        assert seeded.deliveries[0].occurrence is not None
        assert seeded.deliveries[0].occurrence.date == date(2026, 8, 5)

        # Evaluated after the nominal 23:00 window time but still within
        # quiet hours: due_at must have shifted to the next day's 07:00,
        # so nothing delivers yet.
        before_shift_end = evaluate(
            entries, schedule, seeded.state_after, datetime(2026, 8, 6, 23, 30, tzinfo=NY)
        )
        assert before_shift_end.deliveries == ()
        pending = next(
            s
            for s in before_shift_end.skips
            if s.occurrence and s.occurrence.date == date(2026, 8, 6)
        )
        assert pending.reason == SkipReason.NOT_YET_DUE
        assert pending.occurrence is not None
        assert pending.occurrence.due_at == datetime(2026, 8, 7, 7, 0, tzinfo=NY)

        # Evaluated after quiet hours end: the *same* occurrence (still
        # keyed to 2026-08-06, not 08-07) becomes due and delivers exactly
        # once.
        after_shift_end = evaluate(
            entries, schedule, before_shift_end.state_after, datetime(2026, 8, 7, 7, 30, tzinfo=NY)
        )
        assert len(after_shift_end.deliveries) == 1
        delivered_occ = after_shift_end.deliveries[0].occurrence
        assert delivered_occ is not None
        assert delivered_occ.date == date(2026, 8, 6)
        assert delivered_occ.due_at == datetime(2026, 8, 7, 7, 0, tzinfo=NY)
        key = "2026-08-06/23:00"
        assert after_shift_end.state_after.window_decisions[key].outcome == "delivered"

        # Re-running later the same day never re-delivers it.
        rerun = evaluate(
            entries, schedule, after_shift_end.state_after, datetime(2026, 8, 7, 8, 0, tzinfo=NY)
        )
        assert not any(
            d.occurrence and d.occurrence.date == date(2026, 8, 6) for d in rerun.deliveries
        )

    def test_window_before_quiet_hours_is_unaffected(self) -> None:
        """A window whose nominal time is outside quiet hours delivers at
        its own time, unshifted."""
        schedule = _config(
            windows=["09:00"], quiet_hours=QuietHoursConfig(start="22:00", end="07:00")
        )
        entries = (_entry("mav-1"),)

        outcome = evaluate(entries, schedule, _state(), datetime(2026, 8, 6, 9, 0, tzinfo=NY))

        assert len(outcome.deliveries) == 1
        occ = outcome.deliveries[0].occurrence
        assert occ is not None
        assert occ.due_at == datetime(2026, 8, 6, 9, 0, tzinfo=NY)


class TestQuietHoursHoldBacklog:
    """FR-004/FR-020: a window batch is a medium/legacy delivery, so it is
    held whenever *now* falls inside quiet hours — even when the window's
    own configured time sits safely outside them. Shifting ``due_at`` at
    occurrence-build time (``TestQuietHoursShift``) only covers windows
    whose configured time is itself inside quiet hours; a backlogged
    evaluation (laptop asleep, cron catching up) needs this second gate.
    """

    _QUIET = QuietHoursConfig(start="22:00", end="07:00")

    # Aged ~15h at the 23:00 tick and ~23.5h at the 07:30 one: comfortably
    # inside the default 24h ``max_entry_age_hours`` throughout, so these
    # scenarios stay isolated to window batching and never cross into US4's
    # max-age escalation (covered in test_evaluate_escalation.py).
    _CREATED_AT = "2026-08-06T12:00:00Z"

    def test_backlogged_batch_is_held_when_evaluated_inside_quiet_hours(self) -> None:
        schedule = _config(windows=["09:00"], quiet_hours=self._QUIET)
        entries = (_entry("mav-1", created_at=self._CREATED_AT),)
        # Machine asleep all day; the first evaluation lands at 23:00, deep
        # inside quiet hours. The 09:00 batch must not push at 23:00.
        now = datetime(2026, 8, 6, 23, 0, tzinfo=NY)

        outcome = evaluate(entries, schedule, _state(), now)

        assert outcome.deliveries == ()
        quiet_skips = [s for s in outcome.skips if s.reason == SkipReason.QUIET_HOURS]
        assert len(quiet_skips) == 1
        assert quiet_skips[0].occurrence is not None
        assert quiet_skips[0].occurrence.date == date(2026, 8, 6)
        assert quiet_skips[0].entry_ids == ("mav-1",)
        # No decision recorded: the occurrence stays due (FR-020) and no
        # audit record claims a delivery that never happened.
        assert "2026-08-06/09:00" not in outcome.state_after.window_decisions
        assert outcome.state_after.deliveries == []

    def test_held_batch_delivers_exactly_once_after_quiet_hours_end(self) -> None:
        schedule = _config(windows=["09:00"], quiet_hours=self._QUIET)
        entries = (_entry("mav-1", created_at=self._CREATED_AT),)

        held = evaluate(entries, schedule, _state(), datetime(2026, 8, 6, 23, 0, tzinfo=NY))
        assert held.deliveries == ()

        # 07:30 — the first evaluation quiet hours (22:00-07:00) permit.
        after_quiet = evaluate(
            entries, schedule, held.state_after, datetime(2026, 8, 7, 7, 30, tzinfo=NY)
        )
        batches = [d for d in after_quiet.deliveries if d.kind == DecisionKind.WINDOW_BATCH]
        assert len(batches) == 1
        assert batches[0].entry_ids == ("mav-1",)
        assert batches[0].occurrence is not None
        # The *held* occurrence delivers — not a freshly-minted one.
        assert batches[0].occurrence.date == date(2026, 8, 6)
        key = "2026-08-06/09:00"
        assert after_quiet.state_after.window_decisions[key].outcome == "delivered"

        # Exactly once: a later evaluation the same morning re-skips it.
        rerun = evaluate(
            entries, schedule, after_quiet.state_after, datetime(2026, 8, 7, 7, 45, tzinfo=NY)
        )
        assert [d for d in rerun.deliveries if d.kind == DecisionKind.WINDOW_BATCH] == []
        assert len(rerun.state_after.deliveries) == 1

    def test_quiet_hours_suppress_deliveries_not_decisions(self) -> None:
        """An occurrence that would deliver nothing anyway still settles
        inside quiet hours — quiet hours gate pushes, not bookkeeping."""
        schedule = _config(windows=["09:00"], quiet_hours=self._QUIET)

        outcome = evaluate((), schedule, _state(), datetime(2026, 8, 6, 23, 0, tzinfo=NY))

        assert outcome.deliveries == ()
        assert outcome.state_after.window_decisions["2026-08-06/09:00"].outcome == "empty"
        assert not any(s.reason == SkipReason.QUIET_HOURS for s in outcome.skips)

    def test_fresh_state_does_not_catch_up_a_never_evaluated_prior_occurrence(self) -> None:
        """The catch-up path reclaims only an occurrence this scheduler
        actually held, never one nobody ever evaluated — otherwise a
        brand-new schedule's first run double-fires (yesterday's batch plus
        today's)."""
        # `load_state()` stamps a first-ever run's empty state with *now*.
        now = datetime(2026, 8, 6, 7, 30, tzinfo=NY)
        fresh = DeliveryState(updated_at="2026-08-06T11:30:00Z")
        schedule = _config(windows=["09:00"], quiet_hours=self._QUIET)
        entries = (_entry("mav-1", created_at="2026-08-06T06:00:00Z"),)

        outcome = evaluate(entries, schedule, fresh, now)

        assert outcome.deliveries == ()
        assert "2026-08-05/09:00" not in outcome.state_after.window_decisions


class TestDaylightSaving:
    """2026-03-08: US Eastern spring-forward (02:00 -> 03:00, 02:30 does
    not exist). 2026-11-01: US Eastern fall-back (01:00-02:00 repeats)."""

    def test_spring_forward_gap_resolves_to_a_real_instant(self) -> None:
        schedule = _config(windows=["02:30"])
        entries = (_entry("mav-1"),)
        # A real, valid instant shortly after the gap closes.
        now = datetime(2026, 3, 8, 3, 30, tzinfo=NY)

        outcome = evaluate(entries, schedule, _state(), now)

        assert len(outcome.deliveries) == 1
        due_at = outcome.deliveries[0].occurrence.due_at  # type: ignore[union-attr]
        # due_at must denote a real instant: round-tripping through UTC
        # reproduces the identical local wall time (PEP 495).
        assert due_at.astimezone(UTC).astimezone(NY) == due_at
        assert due_at <= now

    def test_spring_forward_gap_not_yet_due_before_transition(self) -> None:
        schedule = _config(windows=["02:30"])
        entries = (_entry("mav-1"),)
        now = datetime(2026, 3, 8, 1, 0, tzinfo=NY)

        outcome = evaluate(entries, schedule, _state(), now)

        assert outcome.deliveries == ()
        assert outcome.skips[0].reason == SkipReason.NOT_YET_DUE

    def test_fall_back_ambiguous_hour_does_not_double_deliver(self) -> None:
        schedule = _config(windows=["01:30"])
        entries = (_entry("mav-1"),)
        first_pass = datetime(2026, 11, 1, 1, 35, tzinfo=NY, fold=0)

        first = evaluate(entries, schedule, _state(), first_pass)
        assert len(first.deliveries) == 1

        # The same wall-clock instant occurs a second time (fold=1, an hour
        # later in absolute UTC terms) — must not re-deliver.
        second_pass = datetime(2026, 11, 1, 1, 35, tzinfo=NY, fold=1)
        second = evaluate(entries, schedule, first.state_after, second_pass)

        assert second.deliveries == ()
        assert len(second.skips) == 1
        assert second.skips[0].reason == SkipReason.ALREADY_DELIVERED
        assert len(second.state_after.deliveries) == 1
