"""GeneratorAgent abstract base class for text generation agents.

This module defines the GeneratorAgent ABC that all generator agents must inherit
from. It is the ACP-compatible interface for single-shot text generation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from maverick.agents.tools import GENERATOR_TOOLS
from maverick.constants import DEFAULT_MODEL
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

    Provides common infrastructure for single-shot text generation.
    Generators operate on context provided in prompts and have no tools.

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
        allowed_tools: Tool list for this generator (typically empty).
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
            max_tokens: Optional maximum output tokens (default used if None).
            temperature: Optional sampling temperature 0.0-1.0 (default).

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

    @property
    def name(self) -> str:
        """Unique identifier for the generator."""
        return self._name

    @property
    def system_prompt(self) -> str:
        """System prompt defining output format."""
        return self._system_prompt

    @property
    def instructions(self) -> str:
        """Alias for system_prompt for executor compatibility.

        The ACP executor resolves agent instructions via
        ``getattr(agent, 'instructions', None)``.  Without this alias,
        generator agents' system prompts are silently dropped.
        """
        return self._system_prompt

    @property
    def model(self) -> str:
        """Claude model ID."""
        return self._model

    @property
    def allowed_tools(self) -> list[str]:
        """Tool list for this generator (typically empty)."""
        return list(GENERATOR_TOOLS)

    @abstractmethod
    def build_prompt(self, context: dict[str, Any]) -> str:
        """Construct the prompt string from context (FR-017).

        This method is the ACP-compatible interface. Generators implement
        this to construct the prompt text; the executor handles all interaction
        with the ACP agent subprocess.

        Args:
            context: Input context dictionary (varies by generator type).

        Returns:
            Complete prompt text ready for the ACP agent.
        """
        ...

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
