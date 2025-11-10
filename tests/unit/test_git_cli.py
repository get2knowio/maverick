"""Unit tests for git CLI helpers.

Tests the tolerant git command runner and branch name validator
with success, failure, and invalid branch scenarios.
"""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from src.utils.git_cli import GitCommandError, run_git_command, validate_branch_name


class TestValidateBranchName:
    """Tests for branch name validation."""

    def test_valid_simple_branch_name(self):
        """Valid simple branch name should pass."""
        validate_branch_name("main")
        validate_branch_name("feature")
        validate_branch_name("develop")

    def test_valid_branch_name_with_slashes(self):
        """Valid branch name with slashes should pass."""
        validate_branch_name("feature/new-feature")
        validate_branch_name("bugfix/fix-123")
        validate_branch_name("001-task-branch-switch")

    def test_valid_branch_name_with_dots_and_dashes(self):
        """Valid branch name with dots and dashes should pass."""
        validate_branch_name("v1.0.0")
        validate_branch_name("release-2024")
        validate_branch_name("hotfix_urgent")

    def test_invalid_branch_name_with_spaces(self):
        """Branch name with spaces should fail."""
        with pytest.raises(ValueError, match="Invalid git branch name"):
            validate_branch_name("feature branch")

    def test_invalid_branch_name_with_special_chars(self):
        """Branch name with special characters should fail."""
        with pytest.raises(ValueError, match="Invalid git branch name"):
            validate_branch_name("feature@branch")
        with pytest.raises(ValueError, match="Invalid git branch name"):
            validate_branch_name("feature#branch")
        with pytest.raises(ValueError, match="Invalid git branch name"):
            validate_branch_name("feature$branch")

    def test_invalid_empty_branch_name(self):
        """Empty branch name should fail."""
        with pytest.raises(ValueError, match="Invalid git branch name"):
            validate_branch_name("")

    def test_invalid_branch_name_with_only_whitespace(self):
        """Branch name with only whitespace should fail."""
        with pytest.raises(ValueError, match="Invalid git branch name"):
            validate_branch_name("   ")


class TestRunGitCommand:
    """Tests for git command runner."""

    @patch("subprocess.run")
    def test_successful_git_command(self, mock_run):
        """Successful git command should return output."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=b"* main\n  feature/test\n",
            stderr=b"",
        )

        result = run_git_command(["branch"])

        assert result.success is True
        assert result.stdout == "* main\n  feature/test\n"
        assert result.stderr == ""
        assert result.returncode == 0
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_failed_git_command(self, mock_run):
        """Failed git command should return error details."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout=b"",
            stderr=b"fatal: not a git repository\n",
        )

        result = run_git_command(["status"])

        assert result.success is False
        assert result.stdout == ""
        assert result.stderr == "fatal: not a git repository\n"
        assert result.returncode == 1

    @patch("subprocess.run")
    def test_git_command_with_non_utf8_output(self, mock_run):
        """Git command with non-UTF-8 output should decode tolerantly."""
        # Simulate invalid UTF-8 bytes
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=b"file: \xff\xfe invalid bytes\n",
            stderr=b"",
        )

        result = run_git_command(["log"])

        # Should not crash, should use replacement character
        assert result.success is True
        assert "file:" in result.stdout
        # The invalid bytes should be replaced, not crash
        assert isinstance(result.stdout, str)

    @patch("subprocess.run")
    def test_git_command_with_timeout(self, mock_run):
        """Git command timeout should raise GitCommandError."""
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd=["git", "fetch"], timeout=30
        )

        with pytest.raises(GitCommandError, match="Git command timed out"):
            run_git_command(["fetch"], timeout=30)

    @patch("subprocess.run")
    def test_git_command_with_os_error(self, mock_run):
        """Git command OS error should raise GitCommandError."""
        mock_run.side_effect = OSError("git executable not found")

        with pytest.raises(GitCommandError, match="Git command failed"):
            run_git_command(["status"])

    @patch("subprocess.run")
    def test_git_command_with_cwd(self, mock_run):
        """Git command should use specified working directory."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=b"output\n",
            stderr=b"",
        )

        run_git_command(["status"], cwd="/tmp/repo")

        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["cwd"] == "/tmp/repo"

    @patch("subprocess.run")
    def test_git_command_captures_both_streams(self, mock_run):
        """Git command should capture both stdout and stderr."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=b"stdout text\n",
            stderr=b"stderr text\n",
        )

        result = run_git_command(["status"])

        assert result.stdout == "stdout text\n"
        assert result.stderr == "stderr text\n"

    @patch("subprocess.run")
    def test_git_command_error_with_retry_hint(self, mock_run):
        """Failed git command should include retry hint for transient errors."""
        mock_run.return_value = MagicMock(
            returncode=128,
            stdout=b"",
            stderr=b"fatal: unable to access: Connection timed out\n",
        )

        result = run_git_command(["fetch"])

        assert result.success is False
        assert result.returncode == 128
        assert result.error_code is not None
        assert result.retry_hint is not None

    @patch("subprocess.run")
    def test_git_command_error_without_retry_hint(self, mock_run):
        """Failed git command with permanent error should not suggest retry."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout=b"",
            stderr=b"error: pathspec 'invalid' did not match any file(s)\n",
        )

        result = run_git_command(["checkout", "invalid"])

        assert result.success is False
        assert result.returncode == 1
        # Permanent errors should not suggest retry
        if result.retry_hint:
            assert result.retry_hint is False
