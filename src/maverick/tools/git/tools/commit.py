"""Git commit tool for MCP.

Provides the git_commit tool for creating commits with conventional formatting.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from claude_agent_sdk import tool

from maverick.runners.git import GitRunner
from maverick.tools.git.constants import COMMIT_TYPES, DEFAULT_TIMEOUT
from maverick.tools.git.formatting import format_commit_message
from maverick.tools.git.responses import error_response, success_response

logger = logging.getLogger(__name__)


def create_git_commit_tool(cwd: Path | None = None) -> Any:
    """Create git_commit tool with working directory closure.

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
            runner = _get_runner()

            # Stage all changes first, then commit
            add_result = await runner.add(add_all=True)
            if not add_result.success:
                logger.error(
                    "git_commit: Failed to stage changes: %s", add_result.error
                )
                return error_response(
                    f"Failed to stage changes: {add_result.error}",
                    "GIT_ERROR",
                )

            # Create the commit using GitRunner
            result = await runner.commit(formatted_message)

            if not result.success:
                error_msg = (result.error or "").lower()
                output_msg = result.output.lower()

                # T022: Check for "nothing to commit" in various forms
                if (
                    "nothing to commit" in error_msg
                    or "nothing to commit" in output_msg
                    or "nothing added to commit" in error_msg
                    or "nothing added to commit" in output_msg
                ):
                    logger.info("git_commit: nothing to commit")
                    return error_response(
                        "No changes staged for commit. "
                        "Use 'git add' to stage files first.",
                        "NOTHING_TO_COMMIT",
                    )

                # Other errors
                error_message = result.error or result.output or "Unknown git error"
                logger.error("git_commit failed: %s", error_message)
                return error_response(
                    f"Git commit failed: {error_message}", "GIT_ERROR"
                )

            # Get the commit SHA using GitRunner
            commit_sha = await runner.get_head_sha()
            logger.info("Commit created successfully: %s", commit_sha)

            return success_response(
                {
                    "success": True,
                    "commit_sha": commit_sha,
                    "message": formatted_message,
                }
            )

        except Exception as e:
            logger.exception("Unexpected error in git_commit")
            return error_response(f"Unexpected error: {str(e)}", "INTERNAL_ERROR")

    return git_commit
