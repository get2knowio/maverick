"""CriteriaWriterAgent — success criteria and objective specialist."""

from __future__ import annotations

from typing import Any

from maverick.agents.base import MaverickAgent
from maverick.agents.prompts.common import (
    TOOL_USAGE_GLOB,
    TOOL_USAGE_GREP,
    TOOL_USAGE_READ,
)
from maverick.agents.tools import PLANNER_TOOLS
from maverick.preflight_briefing.models import CriteriaWriterBrief

CRITERIA_WRITER_SYSTEM_PROMPT = f"""You are a success criteria and objective specialist.

## Your Role

Given a PRD (Product Requirements Document), you draft measurable success
criteria and a clear objective for the resulting flight plan. You produce
a structured brief covering:

1. **Success Criteria** — specific, independently verifiable criteria that
   define "done" for this PRD. Each criterion must be measurable.
2. **Objective Draft** — a clear, concise objective paragraph summarizing
   what the flight plan aims to achieve.
3. **Measurability Notes** — observations about which requirements are
   easy vs. hard to measure, and suggestions for making vague requirements
   more concrete.

## Tool Usage Guidelines

You have access to: **Read, Glob, Grep**

### Read
{TOOL_USAGE_READ}

### Glob
{TOOL_USAGE_GLOB}

### Grep
{TOOL_USAGE_GREP}

## Principles

- Every success criterion must be independently verifiable.
- Use measurable language: "X exists", "Y passes", "Z returns N".
- Explore the codebase to ground criteria in reality (existing tests,
  validation commands, CI checks).
- Do NOT include build-green / CI-passing criteria (e.g., "cargo fmt exits 0",
  "linter passes", "all tests pass"). These are enforced automatically by the
  validation pipeline on every work unit. Success criteria must describe
  *feature* outcomes, not toolchain hygiene.
- The objective should be one paragraph, action-oriented, and specific.

## Constraints

- Do NOT modify any files — you are read-only.
- You MUST produce valid JSON matching the output schema exactly.
"""


class CriteriaWriterAgent(MaverickAgent[str, dict[str, Any]]):
    """Agent that drafts measurable success criteria and objectives.

    Type Parameters:
        Context: str — the full prompt text.
        Result: dict[str, Any] — structured output matching CriteriaWriterBrief.
    """

    def __init__(
        self,
        model: str | None = None,
        mcp_servers: dict[str, Any] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> None:
        super().__init__(
            name="criteria_writer",
            instructions=CRITERIA_WRITER_SYSTEM_PROMPT,
            allowed_tools=list(PLANNER_TOOLS),
            model=model,
            mcp_servers=mcp_servers,
            max_tokens=max_tokens,
            temperature=temperature,
            output_model=CriteriaWriterBrief,
        )

    def build_prompt(self, context: str) -> str:
        return context
