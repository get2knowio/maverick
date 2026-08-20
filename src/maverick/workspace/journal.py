"""In-progress application journal and cross-run advisory lock.

``ApplicationRecord`` (FR-049) and the pid-stamped lock (FR-048), modeled
byte-for-byte on ``workflows/reconcile/state.py``'s lock pattern (research.md
R8). The journal answers "did a previous run die mid-application?" and must
survive the process; the lock answers "is another run live?" and dies with
it.

**Contention semantics diverge from `notify`, follow `reconcile`**: a held
lock is a hard refusal naming the pid, never a benign skip — two isolated
runs in one checkout can destroy each other's work inside the undo window
(research.md R8).
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from maverick.logging import get_logger

__all__ = [
    "ApplicationRecord",
    "acquire_lock",
    "clear_record",
    "holding_pid",
    "read_record",
    "release_lock",
    "write_record",
]

logger = get_logger(__name__)

_RUNS_SUBDIR = Path(".maverick") / "runs"
_JOURNAL_FILENAME = "isolation-journal.json"
_LOCK_FILENAME = "isolation.lock"

#: The only schema version this module has ever written.
_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class ApplicationRecord:
    """The in-progress marker (FR-049).

    Written before a fold-back or an undo begins, cleared once it
    completes. Invariant: at most one record exists at a time — a direct
    consequence of FR-015 and FR-048.

    Attributes:
        schema_version: ``1``.
        run_id: Owning run.
        workflow: ``"fly"`` / ``"spec-chain"``.
        unit_key: Which unit was mid-application.
        operation: Which direction was in flight.
        restore_operation_id: The jj operation to rewind to — the recovery
            handle handed to the user.
        workspace_path: Where the delta still lives.
        started_at: Injected, never ``datetime.now()`` internally.
    """

    run_id: str
    workflow: str
    unit_key: str
    operation: str
    restore_operation_id: str
    workspace_path: str
    started_at: datetime
    schema_version: int = _SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        d = asdict(self)
        d["started_at"] = self.started_at.isoformat()
        return d

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> ApplicationRecord:
        payload = dict(data)
        started_at = payload["started_at"]
        if isinstance(started_at, str):
            payload["started_at"] = datetime.fromisoformat(started_at)
        return cls(**payload)  # type: ignore[arg-type]


def _journal_path(checkout: Path) -> Path:
    return checkout / _RUNS_SUBDIR / _JOURNAL_FILENAME


def _lock_path(checkout: Path) -> Path:
    return checkout / _RUNS_SUBDIR / _LOCK_FILENAME


async def write_record(checkout: Path, record: ApplicationRecord) -> None:
    """Atomically persist *record* to
    ``<checkout>/.maverick/runs/isolation-journal.json`` (temp + rename,
    same pattern as ``notify/state.py``/``reconcile/state.py``)."""
    from maverick.utils.atomic import atomic_write_text

    path = _journal_path(checkout)
    content = json.dumps(record.to_dict(), indent=2)
    await asyncio.to_thread(atomic_write_text, path, content, mkdir=True)
    logger.debug(
        "isolation_journal_written",
        unit_key=record.unit_key,
        operation=record.operation,
        workspace_path=record.workspace_path,
    )


async def read_record(checkout: Path) -> ApplicationRecord | None:
    """The current journal record, or ``None`` if none exists."""
    path = _journal_path(checkout)
    if not await asyncio.to_thread(path.is_file):
        return None
    text = await asyncio.to_thread(path.read_text, encoding="utf-8")
    return ApplicationRecord.from_dict(json.loads(text))


async def clear_record(checkout: Path) -> None:
    """Remove the journal file. Idempotent — clearing an already-absent
    record is not an error."""
    path = _journal_path(checkout)

    def _clear() -> None:
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    await asyncio.to_thread(_clear)


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


async def acquire_lock(checkout: Path) -> bool:
    """Acquire the run-scoped isolation lockfile.

    Mirrors ``workflows/reconcile/state.py``'s ``acquire_lock`` byte-for-
    byte (research.md R8). Returns ``True`` if the lock was acquired (the
    current pid is now stamped into
    ``.maverick/runs/isolation.lock``), ``False`` if a live process
    already holds it. A malformed or unreadable existing lockfile is
    treated as stale and reclaimed, same as a lockfile naming a dead pid.
    """
    lock_path = _lock_path(checkout)

    def _try_acquire() -> bool:
        if lock_path.is_file():
            try:
                existing_pid = int(lock_path.read_text(encoding="utf-8").strip())
            except (OSError, ValueError) as exc:
                logger.debug(
                    "isolation_lock_malformed_reclaimed", path=str(lock_path), error=str(exc)
                )
            else:
                if _pid_is_alive(existing_pid):
                    return False
                logger.debug("isolation_lock_stale_reclaimed", stale_pid=existing_pid)
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.write_text(str(os.getpid()), encoding="utf-8")
        return True

    return await asyncio.to_thread(_try_acquire)


async def release_lock(checkout: Path) -> None:
    """Release the isolation lockfile. Best-effort: no error if missing."""
    lock_path = _lock_path(checkout)

    def _release() -> None:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass

    await asyncio.to_thread(_release)


def holding_pid(checkout: Path) -> int | None:
    """The pid currently named in the lockfile, if it exists and is
    well-formed (regardless of liveness) — used to build
    ``IsolationLockedError``'s message when acquisition fails."""
    lock_path = _lock_path(checkout)
    if not lock_path.is_file():
        return None
    try:
        return int(lock_path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
