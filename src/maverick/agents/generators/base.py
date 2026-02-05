"""GeneratorAgent abstract base class for text generation agents.

This module defines the GeneratorAgent ABC that all generator agents must inherit
from. It uses Claude Agent SDK's query() function for stateless, single-shot text
generation without tools.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, query

from maverick.agents.result import AgentUsage
from maverick.agents.tools import GENERATOR_TOOLS
from maverick.agents.utils import extract_text
from maverick.constants import DEFAULT_MODEL
from maverick.exceptions import GeneratorError
from maverick.logging import get_logger

__all__ = [
    "GeneratorAgent",
    "DEFAULT_MODEL",
]

# =============================================================================
# Module Logger
# =============================================================================

logger = get_logger(__name__)

# =============================================================================
# Constants
# =============================================================================

#: Maximum diff size in bytes (100KB)
MAX_DIFF_SIZE: int = 102400

#: Maximum code snippet size in bytes (10KB)
MAX_SNIPPET_SIZE: int = 10240

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

            async def generate(
                self,
                context: dict[str, Any],
                return_usage: bool = False
            ) -> str | tuple[str, AgentUsage]:
                # All context is provided in the prompt
                prompt = f"Generate text for: {context['input']}"
                if return_usage:
                    return await self._query_with_usage(prompt)
                return await self._query(prompt)
        ```
    """

    def __init__(
        self,
        name: str,
        system_prompt: str,
        model: str = DEFAULT_MODEL,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> None:
        """Initialize the generator.

        Args:
            name: Unique identifier for the generator.
            system_prompt: System prompt defining output format.
            model: Claude model ID.
            max_tokens: Optional maximum output tokens (SDK default used if None).
            temperature: Optional sampling temperature 0.0-1.0 (SDK default).

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
        self._max_tokens = max_tokens
        self._temperature = temperature
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
        # Build extra_args for API parameters (max_tokens, temperature)
        # SDK requires string values in extra_args
        extra_args: dict[str, str | None] = {}
        if self._max_tokens is not None:
            extra_args["max_tokens"] = str(self._max_tokens)
        if self._temperature is not None:
            extra_args["temperature"] = str(self._temperature)

        return ClaudeAgentOptions(
            system_prompt=self._system_prompt,
            model=self._model,
            max_turns=MAX_TURNS,
            allowed_tools=list(GENERATOR_TOOLS),
            extra_args=extra_args,
        )

    @abstractmethod
    async def generate(
        self,
        context: dict[str, Any],
        return_usage: bool = False,
    ) -> str | tuple[str, AgentUsage]:
        """Generate text from context.

        Args:
            context: Input context dictionary (varies by generator type).
            return_usage: If True, return (text, usage) tuple.

        Returns:
            Generated text output, or (text, usage) if return_usage is True.

        Raises:
            GeneratorError: On generation failure (API errors, invalid input).
        """
        ...

    async def _query(self, prompt: str, system_prompt: str | None = None) -> str:
        """Execute a single-shot query using Claude Agent SDK.

        Args:
            prompt: The user prompt to send to Claude.
            system_prompt: Optional system prompt override.

        Returns:
            Generated text response.

        Raises:
            GeneratorError: If the query fails.
        """
        text, _ = await self._query_with_usage(prompt, system_prompt)
        return text

    async def _query_with_usage(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> tuple[str, AgentUsage]:
        """Execute query and return text with usage stats.

        Args:
            prompt: The user prompt to send to Claude.
            system_prompt: Optional system prompt override.

        Returns:
            Tuple of (generated text, usage stats).

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
            # Build extra_args for API parameters
            extra_args: dict[str, str | None] = {}
            if self._max_tokens is not None:
                extra_args["max_tokens"] = str(self._max_tokens)
            if self._temperature is not None:
                extra_args["temperature"] = str(self._temperature)

            options = ClaudeAgentOptions(
                system_prompt=system_prompt,
                model=self._model,
                max_turns=MAX_TURNS,
                allowed_tools=list(GENERATOR_TOOLS),
                extra_args=extra_args,
            )
        else:
            options = self._options

        try:
            text_parts: list[str] = []
            messages = []

            async for message in query(prompt=prompt, options=options):
                messages.append(message)
                # Extract text from AssistantMessage
                # NOTE: Using type().__name__ string comparison to avoid importing
                # SDK message types, keeping generators lightweight and decoupled
                if type(message).__name__ == "AssistantMessage":
                    text = extract_text(message)
                    if text:
                        text_parts.append(text)

            result_text = "\n".join(text_parts)
            usage = self._extract_usage(messages)

            logger.debug(
                "Generator '%s' received response length: %d, tokens: %d",
                self._name,
                len(result_text),
                usage.total_tokens,
            )
            return result_text, usage

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
        except Exception as e:
            # Classify Claude SDK errors for better reporting
            error_msg = self._classify_sdk_error(e)
            logger.error(
                "Generator '%s' query failed: %s",
                self._name,
                error_msg,
            )
            raise GeneratorError(
                message=error_msg,
                generator_name=self._name,
            ) from e

    @staticmethod
    def _classify_sdk_error(error: Exception) -> str:
        """Classify a Claude SDK error into a human-readable message.

        Provides actionable context for common failure modes like capacity
        exhaustion, authentication failures, and CLI process crashes.

        Args:
            error: The exception raised by the SDK.

        Returns:
            Descriptive error message.
        """
        error_str = str(error)
        error_type = type(error).__name__

        # Check for ProcessError attributes (SDK subprocess failures)
        exit_code = getattr(error, "exit_code", None)

        # Capacity / rate limit indicators
        capacity_indicators = [
            "capacity",
            "rate limit",
            "overloaded",
            "529",
            "too many requests",
        ]
        if any(indicator in error_str.lower() for indicator in capacity_indicators):
            return f"Claude API capacity exhausted: {error_str}"

        # Authentication errors
        auth_indicators = ["auth", "api key", "unauthorized", "403", "401"]
        if any(indicator in error_str.lower() for indicator in auth_indicators):
            return f"Claude API authentication error: {error_str}"

        # CLI process failures (exit code but no specific classification)
        if exit_code is not None:
            return (
                f"Claude CLI process failed (exit code {exit_code}). "
                f"This may indicate capacity exhaustion, a network error, "
                f"or a CLI crash. Original error: {error_type}: {error_str}"
            )

        # Generic SDK errors
        if "ClaudeSDK" in error_type or "CLI" in error_type:
            return f"Claude SDK error ({error_type}): {error_str}"

        return f"Unexpected error ({error_type}): {error_str}"

    def _extract_usage(self, messages: list[Any]) -> AgentUsage:
        """Extract usage statistics from messages (FR-014).

        Args:
            messages: List of messages from Claude response.

        Returns:
            AgentUsage with token counts and timing.
        """
        from maverick.agents.utils import extract_usage

        return extract_usage(messages)

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
