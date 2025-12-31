"""Unit tests for TUI services module."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.tui.models import GitHubIssue
from maverick.tui.services import (
    GitHubConnectionResult,
    IssueListResult,
    NotificationResult,
    check_github_connection,
    list_github_issues,
    send_test_notification,
)

if TYPE_CHECKING:
    pass


class TestGitHubConnectionResult:
    """Tests for GitHubConnectionResult dataclass."""

    def test_successful_connection(self) -> None:
        """Test creating a successful connection result."""
        result = GitHubConnectionResult(
            connected=True,
            message="✓ Connected",
            status="success",
        )
        assert result.connected is True
        assert result.message == "✓ Connected"
        assert result.status == "success"

    def test_failed_connection(self) -> None:
        """Test creating a failed connection result."""
        result = GitHubConnectionResult(
            connected=False,
            message="✗ Authentication failed",
            status="error",
        )
        assert result.connected is False
        assert "Authentication failed" in result.message
        assert result.status == "error"

    def test_timeout_connection(self) -> None:
        """Test creating a timeout connection result."""
        result = GitHubConnectionResult(
            connected=False,
            message="✗ Connection timed out",
            status="timeout",
        )
        assert result.connected is False
        assert result.status == "timeout"


class TestNotificationResult:
    """Tests for NotificationResult dataclass."""

    def test_successful_notification(self) -> None:
        """Test creating a successful notification result."""
        result = NotificationResult(
            sent=True,
            message="✓ Test notification sent",
            status="success",
        )
        assert result.sent is True
        assert result.status == "success"

    def test_failed_notification(self) -> None:
        """Test creating a failed notification result."""
        result = NotificationResult(
            sent=False,
            message="✗ Failed to send notification",
            status="error",
        )
        assert result.sent is False
        assert result.status == "error"

    def test_disabled_notification(self) -> None:
        """Test creating a disabled notification result."""
        result = NotificationResult(
            sent=False,
            message="✗ Notifications are disabled",
            status="disabled",
        )
        assert result.sent is False
        assert result.status == "disabled"


class TestIssueListResult:
    """Tests for IssueListResult dataclass."""

    def test_successful_issue_list(self) -> None:
        """Test creating a successful issue list result."""
        issues = (
            GitHubIssue(
                number=1,
                title="Test Issue",
                labels=("bug",),
                url="https://github.com/test/repo/issues/1",
                state="open",
            ),
        )
        result = IssueListResult(
            issues=issues,
            success=True,
            error_message=None,
        )
        assert result.success is True
        assert len(result.issues) == 1
        assert result.error_message is None

    def test_failed_issue_list(self) -> None:
        """Test creating a failed issue list result."""
        result = IssueListResult(
            issues=(),
            success=False,
            error_message="Failed to fetch issues",
        )
        assert result.success is False
        assert len(result.issues) == 0
        assert result.error_message == "Failed to fetch issues"


class TestCheckGitHubConnection:
    """Tests for check_github_connection service function."""

    @pytest.mark.asyncio
    async def test_gh_cli_not_found(self) -> None:
        """Test handling when gh CLI is not installed."""
        with patch("maverick.tui.services.shutil.which", return_value=None):
            result = await check_github_connection()

        assert result.connected is False
        assert "GitHub CLI (gh) not found" in result.message
        assert result.status == "error"

    @pytest.mark.asyncio
    async def test_successful_connection(self) -> None:
        """Test successful GitHub connection."""
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.timed_out = False

        with (
            patch("maverick.tui.services.shutil.which", return_value="/usr/bin/gh"),
            patch("maverick.tui.services.CommandRunner") as mock_runner_class,
        ):
            mock_runner = MagicMock()
            mock_runner.run = AsyncMock(return_value=mock_result)
            mock_runner_class.return_value = mock_runner

            result = await check_github_connection()

        assert result.connected is True
        assert result.message == "✓ Connected"
        assert result.status == "success"

    @pytest.mark.asyncio
    async def test_auth_failure(self) -> None:
        """Test GitHub authentication failure."""
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.timed_out = False
        mock_result.stderr = "Authentication required"

        with (
            patch("maverick.tui.services.shutil.which", return_value="/usr/bin/gh"),
            patch("maverick.tui.services.CommandRunner") as mock_runner_class,
        ):
            mock_runner = MagicMock()
            mock_runner.run = AsyncMock(return_value=mock_result)
            mock_runner_class.return_value = mock_runner

            result = await check_github_connection()

        assert result.connected is False
        assert "Authentication required" in result.message
        assert result.status == "error"

    @pytest.mark.asyncio
    async def test_connection_timeout(self) -> None:
        """Test GitHub connection timeout."""
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.timed_out = True

        with (
            patch("maverick.tui.services.shutil.which", return_value="/usr/bin/gh"),
            patch("maverick.tui.services.CommandRunner") as mock_runner_class,
        ):
            mock_runner = MagicMock()
            mock_runner.run = AsyncMock(return_value=mock_result)
            mock_runner_class.return_value = mock_runner

            result = await check_github_connection()

        assert result.connected is False
        assert "timed out" in result.message
        assert result.status == "timeout"

    @pytest.mark.asyncio
    async def test_exception_handling(self) -> None:
        """Test handling of unexpected exceptions."""
        with (
            patch("maverick.tui.services.shutil.which", return_value="/usr/bin/gh"),
            patch("maverick.tui.services.CommandRunner") as mock_runner_class,
        ):
            mock_runner = MagicMock()
            mock_runner.run = AsyncMock(side_effect=Exception("Unexpected error"))
            mock_runner_class.return_value = mock_runner

            result = await check_github_connection()

        assert result.connected is False
        assert "Error" in result.message
        assert result.status == "error"


class TestSendTestNotification:
    """Tests for send_test_notification service function."""

    @pytest.mark.asyncio
    async def test_curl_not_found(self) -> None:
        """Test handling when curl is not installed."""
        with patch("maverick.tui.services.shutil.which", return_value=None):
            result = await send_test_notification(topic="test-topic")

        assert result.sent is False
        assert "curl not found" in result.message
        assert result.status == "error"

    @pytest.mark.asyncio
    async def test_successful_notification(self) -> None:
        """Test successful notification delivery."""
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.timed_out = False

        with (
            patch("maverick.tui.services.shutil.which", return_value="/usr/bin/curl"),
            patch("maverick.tui.services.CommandRunner") as mock_runner_class,
        ):
            mock_runner = MagicMock()
            mock_runner.run = AsyncMock(return_value=mock_result)
            mock_runner_class.return_value = mock_runner

            result = await send_test_notification(topic="test-topic")

        assert result.sent is True
        assert "Test notification sent" in result.message
        assert result.status == "success"

    @pytest.mark.asyncio
    async def test_notification_failure(self) -> None:
        """Test notification delivery failure."""
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.timed_out = False

        with (
            patch("maverick.tui.services.shutil.which", return_value="/usr/bin/curl"),
            patch("maverick.tui.services.CommandRunner") as mock_runner_class,
        ):
            mock_runner = MagicMock()
            mock_runner.run = AsyncMock(return_value=mock_result)
            mock_runner_class.return_value = mock_runner

            result = await send_test_notification(topic="test-topic")

        assert result.sent is False
        assert "Failed to send notification" in result.message
        assert result.status == "error"

    @pytest.mark.asyncio
    async def test_notification_timeout(self) -> None:
        """Test notification timeout."""
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.timed_out = True

        with (
            patch("maverick.tui.services.shutil.which", return_value="/usr/bin/curl"),
            patch("maverick.tui.services.CommandRunner") as mock_runner_class,
        ):
            mock_runner = MagicMock()
            mock_runner.run = AsyncMock(return_value=mock_result)
            mock_runner_class.return_value = mock_runner

            result = await send_test_notification(topic="test-topic")

        assert result.sent is False
        assert "timed out" in result.message
        assert result.status == "timeout"

    @pytest.mark.asyncio
    async def test_custom_message(self) -> None:
        """Test notification with custom message."""
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.timed_out = False

        with (
            patch("maverick.tui.services.shutil.which", return_value="/usr/bin/curl"),
            patch("maverick.tui.services.CommandRunner") as mock_runner_class,
        ):
            mock_runner = MagicMock()
            mock_runner.run = AsyncMock(return_value=mock_result)
            mock_runner_class.return_value = mock_runner

            result = await send_test_notification(
                topic="test-topic",
                message="Custom notification message",
            )

        assert result.sent is True
        # Verify the correct message was sent
        call_args = mock_runner.run.call_args[0][0]
        assert "Custom notification message" in call_args


class TestListGitHubIssues:
    """Tests for list_github_issues service function."""

    @pytest.mark.asyncio
    async def test_gh_cli_not_found(self) -> None:
        """Test handling when gh CLI is not installed."""
        with patch("maverick.tui.services.shutil.which", return_value=None):
            result = await list_github_issues(label="tech-debt")

        assert result.success is False
        assert len(result.issues) == 0
        assert "GitHub CLI (gh) not found" in result.error_message

    @pytest.mark.asyncio
    async def test_successful_issue_list(self) -> None:
        """Test successful issue listing."""
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.timed_out = False
        mock_result.stdout = """[
            {
                "number": 1,
                "title": "Test Issue",
                "labels": [{"name": "bug"}],
                "url": "https://github.com/test/repo/issues/1",
                "state": "open"
            },
            {
                "number": 2,
                "title": "Another Issue",
                "labels": [{"name": "tech-debt"}, {"name": "priority: high"}],
                "url": "https://github.com/test/repo/issues/2",
                "state": "open"
            }
        ]"""

        with (
            patch("maverick.tui.services.shutil.which", return_value="/usr/bin/gh"),
            patch("maverick.tui.services.CommandRunner") as mock_runner_class,
        ):
            mock_runner = MagicMock()
            mock_runner.run = AsyncMock(return_value=mock_result)
            mock_runner_class.return_value = mock_runner

            result = await list_github_issues(label="tech-debt")

        assert result.success is True
        assert len(result.issues) == 2
        assert result.issues[0].number == 1
        assert result.issues[0].title == "Test Issue"
        assert result.issues[0].labels == ("bug",)
        assert result.issues[1].labels == ("tech-debt", "priority: high")

    @pytest.mark.asyncio
    async def test_empty_issue_list(self) -> None:
        """Test handling empty issue list."""
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.timed_out = False
        mock_result.stdout = "[]"

        with (
            patch("maverick.tui.services.shutil.which", return_value="/usr/bin/gh"),
            patch("maverick.tui.services.CommandRunner") as mock_runner_class,
        ):
            mock_runner = MagicMock()
            mock_runner.run = AsyncMock(return_value=mock_result)
            mock_runner_class.return_value = mock_runner

            result = await list_github_issues(label="nonexistent")

        assert result.success is True
        assert len(result.issues) == 0
        assert result.error_message is None

    @pytest.mark.asyncio
    async def test_gh_cli_error(self) -> None:
        """Test handling gh CLI error."""
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.timed_out = False
        mock_result.stderr = "Repository not found"

        with (
            patch("maverick.tui.services.shutil.which", return_value="/usr/bin/gh"),
            patch("maverick.tui.services.CommandRunner") as mock_runner_class,
        ):
            mock_runner = MagicMock()
            mock_runner.run = AsyncMock(return_value=mock_result)
            mock_runner_class.return_value = mock_runner

            result = await list_github_issues(label="tech-debt")

        assert result.success is False
        assert len(result.issues) == 0
        assert "Repository not found" in result.error_message

    @pytest.mark.asyncio
    async def test_timeout(self) -> None:
        """Test handling timeout."""
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.timed_out = True

        with (
            patch("maverick.tui.services.shutil.which", return_value="/usr/bin/gh"),
            patch("maverick.tui.services.CommandRunner") as mock_runner_class,
        ):
            mock_runner = MagicMock()
            mock_runner.run = AsyncMock(return_value=mock_result)
            mock_runner_class.return_value = mock_runner

            result = await list_github_issues(label="tech-debt")

        assert result.success is False
        assert "timed out" in result.error_message

    @pytest.mark.asyncio
    async def test_json_parse_error(self) -> None:
        """Test handling JSON parse error."""
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.timed_out = False
        mock_result.stdout = "not valid json"

        with (
            patch("maverick.tui.services.shutil.which", return_value="/usr/bin/gh"),
            patch("maverick.tui.services.CommandRunner") as mock_runner_class,
        ):
            mock_runner = MagicMock()
            mock_runner.run = AsyncMock(return_value=mock_result)
            mock_runner_class.return_value = mock_runner

            result = await list_github_issues(label="tech-debt")

        assert result.success is False
        assert "Failed to parse issue data" in result.error_message

    @pytest.mark.asyncio
    async def test_custom_limit(self) -> None:
        """Test using custom limit parameter."""
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.timed_out = False
        mock_result.stdout = "[]"

        with (
            patch("maverick.tui.services.shutil.which", return_value="/usr/bin/gh"),
            patch("maverick.tui.services.CommandRunner") as mock_runner_class,
        ):
            mock_runner = MagicMock()
            mock_runner.run = AsyncMock(return_value=mock_result)
            mock_runner_class.return_value = mock_runner

            await list_github_issues(label="tech-debt", limit=100)

        # Verify the correct limit was passed
        call_args = mock_runner.run.call_args[0][0]
        assert "--limit" in call_args
        limit_index = call_args.index("--limit")
        assert call_args[limit_index + 1] == "100"
