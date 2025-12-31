from __future__ import annotations

from pathlib import Path

from claude_agent_sdk import create_sdk_mcp_server
from claude_agent_sdk.types import McpSdkServerConfig

from maverick.logging import get_logger
from maverick.tools.github.tools.diffs import github_get_pr_diff
from maverick.tools.github.tools.issues import (
    github_add_labels,
    github_close_issue,
    github_get_issue,
    github_list_issues,
)
from maverick.tools.github.tools.prs import github_create_pr, github_pr_status

logger = get_logger(__name__)

#: MCP Server configuration
SERVER_NAME: str = "github-tools"
SERVER_VERSION: str = "1.0.0"


def create_github_tools_server(
    cwd: Path | None = None,
    skip_verification: bool = True,
) -> McpSdkServerConfig:
    """Create MCP server with all GitHub tools registered (T008).

    This factory function creates an MCP server instance with all 7 GitHub
    tools registered. Verification is lazy - tools will verify prerequisites
    on first use via verify_github_prerequisites().

    Args:
        cwd: Working directory for prerequisite checks and GitHub operations.
            Defaults to current working directory.
        skip_verification: Deprecated parameter, ignored. Verification is
            always lazy to avoid asyncio.run() in factory functions.

    Returns:
        Configured MCP server instance.

    Example:
        ```python
        from maverick.tools.github import create_github_tools_server

        server = create_github_tools_server()
        agent = MaverickAgent(
            mcp_servers={"github-tools": server},
            allowed_tools=["mcp__github-tools__github_create_pr"],
        )
        ```

    Note:
        For fail-fast verification, call verify_github_prerequisites()
        before creating the server:

        ```python
        await verify_github_prerequisites()
        server = create_github_tools_server()
        ```
    """
    # Capture cwd in closure (no global state)
    _cwd = cwd

    logger.info("Creating GitHub tools MCP server (version %s)", SERVER_VERSION)

    # Create and return MCP server with all tools
    server = create_sdk_mcp_server(
        name=SERVER_NAME,
        version=SERVER_VERSION,
        tools=[
            github_create_pr,
            github_list_issues,
            github_get_issue,
            github_get_pr_diff,
            github_pr_status,
            github_add_labels,
            github_close_issue,
        ],
    )

    return server
