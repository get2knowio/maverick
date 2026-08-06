"""High-severity interrupt policy (US2, FR-002, FR-004).

The one decision kind that fires the moment an entry is recorded, with no
window to wait for. Everything about *how* the decision is emitted lives in
:mod:`~maverick.assumptions.schedule.decisions`; this module contributes
only the policy — who is due, and whether quiet hours may hold them.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from maverick.assumptions.models import AssumptionReportEntry
from maverick.assumptions.schedule.decisions import (
    DecisionSink,
    EntryDecisionSpec,
    process_entry_decisions,
)
from maverick.assumptions.schedule.models import BatchSummary, DecisionKind, format_utc
from maverick.assumptions.schedule.state import EntryTrackingRecord
from maverick.assumptions.schedule.windows import high_severity_held_by_quiet_hours
from maverick.config import AssumptionScheduleConfig


def process_high_interrupts(
    *,
    high_entries: Sequence[AssumptionReportEntry],
    tracking: dict[str, EntryTrackingRecord],
    schedule: AssumptionScheduleConfig,
    summary: BatchSummary,
    now: datetime,
    sink: DecisionSink,
) -> None:
    """Decide interrupt delivery for *high_entries* (US2, FR-002, FR-004).

    Idempotence here is per-entry via
    :attr:`EntryTrackingRecord.interrupt_delivered_at`, not per-occurrence
    like window batches: an entry that already carries a timestamp there
    never produces a second :attr:`DecisionKind.INTERRUPT` decision.

    Quiet-hours gating (research R8,
    :func:`~maverick.assumptions.schedule.windows.high_severity_held_by_quiet_hours`):
    when ``schedule.quiet_hours`` is set and ``schedule.high_overrides_quiet``
    is ``False``, an entry whose interrupt would otherwise fire during quiet
    hours is held — recorded as a :attr:`SkipReason.QUIET_HOURS` skip, *not*
    stamped as delivered — so it becomes due again at the first evaluation
    after quiet hours end. Any other combination (no quiet hours configured,
    or ``high_overrides_quiet=True``) delivers immediately. This is one of
    the two decision kinds ``high_overrides_quiet`` governs; the other is
    :func:`~maverick.assumptions.schedule.escalation.process_high_renotify`.

    Mutates *tracking* and *sink* in place — the same deliberate, scoped
    exception to this package's functional style as every other
    decision-producing helper.
    """
    delivered_at = format_utc(now)

    def is_due(entry: AssumptionReportEntry) -> bool:
        record = tracking.get(entry.record.bead_id)
        # already delivered — idempotent, never re-fires here
        return record is None or record.interrupt_delivered_at is None

    def stamp(bead_id: str, record: EntryTrackingRecord) -> EntryTrackingRecord:
        return record.model_copy(update={"interrupt_delivered_at": delivered_at})

    process_entry_decisions(
        EntryDecisionSpec(
            kind=DecisionKind.INTERRUPT,
            due_rule="high-severity interrupt due",
            held_rule=(
                "high-severity interrupt held: quiet hours are absolute "
                "(high_overrides_quiet=false)"
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
