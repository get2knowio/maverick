"""Persisted delivery state for the assumption batch scheduler (`maverick notify`).

State is persisted to ``<cwd>/.maverick/notify/state.json`` (schema_version 1)
via whole-file atomic writes (``maverick.utils.atomic.atomic_write_json``).
Unlike per-run state under ``.maverick/runs/<run-id>/``, this file is
cross-run: idempotence (FR-010), delivery history (FR-011), and escalation
backoff (FR-006/FR-007) all span invocations, so it lives in a stable
feature directory instead. Concurrency is guarded by a pid-stamped advisory
lockfile at ``<cwd>/.maverick/notify/lock``, mirroring
``maverick.workflows.reconcile.state``'s ``acquire_lock``/``release_lock``/
``_pid_is_alive`` pattern byte-for-byte (research.md R4).

See specs/054-assumption-batch-scheduler/data-model.md §4 and
specs/054-assumption-batch-scheduler/contracts/delivery-state-schema.md for
the full schema and invariants.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from maverick.assumptions.schedule.models import DecisionKind, format_utc, parse_utc
from maverick.exceptions.base import MaverickError
from maverick.logging import get_logger
from maverick.utils.atomic import atomic_write_json

if TYPE_CHECKING:
    from maverick.assumptions.schedule.models import DeliveryDecision, EvaluationOutcome

__all__ = [
    "DeliveryRecord",
    "DeliveryState",
    "DeliveryStateSchemaError",
    "EntryTrackingRecord",
    "TerminalOutcome",
    "WindowDecisionRecord",
    "acquire_lock",
    "finalize_state",
    "load_state",
    "prune",
    "release_lock",
    "save_state",
]

logger = get_logger(__name__)

_NOTIFY_SUBDIR = Path(".maverick") / "notify"
_STATE_FILENAME = "state.json"
_LOCK_FILENAME = "lock"

#: Only schema_version 1 is understood. Any other value is refused rather
#: than silently rewritten (contracts/delivery-state-schema.md invariant 7).
_SUPPORTED_SCHEMA_VERSION = 1

#: FR-023 retention window: a terminal entry's tracking row (and the
#: deliveries/window_decisions records that reference only terminal
#: entries) become prunable 90 days after the terminal transition.
_RETENTION = timedelta(days=90)


class DeliveryStateSchemaError(MaverickError):
    """Raised when persisted notify state carries an unsupported schema_version.

    Per contracts/delivery-state-schema.md invariant 7: an unrecognized
    ``schema_version`` must never be silently rewritten — evaluation refuses
    with a clear error instead of guessing at the shape of a newer schema.
    """


class WindowDecisionRecord(BaseModel):
    """One decided window occurrence, keyed ``"YYYY-MM-DD/HH:MM"`` in
    :attr:`DeliveryState.window_decisions` — the idempotence ledger for
    occurrences (FR-010)."""

    model_config = ConfigDict(frozen=True)

    outcome: Literal["delivered", "skipped-min-batch", "empty"] = Field(
        description="What happened to this occurrence"
    )
    decided_at: str = Field(description="UTC ISO-8601 timestamp of the decision")
    entry_ids: list[str] = Field(
        default_factory=list, description="Bead ids covered by this decision"
    )
    rule: str = Field(description="Human-readable rule citation for audit (SC-004)")


class TerminalOutcome(BaseModel):
    """Terminal state for a tracked entry (FR-016: nothing leaves silently).

    Starts the FR-023 90-day retention clock via :attr:`at`.
    """

    model_config = ConfigDict(frozen=True)

    kind: Literal["resolved-by-human", "auto-waived"] = Field(
        description="How the entry left tracking"
    )
    at: str = Field(description="UTC ISO-8601 timestamp; starts the retention clock")
    detail: str | None = Field(default=None, description="Auto-waive rationale, if applicable")


class EntryTrackingRecord(BaseModel):
    """Per-entry scheduler state, keyed by bead id in
    :attr:`DeliveryState.entry_tracking`."""

    model_config = ConfigDict(frozen=True)

    first_seen: str = Field(description="Fallback age basis when created_at is missing (R1)")
    severity: str = Field(description="Severity as evaluated (legacy entries => 'medium')")
    interrupt_delivered_at: str | None = Field(
        default=None, description="High-tier first delivery timestamp (FR-002)"
    )
    escalation_delivered_at: str | None = Field(
        default=None, description="Max-age escalation delivery timestamp (FR-006)"
    )
    renotify_count: int = Field(default=0, description="Index into the backoff ladder (FR-007)")
    next_renotify_at: str | None = Field(
        default=None, description="Precomputed next backoff instant"
    )
    terminal: TerminalOutcome | None = Field(
        default=None, description="Set once the scheduler observes/creates terminal state"
    )


class DeliveryRecord(BaseModel):
    """One append-only audit trail entry in :attr:`DeliveryState.deliveries`
    (FR-011). Only written after the underlying ntfy POST succeeded
    (FR-012)."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["window-batch", "interrupt", "escalation", "renotify"] = Field(
        description="Delivery kind"
    )
    delivered_at: str = Field(description="UTC ISO-8601; only set after ntfy success")
    trigger: str = Field(description="Occurrence key or rule citation")
    entry_ids: list[str] = Field(default_factory=list, description="Bead ids covered")
    summary: dict[str, Any] = Field(description="Serialized BatchSummary")


class DeliveryState(BaseModel):
    """Top-level persisted state, round-tripped to
    ``<cwd>/.maverick/notify/state.json`` (contracts/delivery-state-schema.md)."""

    model_config = ConfigDict(frozen=True)

    schema_version: int = Field(default=1, description="Guards future migrations")
    updated_at: str = Field(description="UTC ISO-8601 timestamp of last update")
    window_decisions: dict[str, WindowDecisionRecord] = Field(
        default_factory=dict, description="Occurrence idempotence ledger (FR-010)"
    )
    entry_tracking: dict[str, EntryTrackingRecord] = Field(
        default_factory=dict, description="Per-entry scheduler state, keyed by bead id"
    )
    deliveries: list[DeliveryRecord] = Field(
        default_factory=list, description="Append-only audit trail (FR-011)"
    )


def _utc_now_iso() -> str:
    """Current UTC instant as ``"YYYY-MM-DDTHH:MM:SSZ"`` (house convention)."""
    return format_utc(datetime.now(UTC))


def _empty_state() -> DeliveryState:
    return DeliveryState(updated_at=_utc_now_iso())


def _state_path(cwd: Path) -> Path:
    return cwd / _NOTIFY_SUBDIR / _STATE_FILENAME


def _lock_path(cwd: Path) -> Path:
    return cwd / _NOTIFY_SUBDIR / _LOCK_FILENAME


async def load_state(cwd: Path) -> DeliveryState:
    """Load persisted delivery state from ``<cwd>/.maverick/notify/state.json``.

    A missing file returns a fresh empty state (first run). A corrupt or
    unparseable file also degrades to an empty state, logged as a structured
    warning: delivery history is lost but behavior stays safe (worst case is
    one re-delivery, never a missed entry — contracts/delivery-state-schema.md
    invariant 7). A file carrying an unsupported ``schema_version`` is a hard
    refusal — see :class:`DeliveryStateSchemaError`.

    Args:
        cwd: Repository root, resolved once at the CLI boundary.

    Returns:
        The persisted state, or an empty :class:`DeliveryState` if none
        exists or the file is unreadable.

    Raises:
        DeliveryStateSchemaError: ``schema_version`` is present and not 1.
    """
    path = _state_path(cwd)
    if not await asyncio.to_thread(path.is_file):
        return _empty_state()

    try:
        text = await asyncio.to_thread(path.read_text, encoding="utf-8")
        raw = json.loads(text)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("notify_state_corrupt", path=str(path), error=str(exc))
        return _empty_state()

    schema_version = raw.get("schema_version") if isinstance(raw, dict) else None
    if schema_version is not None and schema_version != _SUPPORTED_SCHEMA_VERSION:
        raise DeliveryStateSchemaError(
            f"Unsupported notify state schema_version {schema_version!r} at "
            f"{path} (expected {_SUPPORTED_SCHEMA_VERSION}); refusing to "
            "evaluate rather than silently rewrite a newer schema."
        )

    try:
        return DeliveryState.model_validate(raw)
    except ValidationError as exc:
        logger.warning("notify_state_corrupt", path=str(path), error=str(exc))
        return _empty_state()


async def save_state(state: DeliveryState, cwd: Path) -> None:
    """Atomically persist *state* to ``<cwd>/.maverick/notify/state.json``.

    Args:
        state: The delivery state to persist. Callers own setting
            ``updated_at`` before calling (write-after-success discipline —
            contracts/delivery-state-schema.md invariant 2 — means this is
            called once per run, after effects complete).
        cwd: Repository root, resolved once at the CLI boundary.
    """
    path = _state_path(cwd)
    content = state.model_dump(mode="json")
    await asyncio.to_thread(atomic_write_json, path, content)


def _pid_is_alive(pid: int) -> bool:
    """Whether *pid* refers to a live process.

    ``ProcessLookupError`` means the pid is dead (reclaim the lock).
    ``PermissionError`` means it's alive but owned by another user (treat
    as live — we can't reclaim what we can't verify is dead).
    """
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


async def acquire_lock(cwd: Path) -> bool:
    """Acquire the notify lockfile at ``<cwd>/.maverick/notify/lock``.

    Mirrors ``maverick.workflows.reconcile.state.acquire_lock`` byte-for-byte
    (research.md R4): a malformed or unreadable existing lockfile, or one
    naming a dead pid, is treated as stale and reclaimed. Contention against
    a live holder is a benign skip for `maverick notify` (research.md R7),
    not an error — the caller decides what that means for exit status.

    Args:
        cwd: Repository root, resolved once at the CLI boundary.

    Returns:
        ``True`` if the lock was acquired (current pid now stamped into the
        lockfile), ``False`` if a live process already holds it.
    """
    lock_path = _lock_path(cwd)

    def _try_acquire() -> bool:
        if lock_path.is_file():
            try:
                existing_pid = int(lock_path.read_text(encoding="utf-8").strip())
            except (OSError, ValueError) as exc:
                logger.debug(
                    "notify_lock_malformed_reclaimed", path=str(lock_path), error=str(exc)
                )
            else:
                if _pid_is_alive(existing_pid):
                    return False
                logger.debug("notify_lock_stale_reclaimed", stale_pid=existing_pid)
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.write_text(str(os.getpid()), encoding="utf-8")
        return True

    return await asyncio.to_thread(_try_acquire)


async def release_lock(cwd: Path) -> None:
    """Release the notify lockfile. Best-effort: no error if missing.

    Args:
        cwd: Repository root, resolved once at the CLI boundary.
    """
    lock_path = _lock_path(cwd)

    def _release() -> None:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass

    await asyncio.to_thread(_release)


def prune(state: DeliveryState, now: datetime) -> DeliveryState:
    """Apply the FR-023 retention rule to *state*.

    An ``entry_tracking`` row is prunable once its :attr:`TerminalOutcome.at`
    is at least 90 days before *now*. A ``deliveries`` record or a
    ``window_decisions`` key is prunable when every entry id it references
    is itself prunable; a record referencing any still-open entry is never
    pruned (contracts/delivery-state-schema.md invariants 5 and 6).

    A record referencing *zero* entries — an ``"empty"`` window decision,
    the audit trail for "why was nothing delivered at 09:00" — satisfies
    that rule vacuously but has no entry to date it, so it falls back to
    its own decision timestamp (``decided_at`` / ``delivered_at``) against
    the same 90-day horizon. Keeping such records forever would make every
    quiet window occurrence immortal state (three windows a day against a
    quiet ledger is ~1,100 permanent keys a year, rewritten in full on
    every cron fire); pruning them immediately would destroy the audit
    trail inside the review horizon.

    An entry id that isn't present in ``entry_tracking`` at all is
    conservatively treated as not prunable — unknown status errs toward
    "open". An unparseable timestamp is likewise treated as not prunable.

    Args:
        state: The state to prune.
        now: Aware datetime to measure retention against (UTC recommended;
            any aware datetime works since terminal timestamps are UTC).

    Returns:
        A new :class:`DeliveryState` with prunable records removed;
        *state* itself is never mutated.
    """

    def _retained_elapsed(timestamp: str) -> bool:
        moment = parse_utc(timestamp)
        return moment is not None and (now - moment) >= _RETENTION

    def _entry_prunable(entry_id: str) -> bool:
        record = state.entry_tracking.get(entry_id)
        if record is None or record.terminal is None:
            return False
        return _retained_elapsed(record.terminal.at)

    def _record_prunable(entry_ids: list[str], own_timestamp: str) -> bool:
        if not entry_ids:
            return _retained_elapsed(own_timestamp)
        return all(_entry_prunable(eid) for eid in entry_ids)

    pruned_entry_tracking = {
        entry_id: record
        for entry_id, record in state.entry_tracking.items()
        if not _entry_prunable(entry_id)
    }
    pruned_window_decisions = {
        key: record
        for key, record in state.window_decisions.items()
        if not _record_prunable(record.entry_ids, record.decided_at)
    }
    pruned_deliveries = [
        record
        for record in state.deliveries
        if not _record_prunable(record.entry_ids, record.delivered_at)
    ]

    return state.model_copy(
        update={
            "entry_tracking": pruned_entry_tracking,
            "window_decisions": pruned_window_decisions,
            "deliveries": pruned_deliveries,
        }
    )


#: The :class:`EntryTrackingRecord` fields each per-entry decision kind
#: stamps speculatively, and which therefore must be reverted when that
#: decision's ntfy push fails (FR-012).
#: :attr:`DecisionKind.WINDOW_BATCH` owns no per-entry field — its
#: idempotence lives entirely in ``window_decisions`` — so it is absent.
_ENTRY_TRACKING_FIELDS_BY_KIND: dict[DecisionKind, tuple[str, ...]] = {
    DecisionKind.INTERRUPT: ("interrupt_delivered_at",),
    DecisionKind.ESCALATION: ("escalation_delivered_at",),
    DecisionKind.RENOTIFY: ("renotify_count", "next_renotify_at"),
}


def _revert_entry_tracking_mutation(
    entry_tracking: dict[str, EntryTrackingRecord],
    prior_tracking: dict[str, EntryTrackingRecord],
    decision: DeliveryDecision,
) -> dict[str, EntryTrackingRecord]:
    """Undo one failed decision's speculative ``entry_tracking`` mutation (FR-012).

    Per-entry decision kinds stamp a "delivered" marker on each covered
    entry's :class:`EntryTrackingRecord` speculatively, before the effects
    layer (``maverick notify``) knows whether the ntfy push actually
    succeeded (mirrors how
    :func:`~maverick.assumptions.schedule.evaluate.evaluate` speculatively
    records window decisions). A failed push must leave the marker exactly
    as it was before this evaluation, so the entry is due again next time;
    this is the per-entry counterpart to the window_decisions-keyed
    reversion in :func:`finalize_state`.

    Every per-entry kind is covered via
    :data:`_ENTRY_TRACKING_FIELDS_BY_KIND`, not just INTERRUPT: an
    unreverted ESCALATION would leave ``escalation_delivered_at`` stamped
    on an entry whose push never landed, and escalation fires *exactly
    once* — so that entry would never escalate again. An unreverted
    RENOTIFY would likewise advance the backoff ladder without delivering.
    :attr:`DecisionKind.WINDOW_BATCH` owns no per-entry field and is a
    no-op here.

    Args:
        entry_tracking: The candidate ``entry_tracking`` mapping to revert
            (typically ``outcome.state_after.entry_tracking``) — this
            function returns a new dict rather than mutating in place.
        prior_tracking: ``prior_state.entry_tracking``, the pre-evaluation
            baseline to revert back to.
        decision: The delivery decision whose ntfy push failed.

    Returns:
        A new mapping with *decision*'s per-entry markers reverted for each
        of its ``entry_ids``.
    """
    fields = _ENTRY_TRACKING_FIELDS_BY_KIND.get(decision.kind)
    if fields is None:
        return entry_tracking

    reverted = dict(entry_tracking)
    for bead_id in decision.entry_ids:
        current = reverted.get(bead_id)
        if current is None:
            continue
        prior = prior_tracking.get(bead_id)
        update = {
            name: (
                getattr(prior, name)
                if prior is not None
                else EntryTrackingRecord.model_fields[name].get_default()
            )
            for name in fields
        }
        reverted[bead_id] = current.model_copy(update=update)
    return reverted


def finalize_state(
    *,
    outcome: EvaluationOutcome,
    prior_state: DeliveryState,
    failed_indices: Iterable[int],
    now: datetime,
) -> DeliveryState:
    """Strip failed decisions' mutations out of ``outcome.state_after`` (FR-012).

    :func:`~maverick.assumptions.schedule.evaluate.evaluate` builds
    ``outcome.state_after`` assuming every delivery decision's ntfy push
    succeeds (its own docstring says as much) — this is the pure,
    effects-adjacent counterpart that reverts exactly the window-decision
    keys, per-entry tracking markers, and audit-trail records belonging to
    decisions whose delivery actually failed, so the underlying
    occurrence/entry stays undecided (and therefore due again) on the next
    evaluation. A decision that succeeds is recorded individually — a
    partial-success run (some due decisions deliver, others fail) persists
    exactly the successes. Also applies FR-023 retention pruning to
    whatever survives.

    This function performs no I/O — the ``notify`` CLI command is
    responsible for calling :func:`save_state` with its result.

    Args:
        outcome: The :class:`~maverick.assumptions.schedule.models.EvaluationOutcome`
            returned by ``evaluate()``.
        prior_state: The state ``evaluate()`` was called with — the
            pre-evaluation baseline every failed decision reverts to.
        failed_indices: Positions into ``outcome.deliveries`` whose ntfy
            push failed. Empty means every decision succeeded.
        now: The same aware local ``now`` passed to ``evaluate()``, used
            for FR-023 retention pruning.

    Returns:
        A new :class:`DeliveryState` ready to persist via
        :func:`save_state`.
    """
    state_after = outcome.state_after
    failed = set(failed_indices)
    if not failed:
        return prune(state_after, now.astimezone(UTC))

    revert_keys: set[str] = set()
    entry_tracking = dict(state_after.entry_tracking)
    for i in failed:
        decision = outcome.deliveries[i]
        if decision.occurrence is not None:
            revert_keys.add(decision.occurrence.key)
        entry_tracking = _revert_entry_tracking_mutation(
            entry_tracking, prior_state.entry_tracking, decision
        )
    window_decisions = {
        key: record
        for key, record in state_after.window_decisions.items()
        if key not in revert_keys
    }

    # `state_after.deliveries` is `[*prior_state.deliveries, *delivery_records]`
    # (evaluate.py), and `delivery_records` is built 1:1, in order, with
    # `outcome.deliveries` — so the tail past `prior_state.deliveries` lines
    # up index-for-index with `outcome.deliveries`.
    original_count = len(prior_state.deliveries)
    new_records = state_after.deliveries[original_count:]
    kept_records = [record for i, record in enumerate(new_records) if i not in failed]
    final_deliveries = [*prior_state.deliveries, *kept_records]

    final_state = state_after.model_copy(
        update={
            "window_decisions": window_decisions,
            "entry_tracking": entry_tracking,
            "deliveries": final_deliveries,
        }
    )
    return prune(final_state, now.astimezone(UTC))
