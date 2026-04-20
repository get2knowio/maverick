"""AcpStepExecutor — ACP adapter implementing the StepExecutor protocol.

This module provides an ACP-based executor that spawns agent subprocesses via
the agent-client-protocol SDK and communicates over stdio. It supports:
- Connection caching (one subprocess per provider, via :class:`ConnectionPool`)
- Per-session retry with tenacity
- Circuit breaker detection via MaverickAcpClient
- JSON output extraction for non-MCP text-response steps that opt into output_schema
- Proper error mapping to the Maverick exception hierarchy
- Transparent reconnect on connection drop (FR-021)

FR-023: Log subprocess spawn at INFO level.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from acp import RequestError as AcpRequestError
from acp import text_block
from pydantic import BaseModel
from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential

from maverick.config import AgentProviderConfig
from maverick.exceptions.agent import (
    AgentError,
    CircuitBreakerError,
    MaverickTimeoutError,
    NetworkError,
)
from maverick.exceptions.workflow import ReferenceResolutionError
from maverick.executor._connection_pool import CachedConnection, ConnectionPool
from maverick.executor._json_output import extract_json_output
from maverick.executor._model_resolver import (
    get_available_model_ids,
    resolve_model_for_provider,
    resolve_model_label,
)
from maverick.executor.acp_client import MAX_SAME_TOOL_CALLS, MaverickAcpClient
from maverick.executor.config import DEFAULT_EXECUTOR_CONFIG, StepConfig
from maverick.executor.protocol import EventCallback
from maverick.executor.provider_registry import AgentProviderRegistry
from maverick.executor.result import ExecutorResult
from maverick.logging import get_logger
from maverick.registry import ComponentRegistry

__all__ = ["AcpStepExecutor"]

logger = get_logger(__name__)

_GEMINI_MODEL_FLAG = "--model"
_GEMINI_PROVIDER = "gemini"


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
        self._logger = get_logger(__name__)
        self._pool = ConnectionPool(logger=self._logger)
        self._session_uses_tool_output_contract: dict[str, bool] = {}
        self._session_provider_keys: dict[str, str] = {}

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
        agent_kwargs: dict[str, Any] | None = None,
    ) -> ExecutorResult:
        """Execute an agent step via ACP and return a typed ExecutorResult.

        Args:
            step_name: DSL step name for observability logging.
            agent_name: Registered agent name in ComponentRegistry.
            prompt: Context passed to agent.build_prompt() to get a string prompt.
            instructions: Optional system instructions prepended to the prompt.
            allowed_tools: Tool allowlist forwarded to MaverickAcpClient.
            cwd: Working directory for the ACP session. None = current dir.
            output_schema: Optional Pydantic model for structured text-output
                validation. Do not use for MCP tool-backed/mailbox responses.
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
            agent_instance = agent_class(**(agent_kwargs or {}))
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
        effective_instructions = instructions or getattr(agent_instance, "instructions", None)

        # Append text-output schema guidance for non-MCP callers.
        if output_schema is not None:
            schema_json = json.dumps(output_schema.model_json_schema(), indent=2)
            raw_prompt = (
                f"{raw_prompt}\n\n---\n\n"
                f"[OUTPUT CONTRACT]\n"
                f"Respond with a single JSON object that conforms "
                f"exactly to this JSON Schema. Do not add explanatory "
                f"prose before or after the JSON. A ```json fence is "
                f"allowed but not required. Use only the field names "
                f"and types shown — do not nest objects where strings "
                f"are expected.\n\n"
                f"```json\n{schema_json}\n```"
            )

        if effective_instructions:
            prompt_text = f"[SYSTEM INSTRUCTIONS]\n{effective_instructions}\n\n---\n\n{raw_prompt}"
        else:
            prompt_text = raw_prompt

        # --- Get or create cached ACP connection ---
        effective_max_tokens = effective_config.max_tokens or self._global_max_tokens
        provider_key, runtime_provider_config = _resolve_runtime_provider_config(
            provider_name,
            provider_config,
            effective_config,
        )
        cached = await self._pool.get_or_create(
            provider_key,
            runtime_provider_config,
            max_output_tokens=effective_max_tokens,
        )

        # --- Resolve effective retry ---
        max_attempts = 1
        if effective_config.max_retries is not None and effective_config.max_retries > 0:
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
        allowed_tools_frozen = frozenset(allowed_tools) if allowed_tools is not None else None
        cwd_str = str(cwd) if cwd is not None else str(Path.cwd())

        model_label: str | None = None
        try:
            output, model_label = await self._execute_with_retry(
                step_name=step_name,
                agent_name=agent_name,
                prompt_text=prompt_text,
                cached=cached,
                provider_key=provider_key,
                provider_name=provider_name,
                provider_config=runtime_provider_config,
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
        """Close all cached ACP connections and terminate subprocesses."""
        await self._pool.close_all()
        self._session_uses_tool_output_contract.clear()
        self._session_provider_keys.clear()

    async def cancel_session(
        self,
        session_id: str,
        provider: str | None = None,
    ) -> None:
        """Cancel the in-flight turn on ``session_id``.

        Sends an ACP ``CancelNotification`` to the agent. The ongoing
        ``prompt_session`` call returns with ``StopReason.cancelled``;
        the session itself remains alive for future prompts. Best-effort:
        if the provider/session is not active, this is a no-op.
        """
        provider_key = self._session_provider_keys.get(session_id)
        if provider_key is None:
            if provider is not None:
                provider_key = provider
            else:
                provider_key, _ = self._provider_registry.default()

        if provider_key not in self._pool:
            return

        cached = self._pool[provider_key]
        try:
            await cached.conn.cancel(session_id)
        except Exception as exc:
            self._logger.debug(
                "acp_executor.cancel_failed",
                session_id=session_id,
                error=str(exc),
            )

    # -----------------------------------------------------------------
    # Multi-turn session support (actor-mailbox architecture)
    # -----------------------------------------------------------------

    async def create_session(
        self,
        *,
        provider: str | None = None,
        config: StepConfig | None = None,
        cwd: Path | None = None,
        step_name: str = "session",
        agent_name: str = "actor",
        event_callback: EventCallback | None = None,
        allowed_tools: list[str] | None = None,
        one_shot_tools: list[str] | None = None,
        mcp_servers: list[Any] | None = None,
    ) -> str:
        """Create a persistent ACP session and return its session_id.

        The session stays alive on the provider's subprocess until
        ``close_session`` is called or the executor is cleaned up.
        Use ``prompt_session`` to send follow-up prompts.

        Args:
            provider: Provider name. None = default provider.
            config: Step config for provider/model resolution.
            cwd: Working directory for the session.
            step_name: For logging/observability.
            agent_name: For logging/observability.
            event_callback: Async callback for streaming events.
            allowed_tools: Tool allowlist for the client.
            mcp_servers: MCP server configs (McpServerStdio) to attach
                to the session.  The agent subprocess spawns and connects
                to these servers, making their tools available. When these
                servers define the structured output contract, use their tool
                schemas instead of output_schema on prompt_session().

        Returns:
            The ACP session_id string.
        """
        effective_config = config if config is not None else DEFAULT_EXECUTOR_CONFIG

        if provider is not None:
            provider_name = provider
            provider_config = self._provider_registry.get(provider)
        elif effective_config.provider is not None:
            provider_name = effective_config.provider
            provider_config = self._provider_registry.get(effective_config.provider)
        else:
            provider_name, provider_config = self._provider_registry.default()

        effective_max_tokens = effective_config.max_tokens or self._global_max_tokens
        provider_key, runtime_provider_config = _resolve_runtime_provider_config(
            provider_name,
            provider_config,
            effective_config,
        )
        cached = await self._pool.get_or_create(
            provider_key,
            runtime_provider_config,
            max_output_tokens=effective_max_tokens,
        )

        cwd_str = str(cwd) if cwd else str(Path.cwd())

        # Reset client for the new session
        allowed_tools_frozen = frozenset(allowed_tools) if allowed_tools else None
        one_shot_frozen = frozenset(one_shot_tools) if one_shot_tools else None
        cached.client.reset(
            step_name=step_name,
            agent_name=agent_name,
            event_callback=event_callback,
            allowed_tools=allowed_tools_frozen,
            one_shot_tools=one_shot_frozen,
        )

        session = await cached.conn.new_session(cwd=cwd_str, mcp_servers=mcp_servers or [])
        session_id = session.session_id
        self._session_uses_tool_output_contract[session_id] = _uses_tool_output_contract(
            mcp_servers
        )
        self._session_provider_keys[session_id] = provider_key

        # Set model if configured
        resolved_model = effective_config.model_id or runtime_provider_config.default_model
        if resolved_model:
            resolved_model = resolve_model_for_provider(resolved_model, session)
            try:
                await cached.conn.set_session_model(
                    model_id=resolved_model,
                    session_id=session_id,
                )
            except Exception as exc:
                self._logger.warning(
                    "acp_executor.create_session_model_failed",
                    model_id=resolved_model,
                    error=str(exc),
                )

        self._logger.info(
            "acp_executor.session_created",
            session_id=session_id,
            provider=provider_name,
            step_name=step_name,
        )
        return session_id

    async def prompt_session(
        self,
        *,
        session_id: str,
        prompt_text: str,
        provider: str | None = None,
        config: StepConfig | None = None,
        step_name: str = "session",
        agent_name: str = "actor",
        event_callback: EventCallback | None = None,
        output_schema: type[BaseModel] | None = None,
    ) -> ExecutorResult:
        """Send a follow-up prompt to an existing ACP session.

        Unlike ``execute()``, this reuses the session created by
        ``create_session()`` — the agent retains full conversation
        history from prior prompts.  This is the mechanism that enables
        persistent context in the actor-mailbox architecture.

        Args:
            session_id: Session ID from ``create_session()``.
            prompt_text: The prompt text to send (already formatted).
            provider: Provider name. None = default.
            config: Step config for timeout resolution.
            step_name: For logging/observability.
            agent_name: For logging/observability.
            event_callback: Async callback for streaming events.
            output_schema: Optional Pydantic model for output extraction on
                plain text-response sessions. Incompatible with MCP tool-backed
                sessions whose structured output is delivered via tool calls.

        Returns:
            ExecutorResult with the agent's response.
        """
        effective_config = config if config is not None else DEFAULT_EXECUTOR_CONFIG

        provider_key = self._session_provider_keys.get(session_id)
        if provider_key is None:
            if provider is not None:
                provider_key = provider
            elif effective_config.provider is not None:
                provider_key = effective_config.provider
            else:
                provider_key, _ = self._provider_registry.default()

        if provider_key not in self._pool:
            raise AgentError(
                f"No active connection for provider '{provider_key}'. "
                f"Call create_session() first.",
                agent_name=agent_name,
            )

        cached = self._pool[provider_key]

        if output_schema is not None and self._session_uses_tool_output_contract.get(
            session_id, False
        ):
            raise AgentError(
                "output_schema is incompatible with MCP tool-backed sessions. "
                "Use the MCP tool schema as the agent-facing contract and "
                "validate typed payloads downstream of the tool call.",
                agent_name=agent_name,
            )

        # Reset per-turn accumulators, preserving session identity
        cached.client.reset_for_turn()
        if event_callback:
            cached.client._event_callback = event_callback

        self._logger.debug(
            "acp_executor.prompt_session",
            session_id=session_id,
            step_name=step_name,
            prompt_len=len(prompt_text),
        )

        start_time = time.monotonic()
        try:
            coro = cached.conn.prompt(
                prompt=[text_block(prompt_text)],
                session_id=session_id,
            )
            if effective_config.timeout is not None:
                await asyncio.wait_for(coro, timeout=float(effective_config.timeout))
            else:
                await coro
        except TimeoutError as exc:
            # Send an ACP CancelNotification so the agent stops the
            # stalled turn instead of leaving the session half-alive.
            # The session itself remains usable for future prompts.
            try:
                await cached.conn.cancel(session_id)
            except Exception as cancel_exc:
                self._logger.debug(
                    "acp_executor.cancel_after_timeout_failed",
                    session_id=session_id,
                    error=str(cancel_exc),
                )
            raise MaverickTimeoutError(
                f"ACP prompt on session '{session_id}' timed out after "
                f"{effective_config.timeout}s",
                timeout_seconds=float(effective_config.timeout or 0),
            ) from exc
        except AcpRequestError as exc:
            raise NetworkError(
                f"ACP prompt failed on session '{session_id}': {exc}",
            ) from exc

        # Check circuit breaker
        if cached.client.aborted:
            most_called_tool = _find_most_called_tool(cached.client)
            raise CircuitBreakerError(
                tool_name=most_called_tool,
                call_count=MAX_SAME_TOOL_CALLS,
                max_calls=MAX_SAME_TOOL_CALLS,
                agent_name=agent_name,
            )

        accumulated_text = cached.client.get_accumulated_text()
        duration_ms = int((time.monotonic() - start_time) * 1000)

        self._logger.debug(
            "acp_executor.prompt_session_complete",
            session_id=session_id,
            step_name=step_name,
            response_len=len(accumulated_text),
            duration_ms=duration_ms,
        )

        # Extract and validate output
        output: BaseModel | str
        if output_schema is not None:
            output = extract_json_output(
                text=accumulated_text,
                output_schema=output_schema,
                step_name=step_name,
            )
        else:
            output = accumulated_text

        return ExecutorResult(
            output=output,
            success=True,
            usage=None,
            events=(),
        )

    async def _execute_with_retry(
        self,
        *,
        step_name: str,
        agent_name: str,
        prompt_text: str,
        cached: CachedConnection,
        provider_key: str,
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
        """
        # Mutable references so _run_single_attempt always uses the latest
        # connection after a transparent reconnect, and captures the
        # resolved model label.
        current_cached: list[CachedConnection] = [cached]
        resolved_model_label: list[str | None] = [None]

        async def _run_single_attempt() -> Any:
            """Execute one ACP session: create session → prompt → extract output."""
            conn = current_cached[0].conn
            client = current_cached[0].client

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
                    current_cached[0] = await self._pool.reconnect(provider_key, provider_config)
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
                resolved_model = resolve_model_for_provider(resolved_model, session)

                available_ids = get_available_model_ids(session)
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
            label = resolve_model_label(
                session,
                resolved_model,
            )
            if label:
                resolved_model_label[0] = f"{provider_name}/{label}"

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
                    await asyncio.wait_for(coro, timeout=float(effective_config.timeout))
                else:
                    await coro
            except TimeoutError as exc:
                raise MaverickTimeoutError(
                    f"ACP step '{step_name}' timed out after {effective_config.timeout}s",
                    timeout_seconds=float(effective_config.timeout or 0),
                ) from exc
            except AcpRequestError:
                # Attempt one transparent reconnect and retry the full
                # session + prompt once before surfacing as NetworkError.
                try:
                    current_cached[0] = await self._pool.reconnect(provider_key, provider_config)
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
                        await asyncio.wait_for(retry_coro, timeout=float(effective_config.timeout))
                    else:
                        await retry_coro
                    # Update session_id so response_complete log is accurate
                    session_id = retry_session_id
                except AcpRequestError as retry_exc:
                    raise NetworkError(
                        f"ACP request failed for step '{step_name}' after reconnect: {retry_exc}",
                    ) from retry_exc

            # Check circuit breaker
            if client.aborted:
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

            if output_schema is not None:
                return extract_json_output(
                    text=accumulated_text,
                    output_schema=output_schema,
                    step_name=step_name,
                )
            return accumulated_text

        if max_attempts <= 1:
            output = await _run_single_attempt()
            return output, resolved_model_label[0]

        result: Any = None
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=1, min=wait_min, max=wait_max),
            reraise=True,
        ):
            with attempt:
                result = await _run_single_attempt()
        return result, resolved_model_label[0]


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


def _uses_tool_output_contract(mcp_servers: list[Any] | None) -> bool:
    """Return True when attached MCP servers define the output contract."""
    for server in mcp_servers or []:
        if getattr(server, "name", "") == "supervisor-inbox":
            return True

        args = getattr(server, "args", None) or []
        arg_strings = [str(arg) for arg in args]
        if "serve-inbox" in arg_strings:
            return True
        if any(arg.startswith("submit_") for arg in arg_strings):
            return True
    return False


def _resolve_runtime_provider_config(
    provider_name: str,
    provider_config: AgentProviderConfig,
    effective_config: StepConfig,
) -> tuple[str, AgentProviderConfig]:
    """Resolve the concrete provider cache key and launch config for a step."""
    requested_model = effective_config.model_id or provider_config.default_model
    if provider_name != _GEMINI_PROVIDER or not requested_model:
        return provider_name, provider_config

    command = provider_config.command
    if not command:
        return provider_name, provider_config

    updated_command = _set_cli_flag(command, _GEMINI_MODEL_FLAG, requested_model)
    updated_config = provider_config.model_copy(
        update={
            "command": updated_command,
            "default_model": requested_model,
        }
    )
    if requested_model == provider_config.default_model:
        return provider_name, updated_config
    return f"{provider_name}:{requested_model}", updated_config


def _set_cli_flag(command: list[str], flag: str, value: str) -> list[str]:
    """Return a CLI command with a single flag set to the requested value."""
    updated = list(command)
    try:
        flag_index = updated.index(flag)
    except ValueError:
        return [*updated, flag, value]

    value_index = flag_index + 1
    if value_index < len(updated):
        updated[value_index] = value
    else:
        updated.append(value)
    return updated
