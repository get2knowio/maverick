"""Git diff tool for MCP.

Provides the git_diff_stats tool for getting statistics about uncommitted changes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from claude_agent_sdk import tool

from maverick.exceptions import NotARepositoryError
from maverick.git import AsyncGitRepository
from maverick.logging import get_logger
from maverick.tools.git.responses import error_response, success_response

logger = get_logger(__name__)


def create_git_diff_stats_tool(cwd: Path | None = None) -> Any:
    """Create git_diff_stats tool with working directory closure.

    Args:
        cwd: Working directory for git operations.

    Returns:
        Decorated tool function.
    """
    _cwd = cwd

    def _get_repo() -> AsyncGitRepository:
        """Get AsyncGitRepository with current working directory."""
        working_dir = _cwd or Path.cwd()
        return AsyncGitRepository(working_dir)

    @tool(
        "git_diff_stats",
        "Get statistics about uncommitted changes",
        {},
    )
    async def git_diff_stats(args: dict[str, Any]) -> dict[str, Any]:
        """Get statistics about uncommitted changes.

        Args:
            args: Tool arguments (none required).

        Returns:
            MCP response with diff statistics or error.

        Raises:
            Never raises - always returns MCP response format with success or error.
            Error codes returned:
            - NOT_A_REPOSITORY: Not inside a git repository
            - GIT_ERROR: Other git operation failures
        """
        logger.info("git_diff_stats: Getting diff statistics")

        try:
            repo = _get_repo()

            # Get diff stats using AsyncGitRepository
            stats = await repo.diff_stats()

            logger.info(
                "git_diff_stats: %d files, %d insertions, %d deletions",
                stats.files_changed,
                stats.insertions,
                stats.deletions,
            )

            return success_response(
                {
                    "files_changed": stats.files_changed,
                    "insertions": stats.insertions,
                    "deletions": stats.deletions,
                }
            )

        except NotARepositoryError:
            logger.error("git_diff_stats: Not inside a git repository")
            return error_response("Not inside a git repository", "NOT_A_REPOSITORY")
        except Exception as e:
            logger.error("git_diff_stats: Unexpected error: %s", e)
            return error_response(str(e), "GIT_ERROR")

    return git_diff_stats
