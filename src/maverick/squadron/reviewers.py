"""Shared construction of the two-lens reviewer pair.

Every workflow that reviews code uses the *same* two lenses — one
``maverick.correctness-reviewer`` and one
``maverick.completeness-reviewer`` — built from the ``review`` role.
:class:`~maverick.squadron.fly.FlySquadron` owned that construction
sequence until a second consumer appeared
(:class:`~maverick.squadron.critique.CritiqueSquadron`, 058); per
research R1 it lives here instead of being copied.

The load-bearing details this function preserves from fly's original:

* **Two independent** :func:`runtime_for_agent` calls. Each
  :class:`~maverick.agents.reviewer.ReviewerAgent` owns its own runtime
  scope — the lenses run concurrently, so a shared runtime would
  interleave two conversations into one scope.
* Tier-suffixed tags (``correctness-reviewer.complex``) so per-tier
  agents stay distinguishable in cost telemetry, with no suffix at all
  under :data:`~maverick.squadron.tiers.DEFAULT_TIER`.
* The 056-context-file-protection DI bundle
  (:meth:`~maverick.squadron.base.Squadron._agent_protection_kwargs`)
  splatted into both agents.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from maverick.agents.reviewer import ReviewerAgent
from maverick.runtime.agent_factory import runtime_for_agent
from maverick.squadron.tiers import DEFAULT_TIER

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from maverick.config import AgentBindingConfig, AgentsConfig
    from maverick.executor.config import StepConfig
    from maverick.runtime.registry import CostSink

#: Persona names — stable identifiers the runway store and cost
#: telemetry key on. Not derived from ``review_kind``: the mapping is a
#: contract, not a formatting rule.
CORRECTNESS_PERSONA = "maverick.correctness-reviewer"
COMPLETENESS_PERSONA = "maverick.completeness-reviewer"

__all__ = [
    "COMPLETENESS_PERSONA",
    "CORRECTNESS_PERSONA",
    "build_reviewer_pair",
]


def build_reviewer_pair(
    *,
    cwd: Path,
    agents_config: AgentsConfig,
    step_config: StepConfig | dict[str, Any] | None = None,
    tier_name: str = DEFAULT_TIER,
    binding_override: AgentBindingConfig | None = None,
    cost_sink: CostSink | None = None,
    protection_kwargs: Mapping[str, Any] | None = None,
) -> tuple[ReviewerAgent, ReviewerAgent]:
    """Build the correctness/completeness reviewer pair for one tier.

    Args:
        cwd: Working directory the agents operate in (Guardrail 7 — the
            caller resolved it, this layer never defaults it).
        agents_config: The user's ``agents:`` block; supplies the
            ``review`` role binding.
        step_config: Per-step provider settings (timeout, max_tokens,
            …), already merged with any tier override by the caller.
        tier_name: Tier the pair serves. :data:`DEFAULT_TIER` means "the
            role's base binding" and yields unsuffixed tags.
        binding_override: Explicit provider/model override for this
            tier, or ``None`` to use the role's base binding.
        cost_sink: Where both agents report cost telemetry.
        protection_kwargs: The 056 protection DI bundle to splat into
            each agent — normally
            ``Squadron._agent_protection_kwargs()``. ``None`` leaves
            both agents on the pre-056 zero-behavior-change path.

    Returns:
        ``(correctness_reviewer, completeness_reviewer)``. Neither agent
        is opened — the caller owns lifecycle.

    Raises:
        ValueError: No ``agents.review`` binding configured.
        ImportError: The provider's adapter SDK isn't installed.
    """
    suffix = "" if tier_name == DEFAULT_TIER else f".{tier_name}"
    protection: Mapping[str, Any] = protection_kwargs or {}

    # One runtime per agent — never shared. The two lenses run
    # concurrently and each needs its own scope.
    correctness_runtime, _ = runtime_for_agent(
        "review",
        agents_config=agents_config,
        binding_override=binding_override,
    )
    completeness_runtime, _ = runtime_for_agent(
        "review",
        agents_config=agents_config,
        binding_override=binding_override,
    )

    correctness = ReviewerAgent(
        runtime=correctness_runtime,
        cwd=str(cwd),
        cost_sink=cost_sink,
        step_config=step_config,
        review_kind="correctness",
        persona_name=CORRECTNESS_PERSONA,
        tag=f"correctness-reviewer{suffix}",
        **protection,
    )
    completeness = ReviewerAgent(
        runtime=completeness_runtime,
        cwd=str(cwd),
        cost_sink=cost_sink,
        step_config=step_config,
        review_kind="completeness",
        persona_name=COMPLETENESS_PERSONA,
        tag=f"completeness-reviewer{suffix}",
        **protection,
    )
    return correctness, completeness
