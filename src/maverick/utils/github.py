"""GitHub CLI helper utilities for Maverick agents.

This module provides async functions for GitHub operations using the gh CLI
with automatic retry and exponential backoff.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any

from maverick.exceptions import GitHubError

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

#: Default timeout for GitHub CLI operations in seconds
DEFAULT_GITHUB_TIMEOUT: float = 30.0

#: Maximum retries for GitHub API errors
MAX_GITHUB_RETRIES: int = 3

#: Base backoff time in seconds for exponential backoff
BACKOFF_BASE: float = 2.0


# =============================================================================
# Low-level GitHub CLI Operations
# =============================================================================


async def _run_gh_command(
    *args: str,
    cwd: Path,
    timeout: float = DEFAULT_GITHUB_TIMEOUT,
) -> tuple[str, str, int]:
    """Run a gh CLI command asynchronously.

    Args:
        *args: gh command arguments (without 'gh' prefix).
        cwd: Working directory for the command.
        timeout: Timeout in seconds.

    Returns:
        Tuple of (stdout, stderr, return_code).

    Raises:
        asyncio.TimeoutError: If command times out.
    """
    process = await asyncio.create_subprocess_exec(
        "gh",
        *args,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        raise

    stdout = stdout_bytes.decode().strip()
    stderr = stderr_bytes.decode().strip()
    return_code = process.returncode or 0

    return stdout, stderr, return_code


def _parse_rate_limit_wait(stderr: str) -> int | None:
    """Parse rate limit wait time from error message.

    Args:
        stderr: Standard error output from gh command.

    Returns:
        Seconds to wait, or None if not a rate limit error.
    """
    # Look for patterns like "retry after 60 seconds" or "wait 120s"
    patterns = [
        r"retry after (\d+)",
        r"wait (\d+)\s*s",
        r"(\d+)\s*seconds",
    ]

    stderr_lower = stderr.lower()
    if "rate limit" not in stderr_lower:
        return None

    for pattern in patterns:
        match = re.search(pattern, stderr_lower)
        if match:
            return int(match.group(1))

    # Default wait time if rate limited but no specific time given
    return 60


# =============================================================================
# Issue Operations
# =============================================================================


async def fetch_issue(
    issue_number: int,
    cwd: Path,
    max_retries: int = MAX_GITHUB_RETRIES,
) -> dict[str, Any]:
    """Fetch GitHub issue details with retry and exponential backoff.

    Args:
        issue_number: GitHub issue number.
        cwd: Working directory (for repo context).
        max_retries: Maximum number of retry attempts.

    Returns:
        Issue data dictionary with keys: number, title, body, labels, state, url.

    Raises:
        GitHubError: After retry exhaustion with actionable message.

    Example:
        >>> issue = await fetch_issue(42, Path.cwd())
        >>> issue["title"]
        'Bug: Login fails on Safari'
    """
    fields = "number,title,body,labels,state,url,author,assignees,createdAt,updatedAt"

    for attempt in range(max_retries):
        try:
            stdout, stderr, return_code = await _run_gh_command(
                "issue",
                "view",
                str(issue_number),
                "--json",
                fields,
                cwd=cwd,
            )

            if return_code == 0:
                data = json.loads(stdout)
                title = data.get("title", "")
                logger.debug("Fetched issue #%d: %s", issue_number, title)
                return data

            error_msg = stderr or stdout
            error_lower = error_msg.lower()

            # Check for specific error types
            if "not found" in error_lower or "could not find" in error_lower:
                raise GitHubError(
                    f"Issue #{issue_number} not found",
                    issue_number=issue_number,
                )

            if "rate limit" in error_lower:
                retry_after = _parse_rate_limit_wait(error_msg)
                if attempt < max_retries - 1:
                    wait_time = retry_after or (BACKOFF_BASE ** (attempt + 1))
                    logger.warning(
                        "GitHub rate limit hit, waiting %.1fs (attempt %d/%d)",
                        wait_time,
                        attempt + 1,
                        max_retries,
                    )
                    await asyncio.sleep(wait_time)
                    continue
                raise GitHubError(
                    f"GitHub rate limit exceeded, retry after {retry_after} seconds",
                    issue_number=issue_number,
                    retry_after=retry_after,
                )

            if "authentication" in error_lower or "unauthorized" in error_lower:
                raise GitHubError(
                    "GitHub authentication failed. Run: gh auth login",
                    issue_number=issue_number,
                )

            # Generic error with retry
            if attempt < max_retries - 1:
                wait_time = BACKOFF_BASE ** (attempt + 1)
                logger.warning(
                    "GitHub CLI error, retrying in %.1fs (attempt %d/%d): %s",
                    wait_time,
                    attempt + 1,
                    max_retries,
                    error_msg,
                )
                await asyncio.sleep(wait_time)
                continue

            raise GitHubError(
                f"GitHub CLI error: {error_msg}",
                issue_number=issue_number,
            )

        except asyncio.TimeoutError:
            if attempt < max_retries - 1:
                wait_time = BACKOFF_BASE ** (attempt + 1)
                logger.warning(
                    "GitHub request timed out, retrying in %.1fs (attempt %d/%d)",
                    wait_time,
                    attempt + 1,
                    max_retries,
                )
                await asyncio.sleep(wait_time)
                continue
            raise GitHubError(
                "GitHub request timed out after retries",
                issue_number=issue_number,
            )
        except json.JSONDecodeError as e:
            raise GitHubError(
                f"Failed to parse GitHub response: {e}",
                issue_number=issue_number,
            )

    raise GitHubError(
        "GitHub fetch failed after all retries",
        issue_number=issue_number,
    )


async def list_issues(
    cwd: Path,
    state: str = "open",
    labels: list[str] | None = None,
    limit: int = 30,
) -> list[dict[str, Any]]:
    """List GitHub issues with optional filters.

    Args:
        cwd: Working directory (for repo context).
        state: Issue state filter ("open", "closed", "all").
        labels: Optional list of labels to filter by.
        limit: Maximum number of issues to return.

    Returns:
        List of issue data dictionaries.

    Raises:
        GitHubError: On CLI or API errors.
    """
    args = ["issue", "list", "--state", state, "--limit", str(limit)]
    args.extend(["--json", "number,title,body,labels,state,url"])

    if labels:
        for label in labels:
            args.extend(["--label", label])

    stdout, stderr, return_code = await _run_gh_command(*args, cwd=cwd)

    if return_code != 0:
        raise GitHubError(f"Failed to list issues: {stderr or stdout}")

    try:
        return json.loads(stdout) if stdout else []
    except json.JSONDecodeError as e:
        raise GitHubError(f"Failed to parse issue list: {e}")


async def add_issue_comment(
    issue_number: int,
    body: str,
    cwd: Path,
) -> None:
    """Add a comment to a GitHub issue.

    Args:
        issue_number: GitHub issue number.
        body: Comment body text (markdown supported).
        cwd: Working directory (for repo context).

    Raises:
        GitHubError: On CLI or API errors.
    """
    stdout, stderr, return_code = await _run_gh_command(
        "issue",
        "comment",
        str(issue_number),
        "--body",
        body,
        cwd=cwd,
    )

    if return_code != 0:
        raise GitHubError(
            f"Failed to add comment: {stderr or stdout}",
            issue_number=issue_number,
        )

    logger.debug("Added comment to issue #%d", issue_number)


async def check_gh_auth(cwd: Path) -> bool:
    """Check if GitHub CLI is authenticated.

    Args:
        cwd: Working directory.

    Returns:
        True if authenticated, False otherwise.
    """
    stdout, stderr, return_code = await _run_gh_command(
        "auth",
        "status",
        cwd=cwd,
        timeout=10.0,
    )
    return return_code == 0
