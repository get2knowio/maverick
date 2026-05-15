"""``ClaudeCodeRuntime`` — :class:`AgentRuntime` over the Claude Agent SDK.

Wraps :class:`claude_agent_sdk.ClaudeSDKClient` to expose Maverick's
agent layer to Anthropic's Claude family via the official
``claude-agent-sdk`` package. The SDK spawns and manages the
``claude`` CLI subprocess; Maverick doesn't allocate ports, juggle
passwords, validate model IDs at startup, or maintain any client code.

**Auth.** Three options, checked in order:

1. ``CLAUDE_CODE_OAUTH_TOKEN`` env var — a long-lived OAuth token
   minted by ``claude setup-token``. Best for CI / non-interactive
   contexts.
2. ``~/.claude/.credentials.json`` — the interactive Claude Code
   OAuth flow's stored token. What you get when you've logged in
   via the ``claude`` CLI on this machine.
3. ``ANTHROPIC_API_KEY`` env var — pay-per-token API access (rather
   than subscription draw). Useful for production deployments
   without a Max subscription.

Per Anthropic's Feb 2026 terms update + the licensing relaxation that
followed, both the OAuth and API-key paths are now permitted for any
agent use case; OAuth-authenticated calls draw from a separate "Agent
SDK credit pool" starting June 15, 2026.

**Structured output.** Implemented via a hidden ``submit_result`` MCP
tool registered with the agent's schema. The model is forced (via
``allowed_tools`` + system-prompt prefix) to call ``submit_result``
exactly once with a typed payload; the runtime captures the args and
returns them as :attr:`RuntimeResult.structured`.

**Lifecycle.** ``execute()`` lazily constructs a
:class:`ClaudeSDKClient` keyed by ``(schema, system, model)`` — any
change to that triple forces a reconnect because the MCP tool's
``input_schema`` is baked into ``ClaudeAgentOptions`` at connect time.
Subsequent ``execute()`` calls reuse the subprocess (warm cache
accrues). ``reset()`` disconnects; the next ``execute()`` reconnects.
``aclose()`` is equivalent to ``reset()`` here.

**Cost.** The SDK exposes ``total_cost_usd`` on the
``ResultMessage`` — populated directly into the
:class:`CostRecord`. Token counts come from
``ResultMessage.usage``.

V0 spike → production lift: the algorithm is the same, but the
error types are now :mod:`maverick.runtime.errors` canonical names
(no leftover ``OpenCode*`` naming), the protocol is the v1
``AgentRuntime`` shape, and we honour ``CLAUDE_CODE_OAUTH_TOKEN``
for CI.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, ClassVar

from pydantic import BaseModel

from maverick.logging import get_logger
from maverick.runtime.cost import CostRecord
from maverick.runtime.errors import (
    AgentRuntimeError,
    RuntimeAuthError,
    RuntimeProtocolError,
    RuntimeServerStartError,
    RuntimeStructuredOutputError,
    RuntimeTransientError,
)
from maverick.runtime.protocol import (
    AgentRuntime,
    RuntimeResult,
    UnsupportedBindingError,
)
from maverick.runtime.tiers import ProviderModel

logger = get_logger(__name__)

#: Default Claude model when no binding is specified. Haiku is the
#: v0 default because it's the cheapest tier; opus is for frontier
#: roles. Selected per-call via ``ProviderModel.model_id``.
DEFAULT_CLAUDE_MODEL = "claude-haiku-4-5"

#: Canonical name for the hidden structured-output tool. Must match
#: what the runtime registers under ``ClaudeAgentOptions.mcp_servers``.
SUBMIT_RESULT_TOOL = "submit_result"
SUBMIT_RESULT_MCP_NAME = f"mcp__maverick_struct__{SUBMIT_RESULT_TOOL}"

#: Maximum number of agent turns the SDK is allowed to take inside one
#: ``execute()`` call before the loop is terminated. Briefings / outlines
#: can take 20-40 turns when the model reads files first; we leave room.
#: Probe-validated at 60 against the sample project's navigator briefing
#: which used ~20 turns reading files before calling submit_result.
DEFAULT_MAX_TURNS = 60


class ClaudeCodeRuntime(AgentRuntime):
    """One Claude Agent SDK client per runtime instance.

    Args:
        model: Default Claude model identifier used when ``execute()``
            is called without a ``ProviderModel`` override. Honours
            ``CLAUDE_MODEL_OVERRIDE`` env var if set for testing.
        max_turns: Hard cap on agent turns within one ``execute()``.
        api_key: Optional explicit Anthropic API key. When ``None``
            (default), auth resolves via the SDK's normal flow:
            ``CLAUDE_CODE_OAUTH_TOKEN`` env var → ``~/.claude/.credentials.json``
            → ``ANTHROPIC_API_KEY`` env var.
    """

    label = "claude_code"

    SUPPORTED_PROVIDER_IDS: ClassVar[frozenset[str]] = frozenset(
        {"anthropic", "claude", "claude-code", "claude-sdk"}
    )

    def __init__(
        self,
        *,
        model: str | None = None,
        max_turns: int = DEFAULT_MAX_TURNS,
        api_key: str | None = None,
    ) -> None:
        self._default_model = (
            model or os.environ.get("CLAUDE_MODEL_OVERRIDE") or DEFAULT_CLAUDE_MODEL
        )
        self._max_turns = max_turns
        # When the caller explicitly passes a key, plumb it into the
        # SDK's env so its auth resolution picks it up over the OAuth
        # paths. We don't mutate os.environ — we set it per-spawn via
        # ClaudeAgentOptions.env.
        self._api_key_override = api_key

        self._client: Any | None = None  # claude_agent_sdk.ClaudeSDKClient
        self._client_key: str | None = None
        self._captured_args: dict[str, Any] | None = None

    # --- AgentRuntime interface ---------------------------------------------

    async def execute(
        self,
        prompt: str,
        *,
        schema: type[BaseModel] | None = None,
        system: str | None = None,
        persona: str | None = None,
        model: ProviderModel | None = None,
        timeout: float = 600.0,
    ) -> RuntimeResult:
        if schema is None:
            raise NotImplementedError(
                "ClaudeCodeRuntime: plain-text execute() is not wired in v0; "
                "every consumer currently expects a typed payload"
            )

        model_id = self._resolve_model(model)
        client = await self._ensure_client(schema=schema, system=system, model=model_id)
        self._captured_args = None
        try:
            result_msg = await asyncio.wait_for(
                self._query_and_drain(client, prompt),
                timeout=timeout,
            )
        except TimeoutError as exc:
            raise RuntimeTransientError(
                f"claude_code: execute timed out after {timeout}s"
            ) from exc
        except Exception as exc:
            raise self._classify_exception(exc) from exc

        if result_msg is None:
            raise RuntimeProtocolError("claude_code: stream closed without a ResultMessage")
        if getattr(result_msg, "is_error", False):
            err_text = (result_msg.errors or [])[:1] or [result_msg.subtype or "unknown"]
            raise AgentRuntimeError(
                f"claude_code: is_error subtype={result_msg.subtype} {err_text}"
            )

        structured = self._captured_args
        if structured is None:
            preview = (result_msg.result or "")[:300]
            logger.debug(
                "claude_code.submit_result_missing",
                stop_reason=result_msg.stop_reason,
                subtype=getattr(result_msg, "subtype", None),
                result_preview=preview,
            )
            raise RuntimeStructuredOutputError(
                f"claude_code: submit_result was never called "
                f"(stop_reason={result_msg.stop_reason}, "
                f"subtype={getattr(result_msg, 'subtype', None)})",
                body={
                    "stop_reason": result_msg.stop_reason,
                    "subtype": getattr(result_msg, "subtype", None),
                    "result": result_msg.result,
                },
            )

        return RuntimeResult(
            text=result_msg.result or "",
            structured=structured,
            cost=self._cost_from_result(result_msg, model_id=model_id),
            finish=result_msg.stop_reason,
            raw=result_msg,
        )

    async def reset(self) -> None:
        client = self._client
        self._client = None
        self._client_key = None
        if client is None:
            return
        try:
            await client.disconnect()
        except Exception as exc:  # noqa: BLE001 — teardown never raises
            logger.debug("claude_code_runtime.reset_failed", error=str(exc))

    async def aclose(self) -> None:
        await self.reset()

    def validate_binding(self, binding: ProviderModel) -> bool:
        return binding.provider_id in self.SUPPORTED_PROVIDER_IDS

    # --- Internals ---------------------------------------------------------

    def _resolve_model(self, model: ProviderModel | None) -> str:
        if model is None:
            return self._default_model
        if not self.validate_binding(model):
            raise UnsupportedBindingError(
                f"ClaudeCodeRuntime cannot serve {model.label!r}; "
                f"provider must be one of {sorted(self.SUPPORTED_PROVIDER_IDS)}"
            )
        return model.model_id

    async def _ensure_client(
        self,
        *,
        schema: type[BaseModel],
        system: str | None,
        model: str,
    ) -> Any:
        key = f"{model}|{system or ''}|{schema.__name__}|{schema.model_json_schema()}"
        if self._client is not None and self._client_key == key:
            return self._client
        await self.reset()

        from claude_agent_sdk import (
            ClaudeAgentOptions,
            ClaudeSDKClient,
            create_sdk_mcp_server,
        )
        from claude_agent_sdk import tool as sdk_tool

        json_schema = schema.model_json_schema()

        @sdk_tool(
            SUBMIT_RESULT_TOOL,
            f"Submit the final typed payload as a {schema.__name__}. "
            f"Call this exactly once with all required fields filled in.",
            json_schema,
        )
        async def _submit(args: dict[str, Any]) -> dict[str, Any]:
            self._captured_args = dict(args)
            return {"content": [{"type": "text", "text": "accepted"}]}

        server = create_sdk_mcp_server(name="maverick_struct", tools=[_submit])
        forced_prefix = (
            "When you are ready to answer, call the "
            f"`{SUBMIT_RESULT_TOOL}` tool with the typed payload. "
            "Do not emit a final assistant message; the tool call is your answer.\n\n"
        )
        env_override: dict[str, str] = {}
        if self._api_key_override is not None:
            env_override["ANTHROPIC_API_KEY"] = self._api_key_override
        options = ClaudeAgentOptions(
            mcp_servers={"maverick_struct": server},
            allowed_tools=[SUBMIT_RESULT_MCP_NAME],
            system_prompt=forced_prefix + (system or ""),
            model=model,
            max_turns=self._max_turns,
            permission_mode="bypassPermissions",
            env=env_override or {},
        )
        try:
            client = ClaudeSDKClient(options=options)
            await client.connect()
        except Exception as exc:
            raise self._classify_exception(exc) from exc
        self._client = client
        self._client_key = key
        return client

    async def _query_and_drain(self, client: Any, prompt: str) -> Any:
        from claude_agent_sdk import ResultMessage

        await client.query(prompt)
        final: Any = None
        async for msg in client.receive_response():
            if isinstance(msg, ResultMessage):
                final = msg
        return final

    def _cost_from_result(self, result_msg: Any, *, model_id: str) -> CostRecord:
        usage = result_msg.usage or {}
        return CostRecord(
            provider_id="anthropic",
            model_id=model_id,
            cost_usd=result_msg.total_cost_usd,
            input_tokens=int(usage.get("input_tokens") or 0),
            output_tokens=int(usage.get("output_tokens") or 0),
            cache_read_tokens=int(usage.get("cache_read_input_tokens") or 0),
            cache_write_tokens=int(usage.get("cache_creation_input_tokens") or 0),
            finish=result_msg.stop_reason,
        )

    def _classify_exception(self, exc: BaseException) -> Exception:
        """Map Claude SDK exceptions onto Maverick's runtime hierarchy."""
        from claude_agent_sdk import (
            ClaudeSDKError,
            CLIConnectionError,
            CLIJSONDecodeError,
            CLINotFoundError,
        )

        if isinstance(exc, CLINotFoundError):
            return RuntimeServerStartError(f"claude_code: CLI not found: {exc}")
        if isinstance(exc, CLIConnectionError):
            return RuntimeTransientError(f"claude_code: connection lost: {exc}")
        if isinstance(exc, CLIJSONDecodeError):
            return RuntimeProtocolError(f"claude_code: bad JSON on stream: {exc}", body=None)
        if isinstance(exc, ClaudeSDKError):
            msg = str(exc).lower()
            if "auth" in msg or "credentials" in msg or "401" in msg:
                return RuntimeAuthError(f"claude_code: auth failure: {exc}")
            if "rate" in msg or "429" in msg or "503" in msg:
                return RuntimeTransientError(f"claude_code: transient: {exc}")
            return AgentRuntimeError(f"claude_code: {exc}")
        return AgentRuntimeError(f"claude_code: unexpected {type(exc).__name__}: {exc}")


__all__ = [
    "DEFAULT_CLAUDE_MODEL",
    "DEFAULT_MAX_TURNS",
    "ClaudeCodeRuntime",
]
