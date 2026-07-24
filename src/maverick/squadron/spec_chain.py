"""``SpecChainSquadron`` — the single agent `maverick spec` needs.

Binds to the existing ``"generate"`` role (R10) — the closest semantic
match for long-form Spec Kit document synthesis. Constructed with the
hidden workspace as ``cwd`` so its one :class:`SpecChainAgent` operates
inside the isolated working copy, never the user's checkout.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING

from maverick.agents.base import Agent
from maverick.agents.spec_chain import SpecChainAgent
from maverick.runtime.agent_factory import runtime_for_agent
from maverick.squadron.base import Squadron

if TYPE_CHECKING:
    from maverick.config import MaverickConfig
    from maverick.runtime.registry import CostSink

__all__ = ["SpecChainSquadron"]


class SpecChainSquadron(Squadron):
    """Squadron for the ``maverick spec`` headless chain workflow."""

    chain_agent: SpecChainAgent

    def __init__(
        self,
        *,
        cwd: Path,
        config: MaverickConfig,
        cost_sink: CostSink | None = None,
    ) -> None:
        super().__init__(cwd=cwd, config=config, cost_sink=cost_sink)

    async def _build_agents(self) -> None:
        runtime, _ = runtime_for_agent("generate", agents_config=self._config.agents)
        self.chain_agent = SpecChainAgent(
            runtime=runtime,
            cwd=str(self._cwd),
            cost_sink=self._cost_sink,
        )
        await self.chain_agent.open()

    def _all_agents(self) -> Iterable[Agent]:
        agent = getattr(self, "chain_agent", None)
        if agent is not None:
            yield agent
