"""``BriefingAgent`` — generic briefing agent backed by OpenCode.

Used by both refuel briefings (navigator/structuralist/recon/contrarian)
and pre-flight briefings (scopist/codebase_analyst/criteria_writer/
preflight_contrarian). Each instance owns one result schema and one
persona name, both passed at construction time.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import BaseModel

from maverick.agents.base import Agent

if TYPE_CHECKING:
    from maverick.executor.config import StepConfig
    from maverick.runtime.opencode import (
        CostSink,
        OpenCodeClient,
        OpenCodeServerHandle,
        Tier,
    )

BRIEFING_TIMEOUT_SECONDS = 1200

# Map the in-process agent label to the bundled OpenCode persona file.
# The .md files live at ``runtime/opencode/profile/agents/maverick.<persona>.md``.
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

    Returns ``None`` for unmapped names so the OpenCode server falls
    back to its default agent and surfaces the missing persona in
    logs rather than silently routing to the wrong system prompt.
    """
    return OPENCODE_AGENT_MAP.get(agent_name)


class BriefingAgent(Agent):
    """One briefing agent: per-instance schema + per-instance persona."""

    # Set per-instance via constructor; the class default is BaseModel
    # so type checkers see a valid type.
    result_model: ClassVar[type[BaseModel]] = BaseModel
    provider_tier: ClassVar[str] = "briefing"

    def __init__(
        self,
        *,
        handle: OpenCodeServerHandle,
        cwd: str,
        agent_name: str,
        result_model: type[BaseModel],
        step_config: StepConfig | dict[str, Any] | None = None,
        tier_overrides: dict[str, Tier] | None = None,
        cost_sink: CostSink | None = None,
        tag: str | None = None,
        client_factory: Callable[[], OpenCodeClient] | None = None,
    ) -> None:
        super().__init__(
            handle=handle,
            cwd=cwd,
            step_config=step_config,
            tier_overrides=tier_overrides,
            cost_sink=cost_sink,
            tag=tag or f"briefing.{agent_name}",
            opencode_agent=opencode_agent_for(agent_name),
            result_model=result_model,
            client_factory=client_factory,
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
        return await self._send_structured(wrapped, timeout=BRIEFING_TIMEOUT_SECONDS)


__all__ = [
    "BRIEFING_TIMEOUT_SECONDS",
    "OPENCODE_AGENT_MAP",
    "BriefingAgent",
    "opencode_agent_for",
]
