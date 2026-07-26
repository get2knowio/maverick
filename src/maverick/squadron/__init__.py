"""Per-workflow Squadron — owns the airframe-backed agent set.

A Squadron is the substrate-aware container for a single workflow run.
It builds one :class:`airframe.AgentRuntime` per agent role via
:func:`maverick.runtime.agent_factory.runtime_for_agent` (driven by
:class:`MaverickConfig.agents`), and exposes the typed agents the
workflow's Burr graph needs.

A workflow opens its squadron for the length of the run and hands it to
the graph builder::

    async with FlySquadron(cwd=cwd, config=config, cost_sink=sink) as squadron:
        app = build_fly_application(squadron=squadron, event_queue=queue, ...)
        ...

Per-complexity provider/model routing is shared across squadrons in
:mod:`maverick.squadron.tiers`.
"""

from __future__ import annotations

from maverick.squadron.base import Squadron
from maverick.squadron.decomposer_pool import DecomposerAgentPool
from maverick.squadron.fly import FlySquadron
from maverick.squadron.plan import PlanSquadron
from maverick.squadron.reconcile import ReconcileSquadron
from maverick.squadron.refuel import RefuelSquadron

__all__ = [
    "DecomposerAgentPool",
    "FlySquadron",
    "PlanSquadron",
    "ReconcileSquadron",
    "RefuelSquadron",
    "Squadron",
]
