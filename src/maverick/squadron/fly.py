"""``FlySquadron`` — agents the ``fly`` workflow exercises.

* Coder (implementer + fixer) — one persistent OpenCode session per bead.
* Correctness reviewer — one persistent session per bead.
* Completeness reviewer — one persistent session per bead.

The coder is reused across implement → fix within a bead so the
session retains context.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable

from maverick.agents.base import Agent
from maverick.agents.coding import CodingAgent
from maverick.agents.reviewer import ReviewerAgent
from maverick.runtime.opencode import ProviderModel
from maverick.squadron.base import Squadron


class FlySquadron(Squadron):
    """Squadron for the bead-implementing ``fly`` workflow."""

    coder: CodingAgent
    correctness_reviewer: ReviewerAgent
    completeness_reviewer: ReviewerAgent

    async def _build_agents(self) -> None:
        handle = self.handle
        cwd = str(self._cwd)
        self.coder = CodingAgent(
            handle=handle,
            cwd=cwd,
            tier_overrides=self._tier_overrides,
            cost_sink=self._cost_sink,
        )
        self.correctness_reviewer = ReviewerAgent(
            handle=handle,
            cwd=cwd,
            tier_overrides=self._tier_overrides,
            cost_sink=self._cost_sink,
            review_kind="correctness",
            opencode_agent="maverick.correctness-reviewer",
        )
        self.completeness_reviewer = ReviewerAgent(
            handle=handle,
            cwd=cwd,
            tier_overrides=self._tier_overrides,
            cost_sink=self._cost_sink,
            review_kind="completeness",
            opencode_agent="maverick.completeness-reviewer",
        )
        await asyncio.gather(
            self.coder.open(),
            self.correctness_reviewer.open(),
            self.completeness_reviewer.open(),
        )

    def _all_agents(self) -> Iterable[Agent]:
        for attr in ("coder", "correctness_reviewer", "completeness_reviewer"):
            agent = getattr(self, attr, None)
            if agent is not None:
                yield agent

    def _declared_bindings(self) -> Iterable[ProviderModel]:
        # Validate the implement and review tier bindings at startup.
        seen: set[ProviderModel] = set()
        for agent_cls in (CodingAgent, ReviewerAgent):
            for binding in self._resolved_bindings_for(agent_cls):
                if binding not in seen:
                    seen.add(binding)
                    yield binding


__all__ = ["FlySquadron"]
