from __future__ import annotations

from pathlib import Path

from maverick.exceptions.base import MaverickError


class RunnerError(MaverickError):
    """Base exception for runner failures.

    Attributes:
        message: Human-readable error message.
    """

    pass


class WorkingDirectoryError(RunnerError):
    """Working directory does not exist or is not accessible.

    Attributes:
        message: Human-readable error message.
        path: The path that was not found.
    """

    def __init__(self, message: str, path: Path | str | None = None) -> None:
        """Initialize the WorkingDirectoryError.

        Args:
            message: Human-readable error message.
            path: The path that was not found.
        """
        self.path = path
        super().__init__(message)


class CommandTimeoutError(RunnerError):
    """Command execution exceeded timeout.

    Attributes:
        message: Human-readable error message.
        timeout_seconds: The timeout that was exceeded.
        command: The command that timed out.
    """

    def __init__(
        self,
        message: str,
        timeout_seconds: float | None = None,
        command: list[str] | None = None,
    ) -> None:
        """Initialize the CommandTimeoutError.

        Args:
            message: Human-readable error message.
            timeout_seconds: The timeout value that was exceeded.
            command: The command that timed out.
        """
        self.timeout_seconds = timeout_seconds
        self.command = command
        super().__init__(message)


class CommandNotFoundError(RunnerError):
    """Executable not found in PATH.

    Attributes:
        message: Human-readable error message.
        executable: The command that was not found.
    """

    def __init__(self, message: str, executable: str | None = None) -> None:
        """Initialize the CommandNotFoundError.

        Args:
            message: Human-readable error message.
            executable: The command that was not found.
        """
        self.executable = executable
        super().__init__(message)
