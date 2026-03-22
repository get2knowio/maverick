"""FixerAgent for applying targeted code fixes.

Handles validation failures, gate remediation, and other fix-from-error-output
scenarios. Has full search and Bash access to diagnose issues and verify fixes.
"""

from __future__ import annotations

from typing import Any

from maverick.agents.base import MaverickAgent
from maverick.agents.context import AgentContext
from maverick.agents.prompts.common import (
    TOOL_USAGE_BASH,
    TOOL_USAGE_EDIT,
    TOOL_USAGE_GLOB,
    TOOL_USAGE_GREP,
    TOOL_USAGE_READ,
    TOOL_USAGE_WRITE,
)
from maverick.agents.tools import AUTONOMOUS_FIXER_TOOLS
from maverick.logging import get_logger
from maverick.models.fixer import FixerResult

logger = get_logger(__name__)

# =============================================================================
# Constants
# =============================================================================

FIXER_SYSTEM_PROMPT = f"""You are a code fixer within an orchestrated workflow.
You fix validation failures, gate check errors, and other issues identified by
the orchestration layer.

## Your Role

You analyze error output, identify root causes, apply targeted fixes, and
optionally verify them by re-running commands via Bash.

## Tool Usage Guidelines

You have access to: **Read, Write, Edit, Glob, Grep, Bash**

### Read
{TOOL_USAGE_READ}
- Read the specific file mentioned in the error to understand context
  around the failure before applying changes.

### Edit
{TOOL_USAGE_EDIT}

### Write
{TOOL_USAGE_WRITE}

### Glob
{TOOL_USAGE_GLOB}

### Grep
{TOOL_USAGE_GREP}

### Bash
{TOOL_USAGE_BASH}
- Use Bash to run validation commands and verify your fixes work.

## Approach

1. Analyze the error output carefully
2. Identify the root cause of each failure
3. Search for related files if needed (Glob/Grep)
4. Apply minimal, targeted fixes
5. Optionally re-run failing commands via Bash to verify fixes
6. Report what you fixed and the final status

## Code Quality Principles

- **Minimal changes only**: Make only the changes necessary to fix the stated
  error. Do not refactor surrounding code.
- **No feature additions**: Do not add features, improvements, or enhancements
  beyond what is needed to resolve the error.
- **Security awareness**: Do not introduce command injection, XSS, or other
  vulnerabilities when applying fixes. Validate at system boundaries.
- **Read before writing**: Always read and understand the file before modifying
  it. Do not guess at file contents or structure.
- **Match existing style**: Preserve the coding style, naming conventions, and
  formatting of the surrounding code.

## Constraints

- Make only the changes necessary to fix the stated errors
- Do not refactor surrounding code or add features
- Do not run git operations (commits, pushes) — the orchestration handles that
- Preserve existing code style and formatting
"""


# =============================================================================
# FixerAgent
# =============================================================================


class FixerAgent(MaverickAgent[AgentContext, FixerResult]):
    """Agent for fixing validation failures and gate errors.

    Has full tool access (Read, Write, Edit, Glob, Grep, Bash) to diagnose
    issues, search for related files, apply fixes, and verify them.

    Used for:
        - Fixing linting, formatting, and type errors from validation pipelines
        - Remediating gate check failures after implementation
        - Applying targeted fixes from error output

    Type Parameters:
        Context: AgentContext - base context type (uses extra dict for prompts)
        Result: FixerResult - typed output contract with success, summary,
            files_mentioned, and error_details fields.
    """

    def __init__(
        self,
        model: str | None = None,
        mcp_servers: dict[str, Any] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> None:
        """Initialize FixerAgent.

        Args:
            model: Claude model ID (defaults to claude-sonnet-4-5-20250929).
            mcp_servers: Optional MCP server configurations.
            max_tokens: Optional maximum output tokens (SDK default used if None).
            temperature: Optional sampling temperature 0.0-1.0 (SDK default).
        """
        super().__init__(
            name="fixer",
            instructions=FIXER_SYSTEM_PROMPT,
            allowed_tools=list(AUTONOMOUS_FIXER_TOOLS),
            model=model,
            mcp_servers=mcp_servers,
            max_tokens=max_tokens,
            temperature=temperature,
            output_model=FixerResult,
        )

    def build_prompt(self, context: AgentContext | dict[str, Any]) -> str:
        """Construct the prompt string from context (FR-017).

        Args:
            context: Runtime context — either an AgentContext with
                extra["prompt"] or a plain dict with a "prompt" key.

        Returns:
            Complete prompt text ready for the ACP agent.
        """
        if isinstance(context, dict):
            return str(context.get("prompt", ""))
        return str(context.extra.get("prompt", ""))
