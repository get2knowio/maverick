"""``CodexRuntime`` — :class:`AgentRuntime` over the OpenAI Codex SDK.

Wraps :class:`openai_codex_sdk.Codex` to route OpenAI / GPT-family
work through the user's ChatGPT Plus subscription (or an
``OPENAI_API_KEY``) via the official ``openai-codex-sdk`` package.
The SDK spawns the ``codex`` CLI subprocess per turn; Maverick
doesn't allocate ports, juggle passwords, or maintain any client
code.

**Why this exists alongside CopilotRuntime.** Different auth path:
ChatGPT Plus subscription instead of GitHub Copilot. Useful as a
secondary binding when Copilot is rate-limited or the user only has
a ChatGPT Plus seat.

**Auth.** Three options, checked in order:

1. Explicit ``api_key=`` constructor argument — exported as
   ``CODEX_API_KEY`` for the subprocess.
2. ``OPENAI_API_KEY`` / ``CODEX_API_KEY`` env vars (the SDK
   inherits ``os.environ`` for the subprocess by default, so these
   "just work" if set).
3. ``~/.local/share/opencode/auth.json::openai.key`` — the API key
   minted by ``opencode auth login openai`` when the user already
   has opencode auth configured.
4. Implicit fallback: the ``codex`` CLI reads
   ``~/.codex/auth.json`` directly when present (created by
   ``codex login``). No work for us — the subprocess just uses it.

**Structured output.** First-class: the Codex CLI accepts an
``--output-schema`` flag that constrains the final response to a
JSON Schema. We pass ``schema.model_json_schema()`` via
:attr:`TurnOptions.outputSchema` and parse :attr:`Turn.final_response`
as JSON — no tool-forcing pattern needed.

**Lifecycle.** ``Codex()`` is lightweight (no subprocess yet).
``start_thread()`` returns a lightweight ``Thread`` object. Each
``thread.run()`` actually spawns the ``codex exec`` subprocess,
drains its JSONL event stream, and returns a typed ``Turn``. So
there's no persistent server to manage. ``reset()`` drops the
current thread (the next ``execute()`` starts a fresh one);
``aclose()`` is equivalent.

**Claude is not routed here.** Codex is OpenAI-only by design.
:meth:`validate_binding` rejects any ``model_id`` starting with
``claude-``.

**Cost.** ``Turn.usage`` exposes ``input_tokens``,
``output_tokens``, and ``cached_input_tokens``. The Codex CLI does
not return per-call ``cost_usd``; we look up a per-model rate from
a stub pricing map (real pricing migrates to
``runtime/pricing.py`` in a later phase). Models we haven't priced
report ``cost_usd=None``; tokens are always populated.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel

from maverick.logging import get_logger
from maverick.runtime.cost import CostRecord
from maverick.runtime.errors import (
    AgentRuntimeError,
    RuntimeAuthError,
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

#: Default Codex model when no binding is specified. ``gpt-5-codex``
#: is the v0 default — the standard codex model. Selected per-call
#: via ``ProviderModel.model_id``.
DEFAULT_CODEX_MODEL = "gpt-5-codex"

#: Path to the opencode auth file when present.
DEFAULT_AUTH_PATH = Path.home() / ".local" / "share" / "opencode" / "auth.json"

#: Provider IDs this runtime claims to serve. ``openai`` is the
#: canonical name; ``codex`` is an alias for users who configure
#: their tier as ``codex/gpt-5-codex``.
SUPPORTED_PROVIDER_IDS: frozenset[str] = frozenset({"openai", "codex"})

#: Stub pricing map — USD per 1K tokens (input, output). Real
#: per-(provider, model) pricing moves to
#: :mod:`maverick.runtime.pricing` in a later phase.
_PRICING: dict[str, tuple[float, float]] = {
    "gpt-5-codex": (0.0015, 0.0060),
    "gpt-5-codex-mini": (0.00025, 0.0010),
    "o5-codex": (0.0030, 0.0120),
}


def _resolve_api_key(api_key: str | None) -> str | None:
    """Resolve the OpenAI API key from explicit arg → env → opencode auth.json.

    Returns ``None`` when no API key is found in any of the explicit
    sources. That's a valid state: the codex CLI itself reads
    ``~/.codex/auth.json`` (populated by ``codex login``) when no env
    var is set. We only raise :class:`RuntimeAuthError` when the
    subprocess actually fails for auth reasons.
    """
    if api_key:
        return api_key
    env = os.environ.get("OPENAI_API_KEY") or os.environ.get("CODEX_API_KEY")
    if env:
        return env
    auth_path = Path(os.environ.get("OPENCODE_AUTH_PATH") or DEFAULT_AUTH_PATH)
    if auth_path.exists():
        try:
            data = json.loads(auth_path.read_text())
            key = (data.get("openai") or {}).get("key")
            if isinstance(key, str) and key:
                return key
        except (OSError, json.JSONDecodeError) as exc:
            logger.debug(
                "codex_runtime.auth_file_unreadable",
                path=str(auth_path),
                error=str(exc),
            )
    return None


def _compute_cost_usd(model_id: str, *, input_tokens: int, output_tokens: int) -> float | None:
    """Look up per-1K-token pricing and compute USD cost."""
    rates = _PRICING.get(model_id)
    if rates is None:
        return None
    in_rate, out_rate = rates
    return round((input_tokens / 1000.0) * in_rate + (output_tokens / 1000.0) * out_rate, 6)


class CodexRuntime(AgentRuntime):
    """One Codex SDK client per runtime instance.

    Args:
        model: Default Codex model identifier used when ``execute()``
            is called without a ``ProviderModel`` override. Honours
            ``CODEX_MODEL_OVERRIDE`` env var if set for testing.
        api_key: Optional explicit OpenAI API key. When ``None``
            (default), auth resolves via ``OPENAI_API_KEY`` /
            ``CODEX_API_KEY`` env vars → opencode auth.json → falls
            back to ``~/.codex/auth.json`` via the CLI subprocess.
        codex_path: Optional override for the ``codex`` CLI path.
        sandbox_mode: Sandbox mode passed to the codex CLI. Defaults
            to ``read-only`` — typed-output workflows shouldn't be
            writing files. Override to ``workspace-write`` for
            agents that need filesystem access.
        skip_git_repo_check: Skip the CLI's "are you in a git repo?"
            guard. ``True`` by default since Maverick agents
            operate against arbitrary working directories.
    """

    label = "codex"

    SUPPORTED_PROVIDER_IDS: ClassVar[frozenset[str]] = SUPPORTED_PROVIDER_IDS

    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | None = None,
        codex_path: str | None = None,
        sandbox_mode: str = "read-only",
        skip_git_repo_check: bool = True,
    ) -> None:
        self._default_model = (
            model or os.environ.get("CODEX_MODEL_OVERRIDE") or DEFAULT_CODEX_MODEL
        )
        self._api_key_override = api_key
        self._codex_path = codex_path or os.environ.get("CODEX_PATH")
        self._sandbox_mode = sandbox_mode
        self._skip_git_repo_check = skip_git_repo_check

        self._client: Any | None = None  # openai_codex_sdk.Codex
        self._thread: Any | None = None  # openai_codex_sdk.Thread
        self._thread_key: str | None = None

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
                "CodexRuntime: plain-text execute() is not wired in v0; "
                "every consumer currently expects a typed payload"
            )

        model_id = self._resolve_model(model)
        thread = await self._ensure_thread(model=model_id)

        # Codex prepends `system` content as the first user message —
        # there's no SDK-level system_message setting. Concatenate the
        # persona instructions onto the prompt.
        full_prompt = prompt if not system else f"{system}\n\n{prompt}"

        turn_options = {"outputSchema": schema.model_json_schema()}

        try:
            turn = await asyncio.wait_for(
                thread.run(full_prompt, turn_options),
                timeout=timeout,
            )
        except TimeoutError as exc:
            raise RuntimeTransientError(f"codex: execute timed out after {timeout}s") from exc
        except Exception as exc:
            raise self._classify_exception(exc) from exc

        final = turn.final_response or ""
        if not final:
            raise RuntimeStructuredOutputError(
                "codex: turn completed with empty final_response",
                body={"items_count": len(turn.items)},
            )

        try:
            structured = json.loads(final)
        except json.JSONDecodeError as exc:
            raise RuntimeStructuredOutputError(
                f"codex: final_response was not valid JSON: {exc}",
                body=final[:500],
            ) from exc

        return RuntimeResult(
            text=final,
            structured=structured,
            cost=self._cost_from_usage(turn.usage, model_id=model_id),
            finish="stop",
            raw=turn,
        )

    async def reset(self) -> None:
        """Drop the current thread; the next execute() starts a fresh one."""
        self._thread = None
        self._thread_key = None

    async def aclose(self) -> None:
        await self.reset()
        # Codex() holds no persistent resources — no subprocess pool,
        # no HTTP client. Dropping the reference is sufficient.
        self._client = None

    def validate_binding(self, binding: ProviderModel) -> bool:
        if binding.provider_id not in self.SUPPORTED_PROVIDER_IDS:
            return False
        # Codex is OpenAI-only. Anthropic bindings route through
        # ClaudeCodeRuntime / AnthropicRuntime.
        return not binding.model_id.startswith("claude-")

    # --- Internals ---------------------------------------------------------

    def _resolve_model(self, model: ProviderModel | None) -> str:
        if model is None:
            return self._default_model
        if not self.validate_binding(model):
            raise UnsupportedBindingError(
                f"CodexRuntime cannot serve {model.label!r}; "
                f"provider must be one of {sorted(self.SUPPORTED_PROVIDER_IDS)} "
                f"and the model_id must not start with 'claude-'"
            )
        return model.model_id

    async def _ensure_thread(self, *, model: str) -> Any:
        if self._thread is not None and self._thread_key == model:
            return self._thread
        client = self._ensure_client()
        thread_options = {
            "model": model,
            "sandboxMode": self._sandbox_mode,
            "skipGitRepoCheck": self._skip_git_repo_check,
        }
        try:
            thread = client.start_thread(thread_options)
        except Exception as exc:
            raise self._classify_exception(exc) from exc
        self._thread = thread
        self._thread_key = model
        return thread

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        from openai_codex_sdk import Codex

        options: dict[str, Any] = {}
        if self._codex_path is not None:
            options["codexPathOverride"] = self._codex_path
        api_key = _resolve_api_key(self._api_key_override)
        if api_key is not None:
            options["apiKey"] = api_key
        try:
            self._client = Codex(options)
        except Exception as exc:
            raise self._classify_exception(exc) from exc
        return self._client

    def _cost_from_usage(self, usage: Any, *, model_id: str) -> CostRecord:
        if usage is None:
            return CostRecord(
                provider_id="openai",
                model_id=model_id,
                cost_usd=None,
                input_tokens=0,
                output_tokens=0,
                cache_read_tokens=0,
                cache_write_tokens=0,
                finish="stop",
            )
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        cache_read = int(getattr(usage, "cached_input_tokens", 0) or 0)
        return CostRecord(
            provider_id="openai",
            model_id=model_id,
            cost_usd=_compute_cost_usd(
                model_id, input_tokens=input_tokens, output_tokens=output_tokens
            ),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read,
            cache_write_tokens=0,  # Codex SDK doesn't expose cache-write counts.
            finish="stop",
        )

    def _classify_exception(self, exc: BaseException) -> Exception:
        """Map Codex SDK exceptions onto Maverick's runtime hierarchy."""
        if isinstance(exc, UnsupportedBindingError):
            return exc

        from openai_codex_sdk.errors import (
            CodexAuthError,
            CodexExecError,
            CodexInstallError,
            CodexSdkError,
            EventParseError,
            ThreadRunError,
        )

        if isinstance(exc, CodexAuthError):
            return RuntimeAuthError(f"codex: auth: {exc}")
        if isinstance(exc, CodexInstallError):
            return RuntimeServerStartError(f"codex: install failure: {exc}")
        if isinstance(exc, FileNotFoundError):
            return RuntimeServerStartError(f"codex: CLI not found: {exc}")
        if isinstance(exc, EventParseError):
            return RuntimeStructuredOutputError(f"codex: malformed event stream: {exc}", body=None)
        if isinstance(exc, ThreadRunError):
            msg = str(exc).lower()
            if "auth" in msg or "401" in msg or "unauthorized" in msg or "credentials" in msg:
                return RuntimeAuthError(f"codex: auth: {exc}")
            if "rate" in msg or "429" in msg or "503" in msg or "timeout" in msg:
                return RuntimeTransientError(f"codex: transient: {exc}")
            if "schema" in msg or "json" in msg:
                return RuntimeStructuredOutputError(
                    f"codex: structured output failed: {exc}", body=None
                )
            return AgentRuntimeError(f"codex: thread run failed: {exc}")
        if isinstance(exc, CodexExecError):
            return RuntimeTransientError(f"codex: exec failure: {exc}")
        if isinstance(exc, CodexSdkError):
            return AgentRuntimeError(f"codex: sdk: {exc}")
        return AgentRuntimeError(f"codex: unexpected {type(exc).__name__}: {exc}")


__all__ = [
    "DEFAULT_CODEX_MODEL",
    "CodexRuntime",
]
