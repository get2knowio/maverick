"""Unit tests for GitHub issue MCP tools.

Tests issue-related GitHub tools: list, get, add_labels, close_issue.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from maverick.tools.github import (
    github_add_labels,
    github_close_issue,
    github_get_issue,
    github_list_issues,
)


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
            "maverick.tools.github.tools.issues.run_gh_command",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.return_value = (stdout, stderr, return_code)

            result = await github_list_issues.handler(
                {"label": "bug", "state": "open", "limit": 30}
            )

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
            "maverick.tools.github.tools.issues.run_gh_command",
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
            "maverick.tools.github.tools.issues.run_gh_command",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.return_value = (stdout, stderr, return_code)

            result = await github_list_issues.handler(
                {"label": "nonexistent", "state": "open", "limit": 30}
            )

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
            "maverick.tools.github.tools.issues.run_gh_command",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.return_value = (stdout, stderr, return_code)

            result = await github_list_issues.handler({"state": "open", "limit": 30})

        # Verify error response
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["isError"] is True
        assert "error_code" in response_data


class TestGitHubAddLabels:
    """Tests for github_add_labels tool (T037-T038)."""

    @pytest.mark.asyncio
    async def test_github_add_labels_success(self) -> None:
        """Test adding labels to an issue successfully (T037).

        Verifies:
        - Labels are added to the issue
        - gh CLI command is called with correct arguments
        - Success response includes issue_number and labels_added
        """
        issue_number = 123
        labels = ["bug", "priority-high"]

        with patch(
            "maverick.tools.github.tools.issues.run_gh_command",
            new_callable=AsyncMock,
        ) as mock_run:
            # gh issue edit 123 --add-label bug --add-label priority-high
            mock_run.return_value = ("", "", 0)

            result = await github_add_labels.handler(
                {
                    "issue_number": issue_number,
                    "labels": labels,
                }
            )

        # Verify gh command called with correct arguments
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0]
        assert "issue" in call_args
        assert "edit" in call_args
        assert str(issue_number) in call_args
        assert "--add-label" in call_args
        # Verify both labels are in the command
        assert "bug" in call_args
        assert "priority-high" in call_args

        # Verify success response
        assert "content" in result
        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "text"

        # Parse response data
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["success"] is True
        assert response_data["issue_number"] == issue_number
        assert response_data["labels_added"] == labels

    @pytest.mark.asyncio
    async def test_github_add_labels_new_label_creation(self) -> None:
        """Test that new labels are created if they don't exist (T038).

        The gh CLI automatically creates labels that don't exist,
        so this test verifies that the operation succeeds even when
        adding labels that may not exist in the repository.
        """
        issue_number = 456
        labels = ["new-label", "another-new-label"]

        with patch(
            "maverick.tools.github.tools.issues.run_gh_command",
            new_callable=AsyncMock,
        ) as mock_run:
            # gh CLI creates new labels automatically
            mock_run.return_value = ("", "", 0)

            result = await github_add_labels.handler(
                {
                    "issue_number": issue_number,
                    "labels": labels,
                }
            )

        # Verify command was called
        mock_run.assert_called_once()

        # Verify success response
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["success"] is True
        assert response_data["issue_number"] == issue_number
        assert response_data["labels_added"] == labels

    @pytest.mark.asyncio
    async def test_github_add_labels_multiple_labels(self) -> None:
        """Test adding multiple labels at once."""
        issue_number = 789
        labels = ["bug", "urgent", "needs-triage", "backend"]

        with patch(
            "maverick.tools.github.tools.issues.run_gh_command",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.return_value = ("", "", 0)

            result = await github_add_labels.handler(
                {
                    "issue_number": issue_number,
                    "labels": labels,
                }
            )

        # Verify all labels are in the command
        call_args = mock_run.call_args[0]
        for label in labels:
            assert label in call_args

        # Verify success response
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["success"] is True
        assert response_data["labels_added"] == labels

    @pytest.mark.asyncio
    async def test_github_add_labels_empty_list_error(self) -> None:
        """Test empty labels list returns INVALID_INPUT error."""
        result = await github_add_labels.handler(
            {
                "issue_number": 100,
                "labels": [],
            }
        )

        # Verify error response
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["isError"] is True
        assert response_data["error_code"] == "INVALID_INPUT"
        assert "empty" in response_data["message"].lower()

    @pytest.mark.asyncio
    async def test_github_add_labels_invalid_issue_number(self) -> None:
        """Test invalid issue_number (<=0) returns INVALID_INPUT error."""
        # Test with 0
        result = await github_add_labels.handler(
            {
                "issue_number": 0,
                "labels": ["bug"],
            }
        )

        response_data = json.loads(result["content"][0]["text"])
        assert response_data["isError"] is True
        assert response_data["error_code"] == "INVALID_INPUT"
        assert "positive" in response_data["message"].lower()

        # Test with negative number
        result = await github_add_labels.handler(
            {
                "issue_number": -5,
                "labels": ["bug"],
            }
        )

        response_data = json.loads(result["content"][0]["text"])
        assert response_data["isError"] is True
        assert response_data["error_code"] == "INVALID_INPUT"
        assert "positive" in response_data["message"].lower()

    @pytest.mark.asyncio
    async def test_github_add_labels_issue_not_found(self) -> None:
        """Test issue not found (404) returns NOT_FOUND error."""
        issue_number = 999

        with patch(
            "maverick.tools.github.tools.issues.run_gh_command",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.return_value = ("", "could not find issue 999", 1)

            result = await github_add_labels.handler(
                {
                    "issue_number": issue_number,
                    "labels": ["bug"],
                }
            )

        # Verify error response
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["isError"] is True
        assert response_data["error_code"] == "NOT_FOUND"
        assert str(issue_number) in response_data["message"]

    @pytest.mark.asyncio
    async def test_github_add_labels_not_found_specific_message(self) -> None:
        """Test github_add_labels with specific 'not found' message (lines 674-675)."""
        issue_number = 888

        with patch(
            "maverick.tools.github.tools.issues.run_gh_command",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.return_value = ("", "issue not found", 1)

            result = await github_add_labels.handler(
                {
                    "issue_number": issue_number,
                    "labels": ["bug"],
                }
            )

        # Verify error response with specific message
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["isError"] is True
        assert response_data["error_code"] == "NOT_FOUND"
        assert f"Issue #{issue_number} not found" in response_data["message"]

    @pytest.mark.asyncio
    async def test_github_add_labels_single_label(self) -> None:
        """Test adding a single label."""
        issue_number = 200
        labels = ["documentation"]

        with patch(
            "maverick.tools.github.tools.issues.run_gh_command",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.return_value = ("", "", 0)

            result = await github_add_labels.handler(
                {
                    "issue_number": issue_number,
                    "labels": labels,
                }
            )

        # Verify command structure
        call_args = mock_run.call_args[0]
        assert "issue" in call_args
        assert "edit" in call_args
        assert str(issue_number) in call_args
        assert "--add-label" in call_args
        assert "documentation" in call_args

        # Verify success response
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["success"] is True
        assert response_data["labels_added"] == labels


class TestGithubGetIssue:
    """Tests for github_get_issue MCP tool."""

    @pytest.mark.asyncio
    async def test_github_get_issue_success(self) -> None:
        """Test github_get_issue success case with full issue details (T019)."""
        # Mock issue data with nested objects
        issue_data = {
            "number": 42,
            "title": "Critical bug in authentication",
            "body": (
                "Users cannot log in after recent update.\n\n"
                "Steps to reproduce:\n1. Open app\n2. Try to log in"
            ),
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
            "maverick.tools.github.tools.issues.run_gh_command",
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
            "maverick.tools.github.tools.issues.run_gh_command",
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
    async def test_github_get_issue_not_found_specific_message(self) -> None:
        """Test github_get_issue with specific 'not found' message (lines 455-456)."""
        stdout = ""
        stderr = "issue not found"
        return_code = 1

        with patch(
            "maverick.tools.github.tools.issues.run_gh_command",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.return_value = (stdout, stderr, return_code)

            result = await github_get_issue.handler({"issue_number": 777})

        # Verify error response with specific message
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["isError"] is True
        assert response_data["error_code"] == "NOT_FOUND"
        assert "Issue #777 not found" in response_data["message"]

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
            "maverick.tools.github.tools.issues.run_gh_command",
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
            "maverick.tools.github.tools.issues.run_gh_command",
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
            "maverick.tools.github.tools.issues.run_gh_command",
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
            "maverick.tools.github.tools.issues.run_gh_command",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.return_value = (stdout, stderr, return_code)

            result = await github_get_issue.handler({"issue_number": 42})

        # Verify error response
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["isError"] is True
        assert response_data["error_code"] == "INTERNAL_ERROR"
        assert "parse" in response_data["message"].lower()


class TestGitHubCloseIssue:
    """Tests for github_close_issue tool (T042-T044)."""

    @pytest.mark.asyncio
    async def test_github_close_issue_with_comment(self) -> None:
        """Test closing issue with a comment (T042).

        Verifies:
        - Issue successfully closed with comment
        - Success response with correct fields
        - gh command called with comment argument
        """
        issue_number = 123
        comment = "Fixed in PR #456"

        with patch(
            "maverick.tools.github.tools.issues.run_gh_command",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.return_value = ("", "", 0)

            result = await github_close_issue.handler(
                {
                    "issue_number": issue_number,
                    "comment": comment,
                }
            )

        # Verify gh command called with correct arguments
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0]
        assert "issue" in call_args
        assert "close" in call_args
        assert str(issue_number) in call_args
        assert "--comment" in call_args
        assert comment in call_args

        # Verify response structure
        assert "content" in result
        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "text"

        # Parse response data
        response_data = json.loads(result["content"][0]["text"])

        # Verify success response fields
        assert response_data["success"] is True
        assert response_data["issue_number"] == issue_number
        assert response_data["state"] == "closed"

    @pytest.mark.asyncio
    async def test_github_close_issue_without_comment(self) -> None:
        """Test closing issue without providing a comment (T043).

        Verifies:
        - Issue successfully closed without comment
        - gh command called without comment argument
        - Success response with correct fields
        """
        issue_number = 789

        with patch(
            "maverick.tools.github.tools.issues.run_gh_command",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.return_value = ("", "", 0)

            result = await github_close_issue.handler(
                {
                    "issue_number": issue_number,
                }
            )

        # Verify gh command called without comment
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0]
        assert "issue" in call_args
        assert "close" in call_args
        assert str(issue_number) in call_args
        assert "--comment" not in call_args

        # Parse response data
        response_data = json.loads(result["content"][0]["text"])

        # Verify success response
        assert response_data["success"] is True
        assert response_data["issue_number"] == issue_number
        assert response_data["state"] == "closed"

    @pytest.mark.asyncio
    async def test_github_close_issue_already_closed(self) -> None:
        """Test closing an already-closed issue is idempotent (T044).

        Verifies:
        - Already-closed issues return success (not error)
        - Response indicates closed state
        - Idempotent behavior
        """
        issue_number = 456

        with patch(
            "maverick.tools.github.tools.issues.run_gh_command",
            new_callable=AsyncMock,
        ) as mock_run:
            # Mock gh CLI response when issue is already closed
            mock_run.return_value = ("", "issue is already closed", 1)

            result = await github_close_issue.handler(
                {
                    "issue_number": issue_number,
                }
            )

        # Verify gh command was called
        mock_run.assert_called_once()

        # Parse response data
        response_data = json.loads(result["content"][0]["text"])

        # Verify idempotent success response (not an error)
        assert response_data["success"] is True
        assert response_data["issue_number"] == issue_number
        assert response_data["state"] == "closed"

    @pytest.mark.asyncio
    async def test_github_close_issue_invalid_number(self) -> None:
        """Test closing issue with invalid issue number returns error.

        Verifies:
        - Invalid issue_number (<=0) returns INVALID_INPUT error
        - No gh command executed
        """
        result = await github_close_issue.handler({"issue_number": 0})

        # Parse error response
        response_data = json.loads(result["content"][0]["text"])

        # Verify error response
        assert response_data["isError"] is True
        assert response_data["error_code"] == "INVALID_INPUT"
        assert "positive" in response_data["message"].lower()

    @pytest.mark.asyncio
    async def test_github_close_issue_not_found(self) -> None:
        """Test closing non-existent issue returns NOT_FOUND error.

        Verifies:
        - Issue not found (404) returns NOT_FOUND error
        - Error message includes issue number
        """
        issue_number = 999

        with patch(
            "maverick.tools.github.tools.issues.run_gh_command",
            new_callable=AsyncMock,
        ) as mock_run:
            # Mock gh CLI response for non-existent issue
            mock_run.return_value = ("", "issue not found", 1)

            result = await github_close_issue.handler(
                {
                    "issue_number": issue_number,
                }
            )

        # Parse error response
        response_data = json.loads(result["content"][0]["text"])

        # Verify error response
        assert response_data["isError"] is True
        assert response_data["error_code"] == "NOT_FOUND"
        assert str(issue_number) in response_data["message"]

    @pytest.mark.asyncio
    async def test_github_close_issue_timeout(self) -> None:
        """Test github_close_issue handles timeout error."""
        import asyncio

        with patch(
            "maverick.tools.github.tools.issues.run_gh_command",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.side_effect = asyncio.TimeoutError("Operation timed out")

            result = await github_close_issue.handler({"issue_number": 100})

        # Verify error response
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["isError"] is True
        assert response_data["error_code"] == "TIMEOUT"

    @pytest.mark.asyncio
    async def test_github_close_issue_unexpected_exception(self) -> None:
        """Test github_close_issue handles unexpected exceptions."""
        with patch(
            "maverick.tools.github.tools.issues.run_gh_command",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.side_effect = Exception("Unexpected error")

            result = await github_close_issue.handler({"issue_number": 100})

        # Verify error response
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["isError"] is True
        assert response_data["error_code"] == "INTERNAL_ERROR"
