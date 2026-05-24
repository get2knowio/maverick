"""One-shot persona agents — bundled personas, single airframe call.

Five personas (``maverick.consolidator``, ``maverick.curator``,
``maverick.validation-fixer``, ``maverick.runway-seed``,
``maverick.flight-plan-generator``) each take a per-call prompt and
return either a typed payload (curator's structured plan) or free-form
text (the other four, after airframe v0.3 added plain-text execute).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from maverick.agents.base import Agent
from maverick.payloads import SubmitCurationPlanPayload

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

    async def consolidate(self, prompt: str) -> str:
        return await self._execute_text_via_runtime(prompt, timeout=CONSOLIDATOR_TIMEOUT_SECONDS)


class ValidationFixerAgent(Agent):
    """Runs ``maverick.validation-fixer`` to apply fixes via tools."""

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

    async def fix(self, prompt: str) -> str:
        return await self._execute_text_via_runtime(prompt, timeout=FIXER_TIMEOUT_SECONDS)


class RunwaySeedAgent(Agent):
    """Runs ``maverick.runway-seed`` to write semantic files via tools."""

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

    async def seed(self, prompt: str, *, timeout: float = SEED_TIMEOUT_SECONDS) -> str:
        return await self._execute_text_via_runtime(prompt, timeout=timeout)


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

    async def derive(self, prompt: str) -> str:
        return await self._execute_text_via_runtime(prompt, timeout=VERIFICATION_TIMEOUT_SECONDS)


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
