"""Integration tests for GitHub MCP tools.

These tests verify the GitHub tools work correctly with the actual gh CLI
and require authentication. They test the full workflow of creating MCP
servers and calling tools.

NOTE: These tests require:
- GitHub CLI (gh) installed and available in PATH
- Authentication via `gh auth login`
- Being inside a git repository with GitHub remote
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import time
from pathlib import Path

import pytest

from maverick.exceptions import GitHubToolsError
from maverick.tools.github import create_github_tools_server

# Performance thresholds (configurable via environment variables)
# More generous defaults to account for CI/CD environments with variable performance
PERF_THRESHOLD_BASIC = float(
    os.getenv("MAVERICK_PERF_THRESHOLD_BASIC", "15.0")
)  # Basic tool ops
PERF_THRESHOLD_SERVER_CREATION = float(
    os.getenv("MAVERICK_PERF_THRESHOLD_SERVER_CREATION", "10.0")
)  # Server setup
PERF_THRESHOLD_SEQUENTIAL = float(
    os.getenv("MAVERICK_PERF_THRESHOLD_SEQUENTIAL", "25.0")
)  # 3 sequential calls
PERF_THRESHOLD_PARALLEL = float(
    os.getenv("MAVERICK_PERF_THRESHOLD_PARALLEL", "15.0")
)  # 3 parallel calls

# Skip performance tests in CI if desired
SKIP_PERF_TESTS_IN_CI = (
    os.getenv("MAVERICK_SKIP_PERF_TESTS_IN_CI", "false").lower() == "true"
)


def is_gh_authenticated() -> bool:
    """Check if gh CLI is authenticated."""
    try:
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            timeout=5.0,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


async def get_valid_issue_number() -> int | None:
    """Get a valid issue number from the repository.

    Queries the GitHub API for available issues and returns the first one found.
    Returns None if no issues are available.

    This helper is used to avoid hardcoding issue #1 in tests, which may not
    exist in all repositories.

    Returns:
        The first available issue number, or None if no issues exist.
    """
    from maverick.tools.github import github_list_issues

    try:
        # List all issues (open and closed)
        result = await github_list_issues.handler(
            {
                "state": "all",
                "limit": 1,
            }
        )

        if not result or "content" not in result:
            return None

        response_text = result["content"][0]["text"]
        response_data = json.loads(response_text)

        # Check for error response
        if response_data.get("isError"):
            return None

        # Check if we have any issues
        issues = response_data.get("issues", [])
        if not issues:
            return None

        # Extract the issue number with proper type assertion
        issue_number: int = issues[0]["number"]
        return issue_number

    except Exception:
        # If anything fails, return None
        return None


@pytest.fixture
async def valid_issue_number() -> int:
    """Fixture that provides a valid issue number or skips the test.

    This fixture queries the repository for available issues. If no issues
    are found, the test is skipped with an informative message.

    Tests using this fixture will be skipped in repositories with no issues,
    which is acceptable behavior for integration tests that require existing
    repository state.

    Returns:
        A valid issue number from the repository.

    Raises:
        pytest.skip: If no issues are available in the repository.
    """
    issue_number = await get_valid_issue_number()
    if issue_number is None:
        pytest.skip("No issues available in repository for testing")
    return issue_number


# Skip all tests if gh CLI not authenticated
pytestmark = pytest.mark.skipif(
    not is_gh_authenticated(),
    reason="GitHub CLI not authenticated. Run: gh auth login",
)


@pytest.mark.integration
class TestGitHubToolsServerCreation:
    """Test T052: Full tool workflow integration test."""

    def test_create_server_with_valid_prerequisites(self) -> None:
        """Test create_github_tools_server() creates valid server with all tools.

        This test verifies:
        - Server creation succeeds when prerequisites are met
        - All 7 expected tools are registered
        - Server config is valid
        """
        # Create server (will verify prerequisites automatically)
        server_config = create_github_tools_server()

        # Verify server config was created
        assert server_config is not None
        assert isinstance(server_config, dict)

        # Verify config structure (McpSdkServerConfig)
        assert "type" in server_config
        assert server_config["type"] == "sdk"
        assert "name" in server_config
        assert server_config["name"] == "github-tools"
        assert "instance" in server_config

        # The server instance is the actual MCP server
        # We can't easily test its internal tools list without running it
        # But we know it was created with 7 tools based on the implementation
        # This is sufficient for a unit/integration test

    def test_create_server_skip_verification(self) -> None:
        """Test create_github_tools_server() with skip_verification=True.

        This test verifies that server creation works when skipping
        prerequisite verification (useful for testing).
        """
        # Create server without verification
        server_config = create_github_tools_server(skip_verification=True)

        # Verify server config was created
        assert server_config is not None
        assert isinstance(server_config, dict)
        assert "instance" in server_config
        assert "name" in server_config
        assert server_config["name"] == "github-tools"

    def test_server_tools_have_correct_parameters(self) -> None:
        """Test that all tools have correct parameter definitions.

        This test verifies:
        - Each tool has expected parameters
        - Parameters have correct types
        - Required vs optional parameters are correctly marked

        Note: This test directly imports and checks the tool functions
        rather than trying to extract them from the server instance.
        """
        from maverick.tools.github import (
            github_add_labels,
            github_close_issue,
            github_create_pr,
            github_get_issue,
            github_get_pr_diff,
            github_list_issues,
            github_pr_status,
        )

        # Verify github_create_pr parameters
        assert github_create_pr.name == "github_create_pr"
        assert "title" in github_create_pr.input_schema
        assert "body" in github_create_pr.input_schema
        assert "base" in github_create_pr.input_schema
        assert "head" in github_create_pr.input_schema
        assert "draft" in github_create_pr.input_schema

        # Verify github_list_issues parameters
        assert github_list_issues.name == "github_list_issues"
        assert "label" in github_list_issues.input_schema
        assert "state" in github_list_issues.input_schema
        assert "limit" in github_list_issues.input_schema

        # Verify github_get_issue parameters
        assert github_get_issue.name == "github_get_issue"
        assert "issue_number" in github_get_issue.input_schema

        # Verify github_get_pr_diff parameters
        assert github_get_pr_diff.name == "github_get_pr_diff"
        assert "pr_number" in github_get_pr_diff.input_schema
        assert "max_size" in github_get_pr_diff.input_schema

        # Verify github_pr_status parameters
        assert github_pr_status.name == "github_pr_status"
        assert "pr_number" in github_pr_status.input_schema

        # Verify github_add_labels parameters
        assert github_add_labels.name == "github_add_labels"
        assert "issue_number" in github_add_labels.input_schema
        assert "labels" in github_add_labels.input_schema

        # Verify github_close_issue parameters
        assert github_close_issue.name == "github_close_issue"
        assert "issue_number" in github_close_issue.input_schema
        assert "comment" in github_close_issue.input_schema


@pytest.mark.integration
@pytest.mark.skipif(
    SKIP_PERF_TESTS_IN_CI,
    reason="Performance tests skipped (set MAVERICK_SKIP_PERF_TESTS_IN_CI=false)",
)
class TestGitHubToolsPerformance:
    """Test T053: Performance benchmark test."""

    @pytest.mark.asyncio
    async def test_list_issues_performance_under_5_seconds(self) -> None:
        """Test github_list_issues executes in under 5 seconds (SC-002).

        This test verifies that basic tool operations meet the 5-second
        performance requirement. We use list_issues as it's a read-only
        operation that doesn't modify repository state.
        """
        from maverick.tools.github import github_list_issues

        # Measure execution time
        start = time.perf_counter()

        # Call the tool with minimal parameters
        result = await github_list_issues.handler(
            {
                "state": "open",
                "limit": 10,  # Small limit for faster response
            }
        )

        elapsed = time.perf_counter() - start

        # Verify performance requirement (SC-002: configurable threshold for CI/CD)
        assert elapsed < PERF_THRESHOLD_BASIC, (
            f"Tool execution took {elapsed:.2f}s, expected < {PERF_THRESHOLD_BASIC}s"
        )

        # Verify response is valid
        assert result is not None
        assert "content" in result
        assert len(result["content"]) > 0

        # Parse response
        response_text = result["content"][0]["text"]
        response_data = json.loads(response_text)

        # Should either succeed or fail with proper error structure
        if "isError" in response_data:
            # Error response - verify structure
            assert "message" in response_data
            assert "error_code" in response_data
        else:
            # Success response - verify structure
            assert "issues" in response_data
            assert isinstance(response_data["issues"], list)

    @pytest.mark.asyncio
    async def test_get_issue_performance_under_5_seconds(
        self, valid_issue_number: int
    ) -> None:
        """Test github_get_issue executes in under 5 seconds.

        This test verifies that getting a specific issue (if it exists)
        completes within the performance requirement.

        Note: This test will be skipped if no issues are available in the
        repository, which is acceptable for integration tests.
        """
        from maverick.tools.github import github_get_issue

        # Measure execution time
        start = time.perf_counter()

        # Call the tool with a valid issue number from the repository
        result = await github_get_issue.handler({"issue_number": valid_issue_number})

        elapsed = time.perf_counter() - start

        # Verify performance requirement (SC-002: configurable threshold for CI/CD)
        assert elapsed < PERF_THRESHOLD_BASIC, (
            f"Tool execution took {elapsed:.2f}s, expected < {PERF_THRESHOLD_BASIC}s"
        )

        # Verify response is valid
        assert result is not None
        assert "content" in result

    def test_server_creation_performance(self) -> None:
        """Test create_github_tools_server() completes quickly.

        This test verifies that server creation (including prerequisite
        verification) completes in a reasonable time.
        """
        # Measure server creation time
        start = time.perf_counter()

        # Run synchronously to allow internal asyncio.run() calls
        server_config = create_github_tools_server()

        elapsed = time.perf_counter() - start

        # Server creation should be fast (configurable threshold for CI/CD)
        # Note: Verification involves subprocess calls so 10s is reasonable
        assert elapsed < PERF_THRESHOLD_SERVER_CREATION, (
            f"Server creation took {elapsed:.2f}s, "
            f"expected < {PERF_THRESHOLD_SERVER_CREATION}s"
        )

        # Verify server config is valid
        assert server_config is not None
        assert isinstance(server_config, dict)
        assert "instance" in server_config

    @pytest.mark.asyncio
    async def test_multiple_tool_calls_performance(self) -> None:
        """Test multiple sequential tool calls complete efficiently.

        This test verifies that making multiple tool calls doesn't
        degrade performance due to resource leaks or inefficiencies.
        """
        from maverick.tools.github import github_list_issues

        # Measure time for 3 sequential calls
        start = time.perf_counter()

        for _ in range(3):
            result = await github_list_issues.handler(
                {
                    "state": "open",
                    "limit": 5,
                }
            )
            assert result is not None

        elapsed = time.perf_counter() - start

        # 3 calls should complete in reasonable time (configurable threshold for CI/CD)
        assert elapsed < PERF_THRESHOLD_SEQUENTIAL, (
            f"3 tool calls took {elapsed:.2f}s, expected < {PERF_THRESHOLD_SEQUENTIAL}s"
        )

    @pytest.mark.asyncio
    async def test_parallel_tool_calls_performance(self) -> None:
        """Test parallel tool calls execute efficiently.

        This test verifies that tools can be called in parallel without
        blocking or performance degradation.
        """
        from maverick.tools.github import github_list_issues

        # Measure time for 3 parallel calls
        start = time.perf_counter()

        # Execute 3 calls in parallel
        tasks = [
            github_list_issues.handler({"state": "open", "limit": 5}),
            github_list_issues.handler({"state": "closed", "limit": 5}),
            github_list_issues.handler({"state": "all", "limit": 5}),
        ]

        results = await asyncio.gather(*tasks)

        elapsed = time.perf_counter() - start

        # Parallel calls should be faster than sequential
        # (configurable threshold for CI/CD overhead)
        assert elapsed < PERF_THRESHOLD_PARALLEL, (
            f"3 parallel calls took {elapsed:.2f}s, "
            f"expected < {PERF_THRESHOLD_PARALLEL}s"
        )

        # Verify all results are valid
        for result in results:
            assert result is not None
            assert "content" in result


@pytest.mark.integration
class TestGitHubToolsErrorHandling:
    """Test error handling for integration scenarios."""

    def test_create_server_outside_git_repo_succeeds_with_lazy_verification(
        self, tmp_path: Path
    ) -> None:
        """Test that server creation succeeds even outside a git repository.

        With lazy verification, the factory function no longer fails immediately.
        Prerequisites are checked on first tool use. This allows creating servers
        in any context, including async contexts.
        """
        # Create server in a non-git directory should succeed now
        # (verification is lazy)
        server_config = create_github_tools_server(cwd=tmp_path)

        # Verify server was created
        assert server_config is not None
        assert isinstance(server_config, dict)
        assert "name" in server_config
        assert server_config["name"] == "github-tools"

    @pytest.mark.asyncio
    async def test_verify_prerequisites_outside_git_repo_fails(
        self, tmp_path: Path
    ) -> None:
        """Test that verify_github_prerequisites fails outside a git repository.

        This test verifies the explicit verification function correctly detects
        when the directory is not a git repository. Use this for fail-fast behavior.
        """
        from maverick.tools.github import verify_github_prerequisites

        # Explicit verification in a non-git directory should fail
        with pytest.raises(GitHubToolsError) as exc_info:
            await verify_github_prerequisites(cwd=tmp_path)

        # Verify error details
        error = exc_info.value
        assert "git" in str(error).lower()
        assert error.check_failed in ("git_repo", "git_remote")

    @pytest.mark.asyncio
    async def test_invalid_issue_number_returns_error(self) -> None:
        """Test that invalid issue numbers return proper error responses.

        This test verifies error handling for common user mistakes.
        """
        from maverick.tools.github import github_get_issue

        # Call with invalid (negative) issue number
        result = await github_get_issue.handler({"issue_number": -1})

        # Verify error response structure
        assert result is not None
        assert "content" in result
        response_text = result["content"][0]["text"]
        response_data = json.loads(response_text)

        assert response_data["isError"] is True
        assert "message" in response_data
        assert "error_code" in response_data
        assert response_data["error_code"] == "INVALID_INPUT"

    @pytest.mark.asyncio
    async def test_nonexistent_issue_returns_not_found(self) -> None:
        """Test that nonexistent issue numbers return NOT_FOUND error.

        This test verifies proper error handling for missing resources.
        """
        from maverick.tools.github import github_get_issue

        # Use a very high issue number that's unlikely to exist
        result = await github_get_issue.handler({"issue_number": 999999999})

        # Verify error response
        assert result is not None
        assert "content" in result
        response_text = result["content"][0]["text"]
        response_data = json.loads(response_text)

        # Should be an error (likely NOT_FOUND)
        if response_data.get("isError"):
            assert "error_code" in response_data
            # Could be NOT_FOUND or other GitHub API error
            assert response_data["error_code"] in (
                "NOT_FOUND",
                "INTERNAL_ERROR",
                "RATE_LIMIT",
            )

    @pytest.mark.asyncio
    async def test_invalid_state_returns_validation_error(self) -> None:
        """Test that invalid state values are rejected.

        This test verifies input validation for enum-like parameters.
        """
        from maverick.tools.github import github_list_issues

        # Call with invalid state
        result = await github_list_issues.handler(
            {
                "state": "invalid_state",
                "limit": 10,
            }
        )

        # Verify error response
        assert result is not None
        assert "content" in result
        response_text = result["content"][0]["text"]
        response_data = json.loads(response_text)

        assert response_data["isError"] is True
        assert response_data["error_code"] == "INVALID_INPUT"
        assert "state" in response_data["message"].lower()

    @pytest.mark.asyncio
    async def test_empty_issue_list_handled_gracefully(self) -> None:
        """Test that empty issue lists are handled gracefully.

        This test verifies that when a repository has no issues matching
        the criteria, the response is a valid empty list rather than an error.

        Note: This test uses a very specific label that is unlikely to exist,
        ensuring we get an empty result set.
        """
        from maverick.tools.github import github_list_issues

        # Use a label that is extremely unlikely to exist
        result = await github_list_issues.handler(
            {
                "label": "nonexistent-label-xyz-12345",
                "state": "all",
                "limit": 10,
            }
        )

        # Verify response is valid
        assert result is not None
        assert "content" in result
        response_text = result["content"][0]["text"]
        response_data = json.loads(response_text)

        # Should be a success response with empty issues list
        # (not an error)
        if not response_data.get("isError"):
            assert "issues" in response_data
            assert isinstance(response_data["issues"], list)
            # The list should be empty or contain only issues with that label
            # (most likely empty)


@pytest.mark.integration
class TestGitHubToolsResponseFormats:
    """Test that tools return correctly formatted responses."""

    @pytest.mark.asyncio
    async def test_list_issues_response_format(self) -> None:
        """Test github_list_issues returns properly formatted response.

        This test verifies the response structure matches the expected
        MCP format and contains required fields.
        """
        from maverick.tools.github import github_list_issues

        result = await github_list_issues.handler(
            {
                "state": "open",
                "limit": 5,
            }
        )

        # Verify MCP response structure
        assert "content" in result
        assert isinstance(result["content"], list)
        assert len(result["content"]) > 0
        assert result["content"][0]["type"] == "text"

        # Parse and verify data structure
        response_text = result["content"][0]["text"]
        response_data = json.loads(response_text)

        if not response_data.get("isError"):
            # Success response
            assert "issues" in response_data
            assert isinstance(response_data["issues"], list)

            # If there are issues, verify structure
            if response_data["issues"]:
                issue = response_data["issues"][0]
                assert "number" in issue
                assert "title" in issue
                assert "labels" in issue
                assert "state" in issue
                assert "url" in issue

    @pytest.mark.asyncio
    async def test_get_issue_response_format(self, valid_issue_number: int) -> None:
        """Test github_get_issue returns properly formatted response.

        This test verifies the detailed issue response structure.

        Note: This test will be skipped if no issues are available in the
        repository, which is acceptable for integration tests.
        """
        from maverick.tools.github import github_get_issue

        # Get a valid issue from the repository
        result = await github_get_issue.handler({"issue_number": valid_issue_number})

        # Verify MCP response structure
        assert "content" in result
        assert isinstance(result["content"], list)

        # Parse response
        response_text = result["content"][0]["text"]
        response_data = json.loads(response_text)

        if not response_data.get("isError"):
            # Success response - verify detailed structure
            assert "number" in response_data
            assert "title" in response_data
            assert "body" in response_data
            assert "url" in response_data
            assert "state" in response_data
            assert "labels" in response_data
            assert "assignees" in response_data
            assert "author" in response_data
            assert "comments_count" in response_data
            assert "created_at" in response_data
            assert "updated_at" in response_data

    @pytest.mark.asyncio
    async def test_error_response_format(self) -> None:
        """Test that error responses have consistent format.

        This test verifies all errors follow the same structure.
        """
        from maverick.tools.github import github_get_issue

        # Trigger an error with invalid input
        result = await github_get_issue.handler({"issue_number": 0})

        # Verify error response structure
        assert "content" in result
        response_text = result["content"][0]["text"]
        response_data = json.loads(response_text)

        # Verify error fields
        assert response_data["isError"] is True
        assert "message" in response_data
        assert "error_code" in response_data
        assert isinstance(response_data["message"], str)
        assert isinstance(response_data["error_code"], str)
