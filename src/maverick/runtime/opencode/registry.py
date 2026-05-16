"""Per-actor-pool registry of runtime config + cost sink.

Mirrors the legacy ``agent_tool_gateway_for`` lookup pattern so
mailbox actors can pull pool-scoped agents-config + cost sink by
``self.address`` rather than threading them through every constructor.
Four registries live here, each indexed by the pool's external address:

* OpenCode server handles — legacy; remaining for back-compat with
  unmigrated callers, deleted in Phase 7.
* Provider-tier overrides — legacy; same.
* Agents config (airframe ``AgentsConfig``) — current; the workflow
  registers ``squadron.config.agents`` so the actor shells' fallback
  ``_make_agent`` paths can construct via ``runtime_for_agent``.
* Cost sinks — optional; when a workflow registers one (typically a
  :class:`RunwayStore`-backed appender), every successful mailbox send
  flushes a :class:`CostEntry` to it.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from maverick.runtime.opencode.server import OpenCodeServerHandle
from maverick.runtime.opencode.tiers import Tier

if TYPE_CHECKING:
    from maverick.config import AgentsConfig

__all__ = [
    "CostSink",
    "agents_config_for",
    "cost_sink_for",
    "opencode_handle_for",
    "register_agents_config",
    "register_cost_sink",
    "register_opencode_handle",
    "register_tier_overrides",
    "tier_overrides_for",
    "unregister_agents_config",
    "unregister_cost_sink",
    "unregister_opencode_handle",
    "unregister_tier_overrides",
]


# Async callable that accepts a :class:`runway.models.CostEntry`-shaped
# dataclass. Typed as ``Any`` here to avoid pulling runway into the
# runtime package — the mixin imports CostEntry locally and the
# workflow registers an appender that closes over a RunwayStore.
CostSink = Callable[[Any], Awaitable[None]]


_handle_by_pool: dict[str, OpenCodeServerHandle] = {}
_tier_overrides_by_pool: dict[str, dict[str, Tier]] = {}
_agents_config_by_pool: dict[str, AgentsConfig] = {}
_cost_sink_by_pool: dict[str, CostSink] = {}


def opencode_handle_for(pool_address: str) -> OpenCodeServerHandle:
    """Return the handle bound to ``pool_address``.

    Raises:
        KeyError: when no handle is registered — typically means the actor
            was constructed outside an ``actor_pool(opencode_handle=...)``
            context, or the squadron's spawn failed.
    """
    try:
        return _handle_by_pool[pool_address]
    except KeyError as exc:
        raise KeyError(
            f"No OpenCode server registered for pool {pool_address!r}. "
            "Did the workflow forget to wrap actor_pool with a Squadron?"
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


def agents_config_for(pool_address: str) -> AgentsConfig | None:
    """Return the airframe ``AgentsConfig`` for ``pool_address``.

    The fallback ``_make_agent`` paths in mailbox actor shells call this
    when no ``agent=`` was injected by the supervisor: with the config
    in hand, the actor can call :func:`runtime_for_agent` to materialise
    an airframe runtime for its role.

    ``None`` means no config was registered — the actor's fallback
    should raise a clear error rather than silently constructing an
    untargeted agent.
    """
    return _agents_config_by_pool.get(pool_address)


def register_agents_config(pool_address: str, config: AgentsConfig | None) -> None:
    """Bind an :class:`AgentsConfig` to a pool address. ``None`` clears."""
    if config is None:
        _agents_config_by_pool.pop(pool_address, None)
        return
    _agents_config_by_pool[pool_address] = config


def unregister_agents_config(pool_address: str) -> None:
    """Remove the agents config for a pool address. No-op when missing."""
    _agents_config_by_pool.pop(pool_address, None)


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
