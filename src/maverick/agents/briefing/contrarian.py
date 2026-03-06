"""ContrarianAgent — devil's advocate and simplification specialist."""

from __future__ import annotations

from typing import Any

from maverick.agents.base import MaverickAgent
from maverick.agents.prompts.common import (
    TOOL_USAGE_GLOB,
    TOOL_USAGE_GREP,
    TOOL_USAGE_READ,
)
from maverick.agents.tools import PLANNER_TOOLS
from maverick.briefing.models import ContrarianBrief

CONTRARIAN_SYSTEM_PROMPT = f"""You are a devil's advocate and simplification expert.

## Your Role

You receive the outputs of three specialist agents (Navigator, Structuralist,
Recon) and the original flight plan. Your job is to:

1. **Challenge** — identify assumptions, over-engineering, or questionable
   decisions in the other agents' briefs. For each challenge, explain the
   target, your counter-argument, and a concrete recommendation.
2. **Simplify** — propose simpler alternatives to complex approaches.
   For each simplification, describe the current approach, the simpler
   alternative, and the tradeoff.
3. **Consensus** — identify points where all agents agree and the approach
   is sound. These are the "keep" items.

## Tool Usage Guidelines

You have access to: **Read, Glob, Grep**

### Read
{TOOL_USAGE_READ}

### Glob
{TOOL_USAGE_GLOB}

### Grep
{TOOL_USAGE_GREP}

## Principles

- Be constructive, not dismissive. Every challenge must have a recommendation.
- Simplifications must be genuinely simpler, not just different.
- Consensus points should be explicit — silence is not agreement.
- Ground challenges in the actual codebase, not hypotheticals.

## Constraints

- Do NOT modify any files — you are read-only.
- You MUST produce valid JSON matching the output schema exactly.
"""


class ContrarianAgent(MaverickAgent[str, dict[str, Any]]):
    """Agent that challenges other agents' briefs and proposes simplifications.

    Type Parameters:
        Context: str — the full prompt text (includes all 3 prior briefs).
        Result: dict[str, Any] — structured output matching ContrarianBrief.
    """

    def __init__(
        self,
        model: str | None = None,
        mcp_servers: dict[str, Any] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> None:
        super().__init__(
            name="contrarian",
            instructions=CONTRARIAN_SYSTEM_PROMPT,
            allowed_tools=list(PLANNER_TOOLS),
            model=model,
            mcp_servers=mcp_servers,
            max_tokens=max_tokens,
            temperature=temperature,
            output_model=ContrarianBrief,
        )

    def build_prompt(self, context: str) -> str:
        return context
