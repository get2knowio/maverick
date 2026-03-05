"""FlightPlanGeneratorAgent for converting PRDs into structured flight plans.

This agent reads a PRD (Product Requirements Document) and the project
codebase, then produces a structured FlightPlanOutput that can be serialized
into a Maverick flight plan Markdown file.
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

FLIGHT_PLAN_GENERATOR_SYSTEM_PROMPT = f"""You are a flight plan generator.
You convert Product Requirements Documents (PRDs) into structured Maverick
flight plans. You analyze both the PRD and the project codebase to produce
comprehensive, actionable plans.

## Your Role

You receive a PRD and produce a structured flight plan with:
- A clear, measurable objective
- Specific, verifiable success criteria
- Well-defined scope (in, out, boundaries)
- Relevant context for implementers
- Realistic constraints based on the codebase

## Tool Usage Guidelines

You have access to: **Read, Glob, Grep**

### Read
{TOOL_USAGE_READ}
- Read key project files (README, CLAUDE.md, package manifests) to understand
  project structure and conventions.

### Glob
{TOOL_USAGE_GLOB}

### Grep
{TOOL_USAGE_GREP}

## Analysis Process

1. **Read the PRD** carefully to understand the requirements.
2. **Explore the codebase** to understand:
   - Project structure and architecture
   - Existing patterns and conventions
   - Files that will likely be affected
   - Test infrastructure
3. **Produce a flight plan** with:
   - An objective that captures the core goal
   - Success criteria that are specific and verifiable
   - In-scope items that reference actual project paths/modules
   - Out-of-scope items that prevent scope creep
   - Boundaries that define the limits of the work
   - Constraints based on real codebase limitations

## Output Format

You MUST produce valid JSON matching the output schema exactly. Every field
is required. Do not include markdown formatting or code fences in your output.

## Quality Guidelines

- **Success criteria**: Each criterion must be independently verifiable.
  Use specific, measurable language (e.g., "Unit tests achieve >= 80% coverage
  for new code" not "Good test coverage").
- **Scope**: Reference actual project paths and modules, not abstract concepts.
- **Constraints**: Include real technical constraints (language version, framework
  version, existing API contracts to preserve).
- **Context**: Provide enough background for someone unfamiliar with the PRD
  to understand why this work matters.

## Constraints

- Do NOT modify any files — you are read-only
- Produce a single flight plan, not multiple alternatives
- All success criteria should be unchecked (not yet completed)
"""


class FlightPlanGeneratorAgent(MaverickAgent[str, dict[str, Any]]):
    """Agent that converts a PRD into a structured flight plan.

    Uses Read, Glob, and Grep tools to explore the codebase and produce
    a comprehensive flight plan from a PRD prompt.

    Uses a three-tier output extraction strategy:
    1. SDK structured output (``output_format`` enforcement)
    2. ``validate_output()`` fallback (JSON code-block extraction)
    3. Raise AgentError (structured output is required)

    Type Parameters:
        Context: str — the full prompt text including PRD content
        Result: dict[str, Any] — structured output matching FlightPlanOutput
    """

    def __init__(
        self,
        model: str | None = None,
        mcp_servers: dict[str, Any] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> None:
        """Initialize FlightPlanGeneratorAgent.

        Args:
            model: Claude model ID (defaults to project default).
            mcp_servers: Optional MCP server configurations.
            max_tokens: Optional maximum output tokens.
            temperature: Optional sampling temperature 0.0-1.0.
        """
        # Lazy import to avoid circular import chain:
        # agents → workflows.__init__ → workflow → workflows.base
        from maverick.workflows.generate_flight_plan.models import (
            FlightPlanOutput,
        )

        super().__init__(
            name="flight_plan_generator",
            instructions=FLIGHT_PLAN_GENERATOR_SYSTEM_PROMPT,
            allowed_tools=list(PLANNER_TOOLS),
            model=model,
            mcp_servers=mcp_servers,
            max_tokens=max_tokens,
            temperature=temperature,
            output_model=FlightPlanOutput,
        )

    def build_prompt(self, context: str) -> str:
        """Construct the prompt string from context (FR-017).

        For FlightPlanGeneratorAgent, the context IS the prompt text.

        Args:
            context: Full prompt text with PRD and instructions.

        Returns:
            Complete prompt text ready for the ACP agent.
        """
        return context
