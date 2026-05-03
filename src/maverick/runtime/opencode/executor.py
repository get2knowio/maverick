"""OpenCode-backed implementation of :class:`StepExecutor`.

The OpenCode-substrate landing point for single-shot agent runs and
multi-turn sessions outside the xoscar mailbox-actor flow. The
public surface is now:

* :meth:`OpenCodeStepExecutor.execute_named` — run a bundled
  OpenCode markdown persona by name (the canonical path).
* :meth:`OpenCodeStepExecutor.create_session` /
  :meth:`prompt_session` / :meth:`cancel_session` /
  :meth:`close_session` — multi-turn session API for callers that
  hold a session id across multiple sends.

Mailbox actors don't go through the executor at all; they use
:class:`maverick.actors.xoscar.opencode_mixin.OpenCodeAgentMixin`
directly, which builds its own :class:`OpenCodeClient`.

Errors surface via classified :class:`OpenCodeError` subclasses
(Landmines 1-3 mitigations baked in). ``result_model`` translates
to ``format=json_schema`` so the model is forced to call OpenCode's
``StructuredOutput`` tool when typed output is required.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from maverick.exceptions.agent import AgentError
from maverick.executor.config import DEFAULT_EXECUTOR_CONFIG, StepConfig
from maverick.executor.errors import OutputSchemaValidationError
from maverick.executor.protocol import EventCallback
from maverick.executor.result import ExecutorResult, UsageMetadata
from maverick.logging import get_logger
from maverick.runtime.opencode.client import (
    OpenCodeClient,
    SendResult,
    structured_of,
    structured_valid,
    text_of,
)
from maverick.runtime.opencode.errors import (
    OpenCodeError,
    OpenCodeStructuredOutputError,
)
from maverick.runtime.opencode.server import (
    OpenCodeServerHandle,
    spawn_opencode_server,
)
from maverick.runtime.opencode.validation import validate_model_id

logger = get_logger(__name__)


class OpenCodeStepExecutor:
    """OpenCode-backed adapter satisfying the :class:`StepExecutor` Protocol.

    Owns either an externally-supplied :class:`OpenCodeServerHandle` (when
    invoked inside ``actor_pool(with_opencode=True)``) or a server it
    spawned itself (lazy on first use). Either way, :meth:`cleanup`
    terminates the spawned process — externally-supplied handles are
    left alone.

    Args:
        global_max_tokens: Reserved for parity with the legacy executor;
            currently unused (OpenCode's per-message ``max_tokens`` flag
            isn't wired up yet).
        server_handle: Optional pre-spawned handle. When ``None``, the
            executor lazily spawns one on first use and tears it down in
            :meth:`cleanup`.
        password: Optional override for the bearer password — only used
            when ``server_handle`` is ``None`` and we spawn ourselves.
    """

    def __init__(
        self,
        *,
        global_max_tokens: int | None = None,
        server_handle: OpenCodeServerHandle | None = None,
        password: str | None = None,
    ) -> None:
        self._global_max_tokens = global_max_tokens
        self._handle: OpenCodeServerHandle | None = server_handle
        self._owns_handle = server_handle is None
        self._password = password
        self._client: OpenCodeClient | None = None
        self._sessions: dict[str, _SessionState] = {}
        self._session_invalidator: Any = None
        self._logger = logger

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def cleanup(self) -> None:
        """Drop sessions, close the client, terminate any spawned server."""
        client = self._client
        self._client = None
        if client is not None:
            for sid in list(self._sessions):
                try:
                    await client.delete_session(sid)
                except OpenCodeError as exc:
                    self._logger.debug(
                        "opencode_executor.session_delete_failed",
                        session_id=sid,
                        error=str(exc),
                    )
            self._sessions.clear()
            try:
                await client.aclose()
            except Exception as exc:  # noqa: BLE001 — teardown must not raise
                self._logger.debug("opencode_executor.client_close_failed", error=str(exc))
        if self._owns_handle and self._handle is not None:
            try:
                await self._handle.stop()
            except Exception as exc:  # noqa: BLE001
                self._logger.debug("opencode_executor.server_stop_failed", error=str(exc))
            self._handle = None

    async def cleanup_for_eviction(self) -> None:
        """Drop sessions and the client without killing the server.

        Mirrors the legacy executor's eviction hook so an actor pool's
        subprocess quota can recycle this executor's slot. The server
        stays up because other executors may still be using it (when
        ``server_handle`` was passed in at construction time).
        """
        if self._session_invalidator is not None:
            try:
                await self._session_invalidator()
            except Exception as exc:  # noqa: BLE001 — best effort
                self._logger.debug(
                    "opencode_executor.session_invalidator_failed",
                    error=str(exc),
                )
        client = self._client
        self._client = None
        if client is not None:
            for sid in list(self._sessions):
                try:
                    await client.delete_session(sid)
                except OpenCodeError:
                    pass
            try:
                await client.aclose()
            except Exception:  # noqa: BLE001
                pass
        self._sessions.clear()

    def set_session_invalidator(self, callback: Any) -> None:
        """Register a hook that fires when sessions get invalidated.

        Used by mailbox actors that cache session ids and need a chance
        to clear them before the executor's transport tears down.
        """
        self._session_invalidator = callback

    # ------------------------------------------------------------------
    # Named-agent entry point — the OpenCode-native path
    # ------------------------------------------------------------------

    async def execute_named(
        self,
        *,
        agent: str,
        user_prompt: str,
        step_name: str = "execute_named",
        result_model: type[BaseModel] | None = None,
        cwd: Path | None = None,
        config: StepConfig | None = None,
        timeout: float | None = None,
    ) -> ExecutorResult:
        """Run a single prompt against a bundled OpenCode agent persona.

        The persona's system prompt comes from
        ``runtime/opencode/profile/agents/<agent>.md`` (loaded by
        OpenCode via the per-message ``agent=`` selector) — the caller
        only supplies the per-call user prompt and an optional
        Pydantic ``result_model`` for structured output.

        Args:
            agent: Bundled persona name, e.g. ``"maverick.curator"``.
                Must match a markdown file in the OpenCode profile
                agents directory.
            user_prompt: The per-call user message body (already
                templated by the caller).
            step_name: Logical step name used for logging and for
                titling the OpenCode session (default
                ``"execute_named"``).
            result_model: Optional Pydantic model to force structured
                output. When set, the runtime adds
                ``format=json_schema`` and validates the response.
                When ``None``, the assistant's plain text is returned.
            cwd: Optional working directory (currently advisory; the
                OpenCode profile carries the persona-specific
                permission set).
            config: Optional :class:`StepConfig`; ignored model/provider
                fields fall through to the OpenCode server's defaults
                or the profile-declared model.
            timeout: Per-call wallclock budget (seconds). Falls back to
                ``config.timeout`` and finally to the executor default
                of 600 s.

        Returns:
            :class:`ExecutorResult` carrying either the validated
            payload (when ``result_model`` was set) or the plain-text
            response.

        Raises:
            OpenCodeAuthError, OpenCodeModelNotFoundError,
            OpenCodeContextOverflowError, OpenCodeStructuredOutputError,
            OpenCodeError: classified failures from the runtime.
            OutputSchemaValidationError: when ``result_model`` is set
                and the response payload didn't validate.
        """
        del cwd  # accepted for caller parity; OpenCode resolves cwd via profile
        effective_config = config if config is not None else DEFAULT_EXECUTOR_CONFIG
        effective_timeout = timeout if timeout is not None else _resolve_timeout(effective_config)
        start_time = time.monotonic()

        self._logger.info(
            "opencode_executor.named_step_start",
            step_name=step_name,
            agent=agent,
            timeout=effective_timeout,
        )

        client = await self._ensure_client()
        provider_id, model_id = self._resolve_model_binding(effective_config)
        if provider_id and model_id:
            await validate_model_id(client, provider_id, model_id)

        format_block: dict[str, Any] | None = None
        if result_model is not None:
            format_block = {
                "type": "json_schema",
                "schema": result_model.model_json_schema(),
            }
        model_block: dict[str, str] | None = None
        if provider_id and model_id:
            model_block = {"providerID": provider_id, "modelID": model_id}

        session_id = await client.create_session(title=f"step:{step_name}")
        try:
            send_result: SendResult = await client.send_with_event_watch(
                session_id,
                user_prompt,
                model=model_block,
                agent=agent,
                format=format_block,
                timeout=effective_timeout,
            )
        finally:
            try:
                await client.delete_session(session_id)
            except OpenCodeError as exc:
                self._logger.debug(
                    "opencode_executor.delete_session_failed",
                    session_id=session_id,
                    error=str(exc),
                )

        output, usage, model_label = self._build_output(send_result, result_model, step_name)
        duration_ms = int((time.monotonic() - start_time) * 1000)
        self._logger.info(
            "opencode_executor.named_step_complete",
            step_name=step_name,
            agent=agent,
            duration_ms=duration_ms,
            success=True,
        )
        return ExecutorResult(
            output=output,
            success=True,
            usage=usage,
            events=(),
            model_label=model_label,
        )

    # ------------------------------------------------------------------
    # Multi-turn session API (parity with the legacy executor)
    # ------------------------------------------------------------------

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
        mcp_servers: list[Any] | None = None,
    ) -> str:
        """Open a persistent OpenCode session and return its id.

        The session stays alive until :meth:`close_session`,
        :meth:`cleanup_for_eviction`, or :meth:`cleanup` is called. The
        ``mcp_servers`` argument is accepted for source compatibility
        with :class:`AcpStepExecutor` but ignored — external MCP servers
        attach via :file:`opencode.jsonc` instead.
        """
        if mcp_servers:
            self._logger.debug(
                "opencode_executor.mcp_servers_ignored",
                step_name=step_name,
                count=len(mcp_servers),
            )
        del allowed_tools, event_callback, agent_name  # currently unused
        effective_config = config if config is not None else DEFAULT_EXECUTOR_CONFIG
        if provider is not None:
            effective_config = effective_config.model_copy(update={"provider": provider})

        client = await self._ensure_client()
        provider_id, model_id = self._resolve_model_binding(effective_config)
        if provider_id and model_id:
            await validate_model_id(client, provider_id, model_id)

        session_id = await client.create_session(title=f"session:{step_name}")
        self._sessions[session_id] = _SessionState(
            cwd=str(cwd) if cwd is not None else None,
            provider_id=provider_id,
            model_id=model_id,
        )
        self._logger.info(
            "opencode_executor.session_created",
            session_id=session_id,
            provider=provider_id,
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
        """Send a follow-up prompt on an existing session."""
        del provider  # currently unused — model is locked at session creation
        if session_id not in self._sessions:
            raise AgentError(
                f"OpenCodeStepExecutor has no active session {session_id!r}; "
                "call create_session() first.",
                agent_name=agent_name,
            )
        client = await self._ensure_client()
        state = self._sessions[session_id]
        effective_config = config if config is not None else DEFAULT_EXECUTOR_CONFIG
        # Per-prompt overrides take priority over the session-time defaults.
        provider_id = effective_config.provider or state.provider_id
        model_id = effective_config.model_id or state.model_id

        send_result = await self._send_for_step(
            client=client,
            session_id=session_id,
            prompt_text=prompt_text,
            output_schema=output_schema,
            provider_id=provider_id,
            model_id=model_id,
            cwd=Path(state.cwd) if state.cwd else None,
            timeout=_resolve_timeout(effective_config),
            event_callback=event_callback,
        )
        output, usage, model_label = self._build_output(send_result, output_schema, step_name)
        return ExecutorResult(
            output=output,
            success=True,
            usage=usage,
            events=(),
            model_label=model_label,
        )

    async def cancel_session(
        self,
        session_id: str,
        provider: str | None = None,
    ) -> None:
        """Best-effort abort of any in-flight prompt on ``session_id``."""
        del provider
        client = self._client
        if client is None or session_id not in self._sessions:
            return
        try:
            await client.cancel(session_id)
        except OpenCodeError as exc:
            self._logger.debug(
                "opencode_executor.cancel_failed",
                session_id=session_id,
                error=str(exc),
            )

    async def close_session(self, session_id: str) -> None:
        """Drop an active session. Idempotent."""
        client = self._client
        state = self._sessions.pop(session_id, None)
        if client is None or state is None:
            return
        try:
            await client.delete_session(session_id)
        except OpenCodeError as exc:
            self._logger.debug(
                "opencode_executor.close_session_failed",
                session_id=session_id,
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _ensure_client(self) -> OpenCodeClient:
        if self._client is not None:
            return self._client
        if self._handle is None:
            # Lazy-spawn a server. Caller didn't provide one — that's fine
            # for CLI / one-shot work; expensive for tight loops, but
            # those should pass a handle in.
            self._handle = await spawn_opencode_server(password=self._password)
            self._owns_handle = True
        self._client = OpenCodeClient(
            base_url=self._handle.base_url,
            password=self._handle.password,
        )
        return self._client

    def _resolve_model_binding(self, config: StepConfig) -> tuple[str | None, str | None]:
        return config.provider, config.model_id

    async def _send_for_step(
        self,
        *,
        client: OpenCodeClient,
        session_id: str,
        prompt_text: str,
        output_schema: type[BaseModel] | None,
        provider_id: str | None,
        model_id: str | None,
        cwd: Path | None,
        timeout: float,
        event_callback: EventCallback | None,
    ) -> SendResult:
        del cwd, event_callback  # accepted for parity, currently unused
        format_block: dict[str, Any] | None = None
        if output_schema is not None:
            format_block = {
                "type": "json_schema",
                "schema": output_schema.model_json_schema(),
            }
        model_block: dict[str, str] | None = None
        if provider_id and model_id:
            model_block = {"providerID": provider_id, "modelID": model_id}
        return await client.send_with_event_watch(
            session_id,
            prompt_text,
            model=model_block,
            format=format_block,
            timeout=timeout,
        )

    def _build_output(
        self,
        send_result: SendResult,
        output_schema: type[BaseModel] | None,
        step_name: str,
    ) -> tuple[Any, UsageMetadata | None, str | None]:
        info = send_result.info or {}
        usage: UsageMetadata | None = None
        tokens = info.get("tokens") if isinstance(info, dict) else None
        cost = info.get("cost") if isinstance(info, dict) else None
        if isinstance(tokens, dict):
            cache = tokens.get("cache") or {}
            cache_read = int(cache.get("read", 0) or 0) if isinstance(cache, dict) else 0
            cache_write = int(cache.get("write", 0) or 0) if isinstance(cache, dict) else 0
            usage = UsageMetadata(
                input_tokens=int(tokens.get("input", 0) or 0),
                output_tokens=int(tokens.get("output", 0) or 0),
                cache_read_tokens=cache_read,
                cache_write_tokens=cache_write,
                total_cost_usd=float(cost) if isinstance(cost, int | float) else None,
            )

        model_label: str | None = None
        if isinstance(info, dict):
            mid = info.get("modelID")
            pid = info.get("providerID")
            if mid and pid:
                model_label = f"{pid}/{mid}"
            elif mid:
                model_label = str(mid)

        if output_schema is None:
            return send_result.text, usage, model_label

        # Structured-output path: the StructuredOutput tool was forced;
        # use the unwrapped payload from the SendResult.
        payload = send_result.structured
        if payload is None:
            # No structured output emitted. Fall back to extracting JSON from
            # text — same defence-in-depth as the legacy executor's
            # output_schema flow.
            from maverick.executor._json_output import extract_json_output

            try:
                return (
                    extract_json_output(send_result.text, output_schema, step_name),
                    usage,
                    model_label,
                )
            except Exception as exc:
                raise OpenCodeStructuredOutputError(
                    "OpenCode response had no StructuredOutput payload and "
                    f"text-output extraction failed: {exc}",
                    body=send_result.message,
                ) from exc
        try:
            return output_schema.model_validate(payload), usage, model_label
        except ValidationError as exc:
            raise OutputSchemaValidationError(
                step_name=step_name,
                schema_type=output_schema,
                validation_errors=exc,
            ) from exc


class _SessionState:
    """Per-session sticky bindings (cwd, provider, model)."""

    __slots__ = ("cwd", "provider_id", "model_id")

    def __init__(
        self,
        *,
        cwd: str | None,
        provider_id: str | None,
        model_id: str | None,
    ) -> None:
        self.cwd = cwd
        self.provider_id = provider_id
        self.model_id = model_id


def _resolve_timeout(config: StepConfig) -> float:
    """Map a :class:`StepConfig.timeout` (int seconds) to a float."""
    if config.timeout is not None:
        return float(config.timeout)
    return 600.0


__all__ = ["OpenCodeStepExecutor"]


# Re-exports used by tests and callers that want the full SendResult shape.
__all__ += ["structured_of", "structured_valid", "text_of"]
