"""Window occurrences, quiet-hours arithmetic, and the batching engine.

Everything time-shaped in the scheduler lives here: parsing the validated
``"HH:MM"`` config strings, attaching a timezone to a wall time across DST
edges (:func:`_localize`, research R6), deciding whether a moment falls
inside quiet hours, building the occurrence a configured window has on a
given date (:func:`build_occurrence`, research R8), and resolving a due
occurrence into a delivered / rolled-forward / empty / held decision
(:func:`process_due_occurrence`).

Quiet hours split into a severity-blind question and a severity-scoped one:
:func:`in_quiet_hours_now` answers "is this a quiet moment?", while
:func:`high_severity_held_by_quiet_hours` answers "may *this* decision fire
anyway?" — the ``high_overrides_quiet`` flag governs high-severity traffic
only (FR-004, contracts/config-schema.md).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta, tzinfo

from maverick.assumptions.schedule.decisions import DecisionSink
from maverick.assumptions.schedule.models import (
    BatchSummary,
    DecisionKind,
    DeliveryDecision,
    SkipDecision,
    SkipReason,
    WindowOccurrence,
    format_utc,
)
from maverick.assumptions.schedule.state import WindowDecisionRecord
from maverick.config import AssumptionScheduleConfig, QuietHoursConfig


def _parse_hh_mm(value: str) -> time:
    """Parse an already-validated ``"HH:MM"`` config string.

    *value* comes from :class:`AssumptionScheduleConfig`/
    :class:`QuietHoursConfig`, both validated at config-load time
    (contracts/config-schema.md) — no error handling needed here.
    """
    hour_str, _, minute_str = value.partition(":")
    return time(hour=int(hour_str), minute=int(minute_str))


def _localize(naive: datetime, tz: tzinfo) -> datetime:
    """Attach *tz* to a naive local datetime and resolve DST edge cases.

    Round-tripping through UTC (research R6, PEP 495) is a no-op for an
    unambiguous wall time, but for a spring-forward *gap* (a nonexistent
    local time) it resolves the ``fold=0`` pre-transition interpretation
    forward into the real post-transition instant it actually denotes,
    rather than leaving an imaginary local time in play. Ambiguous
    fall-back times keep their ``fold=0`` (first-occurrence) instant,
    which is a real, valid instant either way.
    """
    aware = naive.replace(tzinfo=tz)
    return aware.astimezone(UTC).astimezone(tz)


def _in_quiet_hours(moment: time, quiet: QuietHoursConfig) -> bool:
    """Whether wall-clock *moment* falls inside *quiet* (may span midnight)."""
    start = _parse_hh_mm(quiet.start)
    end = _parse_hh_mm(quiet.end)
    if start < end:
        return start <= moment < end
    # Spans midnight (config rejects start == end): quiet from `start` to
    # 24:00, and again from 00:00 to `end`.
    return moment >= start or moment < end


def in_quiet_hours_now(now: datetime, quiet: QuietHoursConfig | None) -> bool:
    """Whether quiet hours are configured and *now* falls inside them.

    The severity-blind half of the policy: "is this a quiet moment?".
    Whether a given decision may nonetheless be delivered is
    severity-specific — see :func:`high_severity_held_by_quiet_hours`.
    """
    return quiet is not None and _in_quiet_hours(now.time(), quiet)


def high_severity_held_by_quiet_hours(now: datetime, schedule: AssumptionScheduleConfig) -> bool:
    """Whether a *high-severity* decision is held by quiet hours (FR-004).

    ``high_overrides_quiet`` gates high-severity interrupts and
    high-severity backoff re-notifications identically, and *only* those
    (contracts/config-schema.md). Under the default ``True`` a high entry
    punches through quiet hours; under ``False`` quiet hours are absolute
    and it is held until they end.

    Medium-severity traffic — window batches and max-age escalations — is
    deliberately **not** routed through here: it is held by quiet hours
    unconditionally (:func:`in_quiet_hours_now`), whichever way the
    override is configured. Reading ``high_overrides_quiet`` on a medium
    decision is what let an aged medium entry fire an urgent 03:00 push
    under the default config.
    """
    return not schedule.high_overrides_quiet and in_quiet_hours_now(now, schedule.quiet_hours)


def _quiet_hours_shifted_due(
    occ_date: date, window_time: time, quiet: QuietHoursConfig, tz: tzinfo
) -> datetime:
    """Due time shifted to quiet-hours end, same occurrence identity (R8)."""
    start = _parse_hh_mm(quiet.start)
    end = _parse_hh_mm(quiet.end)
    end_date = occ_date
    if start > end and window_time >= start:
        # Evening portion of a midnight-spanning range: quiet end lands
        # the next calendar day (e.g. window 23:00, quiet 22:00-07:00).
        end_date = occ_date + timedelta(days=1)
    return _localize(datetime.combine(end_date, end), tz)


def build_occurrence(
    occ_date: date, window_str: str, quiet: QuietHoursConfig | None, tz: tzinfo
) -> WindowOccurrence:
    """Construct the occurrence for *window_str* on *occ_date*.

    ``date``/``window`` are the occurrence's identity (never shifted);
    ``due_at`` shifts to quiet-hours end when the configured window time
    falls inside quiet hours (research R8) and is fold-aware across DST
    transitions (research R6).
    """
    window_time = _parse_hh_mm(window_str)
    if quiet is not None and _in_quiet_hours(window_time, quiet):
        due_at = _quiet_hours_shifted_due(occ_date, window_time, quiet, tz)
    else:
        due_at = _localize(datetime.combine(occ_date, window_time), tz)
    return WindowOccurrence(date=occ_date, window=window_str, due_at=due_at)


def previously_held_by_quiet_hours(
    *,
    occ: WindowOccurrence,
    last_evaluated_at: datetime | None,
    quiet: QuietHoursConfig | None,
    now: datetime,
    tz: tzinfo,
) -> bool:
    """Whether *occ* is an undecided occurrence this scheduler itself held.

    An occurrence that became due is always settled by
    :func:`process_due_occurrence` — with one exception: a would-be
    delivery reached inside quiet hours is held with no window decision
    recorded, so it stays due (FR-020). Finding it again the next calendar
    day needs a fingerprint, since its ``due_at`` no longer falls on
    ``now``'s date: **the previous evaluation ran at or after this
    occurrence became due, at or before now, and inside quiet hours** —
    i.e. that evaluation is the one that held it. (A delivery whose ntfy
    push failed is reverted to undecided by ``state.finalize_state`` the
    same way, and legitimately retries here.)

    Deliberately *not* satisfied by a plainly stale occurrence nobody ever
    evaluated: ``last_evaluated_at`` then predates ``occ.due_at`` (cron down
    for days) or falls outside quiet hours (a brand-new schedule's first
    run, whose empty state is stamped with the current instant), and the
    caller leaves the occurrence alone rather than double-firing it
    alongside today's. The one case that does slip through is a first-ever
    run started *inside* quiet hours, which cannot be distinguished from a
    genuine hold without persisting more state; the cost is one extra
    summary push on that first morning.

    Args:
        occ: Yesterday's candidate occurrence, known to be undecided.
        last_evaluated_at: ``DeliveryState.updated_at`` parsed to UTC — the
            previous evaluation's clock, or ``None`` if unparseable.
        quiet: The configured quiet hours, if any.
        now: This evaluation's clock.
        tz: ``now``'s timezone, used to read the previous evaluation's
            *local* wall time (quiet hours are a local-time policy).

    Returns:
        ``True`` when the occurrence should be reconsidered now.
    """
    if quiet is None or last_evaluated_at is None:
        return False
    if not (occ.due_at <= last_evaluated_at <= now):
        return False
    return _in_quiet_hours(last_evaluated_at.astimezone(tz).time(), quiet)


def process_due_occurrence(
    *,
    occ: WindowOccurrence,
    key: str,
    window_str: str,
    now: datetime,
    medium_ids: tuple[str, ...],
    low_ids: tuple[str, ...],
    min_batch_size: int,
    quiet: QuietHoursConfig | None,
    summary: BatchSummary,
    window_decisions: dict[str, WindowDecisionRecord],
    sink: DecisionSink,
) -> None:
    """Decide one not-yet-decided occurrence, appending its outcome.

    Quiet-hours gating (FR-004): a window batch is a medium/legacy delivery,
    so it is held whenever *now* falls inside quiet hours — including a
    window whose own configured time sits outside them, reached by a
    backlogged evaluation (machine asleep, cron catching up). Shifting
    ``due_at`` at occurrence-build time (:func:`build_occurrence`, research
    R8) only covers the case where the *configured* window time is itself
    inside quiet hours; this is the second gate that case does not reach.
    ``high_overrides_quiet`` never applies here — it governs high-severity
    traffic only (contracts/config-schema.md).

    Quiet hours suppress *deliveries*, not bookkeeping: an occurrence that
    resolves to a skip anyway (empty, low-only, below min-batch-size)
    settles normally, because settling it delivers nothing. Only a would-be
    delivery is held, and it is held by recording *no* window decision at
    all, so the occurrence stays due and delivers at the first permissible
    evaluation (FR-020) — see :func:`previously_held_by_quiet_hours` for
    how the next day's evaluation finds it again.

    Mutates *window_decisions* and *sink* in place — a small, deliberate
    exception to this package's otherwise functional style, scoped to
    accumulating one ``evaluate()`` call's results across the
    (today, catch-up-yesterday) x windows loop.
    """
    if now < occ.due_at:
        sink.skip(
            SkipDecision(
                reason=SkipReason.NOT_YET_DUE,
                occurrence=occ,
                entry_ids=(),
                rule=f"window {window_str} not yet due (due {occ.due_at.isoformat()})",
            )
        )
        return

    decision, record = _decide_batch(
        occ=occ,
        window_str=window_str,
        medium_ids=medium_ids,
        low_ids=low_ids,
        min_batch_size=min_batch_size,
        summary=summary,
        now=now,
    )
    if isinstance(decision, DeliveryDecision) and in_quiet_hours_now(now, quiet):
        sink.skip(
            SkipDecision(
                reason=SkipReason.QUIET_HOURS,
                occurrence=occ,
                entry_ids=decision.entry_ids,
                rule=(
                    f"window {window_str} batch held: quiet hours suppress "
                    "medium-severity delivery; rolls to the first evaluation "
                    "after quiet hours end"
                ),
            )
        )
        return

    window_decisions[key] = record
    if isinstance(decision, DeliveryDecision):
        sink.deliver(decision, now)
    else:
        sink.skip(decision)


def _decide_batch(
    *,
    occ: WindowOccurrence,
    window_str: str,
    medium_ids: tuple[str, ...],
    low_ids: tuple[str, ...],
    min_batch_size: int,
    summary: BatchSummary,
    now: datetime,
) -> tuple[DeliveryDecision | SkipDecision, WindowDecisionRecord]:
    """Resolve one due occurrence into a decision plus its persisted record.

    Order of precedence: no medium entries at all (empty, or low-only) →
    min-batch-size roll-forward → deliver. Legacy entries need no special
    case here — ``report_entries`` already synthesizes their severity as
    ``MEDIUM`` (FR-019, research R9), so they arrive in *medium_ids* like
    any other medium entry.
    """
    decided_at = format_utc(now)

    if not medium_ids:
        if low_ids:
            rule = (
                f"window {window_str} due; only low-severity entries pending, "
                "never delivered proactively"
            )
            return (
                SkipDecision(
                    reason=SkipReason.LOW_NEVER_PROACTIVE,
                    occurrence=occ,
                    entry_ids=low_ids,
                    rule=rule,
                ),
                WindowDecisionRecord(
                    outcome="empty", decided_at=decided_at, entry_ids=list(low_ids), rule=rule
                ),
            )
        rule = f"window {window_str} due; batch empty (no open entries pending)"
        return (
            SkipDecision(reason=SkipReason.EMPTY_BATCH, occurrence=occ, entry_ids=(), rule=rule),
            WindowDecisionRecord(outcome="empty", decided_at=decided_at, entry_ids=[], rule=rule),
        )

    if len(medium_ids) < min_batch_size:
        rule = f"{len(medium_ids)} < min_batch_size {min_batch_size}; rolled to next window"
        return (
            SkipDecision(
                reason=SkipReason.MIN_BATCH_SIZE, occurrence=occ, entry_ids=medium_ids, rule=rule
            ),
            WindowDecisionRecord(
                outcome="skipped-min-batch",
                decided_at=decided_at,
                entry_ids=list(medium_ids),
                rule=rule,
            ),
        )

    rule = f"window {window_str} due"
    return (
        DeliveryDecision(
            kind=DecisionKind.WINDOW_BATCH,
            entry_ids=medium_ids,
            summary=summary,
            occurrence=occ,
            rule=rule,
        ),
        WindowDecisionRecord(
            outcome="delivered", decided_at=decided_at, entry_ids=list(medium_ids), rule=rule
        ),
    )
