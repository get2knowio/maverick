"""``FlySquadron`` — agents the ``fly`` workflow exercises.

When ``actors.fly.implementer.tiers`` / ``actors.fly.reviewer.tiers`` is
configured, one agent per defined tier is built at startup. Each per-tier
agent owns its own persistent runtime scope and provider/model
binding. Bead routing (complexity → tier) and escalation policy
(complex-bead-failed → retry on next-higher tier) stay in the supervisor;
this layer just builds and hands out agents.

The actor-pool wires each per-tier ``ImplementerActor`` / ``ReviewerActor``
shell to a pre-built agent via the ``agent=`` constructor kwarg so the
existing xoscar boundary stays in place (Path A). Tests and any
no-tiers caller fall back to a single agent under the ``_DEFAULT_TIER``
key — same shape as the supervisor's legacy single-actor path.
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

if TYPE_CHECKING:
    from maverick.config import MaverickConfig
    from maverick.runtime.registry import CostSink

#: Ordered tier names (low → high intelligence). Matches WorkUnitComplexity
#: and ``maverick.actors.xoscar.fly_supervisor.TIER_ORDER``.
TIER_ORDER: tuple[str, ...] = ("trivial", "simple", "moderate", "complex")

#: Sentinel name for the single-agent fallback when no tiers are configured.
DEFAULT_TIER: str = "_default"


def _merge_tier_config(base: Any, override: Any) -> Any:
    """Merge a per-tier override over a base ``StepConfig``.

    Each field set on the override replaces the base. Fields left as
    ``None`` on the override fall through to base. Returns a new
    ``StepConfig`` (``StepConfig`` is frozen, so this is a ``model_copy``).
    """
    if base is None:
        from maverick.executor.config import StepConfig

        return StepConfig(
            provider=override.provider,
            model_id=override.model_id,
            timeout=override.timeout,
            max_tokens=override.max_tokens,
            temperature=override.temperature,
        )
    updates: dict[str, Any] = {}
    for field_name in ("provider", "model_id", "timeout", "max_tokens", "temperature"):
        value = getattr(override, field_name, None)
        if value is not None:
            updates[field_name] = value
    if not updates:
        return base
    return base.model_copy(update=updates)


class FlySquadron(Squadron):
    """Squadron for the bead-implementing ``fly`` workflow."""

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
        """Convert a per-complexity ``ImplementerTierConfig`` to a factory override.

        The complexity-tier config is a Maverick-only shape with extra
        fields (timeout / max_tokens / temperature) the airframe factory
        doesn't consume; only ``provider`` + ``model_id`` flow through.
        Returns ``None`` for the ``DEFAULT_TIER`` sentinel (no
        complexity override) or when neither field is set.
        """
        if tier_name == DEFAULT_TIER or override is None:
            return None
        provider = getattr(override, "provider", None)
        model_id = getattr(override, "model_id", None)
        if not provider or not model_id:
            return None
        return AgentBindingConfig(provider=provider, model_id=model_id)

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
        )
        self.completeness_reviewers[tier_name] = ReviewerAgent(
            runtime=completeness_runtime,
            cwd=str(self._cwd),
            cost_sink=self._cost_sink,
            step_config=step_config,
            review_kind="completeness",
            persona_name="maverick.completeness-reviewer",
            tag=f"completeness-reviewer{suffix}",
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
