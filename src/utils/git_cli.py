"""Git CLI helpers for branch management operations.

Provides tolerant git command runner and branch name validator
using structured logging and safe error handling.
"""

import re
import subprocess
from dataclasses import dataclass
from typing import Literal

from src.utils.logging import get_structured_logger

logger = get_structured_logger(__name__)

# Git-safe branch name pattern: alphanumeric, dots, dashes, underscores, slashes
BRANCH_NAME_PATTERN = re.compile(r"^[A-Za-z0-9._/-]+$")


class GitCommandError(Exception):
    """Exception raised when a git command fails critically."""

    pass


@dataclass
class GitCommandResult:
    """Result of executing a git command.

    Attributes:
        success: True if command succeeded (returncode 0)
        stdout: Standard output decoded as UTF-8 (tolerant)
        stderr: Standard error decoded as UTF-8 (tolerant)
        returncode: Process exit code
        error_code: Standardized error code for categorization (None if success)
        retry_hint: Suggestion whether to retry (None if success, True/False otherwise)
    """

    success: bool
    stdout: str
    stderr: str
    returncode: int
    error_code: str | None = None
    retry_hint: bool | None = None


def validate_branch_name(branch_name: str) -> None:
    """Validate that a branch name is git-safe.

    Args:
        branch_name: Branch name to validate

    Raises:
        ValueError: If branch name contains invalid characters or is empty
    """
    if not branch_name or not branch_name.strip():
        raise ValueError("Invalid git branch name: cannot be empty")

    if not BRANCH_NAME_PATTERN.match(branch_name):
        raise ValueError(
            f"Invalid git branch name: '{branch_name}' - "
            "must contain only alphanumeric, dots, dashes, underscores, or slashes"
        )

    logger.debug("branch_name_validated", branch_name=branch_name)


def _classify_git_error(
    returncode: int, stderr: str
) -> tuple[str | None, bool | None]:
    """Classify git error and determine retry hint.

    Args:
        returncode: Git command exit code
        stderr: Git command stderr output

    Returns:
        Tuple of (error_code, retry_hint)
        - error_code: Standardized error category
        - retry_hint: True if transient, False if permanent, None if unknown
    """
    stderr_lower = stderr.lower()

    # Transient network/remote errors - suggest retry
    if any(
        keyword in stderr_lower
        for keyword in [
            "connection timed out",
            "could not resolve host",
            "connection refused",
            "unable to access",
            "temporary failure",
        ]
    ):
        return ("network_error", True)

    # Repository state errors - might be transient
    if "lock" in stderr_lower or "locked" in stderr_lower:
        return ("lock_error", True)

    # Branch does not exist - permanent error
    if (
        "did not match any file" in stderr_lower
        or "unknown revision" in stderr_lower
        or "not a valid ref" in stderr_lower
    ):
        return ("missing_ref", False)

    # Dirty working tree - permanent until user fixes
    if "uncommitted changes" in stderr_lower or "would be overwritten" in stderr_lower:
        return ("dirty_worktree", False)

    # Generic error - return code hint
    if returncode == 128:
        # Git fatal errors, often configuration/setup issues
        return ("git_fatal", False)

    return ("unknown_error", None)


def run_git_command(
    args: list[str],
    cwd: str | None = None,
    timeout: int | None = None,
) -> GitCommandResult:
    """Run a git command with tolerant output decoding.

    Args:
        args: Git command arguments (without 'git' prefix)
        cwd: Working directory for command execution (None for current)
        timeout: Command timeout in seconds (None for no timeout)

    Returns:
        GitCommandResult with command output and status

    Raises:
        GitCommandError: If command execution fails critically (timeout, OSError)
    """
    cmd = ["git"] + args

    logger.debug(
        "git_command_starting",
        command=args,
        cwd=cwd,
        timeout=timeout,
    )

    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )

        # Decode output tolerantly using errors='replace'
        stdout = result.stdout.decode("utf-8", errors="replace")
        stderr = result.stderr.decode("utf-8", errors="replace")

        success = result.returncode == 0

        if success:
            logger.debug(
                "git_command_succeeded",
                command=args,
                returncode=result.returncode,
            )
            return GitCommandResult(
                success=True,
                stdout=stdout,
                stderr=stderr,
                returncode=result.returncode,
                error_code=None,
                retry_hint=None,
            )
        else:
            # Classify error and provide retry hint
            error_code, retry_hint = _classify_git_error(result.returncode, stderr)

            logger.warning(
                "git_command_failed",
                command=args,
                returncode=result.returncode,
                error_code=error_code,
                retry_hint=retry_hint,
                stderr_preview=stderr[:200],  # Limit log size
            )

            return GitCommandResult(
                success=False,
                stdout=stdout,
                stderr=stderr,
                returncode=result.returncode,
                error_code=error_code,
                retry_hint=retry_hint,
            )

    except subprocess.TimeoutExpired as e:
        logger.error(
            "git_command_timeout",
            command=args,
            timeout=timeout,
            error_message=str(e),
        )
        raise GitCommandError(f"Git command timed out after {timeout}s: {args}") from e

    except OSError as e:
        logger.error(
            "git_command_os_error",
            command=args,
            error_type=type(e).__name__,
            error_message=str(e),
        )
        raise GitCommandError(f"Git command failed with OS error: {e}") from e
