"""Unit tests for GitHub actions.

Tests the github.py action module including:
- fetch_github_issues action with label filtering
- fetch_github_issue action for single issue retrieval
- create_github_pr action with title and body generation
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from maverick.library.actions.github import (
    create_github_pr,
    fetch_github_issue,
    fetch_github_issues,
)
from maverick.runners.models import CommandResult


def make_result(
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
    timed_out: bool = False,
) -> CommandResult:
    """Create a CommandResult for testing."""
    return CommandResult(
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        duration_ms=100,
        timed_out=timed_out,
    )


class TestFetchGitHubIssues:
    """Tests for fetch_github_issues action."""

    @pytest.mark.asyncio
    async def test_fetches_issues_with_label(self) -> None:
        """Test fetches issues filtered by label."""
        issues_data = [
            {
                "number": 123,
                "title": "Fix bug in parser",
                "body": "The parser fails on edge cases",
                "labels": [{"name": "tech-debt"}, {"name": "bug"}],
                "assignees": [],
                "url": "https://github.com/org/repo/issues/123",
                "state": "open",
            },
            {
                "number": 456,
                "title": "Refactor validation",
                "body": "Validation logic needs cleanup",
                "labels": [{"name": "tech-debt"}],
                "assignees": [{"login": "dev1"}],
                "url": "https://github.com/org/repo/issues/456",
                "state": "open",
            },
        ]

        with patch("maverick.library.actions.github._runner") as mock_runner:
            mock_runner.run = AsyncMock(
                return_value=make_result(stdout=json.dumps(issues_data))
            )

            result = await fetch_github_issues(label="tech-debt")

            assert result.success is True
            assert result.total_count == 2
            assert len(result.issues) == 2
            assert result.error is None

            # Verify first issue
            issue1 = result.issues[0]
            assert issue1.number == 123
            assert issue1.title == "Fix bug in parser"
            assert issue1.body == "The parser fails on edge cases"
            assert issue1.labels == ("tech-debt", "bug")
            assert issue1.assignee is None
            assert issue1.url == "https://github.com/org/repo/issues/123"
            assert issue1.state == "open"

            # Verify second issue
            issue2 = result.issues[1]
            assert issue2.number == 456
            assert issue2.assignee == "dev1"
            assert issue2.labels == ("tech-debt",)

    @pytest.mark.asyncio
    async def test_respects_limit_parameter(self) -> None:
        """Test respects limit parameter for number of issues."""
        with patch("maverick.library.actions.github._runner") as mock_runner:
            mock_runner.run = AsyncMock(return_value=make_result(stdout="[]"))

            result = await fetch_github_issues(label="bug", limit=10)

            assert result.success is True

            # Verify limit was passed to gh command
            call_args = mock_runner.run.call_args[0][0]
            assert "--limit" in call_args
            limit_index = call_args.index("--limit")
            assert call_args[limit_index + 1] == "10"

    @pytest.mark.asyncio
    async def test_uses_default_limit(self) -> None:
        """Test uses default limit of 5 when not specified."""
        with patch("maverick.library.actions.github._runner") as mock_runner:
            mock_runner.run = AsyncMock(return_value=make_result(stdout="[]"))

            result = await fetch_github_issues(label="enhancement")

            assert result.success is True

            # Verify default limit was used
            call_args = mock_runner.run.call_args[0][0]
            assert "--limit" in call_args
            limit_index = call_args.index("--limit")
            assert call_args[limit_index + 1] == "5"

    @pytest.mark.asyncio
    async def test_filters_by_state(self) -> None:
        """Test filters issues by state parameter."""
        with patch("maverick.library.actions.github._runner") as mock_runner:
            mock_runner.run = AsyncMock(return_value=make_result(stdout="[]"))

            result = await fetch_github_issues(label="bug", state="closed")

            assert result.success is True

            # Verify state filter was passed
            call_args = mock_runner.run.call_args[0][0]
            assert "--state" in call_args
            state_index = call_args.index("--state")
            assert call_args[state_index + 1] == "closed"

    @pytest.mark.asyncio
    async def test_uses_default_state_open(self) -> None:
        """Test uses default state of 'open' when not specified."""
        with patch("maverick.library.actions.github._runner") as mock_runner:
            mock_runner.run = AsyncMock(return_value=make_result(stdout="[]"))

            result = await fetch_github_issues(label="tech-debt")

            assert result.success is True

            # Verify default state was used
            call_args = mock_runner.run.call_args[0][0]
            assert "--state" in call_args
            state_index = call_args.index("--state")
            assert call_args[state_index + 1] == "open"

    @pytest.mark.asyncio
    async def test_handles_empty_result(self) -> None:
        """Test handles empty issue list gracefully."""
        with patch("maverick.library.actions.github._runner") as mock_runner:
            mock_runner.run = AsyncMock(return_value=make_result(stdout="[]"))

            result = await fetch_github_issues(label="nonexistent")

            assert result.success is True
            assert result.total_count == 0
            assert result.issues == ()
            assert result.error is None

    @pytest.mark.asyncio
    async def test_handles_issues_without_body(self) -> None:
        """Test handles issues with missing body field."""
        issues_data = [
            {
                "number": 789,
                "title": "Issue without body",
                "labels": [],
                "assignees": [],
                "url": "https://github.com/org/repo/issues/789",
                "state": "open",
            },
        ]

        with patch("maverick.library.actions.github._runner") as mock_runner:
            mock_runner.run = AsyncMock(
                return_value=make_result(stdout=json.dumps(issues_data))
            )

            result = await fetch_github_issues(label="bug")

            assert result.success is True
            assert result.issues[0].body is None

    @pytest.mark.asyncio
    async def test_handles_issues_without_assignees(self) -> None:
        """Test handles issues with no assignees."""
        issues_data = [
            {
                "number": 100,
                "title": "Unassigned issue",
                "labels": [{"name": "tech-debt"}],
                "assignees": [],
                "url": "https://github.com/org/repo/issues/100",
                "state": "open",
            },
        ]

        with patch("maverick.library.actions.github._runner") as mock_runner:
            mock_runner.run = AsyncMock(
                return_value=make_result(stdout=json.dumps(issues_data))
            )

            result = await fetch_github_issues(label="tech-debt")

            assert result.success is True
            assert result.issues[0].assignee is None

    @pytest.mark.asyncio
    async def test_handles_gh_cli_failure(self) -> None:
        """Test handles GitHub CLI command failure gracefully."""
        with patch("maverick.library.actions.github._runner") as mock_runner:
            mock_runner.run = AsyncMock(
                return_value=make_result(
                    returncode=1, stderr="fatal: not a GitHub repository"
                )
            )

            result = await fetch_github_issues(label="bug")

            assert result.success is False
            assert result.total_count == 0
            assert result.issues == ()
            assert result.error is not None
            assert "not a GitHub repository" in result.error

    @pytest.mark.asyncio
    async def test_requests_correct_fields(self) -> None:
        """Test requests all necessary fields from GitHub CLI."""
        with patch("maverick.library.actions.github._runner") as mock_runner:
            mock_runner.run = AsyncMock(return_value=make_result(stdout="[]"))

            await fetch_github_issues(label="tech-debt")

            # Verify --json includes all required fields
            call_args = mock_runner.run.call_args[0][0]
            assert "--json" in call_args
            json_index = call_args.index("--json")
            fields = call_args[json_index + 1]
            assert "number" in fields
            assert "title" in fields
            assert "body" in fields
            assert "labels" in fields
            assert "assignees" in fields
            assert "url" in fields
            assert "state" in fields


class TestFetchGitHubIssue:
    """Tests for fetch_github_issue action."""

    @pytest.mark.asyncio
    async def test_fetches_single_issue(self) -> None:
        """Test fetches a single issue by number."""
        issue_data = {
            "number": 42,
            "title": "Critical bug",
            "body": "This is a critical issue",
            "labels": [{"name": "bug"}, {"name": "priority"}],
            "assignees": [{"login": "developer"}],
            "url": "https://github.com/org/repo/issues/42",
            "state": "open",
        }

        with patch("maverick.library.actions.github._runner") as mock_runner:
            mock_runner.run = AsyncMock(
                return_value=make_result(stdout=json.dumps(issue_data))
            )

            result = await fetch_github_issue(issue_number=42)

            assert result.success is True
            assert result.error is None

            issue = result.issue
            assert issue.number == 42
            assert issue.title == "Critical bug"
            assert issue.body == "This is a critical issue"
            assert issue.labels == ("bug", "priority")
            assert issue.assignee == "developer"
            assert issue.url == "https://github.com/org/repo/issues/42"
            assert issue.state == "open"

    @pytest.mark.asyncio
    async def test_handles_issue_without_body(self) -> None:
        """Test handles issue with missing body field."""
        issue_data = {
            "number": 50,
            "title": "Issue without body",
            "labels": [],
            "assignees": [],
            "url": "https://github.com/org/repo/issues/50",
            "state": "closed",
        }

        with patch("maverick.library.actions.github._runner") as mock_runner:
            mock_runner.run = AsyncMock(
                return_value=make_result(stdout=json.dumps(issue_data))
            )

            result = await fetch_github_issue(issue_number=50)

            assert result.success is True
            assert result.issue.body is None
            assert result.issue.state == "closed"

    @pytest.mark.asyncio
    async def test_handles_issue_without_assignees(self) -> None:
        """Test handles issue with no assignees."""
        issue_data = {
            "number": 60,
            "title": "Unassigned issue",
            "body": "This issue has no assignee",
            "labels": [{"name": "enhancement"}],
            "assignees": [],
            "url": "https://github.com/org/repo/issues/60",
            "state": "open",
        }

        with patch("maverick.library.actions.github._runner") as mock_runner:
            mock_runner.run = AsyncMock(
                return_value=make_result(stdout=json.dumps(issue_data))
            )

            result = await fetch_github_issue(issue_number=60)

            assert result.success is True
            assert result.issue.assignee is None

    @pytest.mark.asyncio
    async def test_handles_nonexistent_issue(self) -> None:
        """Test handles request for nonexistent issue number."""
        with patch("maverick.library.actions.github._runner") as mock_runner:
            mock_runner.run = AsyncMock(
                return_value=make_result(returncode=1, stderr="issue not found")
            )

            result = await fetch_github_issue(issue_number=9999)

            assert result.success is False
            assert result.issue is None
            assert result.error is not None
            assert "issue not found" in result.error

    @pytest.mark.asyncio
    async def test_passes_correct_issue_number(self) -> None:
        """Test passes correct issue number to GitHub CLI."""
        issue_data = {
            "number": 123,
            "title": "Test",
            "labels": [],
            "assignees": [],
            "url": "https://github.com/org/repo/issues/123",
            "state": "open",
        }

        with patch("maverick.library.actions.github._runner") as mock_runner:
            mock_runner.run = AsyncMock(
                return_value=make_result(stdout=json.dumps(issue_data))
            )

            await fetch_github_issue(issue_number=123)

            # Verify issue number was passed
            call_args = mock_runner.run.call_args[0][0]
            assert "123" in call_args


class TestCreateGitHubPR:
    """Tests for create_github_pr action."""

    @pytest.mark.asyncio
    async def test_creates_pr_with_user_title(self) -> None:
        """Test creates PR with user-provided title."""
        with patch("maverick.library.actions.github._runner") as mock_runner:
            mock_runner.run = AsyncMock(
                return_value=make_result(
                    stdout="https://github.com/org/repo/pull/123\n"
                )
            )

            result = await create_github_pr(
                base_branch="main",
                draft=False,
                title="feat: add new feature",
                generated_title=None,
                generated_body="## Summary\n\nAdded feature X",
            )

            assert result.success is True
            assert result.pr_number == 123
            assert result.pr_url == "https://github.com/org/repo/pull/123"
            assert result.title == "feat: add new feature"
            assert result.draft is False
            assert result.base_branch == "main"
            assert result.error is None

            # Verify title was used in command
            call_args = mock_runner.run.call_args[0][0]
            assert "--title" in call_args
            title_index = call_args.index("--title")
            assert call_args[title_index + 1] == "feat: add new feature"

    @pytest.mark.asyncio
    async def test_uses_generated_title_when_no_user_title(self) -> None:
        """Test uses generated title when user title not provided."""
        with patch("maverick.library.actions.github._runner") as mock_runner:
            mock_runner.run = AsyncMock(
                return_value=make_result(
                    stdout="https://github.com/org/repo/pull/456\n"
                )
            )

            result = await create_github_pr(
                base_branch="develop",
                draft=True,
                title=None,
                generated_title="fix: resolve parser issue",
                generated_body="## Summary\n\nFixed parser bug",
            )

            assert result.success is True
            assert result.title == "fix: resolve parser issue"
            assert result.draft is True

            # Verify generated title was used
            call_args = mock_runner.run.call_args[0][0]
            title_index = call_args.index("--title")
            assert call_args[title_index + 1] == "fix: resolve parser issue"

    @pytest.mark.asyncio
    async def test_uses_default_title_when_none_provided(self) -> None:
        """Test uses default title when neither user nor generated title provided."""
        with patch("maverick.library.actions.github._runner") as mock_runner:
            mock_runner.run = AsyncMock(
                return_value=make_result(
                    stdout="https://github.com/org/repo/pull/789\n"
                )
            )

            result = await create_github_pr(
                base_branch="main",
                draft=False,
                title=None,
                generated_title=None,
                generated_body="## Summary\n\nChanges",
            )

            assert result.success is True
            assert result.title == "Update"

    @pytest.mark.asyncio
    async def test_creates_draft_pr(self) -> None:
        """Test creates PR as draft when draft=True."""
        with patch("maverick.library.actions.github._runner") as mock_runner:
            mock_runner.run = AsyncMock(
                return_value=make_result(
                    stdout="https://github.com/org/repo/pull/100\n"
                )
            )

            result = await create_github_pr(
                base_branch="main",
                draft=True,
                title="WIP: feature",
                generated_title=None,
                generated_body="Work in progress",
            )

            assert result.success is True
            assert result.draft is True

            # Verify --draft flag was passed
            call_args = mock_runner.run.call_args[0][0]
            assert "--draft" in call_args

    @pytest.mark.asyncio
    async def test_creates_non_draft_pr(self) -> None:
        """Test creates non-draft PR when draft=False."""
        with patch("maverick.library.actions.github._runner") as mock_runner:
            mock_runner.run = AsyncMock(
                return_value=make_result(
                    stdout="https://github.com/org/repo/pull/200\n"
                )
            )

            result = await create_github_pr(
                base_branch="main",
                draft=False,
                title="feat: complete feature",
                generated_title=None,
                generated_body="Feature is ready",
            )

            assert result.success is True
            assert result.draft is False

            # Verify --draft flag was NOT passed
            call_args = mock_runner.run.call_args[0][0]
            assert "--draft" not in call_args

    @pytest.mark.asyncio
    async def test_sets_base_branch(self) -> None:
        """Test sets correct base branch for PR."""
        with patch("maverick.library.actions.github._runner") as mock_runner:
            mock_runner.run = AsyncMock(
                return_value=make_result(
                    stdout="https://github.com/org/repo/pull/300\n"
                )
            )

            result = await create_github_pr(
                base_branch="develop",
                draft=False,
                title="feat: new feature",
                generated_title=None,
                generated_body="Feature description",
            )

            assert result.success is True
            assert result.base_branch == "develop"

            # Verify --base flag was passed correctly
            call_args = mock_runner.run.call_args[0][0]
            assert "--base" in call_args
            base_index = call_args.index("--base")
            assert call_args[base_index + 1] == "develop"

    @pytest.mark.asyncio
    async def test_includes_pr_body(self) -> None:
        """Test includes PR body in creation."""
        pr_body = (
            "## Summary\n\nThis PR adds feature X\n\n"
            "## Changes\n- Added file A\n- Updated file B"
        )

        with patch("maverick.library.actions.github._runner") as mock_runner:
            mock_runner.run = AsyncMock(
                return_value=make_result(
                    stdout="https://github.com/org/repo/pull/400\n"
                )
            )

            result = await create_github_pr(
                base_branch="main",
                draft=False,
                title="feat: feature X",
                generated_title=None,
                generated_body=pr_body,
            )

            assert result.success is True

            # Verify body was passed correctly
            call_args = mock_runner.run.call_args[0][0]
            assert "--body" in call_args
            body_index = call_args.index("--body")
            assert call_args[body_index + 1] == pr_body

    @pytest.mark.asyncio
    async def test_extracts_pr_number_from_url(self) -> None:
        """Test correctly extracts PR number from URL."""
        test_cases = [
            ("https://github.com/org/repo/pull/123", 123),
            ("https://github.com/owner/project/pull/456/", 456),
            ("https://github.com/user/repo/pull/789", 789),
        ]

        for pr_url, expected_number in test_cases:
            with patch("maverick.library.actions.github._runner") as mock_runner:
                mock_runner.run = AsyncMock(
                    return_value=make_result(stdout=f"{pr_url}\n")
                )

                result = await create_github_pr(
                    base_branch="main",
                    draft=False,
                    title="test",
                    generated_title=None,
                    generated_body="test body",
                )

                assert result.pr_number == expected_number

    @pytest.mark.asyncio
    async def test_handles_pr_creation_failure(self) -> None:
        """Test handles PR creation failure gracefully."""
        with patch("maverick.library.actions.github._runner") as mock_runner:
            mock_runner.run = AsyncMock(
                return_value=make_result(
                    returncode=1,
                    stderr="GraphQL: Pull request already exists",
                )
            )

            result = await create_github_pr(
                base_branch="main",
                draft=False,
                title="feat: test",
                generated_title=None,
                generated_body="Test body",
            )

            assert result.success is False
            assert result.pr_number is None
            assert result.pr_url is None
            assert result.error is not None
            assert "already exists" in result.error

    @pytest.mark.asyncio
    async def test_handles_invalid_pr_url(self) -> None:
        """Test handles invalid PR URL format gracefully."""
        with patch("maverick.library.actions.github._runner") as mock_runner:
            mock_runner.run = AsyncMock(
                return_value=make_result(stdout="invalid-url-format\n")
            )

            result = await create_github_pr(
                base_branch="main",
                draft=False,
                title="test",
                generated_title=None,
                generated_body="test",
            )

            assert result.success is True
            assert result.pr_url == "invalid-url-format"
            assert result.pr_number is None  # Cannot extract number from invalid URL

    @pytest.mark.asyncio
    async def test_user_title_takes_precedence_over_generated(self) -> None:
        """Test user-provided title takes precedence over generated title."""
        with patch("maverick.library.actions.github._runner") as mock_runner:
            mock_runner.run = AsyncMock(
                return_value=make_result(
                    stdout="https://github.com/org/repo/pull/999\n"
                )
            )

            result = await create_github_pr(
                base_branch="main",
                draft=False,
                title="User Title",
                generated_title="Generated Title",
                generated_body="Body",
            )

            assert result.title == "User Title"

            # Verify user title was used in command
            call_args = mock_runner.run.call_args[0][0]
            title_index = call_args.index("--title")
            assert call_args[title_index + 1] == "User Title"
