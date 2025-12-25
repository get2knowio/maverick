"""Git helper utilities for Maverick agents.

DEPRECATED: This module is deprecated. Use maverick.git instead:
    - All functions -> maverick.git.GitRepository or maverick.git.AsyncGitRepository

This module provides async functions for common git operations with
automatic error recovery following Constitution Principle IV.

This module delegates to GitRunner from maverick.runners.git for the actual
git subprocess execution, adding error handling with GitError exceptions
and auto-recovery logic on top.
"""

from __future__ import annotations

import asyncio
import logging
import warnings
from pathlib import Path

from maverick.exceptions import GitError
from maverick.runners.git import GitRunner

# Issue deprecation warning on import
warnings.warn(
    "maverick.utils.git is deprecated. "
    "Use maverick.git.GitRepository and maverick.git.AsyncGitRepository instead.",
    DeprecationWarning,
    stacklevel=2,
)

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

#: Default timeout for git operations in seconds
DEFAULT_GIT_TIMEOUT: float = 30.0

#: Maximum retries for recoverable git errors
MAX_GIT_RETRIES: int = 3


# =============================================================================
# Internal Helpers
# =============================================================================


def _get_runner(cwd: Path, timeout: float = DEFAULT_GIT_TIMEOUT) -> GitRunner:
    """Create a GitRunner instance for the given working directory.

    Args:
        cwd: Working directory for git operations.
        timeout: Timeout for git operations in seconds.

    Returns:
        GitRunner instance configured for the directory.
    """
    return GitRunner(cwd=cwd, timeout=timeout)


def _raise_git_error(
    result_error: str | None,
    operation: str,
    default_message: str,
) -> None:
    """Raise a GitError from a GitResult error.

    Args:
        result_error: Error message from GitResult, or None.
        operation: Git operation that failed.
        default_message: Default message if result_error is None.

    Raises:
        GitError: Always raises with appropriate recoverable flag.
    """
    error_msg = result_error or default_message
    raise GitError(
        f"Git command failed: {error_msg}",
        operation=operation,
        recoverable=GitRunner.is_recoverable_error(error_msg),
    )


# =============================================================================
# Stash Operations
# =============================================================================


async def has_uncommitted_changes(cwd: Path) -> bool:
    """Check if the working directory has uncommitted changes.

    Args:
        cwd: Working directory.

    Returns:
        True if there are uncommitted changes.
    """
    runner = _get_runner(cwd)
    return await runner.is_dirty()


async def stash_changes(cwd: Path, message: str = "maverick-auto-stash") -> bool:
    """Stash uncommitted changes.

    Args:
        cwd: Working directory.
        message: Stash message for identification.

    Returns:
        True if changes were stashed, False if nothing to stash.
    """
    runner = _get_runner(cwd)

    if not await runner.is_dirty():
        return False

    result = await runner.stash(message)
    if not result.success:
        _raise_git_error(result.error, "stash", "Failed to stash changes")

    logger.debug("Stashed uncommitted changes: %s", message)
    return True


async def unstash_changes(cwd: Path, message: str = "maverick-auto-stash") -> bool:
    """Restore previously stashed changes.

    Args:
        cwd: Working directory.
        message: Stash message to match.

    Returns:
        True if changes were restored, False if stash not found.
    """
    runner = _get_runner(cwd)
    result = await runner.stash_pop_by_message(message)

    if not result.success:
        # Check if it's because no stash was found (not a real error)
        if result.error and "No stash found" in result.error:
            return False
        # Otherwise it's a real error
        _raise_git_error(result.error, "stash", "Failed to pop stash")

    logger.debug("Restored stashed changes matching: %s", message)
    return True


# =============================================================================
# Commit Operations
# =============================================================================


async def stage_files(cwd: Path, *paths: str) -> None:
    """Stage files for commit.

    Args:
        cwd: Working directory.
        *paths: File paths to stage. Use "." for all changes.

    Raises:
        GitError: If staging fails.
    """
    runner = _get_runner(cwd)

    # Convert paths to list for GitRunner.add()
    path_list = list(paths) if paths else None
    add_all = "." in paths if paths else False

    result = await runner.add(paths=path_list, add_all=add_all)
    if not result.success:
        _raise_git_error(result.error, "add", "Failed to stage files")


async def create_commit(
    message: str,
    cwd: Path,
    auto_recover: bool = True,
) -> str:
    """Create a git commit with automatic recovery.

    Args:
        message: Commit message (should follow conventional commits).
        cwd: Working directory.
        auto_recover: If True, attempt recovery on failure.

    Returns:
        Commit SHA on success.

    Raises:
        GitError: If commit fails after recovery attempts.
    """
    runner = _get_runner(cwd)

    for attempt in range(MAX_GIT_RETRIES if auto_recover else 1):
        try:
            # Stage all changes first
            await stage_files(cwd, ".")

            # Create the commit
            result = await runner.commit(message)

            if not result.success:
                error_msg = result.error or "Unknown commit error"
                raise GitError(
                    f"Git command failed: {error_msg}",
                    operation="commit",
                    recoverable=GitRunner.is_recoverable_error(error_msg),
                )

            # Get commit SHA
            sha = await runner.get_head_sha()
            logger.info("Created commit %s: %s", sha[:7], message.split("\n")[0])
            return sha

        except GitError as e:
            if not auto_recover or attempt >= MAX_GIT_RETRIES - 1:
                raise

            # Try recovery
            if e.recoverable:
                logger.warning(
                    "Commit failed (attempt %d), recovery: %s", attempt + 1, e.message
                )
                await _attempt_recovery(cwd, e)
            else:
                raise

    raise GitError("Commit failed after all recovery attempts", operation="commit")


async def _attempt_recovery(cwd: Path, error: GitError) -> None:
    """Attempt to recover from a git error.

    This handles special recovery logic that isn't in GitRunner,
    such as auto-fixing pre-commit hook failures.

    Args:
        cwd: Working directory.
        error: The error to recover from.
    """
    error_msg = error.message.lower()

    if "pre-commit hook" in error_msg or "hook failed" in error_msg:
        # Try to auto-fix formatting issues
        logger.debug("Attempting to fix pre-commit hook issues")
        try:
            # Run ruff format to fix formatting
            # TODO: Consider moving this to a dedicated formatter runner
            process = await asyncio.create_subprocess_exec(
                "ruff",
                "format",
                ".",
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(process.communicate(), timeout=60.0)

            # Stage the fixes
            await stage_files(cwd, ".")
        except Exception as e:
            logger.debug("Auto-fix failed: %s", e)


async def get_head_sha(cwd: Path) -> str:
    """Get the current HEAD commit SHA.

    Args:
        cwd: Working directory.

    Returns:
        Full commit SHA.
    """
    runner = _get_runner(cwd)
    return await runner.get_head_sha()


async def get_current_branch(cwd: Path) -> str:
    """Get the current branch name.

    Args:
        cwd: Working directory.

    Returns:
        Branch name, or "(detached)" if in detached HEAD state.
    """
    runner = _get_runner(cwd)
    return await runner.get_current_branch()


# =============================================================================
# Diff Operations
# =============================================================================


async def get_diff_stats(cwd: Path, ref: str = "HEAD") -> dict[str, tuple[int, int]]:
    """Get diff statistics showing lines added/removed per file.

    Args:
        cwd: Working directory.
        ref: Git reference to diff against (default: HEAD).

    Returns:
        Dict mapping file paths to (lines_added, lines_removed) tuples.
    """
    runner = _get_runner(cwd)
    stats = await runner.get_diff_stats(ref)
    return stats.per_file
