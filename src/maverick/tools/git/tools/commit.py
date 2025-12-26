"""Git commit tool for MCP.

Provides the git_commit tool for creating commits with conventional formatting.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from claude_agent_sdk import tool

from maverick.exceptions import NotARepositoryError, NothingToCommitError
from maverick.git import AsyncGitRepository
from maverick.logging import get_logger
from maverick.tools.git.constants import COMMIT_TYPES
from maverick.tools.git.formatting import format_commit_message
from maverick.tools.git.responses import error_response, success_response

logger = get_logger(__name__)


def create_git_commit_tool(cwd: Path | None = None) -> Any:
    """Create git_commit tool with working directory closure.

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
        "git_commit",
        "Create a git commit with conventional commit format",
        {"message": str, "type": str, "scope": str, "breaking": bool},
    )
    async def git_commit(args: dict[str, Any]) -> dict[str, Any]:
        """Create a git commit with optional conventional commit formatting.

        Args via args dict:
            message: Commit description (required)
            type: Conventional commit type (optional: feat, fix, etc.)
            scope: Scope in parentheses (optional)
            breaking: Add ! for breaking changes (optional, default False)

        Returns:
            Success: {"success": true, "commit_sha": "...", "message": "..."}
            Error: {"isError": true, "error_code": "NOTHING_TO_COMMIT"|...}

        Raises:
            Never raises - always returns MCP response format with success or error.
        """
        # Extract arguments
        message = args.get("message", "").strip()
        commit_type = args.get("type")
        scope = args.get("scope")
        breaking = args.get("breaking", False)

        # T021: Input validation
        if not message:
            logger.warning("git_commit called with empty message")
            return error_response("Commit message cannot be empty", "INVALID_INPUT")

        # Validate commit type if provided
        if commit_type and commit_type not in COMMIT_TYPES:
            logger.warning("git_commit called with invalid type: %s", commit_type)
            valid_types = ", ".join(sorted(COMMIT_TYPES))
            return error_response(
                f"Invalid commit type '{commit_type}'. Must be one of: {valid_types}",
                "INVALID_INPUT",
            )

        # Format the commit message (MCP-specific formatting)
        formatted_message = format_commit_message(message, commit_type, scope, breaking)

        # T023: Log the operation
        logger.info(
            "Creating commit: message='%s', type=%s, scope=%s, breaking=%s",
            message,
            commit_type,
            scope,
            breaking,
        )

        try:
            repo = _get_repo()

            # Create the commit with add_all=True using AsyncGitRepository
            # This stages all changes and commits in one operation
            commit_sha = await repo.commit(formatted_message, add_all=True)
            logger.info("Commit created successfully: %s", commit_sha[:7])

            return success_response(
                {
                    "success": True,
                    "commit_sha": commit_sha,
                    "message": formatted_message,
                }
            )

        except NotARepositoryError:
            logger.error("git_commit: Not inside a git repository")
            return error_response("Not inside a git repository", "NOT_A_REPOSITORY")
        except NothingToCommitError:
            logger.info("git_commit: nothing to commit")
            return error_response(
                "No changes staged for commit. Use 'git add' to stage files first.",
                "NOTHING_TO_COMMIT",
            )
        except Exception as e:
            logger.exception("Unexpected error in git_commit")
            return error_response(f"Unexpected error: {str(e)}", "INTERNAL_ERROR")

    return git_commit
