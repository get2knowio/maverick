"""Git utility MCP tools for Maverick agents.

This module provides MCP tools for git operations (branch, commit, push, diff).
Tools are async functions decorated with @tool that return MCP-formatted responses.

Usage:
    from maverick.tools.git import create_git_tools_server

    server = create_git_tools_server()
    agent = MaverickAgent(mcp_servers={"git-tools": server})
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool
from claude_agent_sdk.types import McpSdkServerConfig

from maverick.exceptions import GitToolsError

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

#: Default timeout for git operations in seconds
DEFAULT_TIMEOUT: float = 30.0

#: MCP Server configuration
SERVER_NAME: str = "git-tools"
SERVER_VERSION: str = "1.0.0"

#: Valid conventional commit types
COMMIT_TYPES: set[str] = {
    "feat",
    "fix",
    "docs",
    "style",
    "refactor",
    "test",
    "chore",
}


# =============================================================================
# Helper Functions
# =============================================================================


def _success_response(data: dict[str, Any]) -> dict[str, Any]:
    """Create MCP success response.

    Args:
        data: Response data to serialize.

    Returns:
        MCP-formatted success response.
    """
    return {"content": [{"type": "text", "text": json.dumps(data)}]}


def _error_response(
    message: str,
    error_code: str,
    retry_after_seconds: int | None = None,
) -> dict[str, Any]:
    """Create MCP error response.

    Args:
        message: Human-readable error message.
        error_code: Machine-readable error code.
        retry_after_seconds: Optional retry delay for rate limiting.

    Returns:
        MCP-formatted error response.
    """
    error_data: dict[str, Any] = {
        "isError": True,
        "message": message,
        "error_code": error_code,
    }
    if retry_after_seconds is not None:
        error_data["retry_after_seconds"] = retry_after_seconds
    return {"content": [{"type": "text", "text": json.dumps(error_data)}]}


async def _verify_git_prerequisites(cwd: Path | None = None) -> None:
    """Verify git is installed and we're in a repository.

    Args:
        cwd: Working directory to check.

    Raises:
        GitToolsError: If any prerequisite check fails.
    """
    # Check git installed
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        if proc.returncode != 0:
            raise GitToolsError(
                "git is not installed or not in PATH",
                check_failed="git_installed",
            )
    except FileNotFoundError as err:
        raise GitToolsError(
            "git is not installed or not in PATH",
            check_failed="git_installed",
        ) from err

    # Check inside git repo
    proc = await asyncio.create_subprocess_exec(
        "git",
        "rev-parse",
        "--git-dir",
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()
    if proc.returncode != 0:
        raise GitToolsError(
            "not inside a git repository",
            check_failed="in_git_repo",
        )


async def _run_git_command(
    *args: str,
    cwd: Path | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> tuple[str, str, int]:
    """Run a git command asynchronously.

    Args:
        *args: git command arguments (without 'git' prefix).
        cwd: Working directory for the command.
        timeout: Timeout in seconds.

    Returns:
        Tuple of (stdout, stderr, return_code).

    Raises:
        asyncio.TimeoutError: If command times out.
    """
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(),
            timeout=timeout,
        )
        return (
            stdout_bytes.decode("utf-8", errors="replace").strip(),
            stderr_bytes.decode("utf-8", errors="replace").strip(),
            proc.returncode or 0,
        )
    except asyncio.TimeoutError:
        # Kill the process on timeout
        try:
            proc.kill()
            await proc.wait()
        except ProcessLookupError:
            pass
        raise


def _format_commit_message(
    message: str,
    commit_type: str | None = None,
    scope: str | None = None,
    breaking: bool = False,
) -> str:
    """Format a commit message in conventional commit format.

    Args:
        message: Commit description.
        commit_type: Conventional commit type (feat, fix, etc.).
        scope: Optional scope in parentheses.
        breaking: Add ! for breaking changes.

    Returns:
        Formatted commit message.

    Examples:
        >>> _format_commit_message("add feature", "feat", "api")
        'feat(api): add feature'
        >>> _format_commit_message("breaking change", "feat", breaking=True)
        'feat!: breaking change'
    """
    if not commit_type:
        return message

    prefix = commit_type
    if scope:
        prefix = f"{prefix}({scope})"
    if breaking:
        prefix = f"{prefix}!"

    return f"{prefix}: {message}"


# =============================================================================
# Factory Function
# =============================================================================


def create_git_tools_server(
    cwd: Path | None = None,
    skip_verification: bool = True,
) -> McpSdkServerConfig:
    """Create MCP server with all git tools registered (T048).

    This factory function creates an MCP server instance with all 5 git
    tools registered. Verification is lazy - tools will verify prerequisites
    on first use via _verify_git_prerequisites().

    Args:
        cwd: Working directory for prerequisite checks and git operations.
            Defaults to current working directory.
        skip_verification: Deprecated parameter, ignored. Verification is
            always lazy to avoid asyncio.run() in factory functions.

    Returns:
        Configured MCP server instance.

    Example:
        ```python
        from maverick.tools.git import create_git_tools_server

        server = create_git_tools_server()
        agent = MaverickAgent(
            mcp_servers={"git-tools": server},
            allowed_tools=["mcp__git-tools__git_commit"],
        )
        ```
    """
    # Capture cwd in closure (no global state)
    _cwd = cwd

    logger.info("Creating git tools MCP server (version %s)", SERVER_VERSION)

    # Define all tool functions inside the factory to capture _cwd in closure
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
        """
        # Extract arguments
        message = args.get("message", "").strip()
        commit_type = args.get("type")
        scope = args.get("scope")
        breaking = args.get("breaking", False)

        # Get working directory from closure
        working_dir = _cwd or Path.cwd()

        # T021: Input validation
        if not message:
            logger.warning("git_commit called with empty message")
            return _error_response("Commit message cannot be empty", "INVALID_INPUT")

        # Validate commit type if provided
        if commit_type and commit_type not in COMMIT_TYPES:
            logger.warning("git_commit called with invalid type: %s", commit_type)
            valid_types = ", ".join(sorted(COMMIT_TYPES))
            return _error_response(
                f"Invalid commit type '{commit_type}'. Must be one of: {valid_types}",
                "INVALID_INPUT",
            )

        # Format the commit message
        formatted_message = _format_commit_message(
            message, commit_type, scope, breaking
        )

        # T023: Log the operation
        logger.info(
            "Creating commit: message='%s', type=%s, scope=%s, breaking=%s",
            message,
            commit_type,
            scope,
            breaking,
        )

        try:
            # Create the commit
            stdout, stderr, return_code = await _run_git_command(
                "commit",
                "-m",
                formatted_message,
                cwd=working_dir,
            )

            # T022: Check for nothing to commit
            if return_code != 0:
                stderr_lower = stderr.lower()
                stdout_lower = stdout.lower()

                # Check for "nothing to commit" in various forms
                if (
                    "nothing to commit" in stderr_lower
                    or "nothing to commit" in stdout_lower
                    or "nothing added to commit" in stderr_lower
                    or "nothing added to commit" in stdout_lower
                ):
                    logger.info("git_commit: nothing to commit")
                    return _error_response(
                        "No changes staged for commit. "
                        "Use 'git add' to stage files first.",
                        "NOTHING_TO_COMMIT",
                    )

                # Other errors
                error_message = stderr or stdout or "Unknown git error"
                logger.error("git_commit failed: %s", error_message)
                return _error_response(
                    f"Git commit failed: {error_message}", "GIT_ERROR"
                )

            # Get the commit SHA
            sha_stdout, sha_stderr, sha_return_code = await _run_git_command(
                "rev-parse",
                "HEAD",
                cwd=working_dir,
            )

            if sha_return_code != 0:
                # Commit succeeded but couldn't get SHA (unusual but handle it)
                logger.warning(
                    "Commit created but couldn't retrieve SHA: %s", sha_stderr
                )
                commit_sha = "unknown"
            else:
                commit_sha = sha_stdout.strip()

            logger.info("Commit created successfully: %s", commit_sha)

            return _success_response(
                {
                    "success": True,
                    "commit_sha": commit_sha,
                    "message": formatted_message,
                }
            )

        except asyncio.TimeoutError:
            logger.error("git_commit timed out")
            return _error_response(
                f"Git commit operation timed out after {DEFAULT_TIMEOUT} seconds",
                "TIMEOUT",
            )
        except Exception as e:
            logger.exception("Unexpected error in git_commit")
            return _error_response(f"Unexpected error: {str(e)}", "INTERNAL_ERROR")

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

        Error codes:
            - NOT_A_REPOSITORY: Not inside a git repository
            - DETACHED_HEAD: Cannot push from detached HEAD
            - AUTHENTICATION_REQUIRED: Authentication failure
            - NETWORK_ERROR: Network connectivity issues
            - GIT_ERROR: Other git operation failures
        """
        logger.info("git_push: Starting push operation")

        # Get working directory from closure
        working_dir = _cwd or Path.cwd()

        try:
            # Verify prerequisites
            await _verify_git_prerequisites(working_dir)
        except GitToolsError as e:
            logger.error("git_push: Prerequisites check failed: %s", e)
            return _error_response(str(e), "NOT_A_REPOSITORY")

        set_upstream = args.get("set_upstream", False)

        # Check if we're in detached HEAD state
        try:
            stdout, stderr, returncode = await _run_git_command(
                "rev-parse", "--abbrev-ref", "HEAD", cwd=working_dir
            )
            if returncode == 0 and stdout == "HEAD":
                logger.error("git_push: Cannot push from detached HEAD state")
                return _error_response(
                    "Cannot push from detached HEAD state. "
                    "Create a branch first with git_create_branch",
                    "DETACHED_HEAD",
                )
            current_branch = stdout
        except Exception as e:
            logger.error("git_push: Failed to get current branch: %s", e)
            return _error_response(str(e), "GIT_ERROR")

        # Build push command
        push_args = ["push"]
        if set_upstream:
            push_args.extend(["-u", "origin", current_branch])

        # Execute push
        try:
            stdout, stderr, returncode = await _run_git_command(
                *push_args, cwd=working_dir
            )

            if returncode != 0:
                # Check for authentication errors
                if any(
                    pattern in stderr.lower()
                    for pattern in [
                        "authentication failed",
                        "could not read",
                        "permission denied",
                        "credentials",
                    ]
                ):
                    logger.error("git_push: Authentication failed: %s", stderr)
                    return _error_response(
                        f"Authentication required: {stderr}. "
                        "Run 'gh auth login' or configure git credentials",
                        "AUTHENTICATION_REQUIRED",
                    )

                # Check for network errors
                if any(
                    pattern in stderr.lower()
                    for pattern in [
                        "could not resolve host",
                        "connection refused",
                        "network",
                        "timeout",
                    ]
                ):
                    logger.error("git_push: Network error: %s", stderr)
                    return _error_response(
                        f"Network error: {stderr}",
                        "NETWORK_ERROR",
                    )

                # Generic git error
                logger.error("git_push: Git push failed: %s", stderr)
                return _error_response(f"Git push failed: {stderr}", "GIT_ERROR")

            # Parse output to count commits pushed
            commits_pushed = 0
            output_text = stdout + stderr

            # Look for patterns like "main -> main" or "branch-name -> branch-name"
            # or count commits in the output
            for line in output_text.split("\n"):
                if "->" in line and current_branch in line:
                    # Successfully pushed
                    commits_pushed = 1  # At least one commit
                    break

            # Get remote name (usually origin)
            remote = "origin"

            logger.info(
                "git_push: Successfully pushed %d commits to %s/%s",
                commits_pushed,
                remote,
                current_branch,
            )

            return _success_response(
                {
                    "success": True,
                    "commits_pushed": commits_pushed,
                    "remote": remote,
                    "branch": current_branch,
                }
            )

        except asyncio.TimeoutError:
            logger.error("git_push: Operation timed out")
            return _error_response("Push operation timed out", "NETWORK_ERROR")
        except Exception as e:
            logger.error("git_push: Unexpected error: %s", e)
            return _error_response(str(e), "GIT_ERROR")

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
            Returns "(detached)" if in detached HEAD state.

        Error codes:
            - NOT_A_REPOSITORY: Not inside a git repository
            - GIT_ERROR: Other git operation failures
        """
        logger.info("git_current_branch: Getting current branch")

        # Get working directory from closure
        working_dir = _cwd or Path.cwd()

        try:
            # Verify prerequisites
            await _verify_git_prerequisites(working_dir)
        except GitToolsError as e:
            logger.error("git_current_branch: Prerequisites check failed: %s", e)
            return _error_response(str(e), "NOT_A_REPOSITORY")

        try:
            stdout, stderr, returncode = await _run_git_command(
                "rev-parse", "--abbrev-ref", "HEAD", cwd=working_dir
            )

            if returncode != 0:
                logger.error("git_current_branch: Failed to get branch: %s", stderr)
                return _error_response(
                    f"Failed to get current branch: {stderr}",
                    "GIT_ERROR",
                )

            branch_name = stdout if stdout != "HEAD" else "(detached)"
            logger.info("git_current_branch: Current branch is '%s'", branch_name)

            return _success_response({"branch": branch_name})

        except asyncio.TimeoutError:
            logger.error("git_current_branch: Operation timed out")
            return _error_response("Operation timed out", "GIT_ERROR")
        except Exception as e:
            logger.error("git_current_branch: Unexpected error: %s", e)
            return _error_response(str(e), "GIT_ERROR")

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
            Parses output like "3 files changed, 50 insertions(+), 20 deletions(-)"

        Error codes:
            - NOT_A_REPOSITORY: Not inside a git repository
            - GIT_ERROR: Other git operation failures
        """
        logger.info("git_diff_stats: Getting diff statistics")

        # Get working directory from closure
        working_dir = _cwd or Path.cwd()

        try:
            # Verify prerequisites
            await _verify_git_prerequisites(working_dir)
        except GitToolsError as e:
            logger.error("git_diff_stats: Prerequisites check failed: %s", e)
            return _error_response(str(e), "NOT_A_REPOSITORY")

        try:
            stdout, stderr, returncode = await _run_git_command(
                "diff", "--shortstat", cwd=working_dir
            )

            if returncode != 0:
                logger.error("git_diff_stats: Failed to get diff stats: %s", stderr)
                return _error_response(
                    f"Failed to get diff statistics: {stderr}",
                    "GIT_ERROR",
                )

            # Parse the output
            files_changed = 0
            insertions = 0
            deletions = 0

            if stdout:
                # Example: " 3 files changed, 50 insertions(+), 20 deletions(-)"
                # Extract numbers using regex
                files_match = re.search(r"(\d+)\s+files?\s+changed", stdout)
                insertions_match = re.search(r"(\d+)\s+insertions?", stdout)
                deletions_match = re.search(r"(\d+)\s+deletions?", stdout)

                if files_match:
                    files_changed = int(files_match.group(1))
                if insertions_match:
                    insertions = int(insertions_match.group(1))
                if deletions_match:
                    deletions = int(deletions_match.group(1))

            logger.info(
                "git_diff_stats: %d files, %d insertions, %d deletions",
                files_changed,
                insertions,
                deletions,
            )

            return _success_response(
                {
                    "files_changed": files_changed,
                    "insertions": insertions,
                    "deletions": deletions,
                }
            )

        except asyncio.TimeoutError:
            logger.error("git_diff_stats: Operation timed out")
            return _error_response("Operation timed out", "GIT_ERROR")
        except Exception as e:
            logger.error("git_diff_stats: Unexpected error: %s", e)
            return _error_response(str(e), "GIT_ERROR")

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

        Error codes:
            - NOT_A_REPOSITORY: Not inside a git repository
            - INVALID_INPUT: Invalid branch name
            - BRANCH_EXISTS: Branch already exists
            - BRANCH_NOT_FOUND: Base branch doesn't exist
            - GIT_ERROR: Other git operation failures
        """
        logger.info("git_create_branch: Creating new branch")

        # Get working directory from closure
        working_dir = _cwd or Path.cwd()

        try:
            # Verify prerequisites
            await _verify_git_prerequisites(working_dir)
        except GitToolsError as e:
            logger.error("git_create_branch: Prerequisites check failed: %s", e)
            return _error_response(str(e), "NOT_A_REPOSITORY")

        # Validate required arguments
        branch_name = args.get("name")
        if not branch_name:
            logger.error("git_create_branch: Branch name is required")
            return _error_response("Branch name is required", "INVALID_INPUT")

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
            return _error_response(error_msg, "INVALID_INPUT")

        base_branch = args.get("base", "")

        # Build checkout command
        checkout_args = ["checkout", "-b", branch_name]
        if base_branch:
            checkout_args.append(base_branch)

        try:
            stdout, stderr, returncode = await _run_git_command(
                *checkout_args, cwd=working_dir
            )

            if returncode != 0:
                # Check for branch already exists
                if "already exists" in stderr.lower():
                    logger.error(
                        "git_create_branch: Branch '%s' already exists", branch_name
                    )
                    return _error_response(
                        f"Branch '{branch_name}' already exists",
                        "BRANCH_EXISTS",
                    )

                # Check for base branch not found
                if (
                    "not found" in stderr.lower()
                    or "did not match" in stderr.lower()
                    or "unknown revision" in stderr.lower()
                ):
                    logger.error(
                        "git_create_branch: Base branch '%s' not found", base_branch
                    )
                    return _error_response(
                        f"Base branch '{base_branch}' not found",
                        "BRANCH_NOT_FOUND",
                    )

                # Generic git error
                logger.error("git_create_branch: Failed to create branch: %s", stderr)
                return _error_response(
                    f"Failed to create branch: {stderr}",
                    "GIT_ERROR",
                )

            # Successfully created branch
            effective_base = base_branch if base_branch else "(current)"
            logger.info(
                "git_create_branch: Created and checked out branch '%s' from '%s'",
                branch_name,
                effective_base,
            )

            return _success_response(
                {
                    "success": True,
                    "branch": branch_name,
                    "base": effective_base,
                }
            )

        except asyncio.TimeoutError:
            logger.error("git_create_branch: Operation timed out")
            return _error_response("Operation timed out", "GIT_ERROR")
        except Exception as e:
            logger.error("git_create_branch: Unexpected error: %s", e)
            return _error_response(str(e), "GIT_ERROR")

    # Store tools for test access
    tools = {
        "git_commit": git_commit,
        "git_push": git_push,
        "git_current_branch": git_current_branch,
        "git_diff_stats": git_diff_stats,
        "git_create_branch": git_create_branch,
    }

    # Create and return MCP server with all tools
    server = create_sdk_mcp_server(
        name=SERVER_NAME,
        version=SERVER_VERSION,
        tools=list(tools.values()),
    )

    # Add tools to the server dict for test access
    # Type ignore because we're adding to the dict for test purposes
    server["tools"] = tools  # type: ignore[typeddict-unknown-key]

    return server
