"""Resumable run-state persistence for reconcile (data-model.md §3).

Run state is persisted to ``.maverick/runs/<run-id>/reconcile.json``
(schema_version 1) via atomic temp-file+rename writes after every
per-answer stage transition — the same pattern as
``maverick.workflows.spec_chain.state``. Also provides a run-scoped,
pid-stamped lockfile (``.maverick/runs/reconcile.lock``) implementing
the refuse-to-start guard from research.md R9/R14.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from maverick.logging import get_logger
from maverick.utils.atomic import atomic_write_text
from maverick.workflows.reconcile.models import ReconcileStage

__all__ = [
    "AnswerState",
    "ReconcileRunState",
    "acquire_lock",
    "discover_resumable",
    "load_run_state",
    "release_lock",
    "save_run_state",
]

logger = get_logger(__name__)

_RUNS_SUBDIR = Path(".maverick") / "runs"
_STATE_FILENAME = "reconcile.json"
_LOCK_FILENAME = "reconcile.lock"

RunStatus = Literal["running", "completed", "failed"]

#: Run statuses discover_resumable treats as resumable. Reconcile has no
#: "halted" status (unlike spec-chain) — a "running" state found on disk is
#: itself the crash signal (research.md R9).
_RESUMABLE_STATUSES = frozenset({"running"})


class AnswerState(BaseModel):
    """Per-answer checkpoint nested in :class:`ReconcileRunState`.

    ``restore_op_id`` is the jj operation id captured at answer start (the
    all-or-nothing restore point, research.md R8); ``stage`` tracks progress
    through the per-answer state machine (data-model.md §3).
    """

    model_config = ConfigDict(frozen=True)

    entry_id: str = Field(description="bd bead id of the ledger entry")
    target_change_id: str | None = Field(
        description="Resolved jj correction target; None if unlocatable"
    )
    restore_op_id: str | None = Field(
        description="jj op id snapshotted at answer start (research.md R8)"
    )
    stage: ReconcileStage = Field(description="Current per-answer stage")
    terminal_status: str | None = Field(
        default=None, description="AnswerOutcome.status once terminal"
    )
    reason: str = Field(default="", description="Failure/skip reason, if any")


class ReconcileRunState(BaseModel):
    """Persisted reconcile run state.

    Written atomically to ``.maverick/runs/<run-id>/reconcile.json`` after
    every per-answer stage transition (data-model.md §3).
    """

    model_config = ConfigDict(frozen=True)

    schema_version: int = Field(default=1, description="Guards future migrations")
    run_id: str = Field(description="Matches the .maverick/runs/ directory name")
    status: RunStatus = Field(description="Overall run status")
    updated_at: str = Field(description="UTC ISO-8601 timestamp of last update")
    answers: list[AnswerState] = Field(
        default_factory=list,
        description="Per-answer checkpoints, ordered by stack_index",
    )


def _state_path(base: Path, run_id: str) -> Path:
    return base / _RUNS_SUBDIR / run_id / _STATE_FILENAME


def _lock_path(base: Path) -> Path:
    return base / _RUNS_SUBDIR / _LOCK_FILENAME


async def save_run_state(state: ReconcileRunState, base: Path) -> None:
    """Atomically persist *state* to ``.maverick/runs/<run_id>/reconcile.json``."""
    path = _state_path(base, state.run_id)
    content = json.dumps(state.model_dump(mode="json"), indent=2)
    await asyncio.to_thread(atomic_write_text, path, content, mkdir=True)


async def load_run_state(run_id: str, base: Path) -> ReconcileRunState | None:
    """Load a persisted run state by run id. ``None`` if not found."""
    path = _state_path(base, run_id)
    if not await asyncio.to_thread(path.is_file):
        return None
    text = await asyncio.to_thread(path.read_text, encoding="utf-8")
    return ReconcileRunState.model_validate(json.loads(text))


async def discover_resumable(base: Path) -> ReconcileRunState | None:
    """Scan ``.maverick/runs/*/reconcile.json`` for the newest resumable run.

    Reconcile is single-repo (not per-feature like spec-chain), so there is
    no feature filter — this simply finds the newest ``updated_at`` among
    runs with ``status == "running"``. A ``running`` state found on disk
    *is* the resumable signal (research.md R9): the run either crashed or is
    still in flight, and callers `acquire_lock` first to disambiguate.
    Corrupt or unparseable sibling state files are skipped, not fatal.
    """
    runs_dir = base / _RUNS_SUBDIR
    if not await asyncio.to_thread(runs_dir.is_dir):
        return None

    run_dirs = await asyncio.to_thread(lambda: list(runs_dir.iterdir()))
    candidates: list[ReconcileRunState] = []
    for run_dir in run_dirs:
        state_path = run_dir / _STATE_FILENAME
        if not await asyncio.to_thread(state_path.is_file):
            continue
        try:
            text = await asyncio.to_thread(state_path.read_text, encoding="utf-8")
            state = ReconcileRunState.model_validate(json.loads(text))
        except Exception as exc:
            logger.debug("reconcile_state_unreadable", path=str(state_path), error=str(exc))
            continue
        if state.status in _RESUMABLE_STATUSES:
            candidates.append(state)

    if not candidates:
        return None
    return max(candidates, key=lambda s: s.updated_at)


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


async def acquire_lock(base: Path) -> bool:
    """Acquire the run-scoped reconcile lockfile.

    Returns ``True`` if the lock was acquired (the current pid is now
    stamped into ``.maverick/runs/reconcile.lock``), ``False`` if a live
    process already holds it. A malformed or unreadable existing lockfile is
    treated as stale and reclaimed, same as a lockfile naming a dead pid.
    """
    lock_path = _lock_path(base)

    def _try_acquire() -> bool:
        if lock_path.is_file():
            try:
                existing_pid = int(lock_path.read_text(encoding="utf-8").strip())
            except (OSError, ValueError) as exc:
                logger.debug(
                    "reconcile_lock_malformed_reclaimed", path=str(lock_path), error=str(exc)
                )
            else:
                if _pid_is_alive(existing_pid):
                    return False
                logger.debug("reconcile_lock_stale_reclaimed", stale_pid=existing_pid)
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.write_text(str(os.getpid()), encoding="utf-8")
        return True

    return await asyncio.to_thread(_try_acquire)


async def release_lock(base: Path) -> None:
    """Release the reconcile lockfile. Best-effort: no error if missing."""
    lock_path = _lock_path(base)

    def _release() -> None:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass

    await asyncio.to_thread(_release)
