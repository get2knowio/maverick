"""``DecomposerAgentPool`` — per-tier LRU pool of :class:`DecomposerAgent`.

Mirrors the legacy ``_DecomposerPool`` (which pooled
:class:`DecomposerActor` xoscar refs) but at the agent layer. The
RefuelSquadron exposes one of these so the actor pool — or any other
caller in step 3+ — can acquire a tier-specific decomposer without
each call paying for fresh OpenCode session setup.

Behaviour:

1. **Reuse**: an idle agent of ``tier`` is in the cache → return it.
2. **Spawn**: under the cap → call the factory for a fresh agent.
3. **Evict + spawn**: at cap with idle agents of other tiers →
   close + drop the LRU idle agent, then spawn fresh for ``tier``.
4. **Wait**: at cap with no idle agents → block until ``release``.

``set_context`` broadcasts to every live agent and is replayed onto
every freshly-spawned agent so the seeded prompt cache is consistent
across the pool.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from maverick.agents.decomposer import DecomposerAgent
from maverick.logging import get_logger

logger = get_logger(__name__)

DecomposerAgentFactory = Callable[[str], Awaitable[DecomposerAgent]]
"""``async def factory(tier_name) -> DecomposerAgent`` — builds + opens a fresh agent."""


class DecomposerAgentPool:
    """Demand-driven, LRU-evicting cache of per-tier decomposer agents."""

    def __init__(
        self,
        *,
        cap: int,
        factory: DecomposerAgentFactory,
    ) -> None:
        self._cap = max(1, cap)
        self._factory = factory
        # tier_name → list of idle agents (LIFO; tail is most recent)
        self._idle: dict[str, list[DecomposerAgent]] = {}
        # agent → tier_name (every live agent, idle or busy)
        self._agent_tier: dict[DecomposerAgent, str] = {}
        # idle agents in LRU order (oldest at index 0, newest at tail)
        self._lru: list[DecomposerAgent] = []
        # Awoken on every release / eviction so blocked acquirers retry.
        self._cond = asyncio.Condition()
        # Most recent broadcast context — applied to every freshly
        # spawned agent so it has the same outline view as its peers.
        self._context: dict[str, Any] | None = None

    @property
    def cap(self) -> int:
        return self._cap

    @property
    def total_live(self) -> int:
        """Total live agents across all tiers (busy + idle)."""
        return len(self._agent_tier)

    async def set_context(
        self,
        *,
        outline_json: str,
        flight_plan_content: str,
        verification_properties: str,
    ) -> None:
        """Update the broadcast context.

        Applied to every existing agent AND every agent spawned later.
        """
        ctx = {
            "outline_json": outline_json,
            "flight_plan_content": flight_plan_content,
            "verification_properties": verification_properties,
        }
        async with self._cond:
            self._context = ctx
            agents = list(self._agent_tier)
        if agents:
            await asyncio.gather(*(a.set_context(**ctx) for a in agents))

    async def acquire(self, tier: str) -> DecomposerAgent:
        async with self._cond:
            while True:
                # 1. Reuse an idle agent of this tier.
                idle = self._idle.get(tier)
                if idle:
                    agent = idle.pop()
                    self._lru.remove(agent)
                    return agent
                # 2. Spawn fresh under the cap.
                if self.total_live < self._cap:
                    return await self._spawn(tier)
                # 3. Evict an LRU idle agent of any tier and spawn fresh.
                if self._lru:
                    victim = self._lru[0]
                    await self._evict(victim)
                    return await self._spawn(tier)
                # 4. At cap with everything busy — wait for a release.
                await self._cond.wait()

    async def release(self, agent: DecomposerAgent, tier: str) -> None:
        async with self._cond:
            self._idle.setdefault(tier, []).append(agent)
            self._lru.append(agent)
            self._cond.notify()

    async def teardown(self) -> None:
        """Close every live agent and drop bookkeeping."""
        async with self._cond:
            agents = list(self._agent_tier)
            self._idle.clear()
            self._lru.clear()
            self._agent_tier.clear()
        for a in agents:
            try:
                await a.close()
            except Exception as exc:  # noqa: BLE001 — teardown must not raise
                logger.debug(
                    "decomposer_agent_pool.close_failed",
                    tag=getattr(a, "tag", "?"),
                    error=str(exc),
                )

    async def _spawn(self, tier: str) -> DecomposerAgent:
        """Build + register a fresh agent for ``tier``. Caller holds cond."""
        agent = await self._factory(tier)
        self._agent_tier[agent] = tier
        if self._context is not None:
            await agent.set_context(**self._context)
        return agent

    async def _evict(self, victim: DecomposerAgent) -> None:
        """Close ``victim`` and remove from bookkeeping. Caller holds cond."""
        victim_tier = self._agent_tier.pop(victim, None)
        if victim_tier is not None and victim in self._idle.get(victim_tier, []):
            self._idle[victim_tier].remove(victim)
        if victim in self._lru:
            self._lru.remove(victim)
        try:
            await victim.close()
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "decomposer_agent_pool.evict_close_failed",
                tag=getattr(victim, "tag", "?"),
                error=str(exc),
            )

    def snapshot(self) -> dict[str, Any]:
        """Read-only view of pool state for tests / diagnostics."""
        return {
            "total_live": self.total_live,
            "idle": {tier: len(lst) for tier, lst in self._idle.items()},
            "lru_length": len(self._lru),
            "context_set": self._context is not None,
        }


__all__ = ["DecomposerAgentFactory", "DecomposerAgentPool"]
