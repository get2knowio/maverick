"""Unit tests for GitHub tools error handling.

Tests consistent error handling across all GitHub MCP tools.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from maverick.tools.github import (
    github_add_labels,
    github_close_issue,
    github_create_pr,
    github_get_issue,
    github_get_pr_diff,
    github_list_issues,
    github_pr_status,
)


class TestRateLimitErrorHandling:
    """Tests for rate limit error handling across all GitHub tools (T048)."""

    @pytest.mark.asyncio
    async def test_github_create_pr_rate_limit(self) -> None:
        """Test rate limit error handling for github_create_pr."""
        # Mock rate limit error response
        with patch(
            "maverick.tools.github.tools.prs.run_gh_command",
            new_callable=AsyncMock,
            return_value=("", "API rate limit exceeded. Retry after 120 seconds", 1),
        ):
            result = await github_create_pr.handler(
                {
                    "title": "Test PR",
                    "body": "Test body",
                    "base": "main",
                    "head": "feature",
                    "draft": False,
                }
            )

        # Verify error response structure
        assert "content" in result
        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "text"

        # Parse error data
        error_data = json.loads(result["content"][0]["text"])
        assert error_data["isError"] is True
        assert error_data["error_code"] == "RATE_LIMIT"
        assert "retry_after_seconds" in error_data
        assert error_data["retry_after_seconds"] == 120
        assert "rate limit" in error_data["message"].lower()

    @pytest.mark.asyncio
    async def test_github_list_issues_rate_limit(self) -> None:
        """Test rate limit error handling for github_list_issues."""
        # Mock rate limit error with different pattern
        with patch(
            "maverick.tools.github.tools.issues.run_gh_command",
            new_callable=AsyncMock,
            return_value=(
                "",
                "GitHub API rate limit exceeded. Wait 60s before retrying",
                1,
            ),
        ):
            result = await github_list_issues.handler(
                {
                    "label": "bug",
                    "state": "open",
                    "limit": 30,
                }
            )

        # Verify error response
        error_data = json.loads(result["content"][0]["text"])
        assert error_data["isError"] is True
        assert error_data["error_code"] == "RATE_LIMIT"
        assert error_data["retry_after_seconds"] == 60

    @pytest.mark.asyncio
    async def test_github_pr_status_rate_limit(self) -> None:
        """Test rate limit error handling for github_pr_status."""
        with patch(
            "maverick.tools.github.tools.prs.run_gh_command",
            new_callable=AsyncMock,
            return_value=("", "rate limit exceeded, retry after 90 seconds", 1),
        ):
            result = await github_pr_status.handler({"pr_number": 456})

        error_data = json.loads(result["content"][0]["text"])
        assert error_data["isError"] is True
        assert error_data["error_code"] == "RATE_LIMIT"
        assert error_data["retry_after_seconds"] == 90

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

    @pytest.mark.asyncio
    async def test_github_add_labels_rate_limit(self) -> None:
        """Test rate limit error handling for github_add_labels."""
        with patch(
            "maverick.tools.github.tools.issues.run_gh_command",
            new_callable=AsyncMock,
            return_value=("", "GitHub API rate limit. Retry after 30 seconds.", 1),
        ):
            result = await github_add_labels.handler(
                {
                    "issue_number": 100,
                    "labels": ["bug", "urgent"],
                }
            )

        error_data = json.loads(result["content"][0]["text"])
        assert error_data["isError"] is True
        assert error_data["error_code"] == "RATE_LIMIT"
        assert error_data["retry_after_seconds"] == 30

    @pytest.mark.asyncio
    async def test_github_close_issue_rate_limit(self) -> None:
        """Test rate limit error handling for github_close_issue."""
        with patch(
            "maverick.tools.github.tools.issues.run_gh_command",
            new_callable=AsyncMock,
            return_value=("", "Rate limit hit, wait 75 seconds", 1),
        ):
            result = await github_close_issue.handler(
                {
                    "issue_number": 200,
                    "comment": "Fixed!",
                }
            )

        error_data = json.loads(result["content"][0]["text"])
        assert error_data["isError"] is True
        assert error_data["error_code"] == "RATE_LIMIT"
        assert error_data["retry_after_seconds"] == 75

    @pytest.mark.asyncio
    async def test_rate_limit_error_with_numeric_pattern(self) -> None:
        """Test rate limit parsing with 'retry after N' pattern."""
        with patch(
            "maverick.tools.github.tools.prs.run_gh_command",
            new_callable=AsyncMock,
            return_value=("", "Rate limit exceeded, retry after 150", 1),
        ):
            result = await github_create_pr.handler(
                {
                    "title": "Test",
                    "body": "Body",
                    "base": "main",
                    "head": "test",
                }
            )

        error_data = json.loads(result["content"][0]["text"])
        assert error_data["error_code"] == "RATE_LIMIT"
        assert error_data["retry_after_seconds"] == 150


# =============================================================================
# T049: Network Error Handling Tests
# =============================================================================


class TestNetworkErrorHandling:
    """Tests for network error handling across all GitHub tools (T049)."""

    @pytest.mark.asyncio
    async def test_github_create_pr_network_error(self) -> None:
        """Test network error handling for github_create_pr."""
        # Mock network connection error
        with patch(
            "maverick.tools.github.tools.prs.run_gh_command",
            new_callable=AsyncMock,
            return_value=("", "network error: connection refused", 1),
        ):
            result = await github_create_pr.handler(
                {
                    "title": "Test PR",
                    "body": "Test body",
                    "base": "main",
                    "head": "feature",
                    "draft": False,
                }
            )

        error_data = json.loads(result["content"][0]["text"])
        assert error_data["isError"] is True
        assert error_data["error_code"] == "NETWORK_ERROR"
        assert "retry_after_seconds" not in error_data
        assert "network" in error_data["message"].lower()

    @pytest.mark.asyncio
    async def test_github_list_issues_network_error(self) -> None:
        """Test network error handling for github_list_issues."""
        with patch(
            "maverick.tools.github.tools.issues.run_gh_command",
            new_callable=AsyncMock,
            return_value=("", "Connection timeout - network unreachable", 1),
        ):
            result = await github_list_issues.handler({"state": "open", "limit": 10})

        error_data = json.loads(result["content"][0]["text"])
        assert error_data["isError"] is True
        assert error_data["error_code"] == "NETWORK_ERROR"
        assert "connection" in error_data["message"].lower()

    @pytest.mark.asyncio
    async def test_github_get_issue_network_error(self) -> None:
        """Test network error handling for github_get_issue."""
        with patch(
            "maverick.tools.github.tools.issues.run_gh_command",
            new_callable=AsyncMock,
            return_value=("", "Network error: unable to connect to GitHub API", 1),
        ):
            result = await github_get_issue.handler({"issue_number": 999})

        error_data = json.loads(result["content"][0]["text"])
        assert error_data["isError"] is True
        assert error_data["error_code"] == "NETWORK_ERROR"

    @pytest.mark.asyncio
    async def test_github_pr_status_network_error(self) -> None:
        """Test network error handling for github_pr_status."""
        with patch(
            "maverick.tools.github.tools.prs.run_gh_command",
            new_callable=AsyncMock,
            return_value=("", "connection failed - network down", 1),
        ):
            result = await github_pr_status.handler({"pr_number": 333})

        error_data = json.loads(result["content"][0]["text"])
        assert error_data["isError"] is True
        assert error_data["error_code"] == "NETWORK_ERROR"

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

    @pytest.mark.asyncio
    async def test_github_add_labels_network_error(self) -> None:
        """Test network error handling for github_add_labels."""
        with patch(
            "maverick.tools.github.tools.issues.run_gh_command",
            new_callable=AsyncMock,
            return_value=("", "connection error - network issue", 1),
        ):
            result = await github_add_labels.handler(
                {
                    "issue_number": 555,
                    "labels": ["test"],
                }
            )

        error_data = json.loads(result["content"][0]["text"])
        assert error_data["isError"] is True
        assert error_data["error_code"] == "NETWORK_ERROR"

    @pytest.mark.asyncio
    async def test_github_close_issue_network_error(self) -> None:
        """Test network error handling for github_close_issue."""
        with patch(
            "maverick.tools.github.tools.issues.run_gh_command",
            new_callable=AsyncMock,
            return_value=("", "Network error occurred", 1),
        ):
            result = await github_close_issue.handler({"issue_number": 666})

        error_data = json.loads(result["content"][0]["text"])
        assert error_data["isError"] is True
        assert error_data["error_code"] == "NETWORK_ERROR"

    @pytest.mark.asyncio
    async def test_network_error_includes_context(self) -> None:
        """Test network error includes stderr context."""
        error_message = "connection timeout connecting to api.github.com:443"
        with patch(
            "maverick.tools.github.tools.issues.run_gh_command",
            new_callable=AsyncMock,
            return_value=("", error_message, 1),
        ):
            result = await github_get_issue.handler({"issue_number": 789})

        error_data = json.loads(result["content"][0]["text"])
        assert error_data["error_code"] == "NETWORK_ERROR"
        # Verify original error is preserved
        assert "connection" in error_data["message"].lower()


# =============================================================================
# T050: Auth Error Handling Tests
# =============================================================================


class TestAuthErrorHandling:
    """Tests for authentication error handling across all GitHub tools (T050)."""

    @pytest.mark.asyncio
    async def test_github_create_pr_auth_error(self) -> None:
        """Test authentication error handling for github_create_pr."""
        # Mock authentication failure
        with patch(
            "maverick.tools.github.tools.prs.run_gh_command",
            new_callable=AsyncMock,
            return_value=("", "authentication required - please login", 1),
        ):
            result = await github_create_pr.handler(
                {
                    "title": "Test PR",
                    "body": "Test body",
                    "base": "main",
                    "head": "feature",
                    "draft": False,
                }
            )

        error_data = json.loads(result["content"][0]["text"])
        assert error_data["isError"] is True
        assert error_data["error_code"] == "AUTH_ERROR"
        assert "retry_after_seconds" not in error_data
        assert "gh auth login" in error_data["message"]

    @pytest.mark.asyncio
    async def test_github_list_issues_auth_error(self) -> None:
        """Test authentication error handling for github_list_issues."""
        with patch(
            "maverick.tools.github.tools.issues.run_gh_command",
            new_callable=AsyncMock,
            return_value=("", "Unauthorized - authentication failed", 1),
        ):
            result = await github_list_issues.handler({"state": "open", "limit": 20})

        error_data = json.loads(result["content"][0]["text"])
        assert error_data["isError"] is True
        assert error_data["error_code"] == "AUTH_ERROR"
        assert "gh auth login" in error_data["message"]

    @pytest.mark.asyncio
    async def test_github_get_issue_auth_error(self) -> None:
        """Test authentication error handling for github_get_issue."""
        with patch(
            "maverick.tools.github.tools.issues.run_gh_command",
            new_callable=AsyncMock,
            return_value=("", "Authentication token is invalid", 1),
        ):
            result = await github_get_issue.handler({"issue_number": 111})

        error_data = json.loads(result["content"][0]["text"])
        assert error_data["isError"] is True
        assert error_data["error_code"] == "AUTH_ERROR"
        assert "gh auth login" in error_data["message"]

    @pytest.mark.asyncio
    async def test_github_pr_status_auth_error(self) -> None:
        """Test authentication error handling for github_pr_status."""
        with patch(
            "maverick.tools.github.tools.prs.run_gh_command",
            new_callable=AsyncMock,
            return_value=("", "unauthorized access - authentication required", 1),
        ):
            result = await github_pr_status.handler({"pr_number": 222})

        error_data = json.loads(result["content"][0]["text"])
        assert error_data["isError"] is True
        assert error_data["error_code"] == "AUTH_ERROR"

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

    @pytest.mark.asyncio
    async def test_github_add_labels_auth_error(self) -> None:
        """Test authentication error handling for github_add_labels."""
        with patch(
            "maverick.tools.github.tools.issues.run_gh_command",
            new_callable=AsyncMock,
            return_value=("", "Authentication credentials are missing or invalid", 1),
        ):
            result = await github_add_labels.handler(
                {
                    "issue_number": 444,
                    "labels": ["critical"],
                }
            )

        error_data = json.loads(result["content"][0]["text"])
        assert error_data["isError"] is True
        assert error_data["error_code"] == "AUTH_ERROR"

    @pytest.mark.asyncio
    async def test_github_close_issue_auth_error(self) -> None:
        """Test authentication error handling for github_close_issue."""
        with patch(
            "maverick.tools.github.tools.issues.run_gh_command",
            new_callable=AsyncMock,
            return_value=("", "unauthorized - please authenticate with GitHub", 1),
        ):
            result = await github_close_issue.handler(
                {
                    "issue_number": 555,
                    "comment": "Done",
                }
            )

        error_data = json.loads(result["content"][0]["text"])
        assert error_data["isError"] is True
        assert error_data["error_code"] == "AUTH_ERROR"
        assert "gh auth login" in error_data["message"]

    @pytest.mark.asyncio
    async def test_auth_error_actionable_message(self) -> None:
        """Test auth error returns actionable message."""
        with patch(
            "maverick.tools.github.tools.issues.run_gh_command",
            new_callable=AsyncMock,
            return_value=("", "unauthorized: invalid credentials", 1),
        ):
            result = await github_list_issues.handler({"state": "open", "limit": 5})

        error_data = json.loads(result["content"][0]["text"])
        assert error_data["error_code"] == "AUTH_ERROR"
        # Verify message is actionable
        assert "gh auth login" in error_data["message"]
        assert len(error_data["message"]) > 10  # Not just error code


# =============================================================================
# T031-T033: github_get_pr_diff Tests
# =============================================================================


class TestErrorHandlingConsistency:
    """Tests for consistent error handling behavior across all tools."""

    @pytest.mark.asyncio
    async def test_all_tools_return_dicts_not_exceptions(self) -> None:
        """Test that tools always return MCP dicts, never raise exceptions."""
        # Mock error for all tools
        with patch(
            "maverick.tools.github.runner.run_gh_command",
            new_callable=AsyncMock,
            return_value=("", "Some error", 1),
        ):
            tools_and_args = [
                (
                    github_create_pr,
                    {"title": "T", "body": "B", "base": "m", "head": "f"},
                ),
                (github_list_issues, {"state": "open", "limit": 1}),
                (github_get_issue, {"issue_number": 1}),
                (github_pr_status, {"pr_number": 1}),
                (github_get_pr_diff, {"pr_number": 1}),
                (github_add_labels, {"issue_number": 1, "labels": ["test"]}),
                (github_close_issue, {"issue_number": 1}),
            ]

            for tool, args in tools_and_args:
                result = await tool.handler(args)
                # All tools should return dict with content key
                assert isinstance(result, dict)
                assert "content" in result
                assert isinstance(result["content"], list)
                # Parse error data - should not raise
                error_data = json.loads(result["content"][0]["text"])
                assert "error_code" in error_data or "isError" not in error_data


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
            stdout, stderr, returncode = await run_gh_command(
                "pr", "list", timeout=0.1
            )

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
    async def test_github_create_pr_timeout(self) -> None:
        """Test github_create_pr handles timeout error (lines 352-357)."""
        import asyncio

        with patch(
            "maverick.tools.github.tools.prs.run_gh_command",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.side_effect = asyncio.TimeoutError("Operation timed out")

            result = await github_create_pr.handler(
                {
                    "title": "Test PR",
                    "body": "Test body",
                    "base": "main",
                    "head": "feature",
                }
            )

        # Verify error response
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["isError"] is True
        assert response_data["error_code"] == "TIMEOUT"

    @pytest.mark.asyncio
    async def test_github_create_pr_unexpected_exception(self) -> None:
        """Test github_create_pr handles unexpected exceptions (lines 355-357)."""
        with patch(
            "maverick.tools.github.tools.prs.run_gh_command",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.side_effect = RuntimeError("Unexpected error")

            result = await github_create_pr.handler(
                {
                    "title": "Test PR",
                    "body": "Test body",
                    "base": "main",
                    "head": "feature",
                }
            )

        # Verify error response
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["isError"] is True
        assert response_data["error_code"] == "INTERNAL_ERROR"
        assert "Unexpected error" in response_data["message"]

    @pytest.mark.asyncio
    async def test_github_list_issues_json_decode_error(self) -> None:
        """Test github_list_issues handles JSON parse errors (lines 420-422)."""
        with patch(
            "maverick.tools.github.tools.issues.run_gh_command",
            new_callable=AsyncMock,
        ) as mock_run:
            # Return invalid JSON
            mock_run.return_value = ("invalid json {[", "", 0)

            result = await github_list_issues.handler({"state": "open", "limit": 10})

        # Verify error response
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["isError"] is True
        assert response_data["error_code"] == "INTERNAL_ERROR"
        assert "parse" in response_data["message"].lower()

    @pytest.mark.asyncio
    async def test_github_list_issues_timeout(self) -> None:
        """Test github_list_issues handles timeout error (lines 423-425)."""
        import asyncio

        with patch(
            "maverick.tools.github.tools.issues.run_gh_command",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.side_effect = asyncio.TimeoutError("Operation timed out")

            result = await github_list_issues.handler({"state": "open", "limit": 10})

        # Verify error response
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["isError"] is True
        assert response_data["error_code"] == "TIMEOUT"

    @pytest.mark.asyncio
    async def test_github_list_issues_unexpected_exception(self) -> None:
        """Test github_list_issues handles unexpected exceptions (lines 426-428)."""
        with patch(
            "maverick.tools.github.tools.issues.run_gh_command",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.side_effect = ValueError("Unexpected error")

            result = await github_list_issues.handler({"state": "open", "limit": 10})

        # Verify error response
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["isError"] is True
        assert response_data["error_code"] == "INTERNAL_ERROR"

    @pytest.mark.asyncio
    async def test_github_get_issue_unexpected_exception(self) -> None:
        """Test github_get_issue handles unexpected exceptions (lines 484-486)."""
        with patch(
            "maverick.tools.github.tools.issues.run_gh_command",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.side_effect = KeyError("Unexpected error")

            result = await github_get_issue.handler({"issue_number": 42})

        # Verify error response
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["isError"] is True
        assert response_data["error_code"] == "INTERNAL_ERROR"

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
        """Test github_get_pr_diff handles timeout error (lines 539-541)."""
        import asyncio

        with patch(
            "maverick.tools.github.tools.diffs.run_gh_command",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.side_effect = asyncio.TimeoutError("Operation timed out")

            result = await github_get_pr_diff.handler({"pr_number": 123})

        # Verify error response
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["isError"] is True
        assert response_data["error_code"] == "TIMEOUT"

    @pytest.mark.asyncio
    async def test_github_get_pr_diff_unexpected_exception(self) -> None:
        """Test github_get_pr_diff handles unexpected exceptions (lines 542-544)."""
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
    async def test_github_pr_status_json_decode_error(self) -> None:
        """Test github_pr_status handles JSON parse errors (lines 635-637)."""
        with patch(
            "maverick.tools.github.tools.prs.run_gh_command",
            new_callable=AsyncMock,
        ) as mock_run:
            # Return invalid JSON
            mock_run.return_value = ("invalid json {[", "", 0)

            result = await github_pr_status.handler({"pr_number": 123})

        # Verify error response
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["isError"] is True
        assert response_data["error_code"] == "INTERNAL_ERROR"
        assert "parse" in response_data["message"].lower()

    @pytest.mark.asyncio
    async def test_github_pr_status_timeout(self) -> None:
        """Test github_pr_status handles timeout error (lines 638-640)."""
        import asyncio

        with patch(
            "maverick.tools.github.tools.prs.run_gh_command",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.side_effect = asyncio.TimeoutError("Operation timed out")

            result = await github_pr_status.handler({"pr_number": 123})

        # Verify error response
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["isError"] is True
        assert response_data["error_code"] == "TIMEOUT"

    @pytest.mark.asyncio
    async def test_github_pr_status_unexpected_exception(self) -> None:
        """Test github_pr_status handles unexpected exceptions (lines 641-643)."""
        with patch(
            "maverick.tools.github.tools.prs.run_gh_command",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.side_effect = TypeError("Unexpected error")

            result = await github_pr_status.handler({"pr_number": 123})

        # Verify error response
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["isError"] is True
        assert response_data["error_code"] == "INTERNAL_ERROR"

    @pytest.mark.asyncio
    async def test_github_add_labels_timeout(self) -> None:
        """Test github_add_labels handles timeout error (lines 686-688)."""
        import asyncio

        with patch(
            "maverick.tools.github.tools.issues.run_gh_command",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.side_effect = asyncio.TimeoutError("Operation timed out")

            result = await github_add_labels.handler(
                {
                    "issue_number": 100,
                    "labels": ["bug"],
                }
            )

        # Verify error response
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["isError"] is True
        assert response_data["error_code"] == "TIMEOUT"

    @pytest.mark.asyncio
    async def test_github_add_labels_unexpected_exception(self) -> None:
        """Test github_add_labels handles unexpected exceptions (lines 689-691)."""
        with patch(
            "maverick.tools.github.tools.issues.run_gh_command",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.side_effect = OSError("Unexpected error")

            result = await github_add_labels.handler(
                {
                    "issue_number": 100,
                    "labels": ["bug"],
                }
            )

        # Verify error response
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["isError"] is True
        assert response_data["error_code"] == "INTERNAL_ERROR"


# =============================================================================
# T010: Helper Functions Tests
# =============================================================================
