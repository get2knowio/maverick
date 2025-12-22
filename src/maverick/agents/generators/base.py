"""GeneratorAgent abstract base class for text generation agents.

This module defines the GeneratorAgent ABC that all generator agents must inherit
from. It uses Claude Agent SDK's query() function for stateless, single-shot text
generation without tools.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, query

from maverick.agents.tools import GENERATOR_TOOLS
from maverick.agents.utils import extract_text
from maverick.exceptions import GeneratorError

# =============================================================================
# Module Logger
# =============================================================================

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

#: Maximum diff size in bytes (100KB)
MAX_DIFF_SIZE: int = 102400

#: Maximum code snippet size in bytes (10KB)
MAX_SNIPPET_SIZE: int = 10240

#: Default Claude model for generators
DEFAULT_MODEL: str = "claude-sonnet-4-5-20250929"

#: Default sections for PR descriptions
DEFAULT_PR_SECTIONS: tuple[str, ...] = ("Summary", "Changes", "Testing")

#: Fixed max_turns for generators (single-shot)
MAX_TURNS: int = 1


# =============================================================================
# Abstract Base Class
# =============================================================================


class GeneratorAgent(ABC):
    """Abstract base class for all generator agents.

    Provides common infrastructure for single-shot text generation using
    Claude Agent SDK's query() function. Generators operate on context
    provided in prompts and have no tools.

    ## Generator Role

    Generators are stateless text producers that:
    - Receive all necessary context in their prompts
    - Have no file access or command execution capabilities (no tools)
    - Generate text in a single turn (max_turns=1)
    - Are lightweight and focused on specific output formats

    The orchestration layer provides all context (diffs, code snippets,
    conventions, etc.) in the prompt. Generators do not fetch or retrieve
    data themselves.

    Attributes:
        name: Unique identifier for the generator.
        system_prompt: System prompt defining output format and behavior.
        model: Claude model ID (default: claude-sonnet-4-5-20250929).

    Example:
        ```python
        class MyGenerator(GeneratorAgent):
            def __init__(self):
                super().__init__(
                    name="my-generator",
                    system_prompt="You generate helpful text from provided context.",
                )

            async def generate(self, context: dict[str, Any]) -> str:
                # All context is provided in the prompt
                prompt = f"Generate text for: {context['input']}"
                return await self._query(prompt)
        ```
    """

    def __init__(
        self,
        name: str,
        system_prompt: str,
        model: str = DEFAULT_MODEL,
    ) -> None:
        """Initialize the generator.

        Args:
            name: Unique identifier for the generator.
            system_prompt: System prompt defining output format.
            model: Claude model ID.

        Raises:
            ValueError: If name or system_prompt is empty.
        """
        if not name:
            raise ValueError("name must be non-empty")
        if not system_prompt:
            raise ValueError("system_prompt must be non-empty")

        self._name = name
        self._system_prompt = system_prompt
        self._model = model
        self._options = self._build_options()

    @property
    def name(self) -> str:
        """Unique identifier for the generator."""
        return self._name

    @property
    def system_prompt(self) -> str:
        """System prompt defining output format."""
        return self._system_prompt

    @property
    def model(self) -> str:
        """Claude model ID."""
        return self._model

    def _build_options(self) -> ClaudeAgentOptions:
        """Build ClaudeAgentOptions for SDK query.

        Returns:
            ClaudeAgentOptions configured for single-shot generation with no tools.
        """
        return ClaudeAgentOptions(
            system_prompt=self._system_prompt,
            model=self._model,
            max_turns=MAX_TURNS,
            # Empty set - generators don't use tools
            allowed_tools=list(GENERATOR_TOOLS),
        )

    @abstractmethod
    async def generate(self, context: dict[str, Any]) -> str:
        """Generate text from context.

        Args:
            context: Input context dictionary (varies by generator type).

        Returns:
            Generated text output.

        Raises:
            GeneratorError: On generation failure (API errors, invalid input).
        """
        ...

    async def _query(self, prompt: str, system_prompt: str | None = None) -> str:
        """Execute a single-shot query using Claude Agent SDK.

        Args:
            prompt: The user prompt to send to Claude.
            system_prompt: Optional system prompt override. If provided,
                creates a new options object with this system prompt instead
                of using the instance's default options.

        Returns:
            Generated text response.

        Raises:
            GeneratorError: If the query fails.
        """
        logger.debug(
            "Generator '%s' querying with prompt length: %d",
            self._name,
            len(prompt),
        )

        # Use override options if system_prompt provided, otherwise use default
        if system_prompt is not None:
            options = ClaudeAgentOptions(
                system_prompt=system_prompt,
                model=self._model,
                max_turns=MAX_TURNS,
                # Empty set - generators don't use tools
                allowed_tools=list(GENERATOR_TOOLS),
            )
        else:
            options = self._options

        try:
            text_parts: list[str] = []

            async for message in query(prompt=prompt, options=options):
                # Extract text from AssistantMessage
                # NOTE: Using type().__name__ string comparison to avoid importing
                # SDK message types, keeping generators lightweight and decoupled
                if type(message).__name__ == "AssistantMessage":
                    text = extract_text(message)
                    if text:
                        text_parts.append(text)

            result = "\n".join(text_parts)
            logger.debug(
                "Generator '%s' received response length: %d",
                self._name,
                len(result),
            )
            return result

        except (ValueError, TypeError, RuntimeError, OSError) as e:
            # Expected errors from SDK, validation, or I/O operations
            logger.error(
                "Generator '%s' query failed: %s",
                self._name,
                str(e),
            )
            raise GeneratorError(
                message=f"Query failed: {e}",
                generator_name=self._name,
            ) from e
        except Exception:
            # Unexpected errors - log full traceback for debugging
            logger.exception(
                "Generator '%s' encountered unexpected error during query",
                self._name,
            )
            raise

    def _truncate_input(
        self,
        content: str,
        max_size: int,
        field_name: str,
    ) -> str:
        """Truncate input if it exceeds max_size.

        Args:
            content: Content to potentially truncate.
            max_size: Maximum size in bytes.
            field_name: Name for logging.

        Returns:
            Original content if under limit, or truncated with marker.
        """
        if len(content) <= max_size:
            return content

        logger.warning(
            "Truncating %s from %d to %d bytes",
            field_name,
            len(content),
            max_size,
        )
        return content[:max_size] + "\n... [truncated]"
