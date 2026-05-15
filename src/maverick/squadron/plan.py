"""``PlanSquadron`` — agents the ``plan generate`` workflow exercises.

* Generator (flight-plan synthesizer).
* Briefing agents (scopist / codebase_analyst / criteria_writer /
  preflight_contrarian) — built on demand by the supervisor.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel

from maverick.agents.base import Agent
from maverick.agents.briefing.agent import BriefingAgent
from maverick.agents.generator import GeneratorAgent
from maverick.runtime.opencode import ProviderModel
from maverick.squadron.base import Squadron

if TYPE_CHECKING:
    from maverick.config import MaverickConfig
    from maverick.runtime.opencode import CostSink


class PlanSquadron(Squadron):
    """Squadron for the plan-generation workflow."""

    generator: GeneratorAgent

    def __init__(
        self,
        *,
        cwd: Path,
        config: MaverickConfig,
        cost_sink: CostSink | None = None,
    ) -> None:
        super().__init__(cwd=cwd, config=config, cost_sink=cost_sink)
        # Every briefing built via build_briefing_agent is tracked here so
        # Squadron.close() guarantees its HTTP session is shut down.
        # Pre-flight runs 4 briefings; one forgotten close = leaked client.
        self._briefings: list[BriefingAgent] = []

    async def _build_agents(self) -> None:
        self.generator = GeneratorAgent(
            handle=self.handle,
            cwd=str(self._cwd),
            tier_overrides=self._tier_overrides,
            cost_sink=self._cost_sink,
        )
        await self.generator.open()

    def build_briefing_agent(
        self,
        *,
        agent_name: str,
        result_model: type[BaseModel],
    ) -> BriefingAgent:
        """Build one briefing agent on demand and track it for teardown."""
        agent = BriefingAgent(
            handle=self.handle,
            cwd=str(self._cwd),
            tier_overrides=self._tier_overrides,
            cost_sink=self._cost_sink,
            agent_name=agent_name,
            result_model=result_model,
        )
        self._briefings.append(agent)
        return agent

    def _all_agents(self) -> Iterable[Agent]:
        gen = getattr(self, "generator", None)
        if gen is not None:
            yield gen
        yield from self._briefings

    def _declared_bindings(self) -> Iterable[ProviderModel]:
        seen: set[ProviderModel] = set()
        for agent_cls in (BriefingAgent, GeneratorAgent):
            for binding in self._resolved_bindings_for(agent_cls):
                if binding not in seen:
                    seen.add(binding)
                    yield binding


__all__ = ["PlanSquadron"]
