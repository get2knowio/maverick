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
from maverick.runtime.agent_factory import runtime_for_agent
from maverick.squadron.base import Squadron

if TYPE_CHECKING:
    from maverick.config import MaverickConfig
    from maverick.runtime.registry import CostSink


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
        generator_runtime, _ = runtime_for_agent("generate", agents_config=self._config.agents)
        self.generator = GeneratorAgent(
            runtime=generator_runtime,
            cwd=str(self._cwd),
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

    def _all_agents(self) -> Iterable[Agent]:
        gen = getattr(self, "generator", None)
        if gen is not None:
            yield gen
        yield from self._briefings


__all__ = ["PlanSquadron"]
