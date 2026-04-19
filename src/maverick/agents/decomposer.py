"""DecomposerAgent for breaking down flight plans into work units.

This agent reads a flight plan and codebase context, then produces a
structured DecompositionOutput with individual work unit specifications.
"""

from __future__ import annotations

from typing import Any

from maverick.agents.base import MaverickAgent
from maverick.agents.prompts.common import (
    TOOL_USAGE_GLOB,
    TOOL_USAGE_GREP,
    TOOL_USAGE_READ,
)
from maverick.agents.tools import PLANNER_TOOLS
from maverick.logging import get_logger

logger = get_logger(__name__)

# =============================================================================
# Constants
# =============================================================================

DECOMPOSER_SYSTEM_PROMPT = f"""You are a work unit decomposer.
You break down flight plans into granular, ordered work units suitable
for autonomous implementation by an AI coding agent.

## Your Role

You receive a flight plan (objective, success criteria, scope, constraints)
along with codebase context. You produce a set of work units, each with:
- A kebab-case ID
- A sequence number for execution order
- Optional parallel group for concurrent units
- Dependencies on other units
- A clear task description
- Acceptance criteria traceable to flight plan success criteria
- File scope (create, modify, protect)
- Implementation instructions
- Verification commands

## Tool Usage Guidelines

You have access to: **Read, Glob, Grep**

### Read
{TOOL_USAGE_READ}

### Glob
{TOOL_USAGE_GLOB}

### Grep
{TOOL_USAGE_GREP}

## Decomposition Principles

1. **Right-sized units**: Each unit should be implementable in a single
   focused session (one bead). Not too large, not trivially small.
2. **Clear dependencies**: If unit B requires unit A's output, declare it.
3. **Verifiable**: Each unit must have at least one verification command.
4. **Traceable**: Acceptance criteria should reference flight plan success
   criteria via SC-### format when applicable.
5. **File-aware**: Use Glob/Grep to discover actual file paths for scope.
6. **Procedural**: Instructions must be step-by-step PROCEDURES, not goal
   descriptions. Use RFC 2119 keywords (MUST, SHOULD, MAY) to indicate
   mandatory vs optional steps. Each step should specify the exact file
   and line range to act on. The implementer follows procedures — it
   does not interpret goals.

## Output Format

When the caller provides an MCP tool for structured output, call that tool and
follow its schema. Otherwise, return a single JSON object matching the caller's
requested contract with no explanatory prose before or after it.

## Constraints

- Do NOT modify any files — you are read-only
- Produce work units in dependency order (sequence numbers)
- All work unit IDs must be unique and kebab-case
"""


class DecomposerAgent(MaverickAgent[str, dict[str, Any]]):
    """Agent that decomposes a flight plan into work units.

    Uses Read, Glob, and Grep tools to explore the codebase and produce
    a structured decomposition from a flight plan prompt.

    Canonical runtime path: actor-mailbox sessions that deliver structured
    results through ``submit_*`` MCP tools. This registry agent also remains
    compatible with plain text-response execution when a caller intentionally
    uses ``output_schema``.

    Type Parameters:
        Context: str — the full prompt text including flight plan content
        Result: dict[str, Any] — structured output matching DecompositionOutput
    """

    def __init__(
        self,
        model: str | None = None,
        mcp_servers: dict[str, Any] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> None:
        """Initialize DecomposerAgent.

        Args:
            model: Claude model ID (defaults to project default).
            mcp_servers: Optional MCP server configurations.
            max_tokens: Optional maximum output tokens.
            temperature: Optional sampling temperature 0.0-1.0.
        """
        super().__init__(
            name="decomposer",
            instructions=DECOMPOSER_SYSTEM_PROMPT,
            allowed_tools=list(PLANNER_TOOLS),
            model=model,
            mcp_servers=mcp_servers,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    def build_prompt(self, context: str) -> str:
        """Construct the prompt string from context (FR-017).

        For DecomposerAgent, the context IS the prompt text.

        Args:
            context: Full prompt text with flight plan and instructions.

        Returns:
            Complete prompt text ready for the ACP agent.
        """
        return context
