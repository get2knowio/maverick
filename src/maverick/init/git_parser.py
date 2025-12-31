"""Git remote URL parsing for maverick init.

This module provides functionality to parse git remote URLs and extract
owner/repository information for GitHub configuration.

Supports both SSH and HTTPS URL formats:
- SSH: git@github.com:owner/repo.git
- HTTPS: https://github.com/owner/repo.git
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import TYPE_CHECKING

from maverick.init.models import GitRemoteInfo
from maverick.logging import get_logger

if TYPE_CHECKING:
    pass

__all__ = ["parse_git_remote"]

logger = get_logger(__name__)

# Default timeout for git operations
DEFAULT_TIMEOUT: float = 5.0

# Regex patterns for parsing git remote URLs
# SSH format: git@github.com:owner/repo.git
SSH_PATTERN = re.compile(r"git@[^:]+:([^/]+)/([^/]+?)(?:\.git)?$")

# HTTPS format: https://github.com/owner/repo.git
HTTPS_PATTERN = re.compile(r"https?://[^/]+/([^/]+)/([^/]+?)(?:\.git)?$")


def _parse_remote_url(url: str) -> tuple[str | None, str | None]:
    """Parse owner and repo from a git remote URL.

    Args:
        url: Git remote URL (SSH or HTTPS format).

    Returns:
        Tuple of (owner, repo) or (None, None) if parsing fails.

    Examples:
        >>> _parse_remote_url("git@github.com:owner/repo.git")
        ('owner', 'repo')
        >>> _parse_remote_url("https://github.com/owner/repo")
        ('owner', 'repo')
        >>> _parse_remote_url("invalid-url")
        (None, None)
    """
    # Try SSH pattern first
    match = SSH_PATTERN.match(url)
    if match:
        return match.group(1), match.group(2)

    # Try HTTPS pattern
    match = HTTPS_PATTERN.match(url)
    if match:
        return match.group(1), match.group(2)

    return None, None


async def parse_git_remote(
    project_path: Path,
    remote_name: str = "origin",
    *,
    timeout: float = DEFAULT_TIMEOUT,
) -> GitRemoteInfo:
    """Parse git remote URL to extract owner and repo.

    Uses `git remote get-url` to retrieve the remote URL and parses it
    to extract GitHub owner and repository names.

    Args:
        project_path: Path to git repository.
        remote_name: Name of remote to parse (default: "origin").
        timeout: Timeout in seconds for git command (default: 5.0).

    Returns:
        GitRemoteInfo with parsed owner/repo or None values if:
        - No remote configured with the given name
        - Remote URL format is not recognized
        - Git command fails or times out

    Examples:
        >>> import asyncio
        >>> from pathlib import Path
        >>> info = asyncio.run(parse_git_remote(Path.cwd()))
        >>> if info.owner and info.repo:
        ...     print(f"Repository: {info.full_name}")
        ... else:
        ...     print("Warning: No remote configured")
    """
    try:
        # Execute git remote get-url command
        process = await asyncio.create_subprocess_exec(
            "git",
            "remote",
            "get-url",
            remote_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=project_path,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )
        except TimeoutError:
            # Kill the process on timeout
            process.kill()
            await process.wait()
            logger.warning(
                "git_remote_timeout",
                remote_name=remote_name,
                timeout=timeout,
            )
            return GitRemoteInfo(remote_name=remote_name)

        if process.returncode != 0:
            # Remote doesn't exist or other git error
            error_msg = stderr.decode("utf-8", errors="replace").strip()
            logger.debug(
                "git_remote_error",
                remote_name=remote_name,
                returncode=process.returncode,
                error=error_msg,
            )
            return GitRemoteInfo(remote_name=remote_name)

        # Parse the remote URL
        remote_url = stdout.decode("utf-8", errors="replace").strip()
        if not remote_url:
            logger.debug(
                "git_remote_empty",
                remote_name=remote_name,
            )
            return GitRemoteInfo(remote_name=remote_name)

        owner, repo = _parse_remote_url(remote_url)

        if owner and repo:
            logger.debug(
                "git_remote_parsed",
                remote_name=remote_name,
                owner=owner,
                repo=repo,
                remote_url=remote_url,
            )
        else:
            logger.debug(
                "git_remote_parse_failed",
                remote_name=remote_name,
                remote_url=remote_url,
            )

        return GitRemoteInfo(
            owner=owner,
            repo=repo,
            remote_url=remote_url,
            remote_name=remote_name,
        )

    except FileNotFoundError:
        # git command not found
        logger.warning("git_not_found")
        return GitRemoteInfo(remote_name=remote_name)
    except OSError as e:
        # Other OS errors (permission denied, etc.)
        logger.warning(
            "git_remote_os_error",
            remote_name=remote_name,
            error=str(e),
        )
        return GitRemoteInfo(remote_name=remote_name)
