"""NavigatorAgent — architecture and module layout specialist."""

from __future__ import annotations

from typing import Any

from maverick.agents.base import MaverickAgent
from maverick.agents.prompts.common import (
    TOOL_USAGE_GLOB,
    TOOL_USAGE_GREP,
    TOOL_USAGE_READ,
)
from maverick.agents.tools import PLANNER_TOOLS
from maverick.briefing.models import NavigatorBrief

NAVIGATOR_SYSTEM_PROMPT = f"""You are a software architecture navigator.

## Your Role

Given a flight plan and codebase context, you analyze the architectural
implications and produce a structured brief covering:

1. **Architecture Decisions** — key ADRs for the proposed change, including
   rationale and alternatives considered.
2. **Module Structure** — proposed file/directory layout for new code.
3. **Integration Points** — where the new code connects to existing systems.

## Tool Usage Guidelines

You have access to: **Read, Glob, Grep**

### Read
{TOOL_USAGE_READ}

### Glob
{TOOL_USAGE_GLOB}

### Grep
{TOOL_USAGE_GREP}

## Principles

- Explore the codebase to understand existing patterns before proposing structure.
- Favor consistency with existing architecture over novel approaches.
- Each architecture decision must include alternatives considered.
- Be concrete about file paths and module names.

## Constraints

- Do NOT modify any files — you are read-only.
- You MUST produce valid JSON matching the output schema exactly.
"""


class NavigatorAgent(MaverickAgent[str, dict[str, Any]]):
    """Agent that analyzes architecture and module layout for a flight plan.

    Type Parameters:
        Context: str — the full prompt text.
        Result: dict[str, Any] — structured output matching NavigatorBrief.
    """

    def __init__(
        self,
        model: str | None = None,
        mcp_servers: dict[str, Any] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> None:
        super().__init__(
            name="navigator",
            instructions=NAVIGATOR_SYSTEM_PROMPT,
            allowed_tools=list(PLANNER_TOOLS),
            model=model,
            mcp_servers=mcp_servers,
            max_tokens=max_tokens,
            temperature=temperature,
            output_model=NavigatorBrief,
        )

    def build_prompt(self, context: str) -> str:
        return context
