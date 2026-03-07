"""PreFlightContrarianAgent — devil's advocate for PRD analysis."""

from __future__ import annotations

from typing import Any

from maverick.agents.base import MaverickAgent
from maverick.agents.prompts.common import (
    TOOL_USAGE_GLOB,
    TOOL_USAGE_GREP,
    TOOL_USAGE_READ,
)
from maverick.agents.tools import PLANNER_TOOLS
from maverick.preflight_briefing.models import PreFlightContrarianBrief

PREFLIGHT_CONTRARIAN_SYSTEM_PROMPT = f"""You are a devil's advocate for PRD analysis.

## Your Role

You receive the outputs of three specialist agents (Scopist, Codebase Analyst,
Criteria Writer) and the original PRD. Your job is to:

1. **Scope Challenges** — identify scope items that are too broad, too narrow,
   or missing. Challenge assumptions about what should be in or out of scope.
2. **Criteria Challenges** — identify success criteria that are unmeasurable,
   redundant, or insufficient. Challenge vague or untestable criteria.
3. **Missing Considerations** — identify edge cases, dependencies, risks, or
   requirements that none of the other agents addressed.
4. **Consensus Points** — identify points where all agents agree and the
   approach is sound. These are the "keep" items.

## Tool Usage Guidelines

You have access to: **Read, Glob, Grep**

### Read
{TOOL_USAGE_READ}

### Glob
{TOOL_USAGE_GLOB}

### Grep
{TOOL_USAGE_GREP}

## Principles

- Be constructive, not dismissive. Every challenge must suggest an improvement.
- Ground challenges in the actual codebase, not hypotheticals.
- Missing considerations should be concrete, not speculative.
- Consensus points should be explicit — silence is not agreement.

## Constraints

- Do NOT modify any files — you are read-only.
- You MUST produce valid JSON matching the output schema exactly.
"""


class PreFlightContrarianAgent(MaverickAgent[str, dict[str, Any]]):
    """Agent that challenges the other pre-flight agents' briefs.

    Type Parameters:
        Context: str — the full prompt text (includes all 3 prior briefs).
        Result: dict[str, Any] — structured output matching PreFlightContrarianBrief.
    """

    def __init__(
        self,
        model: str | None = None,
        mcp_servers: dict[str, Any] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> None:
        super().__init__(
            name="preflight_contrarian",
            instructions=PREFLIGHT_CONTRARIAN_SYSTEM_PROMPT,
            allowed_tools=list(PLANNER_TOOLS),
            model=model,
            mcp_servers=mcp_servers,
            max_tokens=max_tokens,
            temperature=temperature,
            output_model=PreFlightContrarianBrief,
        )

    def build_prompt(self, context: str) -> str:
        return context
