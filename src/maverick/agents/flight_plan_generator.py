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

When the caller provides an MCP tool for structured output, call that tool and
follow its schema. Otherwise, return a single JSON object matching the caller's
requested contract. Every required field must be present, and you must not add
explanatory prose before or after the structured output.

## Quality Guidelines

- **Success criteria**: Each criterion must be independently verifiable.
  Use specific, measurable language (e.g., "Unit tests achieve >= 80% coverage
  for new code" not "Good test coverage").
  Do NOT include build-green / CI-passing criteria as success criteria (e.g.,
  "cargo fmt exits 0", "cargo clippy exits 0", "all tests pass"). These are
  enforced automatically by the validation gate on every bead and belong in the
  Constraints section instead. Success criteria should describe *feature*
  outcomes, not toolchain hygiene.
- **Verification Properties**: For each success criterion that specifies an
  exact output, return value, or observable behavior, write an executable test
  assertion in the project's language. Place these in a ## Verification
  Properties section as a fenced code block. These are locked at plan time
  and become the deterministic acceptance gate — the implementer MUST make
  them pass. Only derive properties for criteria with exact, testable
  outcomes. Skip structural criteria ("module exists") or subjective ones.
  Example for a Rust project:
  #[test] fn verify_sc001() {{ assert_eq!(greet("Alice", Formal), "..."); }}
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

    Canonical runtime path: actor-mailbox sessions that deliver structured
    results through ``submit_flight_plan``. This registry agent also remains
    compatible with plain text-response execution when a caller intentionally
    uses ``output_schema``.

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
        super().__init__(
            name="flight_plan_generator",
            instructions=FLIGHT_PLAN_GENERATOR_SYSTEM_PROMPT,
            allowed_tools=list(PLANNER_TOOLS),
            model=model,
            mcp_servers=mcp_servers,
            max_tokens=max_tokens,
            temperature=temperature,
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
