"""One-shot persona agents — bundled personas, single airframe call.

These five agents (``maverick.consolidator``, ``maverick.curator``,
``maverick.validation-fixer``, ``maverick.runway-seed``,
``maverick.flight-plan-generator``) each take a per-call prompt and
return a small typed payload. Airframe adapters require a ``schema``
on ``execute()``, so each agent pairs its persona name with a tiny
Pydantic schema and a one-method send.

Each agent is constructed with an :class:`airframe.AgentRuntime` (built
via :func:`runtime_for_agent`) and a working directory; callers
typically do::

    from maverick.config import load_config
    from maverick.runtime.agent_factory import runtime_for_agent

    config = load_config()
    runtime, _ = runtime_for_agent("briefing", agents_config=config.agents)
    async with ConsolidatorAgent(runtime=runtime, cwd=cwd) as agent:
        payload = await agent.consolidate(prompt)

The role passed to :func:`runtime_for_agent` reflects each persona's
weight class — analysis/summarisation goes through ``briefing``,
tool-using fixers through ``implement``, judgment-style curation
through ``review``, artefact creation through ``generate``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from maverick.agents.base import Agent
from maverick.payloads import (
    SubmitConsolidatedSummaryPayload,
    SubmitCurationPlanPayload,
    SubmitFixOutcomePayload,
    SubmitSeedOutcomePayload,
    SubmitVerificationPropertiesPayload,
)

if TYPE_CHECKING:
    from airframe.protocol import AgentRuntime

    from maverick.runtime.registry import CostSink

CONSOLIDATOR_TIMEOUT_SECONDS = 600
FIXER_TIMEOUT_SECONDS = 1800
SEED_TIMEOUT_SECONDS = 1800
CURATOR_TIMEOUT_SECONDS = 600
VERIFICATION_TIMEOUT_SECONDS = 600


class ConsolidatorAgent(Agent):
    """Runs ``maverick.consolidator`` to produce updated insights markdown."""

    result_model: ClassVar[type[SubmitConsolidatedSummaryPayload]] = (
        SubmitConsolidatedSummaryPayload
    )
    provider_tier: ClassVar[str] = "briefing"
    persona_name: ClassVar[str | None] = "maverick.consolidator"

    def __init__(
        self,
        *,
        runtime: AgentRuntime,
        cwd: str,
        cost_sink: CostSink | None = None,
        tag: str | None = None,
    ) -> None:
        super().__init__(runtime=runtime, cwd=cwd, cost_sink=cost_sink, tag=tag)

    async def consolidate(self, prompt: str) -> SubmitConsolidatedSummaryPayload:
        payload = await self._execute_via_runtime(prompt, timeout=CONSOLIDATOR_TIMEOUT_SECONDS)
        assert isinstance(payload, SubmitConsolidatedSummaryPayload)
        return payload


class ValidationFixerAgent(Agent):
    """Runs ``maverick.validation-fixer`` to apply fixes via tools."""

    result_model: ClassVar[type[SubmitFixOutcomePayload]] = SubmitFixOutcomePayload
    provider_tier: ClassVar[str] = "implement"
    persona_name: ClassVar[str | None] = "maverick.validation-fixer"

    def __init__(
        self,
        *,
        runtime: AgentRuntime,
        cwd: str,
        cost_sink: CostSink | None = None,
        tag: str | None = None,
    ) -> None:
        super().__init__(runtime=runtime, cwd=cwd, cost_sink=cost_sink, tag=tag)

    async def fix(self, prompt: str) -> SubmitFixOutcomePayload:
        payload = await self._execute_via_runtime(prompt, timeout=FIXER_TIMEOUT_SECONDS)
        assert isinstance(payload, SubmitFixOutcomePayload)
        return payload


class RunwaySeedAgent(Agent):
    """Runs ``maverick.runway-seed`` to write semantic files via tools."""

    result_model: ClassVar[type[SubmitSeedOutcomePayload]] = SubmitSeedOutcomePayload
    provider_tier: ClassVar[str] = "briefing"
    persona_name: ClassVar[str | None] = "maverick.runway-seed"

    def __init__(
        self,
        *,
        runtime: AgentRuntime,
        cwd: str,
        cost_sink: CostSink | None = None,
        tag: str | None = None,
    ) -> None:
        super().__init__(runtime=runtime, cwd=cwd, cost_sink=cost_sink, tag=tag)

    async def seed(
        self, prompt: str, *, timeout: float = SEED_TIMEOUT_SECONDS
    ) -> SubmitSeedOutcomePayload:
        payload = await self._execute_via_runtime(prompt, timeout=timeout)
        assert isinstance(payload, SubmitSeedOutcomePayload)
        return payload


class CuratorAgent(Agent):
    """Runs ``maverick.curator`` to produce a jj curation plan."""

    result_model: ClassVar[type[SubmitCurationPlanPayload]] = SubmitCurationPlanPayload
    provider_tier: ClassVar[str] = "review"
    persona_name: ClassVar[str | None] = "maverick.curator"

    def __init__(
        self,
        *,
        runtime: AgentRuntime,
        cwd: str,
        cost_sink: CostSink | None = None,
        tag: str | None = None,
    ) -> None:
        super().__init__(runtime=runtime, cwd=cwd, cost_sink=cost_sink, tag=tag)

    async def curate(self, prompt: str) -> SubmitCurationPlanPayload:
        payload = await self._execute_via_runtime(prompt, timeout=CURATOR_TIMEOUT_SECONDS)
        assert isinstance(payload, SubmitCurationPlanPayload)
        return payload


class VerificationPropertiesAgent(Agent):
    """Runs ``maverick.flight-plan-generator`` to derive verification tests."""

    result_model: ClassVar[type[SubmitVerificationPropertiesPayload]] = (
        SubmitVerificationPropertiesPayload
    )
    provider_tier: ClassVar[str] = "generate"
    persona_name: ClassVar[str | None] = "maverick.flight-plan-generator"

    def __init__(
        self,
        *,
        runtime: AgentRuntime,
        cwd: str,
        cost_sink: CostSink | None = None,
        tag: str | None = None,
    ) -> None:
        super().__init__(runtime=runtime, cwd=cwd, cost_sink=cost_sink, tag=tag)

    async def derive(self, prompt: str) -> SubmitVerificationPropertiesPayload:
        payload = await self._execute_via_runtime(prompt, timeout=VERIFICATION_TIMEOUT_SECONDS)
        assert isinstance(payload, SubmitVerificationPropertiesPayload)
        return payload


__all__ = [
    "CONSOLIDATOR_TIMEOUT_SECONDS",
    "CURATOR_TIMEOUT_SECONDS",
    "FIXER_TIMEOUT_SECONDS",
    "SEED_TIMEOUT_SECONDS",
    "VERIFICATION_TIMEOUT_SECONDS",
    "ConsolidatorAgent",
    "CuratorAgent",
    "RunwaySeedAgent",
    "ValidationFixerAgent",
    "VerificationPropertiesAgent",
]
