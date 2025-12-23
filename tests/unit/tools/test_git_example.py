"""Example unit tests for MCP tools - testing pattern reference.

This file demonstrates best practices for testing MCP tools in Maverick:
1. How to mock GitRunner methods for git commands
2. How to test tool response structure
3. Using MCPToolValidator for schema validation

Use this as a reference when writing tests for other MCP tools.

NOTE: Maverick's MCP tools delegate to GitRunner from maverick.runners.git.
Tests should mock GitRunner methods rather than subprocess calls directly.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.tools.git import create_git_tools_server
from tests.utils.mcp import MCPToolValidator

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def mock_git_runner() -> MagicMock:
    """Create a mock GitRunner for testing git commands.

    This fixture demonstrates how to set up a mock GitRunner that
    simulates git operations without actually running git.

    Returns:
        Mock GitRunner with configurable method returns.

    Example:
        >>> mock_runner = mock_git_runner()
        >>> mock_runner.is_inside_repo = AsyncMock(return_value=True)
        >>> mock_runner.get_current_branch = AsyncMock(return_value="main")
    """
    mock_runner = MagicMock()
    mock_runner.is_inside_repo = AsyncMock(return_value=True)
    mock_runner.get_current_branch = AsyncMock(return_value="main")
    mock_runner.get_diff_stats = AsyncMock(return_value=MagicMock(
        files_changed=0, insertions=0, deletions=0
    ))
    return mock_runner


@pytest.fixture
def mock_subprocess() -> MagicMock:
    """Create a mock subprocess for testing git commands.

    This fixture is kept for backwards compatibility but the preferred
    approach is to mock GitRunner methods directly (see mock_git_runner).

    Returns:
        Mock subprocess with configurable stdout, stderr, and returncode.
    """
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"", b""))
    return mock_proc


@pytest.fixture
def tool_validator() -> MCPToolValidator:
    """Create MCP tool validator with common schemas registered.

    This demonstrates how to use MCPToolValidator to validate
    tool response structures against expected schemas.

    Returns:
        MCPToolValidator with git tool schemas registered.
    """
    validator = MCPToolValidator()

    # Register schema for git_current_branch
    validator.register_schema(
        "git_current_branch",
        {
            "type": "object",
            "required": ["branch"],
            "properties": {
                "branch": {"type": "string"},
            },
        },
    )

    # Register schema for git_diff_stats
    validator.register_schema(
        "git_diff_stats",
        {
            "type": "object",
            "required": ["files_changed", "insertions", "deletions"],
            "properties": {
                "files_changed": {"type": "integer"},
                "insertions": {"type": "integer"},
                "deletions": {"type": "integer"},
            },
        },
    )

    return validator


# =============================================================================
# Test Class
# =============================================================================


class TestGitToolPatterns:
    """Example test class demonstrating MCP tool testing patterns.

    This class shows common patterns for:
    - Mocking subprocess calls
    - Testing success responses
    - Testing error responses
    - Validating response schemas
    """

    @pytest.mark.asyncio
    async def test_git_command_mocking(self, mock_git_runner: MagicMock) -> None:
        """Demonstrate how to mock GitRunner for git commands.

        This test shows the complete pattern for mocking git operations:
        1. Configure mock GitRunner method return values
        2. Patch GitRunner class to return our mock instance
        3. Call the tool
        4. Verify the GitRunner methods were called
        5. Validate the response structure

        Pattern:
            - Mock GitRunner methods with AsyncMock
            - Patch maverick.runners.git.GitRunner class
            - Assert GitRunner methods were called
        """
        # Configure mock GitRunner to return "main" as the current branch
        mock_git_runner.is_inside_repo = AsyncMock(return_value=True)
        mock_git_runner.get_current_branch = AsyncMock(return_value="main")

        # Create the MCP server
        server = create_git_tools_server()
        git_current_branch = server["tools"]["git_current_branch"]

        # Patch GitRunner class to return our mock when instantiated
        with patch(
            "maverick.tools.git.GitRunner", return_value=mock_git_runner
        ):
            # Call the tool via handler
            response = await git_current_branch.handler({})

            # Verify GitRunner methods were called
            mock_git_runner.is_inside_repo.assert_called_once()
            mock_git_runner.get_current_branch.assert_called_once()

        # Validate response structure
        assert "content" in response
        assert len(response["content"]) == 1
        assert response["content"][0]["type"] == "text"

        # Parse and validate data
        data = json.loads(response["content"][0]["text"])
        assert data["branch"] == "main"

    @pytest.mark.asyncio
    async def test_tool_response_validation(
        self, mock_git_runner: MagicMock, tool_validator: MCPToolValidator
    ) -> None:
        """Demonstrate how to validate tool response structure.

        This test shows how to use MCPToolValidator to ensure
        tool responses match expected schemas. This is useful for:
        - Verifying response structure
        - Ensuring required fields are present
        - Validating field types

        Pattern:
            - Create MCPToolValidator fixture with schemas
            - Call the tool
            - Parse MCP response to get data
            - Use validator.assert_valid() to check schema
        """
        # Configure mock GitRunner for diff stats
        from maverick.runners.git import DiffStats
        mock_git_runner.is_inside_repo = AsyncMock(return_value=True)
        mock_git_runner.is_dirty = AsyncMock(return_value=True)
        mock_git_runner.get_diff_stats = AsyncMock(return_value=DiffStats(
            files_changed=3, insertions=50, deletions=20
        ))

        # Create server and get tool
        server = create_git_tools_server()
        git_diff_stats = server["tools"]["git_diff_stats"]

        # Call the tool via handler
        with patch("maverick.tools.git.GitRunner", return_value=mock_git_runner):
            response = await git_diff_stats.handler({})

        # Parse MCP response
        assert "content" in response
        data = json.loads(response["content"][0]["text"])

        # Validate response against schema
        tool_validator.assert_valid("git_diff_stats", data)

        # Additional assertions on specific values
        assert data["files_changed"] == 3
        assert data["insertions"] == 50
        assert data["deletions"] == 20

    @pytest.mark.asyncio
    async def test_error_response_structure(self, mock_git_runner: MagicMock) -> None:
        """Demonstrate how to test error responses.

        This test shows how to verify error responses follow
        the correct MCP error format with:
        - isError: true flag
        - message: human-readable error
        - error_code: machine-readable code

        Pattern:
            - Configure mock to simulate error condition
            - Call the tool
            - Verify error response structure
            - Check error_code matches expected value
        """
        # Configure mock GitRunner to indicate not in a git repo
        mock_git_runner.is_inside_repo = AsyncMock(return_value=False)

        # Create server and get tool
        server = create_git_tools_server()
        git_current_branch = server["tools"]["git_current_branch"]

        # Call the tool via handler
        with patch("maverick.tools.git.GitRunner", return_value=mock_git_runner):
            response = await git_current_branch.handler({})

        # Validate error response structure
        assert "content" in response
        data = json.loads(response["content"][0]["text"])

        # Check error fields
        assert data["isError"] is True
        assert "message" in data
        assert "error_code" in data
        assert data["error_code"] == "NOT_A_REPOSITORY"

    @pytest.mark.asyncio
    async def test_multiple_subprocess_calls(self, mock_git_runner: MagicMock) -> None:
        """Demonstrate testing tools that make multiple GitRunner calls.

        Some tools make multiple GitRunner method calls (e.g., prerequisite
        checks, then the actual operation). This shows how to handle
        that pattern.

        Pattern:
            - Configure mock GitRunner with different method returns
            - Verify each method was called appropriately
            - Test that failures at different stages are handled correctly
        """
        # Track which methods were called
        calls_made: list[str] = []

        async def track_is_inside_repo() -> bool:
            calls_made.append("is_inside_repo")
            return True

        async def track_get_current_branch() -> str:
            calls_made.append("get_current_branch")
            return "feature-branch"

        mock_git_runner.is_inside_repo = AsyncMock(
            side_effect=track_is_inside_repo)
        mock_git_runner.get_current_branch = AsyncMock(
            side_effect=track_get_current_branch)

        # Create server and get tool
        server = create_git_tools_server()
        git_current_branch = server["tools"]["git_current_branch"]

        # Call the tool via handler
        with patch("maverick.tools.git.GitRunner", return_value=mock_git_runner):
            response = await git_current_branch.handler({})

        # Verify multiple GitRunner methods were called
        assert len(calls_made) >= 2  # is_inside_repo + get_current_branch

        # Validate response
        data = json.loads(response["content"][0]["text"])
        assert data["branch"] == "feature-branch"


# =============================================================================
# Key Testing Patterns Summary
# =============================================================================
#
# 1. MOCKING GIT COMMANDS (GitRunner pattern):
#    - Create mock GitRunner with AsyncMock methods
#    - Patch maverick.tools.git._get_runner to return mock
#    - Configure method returns for specific scenarios
#    - Use side_effect for tracking calls or multiple returns
#
# 2. TESTING SUCCESS RESPONSES:
#    - Verify MCP structure: {"content": [{"type": "text", "text": "..."}]}
#    - Parse JSON from text field
#    - Use MCPToolValidator for schema validation
#    - Assert specific field values
#
# 3. TESTING ERROR RESPONSES:
#    - Verify isError: true in response
#    - Check error_code matches expected value
#    - Validate error message is descriptive
#    - Test all error conditions (invalid input, git errors, etc.)
#
# 4. FIXTURES:
#    - Create reusable mock_git_runner fixture
#    - Register common schemas in tool_validator fixture
#    - Use parametrized tests for similar test cases
#
# 5. ASYNC TESTING:
#    - Always use @pytest.mark.asyncio decorator
#    - Use AsyncMock for async functions
#    - Use await when calling tools
#    - Handle TimeoutError and other async exceptions
#
# =============================================================================
