"""Git branch tools for MCP.

Provides tools for branch operations: getting current branch and creating branches.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from claude_agent_sdk import tool

from maverick.exceptions import BranchExistsError, GitError, NotARepositoryError
from maverick.git import AsyncGitRepository
from maverick.logging import get_logger
from maverick.tools.git.responses import error_response, success_response

logger = get_logger(__name__)


def create_git_current_branch_tool(cwd: Path | None = None) -> Any:
    """Create git_current_branch tool with working directory closure.

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
        "git_current_branch",
        "Get the current git branch name",
        {},
    )
    async def git_current_branch(args: dict[str, Any]) -> dict[str, Any]:
        """Get the current git branch name.

        Args:
            args: Tool arguments (none required).

        Returns:
            MCP response with branch name or error.
            Returns the commit SHA if in detached HEAD state.

        Raises:
            Never raises - always returns MCP response format with success or error.
            Error codes returned:
            - NOT_A_REPOSITORY: Not inside a git repository
            - GIT_ERROR: Other git operation failures
        """
        logger.info("git_current_branch: Getting current branch")

        try:
            repo = _get_repo()

            # Get current branch using AsyncGitRepository
            branch_name = await repo.current_branch()
            logger.info("git_current_branch: Current branch is '%s'", branch_name)

            return success_response({"branch": branch_name})

        except NotARepositoryError:
            logger.error("git_current_branch: Not inside a git repository")
            return error_response("Not inside a git repository", "NOT_A_REPOSITORY")
        except Exception as e:
            logger.error("git_current_branch: Unexpected error: %s", e)
            return error_response(str(e), "GIT_ERROR")

    return git_current_branch


def create_git_create_branch_tool(cwd: Path | None = None) -> Any:
    """Create git_create_branch tool with working directory closure.

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
        "git_create_branch",
        "Create and checkout a new git branch",
        {"name": str, "base": str},
    )
    async def git_create_branch(args: dict[str, Any]) -> dict[str, Any]:
        """Create and checkout a new git branch.

        Args:
            args: Tool arguments containing:
                - name (str): Name of the new branch.
                - base (str, optional): Base branch to create from
                    (default: current branch).

        Returns:
            MCP response with branch creation details or error.

        Raises:
            Never raises - always returns MCP response format with success or error.
            Error codes returned:
            - NOT_A_REPOSITORY: Not inside a git repository
            - INVALID_INPUT: Invalid branch name
            - BRANCH_EXISTS: Branch already exists
            - BRANCH_NOT_FOUND: Base branch doesn't exist
            - GIT_ERROR: Other git operation failures
        """
        logger.info("git_create_branch: Creating new branch")

        try:
            repo = _get_repo()

            # Validate required arguments
            branch_name = args.get("name")
            if not branch_name:
                logger.error("git_create_branch: Branch name is required")
                return error_response("Branch name is required", "INVALID_INPUT")

            # Comprehensive branch name validation (git check-ref-format rules)
            validation_errors = []

            # Cannot start or end with dot
            if branch_name.startswith(".") or branch_name.endswith("."):
                validation_errors.append("cannot start or end with '.'")

            # No consecutive dots (..)
            if ".." in branch_name:
                validation_errors.append("cannot contain consecutive dots '..'")

            # No @{ sequence
            if "@{" in branch_name:
                validation_errors.append("cannot contain '@{' sequence")

            # Invalid characters: space, ~, ^, :, ?, *, [, \, control characters
            invalid_chars = {" ", "~", "^", ":", "?", "*", "[", "\\"}
            found_invalid = [char for char in invalid_chars if char in branch_name]
            if found_invalid:
                chars_str = ", ".join(repr(c) for c in found_invalid)
                validation_errors.append(f"cannot contain characters: {chars_str}")

            # Check for control characters (ASCII 0-31, 127)
            if any(ord(char) < 32 or ord(char) == 127 for char in branch_name):
                validation_errors.append("cannot contain control characters")

            if validation_errors:
                logger.error("git_create_branch: Invalid branch name: %s", branch_name)
                errors_str = "; ".join(validation_errors)
                error_msg = f"Invalid branch name '{branch_name}': {errors_str}"
                return error_response(error_msg, "INVALID_INPUT")

            base_branch = args.get("base", "HEAD")

            # Create branch using AsyncGitRepository
            await repo.create_branch(branch_name, checkout=True, from_ref=base_branch)

            # Successfully created branch
            effective_base = base_branch if base_branch != "HEAD" else "(current)"
            logger.info(
                "git_create_branch: Created and checked out branch '%s' from '%s'",
                branch_name,
                effective_base,
            )

            return success_response(
                {
                    "success": True,
                    "branch": branch_name,
                    "base": effective_base,
                }
            )

        except NotARepositoryError:
            logger.error("git_create_branch: Not inside a git repository")
            return error_response("Not inside a git repository", "NOT_A_REPOSITORY")
        except BranchExistsError:
            logger.error(
                "git_create_branch: Branch '%s' already exists", args.get("name", "")
            )
            return error_response(
                f"Branch '{args.get('name', '')}' already exists",
                "BRANCH_EXISTS",
            )
        except ValueError as e:
            # GitRepository raises ValueError for invalid branch names
            logger.error("git_create_branch: Invalid branch name: %s", e)
            return error_response(str(e), "INVALID_INPUT")
        except GitError as e:
            # Check for base branch not found in error message
            error_msg = str(e).lower()
            base_branch = args.get("base", "HEAD")
            if (
                "not found" in error_msg
                or "did not match" in error_msg
                or "unknown revision" in error_msg
            ):
                logger.error(
                    "git_create_branch: Base branch '%s' not found", base_branch
                )
                return error_response(
                    f"Base branch '{base_branch}' not found",
                    "BRANCH_NOT_FOUND",
                )
            logger.error("git_create_branch: Failed to create branch: %s", e)
            return error_response(f"Failed to create branch: {e}", "GIT_ERROR")
        except Exception as e:
            logger.error("git_create_branch: Unexpected error: %s", e)
            return error_response(str(e), "GIT_ERROR")

    return git_create_branch
