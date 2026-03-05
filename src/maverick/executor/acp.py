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
import importlib.metadata
import json
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
    version=importlib.metadata.version("maverick"),
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
    ) -> None:
        self._provider_registry = provider_registry
        self._agent_registry = agent_registry
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
        if not self._agent_registry.agents.has(agent_name):
            raise ReferenceResolutionError(
                reference_type="agent",
                reference_name=agent_name,
                available_names=self._agent_registry.agents.list_names(),
            )

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

        # Prepend system instructions when provided
        if instructions:
            prompt_text = (
                f"[SYSTEM INSTRUCTIONS]\n{instructions}\n\n---\n\n{raw_prompt}"
            )
        else:
            prompt_text = raw_prompt

        # --- Get or create cached ACP connection ---
        cached = await self._get_or_create_connection(provider_name, provider_config)

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

        try:
            output = await self._execute_with_retry(
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
        )

    async def cleanup(self) -> None:
        """Close all cached ACP connections and terminate subprocesses.

        Safe to call multiple times. Logs at INFO level for each connection
        closed (FR-023). Errors during cleanup are logged but not raised.
        """
        for provider_name, cached in list(self._connections.items()):
            self._logger.info(
                "acp_executor.cleanup",
                provider=provider_name,
            )
            try:
                await cached.ctx.__aexit__(None, None, None)
            except Exception as exc:
                self._logger.debug(
                    "acp_executor.cleanup_ctx_error",
                    provider=provider_name,
                    error=str(exc),
                )
        self._connections.clear()

    async def _get_or_create_connection(
        self,
        provider_name: str,
        provider_config: AgentProviderConfig,
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
        env = dict(provider_config.env) if provider_config.env else None

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
            ctx = spawn_agent_process(client, command, *args, env=env)
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
            try:
                stale.proc.terminate()
            except Exception as term_exc:
                self._logger.debug(
                    "acp_executor.reconnect_terminate_error",
                    provider=provider_name,
                    error=str(term_exc),
                )

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
    ) -> Any:
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
            Extracted output (validated BaseModel instance or raw string).

        Raises:
            CircuitBreakerError: Circuit breaker triggered.
            MaverickTimeoutError: Step exceeded timeout.
            OutputSchemaValidationError: Output failed schema validation.
            NetworkError: Connection drop persisted after one reconnect attempt.
            AgentError: Other execution failures.
        """
        # Mutable reference so _run_single_attempt always uses the latest connection
        # after a transparent reconnect.
        current_cached: list[CachedConnection] = [cached]

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
            return await _run_single_attempt()

        # Retry with tenacity
        result: Any = None
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=1, min=wait_min, max=wait_max),
            reraise=True,
        ):
            with attempt:
                result = await _run_single_attempt()
        return result


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


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

    try:
        return output_schema.model_validate_json(json_str)
    except ValidationError as exc:
        raise OutputSchemaValidationError(step_name, output_schema, exc) from exc
    except (json.JSONDecodeError, ValueError) as exc:
        raise MalformedResponseError(
            message=(f"Step '{step_name}': extracted JSON could not be parsed: {exc}"),
            raw_response=json_str[:500],
        ) from exc


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
