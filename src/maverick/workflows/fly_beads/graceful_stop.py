"""Process-level graceful-stop flag for ``maverick fly``.

The CLI's two-stage SIGINT handler sets this flag on the *first* Ctrl-C
so the running fly supervisor can finish its current bead and exit
cleanly instead of throwing away in-flight work. The supervisor's bead
loop checks the flag at each bead boundary via
:func:`is_graceful_stop_requested`. The *second* Ctrl-C bypasses this
flag entirely and cancels the workflow task — see
``maverick.cli.commands.fly._group``.

Module-level state is the right shape here:

* The signal handler runs in the asyncio loop with no easy reference to
  the in-flight ``FlySupervisor`` actor (it's owned by xoscar).
* There is exactly one fly run per process, so a singleton flag has no
  multiplexing problem.
* The supervisor's bead loop polls the flag (no callback machinery
  needed across the actor boundary).

Tests must call :func:`reset_graceful_stop` in a fixture to keep the
flag from leaking between cases.
"""

from __future__ import annotations

__all__ = [
    "is_graceful_stop_requested",
    "request_graceful_stop",
    "reset_graceful_stop",
]


_GRACEFUL_STOP_REQUESTED: bool = False


def request_graceful_stop() -> None:
    """Mark fly to exit cleanly after the current bead completes.

    Idempotent: calling this multiple times has no effect beyond the
    first. The supervisor checks :func:`is_graceful_stop_requested`
    between beads.
    """
    global _GRACEFUL_STOP_REQUESTED
    _GRACEFUL_STOP_REQUESTED = True


def is_graceful_stop_requested() -> bool:
    """True once the user has asked fly to stop after the current bead."""
    return _GRACEFUL_STOP_REQUESTED


def reset_graceful_stop() -> None:
    """Clear the flag.

    Called by the CLI's signal-handler context manager on exit so a
    subsequent fly invocation in the same process (e.g. tests, REPL
    embedding) starts clean. Production CLI runs are one-shot, so this
    is mostly for test hygiene and forward-compat.
    """
    global _GRACEFUL_STOP_REQUESTED
    _GRACEFUL_STOP_REQUESTED = False
