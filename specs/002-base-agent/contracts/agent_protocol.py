"""
Agent Protocol Definitions

This file defines the public API contracts for the base agent abstraction layer.
These protocols serve as the interface specification that implementations must follow.

Feature: 002-base-agent
Date: 2025-12-12
"""
from __future__ import annotations

from abc import abstractmethod
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, Protocol, TypeVar, runtime_checkable

# Type variable for agent classes
AgentT = TypeVar("AgentT", bound="AgentProtocol")


# =============================================================================
# Data Contracts
# =============================================================================


class AgentUsageProtocol(Protocol):
    """Contract for usage statistics (FR-014)."""

    @property
    def input_tokens(self) -> int:
        """Number of input tokens consumed."""
        ...

    @property
    def output_tokens(self) -> int:
        """Number of output tokens generated."""
        ...

    @property
    def total_cost_usd(self) -> float | None:
        """Total cost in USD (may be unavailable)."""
        ...

    @property
    def duration_ms(self) -> int:
        """Execution duration in milliseconds."""
        ...

    @property
    def total_tokens(self) -> int:
        """Total tokens (input + output)."""
        ...


class AgentResultProtocol(Protocol):
    """Contract for agent execution results (FR-008)."""

    @property
    def success(self) -> bool:
        """Whether execution succeeded."""
        ...

    @property
    def output(self) -> str:
        """Text output from agent."""
        ...

    @property
    def metadata(self) -> dict[str, Any]:
        """Arbitrary metadata."""
        ...

    @property
    def errors(self) -> list[Exception]:
        """Errors encountered during execution."""
        ...

    @property
    def usage(self) -> AgentUsageProtocol:
        """Usage statistics."""
        ...


class AgentContextProtocol(Protocol):
    """Contract for runtime context (FR-009)."""

    @property
    def cwd(self) -> Path:
        """Working directory for agent execution."""
        ...

    @property
    def branch(self) -> str:
        """Current git branch name."""
        ...

    @property
    def config(self) -> Any:
        """Application configuration (MaverickConfig)."""
        ...

    @property
    def extra(self) -> dict[str, Any]:
        """Additional context for specific agents."""
        ...


# =============================================================================
# Agent Contract
# =============================================================================


@runtime_checkable
class AgentProtocol(Protocol):
    """
    Contract for all Maverick agents (FR-001, FR-004).

    Agents know HOW to do tasks. Workflows know WHEN to do them.

    All implementations must:
    - Accept name, system_prompt, allowed_tools at construction (FR-002)
    - Validate tools at construction time (FR-002)
    - Implement async execute() method (FR-004, FR-013)
    - Provide streaming query() helper (FR-005)
    """

    @property
    def name(self) -> str:
        """Unique identifier for the agent."""
        ...

    @property
    def system_prompt(self) -> str:
        """System prompt defining agent behavior."""
        ...

    @property
    def allowed_tools(self) -> list[str]:
        """Tools the agent may use."""
        ...

    @abstractmethod
    async def execute(self, context: AgentContextProtocol) -> AgentResultProtocol:
        """
        Execute the agent task.

        Args:
            context: Runtime context (cwd, branch, config)

        Returns:
            Structured result with success, output, metadata, errors, usage

        Raises:
            AgentError: Wrapped SDK errors (no automatic retries per FR-007)
        """
        ...

    async def query(
        self, prompt: str, cwd: str | Path | None = None
    ) -> AsyncIterator[Any]:
        """
        Stream messages from Claude for a single query (FR-005).

        On mid-stream failure, yields partial content before raising StreamingError.

        Args:
            prompt: The prompt to send to Claude
            cwd: Optional working directory override

        Yields:
            Message objects as they stream from Claude

        Raises:
            StreamingError: On mid-stream failure (after yielding partial content)
            AgentError: On other SDK errors
        """
        ...


# =============================================================================
# Registry Contract
# =============================================================================


class AgentRegistryProtocol(Protocol):
    """
    Contract for agent registry (FR-010, FR-011, FR-012).

    The registry enables:
    - Dynamic agent discovery by name
    - Loose coupling between workflows and agent implementations
    - Centralized agent registration
    """

    def register(self, name: str, cls: type[AgentProtocol]) -> None:
        """
        Register an agent class with a unique name (FR-011).

        Args:
            name: Unique name for the agent
            cls: Agent class to register

        Raises:
            DuplicateAgentError: If name already registered
        """
        ...

    def get(self, name: str) -> type[AgentProtocol]:
        """
        Look up an agent class by name (FR-012).

        Args:
            name: Name of the agent to look up

        Returns:
            Agent class

        Raises:
            AgentNotFoundError: If name not found
        """
        ...

    def list_agents(self) -> list[str]:
        """
        List all registered agent names.

        Returns:
            List of registered agent names
        """
        ...

    def create(self, name: str, **kwargs: Any) -> AgentProtocol:
        """
        Look up and instantiate an agent by name.

        Args:
            name: Name of the agent to create
            **kwargs: Arguments passed to agent constructor

        Returns:
            Instantiated agent

        Raises:
            AgentNotFoundError: If name not found
        """
        ...


# =============================================================================
# Utility Contracts
# =============================================================================


class TextExtractorProtocol(Protocol):
    """Contract for text extraction utilities (FR-006)."""

    def extract_text(self, message: Any) -> str:
        """
        Extract text content from an AssistantMessage.

        Args:
            message: AssistantMessage object

        Returns:
            Plain text content
        """
        ...

    def extract_all_text(self, messages: list[Any]) -> str:
        """
        Extract text from all AssistantMessage objects in a list.

        Args:
            messages: List of Message objects

        Returns:
            Combined text content
        """
        ...
