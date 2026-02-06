"""FixerAgent for applying targeted validation fixes.

This module provides the FixerAgent that applies minimal, focused fixes to
specific files based on explicit error information. It is the most constrained
agent with the smallest tool set (Read, Write, Edit only).
"""

from __future__ import annotations

from typing import Any

from maverick.agents.base import MaverickAgent
from maverick.agents.context import AgentContext
from maverick.agents.result import AgentResult
from maverick.agents.tools import FIXER_TOOLS
from maverick.agents.utils import (
    extract_all_text,
    extract_streaming_text,
    get_zero_usage,
)
from maverick.exceptions import AgentError
from maverick.logging import get_logger

logger = get_logger(__name__)

# =============================================================================
# Constants
# =============================================================================

FIXER_SYSTEM_PROMPT = """You are a validation fixer.
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
- Use Read to examine files before modifying them. You MUST read a file before
  using Edit on it.
- Read the specific file mentioned in the fix prompt to understand context
  around the error before applying changes.

### Edit
- Use Edit for targeted replacements in existing files. This is your primary
  tool for applying fixes.
- You MUST Read a file before using Edit on it. Edit will fail otherwise.
- The `old_string` must be unique in the file. If it is not unique, include
  more surrounding context to disambiguate.
- Preserve exact indentation (tabs/spaces) from the file content.

### Write
- Use Write only when a complete file rewrite is necessary. Prefer Edit for
  targeted fixes.
- Write overwrites the entire file content — use it with care.

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


class FixerAgent(MaverickAgent[AgentContext, AgentResult]):
    """Minimal agent for applying targeted validation fixes.

    This agent has the smallest tool set (Read, Write, Edit) and expects
    explicit file paths and error information. It does not search for files
    or investigate issues - it applies specific fixes to known locations.

    Type Parameters:
        Context: AgentContext - base context type (uses extra dict for prompts)
        Result: AgentResult - base result type (success/failure with errors)

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
            system_prompt=FIXER_SYSTEM_PROMPT,
            allowed_tools=list(FIXER_TOOLS),
            model=model,
            mcp_servers=mcp_servers,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    async def execute(self, context: AgentContext) -> AgentResult:
        """Apply a targeted fix based on the provided context.

        The agent uses its tools (Read, Write, Edit) to apply fixes.
        Success is determined by whether the agent completed without errors;
        the caller re-runs validation afterward to verify the fix worked.

        Args:
            context: Runtime context containing:
                - prompt: Description of the fix to apply (from context.extra)
                - cwd: Working directory for file operations
                - config: Optional agent configuration

        Returns:
            AgentResult with:
                - success: True if the agent ran without errors
                - output: Agent's text output (for logging/debugging)
                - usage: Token usage statistics

        Raises:
            AgentError: Wrapped SDK errors (no automatic retries).
        """
        try:
            # Extract prompt from context.extra
            prompt = context.extra.get("prompt")
            if not prompt:
                logger.error("No prompt provided in context.extra")
                return AgentResult.failure_result(
                    errors=[
                        AgentError(
                            message="No prompt provided in context.extra",
                            agent_name=self.name,
                        )
                    ],
                    usage=get_zero_usage(),
                )

            logger.info("Applying fix with FixerAgent")

            # Execute via Claude SDK with streaming
            messages = []
            async for msg in self.query(prompt, cwd=context.cwd):
                messages.append(msg)
                # Stream text to TUI if callback is set
                if self.stream_callback:
                    text = extract_streaming_text(msg)
                    if text:
                        await self.stream_callback(text)

            output = extract_all_text(messages)
            usage = self._extract_usage(messages)

            # The agent's job is to apply fixes via tools. Whether the
            # fix actually resolved validation errors is determined by
            # re-running validation in the retry loop, not by the
            # agent's self-report.
            return AgentResult.success_result(
                output=output,
                usage=usage,
            )

        except AgentError as e:
            # Wrap AgentError in failure result (don't re-raise)
            logger.error("Agent error during fix: %s", e)
            return AgentResult.failure_result(
                errors=[e],
                usage=get_zero_usage(),
            )
        except Exception as e:
            logger.exception("Fix execution failed: %s", e)
            return AgentResult.failure_result(
                errors=[
                    AgentError(
                        message=str(e),
                        agent_name=self.name,
                    )
                ],
                usage=get_zero_usage(),
            )
