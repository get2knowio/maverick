"""FixerAgent and GateRemediationAgent for applying targeted validation fixes.

This module provides:
- FixerAgent: Minimal, constrained fixer (Read, Write, Edit only)
- GateRemediationAgent: Autonomous fixer with Bash access for gate failures
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
from maverick.agents.tools import AUTONOMOUS_FIXER_TOOLS, FIXER_TOOLS
from maverick.logging import get_logger
from maverick.models.fixer import FixerResult

logger = get_logger(__name__)

# =============================================================================
# Constants
# =============================================================================

FIXER_SYSTEM_PROMPT = f"""You are a validation fixer.
You apply targeted corrections to specific files within an orchestrated workflow.

## Your Role

You apply the exact fix described in the prompt. The orchestration layer handles:
- Running validation pipelines (format, lint, type check, tests)
- Deciding which fixes to apply and in what order
- Re-running validation after your changes to verify the fix worked

You focus on:
- Reading the file to understand context before making changes
- Applying the minimal, focused change that addresses the stated error
- Preserving existing code style and formatting

## Tool Usage Guidelines

You have access to: **Read, Write, Edit**

### Read
{TOOL_USAGE_READ}
- Read the specific file mentioned in the fix prompt to understand context
  around the error before applying changes.

### Edit
{TOOL_USAGE_EDIT}

### Write
{TOOL_USAGE_WRITE}

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

- You receive explicit file paths — do not search for files
- Make only the changes necessary to fix the stated error
- Do not refactor surrounding code
- Do not add features or improvements
"""


# =============================================================================
# FixerAgent
# =============================================================================


class FixerAgent(MaverickAgent[AgentContext, FixerResult]):
    """Minimal agent for applying targeted validation fixes.

    This agent has the smallest tool set (Read, Write, Edit) and expects
    explicit file paths and error information. It does not search for files
    or investigate issues - it applies specific fixes to known locations.

    Type Parameters:
        Context: AgentContext - base context type (uses extra dict for prompts)
        Result: FixerResult - typed output contract with success, summary,
            files_mentioned, and error_details fields.

    Use Cases:
        - Fixing linting errors at specific line numbers
        - Applying formatting corrections
        - Resolving type errors in identified files
        - Applying suggested fixes from code review

    Not For:
        - Investigating bug reports (use IssueFixerAgent)
        - Implementing features (use ImplementerAgent)
        - Searching for problematic code (use CodeReviewerAgent)

    Example:
        >>> agent = FixerAgent()
        >>> context = AgentContext(
        ...     cwd=Path("/workspace/project"),
        ...     branch="feature/fix",
        ...     config=MaverickConfig(),
        ...     extra={"prompt": "Fix linting error in file.py line 42"}
        ... )
        >>> result = await agent.execute(context)
        >>> result.success
        True
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
            allowed_tools=list(FIXER_TOOLS),
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


# =============================================================================
# GateRemediationAgent
# =============================================================================

GATE_REMEDIATION_SYSTEM_PROMPT = f"""You are a gate remediation fixer.
The orchestrator independently ran validation and found failures after the
implementer agent completed its work. You have Bash access to run commands,
fix the issues, and re-run validation to verify your fixes.

## Your Role

You fix validation gate failures that the orchestrator detected. You have full
access to read, write, and search code, plus Bash for running commands.

## Tool Usage Guidelines

You have access to: **Read, Write, Edit, Glob, Grep, Bash**

### Read
{TOOL_USAGE_READ}

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

## Approach

1. Analyze the validation failure output carefully
2. Identify the root cause of each failure
3. Apply minimal, targeted fixes
4. Re-run the failing validation commands via Bash to verify your fixes
5. Report what you fixed and the final validation status

## Constraints

- Make only the changes necessary to fix the stated errors
- Do not refactor surrounding code or add features
- Do not run git operations (commits, pushes) — the orchestration handles that
- Preserve existing code style and formatting
"""


class GateRemediationAgent(MaverickAgent[AgentContext, FixerResult]):
    """Autonomous agent for fixing gate validation failures.

    Unlike FixerAgent, this agent has Bash access and can run validation
    commands to verify its fixes. Used when the orchestrator's independent
    gate check fails after implementation.

    Type Parameters:
        Context: AgentContext - base context with gate failure details
        Result: FixerResult - typed output with success/summary/files
    """

    def __init__(
        self,
        model: str | None = None,
        mcp_servers: dict[str, Any] | None = None,
        max_tokens: int | None = None,
    ) -> None:
        """Initialize GateRemediationAgent.

        Args:
            model: Claude model ID (defaults to claude-sonnet-4-5-20250929).
            mcp_servers: Optional MCP server configurations.
            max_tokens: Optional maximum output tokens (SDK default used if None).
        """
        super().__init__(
            name="gate-remediator",
            instructions=GATE_REMEDIATION_SYSTEM_PROMPT,
            allowed_tools=list(AUTONOMOUS_FIXER_TOOLS),
            model=model,
            mcp_servers=mcp_servers,
            max_tokens=max_tokens,
            temperature=0.0,
            output_model=FixerResult,
        )

    def build_prompt(self, context: AgentContext | dict[str, Any]) -> str:
        """Construct the prompt from gate failure context.

        Args:
            context: Runtime context with gate failure details in
                extra["prompt"] or dict["prompt"].

        Returns:
            Complete prompt text ready for the ACP agent.
        """
        if isinstance(context, dict):
            return str(context.get("prompt", ""))
        return str(context.extra.get("prompt", ""))
