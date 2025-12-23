"""Constants for Git MCP tools.

This module contains all constants used across the git tools package.
"""

from __future__ import annotations

#: Default timeout for git operations in seconds
DEFAULT_TIMEOUT: float = 30.0

#: MCP Server configuration
SERVER_NAME: str = "git-tools"
SERVER_VERSION: str = "1.0.0"

#: Valid conventional commit types
COMMIT_TYPES: set[str] = {
    "feat",
    "fix",
    "docs",
    "style",
    "refactor",
    "test",
    "chore",
}
