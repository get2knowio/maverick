"""Runtime bootstrap helpers for the Maverick CLI.

Provides utilities to automatically launch the Temporal development server
and the Maverick worker so that `maverick` can be the sole entrypoint for
running workflows.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import signal
import sys
from asyncio.subprocess import DEVNULL, Process
from dataclasses import dataclass
from typing import Any, Tuple


START_NEW_SESSION = os.name != "nt"
DEFAULT_TEMPORAL_HOST = "localhost:7233"
DEFAULT_TEMPORAL_PORT = 7233


class BootstrapError(RuntimeError):
    """Base error raised when runtime bootstrap fails."""


class TemporalBootstrapError(BootstrapError):
    """Temporal dev server failed to start or respond."""


class WorkerBootstrapError(BootstrapError):
    """Worker process failed to start or exited unexpectedly."""


def parse_host_and_port(address: str | None) -> Tuple[str, int]:
    """Parse host:port string into components."""
    if not address:
        return "localhost", DEFAULT_TEMPORAL_PORT

    host = address
    port = DEFAULT_TEMPORAL_PORT

    if ":" in address:
        host_part, _, port_part = address.rpartition(":")
        host = host_part or "localhost"
        try:
            port = int(port_part)
        except ValueError:
            port = DEFAULT_TEMPORAL_PORT

    return host, port


def _is_local_host(host: str) -> bool:
    """Return True when host resolves to the local machine."""
    local_hosts = {"127.0.0.1", "localhost", "::1"}
    return host.lower() in local_hosts


def _is_truthy_env(var_name: str) -> bool:
    """Return True when the given env var is set to a truthy value."""
    value = os.getenv(var_name, "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class TemporalServerBootstrap:
    """Manage lifecycle of a local Temporal dev server process."""

    temporal_host: str
    logger: Any

    def __post_init__(self) -> None:
        self.process: Process | None = None
        self._host, self._port = parse_host_and_port(self.temporal_host)
        self._skip_requested = _is_truthy_env("MAVERICK_SKIP_TEMPORAL_BOOTSTRAP")
        self._is_local_host = _is_local_host(self._host)
        self._timeout_seconds = float(os.getenv("MAVERICK_TEMPORAL_BOOTSTRAP_TIMEOUT", "45"))

    async def ensure_ready(self) -> None:
        """Ensure the Temporal dev server is running and reachable."""
        if self._skip_requested:
            self.logger.info(
                "temporal_bootstrap_skipped host=%s reason=%s",
                self.temporal_host,
                "env_override",
            )
            return

        if not self._is_local_host:
            self.logger.info(
                "temporal_bootstrap_skipped host=%s reason=%s",
                self.temporal_host,
                "remote_host",
            )
            return

        if await self._is_reachable():
            self.logger.info(
                "temporal_bootstrap_detected host=%s managed=%s",
                self.temporal_host,
                False,
            )
            return

        temporal_cli = os.getenv("TEMPORAL_CLI_PATH") or shutil.which("temporal")
        if not temporal_cli:
            raise TemporalBootstrapError(
                "Temporal CLI executable 'temporal' not found in PATH. "
                "Install the Temporal CLI or set TEMPORAL_CLI_PATH to its location."
            )

        self.logger.info(
            "temporal_bootstrap_starting host=%s cli_path=%s",
            self.temporal_host,
            temporal_cli,
        )
        cmd = [temporal_cli, "server", "start-dev", "--headless"]

        self.process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=DEVNULL,
            stderr=DEVNULL,
            start_new_session=START_NEW_SESSION,
        )

        if not await self._wait_until_ready():
            await self._terminate_process()
            raise TemporalBootstrapError(
                f"Timed out waiting for Temporal dev server to start on {self.temporal_host}."
            )

        self.logger.info("temporal_bootstrap_ready host=%s", self.temporal_host)

    async def stop(self) -> None:
        """Stop managed Temporal process if we started one."""
        if self.process and self.process.returncode is None:
            self.logger.info("temporal_bootstrap_stopping host=%s", self.temporal_host)
            await self._terminate_process()
            self.logger.info("temporal_bootstrap_stopped host=%s", self.temporal_host)

    async def _terminate_process(self) -> None:
        if not self.process or self.process.returncode is not None:
            return

        try:
            if os.name == "nt":
                self.process.terminate()
            else:
                os.killpg(self.process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return

        try:
            await asyncio.wait_for(self.process.wait(), timeout=10)
        except asyncio.TimeoutError:
            if os.name != "nt":
                os.killpg(self.process.pid, signal.SIGKILL)
            else:
                self.process.kill()
            await self.process.wait()

    async def _is_reachable(self) -> bool:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, self._port),
                timeout=1.0,
            )
            writer.close()
            await writer.wait_closed()
            return True
        except (asyncio.TimeoutError, OSError):
            return False

    async def _wait_until_ready(self) -> bool:
        loop = asyncio.get_event_loop()
        deadline = loop.time() + self._timeout_seconds
        while loop.time() < deadline:
            if await self._is_reachable():
                return True
            await asyncio.sleep(0.5)
        return False


@dataclass
class WorkerBootstrap:
    """Manage lifecycle of the Maverick worker process."""

    logger: Any

    def __post_init__(self) -> None:
        self.process: Process | None = None
        self._enabled = not _is_truthy_env("MAVERICK_SKIP_WORKER_BOOTSTRAP")

    async def ensure_ready(self) -> None:
        """Start the worker process unless disabled."""
        if not self._enabled:
            self.logger.info("worker_bootstrap_skipped reason=%s", "env_override")
            return

        if self.process and self.process.returncode is None:
            return

        cmd = [sys.executable, "-m", "src.workers.main"]
        env = os.environ.copy()
        env.setdefault("PYTHONUNBUFFERED", "1")

        self.logger.info("worker_bootstrap_starting cmd=%s", " ".join(cmd))
        self.process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=DEVNULL,
            stderr=DEVNULL,
            env=env,
            start_new_session=START_NEW_SESSION,
        )

        # Give the worker a brief moment to fail fast if something is wrong.
        await asyncio.sleep(0.5)
        if self.process.returncode is not None:
            raise WorkerBootstrapError(
                f"Worker exited immediately with code {self.process.returncode}. "
                "Run 'python -m src.workers.main' manually for logs."
            )

        self.logger.info("worker_bootstrap_ready pid=%s", self.process.pid)

    async def stop(self) -> None:
        """Stop the worker process if we started it."""
        if not self.process or self.process.returncode is not None:
            return

        self.logger.info("worker_bootstrap_stopping pid=%s", self.process.pid)

        try:
            if os.name == "nt":
                self.process.terminate()
            else:
                os.killpg(self.process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return

        try:
            await asyncio.wait_for(self.process.wait(), timeout=10)
        except asyncio.TimeoutError:
            if os.name != "nt":
                os.killpg(self.process.pid, signal.SIGKILL)
            else:
                self.process.kill()
            await self.process.wait()

        self.logger.info("worker_bootstrap_stopped")


class RuntimeBootstrap:
    """High-level bootstrapper that manages Temporal and worker processes."""

    def __init__(self, temporal_host: str, logger, start_worker: bool = True) -> None:
        self.start_worker = start_worker
        self.temporal = TemporalServerBootstrap(temporal_host or DEFAULT_TEMPORAL_HOST, logger)
        self.worker = WorkerBootstrap(logger)

    async def start(self) -> None:
        """Start all required background processes."""
        try:
            await self.temporal.ensure_ready()
            if self.start_worker:
                await self.worker.ensure_ready()
        except Exception:
            await self.stop()
            raise

    async def stop(self) -> None:
        """Stop managed background processes."""
        try:
            if self.start_worker:
                await self.worker.stop()
        finally:
            await self.temporal.stop()
