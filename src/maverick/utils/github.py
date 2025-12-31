"""GitHub CLI helper utilities for Maverick agents.

This module provides async functions for GitHub operations using the gh CLI.
Delegates to the canonical GitHubCLIRunner for core operations while providing
a simpler interface for utilities that only need basic GitHub operations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from maverick.exceptions import GitHubAuthError, GitHubCLINotFoundError, GitHubError
from maverick.logging import get_logger
from maverick.runners.command import CommandRunner
from maverick.runners.github import GitHubCLIRunner

logger = get_logger(__name__)

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
# Module-level runner instance (lazy-initialized)
# =============================================================================

_github_runner: GitHubCLIRunner | None = None
_command_runner: CommandRunner | None = None


def _get_github_runner() -> GitHubCLIRunner:
    """Get or create the module-level GitHubCLIRunner instance.

    Returns:
        GitHubCLIRunner instance.

    Raises:
        GitHubError: If gh CLI is not installed.
    """
    global _github_runner
    if _github_runner is None:
        try:
            _github_runner = GitHubCLIRunner()
        except GitHubCLINotFoundError as e:
            raise GitHubError(
                "GitHub CLI (gh) not found. Install: https://cli.github.com"
            ) from e
    return _github_runner


def _get_command_runner(cwd: Path | None = None) -> CommandRunner:
    """Get a CommandRunner instance for direct gh commands.

    Args:
        cwd: Working directory for command execution.

    Returns:
        CommandRunner instance.
    """
    return CommandRunner(cwd=cwd, timeout=DEFAULT_GITHUB_TIMEOUT)


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
    try:
        runner = _get_github_runner()
        issue = await runner.get_issue(issue_number)

        # Convert GitHubIssue to dict for backward compatibility
        data: dict[str, Any] = {
            "number": issue.number,
            "title": issue.title,
            "body": issue.body,
            "labels": [{"name": label} for label in issue.labels],
            "state": issue.state,
            "url": issue.url,
            "assignees": [{"login": assignee} for assignee in issue.assignees],
        }

        logger.debug("Fetched issue #%d: %s", issue_number, issue.title)
        return data

    except GitHubAuthError as e:
        raise GitHubError(
            "GitHub authentication failed. Run: gh auth login",
            issue_number=issue_number,
        ) from e
    except RuntimeError as e:
        error_msg = str(e).lower()

        if "not found" in error_msg or "could not find" in error_msg:
            raise GitHubError(
                f"Issue #{issue_number} not found",
                issue_number=issue_number,
            ) from e

        if "rate limit" in error_msg:
            raise GitHubError(
                "GitHub rate limit exceeded",
                issue_number=issue_number,
                retry_after=60,
            ) from e

        raise GitHubError(
            f"GitHub CLI error: {e}",
            issue_number=issue_number,
        ) from e


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
    try:
        runner = _get_github_runner()

        # GitHubCLIRunner.list_issues only supports a single label
        # For multiple labels, we need to make multiple calls and merge
        if labels and len(labels) > 1:
            # Use CommandRunner directly for multiple labels
            cmd_runner = _get_command_runner(cwd)
            args = ["gh", "issue", "list", "--state", state, "--limit", str(limit)]
            args.extend(["--json", "number,title,body,labels,state,url"])

            for label in labels:
                args.extend(["--label", label])

            result = await cmd_runner.run(
                args,
                max_retries=MAX_GITHUB_RETRIES,
                retry_delay=BACKOFF_BASE,
            )

            if not result.success:
                raise GitHubError(f"Failed to list issues: {result.stderr}")

            import json

            try:
                return json.loads(result.stdout) if result.stdout.strip() else []
            except json.JSONDecodeError as e:
                raise GitHubError(f"Failed to parse issue list: {e}") from e

        # Use runner for single or no label filter
        filter_label: str | None = labels[0] if labels else None
        issues = await runner.list_issues(label=filter_label, state=state, limit=limit)

        # Convert to dicts for backward compatibility
        return [
            {
                "number": issue.number,
                "title": issue.title,
                "body": issue.body,
                "labels": [{"name": lbl} for lbl in issue.labels],
                "state": issue.state,
                "url": issue.url,
            }
            for issue in issues
        ]

    except GitHubAuthError as e:
        raise GitHubError("GitHub authentication failed. Run: gh auth login") from e
    except RuntimeError as e:
        raise GitHubError(f"Failed to list issues: {e}") from e


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
    cmd_runner = _get_command_runner(cwd)

    result = await cmd_runner.run(
        ["gh", "issue", "comment", str(issue_number), "--body", body],
        max_retries=MAX_GITHUB_RETRIES,
        retry_delay=BACKOFF_BASE,
        scrub_secrets=True,
    )

    if not result.success:
        raise GitHubError(
            f"Failed to add comment: {result.stderr}",
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
    cmd_runner = _get_command_runner(cwd)

    result = await cmd_runner.run(
        ["gh", "auth", "status"],
        timeout=10.0,
    )

    return result.success
