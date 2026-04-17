"""Thespian actor definitions for Maverick's actor-mailbox architecture."""

from __future__ import annotations

import atexit
import logging as _logging
import socket
import time
from typing import Any

from maverick.logging import get_logger

logger = get_logger(__name__)

THESPIAN_PORT = 19500


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def cleanup_stale_admin(port: int = THESPIAN_PORT) -> None:
    """Shut down a stale Thespian admin daemon on *port*, if any.

    The Thespian admin daemon survives the parent process on Ctrl-C.
    Call this before creating a new ActorSystem to avoid
    "not a valid or useable ActorSystem Admin" errors.

    Blocks up to 10s waiting for the port to free.
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

    for _ in range(20):
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
