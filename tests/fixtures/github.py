"""Mock fixtures for GitHub CLI testing.

This module provides mock implementations of GitHub CLI (gh) command execution
for testing GitHub integrations without real API calls.

Provides:
- CommandResponse: Simulates the result of a gh command execution
- CommandCall: Records details of a gh command invocation
- MockGitHubCLI: Mock GitHub CLI with configurable responses
- mock_github_cli fixture for easy test integration
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from time import time_ns

import pytest


@dataclass
class CommandResponse:
    """Represents the result of a GitHub CLI command execution.

    Simulates the return code, stdout, and stderr of a gh command.

    Args:
        returncode: Exit code (0 for success, non-zero for failure)
        stdout: Standard output from the command
        stderr: Standard error from the command

    Example:
        >>> success = CommandResponse(returncode=0, stdout='{"number": 123}')
        >>> failure = CommandResponse(returncode=1, stderr="Error: not found")
    """

    returncode: int = 0
    stdout: str = ""
    stderr: str = ""


@dataclass
class CommandCall:
    """Records details of a GitHub CLI command invocation.

    Captures the arguments and timestamp of a gh command execution
    for test verification.

    Args:
        args: Command arguments passed to gh
        timestamp: When the command was executed

    Example:
        >>> call = CommandCall(
        ...     args=["pr", "create", "--title", "Test"],
        ...     timestamp=datetime.now()
        ... )
    """

    args: list[str]
    timestamp: datetime


@dataclass
class MockGitHubCLI:
    """Mock GitHub CLI with configurable command responses.

    Simulates the GitHub CLI (gh) command execution. Maintains a mapping
    of command patterns to responses and records all command invocations
    for test verification.

    Attributes:
        _command_responses: Mapping of command patterns to responses
        _call_history: Record of all commands executed

    Example:
        >>> cli = MockGitHubCLI()
        >>> cli.set_response(
        ...     "pr create",
        ...     CommandResponse(returncode=0, stdout='{"number": 123}')
        ... )
        >>> response = cli.execute(["pr", "create", "--title", "Test PR"])
        >>> assert response.returncode == 0
        >>> assert len(cli.get_calls()) == 1
    """

    _command_responses: dict[str, CommandResponse] = field(default_factory=dict)
    _call_history: list[CommandCall] = field(default_factory=list)

    def set_response(self, pattern: str, response: CommandResponse) -> None:
        """Configure a response for a command pattern.

        The pattern matching is simple: it checks for exact match first,
        then falls back to a substring match.

        Args:
            pattern: Command pattern to match (e.g., "pr create" or "issue list")
            response: CommandResponse to return when pattern matches

        Example:
            >>> cli = MockGitHubCLI()
            >>> cli.set_response(
            ...     "pr create",
            ...     CommandResponse(returncode=0, stdout='{"number": 42}')
            ... )
            >>> cli.set_response(
            ...     "pr list",
            ...     CommandResponse(returncode=0, stdout='[]')
            ... )
        """
        self._command_responses[pattern] = response

    def execute(self, args: list[str]) -> CommandResponse:
        """Simulate GitHub CLI command execution.

        Records the command invocation and returns the configured response
        for matching patterns. If no pattern matches, returns a default
        success response.

        Args:
            args: Command arguments (e.g., ["pr", "create", "--title", "Test"])

        Returns:
            CommandResponse configured for the matching pattern, or default success

        Example:
            >>> cli = MockGitHubCLI()
            >>> cli.set_response(
            ...     "pr create",
            ...     CommandResponse(returncode=0, stdout='{"number": 123}')
            ... )
            >>> response = cli.execute(["pr", "create", "--title", "Test"])
            >>> assert response.stdout == '{"number": 123}'
        """
        # Record the call with efficient nanosecond-precision timestamp
        # Converted to datetime for API compatibility
        timestamp = datetime.fromtimestamp(time_ns() / 1e9, tz=UTC)
        call = CommandCall(args=args, timestamp=timestamp)
        self._call_history.append(call)

        # Convert args to string for pattern matching
        command_str = " ".join(args)

        # First try exact match
        if command_str in self._command_responses:
            return self._command_responses[command_str]

        # Then try substring match (contains check)
        for pattern, response in self._command_responses.items():
            if pattern in command_str:
                return response

        # Default to success if no match
        return CommandResponse(returncode=0, stdout="", stderr="")

    def get_calls(self, pattern: str | None = None) -> list[CommandCall]:
        """Get recorded command calls, optionally filtered by pattern.

        Args:
            pattern: Optional pattern to filter calls
                (checks if pattern is in command string)

        Returns:
            List of CommandCall objects matching the filter (or all if no filter)

        Example:
            >>> cli = MockGitHubCLI()
            >>> cli.execute(["pr", "create", "--title", "Test"])
            >>> cli.execute(["issue", "list"])
            >>> pr_calls = cli.get_calls("pr")
            >>> assert len(pr_calls) == 1
            >>> all_calls = cli.get_calls()
            >>> assert len(all_calls) == 2
        """
        if pattern is None:
            return self._call_history.copy()

        filtered_calls = []
        for call in self._call_history:
            command_str = " ".join(call.args)
            if pattern in command_str:
                filtered_calls.append(call)

        return filtered_calls

    def reset(self) -> None:
        """Clear all state for test isolation.

        Removes all configured responses and clears the call history.

        Example:
            >>> cli = MockGitHubCLI()
            >>> cli.set_response("pr create", CommandResponse(returncode=0))
            >>> cli.execute(["pr", "create"])
            >>> cli.reset()
            >>> assert len(cli.get_calls()) == 0
        """
        self._command_responses.clear()
        self._call_history.clear()


# =============================================================================
# Pytest Fixtures
# =============================================================================


@pytest.fixture
def mock_github_cli() -> MockGitHubCLI:
    """Fixture providing a fresh MockGitHubCLI instance.

    Returns:
        A new MockGitHubCLI for testing GitHub CLI interactions

    Example:
        >>> def test_pr_creation(mock_github_cli):
        ...     mock_github_cli.set_response(
        ...         "pr create",
        ...         CommandResponse(returncode=0, stdout='{"number": 42}')
        ...     )
        ...     response = mock_github_cli.execute(["pr", "create", "--title", "Test"])
        ...     assert response.returncode == 0
    """
    return MockGitHubCLI()
