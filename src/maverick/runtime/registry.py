"""Per-actor-pool registry of airframe config + cost sink.

Mailbox actors look up pool-scoped state by ``self.address`` rather
than threading every dependency through the actor constructor. Two
registries live here, each indexed by the pool's external address:

* Agents config (airframe :class:`AgentsConfig`) — the workflow
  registers ``squadron.config.agents`` so the actor shells' fallback
  ``_make_agent`` paths can construct via :func:`runtime_for_agent`.
* Cost sinks — optional; when a workflow registers one (typically a
  :class:`RunwayStore`-backed appender), every successful agent send
  flushes a :class:`CostEntry` to it.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from maverick.config import AgentsConfig

__all__ = [
    "CostSink",
    "agents_config_for",
    "cost_sink_for",
    "register_agents_config",
    "register_cost_sink",
    "unregister_agents_config",
    "unregister_cost_sink",
]


# Async callable that accepts a :class:`runway.models.CostEntry`-shaped
# dataclass. Typed as ``Any`` here to avoid pulling runway into the
# runtime package — the agent imports CostEntry locally and the
# workflow registers an appender that closes over a RunwayStore.
CostSink = Callable[[Any], Awaitable[None]]


_agents_config_by_pool: dict[str, AgentsConfig] = {}
_cost_sink_by_pool: dict[str, CostSink] = {}


def agents_config_for(pool_address: str) -> AgentsConfig | None:
    """Return the airframe :class:`AgentsConfig` for ``pool_address``."""
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
    """Return the cost sink for ``pool_address`` or ``None`` when none set."""
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
