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

        with patch(
            "maverick.tools.github._run_gh_command", new_callable=AsyncMock
        ) as mock_run:
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

        with patch(
            "maverick.tools.github._run_gh_command", new_callable=AsyncMock
        ) as mock_run:
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

        with patch(
            "maverick.tools.github._run_gh_command", new_callable=AsyncMock
        ) as mock_run:
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

        with patch(
            "maverick.tools.github._run_gh_command", new_callable=AsyncMock
        ) as mock_run:
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

        with patch(
            "maverick.tools.github._run_gh_command", new_callable=AsyncMock
        ) as mock_run:
            mock_run.return_value = (json.dumps(mock_pr_data), "", 0)

            result = await github_pr_status.handler({"pr_number": pr_number})

        # Parse response data
        response_data = json.loads(result["content"][0]["text"])

        # Verify empty lists
        assert response_data["reviews"] == []
        assert response_data["checks"] == []
        assert response_data["has_conflicts"] is False

    @pytest.mark.asyncio
    async def test_github_pr_status_mergeable_unknown(self) -> None:
        """Test github_pr_status when mergeable status is UNKNOWN (line 611)."""
        pr_number = 200

        # Mock response: PR with UNKNOWN mergeable status
        mock_pr_data = {
            "number": pr_number,
            "state": "OPEN",
            "mergeable": "UNKNOWN",
            "mergeStateStatus": "UNKNOWN",
            "headRefName": "feature/unknown",
            "baseRefName": "main",
            "reviews": [],
            "statusCheckRollup": [],
        }

        with patch(
            "maverick.tools.github._run_gh_command", new_callable=AsyncMock
        ) as mock_run:
            mock_run.return_value = (json.dumps(mock_pr_data), "", 0)

            result = await github_pr_status.handler({"pr_number": pr_number})

        # Parse response data
        response_data = json.loads(result["content"][0]["text"])

        # Verify mergeable is None for UNKNOWN
        assert response_data["mergeable"] is None
        assert response_data["merge_state_status"] == "unknown"
        assert response_data["has_conflicts"] is False

    @pytest.mark.asyncio
    async def test_github_pr_status_mergeable_null(self) -> None:
        """Test github_pr_status when mergeable is null (line 611)."""
        pr_number = 300

        # Mock response: PR with null mergeable status
        mock_pr_data = {
            "number": pr_number,
            "state": "OPEN",
            "mergeable": None,
            "mergeStateStatus": "PENDING",
            "headRefName": "feature/null",
            "baseRefName": "main",
            "reviews": [],
            "statusCheckRollup": [],
        }

        with patch(
            "maverick.tools.github._run_gh_command", new_callable=AsyncMock
        ) as mock_run:
            mock_run.return_value = (json.dumps(mock_pr_data), "", 0)

            result = await github_pr_status.handler({"pr_number": pr_number})

        # Parse response data
        response_data = json.loads(result["content"][0]["text"])

        # Verify mergeable is None for null
        assert response_data["mergeable"] is None
        assert response_data["merge_state_status"] == "pending"
        assert response_data["has_conflicts"] is False

    @pytest.mark.asyncio
    async def test_github_pr_status_mergeable_true_boolean(self) -> None:
        """Test github_pr_status when mergeable is True boolean (line 606)."""
        pr_number = 400

        # Mock response: PR with True mergeable status
        mock_pr_data = {
            "number": pr_number,
            "state": "OPEN",
            "mergeable": True,
            "mergeStateStatus": "CLEAN",
            "headRefName": "feature/bool-true",
            "baseRefName": "main",
            "reviews": [],
            "statusCheckRollup": [],
        }

        with patch(
            "maverick.tools.github._run_gh_command", new_callable=AsyncMock
        ) as mock_run:
            mock_run.return_value = (json.dumps(mock_pr_data), "", 0)

            result = await github_pr_status.handler({"pr_number": pr_number})

        # Parse response data
        response_data = json.loads(result["content"][0]["text"])

        # Verify mergeable is True
        assert response_data["mergeable"] is True
        assert response_data["has_conflicts"] is False

    @pytest.mark.asyncio
    async def test_github_pr_status_mergeable_false_boolean(self) -> None:
        """Test github_pr_status when mergeable is False boolean (line 608)."""
        pr_number = 500

        # Mock response: PR with False mergeable status
        mock_pr_data = {
            "number": pr_number,
            "state": "OPEN",
            "mergeable": False,
            "mergeStateStatus": "DIRTY",
            "headRefName": "feature/bool-false",
            "baseRefName": "main",
            "reviews": [],
            "statusCheckRollup": [],
        }

        with patch(
            "maverick.tools.github._run_gh_command", new_callable=AsyncMock
        ) as mock_run:
            mock_run.return_value = (json.dumps(mock_pr_data), "", 0)

            result = await github_pr_status.handler({"pr_number": pr_number})

        # Parse response data
        response_data = json.loads(result["content"][0]["text"])

        # Verify mergeable is False
        assert response_data["mergeable"] is False
        assert response_data["has_conflicts"] is True


class TestGitHubCreatePR:
    """Tests for github_create_pr MCP tool (T011-T013)."""

    @pytest.mark.asyncio
    async def test_github_create_pr_success(self) -> None:
        """Test creating a PR successfully (T011)."""
        # Mock successful PR creation
        pr_url = "https://github.com/owner/repo/pull/123"
        stdout = pr_url
        stderr = ""
        return_code = 0

        with patch(
            "maverick.tools.github._run_gh_command",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.return_value = (stdout, stderr, return_code)

            result = await github_create_pr.handler(
                {
                    "title": "Add new feature",
                    "body": "This PR implements the new feature",
                    "base": "main",
                    "head": "feature/new-feature",
                    "draft": False,
                }
            )

        # Verify gh command called with correct arguments
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0]
        assert "pr" in call_args
        assert "create" in call_args
        assert "--title" in call_args
        assert "Add new feature" in call_args
        assert "--body" in call_args
        assert "This PR implements the new feature" in call_args
        assert "--base" in call_args
        assert "main" in call_args
        assert "--head" in call_args
        assert "feature/new-feature" in call_args
        assert "--draft" not in call_args

        # Verify response structure
        assert "content" in result
        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "text"

        # Parse response text
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["pr_number"] == 123
        assert response_data["url"] == pr_url
        assert response_data["state"] == "open"
        assert response_data["title"] == "Add new feature"

    @pytest.mark.asyncio
    async def test_github_create_pr_draft(self) -> None:
        """Test creating a draft PR (T012)."""
        # Mock successful draft PR creation
        pr_url = "https://github.com/owner/repo/pull/456"
        stdout = pr_url
        stderr = ""
        return_code = 0

        with patch(
            "maverick.tools.github._run_gh_command",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.return_value = (stdout, stderr, return_code)

            result = await github_create_pr.handler(
                {
                    "title": "WIP: Draft feature",
                    "body": "Work in progress PR",
                    "base": "main",
                    "head": "feature/draft",
                    "draft": True,
                }
            )

        # Verify gh command includes --draft flag
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0]
        assert "pr" in call_args
        assert "create" in call_args
        assert "--draft" in call_args
        assert "--title" in call_args
        assert "WIP: Draft feature" in call_args
        assert "--base" in call_args
        assert "main" in call_args
        assert "--head" in call_args
        assert "feature/draft" in call_args

        # Verify response indicates draft state
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["pr_number"] == 456
        assert response_data["state"] == "draft"
        assert response_data["title"] == "WIP: Draft feature"

    @pytest.mark.asyncio
    async def test_github_create_pr_branch_not_found(self) -> None:
        """Test error when branch doesn't exist (T013)."""
        # Mock branch not found error
        stdout = ""
        stderr = "error: head branch 'feature/nonexistent' not found"
        return_code = 1

        with patch(
            "maverick.tools.github._run_gh_command",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.return_value = (stdout, stderr, return_code)

            result = await github_create_pr.handler(
                {
                    "title": "Test PR",
                    "body": "Test body",
                    "base": "main",
                    "head": "feature/nonexistent",
                    "draft": False,
                }
            )

        # Verify error response
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["isError"] is True
        assert response_data["error_code"] == "BRANCH_NOT_FOUND"
        assert "feature/nonexistent" in response_data["message"]

    @pytest.mark.asyncio
    async def test_github_create_pr_base_branch_not_found(self) -> None:
        """Test error when base branch doesn't exist."""
        # Mock base branch not found error
        stdout = ""
        stderr = "error: base branch 'nonexistent' not found"
        return_code = 1

        with patch(
            "maverick.tools.github._run_gh_command",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.return_value = (stdout, stderr, return_code)

            result = await github_create_pr.handler(
                {
                    "title": "Test PR",
                    "body": "Test body",
                    "base": "nonexistent",
                    "head": "feature/test",
                    "draft": False,
                }
            )

        # Verify error response
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["isError"] is True
        assert response_data["error_code"] == "BRANCH_NOT_FOUND"
        assert "nonexistent" in response_data["message"]

    @pytest.mark.asyncio
    async def test_github_create_pr_empty_title(self) -> None:
        """Test validation error for empty title."""
        result = await github_create_pr.handler(
            {
                "title": "",
                "body": "Valid body",
                "base": "main",
                "head": "feature/test",
                "draft": False,
            }
        )

        # Verify error response
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["isError"] is True
        assert response_data["error_code"] == "INVALID_INPUT"
        assert "title" in response_data["message"].lower()
        assert "empty" in response_data["message"].lower()

    @pytest.mark.asyncio
    async def test_github_create_pr_empty_body(self) -> None:
        """Test validation error for empty body."""
        result = await github_create_pr.handler(
            {
                "title": "Valid title",
                "body": "",
                "base": "main",
                "head": "feature/test",
                "draft": False,
            }
        )

        # Verify error response
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["isError"] is True
        assert response_data["error_code"] == "INVALID_INPUT"
        assert "body" in response_data["message"].lower()
        assert "empty" in response_data["message"].lower()

    @pytest.mark.asyncio
    async def test_github_create_pr_whitespace_title(self) -> None:
        """Test validation error for whitespace-only title."""
        result = await github_create_pr.handler(
            {
                "title": "   ",
                "body": "Valid body",
                "base": "main",
                "head": "feature/test",
                "draft": False,
            }
        )

        # Verify error response
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["isError"] is True
        assert response_data["error_code"] == "INVALID_INPUT"
        assert "title" in response_data["message"].lower()

    @pytest.mark.asyncio
    async def test_github_create_pr_whitespace_body(self) -> None:
        """Test validation error for whitespace-only body."""
        result = await github_create_pr.handler(
            {
                "title": "Valid title",
                "body": "   ",
                "base": "main",
                "head": "feature/test",
                "draft": False,
            }
        )

        # Verify error response
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["isError"] is True
        assert response_data["error_code"] == "INVALID_INPUT"
        assert "body" in response_data["message"].lower()


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
            "maverick.tools.github._run_gh_command",
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
            "maverick.tools.github._run_gh_command",
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
            "maverick.tools.github._run_gh_command",
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
            "maverick.tools.github._run_gh_command",
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
            "maverick.tools.github._run_gh_command",
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
            "maverick.tools.github._run_gh_command",
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
            "maverick.tools.github._run_gh_command",
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
    async def test_github_get_issue_not_found_specific_message(self) -> None:
        """Test github_get_issue with specific 'not found' message (lines 455-456)."""
        stdout = ""
        stderr = "issue not found"
        return_code = 1

        with patch(
            "maverick.tools.github._run_gh_command",
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
            "maverick.tools.github._run_gh_command",
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
            "maverick.tools.github._run_gh_command",
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
            "maverick.tools.github._run_gh_command",
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
            "maverick.tools.github._run_gh_command",
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
            "maverick.tools.github._run_gh_command",
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
# T031-T033: github_get_pr_diff Tests
# =============================================================================


class TestGitHubGetPRDiff:
    """Tests for github_get_pr_diff tool (T031-T033)."""

    @pytest.mark.asyncio
    async def test_github_get_pr_diff_normal_retrieval(self) -> None:
        """Test getting a PR diff successfully with mocked gh CLI (T031).

        Verifies:
        - Successful diff retrieval
        - Correct command execution
        - Proper response structure
        - truncated=false for small diffs
        """
        pr_number = 123
        mock_diff = """diff --git a/file.py b/file.py
index 1234567..abcdefg 100644
--- a/file.py
+++ b/file.py
@@ -1,3 +1,4 @@
+# New comment
 def hello():
     print("Hello, World!")
"""

        with patch(
            "maverick.tools.github._run_gh_command", new_callable=AsyncMock
        ) as mock_run:
            mock_run.return_value = (mock_diff, "", 0)

            result = await github_get_pr_diff.handler({"pr_number": pr_number})

            # Verify command execution
            mock_run.assert_called_once()
            call_args = mock_run.call_args[0]
            assert call_args[0] == "pr"
            assert call_args[1] == "diff"
            assert call_args[2] == str(pr_number)

        # Verify success response structure
        assert "content" in result
        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "text"

        # Parse response data
        response_data = json.loads(result["content"][0]["text"])

        # Verify response fields
        assert "diff" in response_data
        assert response_data["diff"] == mock_diff
        assert response_data["truncated"] is False
        assert "warning" not in response_data
        assert "original_size_bytes" not in response_data

    @pytest.mark.asyncio
    async def test_github_get_pr_diff_truncated_case(self) -> None:
        """Test that large diffs are truncated properly with truncated flag (T032).

        Verifies:
        - Diff truncated at max_size boundary
        - truncated=true flag set
        - Warning message included
        - original_size_bytes included
        """
        pr_number = 456
        # Create a large diff (larger than default 100KB)
        large_diff = (
            "diff --git a/file.py b/file.py\n" + ("+" + "x" * 1000 + "\n") * 150
        )  # ~150KB
        max_size = 50000  # 50KB limit

        with patch(
            "maverick.tools.github._run_gh_command", new_callable=AsyncMock
        ) as mock_run:
            mock_run.return_value = (large_diff, "", 0)

            result = await github_get_pr_diff.handler(
                {"pr_number": pr_number, "max_size": max_size}
            )

            # Verify command execution
            mock_run.assert_called_once()

        # Parse response data
        response_data = json.loads(result["content"][0]["text"])

        # Verify truncation
        assert response_data["truncated"] is True
        assert "warning" in response_data
        assert "truncated" in response_data["warning"].lower()
        assert "original_size_bytes" in response_data
        assert response_data["original_size_bytes"] == len(large_diff.encode("utf-8"))

        # Verify diff was actually truncated
        diff_size = len(response_data["diff"].encode("utf-8"))
        assert diff_size <= max_size
        original_size = response_data["original_size_bytes"]
        assert original_size > max_size

    @pytest.mark.asyncio
    async def test_github_get_pr_diff_not_found(self) -> None:
        """Test error handling when PR doesn't exist (T033).

        Verifies:
        - NOT_FOUND error code
        - Proper error message with PR number
        - Error response structure
        """
        pr_number = 999

        with patch(
            "maverick.tools.github._run_gh_command", new_callable=AsyncMock
        ) as mock_run:
            mock_run.return_value = ("", "pull request not found", 1)

            result = await github_get_pr_diff.handler({"pr_number": pr_number})

        # Parse error response
        response_data = json.loads(result["content"][0]["text"])

        # Verify error response
        assert response_data["isError"] is True
        assert response_data["error_code"] == "NOT_FOUND"
        assert (
            f"#{pr_number}" in response_data["message"]
            or str(pr_number) in response_data["message"]
        )
        assert "not found" in response_data["message"].lower()

    @pytest.mark.asyncio
    async def test_github_get_pr_diff_utf8_truncation(self) -> None:
        """Test UTF-8 truncation works correctly with multibyte characters.

        Verifies:
        - Diff with multibyte UTF-8 characters truncated at byte boundary
        - No broken characters in truncated output
        - Proper handling of UTF-8 decoding errors
        """
        pr_number = 789
        # Create diff with multibyte UTF-8 characters (emoji, Chinese, etc.)
        unicode_diff = "diff --git a/file.py b/file.py\n"
        unicode_diff += "+# Unicode test: 🚀 火箭 αβγδ " + "x" * 5000 + "\n"
        unicode_diff += "+# More content: 中文字符 " + "y" * 5000 + "\n"

        # Set max_size to potentially split in the middle of multibyte char
        max_size = 5100

        with patch(
            "maverick.tools.github._run_gh_command", new_callable=AsyncMock
        ) as mock_run:
            mock_run.return_value = (unicode_diff, "", 0)

            result = await github_get_pr_diff.handler(
                {"pr_number": pr_number, "max_size": max_size}
            )

        response_data = json.loads(result["content"][0]["text"])

        # Verify truncation occurred
        assert response_data["truncated"] is True

        # Verify the truncated diff is valid UTF-8 (no broken characters)
        truncated_diff = response_data["diff"]
        # Should be able to encode back to UTF-8 without errors
        encoded = truncated_diff.encode("utf-8")
        assert len(encoded) <= max_size

        # Verify no broken characters by checking we can decode what we encoded
        assert encoded.decode("utf-8") == truncated_diff

    @pytest.mark.asyncio
    async def test_github_get_pr_diff_invalid_pr_number(self) -> None:
        """Test invalid pr_number (<=0) returns INVALID_INPUT error.

        Verifies:
        - Negative PR numbers rejected
        - Zero PR number rejected
        - INVALID_INPUT error code
        - Appropriate error message
        """
        # Test with negative number
        result = await github_get_pr_diff.handler({"pr_number": -1})

        response_data = json.loads(result["content"][0]["text"])
        assert response_data["isError"] is True
        assert response_data["error_code"] == "INVALID_INPUT"
        assert "positive" in response_data["message"].lower()

        # Test with zero
        result = await github_get_pr_diff.handler({"pr_number": 0})

        response_data = json.loads(result["content"][0]["text"])
        assert response_data["isError"] is True
        assert response_data["error_code"] == "INVALID_INPUT"
        assert "positive" in response_data["message"].lower()


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
        """Test _run_gh_command handles timeout correctly (lines 65-87)."""
        import asyncio

        from maverick.tools.github import _run_gh_command

        # Mock process that times out
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_process.kill = AsyncMock()
        mock_process.wait = AsyncMock()

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with pytest.raises(asyncio.TimeoutError):
                await _run_gh_command("pr", "list", timeout=0.1)

            # Verify process was killed
            mock_process.kill.assert_called_once()
            mock_process.wait.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_gh_command_success(self) -> None:
        """Test _run_gh_command successful execution (lines 83-87)."""
        from maverick.tools.github import _run_gh_command

        # Mock successful process
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"output data", b""))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            stdout, stderr, return_code = await _run_gh_command("pr", "list")

            # Verify return values
            assert stdout == "output data"
            assert stderr == ""
            assert return_code == 0

    @pytest.mark.asyncio
    async def test_run_gh_command_error_with_stderr(self) -> None:
        """Test _run_gh_command with non-zero return code (lines 83-87)."""
        from maverick.tools.github import _run_gh_command

        # Mock process with error
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"", b"error message"))
        mock_process.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            stdout, stderr, return_code = await _run_gh_command("pr", "list")

            # Verify return values
            assert stdout == ""
            assert stderr == "error message"
            assert return_code == 1

    @pytest.mark.asyncio
    async def test_run_gh_command_none_returncode(self) -> None:
        """Test _run_gh_command handles None returncode (lines 85)."""
        from maverick.tools.github import _run_gh_command

        # Mock process with None returncode
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"output", b""))
        mock_process.returncode = None

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            stdout, stderr, return_code = await _run_gh_command("pr", "list")

            # Verify return_code defaults to 0 when None
            assert return_code == 0

    @pytest.mark.asyncio
    async def test_github_create_pr_timeout(self) -> None:
        """Test github_create_pr handles timeout error (lines 352-357)."""
        import asyncio

        with patch(
            "maverick.tools.github._run_gh_command",
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
            "maverick.tools.github._run_gh_command",
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
            "maverick.tools.github._run_gh_command",
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
            "maverick.tools.github._run_gh_command",
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
            "maverick.tools.github._run_gh_command",
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
            "maverick.tools.github._run_gh_command",
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
            "maverick.tools.github._run_gh_command",
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
            "maverick.tools.github._run_gh_command",
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
            "maverick.tools.github._run_gh_command",
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
            "maverick.tools.github._run_gh_command",
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
            "maverick.tools.github._run_gh_command",
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
            "maverick.tools.github._run_gh_command",
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
            "maverick.tools.github._run_gh_command",
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

        with (
            patch(
                "asyncio.create_subprocess_exec",
                side_effect=mock_subprocess_exec,
            ),
            patch(
                "maverick.tools.github._run_gh_command",
                new_callable=AsyncMock,
                return_value=("Logged in as user", "", 0),
            ),
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
            mock_process.communicate = AsyncMock(
                return_value=(b"gh version 2.0.0", b"")
            )
            mock_process.returncode = 0
            return mock_process

        with (
            patch(
                "asyncio.create_subprocess_exec",
                side_effect=mock_subprocess_exec,
            ),
            patch(
                "maverick.tools.github._run_gh_command",
                new_callable=AsyncMock,
                return_value=("", "You are not logged into any GitHub hosts", 1),
            ),
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
                mock_process.communicate = AsyncMock(
                    return_value=(b"gh version 2.0.0", b"")
                )
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

        with (
            patch(
                "asyncio.create_subprocess_exec",
                side_effect=mock_subprocess_exec,
            ),
            patch(
                "maverick.tools.github._run_gh_command",
                new_callable=AsyncMock,
                return_value=("Logged in as user", "", 0),
            ),
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
                mock_process.communicate = AsyncMock(
                    return_value=(b"gh version 2.0.0", b"")
                )
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

        with (
            patch(
                "asyncio.create_subprocess_exec",
                side_effect=mock_subprocess_exec,
            ),
            patch(
                "maverick.tools.github._run_gh_command",
                new_callable=AsyncMock,
                return_value=("Logged in as user", "", 0),
            ),
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

    @pytest.mark.asyncio
    async def test_verify_prerequisites_git_not_installed(self) -> None:
        """Test git not found (FileNotFoundError)."""
        from maverick.exceptions import GitHubToolsError
        from maverick.tools.github import _verify_prerequisites

        call_count = 0

        async def mock_subprocess_exec(*args, **kwargs):
            """Mock subprocess: gh succeeds, git fails with FileNotFoundError."""
            nonlocal call_count
            call_count += 1

            mock_process = AsyncMock()
            command = args[0]

            if command == "gh":
                # gh --version succeeds
                mock_process.communicate = AsyncMock(
                    return_value=(b"gh version 2.0.0", b"")
                )
                mock_process.returncode = 0
                return mock_process
            elif command == "git":
                # git not found
                raise FileNotFoundError("git command not found")

            return mock_process

        with (
            patch(
                "asyncio.create_subprocess_exec",
                side_effect=mock_subprocess_exec,
            ),
            patch(
                "maverick.tools.github._run_gh_command",
                new_callable=AsyncMock,
                return_value=("Logged in as user", "", 0),
            ),
        ):
            with pytest.raises(GitHubToolsError) as exc_info:
                await _verify_prerequisites()

            assert exc_info.value.check_failed == "git_installed"
            assert "git" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_verify_prerequisites_git_timeout(self) -> None:
        """Test git rev-parse times out."""
        import asyncio

        from maverick.exceptions import GitHubToolsError
        from maverick.tools.github import _verify_prerequisites

        call_count = 0

        async def mock_subprocess_exec(*args, **kwargs):
            """Mock subprocess: gh succeeds, git rev-parse times out."""
            nonlocal call_count
            call_count += 1

            mock_process = AsyncMock()
            command = args[0]

            if command == "gh":
                # gh --version succeeds
                mock_process.communicate = AsyncMock(
                    return_value=(b"gh version 2.0.0", b"")
                )
                mock_process.returncode = 0
            elif command == "git" and "rev-parse" in args:
                # git rev-parse times out
                mock_process.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
            else:
                # Other commands succeed
                mock_process.communicate = AsyncMock(return_value=(b"", b""))
                mock_process.returncode = 0

            return mock_process

        with (
            patch(
                "asyncio.create_subprocess_exec",
                side_effect=mock_subprocess_exec,
            ),
            patch(
                "maverick.tools.github._run_gh_command",
                new_callable=AsyncMock,
                return_value=("Logged in as user", "", 0),
            ),
        ):
            with pytest.raises(GitHubToolsError) as exc_info:
                await _verify_prerequisites()

            assert exc_info.value.check_failed == "git_repo"
            assert "timed out" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_verify_prerequisites_git_remote_timeout(self) -> None:
        """Test git remote get-url times out."""
        import asyncio

        from maverick.exceptions import GitHubToolsError
        from maverick.tools.github import _verify_prerequisites

        call_count = 0

        async def mock_subprocess_exec(*args, **kwargs):
            """Mock subprocess: gh and git rev-parse succeed, git remote times out."""
            nonlocal call_count
            call_count += 1

            mock_process = AsyncMock()
            command = args[0]

            if command == "gh":
                # gh --version succeeds
                mock_process.communicate = AsyncMock(
                    return_value=(b"gh version 2.0.0", b"")
                )
                mock_process.returncode = 0
            elif command == "git" and "remote" in args and "get-url" in args:
                # git remote get-url origin times out
                mock_process.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
            else:
                # Other commands succeed
                mock_process.communicate = AsyncMock(return_value=(b"", b""))
                mock_process.returncode = 0

            return mock_process

        with (
            patch(
                "asyncio.create_subprocess_exec",
                side_effect=mock_subprocess_exec,
            ),
            patch(
                "maverick.tools.github._run_gh_command",
                new_callable=AsyncMock,
                return_value=("Logged in as user", "", 0),
            ),
        ):
            with pytest.raises(GitHubToolsError) as exc_info:
                await _verify_prerequisites()

            assert exc_info.value.check_failed == "git_remote"
            assert "timed out" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_verify_prerequisites_gh_returncode_nonzero(self) -> None:
        """Test gh --version returns non-zero exit code."""
        from maverick.exceptions import GitHubToolsError
        from maverick.tools.github import _verify_prerequisites

        async def mock_subprocess_exec(*args, **kwargs):
            """Mock subprocess that returns non-zero for gh --version."""
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(b"", b"error"))
            mock_process.returncode = 1
            return mock_process

        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=mock_subprocess_exec,
        ):
            with pytest.raises(GitHubToolsError) as exc_info:
                await _verify_prerequisites()

            assert exc_info.value.check_failed == "gh_installed"
            assert "gh" in str(exc_info.value).lower()


# =============================================================================
# create_github_tools_server Tests (T008)
# =============================================================================


class TestCreateGitHubToolsServer:
    """Tests for create_github_tools_server factory function (T008)."""

    def test_create_github_tools_server_skip_verification(self) -> None:
        """Test create_github_tools_server with skip_verification=True."""
        from maverick.tools.github import create_github_tools_server

        # Should succeed without checking prerequisites
        server = create_github_tools_server(skip_verification=True)

        # Verify server is created
        assert server is not None

    def test_create_github_tools_server_async_context_error(self) -> None:
        """Test create_github_tools_server raises error when called from
        async context (lines 785-816).
        """
        import asyncio

        from maverick.exceptions import GitHubToolsError
        from maverick.tools.github import create_github_tools_server

        async def async_caller():
            """Try to call create_github_tools_server from async context."""
            # Should raise GitHubToolsError because we're in async context
            with pytest.raises(GitHubToolsError) as exc_info:
                create_github_tools_server(skip_verification=False)

            # Verify error details
            assert exc_info.value.check_failed == "async_context"
            assert "async context" in str(exc_info.value).lower()
            assert "skip_verification=True" in str(exc_info.value)

        # Run the async test
        asyncio.run(async_caller())

    def test_create_github_tools_server_with_verification_success(self) -> None:
        """Test create_github_tools_server runs verification when not skipped."""
        from maverick.tools.github import create_github_tools_server

        # Mock successful subprocess calls
        async def mock_subprocess_exec(*args, **kwargs):
            """Mock successful subprocess execution."""
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(b"", b""))
            mock_process.returncode = 0
            return mock_process

        with (
            patch(
                "asyncio.create_subprocess_exec",
                side_effect=mock_subprocess_exec,
            ),
            patch(
                "maverick.tools.github._run_gh_command",
                new_callable=AsyncMock,
                return_value=("Logged in as user", "", 0),
            ),
        ):
            # Should succeed when prerequisites are met
            server = create_github_tools_server(skip_verification=False)
            assert server is not None

    def test_create_github_tools_server_with_verification_failure(self) -> None:
        """Test create_github_tools_server raises error when prerequisites fail."""
        from maverick.exceptions import GitHubToolsError
        from maverick.tools.github import create_github_tools_server

        # Mock failed gh CLI check
        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("gh command not found"),
        ):
            with pytest.raises(GitHubToolsError) as exc_info:
                create_github_tools_server(skip_verification=False)

            assert exc_info.value.check_failed == "gh_installed"


# =============================================================================
# github_close_issue Tests (T042-T044)
# =============================================================================


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
            "maverick.tools.github._run_gh_command",
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
            "maverick.tools.github._run_gh_command",
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
            "maverick.tools.github._run_gh_command",
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
            "maverick.tools.github._run_gh_command",
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
            "maverick.tools.github._run_gh_command",
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
            "maverick.tools.github._run_gh_command",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.side_effect = Exception("Unexpected error")

            result = await github_close_issue.handler({"issue_number": 100})

        # Verify error response
        response_data = json.loads(result["content"][0]["text"])
        assert response_data["isError"] is True
        assert response_data["error_code"] == "INTERNAL_ERROR"
        assert "Unexpected error" in response_data["message"]
