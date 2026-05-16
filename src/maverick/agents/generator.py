"""``GeneratorAgent`` — generates a flight plan from PRD + briefing."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from maverick.agents.base import Agent
from maverick.payloads import SubmitFlightPlanPayload

if TYPE_CHECKING:
    from airframe.protocol import AgentRuntime

    from maverick.executor.config import StepConfig
    from maverick.runtime.opencode import CostSink

GENERATOR_PROMPT_TIMEOUT_SECONDS = 1200


class GeneratorAgent(Agent):
    """Flight-plan generator."""

    result_model: ClassVar[type[SubmitFlightPlanPayload]] = SubmitFlightPlanPayload
    provider_tier: ClassVar[str] = "generate"
    opencode_agent: ClassVar[str | None] = "maverick.generator"

    def __init__(
        self,
        *,
        runtime: AgentRuntime,
        cwd: str,
        step_config: StepConfig | dict[str, Any] | None = None,
        cost_sink: CostSink | None = None,
        tag: str | None = None,
    ) -> None:
        super().__init__(
            runtime=runtime,
            cwd=cwd,
            step_config=step_config,
            cost_sink=cost_sink,
            tag=tag,
        )

    async def generate(self, prompt: str) -> SubmitFlightPlanPayload:
        """Run the flight-plan prompt and return the typed payload."""
        wrapped = f"# PRD and briefing\n\n{prompt}"
        payload = await self._execute_via_runtime(
            wrapped, timeout=GENERATOR_PROMPT_TIMEOUT_SECONDS
        )
        assert isinstance(payload, SubmitFlightPlanPayload)
        return payload


__all__ = ["GENERATOR_PROMPT_TIMEOUT_SECONDS", "GeneratorAgent"]
