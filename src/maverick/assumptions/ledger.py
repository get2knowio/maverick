"""Ledger operations: record, stamp, resolve, and query assumption entries.

Every function takes an explicit ``cwd``-scoped ``BeadClient`` (Guardrail 7 —
no ``Path.cwd()`` defaults) and returns frozen dataclasses from
``maverick.assumptions.models``. See
``specs/049-assumption-ledger/contracts/ledger-api.md``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from maverick.assumptions.errors import AssumptionLedgerError
from maverick.assumptions.models import (
    ASSUMPTION_LABEL,
    ASSUMPTION_LABELS,
    ASSUMPTION_REVIEW_LABEL,
    EPIC_KEY_FLIGHT_PLAN_NAME,
    EPIC_KEY_SPECKIT_FEATURE,
    KEY_ANSWER,
    KEY_CHANGE_IDS,
    KEY_OWNER_SPEC,
    KEY_SEVERITY,
    KEY_SEVERITY_DEFAULTED,
    KEY_SOURCE_BEAD,
    KEY_STATUS,
    KEY_WAIVE_REASON,
    KEY_WAIVED_AT,
    KEY_WAIVED_BY,
    STATUS_ANSWERED,
    STATUS_OPEN,
    STATUS_WAIVED,
    AssumptionRecord,
    Severity,
    StampResult,
    coerce_severity,
    nnn_prefix,
)
from maverick.exceptions.beads import BeadError
from maverick.logging import get_logger

if TYPE_CHECKING:
    from maverick.beads.client import BeadClient
    from maverick.payloads import AssumptionPayload

logger = get_logger(__name__)

__all__ = [
    "answer",
    "next_chained_epic",
    "open_blocking_entries",
    "open_high_entries_before",
    "parse_description",
    "record_assumption",
    "stamp_change_id",
    "waive",
]

# Statuses that mean "not open" for dedup / query purposes — bd's own
# vocabulary includes "closed" and "done" for finished beads.
_CLOSED_STATUSES = frozenset(("closed", "done"))

_SEVERITY_PRIORITY: dict[Severity, int] = {
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
}

_TITLE_MAX_LEN = 150


def _normalize_question(question: str) -> str:
    """Casefold + collapse-whitespace normalization for dedup matching."""
    return " ".join(question.split()).casefold()


def _section(description: str, marker: str, next_markers: tuple[str, ...]) -> str:
    """Return the body of one ``## <marker>`` section, bounded by the next heading."""
    idx = description.find(marker)
    if idx == -1:
        return ""
    rest = description[idx + len(marker) :]
    end = len(rest)
    for next_marker in next_markers:
        pos = rest.find(next_marker)
        if pos != -1:
            end = min(end, pos)
    return rest[:end].strip()


def parse_description(description: str) -> tuple[str, str, tuple[str, ...]]:
    """Parse an entry's fixed markdown description back into its parts.

    Returns ``(question, adopted_answer, alternatives)`` — the inverse of
    :func:`_build_description`. Used by the ledger's own dedup matching
    and by ``maverick review``'s full-context display.
    """
    question = _section(
        description,
        "## Question",
        ("## Adopted Answer", "## Alternatives Considered", "## Context"),
    )
    adopted_answer = _section(
        description, "## Adopted Answer", ("## Alternatives Considered", "## Context")
    )
    alt_body = _section(description, "## Alternatives Considered", ("## Context",))
    alternatives = (
        tuple(
            line.strip()[2:].strip()
            for line in alt_body.splitlines()
            if line.strip().startswith("- ")
        )
        if alt_body and alt_body != "(none)"
        else ()
    )
    return question, adopted_answer, alternatives


def _extract_question(description: str) -> str:
    """Pull the ``## Question`` section body out of an entry's description."""
    return parse_description(description)[0]


def _build_description(
    *,
    question: str,
    adopted_answer: str,
    alternatives: Sequence[str],
    source_bead_id: str,
    source_title: str,
) -> str:
    alt_body = "\n".join(f"- {alt}" for alt in alternatives) if alternatives else "(none)"
    return (
        "## Question\n\n"
        f"{question}\n\n"
        "## Adopted Answer\n\n"
        f"{adopted_answer}\n\n"
        "## Alternatives Considered\n\n"
        f"{alt_body}\n\n"
        "## Context\n\n"
        f"Source bead: {source_bead_id} — {source_title}\n"
    )


async def _derive_owner_spec(client: BeadClient, *, epic_id: str) -> dict[str, str]:
    """Return the owning epic's state, raising :class:`AssumptionLedgerError` on bd failure.

    Returns an empty mapping when *epic_id* is empty (the global
    ``maverick fly`` path with no resolvable owning epic) rather than
    issuing a ``bd show ""`` that would crash and silently drop the entry.
    """
    if not epic_id:
        return {}
    try:
        epic_details = await client.show(epic_id)
    except BeadError as exc:
        raise AssumptionLedgerError(f"Failed to load epic {epic_id}: {exc}") from exc
    return dict(epic_details.state or {})


async def _resolve_owning_epic(client: BeadClient, *, epic_id: str, source_bead_id: str) -> str:
    """Resolve the epic that should own this assumption entry.

    On the global ``maverick fly`` path (no ``--epic`` filter) *epic_id*
    is empty; fall back to the source bead's parent epic so the ledger
    entry is still parented under a real epic and ``owner_spec`` still
    resolves. Returns ``""`` only when neither is available (best-effort —
    the entry is still recorded, just unparented).
    """
    if epic_id:
        return epic_id
    try:
        source_details = await client.show(source_bead_id)
    except BeadError:
        return ""
    return source_details.parent_id or ""


def _owner_spec_from_epic_state(epic_state: dict[str, str], *, epic_id: str) -> str:
    return (
        epic_state.get(EPIC_KEY_SPECKIT_FEATURE)
        or epic_state.get(EPIC_KEY_FLIGHT_PLAN_NAME)
        or epic_id
    )


async def _find_existing_open_entry(
    client: BeadClient,
    *,
    epic_id: str,
    normalized_question: str,
) -> AssumptionRecord | None:
    """Search open ``assumption`` children of *epic_id* for a question match."""
    if not epic_id:
        return None
    try:
        children = await client.children(epic_id)
    except BeadError as exc:
        raise AssumptionLedgerError(f"Failed to list children of {epic_id}: {exc}") from exc

    for child in children:
        if child.status in _CLOSED_STATUSES:
            continue
        try:
            details = await client.show(child.id)
        except BeadError as exc:
            raise AssumptionLedgerError(f"Failed to load bead {child.id}: {exc}") from exc
        if "assumption" not in (details.labels or []):
            continue
        if _normalize_question(_extract_question(details.description)) == normalized_question:
            return _record_from_details(details)
    return None


def _record_from_details(details: object) -> AssumptionRecord:
    """Reconstruct an :class:`AssumptionRecord` from a ``BeadDetails``."""
    state: dict[str, str] = dict(getattr(details, "state", None) or {})
    severity, _ = coerce_severity(state.get(KEY_SEVERITY))
    change_ids_raw = state.get(KEY_CHANGE_IDS, "")
    change_ids = tuple(c for c in change_ids_raw.split(",") if c) if change_ids_raw else ()
    description = getattr(details, "description", "") or ""
    question, adopted_answer, alternatives = parse_description(description)
    return AssumptionRecord(
        bead_id=getattr(details, "id", ""),
        question=question,
        adopted_answer=adopted_answer,
        alternatives=alternatives,
        severity=severity,
        severity_defaulted=state.get(KEY_SEVERITY_DEFAULTED) == "true",
        status=state.get(KEY_STATUS, STATUS_OPEN),
        owner_spec=state.get(KEY_OWNER_SPEC, ""),
        source_bead=state.get(KEY_SOURCE_BEAD, ""),
        change_ids=change_ids,
        is_legacy=False,
    )


def _legacy_record_from_details(details: object) -> AssumptionRecord:
    """Build a synthetic record for a pre-feature escalation bead (FR-013).

    Legacy beads have the ``assumption-review``/``needs-human-review``
    labels but no ledger state — treated as ``medium`` severity at read
    time, without mutating the bead.
    """
    state: dict[str, str] = dict(getattr(details, "state", None) or {})
    return AssumptionRecord(
        bead_id=getattr(details, "id", ""),
        question=getattr(details, "title", ""),
        adopted_answer="",
        alternatives=(),
        severity=Severity.MEDIUM,
        severity_defaulted=True,
        status=STATUS_OPEN,
        owner_spec=state.get(KEY_OWNER_SPEC) or state.get("flight_plan", ""),
        source_bead=state.get(KEY_SOURCE_BEAD, ""),
        change_ids=(),
        is_legacy=True,
    )


async def next_chained_epic(client: BeadClient, *, epic_id: str) -> str | None:
    """Discovery rule for the high-severity blocks-edge target.

    Among open epics with a ``speckit_feature`` state value, returns the
    one with the smallest NNN prefix strictly greater than the owning
    epic's — the same ordering ``_chain_epic`` uses. Returns ``None``
    when the owning epic has no ``speckit_feature`` (flight-plan runs
    never wire next-epic edges) or no later epic exists.
    """
    try:
        epic_details = await client.show(epic_id)
    except BeadError as exc:
        raise AssumptionLedgerError(f"Failed to load epic {epic_id}: {exc}") from exc

    owning_prefix = nnn_prefix((epic_details.state or {}).get(EPIC_KEY_SPECKIT_FEATURE, ""))
    if owning_prefix is None:
        return None

    try:
        candidates = await client.query("type=epic AND status=open")
    except BeadError as exc:
        raise AssumptionLedgerError(f"Failed to query open epics: {exc}") from exc

    best_id: str | None = None
    best_prefix: int | None = None
    for candidate in candidates:
        if candidate.id == epic_id:
            continue
        try:
            details = await client.show(candidate.id)
        except BeadError as exc:
            raise AssumptionLedgerError(f"Failed to load epic {candidate.id}: {exc}") from exc
        prefix = nnn_prefix((details.state or {}).get(EPIC_KEY_SPECKIT_FEATURE, ""))
        if prefix is None or prefix <= owning_prefix:
            continue
        if best_prefix is None or prefix < best_prefix:
            best_prefix = prefix
            best_id = candidate.id
    return best_id


async def _wire_high_blocks_edge(client: BeadClient, *, entry_id: str, epic_id: str) -> None:
    """Wire a ``blocks`` edge from a high-severity entry onto the next spec's epic."""
    from maverick.beads.models import BeadDependency, DependencyType

    next_epic_id = await next_chained_epic(client, epic_id=epic_id)
    if not next_epic_id:
        return
    try:
        await client.add_dependency(
            BeadDependency(
                blocker_id=entry_id,
                blocked_id=next_epic_id,
                dep_type=DependencyType.BLOCKS,
            )
        )
    except BeadError as exc:
        raise AssumptionLedgerError(f"Failed to wire blocks edge for {entry_id}: {exc}") from exc


async def _maybe_escalate_severity(
    client: BeadClient,
    *,
    existing: AssumptionRecord,
    new_severity: Severity,
    new_defaulted: bool,
    epic_id: str,
) -> AssumptionRecord:
    """Raise an existing open entry's severity when a re-report is more severe.

    A later bead re-reporting the same question at a higher severity must
    strengthen enforcement, not inherit the weaker original: the stored
    ``assumption_severity`` is bumped so the land gate and ``brief`` reflect
    the true blast radius, and — when the escalation reaches ``high`` — the
    ``blocks`` edge onto the next spec's epic is wired. Returns the updated
    record, or *existing* unchanged when the re-report is no more severe.
    """
    if _SEVERITY_PRIORITY[new_severity] >= _SEVERITY_PRIORITY[existing.severity]:
        return existing

    state: dict[str, str] = {KEY_SEVERITY: new_severity.value}
    state[KEY_SEVERITY_DEFAULTED] = "true" if new_defaulted else "false"
    try:
        await client.set_state(
            existing.bead_id,
            state,
            reason=(f"severity escalated {existing.severity.value} -> {new_severity.value}"),
        )
    except BeadError as exc:
        raise AssumptionLedgerError(
            f"Failed to escalate severity on {existing.bead_id}: {exc}"
        ) from exc

    if new_severity is Severity.HIGH and epic_id:
        await _wire_high_blocks_edge(client, entry_id=existing.bead_id, epic_id=epic_id)

    logger.info(
        "assumption_severity_escalated",
        bead_id=existing.bead_id,
        from_severity=existing.severity.value,
        to_severity=new_severity.value,
    )
    return replace(
        existing,
        severity=new_severity,
        severity_defaulted=new_defaulted,
    )


async def record_assumption(
    client: BeadClient,
    *,
    payload: AssumptionPayload,
    source_bead_id: str,
    epic_id: str,
) -> AssumptionRecord | None:
    """Create (or merge into) a ledger entry for one reported assumption.

    Derives the owning spec from the epic's state, applies the severity
    coercion rule, wires a ``discovered-from`` edge to *source_bead_id*, and
    dedups against open entries with the same normalized question under the
    same epic (appending a discovered-from edge to the existing entry
    instead of creating a duplicate).

    Raises:
        AssumptionLedgerError: On any bd-layer failure.
    """
    from maverick.beads.models import (
        BeadCategory,
        BeadDefinition,
        BeadDependency,
        BeadType,
        DependencyType,
    )

    severity, defaulted_here = coerce_severity(payload.severity)
    defaulted = bool(payload.severity_defaulted) or defaulted_here

    # On the global ``maverick fly`` path epic_id is "" (no --epic filter);
    # resolve the source bead's real owning epic so the entry is parented
    # and owner_spec resolves instead of being silently dropped.
    effective_epic_id = await _resolve_owning_epic(
        client, epic_id=epic_id, source_bead_id=source_bead_id
    )

    epic_state = await _derive_owner_spec(client, epic_id=effective_epic_id)
    owner_spec = _owner_spec_from_epic_state(epic_state, epic_id=effective_epic_id)

    normalized_question = _normalize_question(payload.question)
    existing = await _find_existing_open_entry(
        client, epic_id=effective_epic_id, normalized_question=normalized_question
    )
    if existing is not None:
        try:
            await client.add_dependency(
                BeadDependency(
                    blocker_id=source_bead_id,
                    blocked_id=existing.bead_id,
                    dep_type=DependencyType.DISCOVERED_FROM,
                )
            )
        except BeadError as exc:
            raise AssumptionLedgerError(
                f"Failed to wire discovered-from edge onto {existing.bead_id}: {exc}"
            ) from exc
        escalated = await _maybe_escalate_severity(
            client,
            existing=existing,
            new_severity=severity,
            new_defaulted=defaulted,
            epic_id=effective_epic_id,
        )
        logger.info(
            "assumption_dedup_merged",
            bead_id=existing.bead_id,
            source_bead_id=source_bead_id,
            escalated_to=escalated.severity.value if escalated is not existing else None,
        )
        return escalated

    try:
        source_title = source_bead_id
        source_details = await client.show(source_bead_id)
        source_title = source_details.title or source_bead_id
    except BeadError:
        pass  # best-effort context line only

    definition = BeadDefinition(
        title=f"Assumption: {payload.question[:_TITLE_MAX_LEN]}",
        bead_type=BeadType.TASK,
        priority=_SEVERITY_PRIORITY[severity],
        category=BeadCategory.REVIEW,
        description=_build_description(
            question=payload.question,
            adopted_answer=payload.adopted_answer,
            alternatives=payload.alternatives,
            source_bead_id=source_bead_id,
            source_title=source_title,
        ),
        assignee="human",
        labels=list(ASSUMPTION_LABELS),
    )

    try:
        created = await client.create_bead(definition, parent_id=effective_epic_id or None)
    except BeadError as exc:
        raise AssumptionLedgerError(f"Failed to create assumption bead: {exc}") from exc

    state: dict[str, str] = {
        KEY_SEVERITY: severity.value,
        KEY_STATUS: STATUS_OPEN,
        KEY_OWNER_SPEC: owner_spec,
        KEY_SOURCE_BEAD: source_bead_id,
    }
    if defaulted:
        state[KEY_SEVERITY_DEFAULTED] = "true"

    try:
        await client.set_state(
            created.bd_id, state, reason=f"assumption recorded from {source_bead_id}"
        )
    except BeadError as exc:
        raise AssumptionLedgerError(
            f"Failed to set state on assumption bead {created.bd_id}: {exc}"
        ) from exc

    try:
        await client.add_dependency(
            BeadDependency(
                blocker_id=source_bead_id,
                blocked_id=created.bd_id,
                dep_type=DependencyType.DISCOVERED_FROM,
            )
        )
    except BeadError as exc:
        raise AssumptionLedgerError(
            f"Failed to wire discovered-from edge for {created.bd_id}: {exc}"
        ) from exc

    if severity is Severity.LOW:
        from maverick.library.actions.beads import defer_bead

        try:
            await defer_bead(
                created.bd_id, cwd=client.cwd, reason="low-severity assumption — advisory only"
            )
        except Exception as exc:  # noqa: BLE001 — defer_bead has no typed error hierarchy
            raise AssumptionLedgerError(
                f"Failed to defer low-severity entry {created.bd_id}: {exc}"
            ) from exc
    elif severity is Severity.HIGH and effective_epic_id:
        await _wire_high_blocks_edge(client, entry_id=created.bd_id, epic_id=effective_epic_id)

    logger.info(
        "assumption_recorded",
        bead_id=created.bd_id,
        severity=severity.value,
        owner_spec=owner_spec,
        source_bead_id=source_bead_id,
    )
    return AssumptionRecord(
        bead_id=created.bd_id,
        question=payload.question,
        adopted_answer=payload.adopted_answer,
        alternatives=tuple(payload.alternatives),
        severity=severity,
        severity_defaulted=defaulted,
        status=STATUS_OPEN,
        owner_spec=owner_spec,
        source_bead=source_bead_id,
        change_ids=(),
        is_legacy=False,
    )


async def stamp_change_id(
    client: BeadClient,
    *,
    entry_ids: Sequence[str],
    change_id: str,
) -> StampResult:
    """Append *change_id* to each entry's ``assumption_change_ids`` state.

    Append-only and idempotent per ``(entry, change_id)``. Never raises —
    a commit must not fail because stamping failed (FR-012); per-entry
    failures are reported in the returned :class:`StampResult`.
    """
    stamped: list[str] = []
    failed: dict[str, str] = {}

    for entry_id in entry_ids:
        try:
            details = await client.show(entry_id)
            existing_raw = (details.state or {}).get(KEY_CHANGE_IDS, "")
            existing_ids = [c for c in existing_raw.split(",") if c] if existing_raw else []
            if change_id in existing_ids:
                stamped.append(entry_id)
                continue
            existing_ids.append(change_id)
            await client.set_state(
                entry_id,
                {KEY_CHANGE_IDS: ",".join(existing_ids)},
                reason=f"stamp {change_id}",
            )
            stamped.append(entry_id)
        except Exception as exc:  # noqa: BLE001 — never raises (FR-012)
            logger.warning("assumption_stamp_failed", bead_id=entry_id, error=str(exc))
            failed[entry_id] = str(exc)

    return StampResult(change_id=change_id, stamped=tuple(stamped), failed=failed)


async def answer(
    client: BeadClient,
    *,
    bead_id: str,
    answer_text: str,
) -> AssumptionRecord:
    """Record an answer, mark the entry answered, and close it.

    Closing releases any ``blocks`` edges wired for this entry (bd's own
    dependency-release semantics).

    Raises:
        AssumptionLedgerError: If *answer_text* is empty, or on bd failure.
    """
    if not answer_text or not answer_text.strip():
        raise AssumptionLedgerError("Answer text must not be empty")

    try:
        await client.set_state(
            bead_id,
            {KEY_ANSWER: answer_text, KEY_STATUS: STATUS_ANSWERED},
            reason="assumption answered",
        )
        await client.close(bead_id, reason="assumption answered")
        details = await client.show(bead_id)
    except BeadError as exc:
        raise AssumptionLedgerError(f"Failed to answer {bead_id}: {exc}") from exc

    logger.info("assumption_answered", bead_id=bead_id)
    return _record_from_details(details)


async def waive(
    client: BeadClient,
    *,
    bead_id: str,
    reason: str,
    waived_by: str,
) -> AssumptionRecord:
    """Record a waiver (who/when/why), mark the entry waived, and close it.

    Closing releases any ``blocks`` edges wired for this entry (bd's own
    dependency-release semantics).

    Raises:
        AssumptionLedgerError: If *reason* is empty, or on bd failure.
    """
    if not reason or not reason.strip():
        raise AssumptionLedgerError("Waive reason must not be empty")

    waived_at = datetime.now(UTC).isoformat()
    try:
        await client.set_state(
            bead_id,
            {
                KEY_WAIVED_BY: waived_by,
                KEY_WAIVED_AT: waived_at,
                KEY_WAIVE_REASON: reason,
                KEY_STATUS: STATUS_WAIVED,
            },
            reason="assumption waived",
        )
        await client.close(bead_id, reason=f"waived: {reason[:200]}")
        details = await client.show(bead_id)
    except BeadError as exc:
        raise AssumptionLedgerError(f"Failed to waive {bead_id}: {exc}") from exc

    logger.info("assumption_waived", bead_id=bead_id, waived_by=waived_by)
    return _record_from_details(details)


async def open_blocking_entries(client: BeadClient) -> tuple[AssumptionRecord, ...]:
    """Open entries with severity in {medium, high} — powers the land gate.

    Includes legacy escalation beads (``assumption-review`` label without
    ``assumption``), surfaced with ``severity=medium``/``is_legacy=True``.
    """
    try:
        candidates = await client.query("type=task AND status=open")
    except BeadError as exc:
        raise AssumptionLedgerError(f"Failed to query open task beads: {exc}") from exc

    records: list[AssumptionRecord] = []
    for candidate in candidates:
        try:
            details = await client.show(candidate.id)
        except BeadError as exc:
            raise AssumptionLedgerError(f"Failed to load bead {candidate.id}: {exc}") from exc
        labels = details.labels or []
        if ASSUMPTION_LABEL in labels:
            record = _record_from_details(details)
            if record.status == STATUS_OPEN and record.severity in (
                Severity.MEDIUM,
                Severity.HIGH,
            ):
                records.append(record)
        elif ASSUMPTION_REVIEW_LABEL in labels:
            records.append(_legacy_record_from_details(details))
    return tuple(records)


async def open_high_entries_before(
    client: BeadClient,
    *,
    epic_id: str,
) -> tuple[AssumptionRecord, ...]:
    """Open high-severity entries owned by specs ordered before *epic_id*.

    Powers ``_chain_epic`` wiring at refuel time (research R8). Returns an
    empty tuple when *epic_id* has no ``speckit_feature`` NNN prefix.
    """
    try:
        epic_details = await client.show(epic_id)
    except BeadError as exc:
        raise AssumptionLedgerError(f"Failed to load epic {epic_id}: {exc}") from exc

    target_prefix = nnn_prefix((epic_details.state or {}).get(EPIC_KEY_SPECKIT_FEATURE, ""))
    if target_prefix is None:
        return ()

    try:
        candidates = await client.query("type=task AND status=open")
    except BeadError as exc:
        raise AssumptionLedgerError(f"Failed to query open task beads: {exc}") from exc

    records: list[AssumptionRecord] = []
    for candidate in candidates:
        try:
            details = await client.show(candidate.id)
        except BeadError as exc:
            raise AssumptionLedgerError(f"Failed to load bead {candidate.id}: {exc}") from exc
        if ASSUMPTION_LABEL not in (details.labels or []):
            continue
        record = _record_from_details(details)
        if record.severity is not Severity.HIGH or record.status != STATUS_OPEN:
            continue
        owner_prefix = nnn_prefix(record.owner_spec)
        if owner_prefix is not None and owner_prefix < target_prefix:
            records.append(record)
    return tuple(records)
