"""StructuralistAgent — data models and interface specialist."""

from __future__ import annotations

from typing import Any

from maverick.agents.base import MaverickAgent
from maverick.agents.prompts.common import (
    TOOL_USAGE_GLOB,
    TOOL_USAGE_GREP,
    TOOL_USAGE_READ,
)
from maverick.agents.tools import PLANNER_TOOLS

STRUCTURALIST_SYSTEM_PROMPT = f"""You are a data modeling and type design specialist.

## Your Role

Given a flight plan and codebase context, you analyze the data modeling
implications and produce a structured brief covering:

1. **Entities** — proposed data models/classes with fields, types, and
   relationships to other entities.
2. **Interfaces** — protocols, ABCs, or typed contracts that define
   boundaries between components, including methods and consumers.

## Tool Usage Guidelines

You have access to: **Read, Glob, Grep**

### Read
{TOOL_USAGE_READ}

### Glob
{TOOL_USAGE_GLOB}

### Grep
{TOOL_USAGE_GREP}

## Principles

- Examine existing models to match conventions (naming, modeling patterns).
- Identify validation rules and constraints for each entity.
- Use fields as "name: type" strings (e.g., "email: str", "created_at: datetime")
  matching the project's type annotation style.
- Define interfaces at natural boundaries between components.

## Constraints

- Do NOT modify any files — you are read-only.
- If the caller provides an MCP tool for structured output, call that tool and
    follow its schema. Otherwise, return a single JSON object with no
    explanatory prose before or after it.
"""


class StructuralistAgent(MaverickAgent[str, dict[str, Any]]):
    """Agent that analyzes data models and interfaces for a flight plan.

    Type Parameters:
        Context: str — the full prompt text.
        Result: dict[str, Any] — structured output matching StructuralistBrief.
    """

    def __init__(
        self,
        model: str | None = None,
        mcp_servers: dict[str, Any] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> None:
        super().__init__(
            name="structuralist",
            instructions=STRUCTURALIST_SYSTEM_PROMPT,
            allowed_tools=list(PLANNER_TOOLS),
            model=model,
            mcp_servers=mcp_servers,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    def build_prompt(self, context: str) -> str:
        return context
