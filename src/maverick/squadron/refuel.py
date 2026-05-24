"""``RefuelSquadron`` — agents the ``refuel`` workflow exercises.

* Briefing agents (navigator, structuralist, recon, contrarian, plus
  any pre-flight variants) — built on demand, since the supervisor
  fans them out via ``asyncio.gather``.
* Generator (flight-plan synthesizer).
* Decomposer pool (per-tier, demand-driven LRU pool of decomposer agents).
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel

from maverick.agents.base import Agent

if TYPE_CHECKING:
    from maverick.config import MaverickConfig
    from maverick.runtime.registry import CostSink
from maverick.agents.briefing.agent import BriefingAgent
from maverick.agents.decomposer import DecomposerAgent
from maverick.agents.generator import GeneratorAgent
from maverick.runtime.agent_factory import runtime_for_agent
from maverick.squadron.base import Squadron
from maverick.squadron.decomposer_pool import DecomposerAgentPool


class RefuelSquadron(Squadron):
    """Squadron for the refuel (PRD → flight plan → decomposed beads) workflow."""

    generator: GeneratorAgent
    decomposer_pool: DecomposerAgentPool

    def __init__(
        self,
        *,
        cwd: Path,
        config: MaverickConfig,
        cost_sink: CostSink | None = None,
        decomposer_pool_cap: int = 3,
        detail_session_max_turns: int = 5,
        fix_session_max_turns: int = 1,
    ) -> None:
        super().__init__(cwd=cwd, config=config, cost_sink=cost_sink)
        self._decomposer_pool_cap = decomposer_pool_cap
        self._detail_session_max_turns = detail_session_max_turns
        self._fix_session_max_turns = fix_session_max_turns
        # Every briefing built via build_briefing_agent is tracked here so
        # Squadron.close() can guarantee its HTTP session is shut down.
        # Refuel runs 4+ briefings per fan-out; one forgotten close =
        # leaked client.
        self._briefings: list[BriefingAgent] = []

    async def _build_agents(self) -> None:
        cwd = str(self._cwd)
        generator_runtime, _ = runtime_for_agent("generate", agents_config=self._config.agents)
        self.generator = GeneratorAgent(
            runtime=generator_runtime,
            cwd=cwd,
            cost_sink=self._cost_sink,
        )
        await self.generator.open()

        # Decomposer pool — agents are built lazily on first acquire.
        self.decomposer_pool = DecomposerAgentPool(
            cap=self._decomposer_pool_cap,
            factory=self._build_decomposer,
        )

    async def _build_decomposer(self, tier: str) -> DecomposerAgent:
        decomposer_runtime, _ = runtime_for_agent("decompose", agents_config=self._config.agents)
        agent = DecomposerAgent(
            runtime=decomposer_runtime,
            cwd=str(self._cwd),
            cost_sink=self._cost_sink,
            role="pool",
            detail_session_max_turns=self._detail_session_max_turns,
            fix_session_max_turns=self._fix_session_max_turns,
            tag=f"decomposer.pool.{tier}",
        )
        await agent.open()
        return agent

    def build_briefing_agent(
        self,
        *,
        agent_name: str,
        result_model: type[BaseModel],
    ) -> BriefingAgent:
        """Build one briefing agent on demand and track it for teardown.

        Briefings are short-lived — built per supervisor fan-out, not
        pooled. The squadron retains a reference so :meth:`close` shuts
        down every briefing's airframe runtime even if the caller
        forgets.
        """
        briefing_runtime, _ = runtime_for_agent("briefing", agents_config=self._config.agents)
        agent = BriefingAgent(
            runtime=briefing_runtime,
            cwd=str(self._cwd),
            cost_sink=self._cost_sink,
            agent_name=agent_name,
            result_model=result_model,
        )
        self._briefings.append(agent)
        return agent

    async def close(self) -> None:
        # Tear down the decomposer pool's agents before the base class
        # closes the (currently-empty) all_agents list and stops server.
        pool = getattr(self, "decomposer_pool", None)
        if pool is not None:
            await pool.teardown()
        await super().close()

    def _all_agents(self) -> Iterable[Agent]:
        gen = getattr(self, "generator", None)
        if gen is not None:
            yield gen
        yield from self._briefings


__all__ = ["RefuelSquadron"]
