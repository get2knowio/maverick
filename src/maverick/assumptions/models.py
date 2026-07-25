"""Domain models and bead-schema constants for the assumption ledger.

Every ledger entry is a bd bead (research R1) — these constants are the
single source of truth for the labels/state-keys that shape reads/writes
across the ledger, fly wiring, refuel chaining, and the land/review/brief
CLI surfaces (Constitution VI — no magic strings at call sites).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class Severity(StrEnum):
    """Assumption severity — drives the enforcement policy.

    Attributes:
        LOW: Advisory only; deferred out of the ready queue.
        MEDIUM: Blocks ``maverick land`` until answered or waived.
        HIGH: Blocks land and gains a ``blocks`` edge onto the next spec's epic.
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


#: Coercion target when a reported/read severity value is missing or
#: outside {low, medium, high} (FR-011). Applied identically by
#: ``AssumptionPayload`` (agent path) and ``ledger.record_assumption``
#: (direct callers) — see contracts/ledger-api.md "Severity rule".
DEFAULT_SEVERITY: Severity = Severity.MEDIUM


def coerce_severity(value: str | None) -> tuple[Severity, bool]:
    """Coerce a raw severity string, returning ``(severity, defaulted)``.

    ``defaulted`` is True whenever *value* was missing or not one of
    ``{low, medium, high}`` — the caller persists that as
    ``assumption_severity_defaulted=true`` (FR-011). Never raises.
    """
    if value is not None:
        try:
            return Severity(value), False
        except ValueError:
            pass
    return DEFAULT_SEVERITY, True


#: Discriminator label for ledger entries. Combined with the two legacy
#: escalation-bead labels so the existing agent-side skip filter
#: (``library/actions/beads.py``) and ``brief --human`` keep working
#: unchanged for ledger entries too (research R2).
ASSUMPTION_LABEL = "assumption"
ASSUMPTION_REVIEW_LABEL = "assumption-review"
NEEDS_HUMAN_REVIEW_LABEL = "needs-human-review"
ASSUMPTION_LABELS: tuple[str, ...] = (
    ASSUMPTION_LABEL,
    ASSUMPTION_REVIEW_LABEL,
    NEEDS_HUMAN_REVIEW_LABEL,
)

# bd state keys (data-model.md "State keys").
KEY_SEVERITY = "assumption_severity"
KEY_SEVERITY_DEFAULTED = "assumption_severity_defaulted"
KEY_STATUS = "assumption_status"
KEY_OWNER_SPEC = "assumption_owner_spec"
KEY_CHANGE_IDS = "assumption_change_ids"
KEY_ANSWER = "assumption_answer"
KEY_WAIVED_BY = "assumption_waived_by"
KEY_WAIVED_AT = "assumption_waived_at"
KEY_WAIVE_REASON = "assumption_waive_reason"
KEY_SOURCE_BEAD = "source_bead"
#: Standalone-entry variant of ``source_bead`` (R5) — set instead of
#: ``source_bead`` when no spawning bead exists yet (e.g. the spec-chain's
#: clarify step, recorded before its epic is created by ``refuel --speckit``).
KEY_SOURCE_REF = "source_ref"

# Reconcile state keys (data-model.md "1. Ledger extension"; research R12).
KEY_RECONCILE_STATUS = "assumption_reconcile_status"
KEY_RECONCILED_AT = "assumption_reconciled_at"
KEY_RECONCILED_ANSWER = "assumption_reconciled_answer"
KEY_RECONCILE_CHANGE_ID = "assumption_reconcile_change_id"
KEY_RECONCILE_REASON = "assumption_reconcile_reason"

# Epic-level state keys read to derive ``assumption_owner_spec``
# (research R3 — first match wins).
EPIC_KEY_SPECKIT_FEATURE = "speckit_feature"
EPIC_KEY_FLIGHT_PLAN_NAME = "flight_plan_name"

# assumption_status values.
STATUS_OPEN = "open"
STATUS_ANSWERED = "answered"
STATUS_WAIVED = "waived"

# assumption_reconcile_status values (data-model.md "1. Ledger extension").
RECONCILE_STATUS_RECONCILED = "reconciled"
RECONCILE_STATUS_NEEDS_REVIEW = "needs-interactive-review"
#: Non-terminal re-arm sentinel written by ``ledger.answer`` (FR-017). bd
#: rejects empty state values (``bd set-state <id> dim=`` → "invalid state
#: format"), so a re-answered entry cannot clear the dimension to ``""`` —
#: it writes this eligible-again marker instead, which detection treats
#: identically to an unset status (i.e. NOT excluded).
RECONCILE_STATUS_PENDING = "pending"
#: The two terminal reconcile statuses that exclude an entry from
#: changed-answer detection until it is re-armed (data-model §2).
TERMINAL_RECONCILE_STATUSES = frozenset(
    {RECONCILE_STATUS_RECONCILED, RECONCILE_STATUS_NEEDS_REVIEW}
)


def normalize_answer(text: str) -> str:
    """Normalize answer text for changed-answer comparison.

    Collapses all whitespace runs to single spaces and casefolds, so
    formatting-only differences (extra newlines/spaces, case) never count as
    a changed answer. Shared by ``ledger.answered_unreconciled_entries``
    (detection), ``ledger.mark_reconciled`` (idempotence check, SC-008), and
    reconcile detection generally (FR-017).
    """
    return " ".join(text.split()).casefold()


def nnn_prefix(feature_name: str) -> int | None:
    """Extract the leading ``NNN-`` numeric prefix from a spec identifier.

    Returns ``None`` when *feature_name* doesn't start with a 3-digit
    prefix (e.g. a flight-plan name, or a bare epic-ID fallback). Shared
    ordering rule for ``ledger.next_chained_epic``/``open_high_entries_before``
    and ``refuel_speckit._chain_epic`` (research R8).
    """
    match = re.match(r"^(\d{3})-", feature_name)
    return int(match.group(1)) if match else None


@dataclass(frozen=True, slots=True)
class AssumptionRecord:
    """One assumption ledger entry, read back from its bead.

    Attributes:
        bead_id: The entry's own bead ID.
        question: The question the agent (or human) resolved.
        adopted_answer: The answer that was adopted to keep working.
        alternatives: Other answers considered.
        severity: Enforcement severity.
        severity_defaulted: True when severity was missing/invalid at creation.
        status: ``"open"`` | ``"answered"`` | ``"waived"``.
        owner_spec: Owning spec identifier (see ``EPIC_KEY_*`` derivation).
        source_bead: The bead this entry was discovered from.
        change_ids: jj change IDs stamping this entry; empty = unstamped.
        is_legacy: True for pre-feature escalation beads without ledger state.
    """

    bead_id: str
    question: str
    adopted_answer: str
    alternatives: tuple[str, ...]
    severity: Severity
    severity_defaulted: bool
    status: str
    owner_spec: str
    source_bead: str
    change_ids: tuple[str, ...]
    is_legacy: bool


@dataclass(frozen=True, slots=True)
class PerSpecAssumptionCounts:
    """Per-spec assumption counts aggregated for reporting.

    Attributes:
        owner_spec: Owning spec identifier.
        open: Open-entry counts keyed by severity.
        answered: Answered-entry counts keyed by severity.
        waived: Waived-entry counts keyed by severity.
        legacy_open: Open pre-feature escalation beads owned by this spec.
    """

    owner_spec: str
    open: dict[Severity, int]
    answered: dict[Severity, int]
    waived: dict[Severity, int]
    legacy_open: int


class LandVerification(StrEnum):
    """``maverick land``'s classification of a completed landing.

    Attributes:
        VERIFIED: The frontier is empty and every entry is answered
            (or there were no entries at all).
        CONDITIONALLY_VERIFIED: The frontier is empty but at least one
            entry was waived rather than answered.
        BLOCKED: The frontier is non-empty — land refused.
    """

    VERIFIED = "verified"
    CONDITIONALLY_VERIFIED = "conditionally-verified"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class AssumptionReportEntry:
    """Full read-side view of one ledger entry — everything the land
    frontier gate and provenance report need in one place.

    Constructed only by ``ledger.report_entries()``; never from user input.

    Attributes:
        record: The underlying ledger record (question/answer/severity/etc).
        final_answer: The human's recorded answer (``KEY_ANSWER``), if any.
        waived_by: Who waived this entry, if waived.
        waived_at: ISO-8601 waiver timestamp, if waived.
        waive_reason: The recorded waiver reason, if waived.
        reconcile_status: ``assumption_reconcile_status`` state, if set.
        reconciled_answer: The normalized answer applied by reconcile, if any.
        reconcile_change_id: The jj change ID reconcile folded the
            correction into, if reconciled.
        reconcile_reason: Reconcile's recorded reason (e.g. escalation
            context), if set.
        pending_reconcile: True when this entry appears in
            ``ledger.answered_unreconciled_entries()`` — its human answer
            has drifted from the ledger record and hasn't been reconciled.
    """

    record: AssumptionRecord
    final_answer: str | None
    waived_by: str | None
    waived_at: str | None
    waive_reason: str | None
    reconcile_status: str | None
    reconciled_answer: str | None
    reconcile_change_id: str | None
    reconcile_reason: str | None
    pending_reconcile: bool

    @property
    def bucket(self) -> str:
        """``"resolved" | "waived" | "open"`` — derived from ledger status."""
        if self.record.status == STATUS_WAIVED:
            return "waived"
        if self.record.status == STATUS_ANSWERED:
            return "resolved"
        return "open"

    @property
    def affected_change_ids(self) -> tuple[str, ...]:
        """Ledger change stamps plus the reconcile correction id, deduped."""
        ids = list(self.record.change_ids)
        if self.reconcile_change_id and self.reconcile_change_id not in ids:
            ids.append(self.reconcile_change_id)
        return tuple(ids)

    @property
    def blocks_landing(self) -> bool:
        """True when this entry blocks ``maverick land`` (strict, any severity)."""
        return self.bucket == "open" or self.pending_reconcile


@dataclass(frozen=True, slots=True)
class LandFrontier:
    """The land gate's decision input — every entry that blocks landing.

    Attributes:
        open_entries: Open entries of any severity, including open legacy.
        pending_reconcile_entries: Answered entries whose human answer is
            pending reconciliation (051's detection predicate).
    """

    open_entries: tuple[AssumptionReportEntry, ...]
    pending_reconcile_entries: tuple[AssumptionReportEntry, ...]

    @property
    def is_empty(self) -> bool:
        """True when land may proceed — nothing blocks it."""
        return not self.open_entries and not self.pending_reconcile_entries


@dataclass(frozen=True, slots=True)
class StampResult:
    """Outcome of stamping a batch of entries with a jj change ID.

    Attributes:
        change_id: The jj change ID that was stamped.
        stamped: Bead IDs successfully stamped.
        failed: ``{bead_id: error message}`` for entries that failed to stamp.
    """

    change_id: str
    stamped: tuple[str, ...]
    failed: dict[str, str]


@dataclass(frozen=True, slots=True)
class BulkWaiveResult:
    """Outcome of a spec-scoped, severity-filtered bulk waive.

    Mirrors :class:`StampResult`'s batch-with-partial-failure shape
    (contracts/cli-review-bulk-waive.md: "waives what it can, prints
    per-entry failures").

    Attributes:
        waived: Records successfully waived.
        failed: ``{bead_id: error message}`` for entries that failed to waive.
    """

    waived: tuple[AssumptionRecord, ...]
    failed: dict[str, str]
