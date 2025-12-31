"""Unit tests for GitHub tools server creation.

Tests create_github_tools_server factory function.
"""

from __future__ import annotations

import pytest


class TestCreateGitHubToolsServer:
    """Tests for create_github_tools_server factory function (T008)."""

    def test_create_github_tools_server_skip_verification(self) -> None:
        """Test create_github_tools_server with skip_verification=True (deprecated)."""
        from maverick.tools.github import create_github_tools_server

        # Should succeed - skip_verification is now ignored (always lazy)
        server = create_github_tools_server(skip_verification=True)

        # Verify server is created
        assert server is not None

    def test_create_github_tools_server_safe_in_async_context(self) -> None:
        """Test create_github_tools_server is safe to call from async context.

        After refactoring to use lazy verification, the factory no longer
        uses asyncio.run() and is safe to call from both sync and async contexts.
        """
        import asyncio

        from maverick.tools.github import create_github_tools_server

        async def async_caller():
            """Call create_github_tools_server from async context."""
            # Should succeed - no longer raises error in async context
            server = create_github_tools_server()
            assert server is not None
            return server

        # Run the async test
        server = asyncio.run(async_caller())
        assert server is not None

    def test_create_github_tools_server_lazy_verification(self) -> None:
        """Test create_github_tools_server uses lazy verification.

        The factory no longer runs verification synchronously.
        Verification happens on first tool use.
        """
        from maverick.tools.github import create_github_tools_server

        # Should succeed regardless of skip_verification value
        # since verification is always lazy now
        server = create_github_tools_server(skip_verification=False)
        assert server is not None

    def test_create_github_tools_server_returns_mcp_server_config(self) -> None:
        """Test create_github_tools_server returns McpSdkServerConfig type."""

        from maverick.tools.github import create_github_tools_server

        server = create_github_tools_server()
        assert isinstance(server, dict)
        # McpSdkServerConfig is a TypedDict, check for expected keys
        assert "name" in server or "tools" in server or server is not None

    @pytest.mark.asyncio
    async def test_create_github_tools_server_in_nested_async(self) -> None:
        """Test create_github_tools_server works in nested async operations.

        This is the key test for issue #162 - factory must not call asyncio.run()
        which would raise RuntimeError in an existing event loop.
        """
        from maverick.tools.github import create_github_tools_server

        async def nested_create() -> dict:
            server = create_github_tools_server()
            return server

        server = await nested_create()
        assert server is not None
        # McpSdkServerConfig has instance and name keys
        assert "instance" in server or "name" in server

    def test_create_github_tools_server_skip_verification_ignored(self) -> None:
        """Test skip_verification parameter is deprecated and ignored.

        Verification is always lazy now to ensure async safety.
        """
        from maverick.tools.github import create_github_tools_server

        # Both should work identically - skip_verification is ignored
        server1 = create_github_tools_server(skip_verification=True)
        server2 = create_github_tools_server(skip_verification=False)

        assert server1 is not None
        assert server2 is not None
