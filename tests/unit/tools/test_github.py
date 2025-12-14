"""Unit tests for GitHub MCP tools.

Tests the GitHub tools functionality including:
- PR status checking (merge readiness, checks, reviews, conflicts)
- Error handling and validation
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from maverick.tools.github import (
    _classify_error,
    _error_response,
    _parse_rate_limit_wait,
    _success_response,
    github_add_labels,
    github_close_issue,
    github_create_pr,
    github_get_issue,
    github_get_pr_diff,
    github_list_issues,
    github_pr_status,
)


class TestGitHubPrStatus:
    """Tests for github_pr_status tool (T025-T027)."""

    @pytest.mark.asyncio
    async def test_github_pr_status_ready_to_merge(self) -> None:
        """Test github_pr_status when PR is ready to merge (T025).

        Verifies:
        - mergeable=true
        - clean state (CLEAN/clean)
        - passing checks (conclusion=SUCCESS)
        - approved reviews
        - no conflicts detected
        """
        pr_number = 123

        # Mock response: PR ready to merge
        mock_pr_data = {
            "number": pr_number,
            "state": "OPEN",
            "mergeable": "MERGEABLE",
            "mergeStateStatus": "CLEAN",
            "headRefName": "feature/test",
            "baseRefName": "main",
            "reviews": [
                {
                    "author": {"login": "reviewer1"},
                    "state": "APPROVED",
                },
                {
                    "author": {"login": "reviewer2"},
                    "state": "APPROVED",
                },
            ],
            "statusCheckRollup": [
                {
                    "name": "CI Build",
                    "status": "COMPLETED",
                    "conclusion": "SUCCESS",
                },
                {
                    "name": "Unit Tests",
                    "status": "COMPLETED",
                    "conclusion": "SUCCESS",
                },
            ],
        }

        with patch("maverick.tools.github._run_gh_command", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (json.dumps(mock_pr_data), "", 0)

            result = await github_pr_status.handler({"pr_number": pr_number})

            # Verify command execution
            mock_run.assert_called_once()
            call_args = mock_run.call_args[0]
            assert call_args[0] == "pr"
            assert call_args[1] == "view"
            assert call_args[2] == str(pr_number)
            assert "--json" in call_args

        # Verify success response structure
        assert "content" in result
        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "text"

        # Parse response data
        response_data = json.loads(result["content"][0]["text"])

        # Verify PR status fields
        assert response_data["pr_number"] == pr_number
        assert response_data["state"] == "open"
        assert response_data["mergeable"] is True
        assert response_data["merge_state_status"] == "clean"
        assert response_data["has_conflicts"] is False

        # Verify reviews parsed correctly
        assert len(response_data["reviews"]) == 2
        assert response_data["reviews"][0]["author"] == "reviewer1"
        assert response_data["reviews"][0]["state"] == "APPROVED"
        assert response_data["reviews"][1]["author"] == "reviewer2"
        assert response_data["reviews"][1]["state"] == "APPROVED"

        # Verify checks parsed correctly
        assert len(response_data["checks"]) == 2
        assert response_data["checks"][0]["name"] == "CI Build"
        assert response_data["checks"][0]["status"] == "completed"
        assert response_data["checks"][0]["conclusion"] == "SUCCESS"
        assert response_data["checks"][1]["name"] == "Unit Tests"
        assert response_data["checks"][1]["status"] == "completed"
        assert response_data["checks"][1]["conclusion"] == "SUCCESS"

    @pytest.mark.asyncio
    async def test_github_pr_status_failing_checks(self) -> None:
        """Test github_pr_status when PR has failing checks (T026).

        Verifies:
        - checks with conclusion=FAILURE
        - mixed check states (some passing, some failing)
        - proper parsing of check status and conclusion
        """
        pr_number = 456

        # Mock response: PR with failing checks
        mock_pr_data = {
            "number": pr_number,
            "state": "OPEN",
            "mergeable": "MERGEABLE",
            "mergeStateStatus": "UNSTABLE",
            "headRefName": "feature/failing-tests",
            "baseRefName": "main",
            "reviews": [
                {
                    "author": {"login": "reviewer1"},
                    "state": "APPROVED",
                },
            ],
            "statusCheckRollup": [
                {
                    "name": "CI Build",
                    "status": "COMPLETED",
                    "conclusion": "SUCCESS",
                },
                {
                    "name": "Unit Tests",
                    "status": "COMPLETED",
                    "conclusion": "FAILURE",
                },
                {
                    "name": "Linting",
                    "status": "COMPLETED",
                    "conclusion": "FAILURE",
                },
                {
                    "name": "Security Scan",
                    "status": "IN_PROGRESS",
                    "conclusion": None,
                },
            ],
        }

        with patch("maverick.tools.github._run_gh_command", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (json.dumps(mock_pr_data), "", 0)

            result = await github_pr_status.handler({"pr_number": pr_number})

            # Verify command execution
            mock_run.assert_called_once()

        # Parse response data
        response_data = json.loads(result["content"][0]["text"])

        # Verify PR status
        assert response_data["pr_number"] == pr_number
        assert response_data["state"] == "open"
        assert response_data["merge_state_status"] == "unstable"

        # Verify checks with failures
        assert len(response_data["checks"]) == 4

        # Check 1: Passing
        assert response_data["checks"][0]["name"] == "CI Build"
        assert response_data["checks"][0]["conclusion"] == "SUCCESS"

        # Check 2: Failing
        assert response_data["checks"][1]["name"] == "Unit Tests"
        assert response_data["checks"][1]["status"] == "completed"
        assert response_data["checks"][1]["conclusion"] == "FAILURE"

        # Check 3: Failing
        assert response_data["checks"][2]["name"] == "Linting"
        assert response_data["checks"][2]["status"] == "completed"
        assert response_data["checks"][2]["conclusion"] == "FAILURE"

        # Check 4: In progress (no conclusion yet)
        assert response_data["checks"][3]["name"] == "Security Scan"
        assert response_data["checks"][3]["status"] == "in_progress"
        assert response_data["checks"][3]["conclusion"] is None

    @pytest.mark.asyncio
    async def test_github_pr_status_merge_conflicts(self) -> None:
        """Test github_pr_status when PR has merge conflicts (T027).

        Verifies:
        - mergeStateStatus=DIRTY or CONFLICTING
        - has_conflicts=true
        - mergeable=CONFLICTING
        - proper conflict detection logic
        """
        pr_number = 789

        # Mock response: PR with merge conflicts
        mock_pr_data = {
            "number": pr_number,
            "state": "OPEN",
            "mergeable": "CONFLICTING",
            "mergeStateStatus": "DIRTY",
            "headRefName": "feature/conflicting",
            "baseRefName": "main",
            "reviews": [
                {
                    "author": {"login": "reviewer1"},
                    "state": "CHANGES_REQUESTED",
                },
            ],
            "statusCheckRollup": [
                {
                    "name": "CI Build",
                    "status": "COMPLETED",
                    "conclusion": "SUCCESS",
                },
            ],
        }

        with patch("maverick.tools.github._run_gh_command", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (json.dumps(mock_pr_data), "", 0)

            result = await github_pr_status.handler({"pr_number": pr_number})

            # Verify command execution
            mock_run.assert_called_once()

        # Parse response data
        response_data = json.loads(result["content"][0]["text"])

        # Verify conflict detection
        assert response_data["pr_number"] == pr_number
        assert response_data["state"] == "open"
        assert response_data["mergeable"] is False  # CONFLICTING converted to False
        assert response_data["merge_state_status"] == "dirty"
        assert response_data["has_conflicts"] is True

        # Verify reviews with changes requested
        assert len(response_data["reviews"]) == 1
        assert response_data["reviews"][0]["author"] == "reviewer1"
        assert response_data["reviews"][0]["state"] == "CHANGES_REQUESTED"

        # Verify checks still present
        assert len(response_data["checks"]) == 1
        assert response_data["checks"][0]["name"] == "CI Build"

    @pytest.mark.asyncio
    async def test_github_pr_status_not_found(self) -> None:
        """Test github_pr_status when PR doesn't exist."""
        pr_number = 999

        with patch("maverick.tools.github._run_gh_command", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = ("", "pull request not found", 1)

            result = await github_pr_status.handler({"pr_number": pr_number})

        # Parse error response
        response_data = json.loads(result["content"][0]["text"])

        # Verify error response
        assert response_data["isError"] is True
        assert response_data["error_code"] == "NOT_FOUND"
        assert f"PR #{pr_number} not found" in response_data["message"]

    @pytest.mark.asyncio
    async def test_github_pr_status_invalid_input(self) -> None:
        """Test github_pr_status with invalid PR number."""
        result = await github_pr_status.handler({"pr_number": -1})

        # Parse error response
        response_data = json.loads(result["content"][0]["text"])

        # Verify validation error
        assert response_data["isError"] is True
        assert response_data["error_code"] == "INVALID_INPUT"
        assert "must be positive" in response_data["message"]

    @pytest.mark.asyncio
    async def test_github_pr_status_empty_checks_and_reviews(self) -> None:
        """Test github_pr_status when PR has no checks or reviews."""
        pr_number = 100

        # Mock response: PR with no checks or reviews
        mock_pr_data = {
            "number": pr_number,
            "state": "OPEN",
            "mergeable": "MERGEABLE",
            "mergeStateStatus": "CLEAN",
            "headRefName": "feature/simple",
            "baseRefName": "main",
            "reviews": [],
            "statusCheckRollup": None,
        }

        with patch("maverick.tools.github._run_gh_command", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (json.dumps(mock_pr_data), "", 0)

            result = await github_pr_status.handler({"pr_number": pr_number})

        # Parse response data
        response_data = json.loads(result["content"][0]["text"])

        # Verify empty lists
        assert response_data["reviews"] == []
        assert response_data["checks"] == []
        assert response_data["has_conflicts"] is False


class TestGithubListIssues:
    """Tests for github_list_issues MCP tool."""

    @pytest.mark.asyncio
    async def test_github_list_issues_with_label(self) -> None:
        """Test github_list_issues with label filter (T017)."""
        # Mock response data
        issues_data = [
            {
                "number": 1,
                "title": "Bug in login",
                "labels": [{"name": "bug"}, {"name": "priority-high"}],
                "state": "open",
                "url": "https://github.com/owner/repo/issues/1",
            },
            {
                "number": 2,
                "title": "Another bug",
                "labels": [{"name": "bug"}],
                "state": "open",
                "url": "https://github.com/owner/repo/issues/2",
            },
        ]
        stdout = json.dumps(issues_data)
        stderr = ""
        return_code = 0

        with patch(
            "maverick.tools.github._run_gh_command",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.return_value = (stdout, stderr, return_code)

            result = await github_list_issues.handler({"label": "bug", "state": "open", "limit": 30})

        # Verify gh command called with correct arguments
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0]
        assert "issue" in call_args
        assert "list" in call_args
        assert "--label" in call_args
        assert "bug" in call_args
        assert "--state" in call_args
        assert "open" in call_args
        assert "--limit" in call_args
        assert "30" in call_args

        # Verify response structure
        assert "content" in result
        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "text"

        # Parse response text
        response_data = json.loads(result["content"][0]["text"])
        assert "issues" in response_data
        assert len(response_data["issues"]) == 2

        # Verify label extraction from nested objects
        issue1 = response_data["issues"][0]
        assert issue1["number"] == 1
        assert issue1["title"] == "Bug in login"
        assert issue1["labels"] == ["bug", "priority-high"]
        assert issue1["state"] == "open"

        issue2 = response_data["issues"][1]
        assert issue2["number"] == 2
        assert issue2["labels"] == ["bug"]

    @pytest.mark.asyncio
    async def test_github_list_issues_with_state_and_limit(self) -> None:
        """Test github_list_issues with state and limit filtering (T018)."""
        # Mock response with closed issues
        issues_data = [
            {
                "number": 10,
                "title": "Fixed bug",
                "labels": [],
                "state": "closed",
                "url": "https://github.com/owner/repo/issues/10",
            },
            {
                "number": 11,
                "title": "Resolved feature",
                "labels": [{"name": "enhancement"}],
                "state": "closed",
                "url": "https://github.com/owner/repo/issues/11",
            },
        ]
        stdout = json.dumps(issues_data)
        stderr = ""
        return_code = 0

        with patch(
            "maverick.tools.github._run_gh_command",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.return_value = (stdout, stderr, return_code)

            result = await github_list_issues.handler({"state": "closed", "limit": 10})

        # Verify gh command called with correct arguments
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0]
        assert "--state" in call_args
        assert "closed" in call_args
        assert "--limit" in call_args
        assert "10" in call_args

        # Verify response
        response_data = json.loads(result["content"][0]["text"])
        assert len(response_data["issues"]) == 2
        assert response_data["issues"][0]["state"] == "closed"
        assert response_data["issues"][1]["state"] == "closed"

        # Verify labels are properly extracted
        assert response_data["issues"][0]["labels"] == []
        assert response_data["issues"][1]["labels"] == ["enhancement"]

    @pytest.mark.asyncio
    async def test_github_list_issues_empty_result(self) -> None:
        """Test github_list_issues with no matching issues."""
        stdout = "[]"
        stderr = ""
        return_code = 0

        with patch(
            "maverick.tools.github._run_gh_command",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.return_value = (stdout, stderr, return_code)

            result = await github_list_issues.handler({"label": "nonexistent", "state": "open", "limit": 30})

        response_data = json.loads(result["content"][0]["text"])
        assert response_data["issues"] == []

    @pytest.mark.asyncio
    async def test_github_list_issues_invalid_state(self) -> None:
        """Test github_list_issues with invalid state parameter."""
        result = await github_list_issues.handler({"state": "invalid", "limit": 30})

        # Verify error response
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["isError"] is True
        assert response_data["error_code"] == "INVALID_INPUT"
        assert "invalid state" in response_data["message"].lower()

    @pytest.mark.asyncio
    async def test_github_list_issues_invalid_limit(self) -> None:
        """Test github_list_issues with invalid limit parameter."""
        result = await github_list_issues.handler({"state": "open", "limit": 0})

        # Verify error response
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["isError"] is True
        assert response_data["error_code"] == "INVALID_INPUT"
        assert "positive" in response_data["message"].lower()

    @pytest.mark.asyncio
    async def test_github_list_issues_command_failure(self) -> None:
        """Test github_list_issues handles gh command failure."""
        stdout = ""
        stderr = "GitHub API error"
        return_code = 1

        with patch(
            "maverick.tools.github._run_gh_command",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.return_value = (stdout, stderr, return_code)

            result = await github_list_issues.handler({"state": "open", "limit": 30})

        # Verify error response
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["isError"] is True
        assert "error_code" in response_data


class TestGithubGetIssue:
    """Tests for github_get_issue MCP tool."""

    @pytest.mark.asyncio
    async def test_github_get_issue_success(self) -> None:
        """Test github_get_issue success case with full issue details (T019)."""
        # Mock issue data with nested objects
        issue_data = {
            "number": 42,
            "title": "Critical bug in authentication",
            "body": "Users cannot log in after recent update.\n\nSteps to reproduce:\n1. Open app\n2. Try to log in",
            "url": "https://github.com/owner/repo/issues/42",
            "state": "open",
            "labels": [
                {"name": "bug"},
                {"name": "priority-high"},
                {"name": "security"},
            ],
            "assignees": [
                {"login": "developer1"},
                {"login": "developer2"},
            ],
            "author": {"login": "reporter123"},
            "comments": [
                {"id": 1, "body": "Working on it"},
                {"id": 2, "body": "Fix incoming"},
            ],
            "createdAt": "2024-01-15T10:30:00Z",
            "updatedAt": "2024-01-16T14:45:00Z",
        }
        stdout = json.dumps(issue_data)
        stderr = ""
        return_code = 0

        with patch(
            "maverick.tools.github._run_gh_command",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.return_value = (stdout, stderr, return_code)

            result = await github_get_issue.handler({"issue_number": 42})

        # Verify gh command called with correct arguments
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0]
        assert "issue" in call_args
        assert "view" in call_args
        assert "42" in call_args
        assert "--json" in call_args

        # Verify response structure
        assert "content" in result
        response_data = json.loads(result["content"][0]["text"])

        # Verify all fields are present and properly extracted
        assert response_data["number"] == 42
        assert response_data["title"] == "Critical bug in authentication"
        assert "cannot log in" in response_data["body"]
        assert response_data["url"] == "https://github.com/owner/repo/issues/42"
        assert response_data["state"] == "open"

        # Verify label extraction from nested objects
        assert response_data["labels"] == ["bug", "priority-high", "security"]

        # Verify assignee extraction
        assert response_data["assignees"] == ["developer1", "developer2"]

        # Verify author extraction
        assert response_data["author"] == "reporter123"

        # Verify comments count
        assert response_data["comments_count"] == 2

        # Verify timestamps
        assert response_data["created_at"] == "2024-01-15T10:30:00Z"
        assert response_data["updated_at"] == "2024-01-16T14:45:00Z"

    @pytest.mark.asyncio
    async def test_github_get_issue_not_found(self) -> None:
        """Test github_get_issue returns error when issue not found (T020)."""
        stdout = ""
        stderr = "could not find issue 999"
        return_code = 1

        with patch(
            "maverick.tools.github._run_gh_command",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.return_value = (stdout, stderr, return_code)

            result = await github_get_issue.handler({"issue_number": 999})

        # Verify error response
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["isError"] is True
        assert response_data["error_code"] == "NOT_FOUND"
        assert "999" in response_data["message"]
        # Message contains either "not found" or "could not find" depending on stderr
        msg_lower = response_data["message"].lower()
        assert "not found" in msg_lower or "could not find" in msg_lower

    @pytest.mark.asyncio
    async def test_github_get_issue_minimal_data(self) -> None:
        """Test github_get_issue handles minimal issue data."""
        # Issue with no body, labels, assignees, or comments
        issue_data = {
            "number": 5,
            "title": "Simple issue",
            "url": "https://github.com/owner/repo/issues/5",
            "state": "open",
        }
        stdout = json.dumps(issue_data)
        stderr = ""
        return_code = 0

        with patch(
            "maverick.tools.github._run_gh_command",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.return_value = (stdout, stderr, return_code)

            result = await github_get_issue.handler({"issue_number": 5})

        response_data = json.loads(result["content"][0]["text"])
        assert response_data["number"] == 5
        assert response_data["title"] == "Simple issue"
        assert response_data["body"] == ""
        assert response_data["labels"] == []
        assert response_data["assignees"] == []
        assert response_data["comments_count"] == 0

    @pytest.mark.asyncio
    async def test_github_get_issue_invalid_number(self) -> None:
        """Test github_get_issue rejects invalid issue number."""
        result = await github_get_issue.handler({"issue_number": 0})

        # Verify error response
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["isError"] is True
        assert response_data["error_code"] == "INVALID_INPUT"
        assert "positive" in response_data["message"].lower()

    @pytest.mark.asyncio
    async def test_github_get_issue_rate_limit_error(self) -> None:
        """Test github_get_issue handles rate limit errors."""
        stdout = ""
        stderr = "API rate limit exceeded, retry after 60 seconds"
        return_code = 1

        with patch(
            "maverick.tools.github._run_gh_command",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.return_value = (stdout, stderr, return_code)

            result = await github_get_issue.handler({"issue_number": 42})

        # Verify error response with retry_after
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["isError"] is True
        assert response_data["error_code"] == "RATE_LIMIT"
        assert "retry_after_seconds" in response_data
        assert response_data["retry_after_seconds"] == 60

    @pytest.mark.asyncio
    async def test_github_get_issue_timeout(self) -> None:
        """Test github_get_issue handles timeout."""
        import asyncio

        with patch(
            "maverick.tools.github._run_gh_command",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.side_effect = asyncio.TimeoutError("Operation timed out")

            result = await github_get_issue.handler({"issue_number": 42})

        # Verify error response
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["isError"] is True
        assert response_data["error_code"] == "TIMEOUT"

    @pytest.mark.asyncio
    async def test_github_get_issue_invalid_json(self) -> None:
        """Test github_get_issue handles invalid JSON response."""
        stdout = "not valid json {["
        stderr = ""
        return_code = 0

        with patch(
            "maverick.tools.github._run_gh_command",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.return_value = (stdout, stderr, return_code)

            result = await github_get_issue.handler({"issue_number": 42})

        # Verify error response
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["isError"] is True
        assert response_data["error_code"] == "INTERNAL_ERROR"
        assert "parse" in response_data["message"].lower()


# =============================================================================
# T048: Rate Limit Error Handling Tests
# =============================================================================


class TestRateLimitErrorHandling:
    """Tests for rate limit error handling across all GitHub tools (T048)."""

    @pytest.mark.asyncio
    async def test_github_create_pr_rate_limit(self) -> None:
        """Test rate limit error handling for github_create_pr."""
        # Mock rate limit error response
        with patch(
            "maverick.tools.github._run_gh_command",
            new_callable=AsyncMock,
            return_value=("", "API rate limit exceeded. Retry after 120 seconds", 1),
        ):
            result = await github_create_pr.handler({
                "title": "Test PR",
                "body": "Test body",
                "base": "main",
                "head": "feature",
                "draft": False,
            })

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
            "maverick.tools.github._run_gh_command",
            new_callable=AsyncMock,
            return_value=("", "GitHub API rate limit exceeded. Wait 60s before retrying", 1),
        ):
            result = await github_list_issues.handler({
                "label": "bug",
                "state": "open",
                "limit": 30,
            })

        # Verify error response
        error_data = json.loads(result["content"][0]["text"])
        assert error_data["isError"] is True
        assert error_data["error_code"] == "RATE_LIMIT"
        assert error_data["retry_after_seconds"] == 60

    @pytest.mark.asyncio
    async def test_github_pr_status_rate_limit(self) -> None:
        """Test rate limit error handling for github_pr_status."""
        with patch(
            "maverick.tools.github._run_gh_command",
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
            "maverick.tools.github._run_gh_command",
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
            "maverick.tools.github._run_gh_command",
            new_callable=AsyncMock,
            return_value=("", "GitHub API rate limit. Retry after 30 seconds.", 1),
        ):
            result = await github_add_labels.handler({
                "issue_number": 100,
                "labels": ["bug", "urgent"],
            })

        error_data = json.loads(result["content"][0]["text"])
        assert error_data["isError"] is True
        assert error_data["error_code"] == "RATE_LIMIT"
        assert error_data["retry_after_seconds"] == 30

    @pytest.mark.asyncio
    async def test_github_close_issue_rate_limit(self) -> None:
        """Test rate limit error handling for github_close_issue."""
        with patch(
            "maverick.tools.github._run_gh_command",
            new_callable=AsyncMock,
            return_value=("", "Rate limit hit, wait 75 seconds", 1),
        ):
            result = await github_close_issue.handler({
                "issue_number": 200,
                "comment": "Fixed!",
            })

        error_data = json.loads(result["content"][0]["text"])
        assert error_data["isError"] is True
        assert error_data["error_code"] == "RATE_LIMIT"
        assert error_data["retry_after_seconds"] == 75

    @pytest.mark.asyncio
    async def test_rate_limit_error_with_numeric_pattern(self) -> None:
        """Test rate limit parsing with 'retry after N' pattern."""
        with patch(
            "maverick.tools.github._run_gh_command",
            new_callable=AsyncMock,
            return_value=("", "Rate limit exceeded, retry after 150", 1),
        ):
            result = await github_create_pr.handler({
                "title": "Test",
                "body": "Body",
                "base": "main",
                "head": "test",
            })

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
            "maverick.tools.github._run_gh_command",
            new_callable=AsyncMock,
            return_value=("", "network error: connection refused", 1),
        ):
            result = await github_create_pr.handler({
                "title": "Test PR",
                "body": "Test body",
                "base": "main",
                "head": "feature",
                "draft": False,
            })

        error_data = json.loads(result["content"][0]["text"])
        assert error_data["isError"] is True
        assert error_data["error_code"] == "NETWORK_ERROR"
        assert "retry_after_seconds" not in error_data
        assert "network" in error_data["message"].lower()

    @pytest.mark.asyncio
    async def test_github_list_issues_network_error(self) -> None:
        """Test network error handling for github_list_issues."""
        with patch(
            "maverick.tools.github._run_gh_command",
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
            "maverick.tools.github._run_gh_command",
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
            "maverick.tools.github._run_gh_command",
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
            "maverick.tools.github._run_gh_command",
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
            "maverick.tools.github._run_gh_command",
            new_callable=AsyncMock,
            return_value=("", "connection error - network issue", 1),
        ):
            result = await github_add_labels.handler({
                "issue_number": 555,
                "labels": ["test"],
            })

        error_data = json.loads(result["content"][0]["text"])
        assert error_data["isError"] is True
        assert error_data["error_code"] == "NETWORK_ERROR"

    @pytest.mark.asyncio
    async def test_github_close_issue_network_error(self) -> None:
        """Test network error handling for github_close_issue."""
        with patch(
            "maverick.tools.github._run_gh_command",
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
            "maverick.tools.github._run_gh_command",
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
            "maverick.tools.github._run_gh_command",
            new_callable=AsyncMock,
            return_value=("", "authentication required - please login", 1),
        ):
            result = await github_create_pr.handler({
                "title": "Test PR",
                "body": "Test body",
                "base": "main",
                "head": "feature",
                "draft": False,
            })

        error_data = json.loads(result["content"][0]["text"])
        assert error_data["isError"] is True
        assert error_data["error_code"] == "AUTH_ERROR"
        assert "retry_after_seconds" not in error_data
        assert "gh auth login" in error_data["message"]

    @pytest.mark.asyncio
    async def test_github_list_issues_auth_error(self) -> None:
        """Test authentication error handling for github_list_issues."""
        with patch(
            "maverick.tools.github._run_gh_command",
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
            "maverick.tools.github._run_gh_command",
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
            "maverick.tools.github._run_gh_command",
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
            "maverick.tools.github._run_gh_command",
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
            "maverick.tools.github._run_gh_command",
            new_callable=AsyncMock,
            return_value=("", "Authentication credentials are missing or invalid", 1),
        ):
            result = await github_add_labels.handler({
                "issue_number": 444,
                "labels": ["critical"],
            })

        error_data = json.loads(result["content"][0]["text"])
        assert error_data["isError"] is True
        assert error_data["error_code"] == "AUTH_ERROR"

    @pytest.mark.asyncio
    async def test_github_close_issue_auth_error(self) -> None:
        """Test authentication error handling for github_close_issue."""
        with patch(
            "maverick.tools.github._run_gh_command",
            new_callable=AsyncMock,
            return_value=("", "unauthorized - please authenticate with GitHub", 1),
        ):
            result = await github_close_issue.handler({
                "issue_number": 555,
                "comment": "Done",
            })

        error_data = json.loads(result["content"][0]["text"])
        assert error_data["isError"] is True
        assert error_data["error_code"] == "AUTH_ERROR"
        assert "gh auth login" in error_data["message"]

    @pytest.mark.asyncio
    async def test_auth_error_actionable_message(self) -> None:
        """Test auth error returns actionable message."""
        with patch(
            "maverick.tools.github._run_gh_command",
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
# Cross-Cutting Error Handling Tests
# =============================================================================


class TestErrorHandlingConsistency:
    """Tests for consistent error handling behavior across all tools."""

    @pytest.mark.asyncio
    async def test_all_tools_return_dicts_not_exceptions(self) -> None:
        """Test that tools always return MCP dicts, never raise exceptions."""
        # Mock error for all tools
        with patch(
            "maverick.tools.github._run_gh_command",
            new_callable=AsyncMock,
            return_value=("", "Some error", 1),
        ):
            tools_and_args = [
                (github_create_pr, {"title": "T", "body": "B", "base": "m", "head": "f"}),
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
# T010: Helper Functions Tests
# =============================================================================


class TestHelperFunctions:
    """Tests for helper functions in github tools module (T010)."""

    # -------------------------------------------------------------------------
    # _parse_rate_limit_wait tests
    # -------------------------------------------------------------------------

    def test_parse_rate_limit_retry_after_pattern(self) -> None:
        """Test parsing 'retry after N' pattern."""
        stderr = "API rate limit exceeded. retry after 120 seconds"
        result = _parse_rate_limit_wait(stderr)
        assert result == 120

    def test_parse_rate_limit_wait_pattern(self) -> None:
        """Test parsing 'wait Ns' pattern."""
        stderr = "Rate limit hit, please wait 60s before retrying"
        result = _parse_rate_limit_wait(stderr)
        assert result == 60

    def test_parse_rate_limit_seconds_pattern(self) -> None:
        """Test parsing 'N seconds' pattern."""
        stderr = "GitHub API rate limit. Try again in 45 seconds"
        result = _parse_rate_limit_wait(stderr)
        assert result == 45

    def test_parse_rate_limit_no_match_returns_default(self) -> None:
        """Test rate limit present but no time returns default 60s."""
        stderr = "API rate limit exceeded"
        result = _parse_rate_limit_wait(stderr)
        assert result == 60

    def test_parse_rate_limit_non_rate_limit_error(self) -> None:
        """Test non-rate-limit message returns None."""
        stderr = "Authentication required"
        result = _parse_rate_limit_wait(stderr)
        assert result is None

    # -------------------------------------------------------------------------
    # _success_response tests
    # -------------------------------------------------------------------------

    def test_success_response_format(self) -> None:
        """Test success response has correct MCP format with content array."""
        data = {"pr_number": 123, "url": "https://github.com/owner/repo/pull/123"}
        result = _success_response(data)

        # Verify MCP structure
        assert "content" in result
        assert isinstance(result["content"], list)
        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "text"
        assert "text" in result["content"][0]

        # Verify data is JSON serialized
        parsed = json.loads(result["content"][0]["text"])
        assert parsed == data

    def test_success_response_json_serialization(self) -> None:
        """Test success response correctly serializes complex data."""
        data = {
            "issues": [
                {"number": 1, "title": "Bug", "labels": ["bug", "priority-high"]},
                {"number": 2, "title": "Feature", "labels": []},
            ],
            "count": 2,
        }
        result = _success_response(data)

        # Verify JSON round-trip
        parsed = json.loads(result["content"][0]["text"])
        assert parsed == data
        assert len(parsed["issues"]) == 2
        assert parsed["issues"][0]["labels"] == ["bug", "priority-high"]

    # -------------------------------------------------------------------------
    # _error_response tests
    # -------------------------------------------------------------------------

    def test_error_response_basic(self) -> None:
        """Test error response basic structure."""
        message = "Issue not found"
        error_code = "NOT_FOUND"
        result = _error_response(message, error_code)

        # Verify MCP structure
        assert "content" in result
        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "text"

        # Parse error data
        error_data = json.loads(result["content"][0]["text"])
        assert error_data["isError"] is True
        assert error_data["message"] == message
        assert error_data["error_code"] == error_code
        assert "retry_after_seconds" not in error_data

    def test_error_response_with_retry_after(self) -> None:
        """Test error response includes retry_after when provided."""
        message = "Rate limit exceeded"
        error_code = "RATE_LIMIT"
        retry_after = 120
        result = _error_response(message, error_code, retry_after_seconds=retry_after)

        error_data = json.loads(result["content"][0]["text"])
        assert error_data["isError"] is True
        assert error_data["message"] == message
        assert error_data["error_code"] == error_code
        assert error_data["retry_after_seconds"] == 120

    def test_error_response_without_retry_after(self) -> None:
        """Test error response excludes retry_after when None."""
        message = "Network error"
        error_code = "NETWORK_ERROR"
        result = _error_response(message, error_code, retry_after_seconds=None)

        error_data = json.loads(result["content"][0]["text"])
        assert error_data["isError"] is True
        assert error_data["error_code"] == error_code
        assert "retry_after_seconds" not in error_data

    # -------------------------------------------------------------------------
    # _classify_error tests
    # -------------------------------------------------------------------------

    def test_classify_error_not_found(self) -> None:
        """Test classification of 'not found' errors."""
        stderr = "could not find pull request #999"
        message, error_code, retry_after = _classify_error(stderr)

        assert error_code == "NOT_FOUND"
        assert "not found" in message.lower() or "could not find" in message.lower()
        assert retry_after is None

    def test_classify_error_rate_limit(self) -> None:
        """Test classification of rate limit errors with retry_after."""
        stderr = "API rate limit exceeded. retry after 90 seconds"
        message, error_code, retry_after = _classify_error(stderr)

        assert error_code == "RATE_LIMIT"
        assert "rate limit" in message.lower()
        assert retry_after == 90
        assert "90" in message

    def test_classify_error_auth(self) -> None:
        """Test classification of authentication errors."""
        stderr = "authentication required - please login"
        message, error_code, retry_after = _classify_error(stderr)

        assert error_code == "AUTH_ERROR"
        assert "gh auth login" in message
        assert retry_after is None

    def test_classify_error_network(self) -> None:
        """Test classification of network errors."""
        stderr = "network error: connection refused"
        message, error_code, retry_after = _classify_error(stderr)

        assert error_code == "NETWORK_ERROR"
        assert "network" in message.lower()
        assert retry_after is None

    def test_classify_error_network_connection(self) -> None:
        """Test classification of connection errors."""
        stderr = "connection timeout - unable to reach server"
        message, error_code, retry_after = _classify_error(stderr)

        assert error_code == "NETWORK_ERROR"
        assert "connection" in message.lower()
        assert retry_after is None

    def test_classify_error_timeout(self) -> None:
        """Test classification of timeout errors."""
        stderr = "request timeout after 30 seconds"
        message, error_code, retry_after = _classify_error(stderr)

        assert error_code == "TIMEOUT"
        assert "timeout" in message.lower()
        assert retry_after is None

    def test_classify_error_internal(self) -> None:
        """Test classification of unknown/internal errors."""
        stderr = "unexpected server error occurred"
        message, error_code, retry_after = _classify_error(stderr)

        assert error_code == "INTERNAL_ERROR"
        assert message == stderr
        assert retry_after is None

    def test_classify_error_uses_stdout_when_stderr_empty(self) -> None:
        """Test error classification uses stdout when stderr is empty."""
        stdout = "not found"
        stderr = ""
        message, error_code, retry_after = _classify_error(stderr, stdout)

        assert error_code == "NOT_FOUND"
        assert message == stdout

    def test_classify_error_unauthorized(self) -> None:
        """Test classification of unauthorized errors."""
        stderr = "unauthorized access - invalid credentials"
        message, error_code, retry_after = _classify_error(stderr)

        assert error_code == "AUTH_ERROR"
        assert "gh auth login" in message
        assert retry_after is None

    def test_classify_error_case_insensitive(self) -> None:
        """Test error classification is case-insensitive."""
        stderr = "RATE LIMIT EXCEEDED. RETRY AFTER 60 SECONDS"
        message, error_code, retry_after = _classify_error(stderr)

        assert error_code == "RATE_LIMIT"
        assert retry_after == 60


# =============================================================================
# T009: Prerequisite Verification Tests
# =============================================================================


class TestVerifyPrerequisites:
    """Tests for _verify_prerequisites function (T009)."""

    @pytest.mark.asyncio
    async def test_verify_prerequisites_success(self) -> None:
        """Test all prerequisites checks pass successfully."""
        from maverick.tools.github import _verify_prerequisites

        # Mock successful subprocess calls
        async def mock_subprocess_exec(*args, **kwargs):
            """Mock successful subprocess execution."""
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(b"", b""))
            mock_process.returncode = 0
            return mock_process

        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=mock_subprocess_exec,
        ), patch(
            "maverick.tools.github._run_gh_command",
            new_callable=AsyncMock,
            return_value=("Logged in as user", "", 0),
        ):
            # Should not raise any exception
            await _verify_prerequisites()

    @pytest.mark.asyncio
    async def test_verify_prerequisites_gh_not_installed(self) -> None:
        """Test gh CLI not found (FileNotFoundError)."""
        from maverick.exceptions import GitHubToolsError
        from maverick.tools.github import _verify_prerequisites

        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("gh command not found"),
        ):
            with pytest.raises(GitHubToolsError) as exc_info:
                await _verify_prerequisites()

            assert exc_info.value.check_failed == "gh_installed"
            assert "gh" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_verify_prerequisites_gh_not_authenticated(self) -> None:
        """Test gh auth status fails."""
        from maverick.exceptions import GitHubToolsError
        from maverick.tools.github import _verify_prerequisites

        # Mock gh --version succeeds but gh auth status fails
        async def mock_subprocess_exec(*args, **kwargs):
            """Mock subprocess that succeeds for gh --version."""
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(b"gh version 2.0.0", b""))
            mock_process.returncode = 0
            return mock_process

        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=mock_subprocess_exec,
        ), patch(
            "maverick.tools.github._run_gh_command",
            new_callable=AsyncMock,
            return_value=("", "You are not logged into any GitHub hosts", 1),
        ):
            with pytest.raises(GitHubToolsError) as exc_info:
                await _verify_prerequisites()

            assert exc_info.value.check_failed == "gh_authenticated"
            assert "authenticated" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_verify_prerequisites_not_git_repo(self) -> None:
        """Test git rev-parse fails (not in git repo)."""
        from maverick.exceptions import GitHubToolsError
        from maverick.tools.github import _verify_prerequisites

        call_count = 0

        async def mock_subprocess_exec(*args, **kwargs):
            """Mock subprocess: gh succeeds, git rev-parse fails."""
            nonlocal call_count
            call_count += 1

            mock_process = AsyncMock()
            command = args[0]

            if command == "gh":
                # gh --version succeeds
                mock_process.communicate = AsyncMock(return_value=(b"gh version 2.0.0", b""))
                mock_process.returncode = 0
            elif command == "git" and "rev-parse" in args:
                # git rev-parse fails
                mock_process.communicate = AsyncMock(
                    return_value=(b"", b"fatal: not a git repository")
                )
                mock_process.returncode = 128
            else:
                # Other git commands succeed
                mock_process.communicate = AsyncMock(return_value=(b"", b""))
                mock_process.returncode = 0

            return mock_process

        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=mock_subprocess_exec,
        ), patch(
            "maverick.tools.github._run_gh_command",
            new_callable=AsyncMock,
            return_value=("Logged in as user", "", 0),
        ):
            with pytest.raises(GitHubToolsError) as exc_info:
                await _verify_prerequisites()

            assert exc_info.value.check_failed == "git_repo"
            assert "git repository" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_verify_prerequisites_no_remote(self) -> None:
        """Test git remote get-url fails (no origin)."""
        from maverick.exceptions import GitHubToolsError
        from maverick.tools.github import _verify_prerequisites

        call_count = 0

        async def mock_subprocess_exec(*args, **kwargs):
            """Mock subprocess: gh and git rev-parse succeed, git remote fails."""
            nonlocal call_count
            call_count += 1

            mock_process = AsyncMock()
            command = args[0]

            if command == "gh":
                # gh --version succeeds
                mock_process.communicate = AsyncMock(return_value=(b"gh version 2.0.0", b""))
                mock_process.returncode = 0
            elif command == "git" and "remote" in args and "get-url" in args:
                # git remote get-url origin fails
                mock_process.communicate = AsyncMock(
                    return_value=(b"", b"fatal: No such remote 'origin'")
                )
                mock_process.returncode = 128
            else:
                # Other commands succeed
                mock_process.communicate = AsyncMock(return_value=(b"", b""))
                mock_process.returncode = 0

            return mock_process

        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=mock_subprocess_exec,
        ), patch(
            "maverick.tools.github._run_gh_command",
            new_callable=AsyncMock,
            return_value=("Logged in as user", "", 0),
        ):
            with pytest.raises(GitHubToolsError) as exc_info:
                await _verify_prerequisites()

            assert exc_info.value.check_failed == "git_remote"
            assert "remote" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_verify_prerequisites_gh_timeout(self) -> None:
        """Test gh --version times out."""
        import asyncio

        from maverick.exceptions import GitHubToolsError
        from maverick.tools.github import _verify_prerequisites

        async def mock_subprocess_exec(*args, **kwargs):
            """Mock subprocess that times out for gh --version."""
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
            return mock_process

        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=mock_subprocess_exec,
        ):
            with pytest.raises(GitHubToolsError) as exc_info:
                await _verify_prerequisites()

            assert exc_info.value.check_failed == "gh_installed"
            assert "timed out" in str(exc_info.value).lower()
