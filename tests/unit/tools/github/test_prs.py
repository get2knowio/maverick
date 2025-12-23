"""Unit tests for GitHub PR MCP tools.

Tests the github_pr_status and github_create_pr tools.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from maverick.tools.github import (
    github_create_pr,
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
            "maverick.tools.github.tools.prs.run_gh_command", new_callable=AsyncMock
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
            "maverick.tools.github.tools.prs.run_gh_command", new_callable=AsyncMock
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
            "maverick.tools.github.tools.prs.run_gh_command", new_callable=AsyncMock
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
        # CONFLICTING converted to False
        assert response_data["mergeable"] is False
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
            "maverick.tools.github.tools.prs.run_gh_command", new_callable=AsyncMock
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
            "maverick.tools.github.tools.prs.run_gh_command", new_callable=AsyncMock
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
            "maverick.tools.github.tools.prs.run_gh_command", new_callable=AsyncMock
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
            "maverick.tools.github.tools.prs.run_gh_command", new_callable=AsyncMock
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
            "maverick.tools.github.tools.prs.run_gh_command", new_callable=AsyncMock
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
            "maverick.tools.github.tools.prs.run_gh_command", new_callable=AsyncMock
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
            "maverick.tools.github.tools.prs.run_gh_command",
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
            "maverick.tools.github.tools.prs.run_gh_command",
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
            "maverick.tools.github.tools.prs.run_gh_command",
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
            "maverick.tools.github.tools.prs.run_gh_command",
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
