"""Integration tests for GitHub CLI mock fixtures.

This module verifies that the mock_github_cli fixture works correctly
in real test scenarios.
"""

from __future__ import annotations

from tests.fixtures.github import CommandCall, CommandResponse, MockGitHubCLI


def test_mock_github_cli_fixture_available(mock_github_cli: MockGitHubCLI) -> None:
    """Test that mock_github_cli fixture is available."""
    assert isinstance(mock_github_cli, MockGitHubCLI)
    assert len(mock_github_cli.get_calls()) == 0


def test_mock_github_cli_set_response(mock_github_cli: MockGitHubCLI) -> None:
    """Test setting and retrieving command responses."""
    # Configure a response
    mock_github_cli.set_response(
        "pr create", CommandResponse(returncode=0, stdout='{"number": 42}')
    )

    # Execute the command
    response = mock_github_cli.execute(["pr", "create", "--title", "Test PR"])

    # Verify the response
    assert response.returncode == 0
    assert response.stdout == '{"number": 42}'
    assert response.stderr == ""


def test_mock_github_cli_call_recording(mock_github_cli: MockGitHubCLI) -> None:
    """Test that command calls are recorded correctly."""
    # Execute multiple commands
    mock_github_cli.execute(["pr", "create", "--title", "Test"])
    mock_github_cli.execute(["issue", "list"])
    mock_github_cli.execute(["pr", "list"])

    # Verify all calls recorded
    all_calls = mock_github_cli.get_calls()
    assert len(all_calls) == 3

    # Verify filtered calls
    pr_calls = mock_github_cli.get_calls("pr")
    assert len(pr_calls) == 2
    assert pr_calls[0].args == ["pr", "create", "--title", "Test"]
    assert pr_calls[1].args == ["pr", "list"]

    issue_calls = mock_github_cli.get_calls("issue")
    assert len(issue_calls) == 1
    assert issue_calls[0].args == ["issue", "list"]


def test_mock_github_cli_pattern_matching(mock_github_cli: MockGitHubCLI) -> None:
    """Test command pattern matching (exact and substring)."""
    # Configure responses with different patterns
    mock_github_cli.set_response(
        "pr create", CommandResponse(returncode=0, stdout="pr created")
    )
    mock_github_cli.set_response(
        "pr list", CommandResponse(returncode=0, stdout="pr list")
    )

    # Test exact match
    response1 = mock_github_cli.execute(["pr", "create"])
    assert response1.stdout == "pr created"

    # Test substring match
    response2 = mock_github_cli.execute(["pr", "create", "--title", "Test"])
    assert response2.stdout == "pr created"

    # Test different pattern
    response3 = mock_github_cli.execute(["pr", "list"])
    assert response3.stdout == "pr list"


def test_mock_github_cli_default_response(mock_github_cli: MockGitHubCLI) -> None:
    """Test default response when no pattern matches."""
    # Execute command without configuring response
    response = mock_github_cli.execute(["unknown", "command"])

    # Should return default success response
    assert response.returncode == 0
    assert response.stdout == ""
    assert response.stderr == ""


def test_mock_github_cli_reset(mock_github_cli: MockGitHubCLI) -> None:
    """Test that reset clears all state."""
    # Configure response and execute command
    mock_github_cli.set_response(
        "pr create", CommandResponse(returncode=0, stdout="created")
    )
    mock_github_cli.execute(["pr", "create"])

    # Reset
    mock_github_cli.reset()

    # Verify state is cleared
    assert len(mock_github_cli.get_calls()) == 0
    response = mock_github_cli.execute(["pr", "create"])
    assert response.stdout == ""  # No longer matches pattern


def test_command_response_defaults() -> None:
    """Test CommandResponse default values."""
    response = CommandResponse()
    assert response.returncode == 0
    assert response.stdout == ""
    assert response.stderr == ""


def test_command_response_custom_values() -> None:
    """Test CommandResponse with custom values."""
    response = CommandResponse(returncode=1, stdout="output", stderr="error message")
    assert response.returncode == 1
    assert response.stdout == "output"
    assert response.stderr == "error message"


def test_command_call_attributes() -> None:
    """Test CommandCall attributes."""
    from datetime import datetime

    now = datetime.now()
    call = CommandCall(args=["pr", "create"], timestamp=now)

    assert call.args == ["pr", "create"]
    assert call.timestamp == now
