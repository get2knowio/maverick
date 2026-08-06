"""Pure window/severity evaluation for the assumption batch scheduler.

:func:`evaluate` is the scheduler's decision engine: given the currently
open ledger entries, the configured delivery policy, prior persisted state,
and an injected clock, it decides — without touching disk or network —
which review-window occurrences are due, how each due occurrence's batch
resolves (delivered, rolled forward, empty, or held by quiet hours), and
how severity tiers route (medium batches at windows, low counted but
silent, legacy entries already synthesized to medium by ``report_entries``
and requiring no extra mapping — research R9).

Quiet hours are a *severity-scoped* policy, not a global mute: the
``high_overrides_quiet`` flag governs high-severity traffic only —
interrupts and backoff re-notifications — while every medium/legacy
decision (window batches and max-age escalations alike) is held
unconditionally until quiet hours end (FR-004, FR-006,
contracts/config-schema.md).

This module MUST stay pure (plan.md Constitution Check, Principle III):
``entries``/``schedule``/``state``/``now`` are its only inputs, and its only
output is a fresh :class:`~maverick.assumptions.schedule.models.EvaluationOutcome`.
All effects — ntfy delivery, bd auto-waive, and persisting state to disk —
belong to the ``notify`` CLI command layer, strictly after evaluation
(research R6).

Scope (tasks.md T027, US4): beyond window-batch delivery (medium/low tiers)
and high-severity interrupts (:attr:`DecisionKind.INTERRUPT`), evaluation
also decides max-age escalation for medium entries
(:attr:`DecisionKind.ESCALATION`, FR-006/FR-007) and backoff-ladder
re-notification for high entries (:attr:`DecisionKind.RENOTIFY`,
FR-007), plus opt-in auto-waive candidates for aged low entries
(FR-015).

:func:`evaluate` itself is the orchestrator; each decision engine it drives
lives in a sibling module, all of them equally pure:

* :mod:`~maverick.assumptions.schedule.windows` — occurrence construction,
  quiet-hours and DST arithmetic, and the window-batch engine.
* :mod:`~maverick.assumptions.schedule.severity` — high-severity interrupts.
* :mod:`~maverick.assumptions.schedule.escalation` — max-age escalation,
  backoff re-notification, and auto-waive candidates.
* :mod:`~maverick.assumptions.schedule.tracking` — per-entry bookkeeping
  and entry age.
* :mod:`~maverick.assumptions.schedule.decisions` — the shared decision
  plumbing the entry-scoped engines are all expressed against.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Final

from maverick.assumptions.models import STATUS_OPEN, AssumptionReportEntry, Severity
from maverick.assumptions.schedule.decisions import DecisionSink
from maverick.assumptions.schedule.escalation import (
    process_auto_waives,
    process_high_renotify,
    process_medium_escalations,
)
from maverick.assumptions.schedule.models import (
    BatchSummary,
    DecisionKind,
    EvaluationOutcome,
    SkipDecision,
    SkipReason,
    format_utc,
    occurrence_key,
    parse_utc,
)
from maverick.assumptions.schedule.severity import process_high_interrupts
from maverick.assumptions.schedule.state import DeliveryState, EntryTrackingRecord
from maverick.assumptions.schedule.tracking import (
    ensure_tracking,
    entry_age_hours,
    observe_terminal_entries,
)
from maverick.assumptions.schedule.windows import (
    build_occurrence,
    previously_held_by_quiet_hours,
    process_due_occurrence,
)
from maverick.config import AssumptionScheduleConfig

__all__ = ["evaluate"]

#: Suggested review invocation carried on a :class:`BatchSummary` whose
#: open entries span more than one owning spec (data-model.md §3). When they
#: all share one spec, :func:`_build_summary` narrows it to the spec-scoped
#: variant (contracts/ntfy-payload.md).
_REVIEW_INVOCATION: Final = "maverick review --list --status open"


def evaluate(
    entries: Sequence[AssumptionReportEntry],
    schedule: AssumptionScheduleConfig,
    state: DeliveryState,
    now: datetime,
) -> EvaluationOutcome:
    """Evaluate the ledger against the schedule and prior state.

    Pure function of its four arguments (research R6) — no disk or network
    reads. Every configured window is checked against today's occurrence
    (always reported: delivered, rolled forward, empty, held by quiet hours,
    not yet due, or already decided) and, when still undecided, yesterday's
    occurrence too, but only when quiet hours shifted its due time onto
    today (the midnight-spanning-quiet-hours case, research R8, and a
    same-day delayed evaluation, FR-020) or a prior evaluation held it
    inside quiet hours
    (:func:`~maverick.assumptions.schedule.windows.previously_held_by_quiet_hours`).
    Resolved
    entries (answered/waived) are structurally excluded before any batching
    occurs (FR-014).

    Args:
        entries: Ledger entries as read by ``report_entries()`` at
            evaluation time. Entries whose ``record.status`` is not
            ``"open"`` are excluded from batching (FR-014) — they may
            still appear in *entries* (e.g. resolved between accumulation
            and delivery); this function is responsible for filtering
            them out, not the caller.
        schedule: The delivery policy (`assumptions.schedule` config).
        state: Prior persisted delivery state — read-only; a fresh
            candidate state is returned via
            :attr:`EvaluationOutcome.state_after`, never mutated in place.
        now: An aware local datetime
            (:func:`maverick.assumptions.schedule.clock.now_local` at the
            CLI boundary, or an injected aware datetime in tests). Its
            ``tzinfo`` is reused to construct every window occurrence this
            call considers, so DST fold/gap handling is correct for
            whichever timezone the caller passes — pass a ``ZoneInfo``-backed
            ``now`` (what ``now_local()`` resolves) rather than the
            fixed-offset ``timezone`` from ``datetime.now().astimezone()``,
            which would apply today's offset to occurrences on the far side
            of a transition.

    Returns:
        The full set of decisions plus the candidate state assuming every
        delivery decision's ntfy push succeeds — the effects layer removes
        each failed decision's mutations before persisting
        (contracts/delivery-state-schema.md invariant 2).

    Raises:
        ValueError: ``now`` is naive (no ``tzinfo``) — window/quiet-hours
            arithmetic requires an aware clock.
    """
    tz = now.tzinfo
    if tz is None:
        raise ValueError("evaluate() requires an aware `now` (tzinfo is None)")

    open_entries = tuple(entry for entry in entries if entry.record.status == STATUS_OPEN)
    tracking = ensure_tracking(open_entries, state.entry_tracking, now)
    # FR-016: an entry never leaves tracking silently. A human answering or
    # waiving an entry simply drops it out of `open_entries`, so this is the
    # only place that observation can be recorded — and without it no
    # tracking row ever becomes prunable (FR-023) and `state.json` grows
    # without bound.
    tracking = observe_terminal_entries(entries, tracking, now)
    # Snapshot *before* `process_high_interrupts` mutates `tracking` in
    # place: `process_high_renotify` (US4) must see whether an entry was
    # *already* interrupted as of a prior evaluation, not one this very
    # call just performed — a freshly-interrupted entry is never
    # renotify-eligible in the same evaluation that interrupted it.
    prior_tracking = dict(tracking)
    summary = _build_summary(open_entries, tracking, now)

    medium_entries = [entry for entry in open_entries if entry.record.severity is Severity.MEDIUM]
    low_entries = [entry for entry in open_entries if entry.record.severity is Severity.LOW]
    high_entries = [entry for entry in open_entries if entry.record.severity is Severity.HIGH]
    medium_ids = tuple(entry.record.bead_id for entry in medium_entries)
    low_ids = tuple(entry.record.bead_id for entry in low_entries)

    window_decisions = dict(state.window_decisions)
    sink = DecisionSink()

    # High-severity interrupts (US2, FR-002/FR-004) are entry-scoped, not
    # occurrence-scoped — decided once, up front, independent of the window
    # loop below. `tracking` is mutated in place to stamp each delivered
    # entry's `interrupt_delivered_at` (idempotence, T020).
    process_high_interrupts(
        high_entries=high_entries,
        tracking=tracking,
        schedule=schedule,
        summary=summary,
        now=now,
        sink=sink,
    )

    today = now.date()
    yesterday = today - timedelta(days=1)
    last_evaluated_at = parse_utc(state.updated_at)

    for window_str in schedule.windows:
        # Catch-up: yesterday's occurrence matters in exactly two cases —
        # quiet hours shifted its due time forward onto *today* (research
        # R8; e.g. a 23:00 window inside 22:00-07:00 quiet hours becomes due
        # the next morning, one day after its own occurrence date), or this
        # scheduler itself held it inside quiet hours and left it undecided
        # (:func:`_previously_held_by_quiet_hours`, FR-004/FR-020). A plain,
        # unshifted stale occurrence nobody ever evaluated (cron down for
        # days) is deliberately left alone here — it's the max-entry-age
        # escalation path's job (T027), not this one's, otherwise every
        # fresh evaluation of a brand-new schedule would double-fire.
        key_yesterday = occurrence_key(yesterday, window_str)
        if key_yesterday not in window_decisions:
            occ_yesterday = build_occurrence(yesterday, window_str, schedule.quiet_hours, tz)
            if occ_yesterday.due_at.date() == today or previously_held_by_quiet_hours(
                occ=occ_yesterday,
                last_evaluated_at=last_evaluated_at,
                quiet=schedule.quiet_hours,
                now=now,
                tz=tz,
            ):
                process_due_occurrence(
                    occ=occ_yesterday,
                    key=key_yesterday,
                    window_str=window_str,
                    now=now,
                    medium_ids=medium_ids,
                    low_ids=low_ids,
                    min_batch_size=schedule.min_batch_size,
                    quiet=schedule.quiet_hours,
                    summary=summary,
                    window_decisions=window_decisions,
                    sink=sink,
                )

        key_today = occurrence_key(today, window_str)
        occ_today = build_occurrence(today, window_str, schedule.quiet_hours, tz)
        existing_today = window_decisions.get(key_today)
        if existing_today is not None:
            sink.skip(
                SkipDecision(
                    reason=SkipReason.ALREADY_DELIVERED,
                    occurrence=occ_today,
                    entry_ids=tuple(existing_today.entry_ids),
                    rule=existing_today.rule,
                )
            )
        else:
            process_due_occurrence(
                occ=occ_today,
                key=key_today,
                window_str=window_str,
                now=now,
                medium_ids=medium_ids,
                low_ids=low_ids,
                min_batch_size=schedule.min_batch_size,
                quiet=schedule.quiet_hours,
                summary=summary,
                window_decisions=window_decisions,
                sink=sink,
            )

    # Max-age escalation (US4, FR-006/FR-007): a medium entry already
    # covered by a *this-evaluation* window-batch delivery is excluded —
    # it was just delivered on time, so it isn't the starved entry the
    # safety net exists for.
    already_batched_ids = frozenset(
        bead_id
        for decision in sink.deliveries
        if decision.kind is DecisionKind.WINDOW_BATCH
        for bead_id in decision.entry_ids
    )
    process_medium_escalations(
        medium_entries=medium_entries,
        already_batched_ids=already_batched_ids,
        tracking=tracking,
        schedule=schedule,
        summary=summary,
        now=now,
        sink=sink,
    )

    # Backoff-ladder re-notification (US4, FR-007): high entries interrupted
    # as of a *prior* evaluation, still open past max_entry_age_hours.
    process_high_renotify(
        high_entries=high_entries,
        prior_tracking=prior_tracking,
        tracking=tracking,
        schedule=schedule,
        summary=summary,
        now=now,
        sink=sink,
    )

    auto_waives = process_auto_waives(
        low_entries=low_entries, tracking=tracking, schedule=schedule, now=now
    )

    state_after = state.model_copy(
        update={
            "updated_at": format_utc(now),
            "window_decisions": window_decisions,
            "entry_tracking": tracking,
            "deliveries": [*state.deliveries, *sink.delivery_records],
        }
    )

    return EvaluationOutcome(
        deliveries=tuple(sink.deliveries),
        skips=tuple(sink.skips),
        auto_waives=auto_waives,
        state_after=state_after,
    )


def _build_summary(
    open_entries: Sequence[AssumptionReportEntry],
    tracking: dict[str, EntryTrackingRecord],
    now: datetime,
) -> BatchSummary:
    """Content-free aggregate over every currently open entry (FR-008).

    Deliberately global rather than scoped to one decision's covered
    entries: the notification is a "wake up, here's everything pending"
    summons, so counts (including ``LOW`` — clarification Q5), owning
    specs, and the oldest-entry age all reflect the full open set. Which
    bead ids a given decision actually covers is tracked separately on
    :attr:`DeliveryDecision.entry_ids`.
    """
    counts: dict[Severity, int] = dict.fromkeys(Severity, 0)
    for entry in open_entries:
        counts[entry.record.severity] += 1
    owner_specs = tuple(sorted({entry.record.owner_spec for entry in open_entries}))
    oldest_age_hours = (
        max(entry_age_hours(entry, tracking, now) for entry in open_entries)
        if open_entries
        else 0.0
    )
    return BatchSummary(
        counts=counts,
        owner_specs=owner_specs,
        oldest_age_hours=oldest_age_hours,
        review_invocation=_review_invocation(owner_specs),
    )


def _review_invocation(owner_specs: tuple[str, ...]) -> str:
    """The exact sweep command to put in the push (contracts/ntfy-payload.md).

    Narrowed to ``--spec <name>`` when every open entry shares one owning
    spec — the common single-feature case, where the unscoped variant would
    make the recipient re-filter by hand. An empty/unknown spec name is not
    a usable filter, so it falls back to the unscoped form.
    """
    if len(owner_specs) == 1 and owner_specs[0]:
        return f"maverick review --list --spec {owner_specs[0]} --status open"
    return _REVIEW_INVOCATION
