"""OpenCode subprocess lifecycle: spawn, health-poll, terminate.

Mirrors the actor-pool pattern (one OpenCode server per workflow run on
an ephemeral port). Hermetic by default:

* Bind to ``127.0.0.1:0`` and discover the actual port from the server's
  startup line.
* Generate a per-run :envvar:`OPENCODE_SERVER_PASSWORD`; clients send it
  as a ``Bearer`` token. Defends against same-host processes connecting
  to the running server.
* Use :func:`asyncio.create_subprocess_exec` so the parent loop never
  blocks on I/O (Guardrail 1).

Cleanup is best-effort: terminate first, kill on timeout. Stale servers
left behind are diagnosable via the spike's :file:`purge_queued.py`
runbook.
"""

from __future__ import annotations

import asyncio
import os
import re
import secrets
import shutil
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import httpx

from maverick.logging import get_logger
from maverick.runtime.opencode.client import OpenCodeClient
from maverick.runtime.opencode.errors import OpenCodeServerStartError

logger = get_logger(__name__)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_BIND_PORT = 0  # 0 = let the OS pick
DEFAULT_STARTUP_TIMEOUT = 30.0
DEFAULT_SHUTDOWN_TIMEOUT = 5.0

# Match lines like:
#   "opencode server listening on http://127.0.0.1:54812"
#   "Listening on 127.0.0.1:54812"
#   "Server started at http://127.0.0.1:54812"
_LISTEN_RE = re.compile(
    r"(?:listen(?:ing)?|started|running)[^\d]*"
    r"(?:https?://)?(?P<host>[\w.-]+):(?P<port>\d+)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class OpenCodeServerHandle:
    """Reference to a running OpenCode subprocess.

    Use :func:`spawn_opencode_server` (or :func:`opencode_server`) to
    create one. Hold the handle for the duration of the workflow; call
    :meth:`stop` (or let the context manager unwind) to terminate.

    Attributes:
        base_url: ``http://host:port`` to point :class:`OpenCodeClient` at.
        password: Random per-spawn ``OPENCODE_SERVER_PASSWORD``.
        pid: OS pid of the server process.
    """

    base_url: str
    password: str
    pid: int
    _process: asyncio.subprocess.Process

    async def stop(self, *, timeout: float = DEFAULT_SHUTDOWN_TIMEOUT) -> None:
        """Terminate the server process. Idempotent and best-effort."""
        proc = self._process
        if proc.returncode is not None:
            return
        try:
            proc.terminate()
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(proc.wait(), timeout=timeout)
        except TimeoutError:
            logger.warning(
                "opencode.server_kill_after_terminate_timeout",
                pid=proc.pid,
                timeout=timeout,
            )
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(proc.wait(), timeout=timeout)
            except TimeoutError:
                logger.error("opencode.server_failed_to_die", pid=proc.pid)


def _resolve_executable(path_or_name: str | None) -> str:
    candidate = path_or_name or os.environ.get("OPENCODE_BIN") or "opencode"
    resolved = shutil.which(candidate) or candidate
    return resolved


async def spawn_opencode_server(
    *,
    executable: str | None = None,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_BIND_PORT,
    password: str | None = None,
    extra_env: dict[str, str] | None = None,
    config_path: str | None = None,
    startup_timeout: float = DEFAULT_STARTUP_TIMEOUT,
    extra_args: list[str] | None = None,
) -> OpenCodeServerHandle:
    """Spawn ``opencode serve`` and wait until the HTTP endpoint is healthy.

    The function returns once :func:`GET /global/health` returns 2xx. If
    the process exits or the timeout elapses first, raises
    :class:`OpenCodeServerStartError`.

    Args:
        executable: Path to the ``opencode`` binary; defaults to
            ``$OPENCODE_BIN`` or ``opencode`` on ``$PATH``.
        host: Bind address (default ``127.0.0.1``).
        port: Bind port; ``0`` lets the OS pick.
        password: ``OPENCODE_SERVER_PASSWORD`` to inject. Generated per
            spawn when ``None``.
        extra_env: Extra env vars for the subprocess.
        config_path: Optional ``opencode.jsonc`` path to forward via
            ``--config``.
        startup_timeout: Seconds to wait for the server to become
            healthy before giving up.
        extra_args: Additional CLI args appended after the standard ones.
    """
    bin_path = _resolve_executable(executable)
    pwd = password or secrets.token_urlsafe(24)

    env = os.environ.copy()
    env["OPENCODE_SERVER_PASSWORD"] = pwd
    if extra_env:
        env.update(extra_env)

    args: list[str] = [
        bin_path,
        "serve",
        "--port",
        str(port),
        "--hostname",
        host,
    ]
    if config_path:
        args.extend(["--config", config_path])
    if extra_args:
        args.extend(extra_args)

    logger.debug("opencode.spawn_starting", host=host, port=port, bin=bin_path)

    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise OpenCodeServerStartError(
            f"opencode binary not found: {bin_path}",
        ) from exc
    except OSError as exc:
        raise OpenCodeServerStartError(
            f"failed to spawn opencode at {bin_path}: {exc}",
        ) from exc

    # Drain stdout/stderr concurrently so the pipes don't fill and block
    # the child. We watch for the listen line on either stream — opencode
    # has historically logged it on stdout but stderr is also possible.
    listen_evt: asyncio.Event = asyncio.Event()
    listen_box: dict[str, Any] = {}
    log_lines: list[str] = []

    async def _drain(stream: asyncio.StreamReader | None, label: str) -> None:
        if stream is None:
            return
        while True:
            line = await stream.readline()
            if not line:
                break
            text = line.decode(errors="replace").rstrip()
            log_lines.append(f"[{label}] {text}")
            if not listen_evt.is_set():
                m = _LISTEN_RE.search(text)
                if m:
                    listen_box["host"] = m.group("host")
                    listen_box["port"] = int(m.group("port"))
                    listen_evt.set()
            logger.debug("opencode.server_log", stream=label, text=text)

    drain_tasks = [
        asyncio.create_task(_drain(proc.stdout, "stdout")),
        asyncio.create_task(_drain(proc.stderr, "stderr")),
    ]

    try:
        # Wait for either the listen line OR a non-zero port we already know.
        # If the user passed an explicit non-zero port, we don't actually
        # need the listen line — we can poll /global/health directly.
        if port != 0:
            listen_box.setdefault("host", host)
            listen_box.setdefault("port", port)
            listen_evt.set()

        try:
            await asyncio.wait_for(listen_evt.wait(), timeout=startup_timeout)
        except TimeoutError as exc:
            await _kill_process(proc)
            raise OpenCodeServerStartError(
                f"opencode did not log a listen line within "
                f"{startup_timeout}s. Last log lines: "
                f"{log_lines[-10:]}"
            ) from exc

        if proc.returncode is not None:
            raise OpenCodeServerStartError(
                f"opencode exited with code {proc.returncode} during "
                f"startup. Last log lines: {log_lines[-10:]}",
            )

        bound_host = listen_box["host"]
        bound_port = int(listen_box["port"])
        base_url = f"http://{bound_host}:{bound_port}"

        # Poll /global/health to confirm the server is actually serving.
        deadline = asyncio.get_running_loop().time() + startup_timeout
        async with httpx.AsyncClient(
            base_url=base_url,
            timeout=2.0,
            auth=httpx.BasicAuth(OpenCodeClient.BASIC_AUTH_USERNAME, pwd),
        ) as health:
            while True:
                if proc.returncode is not None:
                    raise OpenCodeServerStartError(
                        f"opencode exited with code {proc.returncode} "
                        f"during health probe. Last log lines: "
                        f"{log_lines[-10:]}",
                    )
                try:
                    r = await health.get("/global/health")
                    if r.status_code < 400:
                        break
                except (httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError):
                    pass
                if asyncio.get_running_loop().time() > deadline:
                    await _kill_process(proc)
                    raise OpenCodeServerStartError(
                        f"opencode {base_url} did not pass /global/health "
                        f"within {startup_timeout}s",
                    )
                await asyncio.sleep(0.1)
    except OpenCodeServerStartError:
        for t in drain_tasks:
            t.cancel()
        raise

    logger.info("opencode.server_ready", url=base_url, pid=proc.pid)
    return OpenCodeServerHandle(
        base_url=base_url,
        password=pwd,
        pid=proc.pid,
        _process=proc,
    )


async def _kill_process(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None:
        return
    try:
        proc.terminate()
    except ProcessLookupError:
        return
    try:
        await asyncio.wait_for(proc.wait(), timeout=2.0)
    except TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            return
        try:
            await proc.wait()
        except Exception:  # noqa: BLE001 — diagnostic teardown
            pass


@asynccontextmanager
async def opencode_server(
    *,
    executable: str | None = None,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_BIND_PORT,
    password: str | None = None,
    extra_env: dict[str, str] | None = None,
    config_path: str | None = None,
    startup_timeout: float = DEFAULT_STARTUP_TIMEOUT,
    extra_args: list[str] | None = None,
) -> AsyncIterator[OpenCodeServerHandle]:
    """Async context manager: spawn server, yield handle, terminate on exit."""
    handle = await spawn_opencode_server(
        executable=executable,
        host=host,
        port=port,
        password=password,
        extra_env=extra_env,
        config_path=config_path,
        startup_timeout=startup_timeout,
        extra_args=extra_args,
    )
    try:
        yield handle
    finally:
        await handle.stop()


def client_for(handle: OpenCodeServerHandle, *, timeout: float = 600.0) -> OpenCodeClient:
    """Build an :class:`OpenCodeClient` pre-wired to ``handle``."""
    return OpenCodeClient(
        base_url=handle.base_url,
        timeout=timeout,
        password=handle.password,
    )
