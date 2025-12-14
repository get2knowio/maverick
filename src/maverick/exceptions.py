from __future__ import annotations

from typing import Any


class MaverickError(Exception):
    """Base exception class for all Maverick-specific errors.

    This is the root of the Maverick exception hierarchy. All custom exceptions
    in the Maverick application should inherit from this class. This allows
    catching all Maverick-specific errors at CLI boundaries while letting
    system exceptions propagate naturally.

    Attributes:
        message: Human-readable error message describing what went wrong.

    Example:
        ```python
        try:
            # Maverick operations
            workflow.execute()
        except MaverickError as e:
            # Catch all Maverick errors at CLI boundary
            logger.error(f"Maverick error: {e.message}")
            sys.exit(1)
        ```
    """

    def __init__(self, message: str) -> None:
        """Initialize the MaverickError.

        Args:
            message: Human-readable error message.
        """
        self.message = message
        super().__init__(message)


class AgentError(MaverickError):
    """Base exception for all agent-related errors.

    This is the parent class for all exceptions that can occur during agent
    execution. It provides context about which agent failed and wraps
    underlying errors with actionable information.

    Attributes:
        message: Human-readable error message.
        agent_name: Name of the agent that raised the error (if known).
        error_code: Optional error code for categorizing errors (e.g., INVALID_BRANCH, GIT_ERROR).
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
        message: str = "Claude CLI not found. Install: npm install -g @anthropic-ai/claude-code",
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


class TimeoutError(AgentError):
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
        """Initialize the TimeoutError.

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
    """Exception raised when attempting to register an agent with a name that already exists.

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


class WorkflowError(MaverickError):
    """Base exception for workflow-related errors.

    Attributes:
        message: Human-readable error message.
        workflow_name: Name of the workflow that failed (if known).
    """

    def __init__(self, message: str, workflow_name: str | None = None) -> None:
        """Initialize the WorkflowError.

        Args:
            message: Human-readable error message.
            workflow_name: Optional name of the workflow that failed.
        """
        self.workflow_name = workflow_name
        super().__init__(message)


class ConfigError(MaverickError):
    """Exception for configuration loading, parsing, and validation errors.

    Raised when configuration cannot be loaded, parsed, or validated. This includes
    YAML parsing failures, Pydantic validation errors, and invalid environment
    variable values.

    Attributes:
        message: Human-readable error message describing the configuration issue.
        field: Optional field name that caused the error (e.g., "api_key").
        value: Optional value that failed validation (for debugging).

    Examples:
        ```python
        # YAML parsing failure
        raise ConfigError(
            "Failed to parse maverick.yaml: invalid YAML syntax at line 10"
        )

        # Pydantic validation failure
        raise ConfigError(
            "Invalid configuration value",
            field="max_parallel_reviews",
            value=-1
        )

        # Invalid environment variable
        raise ConfigError(
            "Environment variable must be a valid URL",
            field="MAVERICK_API_URL",
            value="not-a-url"
        )
        ```
    """

    def __init__(
        self,
        message: str,
        field: str | None = None,
        value: Any = None,
    ) -> None:
        """Initialize the ConfigError.

        Args:
            message: Human-readable error message.
            field: Optional field name that caused the error.
            value: Optional value that failed validation.
        """
        self.field = field
        self.value = value
        super().__init__(message)
