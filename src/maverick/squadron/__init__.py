"""Per-workflow Squadron — owns OpenCode server + Agent factory/registry.

A Squadron is the substrate-aware container for a single workflow run.
It spawns one ``opencode serve`` subprocess, validates every binding it
will use at startup (collapsing the silent-bad-modelID landmine to one
place), and exposes the typed agents the workflow's actors need.

Workflows compose Squadron with the xoscar :func:`actor_pool` so the
pool's registry can hand actors back the same OpenCode handle / tier
overrides / cost sink::

    async with FlySquadron(cwd=cwd, config=config, cost_sink=sink) as squadron:
        async with actor_pool(
            opencode_handle=squadron.handle,
            provider_tiers=squadron.tier_overrides,
            cost_sink=squadron.cost_sink,
        ) as (pool, address):
            ...
"""

from __future__ import annotations

from maverick.squadron.base import Squadron
from maverick.squadron.decomposer_pool import DecomposerAgentPool
from maverick.squadron.fly import FlySquadron
from maverick.squadron.plan import PlanSquadron
from maverick.squadron.refuel import RefuelSquadron

__all__ = [
    "DecomposerAgentPool",
    "FlySquadron",
    "PlanSquadron",
    "RefuelSquadron",
    "Squadron",
]
