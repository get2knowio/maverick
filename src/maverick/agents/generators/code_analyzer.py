"""CodeAnalyzer generator for analyzing code snippets.

This module provides the CodeAnalyzer generator that analyzes code snippets
with different analysis types: explain, review, or summarize.
"""

from __future__ import annotations

from typing import Any

from maverick.agents.generators.base import (
    DEFAULT_MODEL,
    MAX_SNIPPET_SIZE,
    GeneratorAgent,
)
from maverick.agents.result import AgentUsage
from maverick.exceptions import GeneratorError
from maverick.logging import get_logger

# =============================================================================
# Module Logger
# =============================================================================

logger = get_logger(__name__)

# =============================================================================
# System Prompts
# =============================================================================

SYSTEM_PROMPT_EXPLAIN = """You are a code analysis assistant that \
explains code in plain English.

When given a code snippet, provide a clear, detailed explanation of:
- What the code does
- How it works (key logic flow)
- Important details about the implementation

Write in clear, accessible language. Focus on helping someone \
understand the code's behavior and purpose."""

SYSTEM_PROMPT_REVIEW = """You are a code review assistant that \
identifies potential issues and improvements.

When given a code snippet, analyze it for:
- Potential bugs or edge cases
- Performance issues
- Security concerns
- Best practice violations
- Suggestions for improvement

Be specific and actionable. Focus on substantive issues, not style \
preferences."""

SYSTEM_PROMPT_SUMMARIZE = """You are a code summarization assistant \
that provides brief overviews.

When given a code snippet, provide a concise summary that includes:
- The primary purpose of the code
- Key functions or components
- Overall structure

Keep the summary brief (2-4 sentences). Focus on high-level \
understanding."""

# =============================================================================
# CodeAnalyzer Generator
# =============================================================================


class CodeAnalyzer(GeneratorAgent):
    """Generator for analyzing code snippets.

    Provides three types of analysis:
    - explain: Plain-English explanation of what the code does
    - review: Potential issues, improvements, and observations
    - summarize: Brief summary of purpose and structure

    Invalid analysis types default to "explain" mode.

    Example:
        ```python
        analyzer = CodeAnalyzer()

        # Explain mode
        result = await analyzer.generate({
            "code": "def factorial(n): return 1 if n == 0 else n * factorial(n-1)",
            "analysis_type": "explain",
        })

        # Review mode with language hint
        result = await analyzer.generate({
            "code": "SELECT * FROM users WHERE id = " + user_input,
            "analysis_type": "review",
            "language": "SQL",
        })
        ```
    """

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        """Initialize the CodeAnalyzer.

        Args:
            model: Claude model ID (default: claude-sonnet-4-5-20250929).
        """
        # Initialize with explain prompt as default
        # Actual prompt will be set dynamically based on analysis_type
        super().__init__(
            name="code-analyzer",
            system_prompt=SYSTEM_PROMPT_EXPLAIN,
            model=model,
        )

    async def generate(
        self,
        context: dict[str, Any],
        return_usage: bool = False,
    ) -> str | tuple[str, AgentUsage]:
        """Generate code analysis based on requested analysis type.

        Args:
            context: Analysis context containing:
                - code (str): The code snippet to analyze (required)
                - analysis_type (str): Type of analysis - "explain",
                  "review", or "summarize" (optional, defaults to
                  "explain")
                - language (str): Programming language hint (optional)
            return_usage: If True, return (text, usage) tuple.

        Returns:
            Generated analysis text, or (analysis, usage) if return_usage is True.

        Raises:
            GeneratorError: If code is missing, empty, or generation fails.
        """
        # Extract and validate code
        code = context.get("code", "").strip()
        if not code:
            raise GeneratorError(
                message="Code snippet is required and cannot be empty",
                generator_name=self._name,
                input_context={"code": code},
            )

        # Get analysis type and default to "explain" for invalid types
        analysis_type = context.get("analysis_type", "explain").lower()
        if analysis_type not in ("explain", "review", "summarize"):
            logger.debug(
                "Invalid analysis_type '%s', defaulting to 'explain'",
                analysis_type,
            )
            analysis_type = "explain"

        # Get optional language hint
        language = context.get("language", "")

        # Truncate code if it exceeds limit
        code = self._truncate_input(code, MAX_SNIPPET_SIZE, "code")

        # Build prompt based on analysis type
        prompt = self._build_prompt(code, analysis_type, language)

        # Get analysis-specific system prompt without mutating instance state
        analysis_system_prompt = self._get_system_prompt(analysis_type)

        # Call the base class _query method with the system prompt override
        if return_usage:
            return await self._query_with_usage(
                prompt, system_prompt=analysis_system_prompt
            )
        return await self._query(prompt, system_prompt=analysis_system_prompt)

    def _get_system_prompt(self, analysis_type: str) -> str:
        """Get the appropriate system prompt for the analysis type.

        Args:
            analysis_type: The type of analysis (explain, review, or summarize).

        Returns:
            The system prompt for the specified analysis type.
        """
        if analysis_type == "review":
            return SYSTEM_PROMPT_REVIEW
        elif analysis_type == "summarize":
            return SYSTEM_PROMPT_SUMMARIZE
        else:
            return SYSTEM_PROMPT_EXPLAIN

    def _build_prompt(
        self,
        code: str,
        analysis_type: str,
        language: str,
    ) -> str:
        """Build the user prompt for code analysis.

        Args:
            code: The code snippet to analyze.
            analysis_type: The type of analysis (explain, review, or summarize).
            language: Optional programming language hint.

        Returns:
            Formatted prompt string.
        """
        # Start with the code block
        prompt_parts = []

        # Add language hint if provided
        if language:
            prompt_parts.append(f"Language: {language}\n")

        # Add the code
        prompt_parts.append(f"Code:\n```\n{code}\n```\n")

        # Add instruction based on analysis type
        if analysis_type == "explain":
            prompt_parts.append(
                "\nPlease explain what this code does and how it works."
            )
        elif analysis_type == "review":
            prompt_parts.append(
                "\nPlease review this code for potential issues, "
                "improvements, and best practices."
            )
        elif analysis_type == "summarize":
            prompt_parts.append(
                "\nPlease provide a brief summary of this code's purpose and structure."
            )

        return "".join(prompt_parts)
