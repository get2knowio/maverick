"""FixerAgent for applying targeted validation fixes.

This module provides the FixerAgent that applies minimal, focused fixes to
specific files based on explicit error information. It is the most constrained
agent with the smallest tool set (Read, Write, Edit only).
"""

from __future__ import annotations

import json
from typing import Any

from maverick.agents.base import MaverickAgent
from maverick.agents.context import AgentContext
from maverick.agents.result import AgentResult
from maverick.agents.tools import FIXER_TOOLS
from maverick.agents.utils import extract_all_text, get_zero_usage
from maverick.exceptions import AgentError
from maverick.logging import get_logger

logger = get_logger(__name__)

# =============================================================================
# Constants
# =============================================================================

FIXER_SYSTEM_PROMPT = """You are a validation fixer.
You apply targeted corrections to specific files.

Your role:
- Apply the exact fix described in the prompt
- Make minimal, focused changes
- Preserve existing code style and formatting
- Verify the fix addresses the stated error

You have access to:
- Read: Read file contents
- Write: Create or overwrite files
- Edit: Make precise edits to existing files

Constraints:
- You receive explicit file paths - do not search for files
- Make only the changes necessary to fix the stated error
- Do not refactor surrounding code
- Do not add features or improvements

Output your result as JSON with these fields:
- success: boolean
- file_modified: boolean
- file_path: string
- changes_made: string description
- error: string or null
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

        Args:
            context: Runtime context containing:
                - prompt: Description of the fix to apply (from context.extra)
                - cwd: Working directory for file operations
                - config: Optional agent configuration

        Returns:
            AgentResult with:
                - success: True if fix was applied successfully
                - output: JSON string with fix details
                - metadata: Optional additional information
                - errors: List of any errors encountered
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

            # Execute via Claude SDK
            messages = []
            async for msg in self.query(prompt, cwd=context.cwd):
                messages.append(msg)

            output = extract_all_text(messages)
            usage = self._extract_usage(messages)

            # Try to parse the output as JSON
            try:
                parsed = json.loads(output)
                success = parsed.get("success", False)

                # Return success or failure based on the fix result
                if success:
                    return AgentResult.success_result(
                        output=output,
                        usage=usage,
                        metadata={"file_path": parsed.get("file_path")},
                    )
                else:
                    return AgentResult.failure_result(
                        errors=[
                            AgentError(
                                message=parsed.get("error", "Fix failed"),
                                agent_name=self.name,
                            )
                        ],
                        usage=usage,
                        output=output,
                    )

            except json.JSONDecodeError as e:
                logger.error("Failed to parse agent output as JSON: %s", e)
                return AgentResult.failure_result(
                    errors=[
                        AgentError(
                            message=f"Malformed JSON output: {e}",
                            agent_name=self.name,
                        )
                    ],
                    usage=usage,
                    output=output,
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
