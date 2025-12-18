"""Example unit tests for MCP tools - testing pattern reference.

This file demonstrates best practices for testing MCP tools in Maverick:
1. How to mock subprocess calls for git commands
2. How to test tool response structure
3. Using MCPToolValidator for schema validation

Use this as a reference when writing tests for other MCP tools.
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
def mock_subprocess() -> MagicMock:
    """Create a mock subprocess for testing git commands.

    This fixture demonstrates how to set up a mock subprocess that
    simulates git command execution without actually running git.

    Returns:
        Mock subprocess with configurable stdout, stderr, and returncode.

    Example:
        >>> mock_proc = mock_subprocess()
        >>> mock_proc.returncode = 0
        >>> mock_proc.communicate = AsyncMock(return_value=(b"main", b""))
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
    async def test_git_command_mocking(self, mock_subprocess: MagicMock) -> None:
        """Demonstrate how to mock subprocess.run for git commands.

        This test shows the complete pattern for mocking git commands:
        1. Configure mock subprocess return values
        2. Patch asyncio.create_subprocess_exec
        3. Call the tool
        4. Verify the git command was called correctly
        5. Validate the response structure

        Pattern:
            - Mock stdout/stderr as bytes (git returns bytes)
            - Use AsyncMock for communicate()
            - Patch at asyncio.create_subprocess_exec level
            - Assert command arguments match expected
        """
        # Configure mock to return "main" as the current branch
        mock_subprocess.returncode = 0
        mock_subprocess.communicate = AsyncMock(return_value=(b"main\n", b""))

        # Create the MCP server
        server = create_git_tools_server()
        git_current_branch = server["tools"]["git_current_branch"]

        # Patch subprocess creation
        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_subprocess
        ) as mock_exec:
            # Call the tool via handler
            response = await git_current_branch.handler({})

            # Verify git command was called correctly
            # First call is for git --version (prerequisite check)
            # Second call is for git rev-parse --git-dir (prerequisite check)
            # Third call is the actual git rev-parse --abbrev-ref HEAD
            assert mock_exec.call_count >= 3

            # Get the last call (actual branch query)
            last_call_args = mock_exec.call_args_list[-1][0]
            assert last_call_args[0] == "git"
            assert last_call_args[1] == "rev-parse"
            assert last_call_args[2] == "--abbrev-ref"
            assert last_call_args[3] == "HEAD"

        # Validate response structure
        assert "content" in response
        assert len(response["content"]) == 1
        assert response["content"][0]["type"] == "text"

        # Parse and validate data
        data = json.loads(response["content"][0]["text"])
        assert data["branch"] == "main"

    @pytest.mark.asyncio
    async def test_tool_response_validation(
        self, mock_subprocess: MagicMock, tool_validator: MCPToolValidator
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
        # Configure mock for diff stats
        diff_output = b" 3 files changed, 50 insertions(+), 20 deletions(-)"
        mock_subprocess.returncode = 0
        mock_subprocess.communicate = AsyncMock(return_value=(diff_output, b""))

        # Create server and get tool
        server = create_git_tools_server()
        git_diff_stats = server["tools"]["git_diff_stats"]

        # Call the tool
        with patch("asyncio.create_subprocess_exec", return_value=mock_subprocess):
            response = await git_diff_stats({})

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
    async def test_error_response_structure(self, mock_subprocess: MagicMock) -> None:
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
        # Configure mock to simulate "not a git repository" error
        mock_subprocess.returncode = 128
        mock_subprocess.communicate = AsyncMock(
            return_value=(b"", b"fatal: not a git repository")
        )

        # Create server and get tool
        server = create_git_tools_server()
        git_current_branch = server["tools"]["git_current_branch"]

        # Call the tool
        with patch("asyncio.create_subprocess_exec", return_value=mock_subprocess):
            response = await git_current_branch({})

        # Validate error response structure
        assert "content" in response
        data = json.loads(response["content"][0]["text"])

        # Check error fields
        assert data["isError"] is True
        assert "message" in data
        assert "error_code" in data
        assert data["error_code"] == "NOT_A_REPOSITORY"

    @pytest.mark.asyncio
    async def test_multiple_subprocess_calls(
        self, mock_subprocess: MagicMock
    ) -> None:
        """Demonstrate testing tools that make multiple git calls.

        Some tools make multiple subprocess calls (e.g., prerequisite
        checks, then the actual operation). This shows how to handle
        that pattern.

        Pattern:
            - Track call count with side_effect or multiple mocks
            - Verify each call's arguments
            - Test that failures at different stages are handled correctly
        """
        # Configure mock to return different values for different calls
        mock_subprocess.returncode = 0

        call_count = 0

        async def communicate_side_effect() -> tuple[bytes, bytes]:
            """Simulate different responses for different calls."""
            nonlocal call_count
            call_count += 1

            # First few calls are prerequisites (version, rev-parse)
            if call_count <= 2:
                return (b"output", b"")
            # Last call is the actual branch query
            return (b"feature-branch\n", b"")

        mock_subprocess.communicate = AsyncMock(side_effect=communicate_side_effect)

        # Create server and get tool
        server = create_git_tools_server()
        git_current_branch = server["tools"]["git_current_branch"]

        # Call the tool
        with patch("asyncio.create_subprocess_exec", return_value=mock_subprocess):
            response = await git_current_branch({})

        # Verify multiple calls were made
        assert call_count >= 3  # version + git-dir check + actual command

        # Validate response
        data = json.loads(response["content"][0]["text"])
        assert data["branch"] == "feature-branch"


# =============================================================================
# Key Testing Patterns Summary
# =============================================================================
#
# 1. MOCKING GIT COMMANDS:
#    - Use AsyncMock for subprocess.communicate()
#    - Return bytes (b"output") not strings
#    - Set returncode (0 for success, non-zero for errors)
#    - Patch at asyncio.create_subprocess_exec level
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
#    - Create reusable mock_subprocess fixture
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
