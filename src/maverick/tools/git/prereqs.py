"""Prerequisite verification for Git tools.

This module provides functions to verify that git is installed and available.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from maverick.exceptions import GitNotFoundError, GitToolsError, NotARepositoryError
from maverick.git import GitRepository
from maverick.logging import get_logger

logger = get_logger(__name__)


async def verify_git_prerequisites(cwd: Path | None = None) -> None:
    """Verify git is installed and we're in a repository.

    Public function for callers who want fail-fast verification before
    using git tools. This is optional - tools will verify prerequisites
    lazily on first use if not called explicitly.

    Uses GitRepository internally for the actual git checks.

    Args:
        cwd: Working directory to check. Defaults to current directory.

    Raises:
        GitToolsError: If any prerequisite check fails:
            - git_installed: Git not found
            - in_git_repo: Not inside a git repository

    Example:
        ```python
        from maverick.tools.git import (
            create_git_tools_server,
            verify_git_prerequisites,
        )

        # Optional fail-fast verification
        await verify_git_prerequisites()

        # Create server (will use lazy verification if not pre-verified)
        server = create_git_tools_server()
        ```
    """
    try:
        # Creating GitRepository validates git is installed and we're in a repo
        # Use asyncio.to_thread since GitRepository constructor is sync
        await asyncio.to_thread(GitRepository, cwd)
    except GitNotFoundError:
        raise GitToolsError(
            "git is not installed or not available on PATH",
            check_failed="git_installed",
        ) from None
    except NotARepositoryError:
        raise GitToolsError(
            "not inside a git repository",
            check_failed="in_git_repo",
        ) from None
