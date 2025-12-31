"""Unit tests for GitHub utilities."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.exceptions import GitHubAuthError, GitHubError
from maverick.runners.models import GitHubIssue
from maverick.utils.github import (
    check_gh_auth,
    fetch_issue,
    list_issues,
)


class TestFetchIssue:
    """Tests for fetch_issue function."""

    @pytest.mark.asyncio
    async def test_fetch_issue_success(self) -> None:
        """Test successful issue fetch."""
        mock_issue = GitHubIssue(
            number=42,
            title="Bug: Login fails on Safari",
            body="Description here",
            labels=("bug",),
            state="open",
            url="https://github.com/owner/repo/issues/42",
            assignees=(),
        )

        mock_runner = MagicMock()
        mock_runner.get_issue = AsyncMock(return_value=mock_issue)

        with patch(
            "maverick.utils.github._get_github_runner", return_value=mock_runner
        ):
            result = await fetch_issue(42, Path("/repo"))

        assert result["number"] == 42
        assert result["title"] == "Bug: Login fails on Safari"

    @pytest.mark.asyncio
    async def test_fetch_issue_not_found_raises_error(self) -> None:
        """Test fetch_issue raises GitHubError when issue not found."""
        mock_runner = MagicMock()
        mock_runner.get_issue = AsyncMock(
            side_effect=RuntimeError("could not find issue")
        )

        with patch(
            "maverick.utils.github._get_github_runner", return_value=mock_runner
        ):
            with pytest.raises(GitHubError) as exc_info:
                await fetch_issue(999, Path("/repo"))

            assert "not found" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_fetch_issue_rate_limit_raises_error(self) -> None:
        """Test fetch_issue raises GitHubError on rate limit."""
        mock_runner = MagicMock()
        mock_runner.get_issue = AsyncMock(
            side_effect=RuntimeError("API rate limit exceeded")
        )

        with patch(
            "maverick.utils.github._get_github_runner", return_value=mock_runner
        ):
            with pytest.raises(GitHubError) as exc_info:
                await fetch_issue(42, Path("/repo"))

            assert "rate limit" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_fetch_issue_authentication_error(self) -> None:
        """Test fetch_issue raises GitHubError on authentication failure."""
        mock_runner = MagicMock()
        mock_runner.get_issue = AsyncMock(side_effect=GitHubAuthError())

        with patch(
            "maverick.utils.github._get_github_runner", return_value=mock_runner
        ):
            with pytest.raises(GitHubError) as exc_info:
                await fetch_issue(42, Path("/repo"))

            assert "authentication" in exc_info.value.message.lower()


class TestListIssues:
    """Tests for list_issues function."""

    @pytest.mark.asyncio
    async def test_list_issues_success(self) -> None:
        """Test successful issue listing."""
        mock_issues = [
            GitHubIssue(
                number=1,
                title="First",
                body="Body 1",
                labels=(),
                state="open",
                url="https://github.com/owner/repo/issues/1",
                assignees=(),
            ),
            GitHubIssue(
                number=2,
                title="Second",
                body="Body 2",
                labels=(),
                state="open",
                url="https://github.com/owner/repo/issues/2",
                assignees=(),
            ),
        ]

        mock_runner = MagicMock()
        mock_runner.list_issues = AsyncMock(return_value=mock_issues)

        with patch(
            "maverick.utils.github._get_github_runner", return_value=mock_runner
        ):
            result = await list_issues(Path("/repo"))

        assert len(result) == 2
        assert result[0]["number"] == 1
        assert result[1]["number"] == 2

    @pytest.mark.asyncio
    async def test_list_issues_empty(self) -> None:
        """Test list_issues returns empty list when no issues."""
        mock_runner = MagicMock()
        mock_runner.list_issues = AsyncMock(return_value=[])

        with patch(
            "maverick.utils.github._get_github_runner", return_value=mock_runner
        ):
            result = await list_issues(Path("/repo"))

        assert result == []

    @pytest.mark.asyncio
    async def test_list_issues_with_state_filter(self) -> None:
        """Test list_issues applies state filter."""
        mock_runner = MagicMock()
        mock_runner.list_issues = AsyncMock(return_value=[])

        with patch(
            "maverick.utils.github._get_github_runner", return_value=mock_runner
        ):
            await list_issues(Path("/repo"), state="closed")

            mock_runner.list_issues.assert_called_once()
            call_kwargs = mock_runner.list_issues.call_args[1]
            assert call_kwargs["state"] == "closed"

    @pytest.mark.asyncio
    async def test_list_issues_with_single_label_filter(self) -> None:
        """Test list_issues applies single label filter via runner."""
        mock_runner = MagicMock()
        mock_runner.list_issues = AsyncMock(return_value=[])

        with patch(
            "maverick.utils.github._get_github_runner", return_value=mock_runner
        ):
            await list_issues(Path("/repo"), labels=["bug"])

            mock_runner.list_issues.assert_called_once()
            call_kwargs = mock_runner.list_issues.call_args[1]
            assert call_kwargs["label"] == "bug"

    @pytest.mark.asyncio
    async def test_list_issues_with_multiple_labels_uses_command_runner(self) -> None:
        """Test list_issues with multiple labels uses CommandRunner directly."""
        from maverick.runners.models import CommandResult

        mock_result = CommandResult(
            returncode=0,
            stdout='[{"number": 1, "title": "Test"}]',
            stderr="",
            duration_ms=100,
            timed_out=False,
        )

        mock_cmd_runner = MagicMock()
        mock_cmd_runner.run = AsyncMock(return_value=mock_result)

        with patch(
            "maverick.utils.github._get_command_runner", return_value=mock_cmd_runner
        ):
            result = await list_issues(Path("/repo"), labels=["bug", "critical"])

            # Should use CommandRunner for multiple labels
            mock_cmd_runner.run.assert_called_once()
            call_args = mock_cmd_runner.run.call_args[0][0]
            assert "--label" in call_args
            assert "bug" in call_args
            assert "critical" in call_args
            assert len(result) == 1

    @pytest.mark.asyncio
    async def test_list_issues_with_limit(self) -> None:
        """Test list_issues applies limit."""
        mock_runner = MagicMock()
        mock_runner.list_issues = AsyncMock(return_value=[])

        with patch(
            "maverick.utils.github._get_github_runner", return_value=mock_runner
        ):
            await list_issues(Path("/repo"), limit=50)

            mock_runner.list_issues.assert_called_once()
            call_kwargs = mock_runner.list_issues.call_args[1]
            assert call_kwargs["limit"] == 50

    @pytest.mark.asyncio
    async def test_list_issues_error_raises_github_error(self) -> None:
        """Test list_issues raises GitHubError on failure."""
        mock_runner = MagicMock()
        mock_runner.list_issues = AsyncMock(
            side_effect=RuntimeError("failed to list issues")
        )

        with patch(
            "maverick.utils.github._get_github_runner", return_value=mock_runner
        ):
            with pytest.raises(GitHubError):
                await list_issues(Path("/repo"))

    @pytest.mark.asyncio
    async def test_list_issues_auth_error_raises_github_error(self) -> None:
        """Test list_issues raises GitHubError on authentication failure."""
        mock_runner = MagicMock()
        mock_runner.list_issues = AsyncMock(side_effect=GitHubAuthError())

        with patch(
            "maverick.utils.github._get_github_runner", return_value=mock_runner
        ):
            with pytest.raises(GitHubError) as exc_info:
                await list_issues(Path("/repo"))

            assert "authentication" in exc_info.value.message.lower()


class TestCheckGhAuth:
    """Tests for check_gh_auth function."""

    @pytest.mark.asyncio
    async def test_check_gh_auth_authenticated(self) -> None:
        """Test check_gh_auth returns True when authenticated."""
        from maverick.runners.models import CommandResult

        mock_result = CommandResult(
            returncode=0,
            stdout="Authenticated as user",
            stderr="",
            duration_ms=100,
            timed_out=False,
        )

        mock_cmd_runner = MagicMock()
        mock_cmd_runner.run = AsyncMock(return_value=mock_result)

        with patch(
            "maverick.utils.github._get_command_runner", return_value=mock_cmd_runner
        ):
            result = await check_gh_auth(Path("/repo"))

        assert result is True

    @pytest.mark.asyncio
    async def test_check_gh_auth_not_authenticated(self) -> None:
        """Test check_gh_auth returns False when not authenticated."""
        from maverick.runners.models import CommandResult

        mock_result = CommandResult(
            returncode=1,
            stdout="",
            stderr="not authenticated",
            duration_ms=100,
            timed_out=False,
        )

        mock_cmd_runner = MagicMock()
        mock_cmd_runner.run = AsyncMock(return_value=mock_result)

        with patch(
            "maverick.utils.github._get_command_runner", return_value=mock_cmd_runner
        ):
            result = await check_gh_auth(Path("/repo"))

        assert result is False


class TestGitHubErrorInheritance:
    """Tests for GitHubError exception behavior."""

    def test_github_error_with_issue_number(self) -> None:
        """Test GitHubError stores issue number."""
        error = GitHubError("Test error", issue_number=42)

        assert error.issue_number == 42

    def test_github_error_with_retry_after(self) -> None:
        """Test GitHubError stores retry_after."""
        error = GitHubError("Rate limited", retry_after=60)

        assert error.retry_after == 60
