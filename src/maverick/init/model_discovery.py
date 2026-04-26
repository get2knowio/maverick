"""Model discovery and parsing for maverick init.

Probes ACP providers for available models and parses user-provided
model specs (provider:model1,model2 format).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from maverick.logging import get_logger

logger = get_logger(__name__)

#: Default models when probing fails or provider doesn't support it.
#:
#: ``opencode`` is intentionally an empty list: ``opencode acp`` doesn't
#: document model selection over ACP — model choice comes from the
#: user's OpenCode config — so we have nothing to advertise here. Users
#: who want named models for opencode can list them explicitly via
#: ``--models opencode:<id1>,<id2>`` at init time.
DEFAULT_MODELS: dict[str, list[str]] = {
    "claude": ["sonnet", "opus", "haiku"],
    "copilot": [
        "claude-sonnet-4-6",
        "gpt-5.3-codex",
        "gpt-5.4",
        "gpt-5-mini",
        "gpt-4.1",
    ],
    "gemini": ["gemini-3.1-pro-preview"],
    "opencode": [],
}


@dataclass
class ProviderModels:
    """Discovered or specified models for a provider."""

    provider: str
    models: list[str] = field(default_factory=list)
    default_model: str | None = None
    source: str = "default"  # "probe", "user", "default"

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "models": self.models,
            "default_model": self.default_model,
            "source": self.source,
        }


def parse_model_specs(
    model_specs: tuple[str, ...] | list[str],
) -> dict[str, list[str]]:
    """Parse provider:model1,model2 specs into a dict.

    Args:
        model_specs: Tuple of specs like ("copilot:gpt-5.3-codex,gpt-5.4",
                     "claude:sonnet,opus")

    Returns:
        Dict of provider → list of model IDs.

    Raises:
        ValueError: If a spec doesn't contain ':' separator.
    """
    result: dict[str, list[str]] = {}

    for spec in model_specs:
        if ":" not in spec:
            raise ValueError(
                f"Invalid model spec '{spec}': must be provider:model1,model2 "
                f"(e.g., copilot:gpt-5.3-codex,gpt-5.4)"
            )

        provider, models_str = spec.split(":", 1)
        provider = provider.strip().lower()
        models = [m.strip() for m in models_str.split(",") if m.strip()]

        if provider in result:
            result[provider].extend(models)
        else:
            result[provider] = models

    return result


async def probe_provider_models(
    provider: str,
) -> ProviderModels:
    """Probe a provider for available models via ACP.

    Fast-path for Claude (ACP probe works). Falls back to defaults
    for Copilot/Gemini where ACP probing is unreliable.

    Args:
        provider: Provider name (claude, copilot, gemini, opencode).

    Returns:
        ProviderModels with discovered or default models.
    """
    if provider == "claude":
        return await _probe_claude_models()
    else:
        # Copilot/Gemini: ACP probe is unreliable, use defaults
        defaults = DEFAULT_MODELS.get(provider, [])
        return ProviderModels(
            provider=provider,
            models=list(defaults),
            default_model=defaults[0] if defaults else None,
            source="default",
        )


async def _probe_claude_models() -> ProviderModels:
    """Probe Claude for available models via ACP session."""
    try:
        from maverick.executor import create_default_executor
        from maverick.executor._model_resolver import get_available_model_ids

        executor = create_default_executor()
        await executor.create_session(
            provider="claude",
            step_name="model_probe",
            agent_name="probe",
        )

        # Read models from cached connection
        cached = executor._pool.cache.get("claude")
        if cached:
            # Re-create session to get fresh model list
            session = await cached.conn.new_session(cwd=".", mcp_servers=[])
            get_available_model_ids(session)

            # Get display names
            models_info = []
            models_state = getattr(session, "models", None)
            if models_state:
                for m in getattr(models_state, "available_models", []):
                    mid = getattr(m, "model_id", None)
                    if mid:
                        models_info.append(mid)

            await executor.cleanup()

            if models_info:
                return ProviderModels(
                    provider="claude",
                    models=models_info,
                    default_model=models_info[0],
                    source="probe",
                )

        await executor.cleanup()

    except Exception as exc:
        logger.debug("model_probe.claude_failed", error=str(exc))

    # Fallback to defaults
    defaults = DEFAULT_MODELS["claude"]
    return ProviderModels(
        provider="claude",
        models=list(defaults),
        default_model=defaults[0],
        source="default",
    )


async def discover_all_models(
    providers: list[str],
    user_specs: dict[str, list[str]] | None = None,
) -> dict[str, ProviderModels]:
    """Discover models for all providers.

    User specs override probing. Probing is attempted for Claude.
    Defaults used for Copilot/Gemini.

    Args:
        providers: List of provider names.
        user_specs: Optional user-provided model specs (from --models).

    Returns:
        Dict of provider → ProviderModels.
    """
    result: dict[str, ProviderModels] = {}

    for provider in providers:
        provider = provider.strip().lower()

        if user_specs and provider in user_specs:
            # User provided explicit models
            models = user_specs[provider]
            result[provider] = ProviderModels(
                provider=provider,
                models=models,
                default_model=models[0] if models else None,
                source="user",
            )
        else:
            # Probe or use defaults
            result[provider] = await probe_provider_models(provider)

    return result
