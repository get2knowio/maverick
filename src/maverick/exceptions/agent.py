from __future__ import annotations

from typing import Any

from maverick.exceptions.base import MaverickError


class AgentError(MaverickError):
    """Base exception for all agent-related errors.

    This is the parent class for all exceptions that can occur during agent
    execution. It provides context about which agent failed and wraps
    underlying errors with actionable information.

    Attributes:
        message: Human-readable error message.
        agent_name: Name of the agent that raised the error (if known).
        error_code: Optional error code for categorizing errors
            (e.g., INVALID_BRANCH, GIT_ERROR).
    """

    def __init__(
        self,
        message: str,
        agent_name: str | None = None,
        error_code: str | None = None,
    ) -> None:
        """Initialize the AgentError.

        Args:
            message: Human-readable error message.
            agent_name: Optional name of the agent that raised the error.
            error_code: Optional error code for categorizing errors.
        """
        self.agent_name = agent_name
        self.error_code = error_code
        super().__init__(message)


class CLINotFoundError(AgentError):
    """Exception raised when Claude CLI is not installed or not found.

    Attributes:
        message: Human-readable error message.
        cli_path: Path where CLI was expected (if known).
    """

    def __init__(
        self,
        message: str = (
            "Claude CLI not found. Install: npm install -g @anthropic-ai/claude-code"
        ),
        cli_path: str | None = None,
    ) -> None:
        """Initialize the CLINotFoundError.

        Args:
            message: Human-readable error message.
            cli_path: Path where CLI was expected.
        """
        self.cli_path = cli_path
        super().__init__(message)


class ProcessError(AgentError):
    """Exception raised when a subprocess execution fails.

    Attributes:
        message: Human-readable error message.
        exit_code: Process exit code (if available).
        stderr: Standard error output (if available).
    """

    def __init__(
        self,
        message: str,
        exit_code: int | None = None,
        stderr: str | None = None,
    ) -> None:
        """Initialize the ProcessError.

        Args:
            message: Human-readable error message.
            exit_code: Process exit code.
            stderr: Standard error output.
        """
        self.exit_code = exit_code
        self.stderr = stderr
        super().__init__(message)


class MaverickTimeoutError(AgentError):
    """Exception raised when an operation times out.

    Attributes:
        message: Human-readable error message.
        timeout_seconds: The timeout value that was exceeded.
    """

    def __init__(
        self,
        message: str = "Operation timed out",
        timeout_seconds: float | None = None,
    ) -> None:
        """Initialize the MaverickTimeoutError.

        Args:
            message: Human-readable error message.
            timeout_seconds: The timeout value that was exceeded.
        """
        self.timeout_seconds = timeout_seconds
        super().__init__(message)


class NetworkError(AgentError):
    """Exception raised for network and connection errors.

    Attributes:
        message: Human-readable error message.
        url: URL that failed (if applicable).
    """

    def __init__(
        self,
        message: str = "Network connection error",
        url: str | None = None,
    ) -> None:
        """Initialize the NetworkError.

        Args:
            message: Human-readable error message.
            url: URL that failed.
        """
        self.url = url
        super().__init__(message)


class StreamingError(AgentError):
    """Exception raised for mid-stream failures during response streaming.

    This error is raised when streaming fails after some messages have already
    been received. The partial_messages field contains any messages that were
    successfully received before the failure.

    Attributes:
        message: Human-readable error message.
        partial_messages: Messages received before the failure.
    """

    def __init__(
        self,
        message: str = "Streaming interrupted",
        partial_messages: list[Any] | None = None,
    ) -> None:
        """Initialize the StreamingError.

        Args:
            message: Human-readable error message.
            partial_messages: Messages received before the failure.
        """
        self.partial_messages = partial_messages or []
        super().__init__(message)


class MalformedResponseError(AgentError):
    """Exception raised when a response cannot be parsed.

    Attributes:
        message: Human-readable error message.
        raw_response: The raw response that could not be parsed.
    """

    def __init__(
        self,
        message: str = "Could not parse response",
        raw_response: str | None = None,
    ) -> None:
        """Initialize the MalformedResponseError.

        Args:
            message: Human-readable error message.
            raw_response: The raw response that could not be parsed.
        """
        self.raw_response = raw_response
        super().__init__(message)


class InvalidToolError(AgentError):
    """Exception raised when an unknown tool is specified in allowed_tools.

    Attributes:
        message: Human-readable error message.
        tool_name: The invalid tool name.
        available_tools: List of valid tool names.
    """

    def __init__(
        self,
        tool_name: str,
        available_tools: list[str] | None = None,
    ) -> None:
        """Initialize the InvalidToolError.

        Args:
            tool_name: The invalid tool name.
            available_tools: List of valid tool names.
        """
        self.tool_name = tool_name
        self.available_tools = available_tools or []
        message = f"Unknown tool '{tool_name}'"
        if available_tools:
            message += f". Available tools: {', '.join(sorted(available_tools)[:10])}"
            if len(available_tools) > 10:
                message += f" (and {len(available_tools) - 10} more)"
        super().__init__(message)


class DuplicateAgentError(AgentError):
    """Exception raised when registering an agent with an existing name.

    Attributes:
        message: Human-readable error message.
        agent_name: The duplicate agent name.
    """

    def __init__(self, agent_name: str) -> None:
        """Initialize the DuplicateAgentError.

        Args:
            agent_name: The duplicate agent name.
        """
        super().__init__(
            f"Agent '{agent_name}' is already registered",
            agent_name=agent_name,
        )


class AgentNotFoundError(AgentError):
    """Exception raised when an agent is not found in the registry.

    Attributes:
        message: Human-readable error message.
        agent_name: The name of the agent that was not found.
    """

    def __init__(self, agent_name: str) -> None:
        """Initialize the AgentNotFoundError.

        Args:
            agent_name: The name of the agent that was not found.
        """
        super().__init__(
            f"Agent '{agent_name}' not found in registry",
            agent_name=agent_name,
        )


class TaskParseError(AgentError):
    """Exception for task file parsing failures.

    Raised when a task file cannot be parsed, such as invalid syntax or missing
    required fields.

    Attributes:
        message: Human-readable error message.
        line_number: Line where error occurred (if known).
    """

    def __init__(
        self,
        message: str,
        line_number: int | None = None,
    ) -> None:
        """Initialize the TaskParseError.

        Args:
            message: Human-readable error message.
            line_number: Line where error occurred.
        """
        self.line_number = line_number
        super().__init__(message)


class GeneratorError(AgentError):
    """Exception for generator agent failures.

    Raised when a generator agent fails during text generation. This includes
    API errors, invalid input validation, and other generation failures.

    Attributes:
        message: Human-readable error message.
        generator_name: Name of the generator that failed.
        input_context: Sanitized context that caused the failure.
    """

    def __init__(
        self,
        message: str,
        generator_name: str | None = None,
        input_context: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the GeneratorError.

        Args:
            message: Human-readable error message.
            generator_name: Name of the generator that failed.
            input_context: Sanitized context that caused the failure.
        """
        self.generator_name = generator_name
        self.input_context = input_context
        super().__init__(message, agent_name=generator_name)
