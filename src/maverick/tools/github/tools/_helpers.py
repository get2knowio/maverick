"""Shared helpers for GitHub tool modules.

Provides common utilities used across prs.py and issues.py to avoid
code duplication and global mutable state.
"""

from __future__ import annotations

from maverick.utils.github_client import GitHubClient


def _get_client() -> GitHubClient:
    """Create a GitHubClient instance.

    Creates a fresh client per call. GitHubClient uses lazy initialization
    (the underlying PyGithub client and ``gh auth token`` subprocess call are
    deferred until the ``github`` property is first accessed), so construction
    is lightweight.

    Returns:
        GitHubClient instance.

    Raises:
        GitHubCLINotFoundError: If gh CLI is not installed (on first API call).
        GitHubAuthError: If gh CLI is not authenticated (on first API call).
    """
    return GitHubClient()


async def _get_repo_name_async() -> str:
    """Get the current repository name from git remote asynchronously.

    Uses shared utility from runner module per CLAUDE.md.

    Returns:
        Repository name in 'owner/repo' format.

    Raises:
        GitHubError: If unable to determine repository name.
    """
    from maverick.tools.github.runner import get_repo_name_async

    return await get_repo_name_async()
