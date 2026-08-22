"""``CritiqueSquadron`` — agents the standalone ``critique`` command uses.

Exactly one reviewer pair, built at
:data:`~maverick.squadron.tiers.DEFAULT_TIER` via the shared
:func:`~maverick.squadron.reviewers.build_reviewer_pair`. No tiers (a
standalone critique has no decomposer-assigned complexity to route on)
and — deliberately — no :class:`~maverick.agents.coding.CodingAgent`.

Per 058 research R1, that last point is why this class exists rather
than reusing :class:`~maverick.squadron.fly.FlySquadron`: `FlySquadron`
also builds a coder, which requires an ``agents.implement`` binding, so
a read-only review command would fail to start on a repository
configured only for review. This squadron's dependency footprint is
exactly ``agents.review``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from maverick.agents.base import Agent
from maverick.agents.reviewer import ReviewerAgent
from maverick.squadron.base import Squadron
from maverick.squadron.reviewers import build_reviewer_pair
from maverick.squadron.tiers import DEFAULT_TIER

if TYPE_CHECKING:
    from pathlib import Path

    from maverick.config import MaverickConfig
    from maverick.executor.config import StepConfig
    from maverick.runtime.registry import CostSink


class CritiqueSquadron(Squadron):
    """Squadron for the standalone ``critique`` command: one reviewer pair."""

    WORKFLOW_NAME = "critique"

    _correctness_reviewer: ReviewerAgent
    _completeness_reviewer: ReviewerAgent

    def __init__(
        self,
        *,
        cwd: Path,
        config: MaverickConfig,
        cost_sink: CostSink | None = None,
        reviewer_config: StepConfig | dict[str, Any] | None = None,
    ) -> None:
        super().__init__(cwd=cwd, config=config, cost_sink=cost_sink)
        self._reviewer_config = reviewer_config

    @property
    def correctness_reviewer(self) -> ReviewerAgent:
        """The ``maverick.correctness-reviewer`` lens (available after ``open()``)."""
        return self._correctness_reviewer

    @property
    def completeness_reviewer(self) -> ReviewerAgent:
        """The ``maverick.completeness-reviewer`` lens (available after ``open()``)."""
        return self._completeness_reviewer

    async def _build_agents(self) -> None:
        self._correctness_reviewer, self._completeness_reviewer = build_reviewer_pair(
            cwd=self._cwd,
            agents_config=self._config.agents,
            step_config=self._reviewer_config,
            tier_name=DEFAULT_TIER,
            cost_sink=self._cost_sink,
            protection_kwargs=self._agent_protection_kwargs(),
        )
        # Both lenses run concurrently at critique time; open them the
        # same way so a slow adapter handshake isn't paid twice serially.
        await asyncio.gather(*(agent.open() for agent in self._all_agents()))

    def _all_agents(self) -> Iterable[Agent]:
        yield self._correctness_reviewer
        yield self._completeness_reviewer


__all__ = ["CritiqueSquadron"]
