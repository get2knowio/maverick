from __future__ import annotations

from maverick.exceptions.agent import AgentError


class MaverickValidationError(AgentError):
    """Exception for validation failures (format, lint, test).

    Named MaverickValidationError to avoid conflict with Pydantic's ValidationError.
    Raised when code validation steps fail, such as formatting, linting, or testing.

    Attributes:
        message: Human-readable error message.
        step: Validation step that failed (e.g., "lint", "test").
        output: Command output.
    """

    def __init__(
        self,
        message: str,
        step: str | None = None,
        output: str | None = None,
    ) -> None:
        """Initialize the MaverickValidationError.

        Args:
            message: Human-readable error message.
            step: Validation step that failed.
            output: Command output.
        """
        self.step = step
        self.output = output
        super().__init__(message)


class NotificationToolsError(AgentError):
    """Exception for notification MCP tools initialization failures.

    Raised when the notification tools MCP server cannot be created.

    Attributes:
        message: Human-readable error message.
        check_failed: The specific check that failed.
    """

    def __init__(
        self,
        message: str,
        check_failed: str | None = None,
    ) -> None:
        """Initialize the NotificationToolsError.

        Args:
            message: Human-readable error message.
            check_failed: The specific check that failed.
        """
        self.check_failed = check_failed
        super().__init__(message)


class ValidationToolsError(AgentError):
    """Exception for validation MCP tools initialization failures.

    Raised when the validation tools MCP server cannot be created.

    Attributes:
        message: Human-readable error message.
        check_failed: The specific check that failed.
    """

    def __init__(
        self,
        message: str,
        check_failed: str | None = None,
    ) -> None:
        """Initialize the ValidationToolsError.

        Args:
            message: Human-readable error message.
            check_failed: The specific check that failed.
        """
        self.check_failed = check_failed
        super().__init__(message)
