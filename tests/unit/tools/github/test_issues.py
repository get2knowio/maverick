"""Unit tests for GitHub issue MCP tools.

Tests input validation and error handling for issue-related GitHub tools.
After PyGithub migration, these tests focus on validation logic rather
than mocking the underlying CLI implementation.
"""

from __future__ import annotations

import json

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
    async def test_github_list_issues_invalid_state(self) -> None:
        """Test github_list_issues rejects invalid state (T020)."""
        result = await github_list_issues.handler(
            {"label": "bug", "state": "invalid", "limit": 30}
        )

        # Parse response
        response_data = json.loads(result["content"][0]["text"])

        # Verify error response
        assert response_data["isError"] is True
        assert response_data["error_code"] == "INVALID_INPUT"
        assert "state" in response_data["message"].lower()

    @pytest.mark.asyncio
    async def test_github_list_issues_invalid_limit(self) -> None:
        """Test github_list_issues rejects invalid limit (T020)."""
        result = await github_list_issues.handler(
            {"label": "bug", "state": "open", "limit": 0}
        )

        # Parse response
        response_data = json.loads(result["content"][0]["text"])

        # Verify error response
        assert response_data["isError"] is True
        assert response_data["error_code"] == "INVALID_INPUT"


class TestGitHubAddLabels:
    """Tests for github_add_labels MCP tool."""

    @pytest.mark.asyncio
    async def test_github_add_labels_empty_list_error(self) -> None:
        """Test github_add_labels rejects empty labels list (T044)."""
        result = await github_add_labels.handler({"issue_number": 123, "labels": []})

        # Parse response
        response_data = json.loads(result["content"][0]["text"])

        # Verify error response
        assert response_data["isError"] is True
        assert response_data["error_code"] == "INVALID_INPUT"

    @pytest.mark.asyncio
    async def test_github_add_labels_invalid_issue_number(self) -> None:
        """Test github_add_labels rejects invalid issue number (T044)."""
        result = await github_add_labels.handler({"issue_number": 0, "labels": ["bug"]})

        # Parse response
        response_data = json.loads(result["content"][0]["text"])

        # Verify error response
        assert response_data["isError"] is True
        assert response_data["error_code"] == "INVALID_INPUT"


class TestGithubGetIssue:
    """Tests for github_get_issue MCP tool."""

    @pytest.mark.asyncio
    async def test_github_get_issue_invalid_number(self) -> None:
        """Test github_get_issue rejects invalid issue number (T026)."""
        result = await github_get_issue.handler({"issue_number": 0})

        # Parse response
        response_data = json.loads(result["content"][0]["text"])

        # Verify error response
        assert response_data["isError"] is True
        assert response_data["error_code"] == "INVALID_INPUT"


class TestGitHubCloseIssue:
    """Tests for github_close_issue MCP tool."""

    @pytest.mark.asyncio
    async def test_github_close_issue_invalid_number(self) -> None:
        """Test github_close_issue rejects invalid issue number."""
        result = await github_close_issue.handler({"issue_number": -1})

        # Parse response
        response_data = json.loads(result["content"][0]["text"])

        # Verify error response
        assert response_data["isError"] is True
        assert response_data["error_code"] == "INVALID_INPUT"
