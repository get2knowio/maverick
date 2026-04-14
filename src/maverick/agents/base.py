"""MaverickAgent abstract base class.

This module defines the MaverickAgent ABC that all concrete agents must inherit from.
It provides a standardized interface for agent creation via ACP-based execution.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from maverick.constants import DEFAULT_MODEL

__all__ = [
    "MaverickAgent",
    "BUILTIN_TOOLS",
    "DEFAULT_MODEL",
]

# =============================================================================
# Type Variables for Generic MaverickAgent
# =============================================================================

# Note: These TypeVars are not bound to AgentContext/AgentResult because
# specialized agents use domain-specific context and result types
# (e.g., ReviewContext, ImplementerContext, FixResult, etc.)
TContext = TypeVar("TContext", contravariant=True)
TResult = TypeVar("TResult", covariant=True)

# =============================================================================
# Constants
# =============================================================================

#: Built-in tools available to all agents (FR-002)
BUILTIN_TOOLS: frozenset[str] = frozenset(
    {
        "Read",
        "Write",
        "Edit",
        "Bash",
        "Glob",
        "Grep",
        "NotebookEdit",
        "WebFetch",
        "WebSearch",
        "TodoWrite",
        "Task",
        "ExitPlanMode",
    }
)


# =============================================================================
# Abstract Base Class
# =============================================================================


class MaverickAgent(ABC, Generic[TContext, TResult]):
    """Abstract base class for all Maverick agents (FR-001).

    This class provides a standardized interface for agent creation.
    Concrete agents inherit from this class and implement the
    build_prompt() method to construct prompts for ACP-based execution.

    For ACP-based execution (FR-017), agents implement build_prompt(context) -> str
    to construct the prompt text; the ACP executor handles all interaction with the
    agent subprocess.

    Agents know HOW to do tasks. Workflows know WHEN to do them.

    Type Parameters:
        TContext: The context type this agent accepts (contravariant).
        TResult: The result type this agent returns (covariant).

    Attributes:
        name: Unique identifier for the agent.
        instructions: Agent-specific role and behavioral guidelines (appended
            to the Claude Code system prompt preset).
        allowed_tools: Tools the agent may use.
        model: Claude model ID (defaults to claude-sonnet-4-5-20250929).
        mcp_servers: MCP server configurations for custom tools.

    Example:
        ```python
        class GreeterAgent(MaverickAgent[AgentContext, AgentResult]):
            def __init__(self):
                super().__init__(
                    name="greeter",
                    instructions="You are a friendly greeter.",
                    allowed_tools=[],
                )

            def build_prompt(self, context: AgentContext) -> str:
                return f"Greet the user: {context.extra.get('name', 'World')}"
        ```
    """

    def __init__(
        self,
        name: str,
        instructions: str,
        allowed_tools: list[str],
        model: str | None = None,
        mcp_servers: dict[str, Any] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> None:
        """Initialize the MaverickAgent.

        Args:
            name: Unique identifier for the agent.
            instructions: Agent-specific role and behavioral guidelines.
                This is appended to the Claude Code system prompt preset
                via the ``{"type": "preset", "preset": "claude_code",
                "append": instructions}`` pattern.  It should describe
                *who the agent is*, not what task it is doing right now.
            allowed_tools: Tools the agent may use (validated at construction).
            model: Optional Claude model ID.
            mcp_servers: Optional MCP server configurations.
            max_tokens: Optional maximum output tokens (default used if None).
            temperature: Optional sampling temperature 0.0-1.0 (default).

        Raises:
            InvalidToolError: If any tool in allowed_tools is unknown.
        """
        self._name = name
        self._instructions = instructions
        self._allowed_tools = list(allowed_tools)
        self._model = model or DEFAULT_MODEL
        self._mcp_servers = mcp_servers or {}
        self._max_tokens = max_tokens
        self._temperature = temperature

        # Validate tools at construction time (FR-002)
        self._validate_tools(self._allowed_tools, self._mcp_servers)

    @property
    def name(self) -> str:
        """Unique identifier for the agent."""
        return self._name

    @property
    def instructions(self) -> str:
        """Agent-specific role and behavioral guidelines (appended to preset)."""
        return self._instructions

    @property
    def allowed_tools(self) -> list[str]:
        """Tools the agent may use."""
        return self._allowed_tools.copy()

    @property
    def model(self) -> str:
        """Claude model ID."""
        return self._model

    @property
    def mcp_servers(self) -> dict[str, Any]:
        """MCP server configurations."""
        return self._mcp_servers.copy()

    def _validate_tools(
        self,
        allowed_tools: list[str],
        mcp_servers: dict[str, Any],
    ) -> None:
        """Validate that all tools are known (FR-002).

        Args:
            allowed_tools: List of tool names to validate.
            mcp_servers: MCP server configurations.

        Raises:
            InvalidToolError: If any tool is unknown.
        """
        from maverick.exceptions import InvalidToolError

        # Build set of valid MCP tool patterns
        mcp_tool_prefixes = {f"mcp__{server}__" for server in mcp_servers}

        for tool in allowed_tools:
            # Check if it's a builtin tool
            if tool in BUILTIN_TOOLS:
                continue

            # Check if it matches an MCP tool pattern
            is_mcp_tool = any(tool.startswith(prefix) for prefix in mcp_tool_prefixes)
            if is_mcp_tool:
                continue

            # Unknown tool
            available = sorted(BUILTIN_TOOLS) + [
                f"mcp__{server}__<tool>" for server in sorted(mcp_servers)
            ]
            raise InvalidToolError(tool, available)

    @abstractmethod
    def build_prompt(self, context: TContext) -> str:
        """Construct the prompt string from a typed context (FR-017).

        This method is the ACP-compatible interface. Agents implement
        this to construct prompt text; the ACP executor handles all interaction
        with the agent subprocess.

        Args:
            context: Domain-specific context (ImplementerContext, ReviewContext, etc.)

        Returns:
            Complete prompt text ready for the ACP agent.
        """
        ...
