"""Per-actor-pool registry of running OpenCode server handles + tier overrides.

Mirrors the legacy ``agent_tool_gateway_for`` lookup pattern so
:class:`OpenCodeAgentMixin` can pull pool-scoped runtime + config by
``self.address`` rather than threading them through every constructor.
Two registries live here:

* OpenCode server handles (per pool) — mandatory.
* Provider-tier overrides (per pool) — optional. When a workflow's
  ``actor_pool()`` context registers tier overrides, the mixin uses
  them; otherwise the runtime falls back to
  :data:`maverick.runtime.opencode.tiers.DEFAULT_TIERS`.
"""

from __future__ import annotations

from maverick.runtime.opencode.server import OpenCodeServerHandle
from maverick.runtime.opencode.tiers import Tier

__all__ = [
    "opencode_handle_for",
    "register_opencode_handle",
    "unregister_opencode_handle",
    "tier_overrides_for",
    "register_tier_overrides",
    "unregister_tier_overrides",
]


_handle_by_pool: dict[str, OpenCodeServerHandle] = {}
_tier_overrides_by_pool: dict[str, dict[str, Tier]] = {}


def opencode_handle_for(pool_address: str) -> OpenCodeServerHandle:
    """Return the handle bound to ``pool_address``.

    Raises:
        KeyError: when no handle is registered — typically means the actor
            was constructed outside an ``actor_pool(with_opencode=True)``
            context, or the spawn failed.
    """
    try:
        return _handle_by_pool[pool_address]
    except KeyError as exc:
        raise KeyError(
            f"No OpenCode server registered for pool {pool_address!r}. "
            "Was the actor created inside actor_pool(with_opencode=True)?"
        ) from exc


def register_opencode_handle(pool_address: str, handle: OpenCodeServerHandle) -> None:
    """Bind a server handle to a pool address. Overwrites any existing binding."""
    _handle_by_pool[pool_address] = handle


def unregister_opencode_handle(pool_address: str) -> None:
    """Remove the binding for a pool address. No-op when missing."""
    _handle_by_pool.pop(pool_address, None)


def tier_overrides_for(pool_address: str) -> dict[str, Tier] | None:
    """Return tier overrides for ``pool_address`` or ``None`` when none set.

    Distinct from :func:`opencode_handle_for` — tier overrides are
    optional. ``None`` means callers should fall back to
    :data:`DEFAULT_TIERS`.
    """
    return _tier_overrides_by_pool.get(pool_address)


def register_tier_overrides(pool_address: str, overrides: dict[str, Tier] | None) -> None:
    """Bind a tier-override map to a pool address. ``None`` clears."""
    if overrides is None or not overrides:
        _tier_overrides_by_pool.pop(pool_address, None)
        return
    _tier_overrides_by_pool[pool_address] = dict(overrides)


def unregister_tier_overrides(pool_address: str) -> None:
    """Remove tier overrides for a pool address. No-op when missing."""
    _tier_overrides_by_pool.pop(pool_address, None)
