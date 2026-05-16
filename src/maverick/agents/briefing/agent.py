"""``BriefingAgent`` — typed briefing agent.

Used by both refuel briefings (navigator / structuralist / recon /
contrarian) and pre-flight briefings (scopist / codebase_analyst /
criteria_writer / preflight_contrarian). Each instance owns one result
schema and one persona name, both passed at construction time.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import BaseModel

from maverick.agents.base import Agent

if TYPE_CHECKING:
    from airframe.protocol import AgentRuntime

    from maverick.executor.config import StepConfig
    from maverick.runtime.opencode import CostSink

BRIEFING_TIMEOUT_SECONDS = 1200

# Map the in-process agent label to the bundled OpenCode persona file.
OPENCODE_AGENT_MAP: dict[str, str] = {
    "navigator": "maverick.navigator",
    "structuralist": "maverick.structuralist",
    "recon": "maverick.recon",
    "contrarian": "maverick.contrarian",
    "scopist": "maverick.scopist",
    "codebase_analyst": "maverick.codebase-analyst",
    "criteria_writer": "maverick.criteria-writer",
    "preflight_contrarian": "maverick.preflight-contrarian",
}


def opencode_agent_for(agent_name: str) -> str | None:
    """Map an agent label (``"navigator"``) to its bundled persona name.

    Returns ``None`` for unmapped names so the runtime falls back to its
    default persona rather than silently routing to the wrong system prompt.
    """
    return OPENCODE_AGENT_MAP.get(agent_name)


class BriefingAgent(Agent):
    """One briefing agent: per-instance schema + per-instance persona."""

    result_model: ClassVar[type[BaseModel]] = BaseModel
    provider_tier: ClassVar[str] = "briefing"

    def __init__(
        self,
        *,
        runtime: AgentRuntime,
        cwd: str,
        agent_name: str,
        result_model: type[BaseModel],
        step_config: StepConfig | dict[str, Any] | None = None,
        cost_sink: CostSink | None = None,
        tag: str | None = None,
    ) -> None:
        super().__init__(
            runtime=runtime,
            cwd=cwd,
            step_config=step_config,
            cost_sink=cost_sink,
            tag=tag or f"briefing.{agent_name}",
            opencode_agent=opencode_agent_for(agent_name),
            result_model=result_model,
        )
        self._agent_name = agent_name

    @property
    def agent_name(self) -> str:
        return self._agent_name

    async def brief(self, prompt: str) -> BaseModel:
        """Run the briefing prompt and return the typed payload."""
        wrapped = (
            "If your analysis surfaces no findings (e.g. greenfield project "
            "with no existing code), set empty arrays / minimal required "
            "fields rather than refusing.\n\n"
            "# Briefing input\n\n"
            f"{prompt}"
        )
        return await self._execute_via_runtime(wrapped, timeout=BRIEFING_TIMEOUT_SECONDS)


__all__ = [
    "BRIEFING_TIMEOUT_SECONDS",
    "OPENCODE_AGENT_MAP",
    "BriefingAgent",
    "opencode_agent_for",
]
