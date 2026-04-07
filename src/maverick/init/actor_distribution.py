"""Distribute discovered models across actors by capability.

Maps actor roles to capability requirements, then assigns the best
available model from discovered providers. Prefers native provider
models (e.g., Claude models via Claude provider) over cross-provider
routing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from maverick.logging import get_logger

logger = get_logger(__name__)

# -------------------------------------------------------------------------
# Capability taxonomy
# -------------------------------------------------------------------------

#: What each actor needs from its model
ACTOR_CAPABILITIES: dict[str, dict[str, str]] = {
    # Plan workflow
    "plan": {
        "scopist": "analysis",
        "codebase_analyst": "analysis",
        "criteria_writer": "reasoning",
        "contrarian": "reasoning",
        "generator": "reasoning",
    },
    # Refuel workflow
    "refuel": {
        "decomposer": "reasoning",
    },
    # Fly workflow
    "fly": {
        "implementer": "code",
        "reviewer": "reasoning",
    },
    # Land workflow
    "land": {
        "curator": "utility",
    },
}

#: Default timeouts per actor (seconds)
ACTOR_TIMEOUTS: dict[str, int] = {
    "implementer": 1800,
    "decomposer": 1800,
    "reviewer": 600,
    "generator": 1200,
    "scopist": 600,
    "codebase_analyst": 600,
    "criteria_writer": 600,
    "contrarian": 600,
    "curator": 300,
}

#: What capability each model provides
MODEL_CAPABILITIES: dict[str, str] = {
    # Claude models
    "sonnet": "reasoning",
    "opus": "reasoning",
    "haiku": "utility",
    "default": "reasoning",
    "claude-sonnet-4-6": "reasoning",
    "claude-opus-4-6": "reasoning",
    "claude-haiku-4-5-20251001": "utility",
    # Copilot/OpenAI models
    "gpt-5.3-codex": "code",
    "gpt-5.2-codex": "code",
    "gpt-5.4": "analysis",
    "gpt-5.2": "analysis",
    "gpt-5.1": "analysis",
    "gpt-5.4-mini": "utility",
    "gpt-5-mini": "utility",
    "gpt-4.1": "utility",
    # Gemini models
    "gemini-3.1-pro-preview": "analysis",
}

#: Capability preference order (best fit first)
CAPABILITY_FALLBACK: dict[str, list[str]] = {
    "code": ["code", "reasoning", "analysis", "utility"],
    "reasoning": ["reasoning", "analysis", "code", "utility"],
    "analysis": ["analysis", "reasoning", "utility", "code"],
    "utility": ["utility", "analysis", "reasoning", "code"],
}

#: Which provider "owns" which model prefix (for native-provider preference)
NATIVE_PROVIDERS: dict[str, str] = {
    "sonnet": "claude",
    "opus": "claude",
    "haiku": "claude",
    "default": "claude",
    "claude-": "claude",
    "gpt-": "copilot",
    "gemini-": "gemini",
}


@dataclass
class ActorConfig:
    """Resolved configuration for a single actor."""

    provider: str
    model_id: str
    timeout: int | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "provider": self.provider,
            "model_id": self.model_id,
        }
        if self.timeout:
            d["timeout"] = self.timeout
        return d


def _get_model_capability(model_id: str) -> str:
    """Determine a model's capability category."""
    if model_id in MODEL_CAPABILITIES:
        return MODEL_CAPABILITIES[model_id]
    # Check prefix matches
    for prefix, cap in MODEL_CAPABILITIES.items():
        if model_id.startswith(prefix):
            return cap
    return "reasoning"  # default assumption


def _get_native_provider(model_id: str) -> str | None:
    """Determine which provider natively owns a model."""
    if model_id in NATIVE_PROVIDERS:
        return NATIVE_PROVIDERS[model_id]
    for prefix, provider in NATIVE_PROVIDERS.items():
        if model_id.startswith(prefix):
            return provider
    return None


def distribute_models(
    providers: dict[str, Any],
    default_provider: str | None = None,
) -> dict[str, dict[str, ActorConfig]]:
    """Distribute discovered models across actors by capability.

    Args:
        providers: Dict of provider_name → ProviderModels (or dict with
            'models' and 'provider' keys).
        default_provider: Fallback provider when no model matches.

    Returns:
        Nested dict: workflow → actor_name → ActorConfig.
    """
    # Build available model pool: list of (provider, model_id, capability)
    pool: list[tuple[str, str, str]] = []
    for prov_name, prov_data in providers.items():
        models = (
            prov_data.models
            if hasattr(prov_data, "models")
            else prov_data.get("models", [])
        )
        for model_id in models:
            cap = _get_model_capability(model_id)
            pool.append((prov_name, model_id, cap))

    if not default_provider:
        default_provider = next(iter(providers), "claude")

    result: dict[str, dict[str, ActorConfig]] = {}

    for workflow, actors in ACTOR_CAPABILITIES.items():
        result[workflow] = {}

        for actor_name, needed_cap in actors.items():
            config = _find_best_model(
                pool, needed_cap, default_provider
            )
            # Add timeout if actor has one
            timeout = ACTOR_TIMEOUTS.get(actor_name)
            if timeout:
                config.timeout = timeout

            result[workflow][actor_name] = config

    return result


def _find_best_model(
    pool: list[tuple[str, str, str]],
    needed_capability: str,
    default_provider: str,
) -> ActorConfig:
    """Find the best model for a capability requirement.

    Preference order:
    1. Native-provider model matching exact capability
    2. Any model matching exact capability
    3. Models matching fallback capabilities
    4. Default provider's first model
    """
    fallback_caps = CAPABILITY_FALLBACK.get(
        needed_capability, [needed_capability]
    )

    for cap in fallback_caps:
        # Pass 1: native-provider models
        for prov, model_id, model_cap in pool:
            if model_cap == cap:
                native = _get_native_provider(model_id)
                if native == prov:
                    return ActorConfig(provider=prov, model_id=model_id)

        # Pass 2: any provider
        for prov, model_id, model_cap in pool:
            if model_cap == cap:
                return ActorConfig(provider=prov, model_id=model_id)

    # Fallback: default provider's first model
    for prov, model_id, _ in pool:
        if prov == default_provider:
            return ActorConfig(provider=prov, model_id=model_id)

    # Last resort
    if pool:
        return ActorConfig(provider=pool[0][0], model_id=pool[0][1])

    return ActorConfig(provider=default_provider, model_id="default")
