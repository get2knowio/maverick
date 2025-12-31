from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from maverick.runners.command import CommandRunner
from maverick.utils.github_client import GitHubClient

if TYPE_CHECKING:
    pass

# =============================================================================
# Constants
# =============================================================================

#: Default timeout for GitHub CLI operations in seconds
DEFAULT_TIMEOUT: float = 30.0

#: Maximum retries for transient failures
MAX_RETRIES: int = 3

#: Initial retry delay in seconds
RETRY_DELAY: float = 1.0

# Module-level client for lazy initialization
_github_client: GitHubClient | None = None


def get_github_client() -> GitHubClient:
    """Get the module-level GitHubClient instance.

    This function provides a singleton-like access to the GitHubClient,
    creating it on first access. The client uses gh CLI for authentication.

    Returns:
        GitHubClient instance.

    Raises:
        GitHubCLINotFoundError: If gh CLI is not installed.
        GitHubAuthError: If gh CLI is not authenticated.
    """
    global _github_client
    if _github_client is None:
        _github_client = GitHubClient()
    return _github_client


def reset_github_client() -> None:
    """Reset the module-level GitHubClient.

    This is useful for testing or when authentication changes.
    The next call to get_github_client() will create a new instance.
    """
    global _github_client
    if _github_client is not None:
        _github_client.close()
        _github_client = None


def get_runner(cwd: Path | None = None) -> CommandRunner:
    """Get a CommandRunner instance for gh commands.

    Args:
        cwd: Working directory for command execution.

    Returns:
        CommandRunner instance configured for GitHub operations.

    Note:
        This is still used for operations that require the gh CLI directly,
        such as getting PR diffs which don't have a PyGithub equivalent.
    """
    return CommandRunner(cwd=cwd, timeout=DEFAULT_TIMEOUT)


async def run_gh_command(
    *args: str,
    cwd: Path | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> tuple[str, str, int]:
    """Run a gh CLI command asynchronously.

    Args:
        *args: gh command arguments (without 'gh' prefix).
        cwd: Working directory for the command.
        timeout: Timeout in seconds.

    Returns:
        Tuple of (stdout, stderr, return_code).

    Note:
        Most GitHub operations now use GitHubClient (PyGithub) for better
        error handling and type safety. This function is retained for
        operations that don't have PyGithub equivalents (e.g., PR diffs).
    """
    runner = get_runner(cwd)
    result = await runner.run(
        ["gh", *args],
        timeout=timeout,
        max_retries=MAX_RETRIES,
        retry_delay=RETRY_DELAY,
    )
    return result.stdout, result.stderr, result.returncode


async def get_repo_name_async(cwd: Path | None = None) -> str:
    """Get the current repository name from gh CLI asynchronously.

    Uses CommandRunner for proper timeout and retry handling per CLAUDE.md.

    Args:
        cwd: Working directory for the command.

    Returns:
        Repository name in 'owner/repo' format.

    Raises:
        GitHubError: If unable to determine repository name.
    """
    from maverick.exceptions import GitHubError

    try:
        stdout, stderr, returncode = await run_gh_command(
            "repo",
            "view",
            "--json",
            "nameWithOwner",
            "-q",
            ".nameWithOwner",
            cwd=cwd,
            timeout=DEFAULT_TIMEOUT,
        )

        if returncode != 0:
            raise GitHubError(f"Failed to get repository name: {stderr}")

        repo_name = stdout.strip()
        if not repo_name:
            raise GitHubError("Unable to determine repository name")

        return repo_name

    except Exception as e:
        if isinstance(e, GitHubError):
            raise
        raise GitHubError(f"Failed to get repository name: {e}") from e
