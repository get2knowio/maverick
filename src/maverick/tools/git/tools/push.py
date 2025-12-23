"""Git push tool for MCP.

This module provides the git_push tool for pushing commits to remote repositories.
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


def create_git_push_tool(cwd: Path | None = None) -> Any:
    """Create git_push tool with working directory closure.

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
        "git_push",
        "Push commits to remote repository",
        {"set_upstream": bool},
    )
    async def git_push(args: dict[str, Any]) -> dict[str, Any]:
        """Push commits to remote repository.

        Args:
            args: Tool arguments containing:
                - set_upstream (bool): Set upstream tracking if true.

        Returns:
            MCP response with push details or error.

        Raises:
            Never raises - always returns MCP response format with success or error.
            Error codes returned:
            - NOT_A_REPOSITORY: Not inside a git repository
            - DETACHED_HEAD: Cannot push from detached HEAD
            - AUTHENTICATION_REQUIRED: Authentication failure
            - NETWORK_ERROR: Network connectivity issues
            - GIT_ERROR: Other git operation failures
        """
        logger.info("git_push: Starting push operation")

        try:
            runner = _get_runner()

            # Verify prerequisites using GitRunner
            if not await runner.is_inside_repo():
                logger.error("git_push: Not inside a git repository")
                return error_response("Not inside a git repository", "NOT_A_REPOSITORY")

            set_upstream = args.get("set_upstream", False)

            # Check if we're in detached HEAD state using GitRunner
            current_branch = await runner.get_current_branch()
            if current_branch == "(detached)":
                logger.error("git_push: Cannot push from detached HEAD state")
                return error_response(
                    "Cannot push from detached HEAD state. "
                    "Create a branch first with git_create_branch",
                    "DETACHED_HEAD",
                )

            # Execute push using GitRunner
            result = await runner.push(
                remote="origin",
                branch=current_branch if set_upstream else None,
                set_upstream=set_upstream,
            )

            if not result.success:
                error_msg = (result.error or "").lower()

                # Check for authentication errors
                if any(
                    pattern in error_msg
                    for pattern in [
                        "authentication failed",
                        "could not read",
                        "permission denied",
                        "credentials",
                    ]
                ):
                    logger.error("git_push: Authentication failed: %s", result.error)
                    return error_response(
                        f"Authentication required: {result.error}. "
                        "Run 'gh auth login' or configure git credentials",
                        "AUTHENTICATION_REQUIRED",
                    )

                # Check for network errors
                if any(
                    pattern in error_msg
                    for pattern in [
                        "could not resolve host",
                        "connection refused",
                        "network",
                        "timeout",
                    ]
                ):
                    logger.error("git_push: Network error: %s", result.error)
                    return error_response(
                        f"Network error: {result.error}",
                        "NETWORK_ERROR",
                    )

                # Generic git error
                logger.error("git_push: Git push failed: %s", result.error)
                return error_response(f"Git push failed: {result.error}", "GIT_ERROR")

            # Parse output to count commits pushed
            commits_pushed = 0
            output_text = result.output

            # Look for patterns like "main -> main" or count commits
            for line in output_text.split("\n"):
                if "->" in line and current_branch in line:
                    commits_pushed = 1  # At least one commit
                    break

            remote = "origin"

            logger.info(
                "git_push: Successfully pushed %d commits to %s/%s",
                commits_pushed,
                remote,
                current_branch,
            )

            return success_response(
                {
                    "success": True,
                    "commits_pushed": commits_pushed,
                    "remote": remote,
                    "branch": current_branch,
                }
            )

        except Exception as e:
            logger.error("git_push: Unexpected error: %s", e)
            return error_response(str(e), "GIT_ERROR")

    return git_push
