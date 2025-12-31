"""Git push tool for MCP.

This module provides the git_push tool for pushing commits to remote repositories.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from claude_agent_sdk import tool

from maverick.exceptions import GitError, NotARepositoryError, PushRejectedError
from maverick.git import AsyncGitRepository
from maverick.logging import get_logger
from maverick.tools.git.responses import error_response, success_response

logger = get_logger(__name__)

# Constants for SHA detection
SHA_HEX_LENGTH = 40
SHA_HEX_CHARS = frozenset("0123456789abcdef")

# Error patterns for classification
_AUTH_PATTERNS = frozenset(
    [
        "authentication failed",
        "could not read",
        "permission denied",
        "credentials",
    ]
)
_NETWORK_PATTERNS = frozenset(
    [
        "could not resolve host",
        "connection refused",
        "network",
        "timeout",
    ]
)


def _classify_push_error(error: Exception) -> tuple[str, str]:
    """Classify push error and return (error_code, message).

    Args:
        error: The exception to classify.

    Returns:
        Tuple of (error_code, user_message).
    """
    error_msg = str(error).lower()

    # Check for authentication errors
    if any(pattern in error_msg for pattern in _AUTH_PATTERNS):
        return (
            "AUTHENTICATION_REQUIRED",
            f"Authentication required: {error}. "
            "Run 'gh auth login' or configure git credentials",
        )

    # Check for network errors
    if any(pattern in error_msg for pattern in _NETWORK_PATTERNS):
        return "NETWORK_ERROR", f"Network error: {error}"

    # Generic git error
    return "GIT_ERROR", f"Git push failed: {error}"


def create_git_push_tool(cwd: Path | None = None) -> Any:
    """Create git_push tool with working directory closure.

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
            repo = _get_repo()

            set_upstream = args.get("set_upstream", False)

            # Check if we're in detached HEAD state using AsyncGitRepository
            current_branch = await repo.current_branch()
            # In GitRepository, detached HEAD returns the commit SHA (40 chars)
            # We detect detached HEAD by checking if it's a valid branch name
            # A commit SHA is 40 hex chars, which is not a typical branch name
            is_detached = len(current_branch) == SHA_HEX_LENGTH and all(
                c in SHA_HEX_CHARS for c in current_branch
            )
            if is_detached:
                logger.error("git_push: Cannot push from detached HEAD state")
                return error_response(
                    "Cannot push from detached HEAD state. "
                    "Create a branch first with git_create_branch",
                    "DETACHED_HEAD",
                )

            # Execute push using AsyncGitRepository
            remote = "origin"
            await repo.push(
                remote=remote,
                branch=current_branch if set_upstream else None,
                set_upstream=set_upstream,
            )

            # Push succeeded
            logger.info(
                "git_push: Successfully pushed to %s/%s",
                remote,
                current_branch,
            )

            return success_response(
                {
                    "success": True,
                    "commits_pushed": 1,  # At least one commit was pushed
                    "remote": remote,
                    "branch": current_branch,
                }
            )

        except NotARepositoryError:
            logger.error("git_push: Not inside a git repository")
            return error_response("Not inside a git repository", "NOT_A_REPOSITORY")
        except PushRejectedError as e:
            error_code, message = _classify_push_error(e)
            logger.error("git_push: %s: %s", error_code, e)
            return error_response(message, error_code)
        except GitError as e:
            error_code, message = _classify_push_error(e)
            logger.error("git_push: %s: %s", error_code, e)
            return error_response(message, error_code)
        except Exception as e:
            logger.error("git_push: Unexpected error: %s", e)
            return error_response(str(e), "GIT_ERROR")

    return git_push
