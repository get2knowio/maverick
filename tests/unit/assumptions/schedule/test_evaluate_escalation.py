"""Escalation, backoff, and auto-waive evaluation tests (tasks.md T025, T026).

Covers US4 (age-based escalation and explicit expiry): max-age escalation
for medium entries bypassing min-batch-size (FR-006, spec.md US4 scenario
1), exactly-once escalation (FR-007), backoff-ladder re-notification for
high entries with the last rung repeating (FR-007), low entries never
escalating to delivery (clarification Q2), quiet-hours gating shared with
interrupts (FR-004/FR-006), and opt-in auto-waive candidates for aged low
entries (FR-015).

Direct ``evaluate(entries, schedule, state, now)`` calls with injected
aware local datetimes only — no freezegun, no ``datetime.now`` mocking
(plan.md Constitution Check, Principle III).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from maverick.assumptions.models import (
    STATUS_OPEN,
    AssumptionRecord,
    AssumptionReportEntry,
    Severity,
)
from maverick.assumptions.schedule.evaluate import evaluate
from maverick.assumptions.schedule.models import DecisionKind, SkipReason
from maverick.assumptions.schedule.state import DeliveryState, EntryTrackingRecord
from maverick.config import AssumptionScheduleConfig, AutoWaivePolicyConfig, QuietHoursConfig

NY = ZoneInfo("America/New_York")


def _iso(dt: datetime) -> str:
    """UTC ISO-8601 ``...Z`` timestamp, matching bd's own ``created_at`` shape."""
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _config(
    *,
    windows: list[str] | None = None,
    min_batch_size: int = 1,
    max_entry_age_hours: int = 24,
    renotify_backoff_hours: list[float] | None = None,
    quiet_hours: QuietHoursConfig | None = None,
    high_overrides_quiet: bool = True,
    auto_waive_low: AutoWaivePolicyConfig | None = None,
) -> AssumptionScheduleConfig:
    return AssumptionScheduleConfig(
        windows=windows if windows is not None else ["09:00"],
        min_batch_size=min_batch_size,
        max_entry_age_hours=max_entry_age_hours,
        renotify_backoff_hours=(
            renotify_backoff_hours
            if renotify_backoff_hours is not None
            else [4.0, 8.0, 16.0, 24.0]
        ),
        quiet_hours=quiet_hours,
        high_overrides_quiet=high_overrides_quiet,
        auto_waive_low=auto_waive_low,
    )


def _state(**overrides: object) -> DeliveryState:
    defaults: dict[str, object] = {"updated_at": "2026-08-01T00:00:00Z"}
    defaults.update(overrides)
    return DeliveryState(**defaults)  # type: ignore[arg-type]


def _entry(
    bead_id: str,
    *,
    severity: Severity = Severity.MEDIUM,
    status: str = STATUS_OPEN,
    owner_spec: str = "054-assumption-batch-scheduler",
    created_at: str | None = None,
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
            is_legacy=False,
            created_at=created_at,
        ),
        final_answer=None,
        waived_by=None,
        waived_at=None,
        waive_reason=None,
        reconcile_status=None,
        reconciled_answer=None,
        reconcile_change_id=None,
        reconcile_reason=None,
        pending_reconcile=False,
    )


_FAR_PAST = datetime(2026, 8, 1, 0, 0, tzinfo=NY)


class TestMediumMaxAgeEscalation:
    """FR-006/FR-007, US4 acceptance scenario 1."""

    def test_aged_medium_below_min_batch_escalates_bypassing_min_batch_size(self) -> None:
        schedule = _config(windows=["09:00"], min_batch_size=5, max_entry_age_hours=24)
        entries = (_entry("mav-1", severity=Severity.MEDIUM, created_at=_iso(_FAR_PAST)),)
        now = datetime(2026, 8, 6, 9, 5, tzinfo=NY)

        outcome = evaluate(entries, schedule, _state(), now)

        # The window itself still rolls the entry forward (min_batch_size
        # not met)...
        min_batch_skips = [s for s in outcome.skips if s.reason == SkipReason.MIN_BATCH_SIZE]
        assert len(min_batch_skips) == 1
        assert min_batch_skips[0].entry_ids == ("mav-1",)

        # ...but escalation delivers it anyway, bypassing that rule.
        escalations = [d for d in outcome.deliveries if d.kind == DecisionKind.ESCALATION]
        assert len(escalations) == 1
        assert escalations[0].entry_ids == ("mav-1",)
        assert escalations[0].occurrence is None

        tracked = outcome.state_after.entry_tracking["mav-1"]
        assert tracked.escalation_delivered_at is not None

    def test_medium_escalates_exactly_once(self) -> None:
        """FR-007: an escalated medium entry does not re-notify."""
        schedule = _config(windows=["09:00"], min_batch_size=5, max_entry_age_hours=24)
        entries = (_entry("mav-1", severity=Severity.MEDIUM, created_at=_iso(_FAR_PAST)),)
        first_now = datetime(2026, 8, 6, 9, 5, tzinfo=NY)

        first = evaluate(entries, schedule, _state(), first_now)
        assert any(d.kind == DecisionKind.ESCALATION for d in first.deliveries)

        second = evaluate(entries, schedule, first.state_after, first_now + timedelta(days=10))

        assert not any(d.kind == DecisionKind.ESCALATION for d in second.deliveries)

    def test_entry_delivered_via_window_batch_this_run_is_not_also_escalated(self) -> None:
        """An entry delivered on time via its window batch is excluded from
        escalation in the *same* evaluation — escalation is the safety net
        for entries the batching rules would otherwise starve, not a
        second delivery for one that just went out normally."""
        schedule = _config(windows=["09:00"], min_batch_size=1, max_entry_age_hours=24)
        entries = (_entry("mav-1", severity=Severity.MEDIUM, created_at=_iso(_FAR_PAST)),)
        now = datetime(2026, 8, 6, 9, 5, tzinfo=NY)

        outcome = evaluate(entries, schedule, _state(), now)

        assert len(outcome.deliveries) == 1
        assert outcome.deliveries[0].kind == DecisionKind.WINDOW_BATCH
        assert not any(d.kind == DecisionKind.ESCALATION for d in outcome.deliveries)


class TestHighBackoffRenotify:
    """FR-007: an unanswered high entry past max age re-notifies on the
    configured backoff ladder, the last rung repeating indefinitely."""

    def _prior_state_with_interrupted_high(self, bead_id: str) -> DeliveryState:
        return _state(
            entry_tracking={
                bead_id: EntryTrackingRecord(
                    first_seen=_iso(_FAR_PAST),
                    severity="high",
                    interrupt_delivered_at=_iso(_FAR_PAST),
                )
            }
        )

    def test_renotify_fires_at_ladder_spacing_and_repeats_last_rung(self) -> None:
        schedule = _config(
            windows=["09:00"], max_entry_age_hours=1, renotify_backoff_hours=[4.0, 8.0]
        )
        entries = (_entry("mav-hi", severity=Severity.HIGH, created_at=_iso(_FAR_PAST)),)
        state = self._prior_state_with_interrupted_high("mav-hi")
        t0 = datetime(2026, 8, 6, 9, 0, tzinfo=NY)

        # First renotify: due immediately (next_renotify_at was unset).
        first = evaluate(entries, schedule, state, t0)
        renotifies = [d for d in first.deliveries if d.kind == DecisionKind.RENOTIFY]
        assert len(renotifies) == 1
        assert renotifies[0].entry_ids == ("mav-hi",)
        tracked1 = first.state_after.entry_tracking["mav-hi"]
        assert tracked1.renotify_count == 1
        assert tracked1.next_renotify_at is not None
        assert _parse(tracked1.next_renotify_at) == (t0 + timedelta(hours=4)).astimezone(UTC)

        # Too early for the next rung: nothing fires.
        second = evaluate(entries, schedule, first.state_after, t0 + timedelta(hours=2))
        assert not any(d.kind == DecisionKind.RENOTIFY for d in second.deliveries)
        assert second.state_after.entry_tracking["mav-hi"].renotify_count == 1

        # Second renotify: due at/after the first rung (4h); spacing to the
        # next one uses the second rung (8h).
        t1 = t0 + timedelta(hours=4, minutes=1)
        third = evaluate(entries, schedule, first.state_after, t1)
        renotifies3 = [d for d in third.deliveries if d.kind == DecisionKind.RENOTIFY]
        assert len(renotifies3) == 1
        tracked3 = third.state_after.entry_tracking["mav-hi"]
        assert tracked3.renotify_count == 2
        assert tracked3.next_renotify_at is not None
        assert _parse(tracked3.next_renotify_at) == (t1 + timedelta(hours=8)).astimezone(UTC)

        # Third renotify: the ladder is exhausted (2 rungs); the last rung
        # (8h) repeats indefinitely.
        t2 = _parse(tracked3.next_renotify_at).astimezone(NY) + timedelta(minutes=1)
        fourth = evaluate(entries, schedule, third.state_after, t2)
        renotifies4 = [d for d in fourth.deliveries if d.kind == DecisionKind.RENOTIFY]
        assert len(renotifies4) == 1
        tracked4 = fourth.state_after.entry_tracking["mav-hi"]
        assert tracked4.renotify_count == 3
        assert tracked4.next_renotify_at is not None
        assert _parse(tracked4.next_renotify_at) == (t2 + timedelta(hours=8)).astimezone(UTC)

    def test_high_not_yet_interrupted_is_not_renotify_eligible(self) -> None:
        """A high entry with no prior interrupt delivery never renotifies —
        it's still on the ordinary interrupt path (T020), not this one."""
        schedule = _config(windows=["09:00"], max_entry_age_hours=1)
        entries = (_entry("mav-hi", severity=Severity.HIGH, created_at=_iso(_FAR_PAST)),)
        now = datetime(2026, 8, 6, 9, 0, tzinfo=NY)

        outcome = evaluate(entries, schedule, _state(), now)

        assert not any(d.kind == DecisionKind.RENOTIFY for d in outcome.deliveries)
        assert any(d.kind == DecisionKind.INTERRUPT for d in outcome.deliveries)

    def test_renotify_freshly_interrupted_this_evaluation_does_not_also_fire(self) -> None:
        """An entry interrupted for the first time *in this very call* must
        not simultaneously renotify — ``prior_tracking`` is the pre-call
        snapshot, so a fresh interrupt is never renotify-eligible until a
        later evaluation."""
        schedule = _config(windows=["09:00"], max_entry_age_hours=1)
        entries = (_entry("mav-hi", severity=Severity.HIGH, created_at=_iso(_FAR_PAST)),)
        now = datetime(2026, 8, 6, 9, 0, tzinfo=NY)

        outcome = evaluate(entries, schedule, _state(), now)

        interrupts = [d for d in outcome.deliveries if d.kind == DecisionKind.INTERRUPT]
        renotifies = [d for d in outcome.deliveries if d.kind == DecisionKind.RENOTIFY]
        assert len(interrupts) == 1
        assert renotifies == []


class TestLowNeverEscalatesToDelivery:
    """Clarification Q2: low never escalates to delivery — its only aging
    path is the opt-in auto-waive policy."""

    def test_aged_low_entry_never_produces_a_delivery(self) -> None:
        schedule = _config(windows=["09:00"], max_entry_age_hours=1)
        entries = (_entry("mav-lo", severity=Severity.LOW, created_at=_iso(_FAR_PAST)),)
        now = datetime(2026, 8, 6, 9, 0, tzinfo=NY)

        outcome = evaluate(entries, schedule, _state(), now)

        assert outcome.deliveries == ()
        low_skips = [s for s in outcome.skips if s.reason == SkipReason.LOW_NEVER_PROACTIVE]
        assert len(low_skips) == 1
        assert low_skips[0].entry_ids == ("mav-lo",)


class TestMediumEscalationQuietHoursGating:
    """Quiet hours gate escalation by *severity*, not by
    ``high_overrides_quiet`` (FR-004, FR-006, contracts/config-schema.md:
    the flag gates high-severity interrupts and high-severity
    re-notifications, and only those). A medium entry's escalation is
    therefore always held until quiet hours end, whichever way the override
    is configured — an aged medium entry must never fire an urgent push at
    03:00.
    """

    def _schedule(self, *, high_overrides_quiet: bool) -> AssumptionScheduleConfig:
        return _config(
            windows=["09:00"],
            min_batch_size=5,
            max_entry_age_hours=1,
            quiet_hours=QuietHoursConfig(start="22:00", end="07:00"),
            high_overrides_quiet=high_overrides_quiet,
        )

    def test_absolute_quiet_hours_hold_escalation_then_deliver_after_quiet_ends(self) -> None:
        schedule = self._schedule(high_overrides_quiet=False)
        entries = (_entry("mav-1", severity=Severity.MEDIUM, created_at=_iso(_FAR_PAST)),)
        during_quiet = datetime(2026, 8, 6, 23, 30, tzinfo=NY)

        held = evaluate(entries, schedule, _state(), during_quiet)

        assert not any(d.kind == DecisionKind.ESCALATION for d in held.deliveries)
        # Entry-scoped (`occurrence is None`) — the window-scoped quiet-hours
        # hold is a separate skip with its own occurrence attached.
        quiet_skips = [
            s for s in held.skips if s.reason == SkipReason.QUIET_HOURS and s.occurrence is None
        ]
        assert len(quiet_skips) == 1
        assert quiet_skips[0].entry_ids == ("mav-1",)
        assert held.state_after.entry_tracking["mav-1"].escalation_delivered_at is None

        after_quiet = datetime(2026, 8, 7, 7, 30, tzinfo=NY)
        delivered = evaluate(entries, schedule, held.state_after, after_quiet)

        escalations = [d for d in delivered.deliveries if d.kind == DecisionKind.ESCALATION]
        assert len(escalations) == 1
        assert escalations[0].entry_ids == ("mav-1",)

    def test_default_override_still_holds_medium_escalation_during_quiet_hours(self) -> None:
        """``high_overrides_quiet=True`` (the default) must not push a
        *medium* escalation through quiet hours — it governs high severity
        only. This is the 03:00 urgent-push regression."""
        schedule = self._schedule(high_overrides_quiet=True)
        entries = (_entry("mav-1", severity=Severity.MEDIUM, created_at=_iso(_FAR_PAST)),)
        during_quiet = datetime(2026, 8, 6, 23, 30, tzinfo=NY)

        outcome = evaluate(entries, schedule, _state(), during_quiet)

        assert not any(d.kind == DecisionKind.ESCALATION for d in outcome.deliveries)
        quiet_skips = [
            s for s in outcome.skips if s.reason == SkipReason.QUIET_HOURS and s.occurrence is None
        ]
        assert len(quiet_skips) == 1
        assert quiet_skips[0].entry_ids == ("mav-1",)
        assert "quiet hours" in quiet_skips[0].rule
        # Nothing stamped: the entry is still escalation-eligible.
        assert outcome.state_after.entry_tracking["mav-1"].escalation_delivered_at is None

    def test_held_medium_escalation_delivers_exactly_once_after_quiet_hours_end(self) -> None:
        """FR-020: the held escalation becomes due at the first permissible
        evaluation — and, per FR-007, fires there exactly once."""
        schedule = self._schedule(high_overrides_quiet=True)
        entries = (_entry("mav-1", severity=Severity.MEDIUM, created_at=_iso(_FAR_PAST)),)

        held = evaluate(entries, schedule, _state(), datetime(2026, 8, 6, 23, 30, tzinfo=NY))
        assert not any(d.kind == DecisionKind.ESCALATION for d in held.deliveries)

        # 07:30 — the first evaluation quiet hours (22:00-07:00) permit.
        delivered = evaluate(
            entries, schedule, held.state_after, datetime(2026, 8, 7, 7, 30, tzinfo=NY)
        )
        escalations = [d for d in delivered.deliveries if d.kind == DecisionKind.ESCALATION]
        assert len(escalations) == 1
        assert escalations[0].entry_ids == ("mav-1",)
        assert delivered.state_after.entry_tracking["mav-1"].escalation_delivered_at is not None

        rerun = evaluate(
            entries, schedule, delivered.state_after, datetime(2026, 8, 7, 8, 0, tzinfo=NY)
        )
        assert not any(d.kind == DecisionKind.ESCALATION for d in rerun.deliveries)


class TestHighSeverityQuietHoursOverride:
    """``high_overrides_quiet`` gates high-severity interrupts and
    high-severity re-notifications identically, and *only* those
    (contracts/config-schema.md). Default ``True`` => both punch through
    quiet hours; ``False`` => quiet hours are absolute and both are held
    until they end."""

    def _schedule(self, *, high_overrides_quiet: bool) -> AssumptionScheduleConfig:
        return _config(
            windows=["09:00"],
            min_batch_size=5,
            max_entry_age_hours=1,
            renotify_backoff_hours=[4.0],
            quiet_hours=QuietHoursConfig(start="22:00", end="07:00"),
            high_overrides_quiet=high_overrides_quiet,
        )

    def _interrupted_state(self, bead_id: str) -> DeliveryState:
        return _state(
            entry_tracking={
                bead_id: EntryTrackingRecord(
                    first_seen=_iso(_FAR_PAST),
                    severity="high",
                    interrupt_delivered_at=_iso(_FAR_PAST),
                )
            }
        )

    def test_default_override_delivers_high_interrupt_through_quiet_hours(self) -> None:
        schedule = self._schedule(high_overrides_quiet=True)
        entries = (_entry("mav-hi", severity=Severity.HIGH, created_at=_iso(_FAR_PAST)),)

        outcome = evaluate(entries, schedule, _state(), datetime(2026, 8, 6, 23, 30, tzinfo=NY))

        interrupts = [d for d in outcome.deliveries if d.kind == DecisionKind.INTERRUPT]
        assert len(interrupts) == 1
        assert interrupts[0].entry_ids == ("mav-hi",)
        assert outcome.state_after.entry_tracking["mav-hi"].interrupt_delivered_at is not None

    def test_absolute_quiet_hours_hold_high_interrupt_until_quiet_ends(self) -> None:
        schedule = self._schedule(high_overrides_quiet=False)
        entries = (_entry("mav-hi", severity=Severity.HIGH, created_at=_iso(_FAR_PAST)),)

        held = evaluate(entries, schedule, _state(), datetime(2026, 8, 6, 23, 30, tzinfo=NY))

        assert not any(d.kind == DecisionKind.INTERRUPT for d in held.deliveries)
        quiet_skips = [
            s for s in held.skips if s.reason == SkipReason.QUIET_HOURS and s.occurrence is None
        ]
        assert len(quiet_skips) == 1
        assert quiet_skips[0].entry_ids == ("mav-hi",)
        assert held.state_after.entry_tracking["mav-hi"].interrupt_delivered_at is None

        delivered = evaluate(
            entries, schedule, held.state_after, datetime(2026, 8, 7, 7, 30, tzinfo=NY)
        )
        interrupts = [d for d in delivered.deliveries if d.kind == DecisionKind.INTERRUPT]
        assert len(interrupts) == 1
        assert interrupts[0].entry_ids == ("mav-hi",)

    def test_default_override_delivers_high_renotify_through_quiet_hours(self) -> None:
        schedule = self._schedule(high_overrides_quiet=True)
        entries = (_entry("mav-hi", severity=Severity.HIGH, created_at=_iso(_FAR_PAST)),)

        outcome = evaluate(
            entries,
            schedule,
            self._interrupted_state("mav-hi"),
            datetime(2026, 8, 6, 23, 30, tzinfo=NY),
        )

        renotifies = [d for d in outcome.deliveries if d.kind == DecisionKind.RENOTIFY]
        assert len(renotifies) == 1
        assert renotifies[0].entry_ids == ("mav-hi",)
        assert outcome.state_after.entry_tracking["mav-hi"].renotify_count == 1

    def test_absolute_quiet_hours_hold_high_renotify_until_quiet_ends(self) -> None:
        schedule = self._schedule(high_overrides_quiet=False)
        entries = (_entry("mav-hi", severity=Severity.HIGH, created_at=_iso(_FAR_PAST)),)

        held = evaluate(
            entries,
            schedule,
            self._interrupted_state("mav-hi"),
            datetime(2026, 8, 6, 23, 30, tzinfo=NY),
        )

        assert not any(d.kind == DecisionKind.RENOTIFY for d in held.deliveries)
        quiet_skips = [
            s for s in held.skips if s.reason == SkipReason.QUIET_HOURS and s.occurrence is None
        ]
        assert len(quiet_skips) == 1
        assert quiet_skips[0].entry_ids == ("mav-hi",)
        tracked = held.state_after.entry_tracking["mav-hi"]
        assert tracked.renotify_count == 0
        assert tracked.next_renotify_at is None

        delivered = evaluate(
            entries, schedule, held.state_after, datetime(2026, 8, 7, 7, 30, tzinfo=NY)
        )
        renotifies = [d for d in delivered.deliveries if d.kind == DecisionKind.RENOTIFY]
        assert len(renotifies) == 1
        assert delivered.state_after.entry_tracking["mav-hi"].renotify_count == 1


# --- T026: auto-waive -------------------------------------------------------


_AGED_LOW_CREATED_AT = _iso(_FAR_PAST)


class TestAutoWaivePolicy:
    """FR-015: opt-in auto-waive of aged low-severity entries."""

    def test_policy_absent_never_yields_auto_waive_decision(self) -> None:
        schedule = _config(windows=["09:00"], auto_waive_low=None)
        entries = (_entry("mav-lo", severity=Severity.LOW, created_at=_AGED_LOW_CREATED_AT),)

        outcome = evaluate(entries, schedule, _state(), datetime(2026, 8, 6, 9, 0, tzinfo=NY))

        assert outcome.auto_waives == ()

    def test_policy_disabled_never_yields_auto_waive_decision(self) -> None:
        policy = AutoWaivePolicyConfig(enabled=False)
        schedule = _config(windows=["09:00"], auto_waive_low=policy)
        entries = (_entry("mav-lo", severity=Severity.LOW, created_at=_AGED_LOW_CREATED_AT),)

        outcome = evaluate(entries, schedule, _state(), datetime(2026, 8, 6, 9, 0, tzinfo=NY))

        assert outcome.auto_waives == ()

    def test_enabled_aged_low_yields_decision_with_full_rationale_text(self) -> None:
        policy = AutoWaivePolicyConfig(
            enabled=True, after_hours=48, rationale="stale low-severity noise, accepted risk"
        )
        schedule = _config(windows=["09:00"], auto_waive_low=policy)
        entries = (_entry("mav-lo", severity=Severity.LOW, created_at=_AGED_LOW_CREATED_AT),)

        outcome = evaluate(entries, schedule, _state(), datetime(2026, 8, 6, 9, 0, tzinfo=NY))

        assert len(outcome.auto_waives) == 1
        decision = outcome.auto_waives[0]
        assert decision.entry_id == "mav-lo"
        assert "48h" in decision.reason_text
        assert "stale low-severity noise, accepted risk" in decision.reason_text

    def test_enabled_not_yet_aged_past_threshold_yields_no_decision(self) -> None:
        policy = AutoWaivePolicyConfig(
            enabled=True, after_hours=100_000, rationale="not aged enough"
        )
        schedule = _config(windows=["09:00"], auto_waive_low=policy)
        entries = (_entry("mav-lo", severity=Severity.LOW, created_at=_AGED_LOW_CREATED_AT),)

        outcome = evaluate(entries, schedule, _state(), datetime(2026, 8, 6, 9, 0, tzinfo=NY))

        assert outcome.auto_waives == ()

    def test_medium_and_high_entries_are_never_auto_waive_candidates(self) -> None:
        """Auto-waive is a low-only path — medium/high age via
        escalation/renotify instead, never auto-waive."""
        policy = AutoWaivePolicyConfig(
            enabled=True, after_hours=1, rationale="should never apply to non-low"
        )
        schedule = _config(windows=["09:00"], max_entry_age_hours=100_000, auto_waive_low=policy)
        entries = (
            _entry("mav-med", severity=Severity.MEDIUM, created_at=_AGED_LOW_CREATED_AT),
            _entry("mav-hi", severity=Severity.HIGH, created_at=_AGED_LOW_CREATED_AT),
        )

        outcome = evaluate(entries, schedule, _state(), datetime(2026, 8, 6, 9, 0, tzinfo=NY))

        assert outcome.auto_waives == ()
