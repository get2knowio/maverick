"""Tests for GitHubClient using PyGithub with gh CLI authentication."""

from __future__ import annotations

import asyncio
import subprocess
import time
from unittest.mock import MagicMock, patch

import pytest

from maverick.exceptions import GitHubAuthError, GitHubCLINotFoundError, GitHubError
from maverick.utils.github_client import (
    DEFAULT_GITHUB_RATE_LIMIT,
    DEFAULT_GITHUB_RATE_PERIOD,
    GitHubClient,
    get_github_client,
    get_github_token,
)


class TestGetGitHubToken:
    """Tests for get_github_token() function."""

    def test_get_github_token_success(self):
        """Test successful token retrieval."""
        mock_result = MagicMock()
        mock_result.stdout = "ghp_test_token_123\n"

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            token = get_github_token()

            assert token == "ghp_test_token_123"
            mock_run.assert_called_once_with(
                ["gh", "auth", "token"],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )

    def test_get_github_token_empty(self):
        """Test empty token returns raises GitHubAuthError."""
        mock_result = MagicMock()
        mock_result.stdout = ""

        with (
            patch("subprocess.run", return_value=mock_result),
            pytest.raises(GitHubAuthError),
        ):
            get_github_token()

    def test_get_github_token_gh_not_found(self):
        """Test FileNotFoundError when gh CLI is not installed."""
        with (
            patch("subprocess.run", side_effect=FileNotFoundError()),
            pytest.raises(GitHubCLINotFoundError),
        ):
            get_github_token()

    def test_get_github_token_auth_failed(self):
        """Test CalledProcessError when gh CLI auth fails."""
        error = subprocess.CalledProcessError(1, "gh", stderr="Not authenticated")
        with (
            patch("subprocess.run", side_effect=error),
            pytest.raises(GitHubAuthError),
        ):
            get_github_token()

    def test_get_github_token_timeout(self):
        """Test TimeoutExpired when gh CLI hangs."""
        error = subprocess.TimeoutExpired("gh", 10)
        with (
            patch("subprocess.run", side_effect=error),
            pytest.raises(GitHubAuthError),
        ):
            get_github_token()


class TestGetGitHubClient:
    """Tests for get_github_client() function."""

    def test_get_github_client_success(self):
        """Test successful client creation."""
        with (
            patch(
                "maverick.utils.github_client.get_github_token",
                return_value="ghp_test",
            ),
            patch("maverick.utils.github_client.Auth.Token") as mock_auth,
            patch("maverick.utils.github_client.Github") as mock_github,
        ):
            client = get_github_client()

            mock_auth.assert_called_once_with("ghp_test")
            mock_github.assert_called_once()
            assert client == mock_github.return_value


class TestGitHubClient:
    """Tests for GitHubClient class."""

    @pytest.fixture
    def mock_github(self):
        """Create a mock PyGithub client."""
        return MagicMock()

    @pytest.fixture
    def client(self, mock_github):
        """Create a GitHubClient with mocked PyGithub."""
        return GitHubClient(github=mock_github)

    def test_init_with_github_client(self, mock_github):
        """Test initialization with provided Github client."""
        client = GitHubClient(github=mock_github)
        assert client.github == mock_github

    def test_lazy_init(self):
        """Test lazy initialization of Github client."""
        with patch("maverick.utils.github_client.get_github_client") as mock_get_client:
            mock_get_client.return_value = MagicMock()
            client = GitHubClient()

            # Should not call get_github_client until accessed
            mock_get_client.assert_not_called()

            # Access github property
            _ = client.github

            mock_get_client.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_issues(self, client, mock_github):
        """Test listing issues from a repository."""
        mock_repo = MagicMock()
        mock_issues = [MagicMock(), MagicMock()]
        mock_repo.get_issues.return_value = mock_issues
        mock_github.get_repo.return_value = mock_repo

        issues = await client.list_issues("owner/repo", state="open", limit=10)

        assert len(issues) == 2
        mock_github.get_repo.assert_called_once_with("owner/repo")
        mock_repo.get_issues.assert_called_once_with(state="open")

    @pytest.mark.asyncio
    async def test_list_issues_with_labels(self, client, mock_github):
        """Test listing issues with label filter."""
        mock_repo = MagicMock()
        mock_repo.get_issues.return_value = []
        mock_github.get_repo.return_value = mock_repo

        await client.list_issues("owner/repo", labels=["bug", "priority"])

        mock_repo.get_issues.assert_called_once_with(
            state="open", labels=["bug", "priority"]
        )

    @pytest.mark.asyncio
    async def test_get_issue(self, client, mock_github):
        """Test getting a single issue."""
        mock_repo = MagicMock()
        mock_issue = MagicMock()
        mock_repo.get_issue.return_value = mock_issue
        mock_github.get_repo.return_value = mock_repo

        issue = await client.get_issue("owner/repo", 42)

        assert issue == mock_issue
        mock_repo.get_issue.assert_called_once_with(42)

    @pytest.mark.asyncio
    async def test_get_issue_not_found(self, client, mock_github):
        """Test getting a non-existent issue."""
        from github import GithubException

        mock_repo = MagicMock()
        mock_repo.get_issue.side_effect = GithubException(
            404, {"message": "Not Found"}, None
        )
        mock_github.get_repo.return_value = mock_repo

        with pytest.raises(GitHubError, match="not found"):
            await client.get_issue("owner/repo", 999)

    @pytest.mark.asyncio
    async def test_add_issue_comment(self, client, mock_github):
        """Test adding a comment to an issue."""
        mock_repo = MagicMock()
        mock_issue = MagicMock()
        mock_repo.get_issue.return_value = mock_issue
        mock_github.get_repo.return_value = mock_repo

        await client.add_issue_comment("owner/repo", 42, "Test comment")

        mock_issue.create_comment.assert_called_once_with("Test comment")

    @pytest.mark.asyncio
    async def test_create_issue(self, client, mock_github):
        """Test creating an issue."""
        mock_repo = MagicMock()
        mock_issue = MagicMock()
        mock_issue.number = 123
        mock_issue.html_url = "https://github.com/owner/repo/issues/123"
        mock_repo.create_issue.return_value = mock_issue
        mock_github.get_repo.return_value = mock_repo

        issue = await client.create_issue(
            "owner/repo",
            title="Test Issue",
            body="Issue description",
            labels=["bug", "priority"],
        )

        assert issue == mock_issue
        assert issue.number == 123
        mock_repo.create_issue.assert_called_once_with(
            title="Test Issue",
            body="Issue description",
            labels=["bug", "priority"],
        )

    @pytest.mark.asyncio
    async def test_create_issue_without_labels(self, client, mock_github):
        """Test creating an issue without labels."""
        mock_repo = MagicMock()
        mock_issue = MagicMock()
        mock_repo.create_issue.return_value = mock_issue
        mock_github.get_repo.return_value = mock_repo

        issue = await client.create_issue(
            "owner/repo",
            title="Test Issue",
            body="Issue description",
        )

        assert issue == mock_issue
        mock_repo.create_issue.assert_called_once_with(
            title="Test Issue",
            body="Issue description",
            labels=[],
        )

    @pytest.mark.asyncio
    async def test_create_issue_error(self, client, mock_github):
        """Test creating an issue with API error."""
        from github import GithubException

        mock_repo = MagicMock()
        mock_repo.create_issue.side_effect = GithubException(
            403, {"message": "Forbidden"}, None
        )
        mock_github.get_repo.return_value = mock_repo

        with pytest.raises(GitHubError, match="Failed to create issue"):
            await client.create_issue(
                "owner/repo",
                title="Test Issue",
                body="Issue description",
            )

    @pytest.mark.asyncio
    async def test_create_pr(self, client, mock_github):
        """Test creating a pull request."""
        mock_repo = MagicMock()
        mock_pr = MagicMock()
        mock_repo.create_pull.return_value = mock_pr
        mock_github.get_repo.return_value = mock_repo

        pr = await client.create_pr(
            "owner/repo",
            title="Test PR",
            body="Description",
            head="feature-branch",
            base="main",
            draft=True,
        )

        assert pr == mock_pr
        mock_repo.create_pull.assert_called_once_with(
            title="Test PR",
            body="Description",
            head="feature-branch",
            base="main",
            draft=True,
        )

    @pytest.mark.asyncio
    async def test_get_pr(self, client, mock_github):
        """Test getting a pull request."""
        mock_repo = MagicMock()
        mock_pr = MagicMock()
        mock_repo.get_pull.return_value = mock_pr
        mock_github.get_repo.return_value = mock_repo

        pr = await client.get_pr("owner/repo", 123)

        assert pr == mock_pr
        mock_repo.get_pull.assert_called_once_with(123)

    @pytest.mark.asyncio
    async def test_update_pr(self, client, mock_github):
        """Test updating a pull request."""
        mock_repo = MagicMock()
        mock_pr = MagicMock()
        mock_repo.get_pull.return_value = mock_pr
        mock_github.get_repo.return_value = mock_repo

        result = await client.update_pr(
            "owner/repo", 123, title="New Title", body="New Body"
        )

        assert result == mock_pr
        mock_pr.edit.assert_called_once_with(title="New Title", body="New Body")

    @pytest.mark.asyncio
    async def test_update_pr_title_only(self, client, mock_github):
        """Test updating only the PR title."""
        mock_repo = MagicMock()
        mock_pr = MagicMock()
        mock_repo.get_pull.return_value = mock_pr
        mock_github.get_repo.return_value = mock_repo

        await client.update_pr("owner/repo", 123, title="New Title")

        mock_pr.edit.assert_called_once_with(title="New Title")

    @pytest.mark.asyncio
    async def test_get_pr_checks(self, client, mock_github):
        """Test getting PR check statuses."""
        mock_repo = MagicMock()
        mock_pr = MagicMock()
        mock_commit = MagicMock()
        mock_check_runs = [MagicMock(), MagicMock()]

        mock_commits = MagicMock()
        mock_commits.totalCount = 1
        mock_commits.reversed = [mock_commit]
        mock_pr.get_commits.return_value = mock_commits
        mock_commit.get_check_runs.return_value = mock_check_runs

        mock_repo.get_pull.return_value = mock_pr
        mock_github.get_repo.return_value = mock_repo

        checks = await client.get_pr_checks("owner/repo", 123)

        assert len(checks) == 2

    @pytest.mark.asyncio
    async def test_get_pr_checks_no_commits(self, client, mock_github):
        """Test getting PR checks when there are no commits."""
        mock_repo = MagicMock()
        mock_pr = MagicMock()

        mock_commits = MagicMock()
        mock_commits.totalCount = 0
        mock_pr.get_commits.return_value = mock_commits

        mock_repo.get_pull.return_value = mock_pr
        mock_github.get_repo.return_value = mock_repo

        checks = await client.get_pr_checks("owner/repo", 123)

        assert checks == []

    @pytest.mark.asyncio
    async def test_get_repo_info(self, client, mock_github):
        """Test getting repository information."""
        mock_repo = MagicMock()
        mock_github.get_repo.return_value = mock_repo

        repo = await client.get_repo_info("owner/repo")

        assert repo == mock_repo
        mock_github.get_repo.assert_called_once_with("owner/repo")

    @pytest.mark.asyncio
    async def test_get_repo_info_not_found(self, client, mock_github):
        """Test getting a non-existent repository."""
        from github import GithubException

        mock_github.get_repo.side_effect = GithubException(
            404, {"message": "Not Found"}, None
        )

        with pytest.raises(GitHubError, match="not found"):
            await client.get_repo_info("owner/nonexistent")

    def test_close(self, client, mock_github):
        """Test closing the client."""
        client.close()

        mock_github.close.assert_called_once()
        assert client._github is None

    def test_close_already_closed(self):
        """Test closing an already closed client."""
        client = GitHubClient()
        client._github = None

        # Should not raise
        client.close()


class TestGitHubClientRateLimiting:
    """Tests for GitHubClient rate limiting functionality."""

    def test_rate_limit_constants(self):
        """Test rate limit constants are defined correctly."""
        assert DEFAULT_GITHUB_RATE_LIMIT == 5000
        assert DEFAULT_GITHUB_RATE_PERIOD == 3600.0

    def test_init_without_rate_limiting(self):
        """Test initialization without rate limiting (default behavior)."""
        mock_github = MagicMock()
        client = GitHubClient(github=mock_github)

        assert client.rate_limiter is None

    def test_init_with_rate_limiting(self):
        """Test initialization with rate limiting enabled."""
        mock_github = MagicMock()
        client = GitHubClient(
            github=mock_github,
            rate_limit=100,
            rate_period=60.0,
        )

        assert client.rate_limiter is not None
        assert client.rate_limiter.max_rate == 100
        assert client.rate_limiter.time_period == 60.0

    def test_init_with_default_period(self):
        """Test initialization with rate limit but default period."""
        mock_github = MagicMock()
        client = GitHubClient(
            github=mock_github,
            rate_limit=5000,
        )

        assert client.rate_limiter is not None
        assert client.rate_limiter.max_rate == 5000
        assert client.rate_limiter.time_period == DEFAULT_GITHUB_RATE_PERIOD

    @pytest.mark.asyncio
    async def test_list_issues_with_rate_limiting(self):
        """Test that list_issues respects rate limiting."""
        mock_github = MagicMock()
        mock_repo = MagicMock()
        mock_issues = [MagicMock(), MagicMock()]
        mock_repo.get_issues.return_value = mock_issues
        mock_github.get_repo.return_value = mock_repo

        # Create client with strict rate limit (2 per second)
        client = GitHubClient(github=mock_github, rate_limit=2, rate_period=1.0)

        # First call should be immediate
        start = time.monotonic()
        await client.list_issues("owner/repo")
        await client.list_issues("owner/repo")
        first_two_duration = time.monotonic() - start

        # First two calls should be fast (within the rate limit)
        assert first_two_duration < 0.5

        # Third call should be delayed by rate limiter
        start = time.monotonic()
        await client.list_issues("owner/repo")
        third_call_duration = time.monotonic() - start

        # The third call should have waited for the rate limit window
        # (approximately 1 second for our 2/second limit)
        assert third_call_duration >= 0.3  # Allow some tolerance

    @pytest.mark.asyncio
    async def test_get_issue_with_rate_limiting(self):
        """Test that get_issue respects rate limiting."""
        mock_github = MagicMock()
        mock_repo = MagicMock()
        mock_issue = MagicMock()
        mock_repo.get_issue.return_value = mock_issue
        mock_github.get_repo.return_value = mock_repo

        client = GitHubClient(github=mock_github, rate_limit=10, rate_period=1.0)

        # Should work with rate limiting
        issue = await client.get_issue("owner/repo", 42)
        assert issue == mock_issue

    @pytest.mark.asyncio
    async def test_add_issue_comment_with_rate_limiting(self):
        """Test that add_issue_comment respects rate limiting."""
        mock_github = MagicMock()
        mock_repo = MagicMock()
        mock_issue = MagicMock()
        mock_repo.get_issue.return_value = mock_issue
        mock_github.get_repo.return_value = mock_repo

        client = GitHubClient(github=mock_github, rate_limit=10, rate_period=1.0)

        # Should work with rate limiting
        await client.add_issue_comment("owner/repo", 42, "Test comment")
        mock_issue.create_comment.assert_called_once_with("Test comment")

    @pytest.mark.asyncio
    async def test_create_issue_with_rate_limiting(self):
        """Test that create_issue respects rate limiting."""
        mock_github = MagicMock()
        mock_repo = MagicMock()
        mock_issue = MagicMock()
        mock_issue.number = 42
        mock_repo.create_issue.return_value = mock_issue
        mock_github.get_repo.return_value = mock_repo

        client = GitHubClient(github=mock_github, rate_limit=10, rate_period=1.0)

        # Should work with rate limiting
        issue = await client.create_issue(
            "owner/repo",
            title="Test Issue",
            body="Description",
            labels=["bug"],
        )
        assert issue == mock_issue
        mock_repo.create_issue.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_pr_with_rate_limiting(self):
        """Test that create_pr respects rate limiting."""
        mock_github = MagicMock()
        mock_repo = MagicMock()
        mock_pr = MagicMock()
        mock_repo.create_pull.return_value = mock_pr
        mock_github.get_repo.return_value = mock_repo

        client = GitHubClient(github=mock_github, rate_limit=10, rate_period=1.0)

        pr = await client.create_pr(
            "owner/repo",
            title="Test PR",
            body="Description",
            head="feature",
            base="main",
        )
        assert pr == mock_pr

    @pytest.mark.asyncio
    async def test_get_pr_with_rate_limiting(self):
        """Test that get_pr respects rate limiting."""
        mock_github = MagicMock()
        mock_repo = MagicMock()
        mock_pr = MagicMock()
        mock_repo.get_pull.return_value = mock_pr
        mock_github.get_repo.return_value = mock_repo

        client = GitHubClient(github=mock_github, rate_limit=10, rate_period=1.0)

        pr = await client.get_pr("owner/repo", 123)
        assert pr == mock_pr

    @pytest.mark.asyncio
    async def test_update_pr_with_rate_limiting(self):
        """Test that update_pr respects rate limiting."""
        mock_github = MagicMock()
        mock_repo = MagicMock()
        mock_pr = MagicMock()
        mock_repo.get_pull.return_value = mock_pr
        mock_github.get_repo.return_value = mock_repo

        client = GitHubClient(github=mock_github, rate_limit=10, rate_period=1.0)

        pr = await client.update_pr("owner/repo", 123, title="New Title")
        assert pr == mock_pr
        mock_pr.edit.assert_called_once_with(title="New Title")

    @pytest.mark.asyncio
    async def test_get_pr_checks_with_rate_limiting(self):
        """Test that get_pr_checks respects rate limiting."""
        mock_github = MagicMock()
        mock_repo = MagicMock()
        mock_pr = MagicMock()
        mock_commit = MagicMock()
        mock_check_runs = [MagicMock()]

        mock_commits = MagicMock()
        mock_commits.totalCount = 1
        mock_commits.reversed = [mock_commit]
        mock_pr.get_commits.return_value = mock_commits
        mock_commit.get_check_runs.return_value = mock_check_runs

        mock_repo.get_pull.return_value = mock_pr
        mock_github.get_repo.return_value = mock_repo

        client = GitHubClient(github=mock_github, rate_limit=10, rate_period=1.0)

        checks = await client.get_pr_checks("owner/repo", 123)
        assert len(checks) == 1

    @pytest.mark.asyncio
    async def test_get_repo_info_with_rate_limiting(self):
        """Test that get_repo_info respects rate limiting."""
        mock_github = MagicMock()
        mock_repo = MagicMock()
        mock_github.get_repo.return_value = mock_repo

        client = GitHubClient(github=mock_github, rate_limit=10, rate_period=1.0)

        repo = await client.get_repo_info("owner/repo")
        assert repo == mock_repo

    @pytest.mark.asyncio
    async def test_without_rate_limiting_no_delays(self):
        """Test that calls without rate limiting have no delays."""
        mock_github = MagicMock()
        mock_repo = MagicMock()
        mock_issues = [MagicMock()]
        mock_repo.get_issues.return_value = mock_issues
        mock_github.get_repo.return_value = mock_repo

        # Create client without rate limiting
        client = GitHubClient(github=mock_github)
        assert client.rate_limiter is None

        # Make many calls quickly
        start = time.monotonic()
        for _ in range(10):
            await client.list_issues("owner/repo")
        duration = time.monotonic() - start

        # Without rate limiting, calls should be nearly instant
        # (only limited by async thread pool overhead)
        assert duration < 2.0  # Should be much faster in practice

    @pytest.mark.asyncio
    async def test_concurrent_rate_limited_calls(self):
        """Test that concurrent calls properly respect rate limits."""
        mock_github = MagicMock()
        mock_repo = MagicMock()
        mock_issues = [MagicMock()]
        mock_repo.get_issues.return_value = mock_issues
        mock_github.get_repo.return_value = mock_repo

        # Create client with 3 requests per second limit
        client = GitHubClient(github=mock_github, rate_limit=3, rate_period=1.0)

        # Fire 6 concurrent requests (should take at least 1 second)
        start = time.monotonic()
        await asyncio.gather(
            client.list_issues("owner/repo"),
            client.list_issues("owner/repo"),
            client.list_issues("owner/repo"),
            client.list_issues("owner/repo"),
            client.list_issues("owner/repo"),
            client.list_issues("owner/repo"),
        )
        duration = time.monotonic() - start

        # 6 requests at 3/second should take at least 1 second
        assert duration >= 0.8  # Allow some tolerance


class TestGitHubClientContextManager:
    """Tests for GitHubClient context manager protocol."""

    @pytest.fixture
    def mock_github(self):
        """Create a mock PyGithub client."""
        return MagicMock()

    def test_sync_context_manager_enter_returns_self(self, mock_github):
        """Test that __enter__ returns the client instance."""
        client = GitHubClient(github=mock_github)
        with client as ctx:
            assert ctx is client

    def test_sync_context_manager_calls_close_on_exit(self, mock_github):
        """Test that __exit__ calls close()."""
        client = GitHubClient(github=mock_github)
        with client:
            pass

        mock_github.close.assert_called_once()
        assert client._github is None

    def test_sync_context_manager_calls_close_on_exception(self, mock_github):
        """Test that __exit__ calls close() even when an exception occurs."""
        client = GitHubClient(github=mock_github)
        with pytest.raises(ValueError, match="test error"):
            with client:
                raise ValueError("test error")

        mock_github.close.assert_called_once()
        assert client._github is None

    @pytest.mark.asyncio
    async def test_async_context_manager_enter_returns_self(self, mock_github):
        """Test that __aenter__ returns the client instance."""
        client = GitHubClient(github=mock_github)
        async with client as ctx:
            assert ctx is client

    @pytest.mark.asyncio
    async def test_async_context_manager_calls_close_on_exit(self, mock_github):
        """Test that __aexit__ calls close()."""
        client = GitHubClient(github=mock_github)
        async with client:
            pass

        mock_github.close.assert_called_once()
        assert client._github is None

    @pytest.mark.asyncio
    async def test_async_context_manager_calls_close_on_exception(self, mock_github):
        """Test that __aexit__ calls close() even when an exception occurs."""
        client = GitHubClient(github=mock_github)
        with pytest.raises(ValueError, match="test error"):
            async with client:
                raise ValueError("test error")

        mock_github.close.assert_called_once()
        assert client._github is None

    @pytest.mark.asyncio
    async def test_async_context_manager_with_operations(self, mock_github):
        """Test using async context manager with actual operations."""
        mock_repo = MagicMock()
        mock_issues = [MagicMock()]
        mock_repo.get_issues.return_value = mock_issues
        mock_github.get_repo.return_value = mock_repo

        async with GitHubClient(github=mock_github) as client:
            issues = await client.list_issues("owner/repo")
            assert len(issues) == 1

        # close() should have been called on exit
        mock_github.close.assert_called_once()

    def test_sync_context_manager_close_idempotent(self):
        """Test that close() via context manager is safe when github is None."""
        client = GitHubClient()
        client._github = None

        # Should not raise
        with client:
            pass
