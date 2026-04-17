"""Thespian actor definitions for Maverick's actor-mailbox architecture."""

from __future__ import annotations

import atexit
import logging as _logging
import os
import socket
import time
from typing import Any

from maverick.logging import get_logger

logger = get_logger(__name__)

THESPIAN_PORT = 19500


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def _force_kill_port(port: int) -> None:
    """Find and kill any process listening on *port*."""
    import signal
    import subprocess

    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        pids = result.stdout.strip().split()
        for pid_str in pids:
            try:
                pid = int(pid_str)
                os.kill(pid, signal.SIGKILL)
                logger.debug("actors.force_killed_pid", pid=pid, port=port)
            except (ValueError, OSError):
                pass
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass


def cleanup_stale_admin(port: int = THESPIAN_PORT) -> None:
    """Shut down a stale Thespian admin daemon on *port*, if any.

    The Thespian admin daemon survives the parent process on Ctrl-C.
    Call this before creating a new ActorSystem to avoid
    "not a valid or useable ActorSystem Admin" errors.

    Tries a graceful Thespian shutdown first, then falls back to
    force-killing the process holding the port.
    """
    if not _port_in_use(port):
        return

    logger.debug("actors.stale_admin_detected", port=port)

    from thespian.actors import ActorSystem

    try:
        stale = ActorSystem(
            "multiprocTCPBase",
            capabilities={"Admin Port": port},
        )
        stale.shutdown()
    except Exception as exc:
        logger.debug("actors.stale_admin_shutdown_failed", error=str(exc))

    # Wait up to 5s for graceful shutdown
    for _ in range(10):
        time.sleep(0.5)
        if not _port_in_use(port):
            return

    # Graceful shutdown didn't work — force kill
    logger.debug("actors.stale_admin_force_killing", port=port)
    _force_kill_port(port)

    # Wait up to 3s more for port to free after kill
    for _ in range(6):
        time.sleep(0.5)
        if not _port_in_use(port):
            return

    logger.warning("actors.stale_admin_port_still_in_use", port=port)


def create_actor_system(port: int = THESPIAN_PORT) -> Any:
    """Create a Thespian ActorSystem with stale-admin cleanup and atexit handler.

    Returns the ActorSystem instance. Registers an atexit handler that
    shuts it down cleanly (with log suppression) on process exit.
    """
    from thespian.actors import ActorSystem

    cleanup_stale_admin(port)

    asys = ActorSystem(
        "multiprocTCPBase",
        capabilities={"Admin Port": port},
    )

    def _cleanup_actor_system() -> None:
        root = _logging.getLogger()
        prev = root.level
        root.setLevel(_logging.CRITICAL)
        try:
            asys.shutdown()
        except Exception:
            pass
        finally:
            root.setLevel(prev)

    atexit.register(_cleanup_actor_system)

    return asys
