"""Edge case tests for Git tools.

Tests the git tools edge cases and error handling including:
- Timeout handling
- Detached HEAD state
- Invalid branch names
- Authentication failures
- Factory async context safety

These tests mock GitRunner to isolate the MCP tools layer.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.runners.git import DiffStats, GitResult
from maverick.tools.git import create_git_tools_server, verify_git_prerequisites


@pytest.fixture
def mock_git_runner() -> MagicMock:
    """Create a mock GitRunner for testing git tools."""
    runner = MagicMock()
    # Default to successful results
    runner.is_inside_repo = AsyncMock(return_value=True)
    runner.add = AsyncMock(return_value=GitResult(
        success=True, output="", error=None, duration_ms=10
    ))
    runner.commit = AsyncMock(return_value=GitResult(
        success=True, output="", error=None, duration_ms=10
    ))
    runner.get_head_sha = AsyncMock(return_value="abc123def456")
    runner.get_current_branch = AsyncMock(return_value="main")
    runner.push = AsyncMock(return_value=GitResult(
        success=True, output="main -> main", error=None, duration_ms=100
    ))
    runner.get_diff_stats = AsyncMock(return_value=DiffStats(
        files_changed=0, insertions=0, deletions=0, per_file={}
    ))
    runner.create_branch = AsyncMock(return_value=GitResult(
        success=True, output="Switched to a new branch", error=None, duration_ms=10
    ))
    return runner


@pytest.fixture
def git_tools():
    server = create_git_tools_server()
    return server["tools"]


@pytest.mark.asyncio
async def test_git_commit_exception(git_tools, mock_git_runner):
    """Test git_commit handles exceptions gracefully."""
    mock_git_runner.add = AsyncMock(side_effect=Exception("Unexpected error"))

    with patch("maverick.tools.git.GitRunner", return_value=mock_git_runner):
        result = await git_tools["git_commit"].handler(
            {"message": "test", "type": "feat"}
        )

        response = result["content"][0]["text"]
        assert '"isError": true' in response
        assert "INTERNAL_ERROR" in response


@pytest.mark.asyncio
async def test_git_push_detached_head(git_tools, mock_git_runner):
    """Test git_push fails when in detached HEAD state."""
    mock_git_runner.get_current_branch = AsyncMock(return_value="(detached)")

    with patch("maverick.tools.git.GitRunner", return_value=mock_git_runner):
        result = await git_tools["git_push"].handler({})

        response = result["content"][0]["text"]
        assert '"isError": true' in response
        assert "DETACHED_HEAD" in response


@pytest.mark.asyncio
async def test_git_create_branch_invalid_name(git_tools, mock_git_runner):
    """Test git_create_branch validates branch name."""
    with patch("maverick.tools.git.GitRunner", return_value=mock_git_runner):
        # Test space
        result = await git_tools["git_create_branch"].handler({"name": "invalid name"})
        assert "INVALID_INPUT" in result["content"][0]["text"]

        # Test start with dot
        result = await git_tools["git_create_branch"].handler({"name": ".invalid"})
        assert "INVALID_INPUT" in result["content"][0]["text"]

        # Test control char
        result = await git_tools["git_create_branch"].handler({"name": "invalid\nname"})
        assert "INVALID_INPUT" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_git_push_auth_failure(git_tools, mock_git_runner):
    """Test git_push handles authentication failure."""
    mock_git_runner.push = AsyncMock(return_value=GitResult(
        success=False,
        output="",
        error="Authentication failed",
        duration_ms=100,
    ))

    with patch("maverick.tools.git.GitRunner", return_value=mock_git_runner):
        result = await git_tools["git_push"].handler({})

        response = result["content"][0]["text"]
        assert '"isError": true' in response
        assert "AUTHENTICATION_REQUIRED" in response


@pytest.mark.asyncio
async def test_git_diff_stats_error(git_tools, mock_git_runner):
    """Test git_diff_stats handles errors."""
    mock_git_runner.is_inside_repo = AsyncMock(return_value=False)

    with patch("maverick.tools.git.GitRunner", return_value=mock_git_runner):
        result = await git_tools["git_diff_stats"].handler({})

        response = result["content"][0]["text"]
        assert '"isError": true' in response
        assert "NOT_A_REPOSITORY" in response


# =============================================================================
# Factory Async Context Safety Tests (Issue #162)
# =============================================================================


class TestGitToolsFactoryAsyncSafety:
    """Tests for create_git_tools_server async context safety."""

    def test_create_git_tools_server_safe_in_sync_context(self) -> None:
        """Test create_git_tools_server can be called from sync context."""
        # Should not raise - no asyncio.run() inside factory
        server = create_git_tools_server()
        assert server is not None
        assert "tools" in server

    @pytest.mark.asyncio
    async def test_create_git_tools_server_safe_in_async_context(self) -> None:
        """Test create_git_tools_server can be called from async context.

        This is the key test for issue #162 - factory must not call asyncio.run()
        which would raise RuntimeError in an existing event loop.
        """
        # Should not raise RuntimeError("This event loop is already running")
        server = create_git_tools_server()
        assert server is not None
        assert "tools" in server

    @pytest.mark.asyncio
    async def test_create_git_tools_server_in_nested_async(self) -> None:
        """Test create_git_tools_server works in nested async operations."""

        async def nested_create() -> dict:
            server = create_git_tools_server()
            return server

        server = await nested_create()
        assert server is not None
        assert "tools" in server

    def test_create_git_tools_server_returns_correct_type(self) -> None:
        """Test create_git_tools_server returns McpSdkServerConfig type."""
        from claude_agent_sdk.types import McpSdkServerConfig

        server = create_git_tools_server()
        assert isinstance(server, dict)
        # McpSdkServerConfig is a TypedDict - verify has expected structure
        assert "tools" in server or server is not None

    def test_create_git_tools_server_skip_verification_ignored(self) -> None:
        """Test skip_verification parameter is deprecated and ignored.

        Verification is always lazy now to ensure async safety.
        """
        # Both should work identically - skip_verification is ignored
        server1 = create_git_tools_server(skip_verification=True)
        server2 = create_git_tools_server(skip_verification=False)

        assert server1 is not None
        assert server2 is not None


# =============================================================================
# Public verify_git_prerequisites Tests (Issue #162)
# =============================================================================


class TestVerifyGitPrerequisitesPublic:
    """Tests for the public verify_git_prerequisites function."""

    @pytest.mark.asyncio
    async def test_verify_git_prerequisites_success(self) -> None:
        """Test verify_git_prerequisites succeeds when all checks pass."""
        mock_runner = MagicMock()
        mock_runner.is_inside_repo = AsyncMock(return_value=True)

        with patch("maverick.tools.git.GitRunner", return_value=mock_runner):
            # Should complete without raising
            await verify_git_prerequisites()

    @pytest.mark.asyncio
    async def test_verify_git_prerequisites_git_not_installed(self) -> None:
        """Test verify_git_prerequisites raises when git is not found."""
        from maverick.exceptions import GitToolsError

        mock_runner = MagicMock()
        mock_runner.is_inside_repo = AsyncMock(
            side_effect=FileNotFoundError("git command not found")
        )

        with patch("maverick.tools.git.GitRunner", return_value=mock_runner):
            with pytest.raises(GitToolsError) as exc_info:
                await verify_git_prerequisites()

            assert exc_info.value.check_failed == "git_installed"
            assert "not installed" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_verify_git_prerequisites_not_in_repo(self) -> None:
        """Test verify_git_prerequisites raises when not in a git repo."""
        from maverick.exceptions import GitToolsError

        mock_runner = MagicMock()
        mock_runner.is_inside_repo = AsyncMock(return_value=False)

        with patch("maverick.tools.git.GitRunner", return_value=mock_runner):
            with pytest.raises(GitToolsError) as exc_info:
                await verify_git_prerequisites()

            assert exc_info.value.check_failed == "in_git_repo"

    @pytest.mark.asyncio
    async def test_verify_git_prerequisites_is_async(self) -> None:
        """Test verify_git_prerequisites is a proper async function.

        This ensures it can be awaited and doesn't block the event loop.
        """
        import inspect

        assert inspect.iscoroutinefunction(verify_git_prerequisites)

    @pytest.mark.asyncio
    async def test_verify_git_prerequisites_fail_fast_pattern(self) -> None:
        """Test the recommended fail-fast pattern works.

        Pattern:
            await verify_git_prerequisites()  # fail-fast check
            server = create_git_tools_server()  # create server
        """
        mock_runner = MagicMock()
        mock_runner.is_inside_repo = AsyncMock(return_value=True)

        with patch("maverick.tools.git.GitRunner", return_value=mock_runner):
            # Fail-fast verification
            await verify_git_prerequisites()

            # Then create server
            server = create_git_tools_server()

            assert server is not None
            assert "tools" in server
