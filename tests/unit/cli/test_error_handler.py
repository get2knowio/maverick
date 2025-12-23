"""Unit tests for cli_error_handler context manager."""

from __future__ import annotations

import pytest

from maverick.cli.common import cli_error_handler
from maverick.cli.context import ExitCode
from maverick.exceptions import AgentError, GitError, MaverickError


def test_cli_error_handler_keyboard_interrupt(capfd):
    """Test cli_error_handler handles KeyboardInterrupt correctly."""
    with pytest.raises(SystemExit) as exc_info, cli_error_handler():
        raise KeyboardInterrupt()

    # Should exit with INTERRUPTED code (130)
    assert exc_info.value.code == ExitCode.INTERRUPTED

    # Should print interrupted message to stderr
    captured = capfd.readouterr()
    assert "Interrupted by user" in captured.err


def test_cli_error_handler_git_error(capfd):
    """Test cli_error_handler handles GitError correctly."""
    with pytest.raises(SystemExit) as exc_info, cli_error_handler():
        raise GitError("Failed to commit", operation="commit")

    # Should exit with FAILURE code (1)
    assert exc_info.value.code == ExitCode.FAILURE

    # Should print formatted error message to stderr
    captured = capfd.readouterr()
    assert "Failed to commit" in captured.err
    assert "commit" in captured.err


def test_cli_error_handler_agent_error(capfd):
    """Test cli_error_handler handles AgentError correctly."""
    with pytest.raises(SystemExit) as exc_info, cli_error_handler():
        raise AgentError("Agent failed to execute")

    # Should exit with FAILURE code (1)
    assert exc_info.value.code == ExitCode.FAILURE

    # Should print formatted error message to stderr
    captured = capfd.readouterr()
    assert "Agent failed to execute" in captured.err


def test_cli_error_handler_maverick_error(capfd):
    """Test cli_error_handler handles MaverickError correctly."""
    with pytest.raises(SystemExit) as exc_info, cli_error_handler():
        raise MaverickError("Something went wrong")

    # Should exit with FAILURE code (1)
    assert exc_info.value.code == ExitCode.FAILURE

    # Should print formatted error message to stderr
    captured = capfd.readouterr()
    assert "Something went wrong" in captured.err


def test_cli_error_handler_generic_exception(capfd):
    """Test cli_error_handler handles generic exceptions correctly."""
    with pytest.raises(SystemExit) as exc_info, cli_error_handler():
        raise ValueError("Unexpected error")

    # Should exit with FAILURE code (1)
    assert exc_info.value.code == ExitCode.FAILURE

    # Should print error message to stderr
    captured = capfd.readouterr()
    assert "Unexpected error" in captured.err


def test_cli_error_handler_success_case():
    """Test cli_error_handler allows successful execution."""
    result = None
    with cli_error_handler():
        result = "success"

    # Should not raise any exception
    assert result == "success"
