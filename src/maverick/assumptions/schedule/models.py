"""Evaluation-domain models for the assumption batch scheduler.

Pure, in-memory frozen dataclasses produced by
:func:`maverick.assumptions.schedule.evaluate.evaluate` and consumed by
:mod:`maverick.assumptions.schedule.deliver` and the ``notify`` CLI command.
These are never persisted directly — the persisted counterpart lives in
:mod:`maverick.assumptions.schedule.state`. See
``specs/054-assumption-batch-scheduler/data-model.md`` §3.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from maverick.assumptions.models import Severity

if TYPE_CHECKING:
    from collections.abc import Mapping

    from maverick.assumptions.schedule.state import DeliveryState

__all__ = [
    "AutoWaiveDecision",
    "BatchSummary",
    "DecisionKind",
    "DeliveryDecision",
    "EvaluationOutcome",
    "SkipDecision",
    "SkipReason",
    "WindowOccurrence",
    "format_age_hours",
    "format_utc",
    "occurrence_key",
    "parse_utc",
]


def format_utc(moment: datetime) -> str:
    """UTC ISO-8601 ``"YYYY-MM-DDTHH:MM:SSZ"`` (the house convention).

    The single formatter for every timestamp this feature persists or
    stamps — ``evaluate``, ``state``, and the ``notify`` command all route
    through it so the three can never drift apart on precision or suffix.

    Args:
        moment: Any aware datetime; converted to UTC before formatting.

    Returns:
        The UTC instant as an ISO-8601 string with a ``Z`` suffix.
    """
    return moment.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_utc(value: str | None) -> datetime | None:
    """Parse a UTC ISO-8601 timestamp (``...Z`` or explicit offset), tolerantly.

    Timestamps reaching the scheduler come from outside its own writes —
    ``created_at`` is copied verbatim from bd, and ``state.json`` is a
    plain file a human can edit — so a malformed value must degrade to
    "unknown" rather than crashing an unattended cron invocation. Callers
    fall back to their own basis (tracked ``first_seen``, or ``now``) on
    ``None``.

    Args:
        value: The candidate timestamp, or ``None``.

    Returns:
        An aware UTC-normalized ``datetime``, or ``None`` when *value* is
        missing, empty, or unparseable.
    """
    if not value:
        return None
    normalized = f"{value[:-1]}+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def occurrence_key(occ_date: date, window: str) -> str:
    """``"YYYY-MM-DD/HH:MM"`` — the window-occurrence idempotence key (FR-010).

    Args:
        occ_date: The occurrence's local calendar date.
        window: The configured ``"HH:MM"`` window string.

    Returns:
        The key used in ``DeliveryState.window_decisions`` and as a
        delivery record's ``trigger``.
    """
    return f"{occ_date.isoformat()}/{window}"


def format_age_hours(hours: float) -> str:
    """Render an age in hours for human/push display (one decimal place).

    ``oldest_age_hours`` is raw float arithmetic, so the unrounded value
    reads as ``11.499999999999998h`` in an ntfy push. Every display site
    formats through here.

    Args:
        hours: The age in hours.

    Returns:
        The age rounded to one decimal place, without a unit suffix.
    """
    return f"{hours:.1f}"


class DecisionKind(StrEnum):
    """Categories of :class:`DeliveryDecision` (data-model.md §3).

    Attributes:
        WINDOW_BATCH: A batched medium/legacy delivery at a review window.
        INTERRUPT: An immediate high-severity delivery outside windows.
        ESCALATION: A medium/high entry delivered after exceeding
            ``max_entry_age_hours``, bypassing min-batch-size.
        RENOTIFY: A repeat high-severity delivery per the backoff ladder.
    """

    WINDOW_BATCH = "window-batch"
    INTERRUPT = "interrupt"
    ESCALATION = "escalation"
    RENOTIFY = "renotify"


class SkipReason(StrEnum):
    """Why a candidate occurrence or entry produced no delivery.

    Attributes:
        MIN_BATCH_SIZE: Batch below the configured minimum; entries roll
            forward to the next occurrence.
        QUIET_HOURS: Suppressed by quiet hours (subject to
            ``high_overrides_quiet`` for high-severity entries).
        ALREADY_DELIVERED: The occurrence already has a recorded decision
            (idempotence, FR-010).
        NOT_YET_DUE: The occurrence's ``due_at`` has not yet elapsed.
        LOW_NEVER_PROACTIVE: Low-severity entries never trigger a delivery
            on their own (clarification Q5); still counted in
            :class:`BatchSummary`.
        EMPTY_BATCH: The occurrence became due with zero covered entries
            (FR-014).
    """

    MIN_BATCH_SIZE = "min-batch-size"
    QUIET_HOURS = "quiet-hours"
    ALREADY_DELIVERED = "already-delivered"
    NOT_YET_DUE = "not-yet-due"
    LOW_NEVER_PROACTIVE = "low-never-proactive"
    EMPTY_BATCH = "empty-batch"


@dataclass(frozen=True, slots=True)
class WindowOccurrence:
    """One scheduled review-window instance on one calendar date.

    Identity key: ``(date, window)`` — at most one decision is ever recorded
    against a given occurrence, enforced via ``state.window_decisions``
    (idempotence, FR-010).

    Attributes:
        date: Local calendar date the window falls on.
        window: Configured ``"HH:MM"`` window string, as written in
            ``AssumptionScheduleConfig.windows``.
        due_at: Aware local datetime the occurrence becomes due; shifted
            past quiet hours when applicable (research R8) and fold-aware
            across DST transitions (research R6).
    """

    date: date
    window: str
    due_at: datetime

    @property
    def key(self) -> str:
        """This occurrence's ``"YYYY-MM-DD/HH:MM"`` idempotence key (FR-010)."""
        return occurrence_key(self.date, self.window)


@dataclass(frozen=True, slots=True)
class BatchSummary:
    """Aggregate, content-free view of the entries covered by one decision.

    Never carries question/answer text or any other entry content
    (FR-008) — only counts and metadata safe to push to a phone.

    One instance is built per evaluation and attached to *every*
    :class:`DeliveryDecision` in the run as well as to every persisted
    delivery record, so :attr:`counts` must not be writable through the
    summary: ``frozen=True`` protects the field binding, not the mapping's
    contents, and a single consumer mutating it would silently rewrite
    every other decision's counts and the persisted audit trail.
    :meth:`__post_init__` therefore snapshots whatever mapping the caller
    passes into a read-only :class:`types.MappingProxyType` — construction
    stays ergonomic (pass a plain ``dict``), reads are unchanged, and
    writes raise.

    Attributes:
        counts: Read-only open-entry counts keyed by severity; includes
            ``LOW`` as an informational-only count even though low never
            triggers delivery on its own (clarification Q5).
        owner_specs: Sorted tuple of owning spec identifiers covered by
            this batch.
        oldest_age_hours: Age in hours of the oldest covered entry, from
            ``created_at`` with a ``first_seen`` fallback (research R1).
        review_invocation: Suggested CLI invocation to review the batch,
            e.g. ``"maverick review --list --status open"``.
    """

    counts: Mapping[Severity, int]
    owner_specs: tuple[str, ...]
    oldest_age_hours: float
    review_invocation: str

    def __post_init__(self) -> None:
        """Detach and freeze :attr:`counts` (see the class docstring)."""
        object.__setattr__(self, "counts", MappingProxyType(dict(self.counts)))

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable projection, shared by persisted state and ``--json``.

        One projection so the audit trail written into ``state.json`` and
        the envelope ``maverick notify --json`` emits can never drift.

        Returns:
            The summary as plain JSON-safe types.
        """
        return {
            "counts": {severity.value: count for severity, count in self.counts.items()},
            "owner_specs": list(self.owner_specs),
            "oldest_age_hours": self.oldest_age_hours,
            "review_invocation": self.review_invocation,
        }


@dataclass(frozen=True, slots=True)
class DeliveryDecision:
    """A decision to deliver one notification (batch, interrupt, or aged).

    Attributes:
        kind: Which delivery category this decision represents.
        entry_ids: Bead IDs covered by this delivery — open at evaluation
            time (FR-014 structural exclusion of resolved entries).
        summary: Content-free aggregate of the covered entries.
        occurrence: The window occurrence this decision fulfils; set only
            for :attr:`DecisionKind.WINDOW_BATCH`, ``None`` otherwise.
        rule: Human-readable rule citation for the audit trail (e.g.
            ``"window 09:00 due"``).
    """

    kind: DecisionKind
    entry_ids: tuple[str, ...]
    summary: BatchSummary
    occurrence: WindowOccurrence | None
    rule: str


@dataclass(frozen=True, slots=True)
class SkipDecision:
    """A decision that no delivery occurs, with its cited rule.

    Attributes:
        reason: Why no delivery occurred.
        occurrence: The window occurrence this skip applies to, when
            window-scoped; ``None`` for entry-scoped skips.
        entry_ids: Bead IDs affected by this skip.
        rule: Human-readable rule citation for the audit trail.
    """

    reason: SkipReason
    occurrence: WindowOccurrence | None
    entry_ids: tuple[str, ...]
    rule: str


@dataclass(frozen=True, slots=True)
class AutoWaiveDecision:
    """A decision to auto-waive one aged low-severity entry (FR-015).

    Attributes:
        entry_id: The bead ID to waive.
        reason_text: The full rationale recorded on the ledger entry.
    """

    entry_id: str
    reason_text: str


@dataclass(frozen=True, slots=True)
class EvaluationOutcome:
    """The complete result of one ``evaluate()`` call.

    Attributes:
        deliveries: Decisions that produce a notification.
        skips: Decisions that produce no notification, with their rule.
        auto_waives: Entries to auto-waive as a side effect of this
            evaluation.
        state_after: The candidate persisted state assuming every
            decision's effect succeeds; the effects layer removes each
            failed decision's mutations before saving (per-decision
            write-after-success — contracts/delivery-state-schema.md
            invariant 2).
    """

    deliveries: tuple[DeliveryDecision, ...]
    skips: tuple[SkipDecision, ...]
    auto_waives: tuple[AutoWaiveDecision, ...]
    state_after: DeliveryState
