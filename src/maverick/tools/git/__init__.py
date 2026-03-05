"""Git utility MCP tools for Maverick agents.

This package provides MCP tools for git operations (branch, commit, push, diff).
Tools are async functions decorated with @tool that return MCP-formatted responses.

NOTE: The individual tool files use the claude_agent_sdk @tool decorator pattern.
These are preserved for future migration to ACP-native tool format.

Usage:
    from maverick.tools.git import create_git_tools_server

    server = create_git_tools_server()
    agent = MaverickAgent(mcp_servers={"git-tools": server})

    # Optional: verify prerequisites explicitly for fail-fast behavior
    from maverick.tools.git import verify_git_prerequisites
    await verify_git_prerequisites()
"""

from __future__ import annotations

try:
    # Re-export all public symbols for backward compatibility
    from maverick.tools.git.constants import (
        COMMIT_TYPES,
        DEFAULT_TIMEOUT,
        SERVER_NAME,
        SERVER_VERSION,
    )
    from maverick.tools.git.formatting import format_commit_message
    from maverick.tools.git.prereqs import verify_git_prerequisites
    from maverick.tools.git.responses import error_response, success_response
    from maverick.tools.git.server import create_git_tools_server

    # Backward compatibility aliases for private functions (used by tests)
    _success_response = success_response
    _error_response = error_response
    _format_commit_message = format_commit_message

    __all__ = [
        # Server factory
        "create_git_tools_server",
        # Prerequisites
        "verify_git_prerequisites",
        # Response helpers (for testing)
        "success_response",
        "error_response",
        # Formatting helpers (for testing)
        "format_commit_message",
        # Constants
        "DEFAULT_TIMEOUT",
        "SERVER_NAME",
        "SERVER_VERSION",
        "COMMIT_TYPES",
    ]
except ImportError:
    # claude_agent_sdk has been removed; tool servers are legacy SDK code
    __all__ = []
