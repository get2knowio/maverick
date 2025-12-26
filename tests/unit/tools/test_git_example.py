"""Example unit tests for MCP tools - testing pattern reference.

This file demonstrates best practices for testing MCP tools in Maverick:
1. How to mock AsyncGitRepository methods for git commands
2. How to test tool response structure
3. Using MCPToolValidator for schema validation

Use this as a reference when writing tests for other MCP tools.

NOTE: Maverick's MCP tools delegate to AsyncGitRepository from maverick.git.
Tests should mock AsyncGitRepository methods rather than subprocess calls.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.exceptions import NotARepositoryError
from maverick.git import DiffStats
from maverick.tools.git import create_git_tools_server
from tests.utils.mcp import MCPToolValidator

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def mock_git_repo() -> MagicMock:
    """Create a mock AsyncGitRepository for testing git commands.

    This fixture demonstrates how to set up a mock AsyncGitRepository that
    simulates git operations without actually running git.

    Returns:
        Mock AsyncGitRepository with configurable method returns.

    Example:
        >>> mock_repo = mock_git_repo()
        >>> mock_repo.current_branch = AsyncMock(return_value="main")
    """
    mock_repo = MagicMock()
    mock_repo.current_branch = AsyncMock(return_value="main")
    mock_repo.diff_stats = AsyncMock(
        return_value=DiffStats(
            files_changed=0,
            insertions=0,
            deletions=0,
            file_list=(),
            per_file={},
        )
    )
    return mock_repo


@pytest.fixture
def mock_subprocess() -> MagicMock:
    """Create a mock subprocess for testing git commands.

    This fixture is kept for backwards compatibility but the preferred
    approach is to mock AsyncGitRepository methods directly.

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
    - Mocking AsyncGitRepository calls
    - Testing success responses
    - Testing error responses
    - Validating response schemas
    """

    @pytest.mark.asyncio
    async def test_git_command_mocking(self, mock_git_repo: MagicMock) -> None:
        """Demonstrate how to mock AsyncGitRepository for git commands.

        This test shows the complete pattern for mocking git operations:
        1. Configure mock AsyncGitRepository method return values
        2. Patch AsyncGitRepository class to return our mock instance
        3. Call the tool
        4. Verify the AsyncGitRepository methods were called
        5. Validate the response structure

        Pattern:
            - Mock AsyncGitRepository methods with AsyncMock
            - Patch maverick.git.AsyncGitRepository class
            - Assert AsyncGitRepository methods were called
        """
        # Configure mock AsyncGitRepository to return "main" as the current branch
        mock_git_repo.current_branch = AsyncMock(return_value="main")

        # Create the MCP server
        server = create_git_tools_server()
        git_current_branch = server["tools"]["git_current_branch"]

        # Patch AsyncGitRepository class to return our mock when instantiated
        with patch(
            "maverick.tools.git.tools.branch.AsyncGitRepository",
            return_value=mock_git_repo,
        ):
            # Call the tool via handler
            response = await git_current_branch.handler({})

            # Verify AsyncGitRepository methods were called
            mock_git_repo.current_branch.assert_called_once()

        # Validate response structure
        assert "content" in response
        assert len(response["content"]) == 1
        assert response["content"][0]["type"] == "text"

        # Parse and validate data
        data = json.loads(response["content"][0]["text"])
        assert data["branch"] == "main"

    @pytest.mark.asyncio
    async def test_tool_response_validation(
        self, mock_git_repo: MagicMock, tool_validator: MCPToolValidator
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
        # Configure mock AsyncGitRepository for diff stats
        mock_git_repo.diff_stats = AsyncMock(
            return_value=DiffStats(
                files_changed=3,
                insertions=50,
                deletions=20,
                file_list=("file1.py", "file2.py", "file3.py"),
                per_file={},
            )
        )

        # Create server and get tool
        server = create_git_tools_server()
        git_diff_stats = server["tools"]["git_diff_stats"]

        # Call the tool via handler
        with patch(
            "maverick.tools.git.tools.diff.AsyncGitRepository",
            return_value=mock_git_repo,
        ):
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
    async def test_error_response_structure(self) -> None:
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
        # Create server and get tool
        server = create_git_tools_server()
        git_current_branch = server["tools"]["git_current_branch"]

        # Call the tool via handler - mock raises NotARepositoryError
        with patch(
            "maverick.tools.git.tools.branch.AsyncGitRepository",
            side_effect=NotARepositoryError("Not a repo", path="/fake"),
        ):
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
    async def test_multiple_subprocess_calls(self, mock_git_repo: MagicMock) -> None:
        """Demonstrate testing tools that make multiple AsyncGitRepository calls.

        Some tools make multiple AsyncGitRepository method calls.
        This shows how to handle that pattern.

        Pattern:
            - Configure mock AsyncGitRepository with different method returns
            - Verify each method was called appropriately
            - Test that failures at different stages are handled correctly
        """
        # Track which methods were called
        calls_made: list[str] = []

        async def track_current_branch() -> str:
            calls_made.append("current_branch")
            return "feature-branch"

        mock_git_repo.current_branch = AsyncMock(side_effect=track_current_branch)

        # Create server and get tool
        server = create_git_tools_server()
        git_current_branch = server["tools"]["git_current_branch"]

        # Call the tool via handler
        with patch(
            "maverick.tools.git.tools.branch.AsyncGitRepository",
            return_value=mock_git_repo,
        ):
            response = await git_current_branch.handler({})

        # Verify AsyncGitRepository methods were called
        assert len(calls_made) >= 1  # current_branch

        # Validate response
        data = json.loads(response["content"][0]["text"])
        assert data["branch"] == "feature-branch"


# =============================================================================
# Key Testing Patterns Summary
# =============================================================================
#
# 1. MOCKING GIT COMMANDS (AsyncGitRepository pattern):
#    - Create mock AsyncGitRepository with AsyncMock methods
#    - Patch maverick.git.AsyncGitRepository to return mock
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
#    - Create reusable mock_git_repo fixture
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
