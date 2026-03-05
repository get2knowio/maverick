"""Maverick MCP tool definitions and servers.

This package provides MCP tool implementations for integration with
Claude Code ACP-based workflows, including GitHub CLI wrappers and utilities.

NOTE: The individual tool servers (git, github, notification, validation) still
use the claude_agent_sdk @tool decorator pattern from the legacy SDK. These are
preserved for future migration to ACP-native tool format. Import failures are
handled gracefully so the rest of maverick can function without the SDK.
"""

from __future__ import annotations

try:
    from maverick.tools.git import create_git_tools_server
    from maverick.tools.github import create_github_tools_server
    from maverick.tools.notification import create_notification_tools_server
    from maverick.tools.validation import create_validation_tools_server

    __all__ = [
        "create_git_tools_server",
        "create_github_tools_server",
        "create_notification_tools_server",
        "create_validation_tools_server",
    ]
except ImportError:
    # claude_agent_sdk has been removed; tool servers are legacy SDK code
    # and will be migrated to ACP-native format in a future task.
    __all__ = []
