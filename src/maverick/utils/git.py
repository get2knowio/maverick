"""Git helper utilities for Maverick agents.

This module provides async functions for common git operations with
automatic error recovery following Constitution Principle IV.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from maverick.exceptions import GitError

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

#: Default timeout for git operations in seconds
DEFAULT_GIT_TIMEOUT: float = 30.0

#: Maximum retries for recoverable git errors
MAX_GIT_RETRIES: int = 3


# =============================================================================
# Low-level Git Operations
# =============================================================================


async def _run_git_command(
    *args: str,
    cwd: Path,
    timeout: float = DEFAULT_GIT_TIMEOUT,
    check: bool = True,
) -> tuple[str, str, int]:
    """Run a git command asynchronously.

    Args:
        *args: Git command arguments (without 'git' prefix).
        cwd: Working directory for the command.
        timeout: Timeout in seconds.
        check: If True, raise GitError on non-zero exit.

    Returns:
        Tuple of (stdout, stderr, return_code).

    Raises:
        GitError: If check=True and command fails.
        asyncio.TimeoutError: If command times out.
    """
    process = await asyncio.create_subprocess_exec(
        "git", *args,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        raise GitError(
            f"Git command timed out after {timeout}s: git {' '.join(args)}",
            operation=args[0] if args else "unknown",
            recoverable=True,
        )

    stdout = stdout_bytes.decode().strip()
    stderr = stderr_bytes.decode().strip()
    return_code = process.returncode or 0

    if check and return_code != 0:
        raise GitError(
            f"Git command failed: {stderr or stdout}",
            operation=args[0] if args else "unknown",
            recoverable=_is_recoverable_error(stderr),
        )

    return stdout, stderr, return_code


def _is_recoverable_error(stderr: str) -> bool:
    """Check if a git error is potentially recoverable."""
    recoverable_patterns = [
        "dirty",
        "uncommitted changes",
        "not staged",
        "pre-commit hook",
        "hook failed",
    ]
    stderr_lower = stderr.lower()
    return any(pattern in stderr_lower for pattern in recoverable_patterns)


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
    stdout, _, _ = await _run_git_command(
        "status", "--porcelain",
        cwd=cwd,
        check=False,
    )
    return bool(stdout.strip())


async def stash_changes(cwd: Path, message: str = "maverick-auto-stash") -> bool:
    """Stash uncommitted changes.

    Args:
        cwd: Working directory.
        message: Stash message for identification.

    Returns:
        True if changes were stashed, False if nothing to stash.
    """
    if not await has_uncommitted_changes(cwd):
        return False

    await _run_git_command(
        "stash", "push", "-m", message,
        cwd=cwd,
    )
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
    # List stashes to find our auto-stash
    stdout, _, _ = await _run_git_command(
        "stash", "list",
        cwd=cwd,
        check=False,
    )

    if not stdout or message not in stdout:
        return False

    # Find the stash index
    for line in stdout.split("\n"):
        if message in line:
            # Extract stash ref (e.g., "stash@{0}")
            stash_ref = line.split(":")[0]
            await _run_git_command(
                "stash", "pop", stash_ref,
                cwd=cwd,
            )
            logger.debug("Restored stashed changes: %s", stash_ref)
            return True

    return False


# =============================================================================
# Commit Operations
# =============================================================================


async def stage_files(cwd: Path, *paths: str) -> None:
    """Stage files for commit.

    Args:
        cwd: Working directory.
        *paths: File paths to stage. Use "." for all changes.
    """
    await _run_git_command("add", *paths, cwd=cwd)


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
    for attempt in range(MAX_GIT_RETRIES if auto_recover else 1):
        try:
            # Stage all changes first
            await stage_files(cwd, ".")

            # Create the commit
            stdout, _, _ = await _run_git_command(
                "commit", "-m", message,
                cwd=cwd,
            )

            # Extract commit SHA
            sha = await get_head_sha(cwd)
            logger.info("Created commit %s: %s", sha[:7], message.split("\n")[0])
            return sha

        except GitError as e:
            if not auto_recover or attempt >= MAX_GIT_RETRIES - 1:
                raise

            # Try recovery
            if e.recoverable:
                logger.warning("Commit failed (attempt %d), attempting recovery: %s", attempt + 1, e.message)
                await _attempt_recovery(cwd, e)
            else:
                raise

    raise GitError("Commit failed after all recovery attempts", operation="commit")


async def _attempt_recovery(cwd: Path, error: GitError) -> None:
    """Attempt to recover from a git error.

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
            process = await asyncio.create_subprocess_exec(
                "ruff", "format", ".",
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
    stdout, _, _ = await _run_git_command(
        "rev-parse", "HEAD",
        cwd=cwd,
    )
    return stdout.strip()


async def get_current_branch(cwd: Path) -> str:
    """Get the current branch name.

    Args:
        cwd: Working directory.

    Returns:
        Branch name.
    """
    stdout, _, _ = await _run_git_command(
        "rev-parse", "--abbrev-ref", "HEAD",
        cwd=cwd,
    )
    return stdout.strip()


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
    stdout, _, return_code = await _run_git_command(
        "diff", "--numstat", ref,
        cwd=cwd,
        check=False,
    )

    if return_code != 0 or not stdout:
        return {}

    stats: dict[str, tuple[int, int]] = {}
    for line in stdout.split("\n"):
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) >= 3:
            added = int(parts[0]) if parts[0] != "-" else 0
            removed = int(parts[1]) if parts[1] != "-" else 0
            file_path = parts[2]
            stats[file_path] = (added, removed)

    return stats
