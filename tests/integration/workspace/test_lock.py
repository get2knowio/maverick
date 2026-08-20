"""Contract test for `IsolationSession`'s cross-run exclusivity lock.

Covers tasks.md T043 -- contract C1 / the contract-test table's T12
(specs/057-isolated-bead-workspaces/contracts/isolation-primitive.md,
"Second session in the same checkout refuses, naming the pid", FR-048).

Contract C1: `__aenter__` acquires `<checkout>/.maverick/runs/isolation.lock`.
A live holder raises `IsolationLockedError` naming the holding pid. A
malformed lockfile or one naming a dead pid is reclaimed. `__aexit__`
releases it.

research.md R8: the lock is modeled byte-for-byte on
`workflows/reconcile/state.py`'s pid-stamped advisory lockfile, including
malformed-or-dead-pid reclamation -- but contention semantics deliberately
diverge from `notify`'s benign concurrent-evaluation skip. `notify` treats a
held lock as expected operation (overlapping cron fires). Two isolated fly
runs in one checkout are *not* expected operation -- they can destroy each
other's work inside the undo window -- so a held lock here is a hard,
pid-named refusal (`IsolationLockedError`), never a silent skip.

"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from maverick.jj.client import JjClient
from maverick.workspace import (
    IsolationLockedError,
    IsolationPolicy,
    IsolationSession,
)

pytestmark = pytest.mark.integration

_LOCK_RELPATH = Path(".maverick") / "runs" / "isolation.lock"


def _fixed_now() -> datetime:
    """A deterministic clock -- the primitive never calls `datetime.now()`
    directly (054's clock-seam convention, reused throughout this suite)."""
    return datetime(2026, 8, 20, 12, 0, 0, tzinfo=UTC)


def _policy(*, root: Path, workflow: str = "test-workflow") -> IsolationPolicy:
    return IsolationPolicy(workflow=workflow, root=root)


def _make_session(
    colocated_repo: JjClient,
    isolation_home: Path,
    *,
    run_id: str,
) -> IsolationSession:
    return IsolationSession(
        checkout=colocated_repo.cwd,
        policy=_policy(root=isolation_home),
        jj_client=colocated_repo,
        run_id=run_id,
        now=_fixed_now,
        home=isolation_home,
    )


def _write_lock(checkout: Path, content: str) -> Path:
    lock_path = checkout / _LOCK_RELPATH
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(content, encoding="utf-8")
    return lock_path


# ---------------------------------------------------------------------------
# T043a -- live-holder refusal: a lockfile naming a pid that is genuinely
# alive for the duration of this test (our own pid) must refuse entry.
# ---------------------------------------------------------------------------


async def test_second_session_refuses_when_live_pid_holds_lock(
    colocated_repo: JjClient, isolation_home: Path
) -> None:
    """A lockfile stamped with the current process's own pid -- guaranteed
    live for the duration of this test -- must cause `__aenter__` to raise
    `IsolationLockedError` naming that exact pid, and must leave the
    lockfile untouched (no reclamation of a live holder).
    """
    own_pid = os.getpid()
    lock_path = _write_lock(colocated_repo.cwd, str(own_pid))

    session = _make_session(colocated_repo, isolation_home, run_id="run-live-holder")

    with pytest.raises(IsolationLockedError) as exc_info:
        async with session:
            pass  # Entry itself must raise -- the body must never run.

    assert exc_info.value.pid == own_pid
    # The lockfile is untouched -- refusing a live holder must never
    # overwrite its stamp.
    assert lock_path.read_text(encoding="utf-8").strip() == str(own_pid)


# ---------------------------------------------------------------------------
# T043b -- dead-pid reclamation: a lockfile naming a pid from a subprocess
# that has already exited must be silently reclaimed, not refused.
# ---------------------------------------------------------------------------


async def test_session_reclaims_lock_naming_a_dead_pid(
    colocated_repo: JjClient, isolation_home: Path
) -> None:
    """A stale lockfile naming a pid that is no longer running must be
    reclaimed on entry: `__aenter__` succeeds, and the lockfile ends up
    stamped with the entering session's own pid.

    Mirrors `workflows/reconcile/state.py`'s
    `test_acquire_lock_reclaims_stale_lock`.
    """
    # Fork a genuinely short-lived subprocess and wait for it to exit so
    # its pid is guaranteed dead, then stamp the lockfile with that dead
    # pid -- mirrors reconcile's `test_acquire_lock_reclaims_stale_lock`.
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    dead_pid = proc.pid
    proc.wait(timeout=5)
    lock_path = _write_lock(colocated_repo.cwd, str(dead_pid))

    session = _make_session(colocated_repo, isolation_home, run_id="run-dead-pid")

    async with session:
        # Reclamation restamps the lockfile with the entering session's
        # own pid -- it must not merely tolerate the dead entry.
        assert lock_path.read_text(encoding="utf-8").strip() == str(os.getpid())


# ---------------------------------------------------------------------------
# T043c -- malformed lockfile reclamation: garbage content must be treated
# as stale, same as a dead pid.
# ---------------------------------------------------------------------------


async def test_session_reclaims_malformed_lockfile(
    colocated_repo: JjClient, isolation_home: Path
) -> None:
    """A lockfile whose content isn't a parseable pid at all (`"not-a-pid"`)
    must be treated as stale and reclaimed, exactly like a dead pid --
    `__aenter__` must succeed rather than raise.

    Mirrors `workflows/reconcile/state.py`'s
    `test_acquire_lock_treats_malformed_lockfile_as_stale`.
    """
    _write_lock(colocated_repo.cwd, "not-a-pid")

    session = _make_session(colocated_repo, isolation_home, run_id="run-malformed")

    async with session:
        pass  # Entry must not raise -- the malformed lockfile is reclaimed.


# ---------------------------------------------------------------------------
# T043d -- release on exit: a clean exit must release the lock so a
# subsequent session in the same checkout can enter cleanly.
# ---------------------------------------------------------------------------


async def test_lock_is_released_on_clean_exit_allowing_a_second_session(
    colocated_repo: JjClient, isolation_home: Path
) -> None:
    """After a session enters and exits cleanly, a second, independent
    session over the same checkout must also be able to enter cleanly --
    the first session's `__aexit__` must have released the lock rather
    than leaving it stamped with a (now-dead-relative-to-the-second-
    session) pid.
    """
    first_session = _make_session(colocated_repo, isolation_home, run_id="run-first")
    second_session = _make_session(colocated_repo, isolation_home, run_id="run-second")

    async with first_session:
        pass

    async with second_session:
        pass  # Must not raise IsolationLockedError -- the first release worked.
