"""ACP subprocess connection pool.

Owns the cache of live ACP subprocess connections keyed by provider.
Responsible for spawning new agent subprocesses, initializing the ACP
handshake, reconnecting on failure, and terminating everything on
cleanup.

Split out of :mod:`maverick.executor.acp` so the executor can stay
focused on step/session orchestration.
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib.metadata
import os
from dataclasses import dataclass
from typing import Any

from acp import PROTOCOL_VERSION
from acp import RequestError as AcpRequestError
from acp.schema import ClientCapabilities, Implementation

from maverick.config import AgentProviderConfig
from maverick.exceptions.agent import CLINotFoundError, NetworkError, ProcessError
from maverick.executor._subprocess import kill_process_group
from maverick.executor._subprocess import spawn_agent_process_pg as spawn_agent_process
from maverick.executor.acp_client import MaverickAcpClient
from maverick.logging import get_logger
from maverick.tools.agent_inbox.subprocess_quota import (
    EvictCallback,
    SubprocessQuota,
)

_default_logger = get_logger(__name__)


def format_acp_error(exc: AcpRequestError) -> str:
    """Render an ACP JSON-RPC error including ``data.details`` when present.

    ``acp.RequestError.__str__`` returns only the bare ``message`` field
    (e.g. ``"Internal error"``), losing the much more useful ``data.details``
    string the agent often supplies (e.g.
    ``"Invalid permissions.defaultMode: auto."``). This helper appends the
    JSON-RPC code and surfaces ``data`` so callers can wrap the exception
    with a meaningful message.
    """
    parts: list[str] = [str(exc) or "ACP error"]
    code = getattr(exc, "code", None)
    if code is not None:
        parts.append(f"(code={code})")
    data = getattr(exc, "data", None)
    if isinstance(data, dict):
        details = data.get("details")
        if isinstance(details, str) and details:
            parts.append(f"— {details}")
        else:
            # Surface whatever the agent shipped — better than silently dropping.
            parts.append(f"data={data!r}")
    elif data is not None:
        parts.append(f"data={data!r}")
    return " ".join(parts)


#: ACP client info — sent during connection initialization
_CLIENT_INFO = Implementation(
    name="maverick",
    version=importlib.metadata.version("maverick-cli"),
)


@dataclass(frozen=True, slots=True)
class CachedConnection:
    """Active ACP connection and its backing subprocess.

    Attributes:
        conn: The ACP ClientSideConnection (live socket).
        proc: The asyncio subprocess backing the connection.
        client: MaverickAcpClient instance used for this connection.
        provider_name: Name of the provider this connection belongs to.
        ctx: The async context manager returned by spawn_agent_process, kept
            so that __aexit__ can be called during cleanup for proper teardown.
    """

    conn: Any  # acp.client.ClientSideConnection
    proc: Any  # asyncio.subprocess.Process
    client: MaverickAcpClient
    provider_name: str
    ctx: Any  # async context manager from spawn_agent_process


async def wait_for_process(proc: Any, timeout: float = 3.0) -> None:
    """Wait for a subprocess to fully exit.

    Prevents ``BaseSubprocessTransport.__del__`` from firing after the
    event loop closes, which causes ``RuntimeError: Event loop is closed``.
    """
    with contextlib.suppress(OSError, ProcessLookupError):
        proc.terminate()
    try:
        await asyncio.wait_for(proc.wait(), timeout=timeout)
    except (TimeoutError, asyncio.CancelledError):
        with contextlib.suppress(OSError, ProcessLookupError):
            proc.kill()
        with contextlib.suppress(TimeoutError, asyncio.CancelledError):
            await asyncio.wait_for(proc.wait(), timeout=1.0)
    except (OSError, ProcessLookupError, TypeError):
        pass  # Process already gone or not a real subprocess


class ConnectionPool:
    """Per-provider cache of live ACP agent subprocesses.

    One connection is cached per provider name for the lifetime of the
    pool. Sessions are created on top of the cached connection by the
    executor — the pool itself only manages subprocess lifecycle.

    Tests may inspect :attr:`cache` directly for read-only assertions
    (``len``, ``__contains__``, ``__getitem__``).
    """

    def __init__(
        self,
        logger: Any = None,
        *,
        subprocess_quota: SubprocessQuota | None = None,
        actor_uid: str | None = None,
        evict_cb: EvictCallback | None = None,
    ) -> None:
        """
        Args:
            logger: Optional structlog logger. Defaults to module logger.
            subprocess_quota: Optional pool-scoped quota that bounds total
                live ACP subprocesses. When set, ``actor_uid`` and
                ``evict_cb`` MUST also be set so the pool can acquire a
                slot before its first spawn and free it on close.
            actor_uid: The owning actor's uid (used as the quota lease key).
            evict_cb: Callback the quota invokes when this pool is the
                LRU eviction victim. The callback is responsible for
                tearing down the subprocess (e.g., calling
                :meth:`AcpStepExecutor.cleanup_for_eviction`).
        """
        self.cache: dict[str, CachedConnection] = {}
        self._logger = logger if logger is not None else _default_logger
        self._quota = subprocess_quota
        self._actor_uid = actor_uid
        self._evict_cb = evict_cb
        # True once we've successfully acquired a quota slot. Multiple
        # provider subprocesses live under one slot — see the design
        # note in ``subprocess_quota.py``: one slot per executor, not
        # per provider.
        self._slot_held = False

    async def get_or_create(
        self,
        provider_name: str,
        provider_config: AgentProviderConfig,
        max_output_tokens: int | None = None,
    ) -> CachedConnection:
        """Return a cached connection, spawning a new subprocess if needed.

        Args:
            provider_name: Logical provider name (e.g. "claude").
            provider_config: AgentProviderConfig with command and env overrides.
            max_output_tokens: Optional token cap threaded through to the
                subprocess env for Claude Code.

        Returns:
            CachedConnection with an initialized ACP connection.

        Raises:
            CLINotFoundError: If the subprocess binary is not found.
            ProcessError: If the subprocess exits with non-zero status.
            NetworkError: If the ACP initialize handshake fails.
        """
        if provider_name in self.cache:
            return self.cache[provider_name]

        # Acquire a global quota slot before spawning. Multiple provider
        # subprocesses inside one pool share a single slot — the slot
        # represents "this executor has live subprocesses," not "one per
        # provider." Idempotent: re-acquire by the same uid bumps activity
        # but doesn't double-count.
        await self._ensure_slot()

        command_args = provider_config.command
        if not command_args:
            raise CLINotFoundError(f"Provider '{provider_name}' has an empty command list")

        command = command_args[0]
        args = tuple(command_args[1:])

        # Build env for subprocess. Always remove CLAUDECODE to prevent the
        # "cannot be launched inside another Claude Code session" guard.
        extra_env = dict(provider_config.env) if provider_config.env else {}
        env = {**os.environ, **extra_env}
        env.pop("CLAUDECODE", None)
        env.pop("CLAUDE_CODE_ENTRYPOINT", None)

        if max_output_tokens is not None:
            env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] = str(max_output_tokens)

        self._logger.info(
            "acp_executor.subprocess_spawn",
            provider=provider_name,
            command=command,
            args=list(args),
        )

        # MaverickAcpClient subclasses acp.Client (a Protocol). Only
        # session_update and request_permission are implemented; the remaining
        # Protocol methods are not used by Maverick — mypy sees them as
        # abstract because acp.Client uses Protocol semantics.
        client = MaverickAcpClient(permission_mode=provider_config.permission_mode)  # type: ignore[abstract]

        try:
            # Raise the default 64KB stream buffer limit to 1MB to handle
            # agents that produce large tool-call messages (e.g., Write tool
            # with full file contents).
            ctx = spawn_agent_process(
                client,
                command,
                *args,
                env=env,
                transport_kwargs={"limit": 1_048_576},
            )
            conn, proc = await ctx.__aenter__()
        except FileNotFoundError as exc:
            raise CLINotFoundError(
                f"Agent subprocess not found for provider '{provider_name}': "
                f"'{command}' — ensure the binary is installed and on PATH",
                cli_path=command,
            ) from exc
        except OSError as exc:
            raise ProcessError(
                f"Failed to spawn agent subprocess for provider '{provider_name}': {exc}"
            ) from exc

        # Give the client a reference to the connection for circuit breaker cancellation
        client._conn = conn

        try:
            await conn.initialize(
                protocol_version=PROTOCOL_VERSION,
                client_capabilities=ClientCapabilities(),
                client_info=_CLIENT_INFO,
            )
        except AcpRequestError as exc:
            raise NetworkError(
                f"ACP initialize handshake failed for provider '{provider_name}': "
                f"{format_acp_error(exc)}"
            ) from exc
        except Exception as exc:
            raise NetworkError(
                f"Unexpected error during ACP initialize for provider '{provider_name}': {exc}"
            ) from exc

        cached = CachedConnection(
            conn=conn,
            proc=proc,
            client=client,
            provider_name=provider_name,
            ctx=ctx,
        )
        self.cache[provider_name] = cached

        self._logger.info(
            "acp_executor.subprocess_ready",
            provider=provider_name,
        )
        return cached

    async def _ensure_slot(self) -> None:
        """Acquire the executor's global quota slot if not already held."""
        if (
            self._quota is None
            or self._actor_uid is None
            or self._evict_cb is None
            or self._slot_held
        ):
            return
        await self._quota.acquire(self._actor_uid, self._evict_cb)
        self._slot_held = True

    async def mark_busy(self) -> None:
        """Mark the executor's slot mid-prompt (shielded from eviction)."""
        if self._quota is not None and self._actor_uid is not None and self._slot_held:
            await self._quota.mark_busy(self._actor_uid)

    async def mark_idle(self) -> None:
        """Mark the executor's slot between prompts (eligible for eviction)."""
        if self._quota is not None and self._actor_uid is not None and self._slot_held:
            await self._quota.mark_idle(self._actor_uid)

    async def reconnect(
        self,
        provider_name: str,
        provider_config: AgentProviderConfig,
    ) -> CachedConnection:
        """Close the stale connection and spawn a fresh replacement (FR-021).

        Logs the reconnect attempt at INFO level. Removes the old connection
        entry from the cache before delegating to :meth:`get_or_create`,
        which will spawn and initialize a new subprocess.

        Raises:
            CLINotFoundError: Binary not found for the new subprocess.
            ProcessError: New subprocess exits with non-zero status.
            NetworkError: ACP initialize handshake fails on the new connection.
        """
        self._logger.info(
            "acp_executor.reconnect_attempt",
            provider=provider_name,
        )

        stale = self.cache.pop(provider_name, None)
        if stale is not None:
            try:
                await stale.conn.close()
            except Exception as close_exc:
                self._logger.debug(
                    "acp_executor.reconnect_close_error",
                    provider=provider_name,
                    error=str(close_exc),
                )
            await wait_for_process(stale.proc)

        new_cached = await self.get_or_create(provider_name, provider_config)

        self._logger.info(
            "acp_executor.reconnect_success",
            provider=provider_name,
        )
        return new_cached

    async def close_all(self, *, release_quota_slot: bool = True) -> None:
        """Close all cached ACP connections and terminate subprocesses.

        Safe to call multiple times. Logs at INFO level for each connection
        closed (FR-023). Errors during cleanup are logged but not raised.
        Each connection gets a 2-second grace period before the subprocess
        is force-killed. The agent is spawned as its own process group
        leader (see ``_subprocess.spawn_stdio_transport_pg``) so we kill
        the whole group, not just the direct child — otherwise the
        ``claude-agent-acp`` node process leaves its spawned ``claude`` CLI
        and MCP server children running as orphans.

        Args:
            release_quota_slot: When True (the default), also release the
                pool's global subprocess-quota slot. Set to False when the
                quota itself is invoking eviction — it has already popped
                the lease and a release would be a no-op (and worse,
                wakes a waiter twice).
        """
        for provider_name, cached in list(self.cache.items()):
            self._logger.info(
                "acp_executor.cleanup",
                provider=provider_name,
                pid=getattr(cached.proc, "pid", None),
            )
            try:
                await asyncio.wait_for(
                    cached.ctx.__aexit__(None, None, None),
                    timeout=2.0,
                )
            except (TimeoutError, asyncio.CancelledError):
                self._logger.debug(
                    "acp_executor.cleanup_timeout_kill",
                    provider=provider_name,
                )
                with contextlib.suppress(OSError, ProcessLookupError):
                    cached.proc.kill()
            except Exception as exc:
                self._logger.debug(
                    "acp_executor.cleanup_ctx_error",
                    provider=provider_name,
                    error=str(exc),
                )
                with contextlib.suppress(OSError, ProcessLookupError):
                    cached.proc.kill()
            # Wait for subprocess to fully exit so its transport is cleaned
            # up before the event loop closes.
            await wait_for_process(cached.proc)
            # Belt-and-suspenders: if any grandchildren survived the
            # direct-process kill, the process group cleanup catches them.
            pid = getattr(cached.proc, "pid", 0)
            if pid:
                kill_process_group(pid)
        self.cache.clear()
        if release_quota_slot and self._slot_held:
            self._slot_held = False
            if self._quota is not None and self._actor_uid is not None:
                await self._quota.release(self._actor_uid)
        elif not release_quota_slot:
            # Eviction path: quota popped the lease before calling our
            # evict_cb, so just clear our local flag.
            self._slot_held = False

    def __contains__(self, provider_name: object) -> bool:
        return provider_name in self.cache

    def __getitem__(self, provider_name: str) -> CachedConnection:
        return self.cache[provider_name]

    def __len__(self) -> int:
        return len(self.cache)
