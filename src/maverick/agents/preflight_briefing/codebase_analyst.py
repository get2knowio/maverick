"""CodebaseAnalystAgent — codebase mapping specialist."""

from __future__ import annotations

from typing import Any

from maverick.agents.base import MaverickAgent
from maverick.agents.prompts.common import (
    TOOL_USAGE_GLOB,
    TOOL_USAGE_GREP,
    TOOL_USAGE_READ,
)
from maverick.agents.tools import PLANNER_TOOLS
from maverick.preflight_briefing.models import CodebaseAnalystBrief

CODEBASE_ANALYST_SYSTEM_PROMPT = f"""You are a codebase analysis specialist.

## Your Role

Given a PRD (Product Requirements Document), you map its requirements to
the existing codebase. You produce a structured brief covering:

1. **Relevant Modules** — existing files/directories that will be affected
   or need to be understood for this change.
2. **Existing Patterns** — architectural and coding patterns already used
   in the codebase that the implementation should follow.
3. **Integration Points** — where new code will connect to existing systems
   (APIs, databases, message queues, shared utilities).
4. **Complexity Assessment** — overall assessment of implementation complexity
   based on codebase analysis.

## Tool Usage Guidelines

You have access to: **Read, Glob, Grep**

### Read
{TOOL_USAGE_READ}

### Glob
{TOOL_USAGE_GLOB}

### Grep
{TOOL_USAGE_GREP}

## Principles

- Thoroughly explore the codebase before assessing complexity.
- Reference actual file paths and module names — do not guess.
- Identify patterns by reading multiple existing implementations.
- Be honest about complexity — neither inflate nor minimize it.

## Constraints

- Do NOT modify any files — you are read-only.
- You MUST produce valid JSON matching the output schema exactly.
"""


class CodebaseAnalystAgent(MaverickAgent[str, dict[str, Any]]):
    """Agent that maps PRD requirements to existing codebase structure.

    Type Parameters:
        Context: str — the full prompt text.
        Result: dict[str, Any] — structured output matching CodebaseAnalystBrief.
    """

    def __init__(
        self,
        model: str | None = None,
        mcp_servers: dict[str, Any] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> None:
        super().__init__(
            name="codebase_analyst",
            instructions=CODEBASE_ANALYST_SYSTEM_PROMPT,
            allowed_tools=list(PLANNER_TOOLS),
            model=model,
            mcp_servers=mcp_servers,
            max_tokens=max_tokens,
            temperature=temperature,
            output_model=CodebaseAnalystBrief,
        )

    def build_prompt(self, context: str) -> str:
        return context
