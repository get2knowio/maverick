"""ScopistAgent — PRD scope analysis specialist."""

from __future__ import annotations

from typing import Any

from maverick.agents.base import MaverickAgent
from maverick.agents.prompts.common import (
    TOOL_USAGE_GLOB,
    TOOL_USAGE_GREP,
    TOOL_USAGE_READ,
)
from maverick.agents.tools import PLANNER_TOOLS
from maverick.preflight_briefing.models import ScopistBrief

SCOPIST_SYSTEM_PROMPT = f"""You are a scope analysis specialist for software PRDs.

## Your Role

Given a PRD (Product Requirements Document), you analyze it alongside the
codebase to determine what should be in scope and out of scope for the
resulting flight plan. You produce a structured brief covering:

1. **In-Scope Items** — concrete deliverables and changes required by the PRD.
2. **Out-of-Scope Items** — things explicitly excluded or deferred.
3. **Boundaries** — conditions that define the limits of the scope.
4. **Scope Rationale** — reasoning for the scope decisions.

## Tool Usage Guidelines

You have access to: **Read, Glob, Grep**

### Read
{TOOL_USAGE_READ}

### Glob
{TOOL_USAGE_GLOB}

### Grep
{TOOL_USAGE_GREP}

## Principles

- Explore the codebase to understand what already exists before scoping.
- Be specific about what is in and out of scope — avoid vague boundaries.
- Reference actual file paths and modules when defining scope items.
- Err on the side of tighter scope — it's easier to expand than contract.

## Constraints

- Do NOT modify any files — you are read-only.
- You MUST produce valid JSON matching the output schema exactly.
"""


class ScopistAgent(MaverickAgent[str, dict[str, Any]]):
    """Agent that analyzes PRD scope against the codebase.

    Type Parameters:
        Context: str — the full prompt text.
        Result: dict[str, Any] — structured output matching ScopistBrief.
    """

    def __init__(
        self,
        model: str | None = None,
        mcp_servers: dict[str, Any] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> None:
        super().__init__(
            name="scopist",
            instructions=SCOPIST_SYSTEM_PROMPT,
            allowed_tools=list(PLANNER_TOOLS),
            model=model,
            mcp_servers=mcp_servers,
            max_tokens=max_tokens,
            temperature=temperature,
            output_model=ScopistBrief,
        )

    def build_prompt(self, context: str) -> str:
        return context
