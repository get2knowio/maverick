"""Git diff tool for MCP.

Provides the git_diff_stats tool for getting statistics about uncommitted changes.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from claude_agent_sdk import tool

from maverick.runners.git import GitRunner
from maverick.tools.git.constants import DEFAULT_TIMEOUT
from maverick.tools.git.responses import error_response, success_response

logger = logging.getLogger(__name__)


def create_git_diff_stats_tool(cwd: Path | None = None) -> Any:
    """Create git_diff_stats tool with working directory closure.

    Args:
        cwd: Working directory for git operations.

    Returns:
        Decorated tool function.
    """
    _cwd = cwd

    def _get_runner() -> GitRunner:
        """Get GitRunner with current working directory."""
        working_dir = _cwd or Path.cwd()
        return GitRunner(cwd=working_dir, timeout=DEFAULT_TIMEOUT)

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
            runner = _get_runner()

            # Verify prerequisites using GitRunner
            if not await runner.is_inside_repo():
                logger.error("git_diff_stats: Not inside a git repository")
                return error_response(
                    "Not inside a git repository", "NOT_A_REPOSITORY"
                )

            # Get diff stats using GitRunner
            stats = await runner.get_diff_stats()

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

        except Exception as e:
            logger.error("git_diff_stats: Unexpected error: %s", e)
            return error_response(str(e), "GIT_ERROR")

    return git_diff_stats
