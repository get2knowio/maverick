"""AcpStepExecutor — ACP adapter implementing the StepExecutor protocol.

This module provides an ACP-based executor that spawns agent subprocesses via
the agent-client-protocol SDK and communicates over stdio. It supports:
- Connection caching (one subprocess per provider)
- Per-session retry with tenacity
- Circuit breaker detection via MaverickAcpClient
- JSON output extraction for typed output_schema
- Proper error mapping to the Maverick exception hierarchy
- Transparent reconnect on connection drop (FR-021)

FR-023: Log subprocess spawn at INFO level.
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib.metadata
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from acp import PROTOCOL_VERSION, spawn_agent_process, text_block
from acp import RequestError as AcpRequestError
from acp.schema import ClientCapabilities, Implementation
from pydantic import BaseModel, ValidationError
from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential

from maverick.config import AgentProviderConfig
from maverick.constants import get_model_type
from maverick.exceptions.agent import (
    AgentError,
    CircuitBreakerError,
    CLINotFoundError,
    MalformedResponseError,
    MaverickTimeoutError,
    NetworkError,
    ProcessError,
)
from maverick.exceptions.workflow import ReferenceResolutionError
from maverick.executor.acp_client import MAX_SAME_TOOL_CALLS, MaverickAcpClient
from maverick.executor.config import DEFAULT_EXECUTOR_CONFIG, StepConfig
from maverick.executor.errors import OutputSchemaValidationError
from maverick.executor.protocol import EventCallback
from maverick.executor.provider_registry import AgentProviderRegistry
from maverick.executor.result import ExecutorResult
from maverick.logging import get_logger
from maverick.registry import ComponentRegistry

__all__ = ["AcpStepExecutor"]

logger = get_logger(__name__)

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


class AcpStepExecutor:
    """ACP adapter implementing the StepExecutor protocol (FR-015).

    Spawns agent subprocesses via the ACP SDK, reuses connections across steps,
    and maps ACP events/errors to Maverick's event and exception hierarchy.

    One subprocess is spawned per provider and cached for the lifetime of this
    executor. Sessions are created fresh per execute() call (and per retry
    attempt). Call cleanup() when the executor is no longer needed.

    Args:
        provider_registry: Resolves provider names → AgentProviderConfig.
        agent_registry: ComponentRegistry for agent class lookup and build_prompt.
    """

    def __init__(
        self,
        provider_registry: AgentProviderRegistry,
        agent_registry: ComponentRegistry,
        global_max_tokens: int | None = None,
    ) -> None:
        self._provider_registry = provider_registry
        self._agent_registry = agent_registry
        self._global_max_tokens = global_max_tokens
        self._connections: dict[str, CachedConnection] = {}
        self._logger = get_logger(__name__)

    async def execute(
        self,
        *,
        step_name: str,
        agent_name: str,
        prompt: Any,
        instructions: str | None = None,
        allowed_tools: list[str] | None = None,
        cwd: Path | None = None,
        output_schema: type[BaseModel] | None = None,
        config: StepConfig | None = None,
        event_callback: EventCallback | None = None,
    ) -> ExecutorResult:
        """Execute an agent step via ACP and return a typed ExecutorResult.

        Args:
            step_name: DSL step name for observability logging.
            agent_name: Registered agent name in ComponentRegistry.
            prompt: Context passed to agent.build_prompt() to get a string prompt.
            instructions: Optional system instructions prepended to the prompt.
            allowed_tools: Tool allowlist forwarded to MaverickAcpClient.
            cwd: Working directory for the ACP session. None = current dir.
            output_schema: Optional Pydantic model for structured output validation.
            config: Per-step execution config. None = DEFAULT_EXECUTOR_CONFIG.
            event_callback: Async callback for real-time AgentStreamChunk events.

        Returns:
            ExecutorResult with output, success=True, usage=None, events=().

        Raises:
            ReferenceResolutionError: Agent not found in registry.
            OutputSchemaValidationError: Output failed schema validation.
            CircuitBreakerError: Agent triggered the tool-call circuit breaker.
            MaverickTimeoutError: Step exceeded configured timeout.
            CLINotFoundError: Agent subprocess binary not found.
            ProcessError: Subprocess exited with non-zero status.
            NetworkError: ACP connection-level error.
            AgentError: Other agent execution failures.
        """
        effective_config = config if config is not None else DEFAULT_EXECUTOR_CONFIG
        start_time = time.monotonic()

        self._logger.info(
            "acp_executor.step_start",
            step_name=step_name,
            agent_name=agent_name,
            provider=effective_config.provider,
            timeout=effective_config.timeout,
        )

        # --- Resolve provider ---
        if effective_config.provider is not None:
            provider_name, provider_config = (
                effective_config.provider,
                self._provider_registry.get(effective_config.provider),
            )
        else:
            provider_name, provider_config = self._provider_registry.default()

        # --- Resolve agent and build prompt string ---
        # Normalize agent name: allow hyphens as alias for underscores
        # (e.g. "unified-reviewer" → "unified_reviewer") so callers can
        # pass either convention.
        _resolved_agent_name = agent_name
        if not self._agent_registry.agents.has(_resolved_agent_name):
            _alt = agent_name.replace("-", "_")
            if self._agent_registry.agents.has(_alt):
                _resolved_agent_name = _alt
            else:
                raise ReferenceResolutionError(
                    reference_type="agent",
                    reference_name=agent_name,
                    available_names=self._agent_registry.agents.list_names(),
                )
        agent_name = _resolved_agent_name

        agent_class = self._agent_registry.agents.get(agent_name)
        try:
            agent_instance = agent_class()  # type: ignore[call-arg]
        except TypeError as exc:
            self._logger.error(
                "acp_executor.agent_instantiation_failed",
                agent_name=agent_name,
                error=str(exc),
            )
            raise AgentError(
                f"Failed to instantiate agent '{agent_name}': {exc}",
                agent_name=agent_name,
            ) from exc

        raw_prompt: str = agent_instance.build_prompt(prompt)

        # Resolve allowed_tools: explicit caller value takes priority,
        # then fall back to the agent's own allowed_tools property.
        if allowed_tools is None:
            agent_tools = getattr(agent_instance, "allowed_tools", None)
            if isinstance(agent_tools, list):
                allowed_tools = agent_tools

        # Resolve instructions: explicit caller instructions take priority,
        # then fall back to the agent's own instructions property.
        effective_instructions = instructions or getattr(
            agent_instance, "instructions", None
        )

        # Append output schema to prompt so the agent knows the exact structure
        if output_schema is not None:
            schema_json = json.dumps(output_schema.model_json_schema(), indent=2)
            raw_prompt = (
                f"{raw_prompt}\n\n---\n\n"
                f"[OUTPUT SCHEMA]\n"
                f"You MUST respond with a single JSON object "
                f"(inside a ```json code fence) that conforms "
                f"exactly to this JSON Schema. Use only the "
                f"field names and types shown — do not nest "
                f"objects where strings are expected.\n\n"
                f"```json\n{schema_json}\n```"
            )

        # Prepend system instructions when available
        if effective_instructions:
            prompt_text = (
                f"[SYSTEM INSTRUCTIONS]\n"
                f"{effective_instructions}\n\n"
                f"---\n\n{raw_prompt}"
            )
        else:
            prompt_text = raw_prompt

        # --- Get or create cached ACP connection ---
        effective_max_tokens = effective_config.max_tokens or self._global_max_tokens
        cached = await self._get_or_create_connection(
            provider_name, provider_config, max_output_tokens=effective_max_tokens
        )

        # --- Resolve effective retry ---
        max_attempts = 1
        if (
            effective_config.max_retries is not None
            and effective_config.max_retries > 0
        ):
            max_attempts = effective_config.max_retries + 1
        elif (
            effective_config.retry_policy is not None
            and effective_config.retry_policy.max_attempts > 1
        ):
            max_attempts = effective_config.retry_policy.max_attempts

        wait_min = 1.0
        wait_max = 10.0
        if effective_config.retry_policy is not None:
            wait_min = effective_config.retry_policy.wait_min
            wait_max = effective_config.retry_policy.wait_max

        # --- Execute with retry ---
        output: Any = None
        allowed_tools_frozen = (
            frozenset(allowed_tools) if allowed_tools is not None else None
        )
        cwd_str = str(cwd) if cwd is not None else str(Path.cwd())

        model_label: str | None = None
        try:
            output, model_label = await self._execute_with_retry(
                step_name=step_name,
                agent_name=agent_name,
                prompt_text=prompt_text,
                cached=cached,
                provider_name=provider_name,
                provider_config=provider_config,
                cwd_str=cwd_str,
                output_schema=output_schema,
                effective_config=effective_config,
                event_callback=event_callback,
                allowed_tools_frozen=allowed_tools_frozen,
                max_attempts=max_attempts,
                wait_min=wait_min,
                wait_max=wait_max,
            )
        except Exception as exc:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            self._logger.error(
                "acp_executor.step_error",
                step_name=step_name,
                agent_name=agent_name,
                error_type=type(exc).__name__,
                error=str(exc),
                duration_ms=duration_ms,
            )
            raise

        duration_ms = int((time.monotonic() - start_time) * 1000)
        self._logger.info(
            "acp_executor.step_complete",
            step_name=step_name,
            agent_name=agent_name,
            duration_ms=duration_ms,
            success=True,
        )

        return ExecutorResult(
            output=output,
            success=True,
            usage=None,
            events=(),
            model_label=model_label,
        )

    async def cleanup(self) -> None:
        """Close all cached ACP connections and terminate subprocesses.

        Safe to call multiple times. Logs at INFO level for each connection
        closed (FR-023). Errors during cleanup are logged but not raised.
        Each connection gets a 2-second grace period before the subprocess
        is force-killed. After termination, waits for the subprocess to
        exit so that ``BaseSubprocessTransport.__del__`` does not fire
        after the event loop closes.
        """
        for provider_name, cached in list(self._connections.items()):
            self._logger.info(
                "acp_executor.cleanup",
                provider=provider_name,
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
            # up before the event loop closes. Without this,
            # BaseSubprocessTransport.__del__ raises RuntimeError.
            await _wait_for_process(cached.proc)
        self._connections.clear()

    async def _get_or_create_connection(
        self,
        provider_name: str,
        provider_config: AgentProviderConfig,
        max_output_tokens: int | None = None,
    ) -> CachedConnection:
        """Return a cached ACP connection, spawning a new subprocess if needed.

        Spawning and initialization are logged at INFO level (FR-023).

        Args:
            provider_name: Logical provider name (e.g. "claude").
            provider_config: AgentProviderConfig with command and env overrides.

        Returns:
            CachedConnection with an initialized ACP connection.

        Raises:
            CLINotFoundError: If the subprocess binary is not found.
            ProcessError: If the subprocess exits with non-zero status.
            NetworkError: If the ACP initialize handshake fails.
        """
        if provider_name in self._connections:
            return self._connections[provider_name]

        command_args = provider_config.command
        if not command_args:
            raise CLINotFoundError(
                f"Provider '{provider_name}' has an empty command list"
            )

        command = command_args[0]
        args = tuple(command_args[1:])

        # Build env for subprocess. Always remove CLAUDECODE to prevent the
        # "cannot be launched inside another Claude Code session" guard.
        extra_env = dict(provider_config.env) if provider_config.env else {}
        env = {**os.environ, **extra_env}
        env.pop("CLAUDECODE", None)
        env.pop("CLAUDE_CODE_ENTRYPOINT", None)

        # Thread max_tokens into the subprocess env for Claude Code.
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
        # Protocol methods (write_text_file, create_terminal, etc.) are not
        # used by Maverick and intentionally left unimplemented — mypy sees
        # them as abstract because acp.Client uses Protocol semantics.
        client = MaverickAcpClient(permission_mode=provider_config.permission_mode)  # type: ignore[abstract]

        try:
            # spawn_agent_process is an async context manager; we enter it and
            # store the resources for the lifetime of this executor.
            # Raise the default 64KB stream buffer limit to 1MB to handle
            # agents that produce large tool-call messages (e.g., Write tool
            # with full file contents).
            ctx = spawn_agent_process(
                client, command, *args, env=env,
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
                f"Failed to spawn agent subprocess for provider "
                f"'{provider_name}': {exc}"
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
                f"ACP initialize handshake failed for provider '{provider_name}': {exc}"
            ) from exc
        except Exception as exc:
            raise NetworkError(
                f"Unexpected error during ACP initialize for provider "
                f"'{provider_name}': {exc}"
            ) from exc

        cached = CachedConnection(
            conn=conn,
            proc=proc,
            client=client,
            provider_name=provider_name,
            ctx=ctx,
        )
        self._connections[provider_name] = cached

        self._logger.info(
            "acp_executor.subprocess_ready",
            provider=provider_name,
        )
        return cached

    async def _reconnect(
        self,
        provider_name: str,
        provider_config: AgentProviderConfig,
    ) -> CachedConnection:
        """Close the stale connection and spawn a fresh replacement (FR-021).

        Logs the reconnect attempt at INFO level. Removes the old connection
        entry from ``_connections`` before delegating to
        ``_get_or_create_connection``, which will spawn and initialize a new
        subprocess.

        Args:
            provider_name: Logical provider name (e.g. "claude").
            provider_config: AgentProviderConfig for the provider.

        Returns:
            A fresh, initialized CachedConnection.

        Raises:
            CLINotFoundError: Binary not found for the new subprocess.
            ProcessError: New subprocess exits with non-zero status.
            NetworkError: ACP initialize handshake fails on the new connection.
        """
        self._logger.info(
            "acp_executor.reconnect_attempt",
            provider=provider_name,
        )

        # Close and discard the stale connection
        stale = self._connections.pop(provider_name, None)
        if stale is not None:
            try:
                await stale.conn.close()
            except Exception as close_exc:
                self._logger.debug(
                    "acp_executor.reconnect_close_error",
                    provider=provider_name,
                    error=str(close_exc),
                )
            await _wait_for_process(stale.proc)

        # Spawn a fresh connection
        new_cached = await self._get_or_create_connection(
            provider_name, provider_config
        )

        self._logger.info(
            "acp_executor.reconnect_success",
            provider=provider_name,
        )
        return new_cached

    async def _execute_with_retry(
        self,
        *,
        step_name: str,
        agent_name: str,
        prompt_text: str,
        cached: CachedConnection,
        provider_name: str,
        provider_config: AgentProviderConfig,
        cwd_str: str,
        output_schema: type[BaseModel] | None,
        effective_config: StepConfig,
        event_callback: EventCallback | None,
        allowed_tools_frozen: frozenset[str] | None,
        max_attempts: int,
        wait_min: float,
        wait_max: float,
    ) -> tuple[Any, str | None]:
        """Run the ACP prompt with optional tenacity retry.

        A fresh ACP session is created per attempt. The connection is reused.
        When an ``AcpRequestError`` is raised by ``conn.new_session()`` or
        ``conn.prompt()``, a single transparent reconnect is attempted (FR-021)
        before the tenacity retry loop re-raises or retries.

        Args:
            step_name: Step name for logging and event tagging.
            agent_name: Agent name for logging and event tagging.
            prompt_text: Final prompt string (with instructions prepended if any).
            cached: Active CachedConnection.
            provider_name: Logical provider name for reconnect.
            provider_config: AgentProviderConfig for reconnect.
            cwd_str: Working directory string for the ACP session.
            output_schema: Optional Pydantic model for output validation.
            effective_config: Resolved StepConfig.
            event_callback: Real-time event forwarding callback.
            allowed_tools_frozen: Frozen set of allowed tool names.
            max_attempts: Total number of attempts (1 = no retry).
            wait_min: Tenacity minimum wait between retries in seconds.
            wait_max: Tenacity maximum wait between retries in seconds.

        Returns:
            Tuple of (extracted output, resolved model label string or None).

        Raises:
            CircuitBreakerError: Circuit breaker triggered.
            MaverickTimeoutError: Step exceeded timeout.
            OutputSchemaValidationError: Output failed schema validation.
            NetworkError: Connection drop persisted after one reconnect attempt.
            AgentError: Other execution failures.
        """
        # Mutable references so _run_single_attempt always uses the latest connection
        # after a transparent reconnect, and captures the resolved model label.
        current_cached: list[CachedConnection] = [cached]
        resolved_model_label: list[str | None] = [None]

        async def _run_single_attempt() -> Any:
            """Execute one ACP session: create session → prompt → extract output."""
            conn = current_cached[0].conn
            client = current_cached[0].client

            # Reset client state for this session
            client.reset(
                step_name=step_name,
                agent_name=agent_name,
                event_callback=event_callback,
                allowed_tools=allowed_tools_frozen,
            )

            self._logger.debug(
                "acp_executor.session_create",
                step_name=step_name,
                provider=current_cached[0].provider_name,
                cwd=cwd_str,
            )

            # --- new_session with transparent reconnect (FR-021) ---
            try:
                session = await conn.new_session(cwd=cwd_str, mcp_servers=[])
            except AcpRequestError:
                # Attempt one transparent reconnect, then retry session creation once.
                try:
                    current_cached[0] = await self._reconnect(
                        provider_name, provider_config
                    )
                    conn = current_cached[0].conn
                    client = current_cached[0].client
                    client.reset(
                        step_name=step_name,
                        agent_name=agent_name,
                        event_callback=event_callback,
                        allowed_tools=allowed_tools_frozen,
                    )
                    session = await conn.new_session(cwd=cwd_str, mcp_servers=[])
                except AcpRequestError as retry_exc:
                    raise NetworkError(
                        f"Failed to create ACP session after reconnect: {retry_exc}"
                    ) from retry_exc

            session_id = session.session_id

            # Thread model selection into the ACP session (Phase 3)
            resolved_model = effective_config.model_id or provider_config.default_model
            if resolved_model:
                # Map semantic names (sonnet/opus/haiku or full IDs) to the
                # provider's actual model IDs before validation.
                resolved_model = _resolve_model_for_provider(resolved_model, session)

                # Validate against available models from the session
                available_ids = _get_available_model_ids(session)
                if available_ids and resolved_model not in available_ids:
                    available_list = ", ".join(sorted(available_ids))
                    raise AgentError(
                        f"Model '{resolved_model}' is not available for "
                        f"provider '{current_cached[0].provider_name}'. "
                        f"Available models: {available_list}",
                        agent_name=agent_name,
                    )
                try:
                    await conn.set_session_model(
                        model_id=resolved_model,
                        session_id=session_id,
                    )
                    self._logger.debug(
                        "acp_executor.session_model_set",
                        step_name=step_name,
                        session_id=session_id,
                        model_id=resolved_model,
                    )
                except Exception as exc:
                    self._logger.warning(
                        "acp_executor.set_session_model_failed",
                        step_name=step_name,
                        model_id=resolved_model,
                        error=str(exc),
                    )

            # Resolve and store effective model for observability
            prov_name = current_cached[0].provider_name
            label = _resolve_model_label(
                session,
                resolved_model,
            )
            if label:
                resolved_model_label[0] = f"{prov_name}/{label}"

            self._logger.debug(
                "acp_executor.prompt_send",
                step_name=step_name,
                session_id=session_id,
                prompt_len=len(prompt_text),
            )

            # --- conn.prompt() with transparent reconnect (FR-021) ---
            try:
                coro = conn.prompt(
                    prompt=[text_block(prompt_text)],
                    session_id=session_id,
                )
                if effective_config.timeout is not None:
                    await asyncio.wait_for(
                        coro, timeout=float(effective_config.timeout)
                    )
                else:
                    await coro
            except TimeoutError as exc:
                raise MaverickTimeoutError(
                    f"ACP step '{step_name}' timed out after "
                    f"{effective_config.timeout}s",
                    timeout_seconds=float(effective_config.timeout or 0),
                ) from exc
            except AcpRequestError:
                # Attempt one transparent reconnect and retry the full
                # session + prompt once before surfacing as NetworkError.
                try:
                    current_cached[0] = await self._reconnect(
                        provider_name, provider_config
                    )
                    conn = current_cached[0].conn
                    client = current_cached[0].client
                    client.reset(
                        step_name=step_name,
                        agent_name=agent_name,
                        event_callback=event_callback,
                        allowed_tools=allowed_tools_frozen,
                    )
                    retry_session = await conn.new_session(cwd=cwd_str, mcp_servers=[])
                    retry_session_id = retry_session.session_id
                    retry_coro = conn.prompt(
                        prompt=[text_block(prompt_text)],
                        session_id=retry_session_id,
                    )
                    if effective_config.timeout is not None:
                        await asyncio.wait_for(
                            retry_coro, timeout=float(effective_config.timeout)
                        )
                    else:
                        await retry_coro
                    # Update session_id so response_complete log is accurate
                    session_id = retry_session_id
                except AcpRequestError as retry_exc:
                    raise NetworkError(
                        f"ACP request failed for step '{step_name}' after "
                        f"reconnect: {retry_exc}",
                    ) from retry_exc

            # Check circuit breaker
            if client.aborted:
                # Find the most-called tool for the error message
                most_called_tool = _find_most_called_tool(client)
                raise CircuitBreakerError(
                    tool_name=most_called_tool,
                    call_count=MAX_SAME_TOOL_CALLS,
                    max_calls=MAX_SAME_TOOL_CALLS,
                    agent_name=agent_name,
                )

            accumulated_text = client.get_accumulated_text()

            self._logger.debug(
                "acp_executor.response_complete",
                step_name=step_name,
                session_id=session_id,
                response_len=len(accumulated_text),
            )

            # Extract and validate output
            if output_schema is not None:
                return _extract_json_output(
                    text=accumulated_text,
                    output_schema=output_schema,
                    step_name=step_name,
                )
            return accumulated_text

        if max_attempts <= 1:
            output = await _run_single_attempt()
            return output, resolved_model_label[0]

        # Retry with tenacity
        result: Any = None
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=1, min=wait_min, max=wait_max),
            reraise=True,
        ):
            with attempt:
                result = await _run_single_attempt()
        return result, resolved_model_label[0]


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


async def _wait_for_process(proc: Any, timeout: float = 3.0) -> None:
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
        with contextlib.suppress(Exception):
            await asyncio.wait_for(proc.wait(), timeout=1.0)
    except Exception:
        pass


def _resolve_model_for_provider(
    requested_model: str,
    session: Any,
) -> str:
    """Map a semantic model name to the ACP provider's actual model ID.

    ACP providers (notably Claude Code) advertise models with short IDs like
    ``"default"`` and ``"opus"`` (or ``"default"`` and ``"sonnet"``).  The
    identity behind ``"default"`` changes between sessions.  This function
    lets ``maverick.yaml`` use stable semantic names (``"sonnet"``,
    ``"opus"``, or full model IDs like ``"claude-sonnet-4-5-20250929"``) and
    resolves them to whatever ID the provider currently exposes.

    Resolution steps:
    1. If ``requested_model`` is already in the available IDs → return as-is.
    2. Determine the *model type* (haiku / sonnet / opus) from the request.
    3. Scan each available model's ``name`` field for a case-insensitive
       match on the type (e.g. ``"Claude Sonnet 4.6"`` contains ``"sonnet"``).
    4. If no match is found, return the original ``requested_model`` unchanged
       (the caller's existing validation will raise if it's truly invalid).

    Args:
        requested_model: Model identifier from maverick.yaml / StepConfig.
        session: ACP NewSessionResponse with ``models`` attribute.

    Returns:
        The provider model ID to pass to ``set_session_model``.
    """
    available_ids = _get_available_model_ids(session)
    if not available_ids or requested_model in available_ids:
        return requested_model

    # Determine what model *type* the user is asking for.
    model_type = get_model_type(requested_model)
    if model_type is None:
        # Not a recognised Claude model name — return as-is for the
        # downstream validator to handle.
        return requested_model

    # Pass 1: Match by human-readable name (most reliable).
    models_state = getattr(session, "models", None)
    if models_state:
        for m in getattr(models_state, "available_models", []):
            mid = getattr(m, "model_id", None)
            name = getattr(m, "name", None) or ""
            if mid and model_type in name.lower():
                return str(mid)

    # Fallback: return the original so that the existing validation
    # surfaces a clear error with the available model list.
    return requested_model


def _resolve_model_label(
    session: Any,
    resolved_model: str | None,
) -> str | None:
    """Build a human-readable model label from the ACP session.

    Prefers the ``name`` field from ``ModelInfo`` (e.g. "Claude Opus 4.6")
    over the bare ``model_id`` (e.g. "opus"). Falls back to
    ``current_model_id`` when no explicit model was requested.

    Args:
        session: ACP NewSessionResponse.
        resolved_model: Model ID explicitly set on the session, or None.

    Returns:
        Display label like "Claude Opus 4.6", or None if unavailable.
    """
    models_state = getattr(session, "models", None)
    if not models_state:
        return resolved_model or None

    # Determine which model_id to look up
    model_id = resolved_model or getattr(
        models_state,
        "current_model_id",
        None,
    )
    if not model_id:
        return None

    # Try to find the full name from available_models
    for m in getattr(models_state, "available_models", []):
        if getattr(m, "model_id", None) == model_id:
            name = getattr(m, "name", None)
            if name:
                return str(name)
            break

    return model_id


def _get_available_model_ids(session: Any) -> set[str]:
    """Extract available model IDs from a NewSessionResponse.

    Checks both ``session.models.available_models`` and
    ``session.config_options`` (config_id="model") since providers
    may advertise models in either or both locations.

    Args:
        session: ACP NewSessionResponse.

    Returns:
        Set of model ID strings, or empty set if unavailable.
    """
    ids: set[str] = set()
    # Source 1: models.available_models (unstable but common)
    models = getattr(session, "models", None)
    if models:
        for m in getattr(models, "available_models", []):
            model_id = getattr(m, "model_id", None)
            if model_id:
                ids.add(model_id)
    # Source 2: config_options with id="model"
    config_options = getattr(session, "config_options", None)
    if config_options:
        for opt in config_options:
            root = getattr(opt, "root", opt)
            if getattr(root, "id", None) == "model":
                for o in getattr(root, "options", []):
                    val = getattr(o, "value", None)
                    if val:
                        ids.add(val)
    return ids


def _find_most_called_tool(client: MaverickAcpClient) -> str:
    """Return the name of the most-called tool from client state.

    Used to populate CircuitBreakerError with a meaningful tool name.

    Args:
        client: MaverickAcpClient with session state populated.

    Returns:
        Tool name with highest call count, or "unknown_tool" if unavailable.
    """
    try:
        counts: dict[str, int] = client._state.tool_call_counts
        if counts:
            return max(counts, key=lambda k: counts[k])
    except Exception:
        pass
    return "unknown_tool"


def _extract_json_output(
    text: str,
    output_schema: type[BaseModel],
    step_name: str,
) -> BaseModel:
    """Extract and validate the last JSON block from agent output text.

    Tries fenced ```json ... ``` code blocks first, then falls back to the
    last brace-matched ``{...}`` block in the text.

    Args:
        text: Raw accumulated text from the ACP agent.
        output_schema: Pydantic BaseModel subclass to validate against.
        step_name: DSL step name (for error context).

    Returns:
        Validated Pydantic model instance.

    Raises:
        MalformedResponseError: If no JSON block is found or parsing fails.
        OutputSchemaValidationError: If the extracted JSON fails schema validation.
    """
    json_str: str | None = None

    # Strategy 1: fenced ```json ... ``` code block (take the last one)
    fenced_matches = list(re.finditer(r"```json\s*([\s\S]*?)```", text, re.IGNORECASE))
    if fenced_matches:
        json_str = fenced_matches[-1].group(1).strip()

    # Strategy 2: last brace-matched {...} block
    if json_str is None:
        json_str = _extract_last_json_object(text)

    if json_str is None:
        raise MalformedResponseError(
            message=(
                f"Step '{step_name}': no JSON block found in agent output. "
                "Expected a ```json ... ``` block or a top-level JSON object."
            ),
            raw_response=text[:500] if text else None,
        )

    # ---- Stage 1: Parse JSON string to Python dict ----
    raw_data = _parse_json_lenient(json_str, step_name)

    # ---- Stage 2: Validate, with coercion fallback ----
    # Try direct validation first (fast path for well-behaved agents).
    try:
        return output_schema.model_validate(raw_data)
    except ValidationError:
        pass

    # Coerce agent output to match schema (e.g., dicts → strings in
    # array-of-string fields). This handles the systematic mismatch where
    # agents produce rich objects that the schema types as flat strings.
    try:
        schema = output_schema.model_json_schema()
        coerced = _coerce_to_schema(raw_data, schema)
        return output_schema.model_validate(coerced)
    except ValidationError as exc:
        raise OutputSchemaValidationError(step_name, output_schema, exc) from exc


def _parse_json_lenient(json_str: str, step_name: str) -> Any:
    """Parse a JSON string, attempting truncation repair on failure.

    Pipeline:
    1. Try ``json.loads()`` directly.
    2. On failure, attempt to repair truncated output (close open strings,
       arrays, objects) and retry.
    3. If both fail, raise ``MalformedResponseError``.

    Args:
        json_str: Raw JSON string extracted from agent output.
        step_name: Step name for logging context.

    Returns:
        Parsed Python data (dict/list).

    Raises:
        MalformedResponseError: If the JSON cannot be parsed even after repair.
    """
    # Fast path
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as first_err:
        logger.debug(
            "acp_executor.json_parse_failed",
            step_name=step_name,
            error=str(first_err),
            json_len=len(json_str),
        )

    # Common LLM quirk: agents produce Python-style escaped single quotes
    # (\') which are invalid in JSON.  Strip the backslash — single quotes
    # are legal unescaped in JSON strings.
    sanitized = json_str.replace("\\'", "'")
    if sanitized != json_str:
        try:
            result = json.loads(sanitized)
            logger.info(
                "acp_executor.json_sanitized_single_quotes",
                step_name=step_name,
            )
            return result
        except json.JSONDecodeError:
            pass

    # Repair path — close truncated structures
    repaired = _repair_truncated_json(json_str)
    if repaired is not None:
        try:
            result = json.loads(repaired)
            logger.warning(
                "acp_executor.json_repaired",
                step_name=step_name,
                original_len=len(json_str),
                repaired_len=len(repaired),
            )
            return result
        except json.JSONDecodeError:
            pass

    raise MalformedResponseError(
        message=(
            f"Step '{step_name}': extracted JSON could not be parsed "
            f"(possibly truncated agent output, {len(json_str)} chars). "
            f"Tail: ...{json_str[-200:]!r}"
        ),
        raw_response=json_str[-500:] if len(json_str) > 500 else json_str,
    )


def _repair_truncated_json(text: str) -> str | None:
    """Attempt to repair JSON truncated mid-output by closing open structures.

    Handles common truncation patterns where the agent hit a token limit
    mid-JSON: unclosed strings, arrays, and objects. Walks the text tracking
    string/escape state and brace depth, then appends closing delimiters.

    Args:
        text: Potentially truncated JSON string.

    Returns:
        Repaired JSON string, or None if repair is not feasible.
    """
    if not text or not text.lstrip().startswith("{"):
        return None

    repaired = text.rstrip()

    # Single pass: track string state, brace/bracket depth
    in_string = False
    escaped = False
    brace_depth = 0
    bracket_depth = 0

    for ch in repaired:
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            if in_string:
                escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            brace_depth += 1
        elif ch == "}":
            brace_depth -= 1
        elif ch == "[":
            bracket_depth += 1
        elif ch == "]":
            bracket_depth -= 1

    # Close unclosed string
    if in_string:
        repaired += '"'

    # Strip trailing comma (invalid before closing delimiter)
    stripped = repaired.rstrip()
    if stripped.endswith(","):
        repaired = stripped[:-1]

    # Close unclosed brackets then braces (innermost first)
    repaired += "]" * bracket_depth
    repaired += "}" * brace_depth

    return repaired


def _coerce_to_schema(data: Any, schema: dict[str, Any]) -> Any:
    """Best-effort coercion of parsed JSON to match a JSON Schema.

    Handles the common agent mismatch where dict/list values appear where
    the schema expects strings, by converting them to compact JSON strings.

    Args:
        data: Parsed JSON data.
        schema: JSON Schema dict from Pydantic's ``model_json_schema()``.

    Returns:
        Coerced data that is more likely to pass validation.
    """
    schema_type = schema.get("type")

    if schema_type == "object":
        if not isinstance(data, dict):
            return data
        props = schema.get("properties", {})
        result = {}
        for key, value in data.items():
            if key in props:
                result[key] = _coerce_to_schema(value, props[key])
            else:
                result[key] = value
        return result

    if schema_type == "array":
        if not isinstance(data, (list, tuple)):
            return data
        items_schema = schema.get("items", {})
        return [_coerce_to_schema(item, items_schema) for item in data]

    if schema_type == "string":
        if isinstance(data, str):
            return data
        # Convert non-string values (dicts, lists) to compact JSON
        return json.dumps(data, ensure_ascii=False)

    return data


def _extract_last_json_object(text: str) -> str | None:
    """Find the last balanced ``{...}`` object in text.

    Scans the text from right to left for ``}`` characters, then walks
    backwards matching braces to find the corresponding opening ``{``.

    Args:
        text: Text to scan for a JSON object.

    Returns:
        The last balanced JSON object string, or None if not found.
    """
    last_close = text.rfind("}")
    if last_close == -1:
        return None

    depth = 0
    in_string = False

    for i in range(last_close, -1, -1):
        ch = text[i]
        if ch == '"':
            # Count preceding backslashes to determine if this quote is escaped.
            # An odd number means the quote is escaped; even means it is not.
            num_backslashes = 0
            j = i - 1
            while j >= 0 and text[j] == "\\":
                num_backslashes += 1
                j -= 1
            if num_backslashes % 2 == 0:
                in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "}":
            depth += 1
        elif ch == "{":
            depth -= 1
            if depth == 0:
                candidate = text[i : last_close + 1]
                # Validate it's parseable JSON before returning
                try:
                    json.loads(candidate)
                    return candidate
                except (json.JSONDecodeError, ValueError):
                    return None

    return None
