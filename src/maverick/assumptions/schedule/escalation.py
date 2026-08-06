"""Age-driven safety nets: escalation, backoff re-notification, auto-waive.

Three policies for entries the normal paths have left sitting (US4):

* :func:`process_medium_escalations` — a medium entry past
  ``max_entry_age_hours`` bypasses windows and ``min_batch_size`` entirely,
  exactly once (FR-006/FR-007).
* :func:`process_high_renotify` — an already-interrupted high entry still
  open past that age keeps re-notifying on the configured backoff ladder,
  indefinitely (FR-007).
* :func:`process_auto_waives` — aged low entries, which have no delivery
  path at all, under an opt-in waive policy (FR-015, research R10).

The first two differ from each other, and from
:func:`~maverick.assumptions.schedule.severity.process_high_interrupts`,
only in policy; all three share
:func:`~maverick.assumptions.schedule.decisions.process_entry_decisions`.
Note the quiet-hours asymmetry between them: escalation is medium-severity
and is therefore held **unconditionally**, while re-notification is
high-severity and obeys ``high_overrides_quiet`` (FR-004).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta

from maverick.assumptions.models import AssumptionReportEntry
from maverick.assumptions.schedule.decisions import (
    DecisionSink,
    EntryDecisionSpec,
    process_entry_decisions,
)
from maverick.assumptions.schedule.models import (
    AutoWaiveDecision,
    BatchSummary,
    DecisionKind,
    format_utc,
    parse_utc,
)
from maverick.assumptions.schedule.state import EntryTrackingRecord
from maverick.assumptions.schedule.tracking import entry_age_hours
from maverick.assumptions.schedule.windows import (
    high_severity_held_by_quiet_hours,
    in_quiet_hours_now,
)
from maverick.config import AssumptionScheduleConfig


def process_medium_escalations(
    *,
    medium_entries: Sequence[AssumptionReportEntry],
    already_batched_ids: frozenset[str],
    tracking: dict[str, EntryTrackingRecord],
    schedule: AssumptionScheduleConfig,
    summary: BatchSummary,
    now: datetime,
    sink: DecisionSink,
) -> None:
    """Decide max-age escalation for medium entries (US4, FR-006/FR-007).

    An open medium entry (including legacy entries, already synthesized as
    medium — FR-019) whose age exceeds ``schedule.max_entry_age_hours``
    escalates regardless of ``min_batch_size`` and window rules, bypassing
    both entirely (FR-006) — this is the safety net that stops a
    perpetually-below-threshold batch from starving. Idempotence is
    per-entry via :attr:`EntryTrackingRecord.escalation_delivered_at`: an
    entry escalates *exactly once* (FR-007) and never re-notifies
    afterward, unlike the high-severity backoff ladder in
    :func:`process_high_renotify`. An entry already covered by this same
    evaluation's window-batch delivery (*already_batched_ids*) is skipped
    here — it was just delivered on time.

    Quiet-hours gating is **unconditional** here (FR-004, research R8), and
    this is where it differs from
    :func:`~maverick.assumptions.schedule.severity.process_high_interrupts`:
    these are medium-severity entries, and ``high_overrides_quiet`` gates
    high severity only (contracts/config-schema.md), so an escalation
    reached inside quiet hours is always held — nothing is stamped, leaving
    the entry eligible until the first evaluation after quiet hours end.

    Mutates *tracking* and *sink* in place — the same deliberate, scoped
    exception to this package's functional style used throughout its
    decision-producing helpers.
    """
    delivered_at = format_utc(now)

    def is_due(entry: AssumptionReportEntry) -> bool:
        bead_id = entry.record.bead_id
        if bead_id in already_batched_ids:
            return False  # delivered on time via this evaluation's window batch

        record = tracking.get(bead_id)
        if record is not None and record.escalation_delivered_at is not None:
            return False  # escalates exactly once (FR-007)

        return entry_age_hours(entry, tracking, now) >= schedule.max_entry_age_hours

    def stamp(bead_id: str, record: EntryTrackingRecord) -> EntryTrackingRecord:
        return record.model_copy(update={"escalation_delivered_at": delivered_at})

    process_entry_decisions(
        EntryDecisionSpec(
            kind=DecisionKind.ESCALATION,
            due_rule=f"max entry age ({schedule.max_entry_age_hours}h) exceeded; escalated",
            held_rule=(
                "escalation held: quiet hours suppress medium-severity delivery "
                "(high_overrides_quiet governs high severity only)"
            ),
            is_due=is_due,
            # Medium severity: quiet hours are absolute regardless of
            # `high_overrides_quiet`, which governs high severity only.
            held_by_quiet_hours=in_quiet_hours_now(now, schedule.quiet_hours),
            stamp=stamp,
        ),
        entries=medium_entries,
        tracking=tracking,
        summary=summary,
        now=now,
        sink=sink,
    )


def process_high_renotify(
    *,
    high_entries: Sequence[AssumptionReportEntry],
    prior_tracking: dict[str, EntryTrackingRecord],
    tracking: dict[str, EntryTrackingRecord],
    schedule: AssumptionScheduleConfig,
    summary: BatchSummary,
    now: datetime,
    sink: DecisionSink,
) -> None:
    """Decide backoff-ladder re-notification for high entries (US4, FR-007).

    A high entry that was already interrupted *as of a prior evaluation*
    (``prior_tracking[bead_id].interrupt_delivered_at`` set — never this
    call's own fresh interrupt, see the ``prior_tracking`` snapshot taken
    in :func:`~maverick.assumptions.schedule.evaluate.evaluate`) and remains
    open past ``max_entry_age_hours`` re-notifies rather than staying
    silent, spaced by ``schedule.renotify_backoff_hours`` — the last rung
    repeats indefinitely once the ladder is exhausted. Unlike medium
    escalation, this never stops firing while the entry stays open and
    unanswered.

    Rung selection: the *Nth* re-notification (0-indexed by the entry's
    ``renotify_count`` going in) schedules its successor
    ``schedule.renotify_backoff_hours[min(N, len(ladder) - 1)]`` hours
    later — so a ladder of ``[4, 8]`` re-notifies after 4h, then 8h, then
    8h again, forever.

    Quiet-hours gating mirrors
    :func:`~maverick.assumptions.schedule.severity.process_high_interrupts`
    exactly (both read
    :func:`~maverick.assumptions.schedule.windows.high_severity_held_by_quiet_hours`
    — ``high_overrides_quiet`` gates the two identically): a held
    re-notification leaves ``next_renotify_at`` untouched, so it is still
    due at the first evaluation after quiet hours end.

    Mutates *tracking* and *sink* in place — the same deliberate, scoped
    exception to this package's functional style used throughout its
    decision-producing helpers.
    """
    ladder = schedule.renotify_backoff_hours

    def is_due(entry: AssumptionReportEntry) -> bool:
        prior = prior_tracking.get(entry.record.bead_id)
        if prior is None or prior.interrupt_delivered_at is None:
            return False  # not interrupted as of a prior evaluation yet

        if entry_age_hours(entry, tracking, now) < schedule.max_entry_age_hours:
            return False

        # Not yet due for the next backoff rung.
        next_renotify_at = parse_utc(prior.next_renotify_at)
        return next_renotify_at is None or now >= next_renotify_at

    def stamp(bead_id: str, record: EntryTrackingRecord) -> EntryTrackingRecord:
        prior = prior_tracking[bead_id]
        index = min(prior.renotify_count, len(ladder) - 1)
        next_renotify_at = now + timedelta(hours=ladder[index])
        return record.model_copy(
            update={
                "renotify_count": prior.renotify_count + 1,
                "next_renotify_at": format_utc(next_renotify_at),
            }
        )

    process_entry_decisions(
        EntryDecisionSpec(
            kind=DecisionKind.RENOTIFY,
            due_rule=(
                "unanswered high-severity entry past max age; re-notifying on backoff ladder"
            ),
            held_rule=(
                "re-notification held: quiet hours are absolute (high_overrides_quiet=false)"
            ),
            is_due=is_due,
            held_by_quiet_hours=high_severity_held_by_quiet_hours(now, schedule),
            stamp=stamp,
        ),
        entries=high_entries,
        tracking=tracking,
        summary=summary,
        now=now,
        sink=sink,
    )


def process_auto_waives(
    *,
    low_entries: Sequence[AssumptionReportEntry],
    tracking: dict[str, EntryTrackingRecord],
    schedule: AssumptionScheduleConfig,
    now: datetime,
) -> tuple[AutoWaiveDecision, ...]:
    """Decide auto-waive candidates for aged low entries (US4, FR-015).

    Absent an explicit, doubly opt-in policy (``schedule.auto_waive_low``
    unset, or set but ``enabled=False``), this never produces a decision —
    low-severity entries otherwise age with no delivery path at all
    (clarification Q2). When enabled, every open low entry whose age meets
    or exceeds ``auto_waive_low.after_hours`` yields one
    :class:`AutoWaiveDecision` carrying the full recorded rationale
    (research R10's format), ready for the effects layer (``notify.py``,
    T028) to execute via ``assumptions.ledger.waive`` and never touched
    here — this function performs no bd I/O (Principle III: pure
    evaluation). No idempotence bookkeeping is needed: a successfully
    auto-waived entry is closed in bd and therefore absent from the next
    evaluation's *open* entries entirely.

    Args:
        low_entries: Open low-severity entries at evaluation time.
        tracking: Per-entry scheduler state (age fallback basis only).
        schedule: The delivery policy, carrying the optional
            ``auto_waive_low`` policy.
        now: The evaluation clock.

    Returns:
        One decision per entry due for auto-waive; empty when the policy
        is absent, disabled, or no entry has aged past its threshold.
    """
    policy = schedule.auto_waive_low
    if policy is None or not policy.enabled:
        return ()

    decisions: list[AutoWaiveDecision] = []
    for entry in low_entries:
        if entry_age_hours(entry, tracking, now) < policy.after_hours:
            continue
        reason_text = (
            f"auto-waived by schedule policy after {policy.after_hours}h: {policy.rationale}"
        )
        decisions.append(AutoWaiveDecision(entry_id=entry.record.bead_id, reason_text=reason_text))
    return tuple(decisions)
