"""Process-group-aware wrapper around ACP's subprocess spawn.

The upstream ``acp.transports.spawn_stdio_transport`` calls
``asyncio.create_subprocess_exec`` without ``start_new_session=True``,
so the ACP agent subprocess shares its process group with the Python
parent. When the parent dies abnormally (SIGKILL, OOM, unclean actor
termination), the agent process — and its own children
(``claude`` CLI, MCP servers) — are reparented to PID 1 and continue
running indefinitely. We've observed this accumulating into memory
exhaustion and container OOMs.

This module provides a drop-in replacement that spawns the subprocess
as a new process group leader. Callers can then kill the whole group
via :func:`os.killpg` during cleanup, which also terminates any
grandchildren the agent has spawned.

Known upstream issues:
- anthropics/claude-agent-sdk-typescript#142 (no pdeathsig on ``claude`` CLI)
- anthropics/claude-agent-sdk-typescript#219 (MCP zombies)
- agentclientprotocol/claude-agent-acp#314 (no SIGHUP handler)
"""

from __future__ import annotations

import asyncio
import asyncio.subprocess as aio_subprocess
import contextlib
import os
import signal
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from acp.client.connection import ClientSideConnection
from acp.interfaces import Agent, Client
from acp.transports import default_environment

from maverick.logging import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def spawn_stdio_transport_pg(
    command: str,
    *args: str,
    env: Mapping[str, str] | None = None,
    cwd: str | Path | None = None,
    stderr: int | None = aio_subprocess.PIPE,
    limit: int | None = None,
    shutdown_timeout: float = 2.0,
) -> AsyncIterator[tuple[asyncio.StreamReader, asyncio.StreamWriter, aio_subprocess.Process]]:
    """Same as ``acp.transports.spawn_stdio_transport`` but with
    ``start_new_session=True``.

    The spawned process becomes the leader of a new process group so
    callers can kill it *and all of its descendants* with a single
    ``os.killpg(proc.pid, SIGTERM)``. On cleanup we try graceful stdin
    EOF first, then escalate to SIGTERM on the group, then SIGKILL.
    """
    merged_env = dict(default_environment())
    if env:
        merged_env.update(env)

    spawn_kwargs: dict[str, Any] = {
        "stdin": aio_subprocess.PIPE,
        "stdout": aio_subprocess.PIPE,
        "stderr": stderr,
        "env": merged_env,
        "cwd": str(cwd) if cwd is not None else None,
        # THE point of this wrapper: detach the child into its own
        # session/process group so killpg reaches grandchildren too.
        "start_new_session": True,
    }
    if limit is not None:
        spawn_kwargs["limit"] = limit

    process = await asyncio.create_subprocess_exec(command, *args, **spawn_kwargs)

    if process.stdout is None or process.stdin is None:
        with contextlib.suppress(Exception):
            _killpg(process.pid, signal.SIGKILL)
        await process.wait()
        raise RuntimeError("spawn_stdio_transport_pg requires stdout/stdin pipes")

    try:
        yield process.stdout, process.stdin, process
    finally:
        # Graceful stdin EOF first.
        if process.stdin is not None:
            try:
                process.stdin.write_eof()
            except (AttributeError, OSError, RuntimeError):
                process.stdin.close()
            with contextlib.suppress(Exception):
                await process.stdin.drain()
            with contextlib.suppress(Exception):
                process.stdin.close()
            with contextlib.suppress(Exception):
                await process.stdin.wait_closed()

        try:
            await asyncio.wait_for(process.wait(), timeout=shutdown_timeout)
        except TimeoutError:
            # SIGTERM the whole group so descendants die with the child.
            _killpg(process.pid, signal.SIGTERM)
            try:
                await asyncio.wait_for(process.wait(), timeout=shutdown_timeout)
            except TimeoutError:
                _killpg(process.pid, signal.SIGKILL)


@asynccontextmanager
async def spawn_agent_process_pg(
    to_client: Callable[[Agent], Client] | Client,
    command: str,
    *args: str,
    env: Mapping[str, str] | None = None,
    cwd: str | Path | None = None,
    transport_kwargs: Mapping[str, Any] | None = None,
    **connection_kwargs: Any,
) -> AsyncIterator[tuple[ClientSideConnection, aio_subprocess.Process]]:
    """Drop-in replacement for ``acp.stdio.spawn_agent_process`` that spawns
    the agent in a new session/process group.
    """
    async with spawn_stdio_transport_pg(
        command,
        *args,
        env=env,
        cwd=cwd,
        **(dict(transport_kwargs) if transport_kwargs else {}),
    ) as (reader, writer, process):
        conn = ClientSideConnection(to_client, writer, reader, **connection_kwargs)
        try:
            yield conn, process
        finally:
            with contextlib.suppress(Exception):
                await conn.close()


def kill_process_group(pid: int, *, grace_seconds: float = 2.0) -> None:
    """Best-effort group kill for a process previously spawned with
    ``spawn_stdio_transport_pg``.

    Sends SIGTERM to the group, sleeps up to ``grace_seconds``, then
    SIGKILL if anyone is still around. Synchronous; safe to call from
    atexit handlers where an event loop may not exist.
    """
    import time

    # Guard against bad inputs (e.g. mock objects in tests, or a PID
    # that was never actually set). Anything not an integer or not
    # positive is a no-op.
    if not isinstance(pid, int) or pid <= 0:
        return
    if not _killpg(pid, signal.SIGTERM):
        return  # group already gone

    deadline = time.monotonic() + grace_seconds
    while time.monotonic() < deadline:
        # If killpg returns 0, the group is gone. Probe with signal 0.
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
