"""ReconAgent — risk analysis and testing strategy specialist."""

from __future__ import annotations

from typing import Any

from maverick.agents.base import MaverickAgent
from maverick.agents.prompts.common import (
    TOOL_USAGE_GLOB,
    TOOL_USAGE_GREP,
    TOOL_USAGE_READ,
)
from maverick.agents.tools import PLANNER_TOOLS
from maverick.briefing.models import ReconBrief

RECON_SYSTEM_PROMPT = f"""You are a risk analyst and testing strategist.

## Your Role

Given a flight plan and codebase context, you identify risks, ambiguities,
and testing needs, producing a structured brief covering:

1. **Risks** — potential problems with severity (low/medium/high) and
   mitigations. Focus on integration risks, performance risks, and
   dependency risks.
2. **Ambiguities** — underspecified areas in the flight plan that could
   lead to incorrect implementation, with suggested resolutions.
3. **Testing Strategy** — how to validate the implementation, including
   unit test patterns, integration test approaches, and edge cases.

## Tool Usage Guidelines

You have access to: **Read, Glob, Grep**

### Read
{TOOL_USAGE_READ}

### Glob
{TOOL_USAGE_GLOB}

### Grep
{TOOL_USAGE_GREP}

## Principles

- Examine existing test patterns and coverage to inform strategy.
- Rate risks by real likelihood, not worst-case paranoia.
- Ambiguities should be specific and actionable, not vague.
- Testing strategy should reference concrete test file patterns.

## Constraints

- Do NOT modify any files — you are read-only.
- You MUST produce valid JSON matching the output schema exactly.
"""


class ReconAgent(MaverickAgent[str, dict[str, Any]]):
    """Agent that analyzes risks and testing strategy for a flight plan.

    Type Parameters:
        Context: str — the full prompt text.
        Result: dict[str, Any] — structured output matching ReconBrief.
    """

    def __init__(
        self,
        model: str | None = None,
        mcp_servers: dict[str, Any] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> None:
        super().__init__(
            name="recon",
            instructions=RECON_SYSTEM_PROMPT,
            allowed_tools=list(PLANNER_TOOLS),
            model=model,
            mcp_servers=mcp_servers,
            max_tokens=max_tokens,
            temperature=temperature,
            output_model=ReconBrief,
        )

    def build_prompt(self, context: str) -> str:
        return context
