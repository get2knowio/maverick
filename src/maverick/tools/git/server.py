"""MCP server factory for Git tools.

Provides the factory function to create an MCP server with all git tools.
"""

from __future__ import annotations

from pathlib import Path

from claude_agent_sdk import create_sdk_mcp_server
from claude_agent_sdk.types import McpSdkServerConfig

from maverick.logging import get_logger
from maverick.tools.git.constants import SERVER_NAME, SERVER_VERSION
from maverick.tools.git.tools.branch import (
    create_git_create_branch_tool,
    create_git_current_branch_tool,
)
from maverick.tools.git.tools.commit import create_git_commit_tool
from maverick.tools.git.tools.diff import create_git_diff_stats_tool
from maverick.tools.git.tools.push import create_git_push_tool

logger = get_logger(__name__)


def create_git_tools_server(
    cwd: Path | None = None,
    skip_verification: bool = True,
) -> McpSdkServerConfig:
    """Create MCP server with all git tools registered (T048).

    This factory function creates an MCP server instance with all 5 git
    tools registered. Verification is lazy - tools will verify prerequisites
    on first use via verify_git_prerequisites().

    Args:
        cwd: Working directory for prerequisite checks and git operations.
            Defaults to current working directory.
        skip_verification: Deprecated parameter, ignored. Verification is
            always lazy to avoid asyncio.run() in factory functions.

    Returns:
        Configured MCP server instance.

    Example:
        ```python
        from maverick.tools.git import create_git_tools_server

        server = create_git_tools_server()
        agent = MaverickAgent(
            mcp_servers={"git-tools": server},
            allowed_tools=["mcp__git-tools__git_commit"],
        )
        ```

    Note:
        For fail-fast verification, call verify_git_prerequisites()
        before creating the server:

        ```python
        await verify_git_prerequisites()
        server = create_git_tools_server()
        ```
    """
    # Capture cwd in closure (no global state)
    _cwd = cwd

    logger.info("Creating git tools MCP server (version %s)", SERVER_VERSION)

    # Create all tool functions with the captured cwd
    git_commit = create_git_commit_tool(_cwd)
    git_push = create_git_push_tool(_cwd)
    git_current_branch = create_git_current_branch_tool(_cwd)
    git_diff_stats = create_git_diff_stats_tool(_cwd)
    git_create_branch = create_git_create_branch_tool(_cwd)

    # Store tools for test access
    tools = {
        "git_commit": git_commit,
        "git_push": git_push,
        "git_current_branch": git_current_branch,
        "git_diff_stats": git_diff_stats,
        "git_create_branch": git_create_branch,
    }

    # Create and return MCP server with all tools
    server = create_sdk_mcp_server(
        name=SERVER_NAME,
        version=SERVER_VERSION,
        tools=list(tools.values()),
    )

    # Add tools to the server dict for test access
    # Type ignore because we're adding to the dict for test purposes
    server["_tools"] = tools  # type: ignore[typeddict-unknown-key]

    return server
