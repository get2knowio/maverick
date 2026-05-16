"""Tier resolution — Maverick's per-role cascade policy.

A "tier" is an ordered list of ``(provider_id, model_id)`` bindings an
agent role tries in turn. Tiers are role-named (``"review"``,
``"implement"``, ``"briefing"``, ``"decompose"``, ``"generate"``) so
the agent declaration stays stable while users tune the underlying
model lists per role via ``maverick.yaml::provider_tiers``.

The :class:`ProviderModel` binding type is re-exported from
:mod:`airframe.protocol` — airframe owns the vendor-neutral primitive.
This module owns the *policy* (cascade ordering, role-name defaults,
config-shape parsing) — Maverick-specific decisions that don't belong
in the runtime library.

The cascade machinery that actually walks the bindings (and the
per-runtime error classification it depends on) still lives in
:mod:`maverick.runtime.opencode.tiers` for now and migrates to a
vendor-neutral home in Phase 6 of the Pattern D migration.

See ``docs/migration-implementation-plan.md``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from airframe.protocol import ProviderModel

__all__ = [
    "DEFAULT_TIERS",
    "ProviderModel",
    "Tier",
    "resolve_tier",
    "tiers_from_config",
]


@dataclass(frozen=True, slots=True)
class Tier:
    """Ordered cascade of bindings for a single agent role."""

    name: str
    bindings: tuple[ProviderModel, ...]

    def __post_init__(self) -> None:
        if not self.bindings:
            raise ValueError(f"Tier {self.name!r} must have at least one binding")


def _pm(provider: str, model: str) -> ProviderModel:
    return ProviderModel(provider_id=provider, model_id=model)


#: Default tier cascades distribute load across the user's flat-rate
#: subscriptions (github-copilot, openai/Codex, opencode/Zen) and a
#: free fallback (openrouter). Ordering is empirical: each role's
#: front-of-line binding is the one that historically returned the best
#: typed payload reliability for that role's payload shape. The cascade
#: silently falls over to the next binding when the front-of-line one
#: hits an auth / model-not-found / structured-output / sustained
#: transient failure.
DEFAULT_TIERS: dict[str, Tier] = {
    "review": Tier(
        "review",
        bindings=(
            _pm("github-copilot", "claude-haiku-4.5"),
            _pm("openai", "gpt-5.4-mini"),
            _pm("opencode", "big-pickle"),
            _pm("openrouter", "openai/gpt-oss-120b:free"),
        ),
    ),
    "implement": Tier(
        "implement",
        bindings=(
            _pm("github-copilot", "gpt-5.3-codex"),
            _pm("openai", "gpt-5.3-codex"),
            _pm("opencode", "qwen3.6-plus"),
            _pm("openrouter", "qwen/qwen-2.5-coder-32b-instruct"),
        ),
    ),
    "briefing": Tier(
        "briefing",
        bindings=(
            _pm("github-copilot", "gpt-5-mini"),
            _pm("openai", "gpt-5.4-mini-fast"),
            _pm("opencode", "gpt-5-nano"),
            _pm("openrouter", "openai/gpt-oss-120b:free"),
        ),
    ),
    "decompose": Tier(
        "decompose",
        bindings=(
            _pm("github-copilot", "claude-sonnet-4.6"),
            _pm("openai", "gpt-5.5"),
            _pm("opencode", "glm-5"),
            _pm("openrouter", "nvidia/nemotron-3-super-120b-a12b:free"),
        ),
    ),
    "generate": Tier(
        "generate",
        bindings=(
            _pm("github-copilot", "claude-sonnet-4.6"),
            _pm("openai", "gpt-5.5"),
            _pm("github-copilot", "gemini-3.1-pro-preview"),
            _pm("openrouter", "meta-llama/llama-3.3-70b-instruct:free"),
        ),
    ),
}


def tiers_from_config(config: Any) -> dict[str, Tier]:
    """Convert a :class:`MaverickConfig.provider_tiers` block into a runtime map.

    Returns an empty dict when no overrides are configured.
    """
    block = getattr(config, "provider_tiers", None)
    if block is None:
        return {}
    raw = getattr(block, "tiers", None)
    if not raw:
        return {}
    out: dict[str, Tier] = {}
    for tier_name, entries in raw.items():
        if not entries:
            continue
        bindings = tuple(
            ProviderModel(provider_id=entry.provider, model_id=entry.model_id) for entry in entries
        )
        if bindings:
            out[tier_name] = Tier(name=tier_name, bindings=bindings)
    return out


def resolve_tier(name: str, *, override: dict[str, Tier] | None = None) -> Tier:
    """Return the configured tier for ``name``.

    Args:
        name: Role tier name as declared on an agent's
            ``provider_tier`` class attribute (e.g. ``"review"``).
        override: Optional per-call override map (typically built from
            user config). Falls back to :data:`DEFAULT_TIERS` when the
            override is ``None`` or doesn't include ``name``.

    Raises:
        KeyError: When ``name`` matches no entry in either map.
    """
    if override and name in override:
        return override[name]
    if name in DEFAULT_TIERS:
        return DEFAULT_TIERS[name]
    raise KeyError(
        f"Unknown provider tier: {name!r}. "
        f"Define it in maverick.yaml::provider_tiers or pick from "
        f"{sorted(DEFAULT_TIERS.keys())}."
    )
