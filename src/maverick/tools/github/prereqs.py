from __future__ import annotations

from pathlib import Path

from maverick.exceptions import GitHubToolsError
from maverick.logging import get_logger
from maverick.tools.github.runner import get_runner

logger = get_logger(__name__)


async def verify_github_prerequisites(cwd: Path | None = None) -> None:
    """Verify gh CLI and git repo prerequisites.

    Public function for callers who want fail-fast verification before
    using GitHub tools. This is optional - tools will verify prerequisites
    lazily on first use if not called explicitly.

    Uses CommandRunner for consistent subprocess handling with timeout.

    Args:
        cwd: Working directory to check. Defaults to current directory.

    Raises:
        GitHubToolsError: If any prerequisite check fails:
            - gh_installed: GitHub CLI not found
            - gh_authenticated: GitHub CLI not authenticated
            - git_installed: Git not found
            - git_repo: Not inside a git repository
            - git_remote: No 'origin' remote configured

    Example:
        ```python
        from maverick.tools.github import (
            create_github_tools_server,
            verify_github_prerequisites,
        )

        # Optional fail-fast verification
        await verify_github_prerequisites()

        # Create server (will use lazy verification if not pre-verified)
        server = create_github_tools_server()
        ```
    """
    working_dir = cwd or Path.cwd()
    runner = get_runner(working_dir)

    # Check 1: gh CLI installed
    result = await runner.run(["gh", "--version"], timeout=5.0)
    if result.returncode == 127:  # Command not found
        raise GitHubToolsError(
            "GitHub CLI (gh) not installed. Install: https://cli.github.com/",
            check_failed="gh_installed",
        )
    if result.timed_out:
        raise GitHubToolsError(
            "GitHub CLI check timed out",
            check_failed="gh_installed",
        )
    if not result.success:
        raise GitHubToolsError(
            f"GitHub CLI (gh) returned error: {result.stderr or result.stdout}",
            check_failed="gh_installed",
        )

    # Check 2: gh CLI authenticated
    result = await runner.run(["gh", "auth", "status"], timeout=10.0)
    if not result.success:
        raise GitHubToolsError(
            "GitHub CLI not authenticated. Run: gh auth login",
            check_failed="gh_authenticated",
        )

    # Check 3: Inside git repository
    result = await runner.run(["git", "rev-parse", "--git-dir"], timeout=5.0)
    if result.returncode == 127:
        raise GitHubToolsError(
            "Git not installed",
            check_failed="git_installed",
        )
    if result.timed_out:
        raise GitHubToolsError(
            "Git repository check timed out",
            check_failed="git_repo",
        )
    if not result.success:
        raise GitHubToolsError(
            "Not inside a git repository",
            check_failed="git_repo",
        )

    # Check 4: Has remote configured
    result = await runner.run(["git", "remote", "get-url", "origin"], timeout=5.0)
    if result.timed_out:
        raise GitHubToolsError(
            "Git remote check timed out",
            check_failed="git_remote",
        )
    if not result.success:
        raise GitHubToolsError(
            "No git remote 'origin' configured",
            check_failed="git_remote",
        )

    logger.debug("GitHub tools prerequisites verified successfully")
