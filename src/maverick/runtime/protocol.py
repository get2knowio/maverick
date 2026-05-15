"""``Runtime`` protocol — vendor-agnostic agent transport.

Maverick agents talk to LLMs through a thin :class:`Runtime` protocol.
Implementations live under ``maverick.runtime.<vendor>_adapter`` and
wrap each vendor's preferred Python SDK (Claude Agent SDK, GitHub
Copilot Python SDK, OpenAI Codex SDK, OpenCode Zen HTTP, Anthropic
direct API, etc.). An agent receives a :class:`Runtime` at
construction and never sees a vendor-specific type at the call site.

Design principles:

1. **Runtime owns its lifecycle.** Subprocesses, HTTP pools, auth
   tokens, session state, retry logic — all hidden behind the
   protocol. The consumer interface is :meth:`execute`, :meth:`reset`,
   :meth:`aclose`.
2. **No opaque handles in the consumer interface.** The historical
   ``StepExecutor`` protocol from the pre-OpenCode ACP era worked
   this way; experience with the OpenCode HTTP runtime's
   ``session_id``-juggling proved we should go back to it.
3. **Scope is explicit, sessions are implicit.** A runtime MAY hold
   context warmth across consecutive :meth:`execute` calls so the
   provider's prompt cache hits accrue within a scope (typically one
   bead). :meth:`reset` drops that scope. Workflows call ``reset()``
   at bead boundaries — same semantics as the legacy
   ``Agent.rotate_session()``, just without the session id.
4. **Errors are vendor-agnostic.** Adapters classify failures into
   the :mod:`maverick.runtime.errors` hierarchy
   (``RuntimeAuthError``, ``RuntimeTransientError``,
   ``RuntimeStructuredOutputError``, etc.) so the cascade machinery
   in :mod:`maverick.runtime.tiers` doesn't need to know which
   adapter raised what.

See ``docs/migration-implementation-plan.md`` for the per-adapter
rollout plan.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel

from maverick.runtime.cost import CostRecord
from maverick.runtime.opencode.tiers import ProviderModel


@dataclass(frozen=True, slots=True)
class RuntimeResult:
    """Canonical execute() result.

    Mirrors the subset of the legacy ``OpenCode SendResult`` that
    ``Agent`` actually consumes, plus a normalised finish reason that
    every transport reports.

    Attributes:
        text: Concatenated assistant text (post any tool-call output).
            For structured-output calls this is typically empty or a
            short acknowledgement — the meaningful payload lives in
            :attr:`structured`.
        structured: Schema-shaped object — already envelope-unwrapped
            for OpenCode, already pulled from the forced-tool-call
            args for Claude Code / Codex / Copilot / Anthropic. ``None``
            when ``schema`` was ``None`` on the execute() call.
        cost: Cost telemetry for this call. Adapters with a vendor-
            computed cost populate ``cost_usd`` directly; others
            compute from token counts × pricing table.
        finish: Provider-reported stop reason
            (``"stop"`` / ``"length"`` / ``"tool_calls"`` /
            ``"end_turn"`` / ``None``).
        raw: The transport-specific result object — kept for
            diagnostics. Not part of the protocol contract; consumers
            should treat it as opaque.
    """

    text: str
    structured: Any
    cost: CostRecord
    finish: str | None
    raw: Any = field(default=None, repr=False)


@runtime_checkable
class Runtime(Protocol):
    """Vendor-agnostic agent runtime.

    Implementations:

    * :class:`maverick.runtime.claude_code_adapter.ClaudeCodeRuntime`
      — Claude family via ``claude-agent-sdk``; subscription auth.
    * :class:`maverick.runtime.copilot_adapter.CopilotRuntime` —
      Copilot via ``github-copilot-sdk``; GitHub Copilot subscription.
    * :class:`maverick.runtime.codex_adapter.CodexRuntime` — OpenAI
      codex via ``openai-codex-sdk``; ChatGPT Plus subscription.
    * :class:`maverick.runtime.opencode_zen_adapter.OpenCodeRuntime`
      — opencode-go Zen gateway via HTTP; opencode subscription.
    * :class:`maverick.runtime.anthropic_adapter.AnthropicRuntime`
      — pay-per-token Anthropic API direct (optional).

    All implementations satisfy the same protocol; agents are
    runtime-agnostic by construction.
    """

    label: str
    """Human-readable runtime tag used in structured-log rows
    (``runtime=claude_code``, ``runtime=copilot``, etc.)."""

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
        """Send one prompt, return a canonical typed result.

        Args:
            prompt: The user message.
            schema: When non-None, the runtime coerces the model's
                response into a schema-conforming dict on
                ``RuntimeResult.structured``. Implementations use the
                vendor's native structured-output mechanism (a forced
                tool call for Claude / Anthropic / Codex / Copilot,
                ``format=json_schema`` for OpenCode Zen). ``None``
                means plain text — text answer on
                ``RuntimeResult.text``, ``structured=None``.
            system: Optional system-prompt override. Adapters that
                bake the system prompt at scope-construction time
                (Claude Code SDK, etc.) may rebuild internal state
                when this changes between calls.
            persona: Optional runtime-specific agent persona label.
                OpenCode honours it (selects bundled ``maverick.*``
                agent files); other adapters typically ignore it.
            model: When non-None, pin this binding for this call.
                Implementations that can't serve the binding raise
                :class:`UnsupportedBindingError`. The cascade in
                :mod:`maverick.runtime.tiers` calls
                :meth:`validate_binding` first to avoid this.
            timeout: Hard wall-clock budget for the call.

        Returns:
            :class:`RuntimeResult` with text + (optional) structured
            payload + cost + finish reason.

        Raises:
            RuntimeAuthError, RuntimeModelNotFoundError,
            RuntimeStructuredOutputError, RuntimeContextOverflowError,
            RuntimeTransientError, RuntimeProtocolError,
            RuntimeServerStartError: classified failures from
            :mod:`maverick.runtime.errors`. The cascade decides what
            to do based on the exception type.
        """
        ...

    async def reset(self) -> None:
        """Drop accumulated context for a fresh scope.

        Called at scope boundaries (typically between beads).
        Implementations release scope-bound state — OpenCode's HTTP
        session is deleted; Claude Code SDK's subprocess is
        disconnected; Anthropic API has no session and this is a
        no-op. Cheap to call; never raises.

        Runtime-wide resources (subprocess pool, HTTP client, auth
        tokens) are kept across :meth:`reset`. Use :meth:`aclose`
        for full teardown.
        """
        ...

    async def aclose(self) -> None:
        """Release runtime-wide resources.

        Idempotent. Implementations must not raise — teardown errors
        should be logged at debug level and swallowed.
        """
        ...

    def validate_binding(self, binding: ProviderModel) -> bool:
        """Return True if this runtime can satisfy the binding.

        Implementations:

        * OpenCodeRuntime: ``True`` for any binding configured on the
          Zen gateway (OpenAI-compatible adapter — most things work).
        * ClaudeCodeRuntime / AnthropicRuntime: ``True`` only for
          ``provider_id`` in ``{"anthropic", "claude", "claude-code",
          "claude-sdk"}``.
        * CopilotRuntime: ``True`` for codex bindings; ``False`` for
          Claude bindings (the Copilot+Claude path is broken per
          Phase 0/0b findings — Claude bindings route through
          ClaudeCodeRuntime or AnthropicRuntime instead).
        * CodexRuntime: ``True`` for OpenAI codex bindings.

        Used by :func:`maverick.runtime.tiers.cascade_send` to
        short-circuit — bindings a runtime can't serve are skipped
        without attempting them.
        """
        ...


class UnsupportedBindingError(Exception):
    """Raised when a runtime is asked to serve a binding it can't serve.

    Distinct from :class:`maverick.runtime.errors.RuntimeError_` —
    this is a programming error (the caller should have checked
    :meth:`Runtime.validate_binding` first), not a runtime failure.
    """


__all__ = ["Runtime", "RuntimeResult", "UnsupportedBindingError"]
