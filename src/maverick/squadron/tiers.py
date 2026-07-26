"""Shared per-complexity tier helpers for squadrons.

A *tier* maps a work item's ``complexity`` (assigned by the decomposer at
refuel time) to its own provider/model binding, so trivial work doesn't
pay frontier prices and complex work doesn't suffer weak models. Three
actors support tiering today — fly's implementer and reviewer, and
refuel's decomposer — and every one of them needs the same three
operations, so they live here rather than on any one squadron.

The user-facing surface is ``actors.<workflow>.<actor>.tiers.<complexity>``;
:func:`maverick.config.lookup_tiers_config` turns that block into a typed
tiers model, and the functions below turn that model into the arguments a
squadron needs to build agents.
"""

from __future__ import annotations

from typing import Any

from maverick.config import AgentBindingConfig

#: Ordered tier names, cheapest → most capable. Matches ``WorkUnitComplexity``
#: and the per-tier fields on every ``*TiersConfig`` model.
TIER_ORDER: tuple[str, ...] = ("trivial", "simple", "moderate", "complex")

#: Sentinel tier name for the single-agent fallback (no tiers configured).
#: Deliberately not a member of :data:`TIER_ORDER`: it means "the role's
#: base binding", which may sit anywhere on the capability scale.
DEFAULT_TIER: str = "_default"

__all__ = [
    "DEFAULT_TIER",
    "TIER_ORDER",
    "binding_for_complexity",
    "defined_tiers",
    "escalation_ladder",
    "merge_tier_config",
]


def merge_tier_config(base: Any, override: Any) -> Any:
    """Merge a per-tier override over a base ``StepConfig``.

    Each field set on the override replaces the base. Fields left as
    ``None`` on the override fall through to base. Returns a new
    ``StepConfig`` (``StepConfig`` is frozen, so this is a ``model_copy``).
    """
    if base is None:
        from maverick.executor.config import StepConfig

        return StepConfig(
            provider=override.provider,
            model_id=override.model_id,
            timeout=override.timeout,
            max_tokens=override.max_tokens,
            temperature=override.temperature,
        )
    updates: dict[str, Any] = {}
    for field_name in ("provider", "model_id", "timeout", "max_tokens", "temperature"):
        value = getattr(override, field_name, None)
        if value is not None:
            updates[field_name] = value
    if not updates:
        return base
    return base.model_copy(update=updates)


def binding_for_complexity(tier_name: str, override: Any) -> AgentBindingConfig | None:
    """Convert a per-complexity tier config to an agent-factory override.

    The tier config is a Maverick-only shape with extra fields (timeout /
    max_tokens / temperature) the airframe factory doesn't consume; only
    ``provider`` + ``model_id`` flow through, and only when *both* are
    set — a half-specified binding would silently pair one tier's
    provider with another's model.

    Returns ``None`` for the :data:`DEFAULT_TIER` sentinel (no complexity
    override) or when the override doesn't fully specify a binding, which
    the factory reads as "use the role's base binding".
    """
    if tier_name == DEFAULT_TIER or override is None:
        return None
    provider = getattr(override, "provider", None)
    model_id = getattr(override, "model_id", None)
    if not provider or not model_id:
        return None
    return AgentBindingConfig(provider=provider, model_id=model_id)


def defined_tiers(tiers_config: Any) -> tuple[str, ...]:
    """Tier names ``tiers_config`` actually defines, cheapest → most capable.

    Sparse configs are normal and supported: defining only ``moderate``
    and ``complex`` is a common shape. Returns ``()`` when the config is
    absent or defines no tiers.
    """
    if tiers_config is None:
        return ()
    return tuple(name for name in TIER_ORDER if getattr(tiers_config, name, None) is not None)


def escalation_ladder(tiers_config: Any, *, max_steps: int | None = None) -> tuple[str, ...]:
    """Build the ordered tier ladder a failed work item escalates along.

    The ladder always starts at :data:`DEFAULT_TIER` (the role's base
    binding, which is where unescalated work runs) and then climbs
    through the *defined* tiers in ascending capability order.

    Tiers are only worth escalating to if they resolve to a **different**
    binding, so a config with no tiers yields ``(DEFAULT_TIER,)`` — no
    escalation at all. That is the point: escalating to an identical
    binding is a retry wearing a costume, and it hid the fact that the
    binding never varied at all (#135).

    ``max_steps`` is deliberately an explicit argument rather than read
    off ``tiers_config.escalation_threshold``: that field means
    "escalation steps allowed" on :class:`DecomposerTiersConfig` but
    "fix rounds before promoting" on :class:`ImplementerTiersConfig`, and
    silently picking one reading for both would be wrong for one of them.

    Args:
        tiers_config: The typed tiers model, or ``None``.
        max_steps: Cap on escalation steps above the base binding.
            ``None`` means uncapped; ``0`` disables escalation.

    Returns:
        The ladder, always non-empty and always starting at
        :data:`DEFAULT_TIER`.
    """
    tiers = defined_tiers(tiers_config)
    if max_steps is not None:
        tiers = tiers[: max(0, max_steps)]
    return (DEFAULT_TIER, *tiers)
