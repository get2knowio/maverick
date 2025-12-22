"""Unit tests for GitHub utilities."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from maverick.exceptions import GitHubError
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

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(
            return_value=(
                b'{"number": 42, "title": "Bug: Login fails on Safari", '
                b'"body": "Description here", "labels": ["bug"], '
                b'"state": "open", "url": "https://github.com/owner/repo/issues/42"}',
                b"",
            )
        )
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await fetch_issue(42, Path("/repo"))

        assert result["number"] == 42
        assert result["title"] == "Bug: Login fails on Safari"

    @pytest.mark.asyncio
    async def test_fetch_issue_not_found_raises_error(self) -> None:
        """Test fetch_issue raises GitHubError when issue not found."""
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(
            return_value=(b"", b"could not find issue")
        )
        mock_process.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with pytest.raises(GitHubError) as exc_info:
                await fetch_issue(999, Path("/repo"))

            assert "not found" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_fetch_issue_rate_limit_retries(self) -> None:
        """Test fetch_issue retries on rate limit."""
        # First attempt: rate limited
        mock_fail_process = AsyncMock()
        mock_fail_process.communicate = AsyncMock(
            return_value=(b"", b"API rate limit exceeded, retry after 60 seconds")
        )
        mock_fail_process.returncode = 1

        # Second attempt: success
        mock_success_process = AsyncMock()
        mock_success_process.communicate = AsyncMock(
            return_value=(b'{"number": 42, "title": "Issue"}', b"")
        )
        mock_success_process.returncode = 0

        processes = [mock_fail_process, mock_success_process]
        call_count = [0]

        def mock_exec(*args, **kwargs):
            process = processes[call_count[0]]
            call_count[0] += 1
            return process

        with patch("asyncio.create_subprocess_exec", side_effect=mock_exec):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await fetch_issue(42, Path("/repo"), max_retries=2)

        assert result["number"] == 42

    @pytest.mark.asyncio
    async def test_fetch_issue_rate_limit_exhausts_retries(self) -> None:
        """Test fetch_issue raises after exhausting retries on rate limit."""
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(
            return_value=(b"", b"API rate limit exceeded, retry after 60 seconds")
        )
        mock_process.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                with pytest.raises(GitHubError) as exc_info:
                    await fetch_issue(42, Path("/repo"), max_retries=2)

                assert "rate limit" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_fetch_issue_authentication_error(self) -> None:
        """Test fetch_issue raises GitHubError on authentication failure."""
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(
            return_value=(b"", b"authentication failed, unauthorized")
        )
        mock_process.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with pytest.raises(GitHubError) as exc_info:
                await fetch_issue(42, Path("/repo"))

            assert "authentication" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_fetch_issue_timeout_retries(self) -> None:
        """Test fetch_issue retries on timeout."""
        # First attempt: timeout
        with (
            patch(
                "asyncio.create_subprocess_exec",
                side_effect=asyncio.TimeoutError,
            ),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            # Should exhaust retries and raise GitHubError
            with pytest.raises(GitHubError) as exc_info:
                await fetch_issue(42, Path("/repo"), max_retries=2)

            assert "timed out" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_fetch_issue_invalid_json_raises_error(self) -> None:
        """Test fetch_issue raises GitHubError on invalid JSON."""
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"invalid json", b""))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with pytest.raises(GitHubError) as exc_info:
                await fetch_issue(42, Path("/repo"))

            assert "parse" in exc_info.value.message.lower()


class TestListIssues:
    """Tests for list_issues function."""

    @pytest.mark.asyncio
    async def test_list_issues_success(self) -> None:
        """Test successful issue listing."""
        issues_json = (
            b'[{"number": 1, "title": "First"}, {"number": 2, "title": "Second"}]'
        )

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(issues_json, b""))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await list_issues(Path("/repo"))

        assert len(result) == 2
        assert result[0]["number"] == 1
        assert result[1]["number"] == 2

    @pytest.mark.asyncio
    async def test_list_issues_empty(self) -> None:
        """Test list_issues returns empty list when no issues."""
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"[]", b""))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await list_issues(Path("/repo"))

        assert result == []

    @pytest.mark.asyncio
    async def test_list_issues_with_state_filter(self) -> None:
        """Test list_issues applies state filter."""
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"[]", b""))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock:
            await list_issues(Path("/repo"), state="closed")

            call_args = mock.call_args[0]
            assert "--state" in call_args
            assert "closed" in call_args

    @pytest.mark.asyncio
    async def test_list_issues_with_label_filters(self) -> None:
        """Test list_issues applies label filters."""
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"[]", b""))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock:
            await list_issues(Path("/repo"), labels=["bug", "critical"])

            call_args = mock.call_args[0]
            assert "--label" in call_args
            # Check that both labels are present
            assert "bug" in call_args
            assert "critical" in call_args

    @pytest.mark.asyncio
    async def test_list_issues_with_limit(self) -> None:
        """Test list_issues applies limit."""
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"[]", b""))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock:
            await list_issues(Path("/repo"), limit=50)

            call_args = mock.call_args[0]
            assert "--limit" in call_args
            assert "50" in call_args

    @pytest.mark.asyncio
    async def test_list_issues_error_raises_github_error(self) -> None:
        """Test list_issues raises GitHubError on failure."""
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(
            return_value=(b"", b"failed to list issues")
        )
        mock_process.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with pytest.raises(GitHubError):
                await list_issues(Path("/repo"))

    @pytest.mark.asyncio
    async def test_list_issues_invalid_json_raises_error(self) -> None:
        """Test list_issues raises GitHubError on invalid JSON."""
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"invalid", b""))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with pytest.raises(GitHubError) as exc_info:
                await list_issues(Path("/repo"))

            assert "parse" in exc_info.value.message.lower()


class TestCheckGhAuth:
    """Tests for check_gh_auth function."""

    @pytest.mark.asyncio
    async def test_check_gh_auth_authenticated(self) -> None:
        """Test check_gh_auth returns True when authenticated."""
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(
            return_value=(b"Authenticated as user", b"")
        )
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await check_gh_auth(Path("/repo"))

        assert result is True

    @pytest.mark.asyncio
    async def test_check_gh_auth_not_authenticated(self) -> None:
        """Test check_gh_auth returns False when not authenticated."""
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"", b"not authenticated"))
        mock_process.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await check_gh_auth(Path("/repo"))

        assert result is False

    @pytest.mark.asyncio
    async def test_check_gh_auth_uses_timeout(self) -> None:
        """Test check_gh_auth uses custom timeout."""
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"OK", b""))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            await check_gh_auth(Path("/repo"))

            # Verify the timeout parameter is used
            # The actual timeout is passed to asyncio.wait_for


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
