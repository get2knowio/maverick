"""MaverickAgent abstract base class.

This module defines the MaverickAgent ABC that all concrete agents must inherit from.
It wraps Claude Agent SDK interactions and provides a standardized interface for
agent creation and execution.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from claude_agent_sdk import Message

    from maverick.agents.context import AgentContext
    from maverick.agents.result import AgentResult, AgentUsage

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

#: Default Claude model for agents
DEFAULT_MODEL: str = "claude-sonnet-4-5-20250929"

#: Default permission mode for Claude SDK
DEFAULT_PERMISSION_MODE: str = "acceptEdits"


# =============================================================================
# Abstract Base Class
# =============================================================================


class MaverickAgent(ABC):
    """Abstract base class for all Maverick agents (FR-001).

    This class wraps Claude Agent SDK interactions and provides a standardized
    interface for agent creation. Concrete agents inherit from this class and
    implement the execute() method.

    Agents know HOW to do tasks. Workflows know WHEN to do them.

    Attributes:
        name: Unique identifier for the agent.
        system_prompt: System prompt defining agent behavior.
        allowed_tools: Tools the agent may use.
        model: Claude model ID (defaults to claude-sonnet-4-5-20250929).
        mcp_servers: MCP server configurations for custom tools.

    Example:
        ```python
        class GreeterAgent(MaverickAgent):
            def __init__(self):
                super().__init__(
                    name="greeter",
                    system_prompt="You are a friendly greeter.",
                    allowed_tools=[],
                )

            async def execute(self, context: AgentContext) -> AgentResult:
                messages = []
                async for msg in self.query("Hello!", cwd=context.cwd):
                    messages.append(msg)
                return AgentResult.success_result(
                    output=extract_all_text(messages),
                    usage=self._extract_usage(messages),
                )
        ```
    """

    def __init__(
        self,
        name: str,
        system_prompt: str,
        allowed_tools: list[str],
        model: str | None = None,
        mcp_servers: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the MaverickAgent.

        Args:
            name: Unique identifier for the agent.
            system_prompt: System prompt defining agent behavior.
            allowed_tools: Tools the agent may use (validated at construction).
            model: Optional Claude model ID.
            mcp_servers: Optional MCP server configurations.

        Raises:
            InvalidToolError: If any tool in allowed_tools is unknown.
        """
        self._name = name
        self._system_prompt = system_prompt
        self._allowed_tools = list(allowed_tools)
        self._model = model or DEFAULT_MODEL
        self._mcp_servers = mcp_servers or {}

        # Validate tools at construction time (FR-002)
        self._validate_tools(self._allowed_tools, self._mcp_servers)

    @property
    def name(self) -> str:
        """Unique identifier for the agent."""
        return self._name

    @property
    def system_prompt(self) -> str:
        """System prompt defining agent behavior."""
        return self._system_prompt

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

    def _build_options(self, cwd: str | Path | None = None) -> Any:
        """Build ClaudeAgentOptions for SDK client (FR-003).

        Args:
            cwd: Optional working directory override.

        Returns:
            ClaudeAgentOptions configured for this agent.
        """
        from claude_agent_sdk import ClaudeAgentOptions

        return ClaudeAgentOptions(
            allowed_tools=self._allowed_tools,
            system_prompt=self._system_prompt,
            model=self._model,
            permission_mode=DEFAULT_PERMISSION_MODE,
            mcp_servers=self._mcp_servers,
            cwd=str(cwd) if cwd else None,
        )

    def _wrap_sdk_error(self, error: Exception) -> Exception:
        """Map Claude SDK errors to Maverick error hierarchy (FR-007).

        Args:
            error: The SDK error to wrap.

        Returns:
            Wrapped Maverick exception with actionable context.
        """
        from maverick.exceptions import (
            AgentError,
            CLINotFoundError,
            MalformedResponseError,
            MaverickTimeoutError,
            NetworkError,
            ProcessError,
        )

        error_type = type(error).__name__

        if error_type == "CLINotFoundError":
            return CLINotFoundError(
                cli_path=getattr(error, "cli_path", None),
            )
        elif error_type == "ProcessError":
            return ProcessError(
                message=str(error),
                exit_code=getattr(error, "exit_code", None),
                stderr=getattr(error, "stderr", None),
            )
        elif error_type == "TimeoutError":
            return MaverickTimeoutError(
                message=str(error),
                timeout_seconds=getattr(error, "timeout_seconds", None),
            )
        elif error_type == "CLIConnectionError":
            return NetworkError(
                message=str(error),
            )
        elif error_type == "CLIJSONDecodeError":
            return MalformedResponseError(
                message=str(error),
                raw_response=getattr(error, "raw", None),
            )
        else:
            # Generic SDK error
            return AgentError(
                message=str(error),
                agent_name=self._name,
            )

    def _extract_usage(self, messages: list[Message]) -> AgentUsage:
        """Extract usage statistics from messages (FR-014).

        Args:
            messages: List of messages from Claude response.

        Returns:
            AgentUsage with token counts and timing.
        """
        from maverick.agents.result import AgentUsage

        # Find ResultMessage for usage stats
        result_msg = None
        for msg in messages:
            if type(msg).__name__ == "ResultMessage":
                result_msg = msg
                break

        if result_msg is None:
            # No result message, return zeros
            return AgentUsage(
                input_tokens=0,
                output_tokens=0,
                total_cost_usd=None,
                duration_ms=0,
            )

        # Extract usage from ResultMessage
        usage = getattr(result_msg, "usage", None) or {}
        return AgentUsage(
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            total_cost_usd=getattr(result_msg, "total_cost_usd", None),
            duration_ms=getattr(result_msg, "duration_ms", 0),
        )

    @abstractmethod
    async def execute(self, context: AgentContext) -> AgentResult:
        """Execute the agent task (FR-004).

        Subclasses must implement this method to define the agent's behavior.

        Args:
            context: Runtime context (cwd, branch, config).

        Returns:
            Structured result with success, output, metadata, errors, usage.

        Raises:
            AgentError: Wrapped SDK errors (no automatic retries per FR-007).
        """
        ...

    async def query(
        self,
        prompt: str,
        cwd: str | Path | None = None,
    ) -> AsyncIterator[Message]:
        """Stream messages from Claude for a single query (FR-005).

        This helper method handles the SDK client lifecycle and streams
        messages back to the caller. On mid-stream failure, it yields
        partial content before raising StreamingError.

        Args:
            prompt: The prompt to send to Claude.
            cwd: Optional working directory override.

        Yields:
            Message objects as they stream from Claude.

        Raises:
            StreamingError: On mid-stream failure (after yielding partial content).
            AgentError: On other SDK errors.
        """
        from claude_agent_sdk import ClaudeSDKClient

        from maverick.exceptions import StreamingError

        options = self._build_options(cwd)
        partial_messages: list[Message] = []

        try:
            async with ClaudeSDKClient(options=options) as client:
                await client.query(prompt)
                async for message in client.receive_response():
                    partial_messages.append(message)
                    yield message
        except Exception as e:
            # If we have partial messages, wrap in StreamingError
            if partial_messages:
                raise StreamingError(
                    message=f"Streaming interrupted: {e}",
                    partial_messages=partial_messages,
                ) from e
            # Otherwise, wrap the SDK error
            raise self._wrap_sdk_error(e) from e
