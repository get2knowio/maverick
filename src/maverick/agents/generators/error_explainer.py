"""ErrorExplainer generator for plain-English error explanations.

This module provides the ErrorExplainer generator that translates cryptic error
output into actionable guidance with structured explanations.
"""

from __future__ import annotations

from typing import Any, Literal

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
# Type Definitions
# =============================================================================

#: Valid error types for ErrorExplainer
ErrorType = Literal["lint", "test", "build", "type"]

#: Runtime validation tuple for error types
VALID_ERROR_TYPES = ("lint", "test", "build", "type")

# =============================================================================
# System Prompt
# =============================================================================

SYSTEM_PROMPT = """You are an expert error explainer that translates cryptic \
error messages into clear, actionable guidance.

Your explanations MUST follow this structure:

**What happened**: Plain English description of the error (1-2 sentences)

**Why this occurred**: Root cause explanation in simple terms (1-2 sentences)

**How to fix**: Actionable steps to resolve the error (numbered list if multiple steps)

**Code example** (if applicable): A corrected code snippet showing the fix

Guidelines:
- Use simple, non-technical language where possible
- Focus on the most likely cause and fix
- If multiple causes are possible, mention the most common one first
- Keep explanations concise and practical
- Always provide actionable next steps
- If source code is provided, reference specific lines or patterns
"""

# =============================================================================
# ErrorExplainer Generator
# =============================================================================


class ErrorExplainer(GeneratorAgent):
    """Generator for plain-English error explanations.

    Translates cryptic error output (lint errors, test failures, build errors,
    type errors) into structured explanations with fix suggestions.

    Input Context:
        - error_output (str, required): Raw error message/traceback
        - source_context (str, optional): Relevant source code
        - error_type (ErrorType, optional): 'lint' | 'test' | 'build' | 'type'

    Output:
        Structured explanation with:
        - What happened (plain description)
        - Why this occurred (root cause)
        - How to fix (actionable steps)
        - Code example (if applicable)

    Example:
        ```python
        explainer = ErrorExplainer()

        context = {
            "error_output": (
                "TypeError: unsupported operand type(s) for +: "
                "'int' and 'str'"
            ),
            "source_context": 'result = 5 + "10"',
            "error_type": "type",
        }

        explanation = await explainer.generate(context)
        # Returns structured explanation with fix suggestions
        ```
    """

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        """Initialize the ErrorExplainer.

        Args:
            model: Claude model ID (default: claude-sonnet-4-5-20250929).
        """
        super().__init__(
            name="error-explainer",
            system_prompt=SYSTEM_PROMPT,
            model=model,
        )

    async def generate(
        self,
        context: dict[str, Any],
        return_usage: bool = False,
    ) -> str | tuple[str, AgentUsage]:
        """Generate error explanation from error context.

        Args:
            context: Must contain 'error_output' (str).
                    May contain 'source_context' (str), 'error_type' (ErrorType).
            return_usage: If True, return (text, usage) tuple.

        Returns:
            Structured explanation with fix suggestions,
            or (explanation, usage) if return_usage is True.

        Raises:
            GeneratorError: If error_output is missing/empty or API call fails.
        """
        # Validate required fields
        error_output = context.get("error_output")
        if not error_output or (
            isinstance(error_output, str) and not error_output.strip()
        ):
            raise GeneratorError(
                message="error_output is required and must be non-empty",
                generator_name=self._name,
                input_context={"error_output": error_output},
            )

        # Extract optional fields
        source_context = context.get("source_context", "")
        error_type = context.get("error_type")

        # Validate error_type at runtime
        if error_type and error_type not in VALID_ERROR_TYPES:
            logger.warning(
                "Invalid error_type '%s', ignoring. Valid types: %s",
                error_type,
                ", ".join(VALID_ERROR_TYPES),
            )
            error_type = None

        # Truncate source_context if needed (error_output is never truncated)
        if source_context:
            source_context = self._truncate_input(
                source_context,
                MAX_SNIPPET_SIZE,
                "source_context",
            )

        # Build prompt
        prompt = self._build_prompt(error_output, source_context, error_type)

        # Query Claude for explanation
        if return_usage:
            return await self._query_with_usage(prompt)
        return await self._query(prompt)

    def _build_prompt(
        self,
        error_output: str,
        source_context: str,
        error_type: ErrorType | None,
    ) -> str:
        """Build the prompt for error explanation.

        Args:
            error_output: Raw error message/traceback.
            source_context: Relevant source code (may be empty).
            error_type: Type of error (may be None).

        Returns:
            Formatted prompt for Claude.
        """
        prompt_parts = ["Please explain this error:"]

        # Add error type if provided
        if error_type:
            prompt_parts.append(f"\nError Type: {error_type}")

        # Add error output
        prompt_parts.append(f"\nError Output:\n```\n{error_output}\n```")

        # Add source context if provided
        if source_context:
            prompt_parts.append(f"\nRelevant Source Code:\n```\n{source_context}\n```")

        prompt_parts.append(
            "\nProvide a clear explanation following the structure "
            "defined in your system prompt."
        )

        return "\n".join(prompt_parts)
