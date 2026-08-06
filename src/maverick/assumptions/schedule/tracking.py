"""Per-entry scheduler bookkeeping: tracking rows and entry age.

:attr:`~maverick.assumptions.schedule.state.DeliveryState.entry_tracking` is
the scheduler's own view of each ledger entry — when it first saw the entry,
what it has already delivered about it, and whether the entry has reached a
terminal state. This module owns that mapping's lifecycle (bootstrap,
terminal observation) and the age computation every threshold in the policy
is measured against.

Both functions here return a *new* mapping rather than mutating the one they
are given: they run before any decision engine, on state that is still
purely derived from the ledger.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from maverick.assumptions.models import STATUS_OPEN, AssumptionReportEntry
from maverick.assumptions.schedule.models import format_utc, parse_utc
from maverick.assumptions.schedule.state import EntryTrackingRecord, TerminalOutcome


def ensure_tracking(
    open_entries: Sequence[AssumptionReportEntry],
    tracking: dict[str, EntryTrackingRecord],
    now: datetime,
) -> dict[str, EntryTrackingRecord]:
    """Bootstrap/refresh :attr:`DeliveryState.entry_tracking` for *open_entries*.

    ``first_seen`` is set once, on an entry's first evaluation, and never
    overwritten thereafter — it is only ever the *fallback* age basis, used
    when ``created_at`` is missing (research R1). Every other field is
    preserved from the prior tracking row (later phases populate them);
    ``severity`` is refreshed to the currently observed value each call.
    """
    updated = dict(tracking)
    for entry in open_entries:
        bead_id = entry.record.bead_id
        existing = updated.get(bead_id)
        # `created_at` is bd's string, copied verbatim — only adopt it as the
        # persisted fallback basis when it actually parses, else this row's
        # own fallback would be as unusable as the value it replaces.
        created_at = entry.record.created_at if parse_utc(entry.record.created_at) else None
        first_seen = (
            existing.first_seen if existing is not None else (created_at or format_utc(now))
        )
        updated[bead_id] = EntryTrackingRecord(
            first_seen=first_seen,
            severity=entry.record.severity.value,
            interrupt_delivered_at=existing.interrupt_delivered_at if existing else None,
            escalation_delivered_at=existing.escalation_delivered_at if existing else None,
            renotify_count=existing.renotify_count if existing else 0,
            next_renotify_at=existing.next_renotify_at if existing else None,
            terminal=existing.terminal if existing else None,
        )
    return updated


def observe_terminal_entries(
    entries: Sequence[AssumptionReportEntry],
    tracking: dict[str, EntryTrackingRecord],
    now: datetime,
) -> dict[str, EntryTrackingRecord]:
    """Stamp ``terminal`` on tracked entries a human answered or waived (FR-016).

    "No entry leaves delivery evaluation silently" has two halves. The
    scheduler's own auto-waives are stamped by the ``notify`` command
    (which knows the waive actually landed in bd); the other half — a
    human resolving an entry via ``maverick review`` — is only ever
    *observed*, because resolution simply makes the entry stop appearing
    in the open set. Without this observation a resolved entry's tracking
    row keeps ``terminal=None`` forever, which also means
    :func:`~maverick.assumptions.schedule.state.prune` can never retire it
    or the delivery/window records referencing it (FR-023).

    Only rows this scheduler already tracks are stamped: an entry that was
    resolved before it was ever seen was never in tracking, and inventing
    a row for it would resurrect exactly the growth this prevents.

    Args:
        entries: *All* ledger entries from ``report_entries()``, not just
            the open ones — the resolved entries are the whole point.
        tracking: The candidate tracking mapping; never mutated in place.
        now: The evaluation clock; starts the FR-023 retention window.

    Returns:
        A new mapping with a ``resolved-by-human`` terminal outcome on each
        newly-observed resolved entry.
    """
    updated = dict(tracking)
    observed_at = format_utc(now)
    for entry in entries:
        if entry.record.status == STATUS_OPEN:
            continue
        record = updated.get(entry.record.bead_id)
        if record is None or record.terminal is not None:
            continue
        updated[entry.record.bead_id] = record.model_copy(
            update={"terminal": TerminalOutcome(kind="resolved-by-human", at=observed_at)}
        )
    return updated


def entry_age_hours(
    entry: AssumptionReportEntry, tracking: dict[str, EntryTrackingRecord], now: datetime
) -> float:
    """Age in hours from ``created_at``, falling back to tracked ``first_seen``."""
    basis = _age_basis(entry, tracking, now)
    delta_hours = (now.astimezone(UTC) - basis).total_seconds() / 3600.0
    return max(delta_hours, 0.0)


def _age_basis(
    entry: AssumptionReportEntry, tracking: dict[str, EntryTrackingRecord], now: datetime
) -> datetime:
    """Age basis: bd's ``created_at``, then tracked ``first_seen``, then *now*.

    Both candidates are external strings (``created_at`` is copied verbatim
    from bd; ``first_seen`` round-trips through a hand-editable state file),
    so each is parsed tolerantly — an unparseable value falls through to the
    next basis rather than crashing an unattended cron run.
    """
    created = parse_utc(entry.record.created_at)
    if created is not None:
        return created
    tracked = tracking.get(entry.record.bead_id)
    if tracked is not None:
        first_seen = parse_utc(tracked.first_seen)
        if first_seen is not None:
            return first_seen
    return now.astimezone(UTC)
