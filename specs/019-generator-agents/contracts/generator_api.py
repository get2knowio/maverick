"""Generator Agents API Contract.

This module defines the Python Protocol/ABC interfaces for generator agents.
These contracts define the expected behavior and signatures that all generators
must implement.

Note: This is a contract definition, not implementation. Implementations
reside in src/maverick/agents/generators/.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Literal, Protocol, runtime_checkable

# =============================================================================
# Type Definitions
# =============================================================================

#: Valid analysis types for CodeAnalyzer
AnalysisType = Literal["explain", "review", "summarize"]

#: Valid error types for ErrorExplainer
ErrorType = Literal["lint", "test", "build", "type"]

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

# =============================================================================
# Base Protocol
# =============================================================================


@runtime_checkable
class GeneratorProtocol(Protocol):
    """Protocol for all generator agents.

    All generators must implement this protocol to be usable by workflows.
    """

    @property
    def name(self) -> str:
        """Unique identifier for the generator."""
        ...

    @property
    def system_prompt(self) -> str:
        """System prompt defining output format."""
        ...

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


# =============================================================================
# Abstract Base Class
# =============================================================================


class GeneratorAgent(ABC):
    """Abstract base class for all generator agents.

    Provides common infrastructure for single-shot text generation using
    Claude Agent SDK's query() function.

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
                    system_prompt="You generate helpful text.",
                )

            async def generate(self, context: dict[str, Any]) -> str:
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

    @abstractmethod
    async def generate(self, context: dict[str, Any]) -> str:
        """Generate text from context.

        Args:
            context: Input context dictionary.

        Returns:
            Generated text output.

        Raises:
            GeneratorError: On generation failure.
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
        # Implementation provided by concrete class
        ...


# =============================================================================
# Concrete Generator Contracts
# =============================================================================


class CommitMessageGeneratorContract(ABC):
    """Contract for commit message generation.

    Input Context:
        - diff (str, required): Git diff output
        - file_stats (dict[str, int], required): {insertions, deletions, files_changed}
        - scope_hint (str, optional): Override scope

    Output:
        Conventional commit message: type(scope): description
    """

    @abstractmethod
    async def generate(self, context: dict[str, Any]) -> str:
        """Generate commit message from diff context.

        Args:
            context: Must contain 'diff' and 'file_stats'.
                    May contain 'scope_hint'.

        Returns:
            Conventional commit message string.

        Raises:
            GeneratorError: If diff is empty or API call fails.
        """
        ...


class PRDescriptionGeneratorContract(ABC):
    """Contract for PR description generation.

    Input Context:
        - commits (list[dict], required): List of {hash, message, author}
        - diff_stats (dict[str, int], required): {insertions, deletions, files_changed}
        - task_summary (str, required): Feature/task description
        - validation_results (dict, required): {passed, stages: [...]}
        - sections (list[str], optional): Custom sections

    Output:
        Markdown PR description with requested sections.
    """

    @abstractmethod
    async def generate(self, context: dict[str, Any]) -> str:
        """Generate PR description from commit/validation context.

        Args:
            context: Must contain 'commits', 'diff_stats', 'task_summary',
                    'validation_results'. May contain 'sections'.

        Returns:
            Markdown PR description string.

        Raises:
            GeneratorError: If required fields missing or API call fails.
        """
        ...


class CodeAnalyzerContract(ABC):
    """Contract for code analysis generation.

    Input Context:
        - code (str, required): Code snippet to analyze
        - analysis_type (AnalysisType, required): 'explain' | 'review' | 'summarize'
        - language (str, optional): Programming language hint

    Output:
        Analysis text appropriate to requested type.
    """

    @abstractmethod
    async def generate(self, context: dict[str, Any]) -> str:
        """Generate code analysis.

        Args:
            context: Must contain 'code' and 'analysis_type'.
                    May contain 'language'.

        Returns:
            Analysis text string.

        Raises:
            GeneratorError: If code is empty or API call fails.
        """
        ...


class ErrorExplainerContract(ABC):
    """Contract for error explanation generation.

    Input Context:
        - error_output (str, required): Raw error message/traceback
        - source_context (str, optional): Relevant source code
        - error_type (ErrorType, optional): 'lint' | 'test' | 'build' | 'type'

    Output:
        Plain-English explanation with fix suggestions.
    """

    @abstractmethod
    async def generate(self, context: dict[str, Any]) -> str:
        """Generate error explanation.

        Args:
            context: Must contain 'error_output'.
                    May contain 'source_context', 'error_type'.

        Returns:
            Explanation with fix suggestions.

        Raises:
            GeneratorError: If error_output is empty or API call fails.
        """
        ...


# =============================================================================
# Exception Contract
# =============================================================================


class GeneratorErrorContract(Exception):
    """Contract for generator-specific errors.

    Attributes:
        message: Human-readable error description.
        generator_name: Name of the failing generator.
        input_context: Context that caused failure (sanitized).
    """

    message: str
    generator_name: str | None
    input_context: dict[str, Any] | None
