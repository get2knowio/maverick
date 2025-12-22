"""Tests for GitHubCLIRunner."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from maverick.exceptions import GitHubAuthError, GitHubCLINotFoundError
from maverick.runners.github import GitHubCLIRunner
from maverick.runners.models import CommandResult, GitHubIssue, PullRequest


@pytest.fixture
def mock_gh_available():
    with patch("shutil.which", return_value="/usr/bin/gh"):
        yield


class TestGitHubCLIRunner:
    def test_gh_not_installed(self):
        """Test GitHubCLINotFoundError raised when gh not installed."""
        with (
            patch("shutil.which", return_value=None),
            pytest.raises(GitHubCLINotFoundError),
        ):
            GitHubCLIRunner()

    @pytest.mark.asyncio
    async def test_auth_check_on_first_use(self, mock_gh_available):
        """Test authentication is checked on first async operation (fail-fast)."""
        # Mock auth check failure
        auth_result = CommandResult(
            returncode=1,
            stdout="",
            stderr="Not authenticated",
            duration_ms=50,
            timed_out=False,
        )

        runner = GitHubCLIRunner()
        mock_runner = AsyncMock()
        mock_runner.run = AsyncMock(return_value=auth_result)
        runner._command_runner = mock_runner

        # First call to any async method should check auth and fail
        with pytest.raises(GitHubAuthError):
            await runner.get_issue(42)

        # Verify auth check was called
        mock_runner.run.assert_called_once_with(["gh", "auth", "status"])

    @pytest.mark.asyncio
    async def test_auth_check_only_once(self, mock_gh_available):
        """Test authentication is checked only once, not on every call."""
        # Mock successful auth check
        auth_result = CommandResult(
            returncode=0,
            stdout="Logged in",
            stderr="",
            duration_ms=50,
            timed_out=False,
        )
        # Mock successful issue fetch
        issue_result = CommandResult(
            returncode=0,
            stdout=json.dumps(
                {
                    "number": 42,
                    "title": "Test",
                    "body": "",
                    "labels": [],
                    "state": "OPEN",
                    "assignees": [],
                    "url": "https://github.com/repo/issues/42",
                }
            ),
            stderr="",
            duration_ms=100,
            timed_out=False,
        )

        runner = GitHubCLIRunner()
        mock_runner = AsyncMock()
        # First call: auth check, second call: get issue, third call: get issue again
        mock_runner.run = AsyncMock(
            side_effect=[auth_result, issue_result, issue_result]
        )
        runner._command_runner = mock_runner

        # First call should check auth
        await runner.get_issue(42)
        # Second call should NOT check auth again
        await runner.get_issue(42)

        # Verify auth check was called only once (first call)
        assert mock_runner.run.call_count == 3
        # First call was auth check
        assert mock_runner.run.call_args_list[0][0][0] == ["gh", "auth", "status"]
        # Second and third calls were issue commands
        assert mock_runner.run.call_args_list[1][0][0][0] == "gh"
        assert mock_runner.run.call_args_list[2][0][0][0] == "gh"

    @pytest.mark.asyncio
    async def test_get_issue(self, mock_gh_available):
        """Test fetching a single issue."""
        auth_result = CommandResult(
            returncode=0, stdout="Logged in", stderr="", duration_ms=50, timed_out=False
        )
        mock_result = CommandResult(
            returncode=0,
            stdout=json.dumps(
                {
                    "number": 42,
                    "title": "Test Issue",
                    "body": "Description",
                    "labels": [{"name": "bug"}],
                    "state": "OPEN",
                    "assignees": [{"login": "user1"}],
                    "url": "https://github.com/repo/issues/42",
                }
            ),
            stderr="",
            duration_ms=100,
            timed_out=False,
        )

        runner = GitHubCLIRunner()
        mock_runner = AsyncMock()
        mock_runner.run = AsyncMock(side_effect=[auth_result, mock_result])
        runner._command_runner = mock_runner

        issue = await runner.get_issue(42)

        assert isinstance(issue, GitHubIssue)
        assert issue.number == 42
        assert issue.title == "Test Issue"
        assert issue.state == "open"
        assert "bug" in issue.labels

    @pytest.mark.asyncio
    async def test_list_issues_with_filter(self, mock_gh_available):
        """Test listing issues with label filter."""
        auth_result = CommandResult(
            returncode=0, stdout="Logged in", stderr="", duration_ms=50, timed_out=False
        )
        mock_result = CommandResult(
            returncode=0,
            stdout=json.dumps(
                [
                    {
                        "number": 1,
                        "title": "Issue 1",
                        "body": "",
                        "labels": [{"name": "bug"}],
                        "state": "OPEN",
                        "assignees": [],
                        "url": "https://github.com/repo/issues/1",
                    },
                ]
            ),
            stderr="",
            duration_ms=100,
            timed_out=False,
        )

        runner = GitHubCLIRunner()
        mock_runner = AsyncMock()
        mock_runner.run = AsyncMock(side_effect=[auth_result, mock_result])
        runner._command_runner = mock_runner

        issues = await runner.list_issues(label="bug", state="open")

        assert len(issues) == 1
        assert issues[0].number == 1

    @pytest.mark.asyncio
    async def test_create_pr(self, mock_gh_available):
        """Test creating a pull request."""
        auth_result = CommandResult(
            returncode=0, stdout="Logged in", stderr="", duration_ms=50, timed_out=False
        )
        create_result = CommandResult(
            returncode=0,
            stdout="https://github.com/repo/pull/123\n",
            stderr="",
            duration_ms=100,
            timed_out=False,
        )
        view_result = CommandResult(
            returncode=0,
            stdout=json.dumps(
                {
                    "number": 123,
                    "title": "Test PR",
                    "body": "PR body",
                    "state": "OPEN",
                    "url": "https://github.com/repo/pull/123",
                    "headRefName": "feature",
                    "baseRefName": "main",
                    "mergeable": True,
                    "isDraft": False,
                }
            ),
            stderr="",
            duration_ms=100,
            timed_out=False,
        )

        runner = GitHubCLIRunner()
        mock_runner = AsyncMock()
        # Auth check, create PR, then get_pr is called which doesn't check auth again
        mock_runner.run = AsyncMock(
            side_effect=[auth_result, create_result, view_result]
        )
        runner._command_runner = mock_runner

        pr = await runner.create_pr(title="Test PR", body="PR body")

        assert isinstance(pr, PullRequest)
        assert pr.number == 123
        assert pr.title == "Test PR"

    @pytest.mark.asyncio
    async def test_get_pr_checks(self, mock_gh_available):
        """Test getting PR check statuses."""
        auth_result = CommandResult(
            returncode=0, stdout="Logged in", stderr="", duration_ms=50, timed_out=False
        )
        mock_result = CommandResult(
            returncode=0,
            stdout=json.dumps(
                [
                    {
                        "name": "test",
                        "state": "completed",
                        "conclusion": "success",
                        "detailsUrl": "https://...",
                    },
                    {
                        "name": "lint",
                        "state": "in_progress",
                        "conclusion": None,
                        "detailsUrl": None,
                    },
                ]
            ),
            stderr="",
            duration_ms=100,
            timed_out=False,
        )

        runner = GitHubCLIRunner()
        mock_runner = AsyncMock()
        mock_runner.run = AsyncMock(side_effect=[auth_result, mock_result])
        runner._command_runner = mock_runner

        checks = await runner.get_pr_checks(123)

        assert len(checks) == 2
        assert checks[0].name == "test"
        assert checks[0].passed is True
        assert checks[1].pending is True
