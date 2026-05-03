"""Process-group-aware kill helper.

When a subprocess is spawned with ``start_new_session=True`` it becomes
the leader of its own process group. Killing the leader leaves
grandchildren (e.g. shell pipelines, MCP servers) reparented to PID 1.
:func:`kill_process_group` sends SIGTERM/SIGKILL to the whole group via
``os.killpg`` instead, so the cleanup is exhaustive.

Synchronous on purpose so it's safe to call from ``atexit`` handlers
where an event loop may not exist.
"""

from __future__ import annotations

import os
import signal
import time

from maverick.logging import get_logger

logger = get_logger(__name__)


def kill_process_group(pid: int, *, grace_seconds: float = 2.0) -> None:
    """Send SIGTERM, wait, then SIGKILL the group of ``pid``. No-op on bad input.

    Args:
        pid: Process group id (typically the spawned subprocess's pid
            when it was created with ``start_new_session=True``).
        grace_seconds: Seconds to wait for the group to exit after
            SIGTERM before falling back to SIGKILL.
    """
    if not isinstance(pid, int) or pid <= 0:
        return
    if not _killpg(pid, signal.SIGTERM):
        return  # group already gone

    deadline = time.monotonic() + grace_seconds
    while time.monotonic() < deadline:
        # Probe with signal 0 — returns False when the group is gone.
        if not _killpg(pid, 0):
            return
        time.sleep(0.05)

    _killpg(pid, signal.SIGKILL)


def _killpg(pid: int, sig: int) -> bool:
    """Return True if the signal reached at least one process.

    Logs errors at debug level; never raises. Returns False if the
    group no longer exists (ProcessLookupError / ESRCH).
    """
    try:
        os.killpg(pid, sig)
        return True
    except ProcessLookupError:
        return False
    except PermissionError as exc:
        logger.debug("subprocess.killpg_permission", pid=pid, sig=sig, error=str(exc))
        return False
    except OSError as exc:
        logger.debug("subprocess.killpg_failed", pid=pid, sig=sig, error=str(exc))
        return False
