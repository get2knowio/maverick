"""Decision plumbing shared by every scheduler decision kind.

Three things live here, all of them the mechanics of *emitting* a decision
rather than the policy of *making* one:

* :class:`DecisionSink` — the accumulator every decision-producing helper
  appends to, pairing each delivery with its speculative audit record so
  the two can never drift apart.
* :func:`build_delivery_record` — that speculative audit record.
* :class:`EntryDecisionSpec` / :func:`process_entry_decisions` — the one
  entry-scoped decision engine behind high-severity interrupts, max-age
  escalations, and backoff re-notifications. Those three differ only in
  policy (which entries are due, whether quiet hours hold them, what gets
  stamped on delivery), so each supplies a spec instead of transcribing the
  control flow again. Adding a fourth kind is a fourth spec, not a fourth
  copy — the divergence that once left ``ESCALATION``/``RENOTIFY`` out of
  ``state.finalize_state``'s revert table (FR-012) started as exactly that
  kind of transcription.

Window batches are deliberately *not* routed through
:func:`process_entry_decisions`: they are occurrence-scoped, carry a
:class:`~maverick.assumptions.schedule.models.WindowOccurrence`, and persist
a :class:`~maverick.assumptions.schedule.state.WindowDecisionRecord` — see
:func:`~maverick.assumptions.schedule.windows.process_due_occurrence`.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from maverick.assumptions.models import AssumptionReportEntry
from maverick.assumptions.schedule.models import (
    BatchSummary,
    DecisionKind,
    DeliveryDecision,
    SkipDecision,
    SkipReason,
    format_utc,
)
from maverick.assumptions.schedule.state import DeliveryRecord, EntryTrackingRecord

_DeliveryKindLiteral = Literal["window-batch", "interrupt", "escalation", "renotify"]


def _delivery_kind_literal(kind: DecisionKind) -> _DeliveryKindLiteral:
    """Map :class:`DecisionKind` to :class:`DeliveryRecord`'s kind literal.

    A explicit match (rather than reusing the matching ``StrEnum`` values
    directly) keeps this mypy-strict: ``DeliveryRecord.kind`` is a
    ``Literal[...]``, and each branch below narrows to exactly one member.
    """
    match kind:
        case DecisionKind.WINDOW_BATCH:
            return "window-batch"
        case DecisionKind.INTERRUPT:
            return "interrupt"
        case DecisionKind.ESCALATION:
            return "escalation"
        case DecisionKind.RENOTIFY:
            return "renotify"


def build_delivery_record(decision: DeliveryDecision, now: datetime) -> DeliveryRecord:
    """Speculative audit-trail entry for one :class:`DeliveryDecision`.

    Assumes the eventual ntfy push succeeds — per data-model.md §3, the
    effects layer (``notify.py``, T017/T024) strips this record back out
    of the state it actually persists for any decision whose delivery
    attempt fails (write-after-success, FR-012).
    """
    trigger = decision.occurrence.key if decision.occurrence is not None else decision.rule
    return DeliveryRecord(
        kind=_delivery_kind_literal(decision.kind),
        delivered_at=format_utc(now),
        trigger=trigger,
        entry_ids=list(decision.entry_ids),
        summary=decision.summary.to_dict(),
    )


@dataclass(frozen=True)
class DecisionSink:
    """Accumulator for one ``evaluate()`` call's decisions.

    Frozen so the three lists can't be swapped out, but the lists
    themselves are appended to in place — a small, deliberate exception to
    this package's otherwise functional style, scoped to gathering results
    across the several decision engines one evaluation runs. Appending a
    delivery and its :class:`DeliveryRecord` is a single operation
    (:meth:`deliver`) precisely so no caller can record one without the
    other.
    """

    deliveries: list[DeliveryDecision] = field(default_factory=list)
    skips: list[SkipDecision] = field(default_factory=list)
    delivery_records: list[DeliveryRecord] = field(default_factory=list)

    def deliver(self, decision: DeliveryDecision, now: datetime) -> None:
        """Record *decision* plus the audit record its push will confirm."""
        self.deliveries.append(decision)
        self.delivery_records.append(build_delivery_record(decision, now))

    def skip(self, decision: SkipDecision) -> None:
        """Record a decision that produced no delivery."""
        self.skips.append(decision)


@dataclass(frozen=True)
class EntryDecisionSpec:
    """One entry-scoped decision kind, expressed as data (research R9).

    Attributes:
        kind: The :class:`DecisionKind` a due batch delivers under.
        due_rule: Human-readable rule text on the delivery decision.
        held_rule: Human-readable rule text on the quiet-hours skip.
        is_due: Per-entry eligibility, evaluated before quiet hours —
            covers idempotence bookkeeping (already delivered?), age
            thresholds, and backoff timing. Returning ``False`` drops the
            entry from this evaluation entirely, producing neither a
            delivery nor a skip.
        held_by_quiet_hours: Whether quiet hours hold *this kind* right
            now. Severity-scoped, and the reason this is a per-spec value
            rather than one shared check: ``high_overrides_quiet`` governs
            high-severity traffic only, while medium escalation is held
            unconditionally (FR-004, contracts/config-schema.md). Computed
            once per call — it is a function of ``now`` and the schedule,
            never of an individual entry.
        stamp: Idempotence bookkeeping applied to each *delivered* entry's
            tracking row — held entries are deliberately left unstamped so
            they stay due at the first evaluation after quiet hours end.
    """

    kind: DecisionKind
    due_rule: str
    held_rule: str
    is_due: Callable[[AssumptionReportEntry], bool]
    held_by_quiet_hours: bool
    stamp: Callable[[str, EntryTrackingRecord], EntryTrackingRecord]


def process_entry_decisions(
    spec: EntryDecisionSpec,
    *,
    entries: Sequence[AssumptionReportEntry],
    tracking: dict[str, EntryTrackingRecord],
    summary: BatchSummary,
    now: datetime,
    sink: DecisionSink,
) -> None:
    """Resolve *entries* under *spec* into at most one delivery and one skip.

    Every due entry coalesces into a *single* delivery carrying the
    content-free, whole-ledger *summary* every decision kind uses (research
    R9) — one push, not one per entry — and every held entry into a single
    :attr:`SkipReason.QUIET_HOURS` skip. An entry that is not due produces
    neither.

    Mutates *tracking* and *sink* in place; see :class:`DecisionSink`.
    """
    due_ids: list[str] = []
    held_ids: list[str] = []

    for entry in entries:
        if not spec.is_due(entry):
            continue
        bead_id = entry.record.bead_id
        if spec.held_by_quiet_hours:
            held_ids.append(bead_id)
        else:
            due_ids.append(bead_id)

    if due_ids:
        sink.deliver(
            DeliveryDecision(
                kind=spec.kind,
                entry_ids=tuple(due_ids),
                summary=summary,
                occurrence=None,
                rule=spec.due_rule,
            ),
            now,
        )
        for bead_id in due_ids:
            tracking[bead_id] = spec.stamp(bead_id, tracking[bead_id])

    if held_ids:
        sink.skip(
            SkipDecision(
                reason=SkipReason.QUIET_HOURS,
                occurrence=None,
                entry_ids=tuple(held_ids),
                rule=spec.held_rule,
            )
        )
