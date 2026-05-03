"""Per-actor-pool registry of OpenCode runtime, tier overrides, and cost sink.

Mirrors the legacy ``agent_tool_gateway_for`` lookup pattern so
:class:`OpenCodeAgentMixin` can pull pool-scoped runtime + config by
``self.address`` rather than threading them through every constructor.
Three registries live here, each indexed by the pool's external address:

* OpenCode server handles — mandatory; spawned by ``actor_pool()``.
* Provider-tier overrides — optional; ``None`` means use ``DEFAULT_TIERS``.
* Cost sinks — optional; when a workflow registers one (typically a
  :class:`RunwayStore`-backed appender), every successful mailbox send
  flushes a :class:`CostEntry` to it.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from maverick.runtime.opencode.server import OpenCodeServerHandle
from maverick.runtime.opencode.tiers import Tier

__all__ = [
    "CostSink",
    "opencode_handle_for",
    "register_opencode_handle",
    "unregister_opencode_handle",
    "tier_overrides_for",
    "register_tier_overrides",
    "unregister_tier_overrides",
    "cost_sink_for",
    "register_cost_sink",
    "unregister_cost_sink",
]


# Async callable that accepts a :class:`runway.models.CostEntry`-shaped
# dataclass. Typed as ``Any`` here to avoid pulling runway into the
# runtime package — the mixin imports CostEntry locally and the
# workflow registers an appender that closes over a RunwayStore.
CostSink = Callable[[Any], Awaitable[None]]


_handle_by_pool: dict[str, OpenCodeServerHandle] = {}
_tier_overrides_by_pool: dict[str, dict[str, Tier]] = {}
_cost_sink_by_pool: dict[str, CostSink] = {}


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


def cost_sink_for(pool_address: str) -> CostSink | None:
    """Return the cost sink for ``pool_address`` or ``None`` when none set.

    Mailbox actors use this to forward each successful send's
    :class:`CostEntry` to the workflow's chosen aggregator (typically
    a :class:`RunwayStore`-backed appender).
    """
    return _cost_sink_by_pool.get(pool_address)


def register_cost_sink(pool_address: str, sink: CostSink | None) -> None:
    """Bind a cost sink to a pool address. ``None`` clears."""
    if sink is None:
        _cost_sink_by_pool.pop(pool_address, None)
        return
    _cost_sink_by_pool[pool_address] = sink


def unregister_cost_sink(pool_address: str) -> None:
    """Remove the cost sink for a pool address. No-op when missing."""
    _cost_sink_by_pool.pop(pool_address, None)
