"""``FlySquadron`` — agents the ``fly`` workflow exercises.

When ``actors.fly.implementer.tiers`` / ``actors.fly.reviewer.tiers`` is
configured, one agent per defined tier is built at startup. Each per-tier
agent owns its own persistent runtime scope and provider/model binding.
Bead routing (complexity → tier) and escalation policy
(complex-bead-failed → retry on next-higher tier) stay in the Burr fly
graph; this layer just builds and hands out agents.

Tests and any no-tiers caller fall back to a single agent under the
:data:`~maverick.squadron.tiers.DEFAULT_TIER` key.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from maverick.agents.base import Agent
from maverick.agents.coding import CodingAgent
from maverick.agents.reviewer import ReviewerAgent
from maverick.config import AgentBindingConfig
from maverick.runtime.agent_factory import runtime_for_agent
from maverick.squadron.base import Squadron
from maverick.squadron.tiers import (
    DEFAULT_TIER,
    TIER_ORDER,
    binding_for_complexity,
    escalation_ladder,
    merge_tier_config,
)

#: Back-compat alias — this module owned the helper before it was shared.
_merge_tier_config = merge_tier_config

if TYPE_CHECKING:
    from maverick.config import MaverickConfig
    from maverick.runtime.registry import CostSink


class FlySquadron(Squadron):
    """Squadron for the bead-implementing ``fly`` workflow."""

    WORKFLOW_NAME = "fly-beads"

    coders: dict[str, CodingAgent]
    correctness_reviewers: dict[str, ReviewerAgent]
    completeness_reviewers: dict[str, ReviewerAgent]

    def __init__(
        self,
        *,
        cwd: Path,
        config: MaverickConfig,
        cost_sink: CostSink | None = None,
        implementer_config: Any = None,
        reviewer_config: Any = None,
        implementer_tiers: Any = None,
        reviewer_tiers: Any = None,
    ) -> None:
        super().__init__(cwd=cwd, config=config, cost_sink=cost_sink)
        self._implementer_config = implementer_config
        self._reviewer_config = reviewer_config
        self._implementer_tiers = implementer_tiers
        self._reviewer_tiers = reviewer_tiers
        self.coders = {}
        self.correctness_reviewers = {}
        self.completeness_reviewers = {}

    def _binding_for_complexity(self, tier_name: str, override: Any) -> AgentBindingConfig | None:
        """Thin instance-level alias for :func:`binding_for_complexity`."""
        return binding_for_complexity(tier_name, override)

    def _build_coder(self, tier_name: str, step_config: Any, override: Any = None) -> CodingAgent:
        suffix = "" if tier_name == DEFAULT_TIER else f".{tier_name}"
        runtime, _ = runtime_for_agent(
            "implement",
            agents_config=self._config.agents,
            binding_override=self._binding_for_complexity(tier_name, override),
        )
        return CodingAgent(
            runtime=runtime,
            cwd=str(self._cwd),
            cost_sink=self._cost_sink,
            step_config=step_config,
            tag=f"coder{suffix}",
            **self._agent_protection_kwargs(),
        )

    def _build_reviewer_pair(self, tier_name: str, step_config: Any, override: Any = None) -> None:
        suffix = "" if tier_name == DEFAULT_TIER else f".{tier_name}"
        binding_override = self._binding_for_complexity(tier_name, override)
        correctness_runtime, _ = runtime_for_agent(
            "review",
            agents_config=self._config.agents,
            binding_override=binding_override,
        )
        completeness_runtime, _ = runtime_for_agent(
            "review",
            agents_config=self._config.agents,
            binding_override=binding_override,
        )
        self.correctness_reviewers[tier_name] = ReviewerAgent(
            runtime=correctness_runtime,
            cwd=str(self._cwd),
            cost_sink=self._cost_sink,
            step_config=step_config,
            review_kind="correctness",
            persona_name="maverick.correctness-reviewer",
            tag=f"correctness-reviewer{suffix}",
            **self._agent_protection_kwargs(),
        )
        self.completeness_reviewers[tier_name] = ReviewerAgent(
            runtime=completeness_runtime,
            cwd=str(self._cwd),
            cost_sink=self._cost_sink,
            step_config=step_config,
            review_kind="completeness",
            persona_name="maverick.completeness-reviewer",
            tag=f"completeness-reviewer{suffix}",
            **self._agent_protection_kwargs(),
        )

    async def _build_agents(self) -> None:
        # Implementers ----------------------------------------------------
        if self._implementer_tiers is None:
            self.coders[DEFAULT_TIER] = self._build_coder(DEFAULT_TIER, self._implementer_config)
        else:
            for tier_name in TIER_ORDER:
                override = getattr(self._implementer_tiers, tier_name, None)
                if override is None:
                    continue
                step_config = _merge_tier_config(self._implementer_config, override)
                self.coders[tier_name] = self._build_coder(tier_name, step_config, override)
            if not self.coders:
                self.coders[DEFAULT_TIER] = self._build_coder(
                    DEFAULT_TIER, self._implementer_config
                )

        # Reviewers — two lenses (correctness + completeness) per tier ---
        reviewer_base = (
            self._reviewer_config
            if self._reviewer_config is not None
            else self._implementer_config
        )
        if self._reviewer_tiers is None:
            self._build_reviewer_pair(DEFAULT_TIER, reviewer_base)
        else:
            for tier_name in TIER_ORDER:
                override = getattr(self._reviewer_tiers, tier_name, None)
                if override is None:
                    continue
                step_config = _merge_tier_config(reviewer_base, override)
                self._build_reviewer_pair(tier_name, step_config, override)
            if not self.correctness_reviewers:
                self._build_reviewer_pair(DEFAULT_TIER, reviewer_base)

        await asyncio.gather(*(a.open() for a in self._all_agents()))

    def implementer_escalation_ladder(self) -> tuple[str, ...]:
        """Tier names a transient-failing implementer escalates along.

        Uncapped: ``ImplementerTiersConfig.escalation_threshold`` counts
        *fix rounds before promoting*, not escalation steps, so it is not
        a cap on this ladder. (It is currently consumed nowhere — see
        #135.)
        """
        return escalation_ladder(self._implementer_tiers)

    def reviewer_escalation_ladder(self) -> tuple[str, ...]:
        """Tier names a transient-failing reviewer escalates along."""
        return escalation_ladder(self._reviewer_tiers)

    def coder_for(self, tier_name: str) -> CodingAgent:
        """Look up the coder for ``tier_name``.

        Falls back to ``DEFAULT_TIER`` (single-actor mode); if that
        isn't present either, returns an arbitrary cached coder. The
        supervisor's escalation routing is the authoritative tier
        picker — by the time we get here we've already resolved
        ``tier_name`` to a key the squadron knows about.
        """
        return self.coders.get(tier_name) or next(iter(self.coders.values()))

    def correctness_reviewer_for(self, tier_name: str) -> ReviewerAgent:
        return self.correctness_reviewers.get(tier_name) or next(
            iter(self.correctness_reviewers.values())
        )

    def completeness_reviewer_for(self, tier_name: str) -> ReviewerAgent:
        return self.completeness_reviewers.get(tier_name) or next(
            iter(self.completeness_reviewers.values())
        )

    def _all_agents(self) -> Iterable[Agent]:
        yield from self.coders.values()
        yield from self.correctness_reviewers.values()
        yield from self.completeness_reviewers.values()


__all__ = ["DEFAULT_TIER", "TIER_ORDER", "FlySquadron"]
