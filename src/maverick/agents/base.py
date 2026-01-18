"""MaverickAgent abstract base class.

This module defines the MaverickAgent ABC that all concrete agents must inherit from.
It wraps Claude Agent SDK interactions and provides a standardized interface for
agent creation and execution.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable, Coroutine
from pathlib import Path
from typing import TYPE_CHECKING, Any, Generic, Literal, TypeVar

from maverick.constants import DEFAULT_MODEL

if TYPE_CHECKING:
    from claude_agent_sdk import Message

    from maverick.agents.result import AgentUsage

# Type alias for stream callbacks that receive text chunks
StreamCallback = Callable[[str], Coroutine[Any, Any, None]]

__all__ = [
    "MaverickAgent",
    "BUILTIN_TOOLS",
    "DEFAULT_MODEL",
    "StreamCallback",
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

#: Permission mode type for Claude SDK
PermissionMode = Literal["default", "acceptEdits", "plan", "bypassPermissions"]

#: Default permission mode for Claude SDK
DEFAULT_PERMISSION_MODE: PermissionMode = "acceptEdits"


# =============================================================================
# Abstract Base Class
# =============================================================================


class MaverickAgent(ABC, Generic[TContext, TResult]):
    """Abstract base class for all Maverick agents (FR-001).

    This class wraps Claude Agent SDK interactions and provides a standardized
    interface for agent creation. Concrete agents inherit from this class and
    implement the execute() method.

    This is a generic class parameterized by context and result types to ensure
    type safety and prevent Liskov Substitution Principle (LSP) violations.

    Agents know HOW to do tasks. Workflows know WHEN to do them.

    Type Parameters:
        TContext: The context type this agent accepts (contravariant).
        TResult: The result type this agent returns (covariant).

    Attributes:
        name: Unique identifier for the agent.
        system_prompt: System prompt defining agent behavior.
        allowed_tools: Tools the agent may use.
        model: Claude model ID (defaults to claude-sonnet-4-5-20250929).
        mcp_servers: MCP server configurations for custom tools.

    Example:
        ```python
        class GreeterAgent(MaverickAgent[AgentContext, AgentResult]):
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
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> None:
        """Initialize the MaverickAgent.

        Args:
            name: Unique identifier for the agent.
            system_prompt: System prompt defining agent behavior.
            allowed_tools: Tools the agent may use (validated at construction).
            model: Optional Claude model ID.
            mcp_servers: Optional MCP server configurations.
            max_tokens: Optional maximum output tokens (SDK default used if None).
            temperature: Optional sampling temperature 0.0-1.0 (SDK default).

        Raises:
            InvalidToolError: If any tool in allowed_tools is unknown.
        """
        self._name = name
        self._system_prompt = system_prompt
        self._allowed_tools = list(allowed_tools)
        self._model = model or DEFAULT_MODEL
        self._mcp_servers = mcp_servers or {}
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._stream_callback: StreamCallback | None = None

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

    @property
    def stream_callback(self) -> StreamCallback | None:
        """Optional callback for streaming text chunks to the TUI."""
        return self._stream_callback

    @stream_callback.setter
    def stream_callback(self, callback: StreamCallback | None) -> None:
        """Set the stream callback for real-time output streaming."""
        self._stream_callback = callback

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

        # Build extra_args for API parameters (max_tokens, temperature)
        # SDK requires string values in extra_args
        extra_args: dict[str, str | None] = {}
        if self._max_tokens is not None:
            extra_args["max_tokens"] = str(self._max_tokens)
        if self._temperature is not None:
            extra_args["temperature"] = str(self._temperature)

        return ClaudeAgentOptions(
            allowed_tools=self._allowed_tools,
            system_prompt=self._system_prompt,
            model=self._model,
            permission_mode=DEFAULT_PERMISSION_MODE,
            mcp_servers=self._mcp_servers,
            cwd=str(cwd) if cwd else None,
            extra_args=extra_args,
            include_partial_messages=True,  # Enable token-by-token streaming
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
        from maverick.agents.utils import extract_usage

        return extract_usage(messages)

    @abstractmethod
    async def execute(self, context: TContext) -> TResult:
        """Execute the agent task (FR-004).

        Subclasses must implement this method to define the agent's behavior.

        Args:
            context: Runtime context (type varies by agent specialization).

        Returns:
            Structured result (type varies by agent specialization).

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
