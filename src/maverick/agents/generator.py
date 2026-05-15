"""``GeneratorAgent`` — generates a flight plan from PRD + briefing."""

from __future__ import annotations

from typing import ClassVar

from maverick.agents.base import Agent
from maverick.payloads import SubmitFlightPlanPayload

GENERATOR_PROMPT_TIMEOUT_SECONDS = 1200


class GeneratorAgent(Agent):
    """OpenCode-backed flight-plan generator."""

    result_model: ClassVar[type[SubmitFlightPlanPayload]] = SubmitFlightPlanPayload
    provider_tier: ClassVar[str] = "generate"
    # Persona system prompt is loaded from
    # ``runtime/opencode/profile/agents/maverick.generator.md`` via
    # ``OPENCODE_CONFIG_DIR``.
    opencode_agent: ClassVar[str | None] = "maverick.generator"

    async def generate(self, prompt: str) -> SubmitFlightPlanPayload:
        """Run the flight-plan prompt and return the typed payload.

        ``prompt`` is the per-call user content (PRD + briefing); persona
        system prompt is loaded by OpenCode from the bundled markdown
        agent file so the cache key stays stable across runs.
        """
        wrapped = f"# PRD and briefing\n\n{prompt}"
        payload = await self._send_structured(wrapped, timeout=GENERATOR_PROMPT_TIMEOUT_SECONDS)
        assert isinstance(payload, SubmitFlightPlanPayload)
        return payload


__all__ = ["GENERATOR_PROMPT_TIMEOUT_SECONDS", "GeneratorAgent"]
