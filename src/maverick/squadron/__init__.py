"""Per-workflow Squadron — owns the airframe-backed agent set.

A Squadron is the substrate-aware container for a single workflow run.
It builds one :class:`airframe.AgentRuntime` per agent role via
:func:`maverick.runtime.agent_factory.runtime_for_agent` (driven by
:class:`MaverickConfig.agents`), and exposes the typed agents the
workflow's actors need.

Workflows compose Squadron with the xoscar :func:`actor_pool`::

    async with FlySquadron(cwd=cwd, config=config, cost_sink=sink) as squadron:
        async with actor_pool(cost_sink=squadron.cost_sink) as (pool, address):
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
