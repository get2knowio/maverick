"""Unit tests for GitHub tools error handling.

Tests consistent error handling across all GitHub MCP tools.
After migration to PyGithub, most tools use GitHubClient while
github_get_pr_diff still uses run_gh_command.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.tools.github import (
    github_add_labels,
    github_close_issue,
    github_get_issue,
    github_get_pr_diff,
    github_list_issues,
)


class TestRateLimitErrorHandling:
    """Tests for rate limit error handling for github_get_pr_diff (T048).

    Note: Most tools now use PyGithub which handles rate limits via exceptions.
    github_get_pr_diff still uses run_gh_command.
    """

    @pytest.mark.asyncio
    async def test_github_get_pr_diff_rate_limit(self) -> None:
        """Test rate limit error handling for github_get_pr_diff."""
        with patch(
            "maverick.tools.github.tools.diffs.run_gh_command",
            new_callable=AsyncMock,
            return_value=("", "Rate limit exceeded. Try again in 45 seconds", 1),
        ):
            result = await github_get_pr_diff.handler({"pr_number": 789})

        error_data = json.loads(result["content"][0]["text"])
        assert error_data["isError"] is True
        assert error_data["error_code"] == "RATE_LIMIT"
        assert error_data["retry_after_seconds"] == 45


class TestNetworkErrorHandling:
    """Tests for network error handling for github_get_pr_diff (T049).

    Note: Most tools now use PyGithub. github_get_pr_diff still uses run_gh_command.
    """

    @pytest.mark.asyncio
    async def test_github_get_pr_diff_network_error(self) -> None:
        """Test network error handling for github_get_pr_diff."""
        with patch(
            "maverick.tools.github.tools.diffs.run_gh_command",
            new_callable=AsyncMock,
            return_value=("", "Network unreachable: cannot connect", 1),
        ):
            result = await github_get_pr_diff.handler({"pr_number": 444})

        error_data = json.loads(result["content"][0]["text"])
        assert error_data["isError"] is True
        assert error_data["error_code"] == "NETWORK_ERROR"


class TestAuthErrorHandling:
    """Tests for authentication error handling for github_get_pr_diff (T050).

    Note: Most tools now use PyGithub. github_get_pr_diff still uses run_gh_command.
    """

    @pytest.mark.asyncio
    async def test_github_get_pr_diff_auth_error(self) -> None:
        """Test authentication error handling for github_get_pr_diff."""
        with patch(
            "maverick.tools.github.tools.diffs.run_gh_command",
            new_callable=AsyncMock,
            return_value=("", "GitHub API: unauthorized", 1),
        ):
            result = await github_get_pr_diff.handler({"pr_number": 333})

        error_data = json.loads(result["content"][0]["text"])
        assert error_data["isError"] is True
        assert error_data["error_code"] == "AUTH_ERROR"


class TestPyGithubErrorHandling:
    """Tests for error handling in PyGithub-based tools."""

    @pytest.mark.asyncio
    async def test_github_list_issues_auth_error(self) -> None:
        """Test GitHubAuthError handling for github_list_issues."""
        from maverick.exceptions import GitHubAuthError

        with (
            patch(
                "maverick.tools.github.tools.issues._get_client",
                side_effect=GitHubAuthError("Not authenticated"),
            ),
        ):
            result = await github_list_issues.handler(
                {"state": "open", "limit": 10, "label": "bug"}
            )

        error_data = json.loads(result["content"][0]["text"])
        assert error_data["isError"] is True
        assert error_data["error_code"] == "AUTH_ERROR"

    @pytest.mark.asyncio
    async def test_github_get_issue_not_found(self) -> None:
        """Test 404 handling for github_get_issue."""
        from maverick.exceptions import GitHubError

        mock_client = MagicMock()
        with (
            patch(
                "maverick.tools.github.tools.issues._get_client",
                return_value=mock_client,
            ),
            patch(
                "maverick.tools.github.tools.issues._get_repo_name_async",
                new=AsyncMock(return_value="owner/repo"),
            ),
        ):
            mock_client.get_issue = AsyncMock(
                side_effect=GitHubError("Issue not found")
            )
            result = await github_get_issue.handler({"issue_number": 999})

        error_data = json.loads(result["content"][0]["text"])
        assert error_data["isError"] is True
        assert error_data["error_code"] == "NOT_FOUND"

    @pytest.mark.asyncio
    async def test_github_add_labels_exception(self) -> None:
        """Test GithubException handling for github_add_labels."""
        from github import GithubException

        mock_client = MagicMock()
        mock_client.github = MagicMock()
        mock_repo = MagicMock()
        mock_issue = MagicMock()
        mock_client.github.get_repo.return_value = mock_repo
        mock_repo.get_issue.return_value = mock_issue
        mock_issue.add_to_labels.side_effect = GithubException(
            403, {"message": "Forbidden"}, None
        )

        with (
            patch(
                "maverick.tools.github.tools.issues._get_client",
                return_value=mock_client,
            ),
            patch(
                "maverick.tools.github.tools.issues._get_repo_name_async",
                new=AsyncMock(return_value="owner/repo"),
            ),
        ):
            result = await github_add_labels.handler(
                {"issue_number": 100, "labels": ["bug"]}
            )

        error_data = json.loads(result["content"][0]["text"])
        assert error_data["isError"] is True
        assert error_data["error_code"] == "INTERNAL_ERROR"

    @pytest.mark.asyncio
    async def test_github_close_issue_not_found(self) -> None:
        """Test 404 handling for github_close_issue."""
        from github import GithubException

        mock_client = MagicMock()
        mock_client.github = MagicMock()
        mock_repo = MagicMock()
        mock_client.github.get_repo.return_value = mock_repo
        mock_repo.get_issue.side_effect = GithubException(
            404, {"message": "Not Found"}, None
        )

        with (
            patch(
                "maverick.tools.github.tools.issues._get_client",
                return_value=mock_client,
            ),
            patch(
                "maverick.tools.github.tools.issues._get_repo_name_async",
                new=AsyncMock(return_value="owner/repo"),
            ),
        ):
            result = await github_close_issue.handler({"issue_number": 999})

        error_data = json.loads(result["content"][0]["text"])
        assert error_data["isError"] is True
        assert error_data["error_code"] == "NOT_FOUND"


class TestErrorHandlingConsistency:
    """Tests for consistent error handling behavior across all tools."""

    @pytest.mark.asyncio
    async def test_all_tools_return_dicts_on_validation_errors(self) -> None:
        """Test that tools return MCP dicts for validation errors."""
        # Test invalid inputs for each tool
        tools_and_invalid_args = [
            (github_list_issues, {"state": "invalid", "limit": 10}),
            (github_get_issue, {"issue_number": -1}),
            (github_get_pr_diff, {"pr_number": 123, "max_size": 0}),
            (github_add_labels, {"issue_number": 1, "labels": []}),
            (github_close_issue, {"issue_number": 0}),
        ]

        for tool, args in tools_and_invalid_args:
            result = await tool.handler(args)
            # All tools should return dict with content key
            assert isinstance(result, dict)
            assert "content" in result
            assert isinstance(result["content"], list)
            # Parse response - should not raise
            response_data = json.loads(result["content"][0]["text"])
            assert "error_code" in response_data
            assert response_data["isError"] is True


# =============================================================================
# Timeout and Exception Handling Tests
# =============================================================================


class TestTimeoutAndExceptionHandling:
    """Tests for timeout and exception handling in _run_gh_command and tools."""

    @pytest.mark.asyncio
    async def test_run_gh_command_timeout(self) -> None:
        """Test run_gh_command handles timeout correctly.

        run_gh_command delegates to CommandRunner, so we mock CommandRunner.run
        to return a timed-out result.
        """
        from maverick.runners.models import CommandResult
        from maverick.tools.github.runner import run_gh_command

        # Mock CommandRunner.run to return a timed-out result
        async def mock_run(cmd, **kwargs):
            return CommandResult(
                returncode=-1, stdout="", stderr="", duration_ms=30000, timed_out=True
            )

        with patch(
            "maverick.tools.github.runner.CommandRunner.run",
            side_effect=mock_run,
        ):
            stdout, stderr, returncode = await run_gh_command("pr", "list", timeout=0.1)

            # Verify timeout result is returned
            assert returncode == -1
            assert stdout == ""
            assert stderr == ""

    @pytest.mark.asyncio
    async def test_run_gh_command_success(self) -> None:
        """Test run_gh_command successful execution."""
        from maverick.runners.models import CommandResult
        from maverick.tools.github.runner import run_gh_command

        # Mock CommandRunner.run to return success
        async def mock_run(cmd, **kwargs):
            return CommandResult(
                returncode=0, stdout="output data", stderr="", duration_ms=100
            )

        with patch(
            "maverick.tools.github.runner.CommandRunner.run",
            side_effect=mock_run,
        ):
            stdout, stderr, return_code = await run_gh_command("pr", "list")

            # Verify return values
            assert stdout == "output data"
            assert stderr == ""
            assert return_code == 0

    @pytest.mark.asyncio
    async def test_run_gh_command_error_with_stderr(self) -> None:
        """Test run_gh_command with non-zero return code."""
        from maverick.runners.models import CommandResult
        from maverick.tools.github.runner import run_gh_command

        # Mock CommandRunner.run to return error
        async def mock_run(cmd, **kwargs):
            return CommandResult(
                returncode=1, stdout="", stderr="error message", duration_ms=100
            )

        with patch(
            "maverick.tools.github.runner.CommandRunner.run",
            side_effect=mock_run,
        ):
            stdout, stderr, return_code = await run_gh_command("pr", "list")

            # Verify return values
            assert stdout == ""
            assert stderr == "error message"
            assert return_code == 1

    @pytest.mark.asyncio
    async def test_run_gh_command_none_returncode(self) -> None:
        """Test run_gh_command handles returncode from CommandResult.

        Note: CommandResult always has an int returncode, so this tests
        normal behavior rather than None handling.
        """
        from maverick.runners.models import CommandResult
        from maverick.tools.github.runner import run_gh_command

        # Mock CommandRunner.run to return success with output
        async def mock_run(cmd, **kwargs):
            return CommandResult(
                returncode=0, stdout="output", stderr="", duration_ms=100
            )

        with patch(
            "maverick.tools.github.runner.CommandRunner.run",
            side_effect=mock_run,
        ):
            stdout, stderr, return_code = await run_gh_command("pr", "list")

            # Verify return_code is 0
            assert return_code == 0

    @pytest.mark.asyncio
    async def test_github_get_pr_diff_invalid_max_size(self) -> None:
        """Test github_get_pr_diff validates max_size parameter (line 503)."""
        result = await github_get_pr_diff.handler({"pr_number": 123, "max_size": 0})

        # Verify error response
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["isError"] is True
        assert response_data["error_code"] == "INVALID_INPUT"
        assert "positive" in response_data["message"].lower()

    @pytest.mark.asyncio
    async def test_github_get_pr_diff_timeout(self) -> None:
        """Test github_get_pr_diff handles timeout error."""

        with patch(
            "maverick.tools.github.tools.diffs.run_gh_command",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.side_effect = TimeoutError("Operation timed out")

            result = await github_get_pr_diff.handler({"pr_number": 123})

        # Verify error response
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["isError"] is True
        assert response_data["error_code"] == "TIMEOUT"

    @pytest.mark.asyncio
    async def test_github_get_pr_diff_unexpected_exception(self) -> None:
        """Test github_get_pr_diff handles unexpected exceptions."""
        with patch(
            "maverick.tools.github.tools.diffs.run_gh_command",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.side_effect = OSError("Unexpected error")

            result = await github_get_pr_diff.handler({"pr_number": 123})

        # Verify error response
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["isError"] is True
        assert response_data["error_code"] == "INTERNAL_ERROR"

    @pytest.mark.asyncio
    async def test_github_list_issues_unexpected_exception(self) -> None:
        """Test github_list_issues handles unexpected exceptions."""
        with patch(
            "maverick.tools.github.tools.issues._get_client",
            side_effect=RuntimeError("Unexpected error"),
        ):
            result = await github_list_issues.handler(
                {"state": "open", "limit": 10, "label": "bug"}
            )

        # Verify error response
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["isError"] is True
        assert response_data["error_code"] == "INTERNAL_ERROR"

    @pytest.mark.asyncio
    async def test_github_get_issue_unexpected_exception(self) -> None:
        """Test github_get_issue handles unexpected exceptions."""
        with patch(
            "maverick.tools.github.tools.issues._get_client",
            side_effect=KeyError("Unexpected error"),
        ):
            result = await github_get_issue.handler({"issue_number": 42})

        # Verify error response
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["isError"] is True
        assert response_data["error_code"] == "INTERNAL_ERROR"
