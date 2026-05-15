"""``OpenCodeZenRuntime`` — :class:`AgentRuntime` for the opencode-go Zen gateway.

Wraps the official ``openai`` Python SDK pointed at
``https://opencode.ai/zen/v1`` — the OpenAI-compatible HTTP endpoint
that fronts the user's opencode-go subscription. Unlike the legacy
``runtime/opencode/`` package this adapter doesn't spawn a local
server — it's a direct HTTP call.

**Auth.** The API key resolves in this order:

1. Explicit ``api_key=`` constructor argument.
2. ``OPENCODE_API_KEY`` env var.
3. ``~/.local/share/opencode/auth.json::opencode-go.key`` — the key
   minted by ``opencode auth login opencode-go``.

If none is available, construction raises :class:`RuntimeAuthError`
on the first ``execute()`` call.

**Structured output.** Uses OpenAI's Chat Completions
``response_format={type: "json_schema", json_schema: {...}}``. We pass
``strict=False`` because some Zen-routed models don't satisfy strict
mode's "every field required, no defaults" rule and we'd rather have
our Pydantic validator catch the gap than have the request rejected
upstream.

**Cost telemetry.** Token counts come from ``response.usage``
(``prompt_tokens``, ``completion_tokens``, plus
``prompt_tokens_details.cached_tokens`` when the provider supports
prompt caching). ``cost_usd`` is computed from a per-model pricing
map (a stub in this module for v0 — pricing migrates to
``runtime/pricing.py`` in a later phase). Models we haven't priced
yet report ``cost_usd=None`` — the structured-log row still fires
with token counts intact.

**Lifecycle.** Stateless HTTP. ``reset()`` is a no-op (no session
state to drop). ``aclose()`` closes the underlying ``AsyncOpenAI``
client's HTTP pool.
"""

from __future__ import annotations

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
    RuntimeModelNotFoundError,
    RuntimeProtocolError,
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


#: Default Zen gateway base URL. Override via ``OPENCODE_ZEN_BASE_URL``.
DEFAULT_ZEN_BASE_URL = "https://opencode.ai/zen/v1"

#: Default model when no binding is specified.
DEFAULT_ZEN_MODEL = "gpt-5-nano"

#: Path to the opencode auth file when present.
DEFAULT_AUTH_PATH = Path.home() / ".local" / "share" / "opencode" / "auth.json"

#: Provider IDs this runtime claims to serve. Maverick's existing tier
#: config uses both ``opencode`` (Zen-curated models like gpt-5-nano,
#: big-pickle) and ``opencode-go`` (the same gateway via the user's
#: subscription key). Both route here.
SUPPORTED_PROVIDER_IDS: frozenset[str] = frozenset({"opencode", "opencode-go", "opencode-zen"})

#: Stub pricing map — USD per 1K tokens (input, output). Models we
#: don't know about return ``cost_usd=None`` rather than guessing.
#: A real per-(provider, model) table moves to
#: :mod:`maverick.runtime.pricing` in a later phase.
_PRICING: dict[str, tuple[float, float]] = {
    # Zen "free" tier
    "minimax-m2.5-free": (0.0, 0.0),
    "deepseek-v4-flash-free": (0.0, 0.0),
    "qwen3.6-plus-free": (0.0, 0.0),
    "nemotron-3-super-free": (0.0, 0.0),
    # Zen paid tier — placeholder rates pending real pricing table.
    "gpt-5-nano": (0.0001, 0.0002),
    "gpt-5-mini": (0.0003, 0.0006),
    "big-pickle": (0.0005, 0.0015),
    "glm-5": (0.0002, 0.0004),
    "qwen3.6-plus": (0.0003, 0.0009),
}


def _resolve_api_key(api_key: str | None) -> str:
    """Resolve the Zen API key from explicit arg → env → auth.json."""
    if api_key:
        return api_key
    env = os.environ.get("OPENCODE_API_KEY")
    if env:
        return env
    auth_path = Path(os.environ.get("OPENCODE_AUTH_PATH") or DEFAULT_AUTH_PATH)
    if auth_path.exists():
        try:
            data = json.loads(auth_path.read_text())
            key = (data.get("opencode-go") or {}).get("key")
            if isinstance(key, str) and key:
                return key
        except (OSError, json.JSONDecodeError) as exc:
            logger.debug(
                "opencode_zen_runtime.auth_file_unreadable",
                path=str(auth_path),
                error=str(exc),
            )
    raise RuntimeAuthError(
        "OpenCodeZenRuntime: no API key found. Set OPENCODE_API_KEY, "
        "pass api_key= explicitly, or run `opencode auth login opencode-go`."
    )


def _compute_cost_usd(model_id: str, *, input_tokens: int, output_tokens: int) -> float | None:
    """Look up per-1K-token pricing and compute USD cost."""
    rates = _PRICING.get(model_id)
    if rates is None:
        return None
    in_rate, out_rate = rates
    return round((input_tokens / 1000.0) * in_rate + (output_tokens / 1000.0) * out_rate, 6)


class OpenCodeZenRuntime(AgentRuntime):
    """One :class:`AsyncOpenAI` client per runtime instance, pointed at Zen.

    Args:
        model: Default model identifier used when ``execute()`` is
            called without a ``ProviderModel`` override.
        base_url: Zen gateway base URL. Override via
            ``OPENCODE_ZEN_BASE_URL`` env var.
        api_key: Explicit Zen API key. When ``None``, falls back to
            ``OPENCODE_API_KEY`` env var, then to the opencode auth.json.
        timeout: Default per-call timeout in seconds.
    """

    label = "opencode_zen"

    SUPPORTED_PROVIDER_IDS: ClassVar[frozenset[str]] = SUPPORTED_PROVIDER_IDS

    def __init__(
        self,
        *,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 600.0,
    ) -> None:
        self._default_model = (
            model or os.environ.get("OPENCODE_ZEN_DEFAULT_MODEL") or DEFAULT_ZEN_MODEL
        )
        self._base_url = (
            base_url or os.environ.get("OPENCODE_ZEN_BASE_URL") or DEFAULT_ZEN_BASE_URL
        )
        self._api_key_override = api_key
        self._timeout = timeout
        self._client: Any | None = None  # AsyncOpenAI; lazy

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
        model_id = self._resolve_model(model)
        client = self._ensure_client()

        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response_format: dict[str, Any] | None = None
        if schema is not None:
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    "strict": False,
                    "schema": schema.model_json_schema(),
                },
            }

        try:
            response = await client.chat.completions.create(
                model=model_id,
                messages=messages,
                response_format=response_format,
                timeout=timeout,
            )
        except Exception as exc:
            raise self._classify_exception(exc) from exc

        return self._build_result(response, model_id=model_id, schema=schema)

    async def reset(self) -> None:
        """No-op: Zen calls are stateless HTTP."""
        return None

    async def aclose(self) -> None:
        client = self._client
        self._client = None
        if client is None:
            return
        try:
            await client.close()
        except Exception as exc:  # noqa: BLE001 — teardown never raises
            logger.debug("opencode_zen_runtime.close_failed", error=str(exc))

    def validate_binding(self, binding: ProviderModel) -> bool:
        return binding.provider_id in self.SUPPORTED_PROVIDER_IDS

    # --- Internals ---------------------------------------------------------

    def _resolve_model(self, model: ProviderModel | None) -> str:
        if model is None:
            return self._default_model
        if not self.validate_binding(model):
            raise UnsupportedBindingError(
                f"OpenCodeZenRuntime cannot serve {model.label!r}; "
                f"provider must be one of {sorted(self.SUPPORTED_PROVIDER_IDS)}"
            )
        return model.model_id

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        from openai import AsyncOpenAI

        api_key = _resolve_api_key(self._api_key_override)
        self._client = AsyncOpenAI(base_url=self._base_url, api_key=api_key, timeout=self._timeout)
        return self._client

    def _build_result(
        self,
        response: Any,
        *,
        model_id: str,
        schema: type[BaseModel] | None,
    ) -> RuntimeResult:
        if not response.choices:
            raise RuntimeProtocolError(
                "opencode_zen: response had no choices",
                body=str(response)[:500],
            )
        choice = response.choices[0]
        message = choice.message
        text = message.content or ""
        finish = choice.finish_reason

        structured: Any = None
        if schema is not None:
            structured = self._parse_structured(text, schema=schema)

        usage = response.usage
        input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        details = getattr(usage, "prompt_tokens_details", None)
        cache_read = int(getattr(details, "cached_tokens", 0) or 0) if details else 0

        cost = CostRecord(
            provider_id="opencode",
            model_id=model_id,
            cost_usd=_compute_cost_usd(
                model_id, input_tokens=input_tokens, output_tokens=output_tokens
            ),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read,
            cache_write_tokens=0,  # OpenAI Chat Completions doesn't expose write counts.
            finish=finish,
        )

        return RuntimeResult(
            text=text,
            structured=structured,
            cost=cost,
            finish=finish,
            raw=response,
        )

    def _parse_structured(self, text: str, *, schema: type[BaseModel]) -> dict[str, Any]:
        """Parse JSON content with light envelope-unwrapping.

        Most Zen models honour ``response_format`` cleanly. A few
        wrap the payload in a single ``{"input": ...}`` / ``{"content":
        ...}`` envelope (same quirk OpenCode's StructuredOutput tool
        hit on Claude). We unwrap one level when we see that shape;
        otherwise the validator catches it.
        """
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeStructuredOutputError(
                f"opencode_zen: structured payload was not valid JSON: {exc}",
                body=text[:500],
            ) from exc
        return _unwrap_envelope(data)

    def _classify_exception(self, exc: BaseException) -> Exception:
        """Map openai SDK exceptions onto Maverick's runtime hierarchy."""
        from openai import (
            APIConnectionError,
            APIStatusError,
            APITimeoutError,
            AuthenticationError,
            BadRequestError,
            NotFoundError,
            PermissionDeniedError,
            RateLimitError,
        )

        if isinstance(exc, AuthenticationError | PermissionDeniedError):
            return RuntimeAuthError(f"opencode_zen: auth: {exc}")
        if isinstance(exc, NotFoundError):
            return RuntimeModelNotFoundError(f"opencode_zen: model not found: {exc}")
        if isinstance(exc, BadRequestError):
            # Many "your schema is bad" / "your input is bad" errors land
            # here; classify as structured-output so the cascade falls over.
            return RuntimeStructuredOutputError(
                f"opencode_zen: bad request: {exc}",
                body=getattr(exc, "body", None),
            )
        if isinstance(exc, RateLimitError | APITimeoutError | APIConnectionError):
            return RuntimeTransientError(f"opencode_zen: transient: {exc}")
        if isinstance(exc, APIStatusError):
            status = getattr(exc, "status_code", None)
            if status is not None and 500 <= status < 600:
                return RuntimeTransientError(f"opencode_zen: 5xx: {exc}")
            return AgentRuntimeError(f"opencode_zen: api error: {exc}")
        return AgentRuntimeError(f"opencode_zen: unexpected {type(exc).__name__}: {exc}")


_ENVELOPE_KEYS = frozenset(
    {
        "input",
        "output",
        "parameter",
        "parameters",
        "arguments",
        "content",
        "data",
        "result",
        "value",
    }
)


def _unwrap_envelope(payload: Any) -> Any:
    """Strip a single-key wrapper around the typed payload.

    Some Zen-routed models emit ``{"input": {...}}`` or
    ``{"content": "<json-string>"}`` instead of the bare payload.
    We unwrap one level when we see that exact shape — if the wrapper's
    value is a JSON string, decode it.
    """
    if not isinstance(payload, dict):
        return payload
    if len(payload) == 1:
        ((k, v),) = payload.items()
        if k in _ENVELOPE_KEYS:
            if isinstance(v, str):
                try:
                    parsed = json.loads(v)
                    return _unwrap_envelope(parsed)
                except json.JSONDecodeError:
                    return payload
            return _unwrap_envelope(v)
    return payload


__all__ = [
    "DEFAULT_ZEN_BASE_URL",
    "DEFAULT_ZEN_MODEL",
    "OpenCodeZenRuntime",
]
