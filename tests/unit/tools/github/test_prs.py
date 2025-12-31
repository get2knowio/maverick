"""Unit tests for GitHub PR MCP tools.

Tests input validation and error handling for PR-related GitHub tools.
After PyGithub migration, these tests focus on validation logic rather
than mocking the underlying CLI implementation.
"""

from __future__ import annotations

import json

import pytest

from maverick.tools.github import (
    github_create_pr,
    github_pr_status,
)


class TestGitHubPrStatus:
    """Tests for github_pr_status MCP tool."""

    @pytest.mark.asyncio
    async def test_github_pr_status_invalid_input(self) -> None:
        """Test github_pr_status rejects invalid PR number."""
        result = await github_pr_status.handler({"pr_number": 0})

        # Parse response
        response_data = json.loads(result["content"][0]["text"])

        # Verify error response
        assert response_data["isError"] is True
        assert response_data["error_code"] == "INVALID_INPUT"


class TestGitHubCreatePR:
    """Tests for github_create_pr MCP tool."""

    @pytest.mark.asyncio
    async def test_github_create_pr_empty_title(self) -> None:
        """Test github_create_pr rejects empty title (T030)."""
        result = await github_create_pr.handler(
            {"title": "", "body": "PR body", "base": "main", "head": "feature"}
        )

        # Parse response
        response_data = json.loads(result["content"][0]["text"])

        # Verify error response
        assert response_data["isError"] is True
        assert response_data["error_code"] == "INVALID_INPUT"

    @pytest.mark.asyncio
    async def test_github_create_pr_empty_body(self) -> None:
        """Test github_create_pr rejects empty body (T030)."""
        result = await github_create_pr.handler(
            {"title": "PR Title", "body": "", "base": "main", "head": "feature"}
        )

        # Parse response
        response_data = json.loads(result["content"][0]["text"])

        # Verify error response
        assert response_data["isError"] is True
        assert response_data["error_code"] == "INVALID_INPUT"

    @pytest.mark.asyncio
    async def test_github_create_pr_whitespace_title(self) -> None:
        """Test github_create_pr rejects whitespace-only title (T030)."""
        result = await github_create_pr.handler(
            {"title": "   ", "body": "PR body", "base": "main", "head": "feature"}
        )

        # Parse response
        response_data = json.loads(result["content"][0]["text"])

        # Verify error response
        assert response_data["isError"] is True
        assert response_data["error_code"] == "INVALID_INPUT"

    @pytest.mark.asyncio
    async def test_github_create_pr_whitespace_body(self) -> None:
        """Test github_create_pr rejects whitespace-only body (T030)."""
        result = await github_create_pr.handler(
            {"title": "PR Title", "body": "   ", "base": "main", "head": "feature"}
        )

        # Parse response
        response_data = json.loads(result["content"][0]["text"])

        # Verify error response
        assert response_data["isError"] is True
        assert response_data["error_code"] == "INVALID_INPUT"
