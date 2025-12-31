"""Commit message formatting helpers for Git tools.

Provides utilities for formatting commit messages in conventional commit format.
"""

from __future__ import annotations


def format_commit_message(
    message: str,
    commit_type: str | None = None,
    scope: str | None = None,
    breaking: bool = False,
) -> str:
    """Format a commit message in conventional commit format.

    This is MCP-specific formatting logic - GitRunner doesn't handle
    conventional commit formatting.

    Args:
        message: Commit description.
        commit_type: Conventional commit type (feat, fix, etc.).
        scope: Optional scope in parentheses.
        breaking: Add ! for breaking changes.

    Returns:
        Formatted commit message.

    Examples:
        >>> format_commit_message("add feature", "feat", "api")
        'feat(api): add feature'
        >>> format_commit_message("breaking change", "feat", breaking=True)
        'feat!: breaking change'
    """
    if not commit_type:
        return message

    prefix = commit_type
    if scope:
        prefix = f"{prefix}({scope})"
    if breaking:
        prefix = f"{prefix}!"

    return f"{prefix}: {message}"
