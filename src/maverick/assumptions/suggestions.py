"""Learned-resolution orchestration: decision capture and corpus collapse.

Composes ``assumptions`` (ledger domain) with ``runway`` (storage) without
either side importing the other directly — ``ledger.py`` deliberately imports
no workflow/CLI/runway modules (research R5,
``specs/055-learned-assumption-resolution/research.md``). This module is the
one shared implementation call sites (``cli/commands/review/entry_actions.py``
today; matching/suggestion evaluation in later phases) compose against.

See ``specs/055-learned-assumption-resolution/contracts/decision-records.md``
for the storage and admission contract.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final, Literal

from maverick.assumptions import ledger
from maverick.assumptions.matching import (
    base_score,
    effective_confidence,
    normalize_question,
    select_best,
)
from maverick.assumptions.models import (
    KEY_AUTO_RESOLVED,
    KEY_SUGGESTION,
    Severity,
    Suggestion,
    suggestion_to_json,
)
from maverick.logging import get_logger

if TYPE_CHECKING:
    from maverick.assumptions.models import AssumptionReportEntry
    from maverick.beads.client import BeadClient
    from maverick.config import AutoResolvePolicyConfig
    from maverick.runway.models import DecisionRecord, MatchFeedbackRecord
    from maverick.runway.store import RunwayStore

__all__ = [
    "attach_suggestions",
    "backfill_suggestions",
    "classify_feedback",
    "collapse_decisions",
    "evaluate_suggestion",
    "record_decision",
    "record_feedback",
]

logger = get_logger(__name__)

_AUTO_RESOLVE_ACTOR: Final = "maverick-resolver"

#: Defensive ceiling on the encoded ``Suggestion`` JSON persisted under
#: ``KEY_SUGGESTION``. ``bd set-state`` stores this value as part of a
#: ``"<dimension>:<value>"`` label with a total-length cap that silently
#: TRUNCATES on overflow (no error) — empirically ~254 chars minus
#: ``len("assumption_suggestion")`` (21) = 233 chars for this key, verified
#: against a real bd 1.1.2 sandbox (binary search around the boundary) and
#: found independent of bead-id/reason length (see the 055
#: quickstart-validation writeup and research.md R4's addendum). 220 leaves a
#: 13-char safety margin below that observed hard boundary while still
#: comfortably fitting realistic content — e.g. a 64-char resolution
#: ("Yes, use AsyncRetrying with 3 attempts and exponential backoff") with a
#: 24-char owner spec and a live microsecond-precision ``computed_at``
#: encodes to 214 chars. A suggestion that would exceed this ceiling is
#: never persisted (never truncated) — see ``_evaluate_and_persist``.
_MAX_SUGGESTION_JSON_LENGTH: Final = 220


async def record_decision(
    store: RunwayStore,
    entry: AssumptionReportEntry,
    *,
    resolution_type: Literal["answered", "waived"],
    resolution: str,
    resolved_by: str,
) -> bool:
    """Append a :class:`DecisionRecord` for a human-initiated resolution.

    Best-effort (FR-004): catches any exception the store append raises,
    logs a warning, and returns ``False`` instead of raising. Callers (the
    human review surfaces — R6) use the return value to decide whether to
    surface a ``[yellow]Warning:[/]`` to the user; the ledger write that
    prompted this call has already succeeded and must never be reported as
    failed because the corpus write failed.

    Args:
        store: Runway store to append into. Callers are responsible for
            resolving it and confirming it's initialized (best-effort
            degradation per FR-021 — an uninitialized store is not this
            function's concern).
        entry: The resolved ledger entry, read *before* the write (its
            question/adopted-answer/severity/owner-spec do not change as a
            result of answering or waiving).
        resolution_type: ``"answered"`` or ``"waived"``.
        resolution: The answer text, or the waive reason.
        resolved_by: Git user name attributed to the resolution.

    Returns:
        ``True`` on a successful append, ``False`` on any failure (already
        logged as a warning).
    """
    from maverick.runway.models import DecisionRecord

    record = entry.record
    try:
        decision = DecisionRecord(
            source_entry_id=record.bead_id,
            question=record.question,
            normalized_question=normalize_question(record.question),
            adopted_answer=record.adopted_answer,
            resolution_type=resolution_type,
            resolution=resolution,
            severity=record.severity.value,
            owner_spec=record.owner_spec,
            resolved_by=resolved_by,
            resolved_at=datetime.now(UTC).isoformat(),
        )
        await store.append_decision(decision)
    except Exception as exc:  # noqa: BLE001 — best-effort corpus write (FR-004)
        logger.warning(
            "decision_record_write_failed",
            source_entry_id=record.bead_id,
            error=str(exc),
        )
        return False
    return True


def collapse_decisions(records: list[DecisionRecord]) -> list[DecisionRecord]:
    """Collapse decision-corpus history to one authoritative record per entry.

    Groups *records* by ``source_entry_id`` and keeps only the record with
    the latest ``resolved_at`` in each group (data-model.md's "Collapse
    rule") — earlier lines remain in the JSONL corpus as history (FR-003)
    but are not authoritative for matching/suggestion purposes.

    Args:
        records: Decision records, in any order (typically append order
            from :meth:`RunwayStore.get_decisions`).

    Returns:
        One record per distinct ``source_entry_id``, order not guaranteed.
    """
    latest: dict[str, DecisionRecord] = {}
    for record in records:
        current = latest.get(record.source_entry_id)
        if current is None or _resolved_at_key(record) > _resolved_at_key(current):
            latest[record.source_entry_id] = record
    return list(latest.values())


def _resolved_at_key(record: DecisionRecord) -> tuple[float, str]:
    """Sort key for ``resolved_at`` comparison.

    Parses ISO-8601 via :meth:`datetime.fromisoformat` where possible
    (falls back to the raw string, which still sorts sanely for the
    zero-padded ISO-8601 timestamps every writer in this codebase produces)
    so both parsed and lexical comparison agree.
    """
    try:
        return (datetime.fromisoformat(record.resolved_at).timestamp(), record.resolved_at)
    except ValueError:
        return (float("-inf"), record.resolved_at)


#: {(normalized question, candidate entry id) -> (acceptances, rejections)}.
_FeedbackIndex = dict[tuple[str, str], tuple[int, int]]


def _index_feedback(feedback: Sequence[MatchFeedbackRecord]) -> _FeedbackIndex:
    """Tally *feedback* into accept/reject counts per exact pairing.

    Built once per batch by :func:`attach_suggestions` /
    :func:`backfill_suggestions` so scoring a record is a dict lookup per
    candidate instead of a full scan of the feedback log — the batch paths
    would otherwise be O(records x candidates x feedback).
    """
    index: _FeedbackIndex = {}
    for item in feedback:
        key = (item.normalized_question, item.source_entry_id)
        acceptances, rejections = index.get(key, (0, 0))
        if item.outcome == "accepted":
            index[key] = (acceptances + 1, rejections)
        elif item.outcome == "rejected":
            index[key] = (acceptances, rejections + 1)
    return index


def evaluate_suggestion(
    record: AssumptionReportEntry,
    corpus: list[DecisionRecord],
    feedback: Sequence[MatchFeedbackRecord] = (),
) -> Suggestion | None:
    """Match *record* against the decision corpus and score a suggestion.

    Pure and synchronous — no I/O. Implements the matching formula from
    ``contracts/decision-records.md`` (research R5/R12):

    1. Collapse *corpus* to one authoritative record per
       ``source_entry_id`` (:func:`collapse_decisions`).
    2. Exclude a self-match — a candidate whose ``source_entry_id`` equals
       *record*'s own bead id (R12: a re-opened/re-answered entry must
       never match the decision record produced by its own earlier
       resolution).
    3. Score each remaining candidate via :func:`matching.base_score`,
       penalized by :func:`matching.effective_confidence` using net
       rejection/acceptance counts from *feedback* for that exact
       (normalized question, candidate) pairing.
    4. Select the best-scoring candidate at or above
       :data:`matching.PRESENTATION_THRESHOLD` via
       :func:`matching.select_best` (deterministic tie-break).

    Args:
        record: The open ledger entry to find a suggestion for.
        corpus: Decision records to match against (any order, may contain
            multiple versions per ``source_entry_id`` — collapsed here).
        feedback: Prior accept/reject decisions on presented suggestions.
            Empty by default — User Story 3 wires real feedback records.

    Returns:
        A single :class:`Suggestion` for the best-matching candidate, or
        ``None`` when no candidate clears the presentation threshold.
    """
    return _evaluate(record, collapse_decisions(corpus), _index_feedback(feedback))


def _evaluate(
    record: AssumptionReportEntry,
    candidates: Sequence[DecisionRecord],
    feedback_index: _FeedbackIndex,
) -> Suggestion | None:
    """Score *record* against a pre-collapsed, pre-indexed corpus.

    The batch-friendly core of :func:`evaluate_suggestion`: *candidates*
    must already be collapsed (:func:`collapse_decisions`) and
    *feedback_index* already tallied (:func:`_index_feedback`), both of
    which are per-corpus rather than per-record work.
    """
    self_id = record.record.bead_id
    scoreable = [c for c in candidates if c.source_entry_id != self_id]
    if not scoreable:
        return None

    normalized_record_question = normalize_question(record.record.question)
    scored: list[tuple[float, str, str, DecisionRecord]] = []
    for candidate in scoreable:
        acceptances, rejections = feedback_index.get(
            (normalized_record_question, candidate.source_entry_id), (0, 0)
        )
        base = base_score(record.record.question, candidate.question)
        confidence = effective_confidence(base, rejections=rejections, acceptances=acceptances)
        scored.append((confidence, candidate.resolved_at, candidate.source_entry_id, candidate))

    winner = select_best(scored)
    if winner is None:
        return None

    confidence, resolved_at, source_entry_id, candidate = winner
    return Suggestion(
        resolution=candidate.resolution,
        resolution_type=candidate.resolution_type,
        source_entry_id=source_entry_id,
        source_spec=candidate.owner_spec,
        resolved_at=resolved_at,
        confidence=confidence,
        computed_at=datetime.now(UTC).isoformat(),
    )


def classify_feedback(
    entry: AssumptionReportEntry,
    suggestion: Suggestion,
    *,
    resolution_type: Literal["answered", "waived"],
    resolution: str,
) -> Literal["accepted", "rejected"]:
    """Classify a human resolution against the suggestion it was shown.

    Pure and synchronous. Per ``contracts/decision-records.md`` "Decision
    capture points": ``"accepted"`` iff *resolution_type* matches
    ``suggestion.resolution_type`` AND the normalized *resolution* text
    matches the normalized ``suggestion.resolution`` text. A type mismatch
    is always ``"rejected"``, even when the text happens to be identical.

    Resolution text is compared with :func:`matching.normalize_question`
    (casefold + strip punctuation + collapse whitespace) per the contract's
    ``normalize()``, **not** the whitespace/case-only
    :func:`~maverick.assumptions.models.normalize_answer` that reconcile's
    changed-answer detection uses. The two answer different questions and
    are meant to diverge: this one asks "is the human's resolution the same
    *decision* the suggestion proposed", where punctuation is noise;
    reconcile asks "did the recorded answer text change at all", where it
    is not. A resolution can therefore be ``"accepted"`` here and still
    count as a changed answer there, by design.

    Args:
        entry: The resolved ledger entry (unused beyond documenting the
            call site's shape — classification only needs *suggestion*
            and the actual resolution).
        suggestion: The suggestion that was presented for *entry* prior to
            resolution.
        resolution_type: How the entry was actually resolved.
        resolution: The actual answer text, or waive reason.

    Returns:
        ``"accepted"`` if the resolution matches the suggestion in both
        type and normalized text, ``"rejected"`` otherwise.
    """
    del entry  # unused: classification depends only on suggestion + actual resolution
    if resolution_type != suggestion.resolution_type:
        return "rejected"
    if normalize_question(resolution) != normalize_question(suggestion.resolution):
        return "rejected"
    return "accepted"


async def record_feedback(
    store: RunwayStore, entry: AssumptionReportEntry, *, accepted: bool
) -> bool:
    """Append a :class:`MatchFeedbackRecord` for a human's accept/reject
    decision on a presented suggestion.

    Best-effort (mirrors :func:`record_decision`'s never-raises/bool-return
    contract): catches any exception the store append raises, logs a
    warning, and returns ``False`` instead of raising.

    **Precondition**: callers must only invoke this when ``entry.suggestion
    is not None`` — the suggestion presented is exactly what this feedback
    penalizes/rewards on future matches. If ``entry.suggestion`` is
    ``None``, this returns ``False`` immediately without writing anything
    (defensive, consistent with the never-raises contract) rather than
    raising.

    Args:
        store: Runway store to append into.
        entry: The resolved ledger entry that carried the suggestion.
        accepted: Whether the human's resolution matched the suggestion.

    Returns:
        ``True`` on a successful append, ``False`` on any failure or when
        *entry* carried no suggestion (already logged as a warning in the
        failure case).
    """
    from maverick.runway.models import MatchFeedbackRecord

    suggestion = entry.suggestion
    if suggestion is None:
        logger.warning(
            "match_feedback_missing_suggestion",
            bead_id=entry.record.bead_id,
        )
        return False

    try:
        record = MatchFeedbackRecord(
            normalized_question=normalize_question(entry.record.question),
            source_entry_id=suggestion.source_entry_id,
            outcome="accepted" if accepted else "rejected",
            recorded_at=datetime.now(UTC).isoformat(),
        )
        await store.append_match_feedback(record)
    except Exception as exc:  # noqa: BLE001 — best-effort corpus write (FR-004 pattern)
        logger.warning(
            "match_feedback_write_failed",
            source_entry_id=entry.record.bead_id,
            error=str(exc),
        )
        return False
    return True


async def _load_corpus(store: RunwayStore) -> tuple[list[DecisionRecord], _FeedbackIndex]:
    """Load and pre-process the decision corpus for a batch, never raising.

    ``decisions.jsonl`` / ``match-feedback.jsonl`` are append-only and
    outlive schema changes, so a read can fail on a row the current wheel
    can't validate. :func:`attach_suggestions` and
    :func:`backfill_suggestions` both document a never-raises contract;
    degrading to an empty corpus (no suggestions this batch) keeps it true
    rather than leaving every caller responsible for wrapping the call.

    Returns the corpus already collapsed to one authoritative record per
    entry and the feedback already tallied — both per-corpus, not
    per-record, work.
    """
    try:
        corpus = await store.get_decisions()
        feedback = await store.get_match_feedback()
    except Exception as exc:  # noqa: BLE001 — best-effort corpus read (FR-004 pattern)
        logger.warning("decision_corpus_read_failed", path=str(store.path), error=str(exc))
        return [], {}
    return collapse_decisions(corpus), _index_feedback(feedback)


async def _evaluate_and_persist(
    client: BeadClient,
    record: AssumptionReportEntry,
    candidates: Sequence[DecisionRecord],
    feedback_index: _FeedbackIndex,
) -> Suggestion | None:
    """Evaluate one entry and persist a resulting suggestion, best-effort.

    Shared by :func:`attach_suggestions` and :func:`backfill_suggestions` so
    the evaluate-then-``set_state`` sequence — and its failure handling —
    lives in exactly one place. Never raises: any failure in evaluation or
    the bd write is logged as a warning and treated as "no suggestion",
    so one bad record never blocks the rest of a batch.

    This is also the natural extension point for auto-resolution
    (User Story 4, not implemented here): a future policy check would slot
    in after a suggestion is computed and before/instead of the plain
    ``set_state`` persist below.

    A suggestion whose encoded JSON would risk bd's silent state-value
    truncation (``_MAX_SUGGESTION_JSON_LENGTH``) is never persisted — it is
    treated exactly like "no candidate matched" (debug log, ``None``
    returned) rather than being written corrupted/truncated. This is
    expected, graceful degradation (R11), not an error, so it logs at
    debug rather than warning.
    """
    try:
        suggestion = _evaluate(record, candidates, feedback_index)
        if suggestion is None:
            return None
        encoded = suggestion_to_json(suggestion)
        if len(encoded) > _MAX_SUGGESTION_JSON_LENGTH:
            logger.debug(
                "suggestion_too_long_to_persist_safely",
                bead_id=record.record.bead_id,
                encoded_length=len(encoded),
                max_length=_MAX_SUGGESTION_JSON_LENGTH,
            )
            return None
        await client.set_state(
            record.record.bead_id,
            {KEY_SUGGESTION: encoded},
            reason="suggestion",
        )
    except Exception as exc:  # noqa: BLE001 — best-effort batch write (FR-004 pattern)
        logger.warning(
            "suggestion_persist_failed",
            bead_id=record.record.bead_id,
            error=str(exc),
        )
        return None
    return suggestion


async def attach_suggestions(
    client: BeadClient,
    store: RunwayStore,
    records: list[AssumptionReportEntry],
    *,
    auto_resolve: AutoResolvePolicyConfig | None = None,
) -> None:
    """Evaluate and persist a suggestion for each of *records*, best-effort.

    Never raises. A store that hasn't been initialized (FR-021-style
    best-effort degradation) is a silent no-op — no corpus to match
    against. Otherwise loads the decision corpus once and evaluates every
    record against it, persisting each match via one ``set_state`` call;
    a failure on any single record (evaluation or persistence) is logged
    and does not block the rest of the batch (see :func:`_evaluate_and_persist`).

    When *auto_resolve* is provided, enabled, and a computed suggestion's
    confidence clears its ``confidence_threshold`` on a ``low``-severity
    record, the entry is auto-waived (User Story 4) instead of being left
    for human review — machine-initiated, so no :class:`DecisionRecord` or
    :class:`MatchFeedbackRecord` is ever written for it (FR-005). This is
    recording-time only; :func:`backfill_suggestions` never auto-resolves.

    Args:
        client: bd client used to persist matched suggestions.
        store: Runway store to read the decision corpus from.
        records: Ledger entries to evaluate (typically newly recorded or
            newly listed open entries).
        auto_resolve: Opt-in auto-resolution policy. ``None`` (the
            default) preserves prior behavior exactly.
    """
    if not store.is_initialized:
        logger.debug("attach_suggestions_store_uninitialized", path=str(store.path))
        return

    candidates, feedback_index = await _load_corpus(store)

    for record in records:
        suggestion = await _evaluate_and_persist(client, record, candidates, feedback_index)
        if suggestion is None:
            continue
        await _maybe_auto_resolve(client, record, suggestion, auto_resolve)


async def _maybe_auto_resolve(
    client: BeadClient,
    record: AssumptionReportEntry,
    suggestion: Suggestion,
    auto_resolve: AutoResolvePolicyConfig | None,
) -> None:
    """Auto-waive *record* when it's eligible under *auto_resolve*.

    Eligibility (all must hold): the record is ``low`` severity,
    *auto_resolve* is provided and enabled, and *suggestion*'s confidence
    clears ``auto_resolve.confidence_threshold``. Never raises — a
    stamp/waive failure is logged and the entry is left as-is (never
    retried; :func:`attach_suggestions` runs once per record).

    ``KEY_AUTO_RESOLVED`` is stamped **before** the waive, deliberately.
    ``bd set-state`` is one subprocess call per key, so the two writes are
    not atomic and either can fail on its own; the stamp is exactly what
    lets a human override the machine's decision (``maverick review <id>``
    bypasses its already-waived refusal only for auto-resolved entries).
    Waiving first would mean a failure in between leaves an entry waived by
    ``maverick-resolver`` that no human can ever reopen. Stamping first
    inverts the failure into the harmless direction: an *open* entry
    carrying a stale ``auto_resolved`` marker, which nothing gates on.
    """
    if record.record.severity != Severity.LOW:
        return
    if auto_resolve is None or not auto_resolve.enabled:
        return
    if suggestion.confidence < auto_resolve.confidence_threshold:
        return

    reason = (
        f"Auto-resolved: matches prior decision {suggestion.source_entry_id} "
        f"from {suggestion.source_spec} ({suggestion.resolved_at}) "
        f"at {suggestion.confidence:.2f} confidence"
    )
    try:
        await client.set_state(
            record.record.bead_id, {KEY_AUTO_RESOLVED: "true"}, reason="auto-resolved"
        )
        await ledger.waive(
            client, bead_id=record.record.bead_id, reason=reason, waived_by=_AUTO_RESOLVE_ACTOR
        )
    except Exception as exc:  # noqa: BLE001 — never let auto-resolve failure break the batch
        # Entry is left open with its suggestion (research R11) and never
        # retried (attach runs once per record), so this warning is the
        # only signal an operator gets — it must carry the actual cause.
        logger.warning(
            "assumption_auto_resolve_failed",
            bead_id=record.record.bead_id,
            error=str(exc),
        )


async def backfill_suggestions(
    client: BeadClient,
    store: RunwayStore,
    entries: list[AssumptionReportEntry],
) -> list[AssumptionReportEntry]:
    """Evaluate and persist suggestions for entries that lack one.

    Entries whose ``.suggestion`` is already set — whether a genuinely
    matched suggestion or (R11) a stored-but-unparseable value that
    degraded to ``None`` upstream in ``report_entry_from_details`` and
    therefore looks identical to "absent" here — are left untouched by
    this simplest-correct implementation: only entries observed with
    ``suggestion is None`` from a *missing* key are distinguishable from
    "present but unparseable" without also threading the raw state value
    through, which nothing tested here currently requires. Never raises.

    Args:
        client: bd client used to persist newly matched suggestions.
        store: Runway store to read the decision corpus from.
        entries: Ledger entries to consider for back-fill.

    Returns:
        *entries* with a freshly computed ``suggestion`` attached (via
        ``dataclasses.replace``) for every entry that got one; entries
        left alone (already had a suggestion, or no match found) are
        returned unchanged.
    """
    if not store.is_initialized:
        logger.debug("backfill_suggestions_store_uninitialized", path=str(store.path))
        return entries

    candidates, feedback_index = await _load_corpus(store)

    updated: list[AssumptionReportEntry] = []
    for entry in entries:
        if entry.suggestion is not None:
            updated.append(entry)
            continue
        suggestion = await _evaluate_and_persist(client, entry, candidates, feedback_index)
        updated.append(replace(entry, suggestion=suggestion) if suggestion is not None else entry)
    return updated
