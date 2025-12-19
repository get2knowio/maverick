"""Git runner for async git operations.

This module provides the GitRunner class for executing git CLI operations
asynchronously without AI involvement. It wraps git commands via CommandRunner
and returns structured GitResult objects.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from maverick.runners.command import CommandRunner

if TYPE_CHECKING:
    pass

__all__ = ["GitResult", "GitRunner"]

# Constants
BRANCH_TIMESTAMP_FORMAT = "%Y%m%d%H%M%S"


@dataclass(frozen=True, slots=True)
class GitResult:
    """Result of a git operation.

    Attributes:
        success: True if operation succeeded (exit code 0).
        output: Combined stdout output from git.
        error: Error message if operation failed.
        duration_ms: Operation duration in milliseconds.
    """

    success: bool
    output: str
    error: str | None
    duration_ms: int


class GitRunner:
    """Execute git operations via subprocess.

    Provides async git operations without AI involvement:
    - Branch creation and checkout
    - Committing changes
    - Pushing to remote
    - Getting diff output for commit message generation

    All operations use CommandRunner internally for timeout handling
    and proper error management.

    Attributes:
        cwd: Working directory for git operations.

    Example:
        ```python
        runner = GitRunner(cwd=Path("/project"))
        result = await runner.create_branch("feature-x")
        if result.success:
            print(f"Branch created in {result.duration_ms}ms")
        ```
    """

    def __init__(
        self,
        cwd: Path | None = None,
        command_runner: CommandRunner | None = None,
    ) -> None:
        """Initialize GitRunner.

        Args:
            cwd: Working directory for git operations.
            command_runner: Optional CommandRunner instance (for testing).
        """
        self._cwd = cwd
        self._runner = command_runner or CommandRunner(cwd=cwd)

    @property
    def cwd(self) -> Path | None:
        """Working directory for git operations."""
        return self._cwd

    async def create_branch(
        self,
        branch_name: str,
        from_ref: str = "HEAD",
    ) -> GitResult:
        """Create and checkout a new branch.

        Args:
            branch_name: Name for the new branch.
            from_ref: Starting point for the branch (default: HEAD).

        Returns:
            GitResult with success status and any output.
        """
        result = await self._runner.run(
            ["git", "checkout", "-b", branch_name, from_ref]
        )
        return GitResult(
            success=result.success,
            output=result.stdout,
            error=result.stderr if not result.success else None,
            duration_ms=result.duration_ms,
        )

    async def create_branch_with_fallback(
        self,
        branch_name: str,
        from_ref: str = "HEAD",
    ) -> GitResult:
        """Create branch with timestamp suffix fallback on conflict.

        If the branch already exists, appends a timestamp suffix and retries.

        Args:
            branch_name: Name for the new branch.
            from_ref: Starting point for the branch (default: HEAD).

        Returns:
            GitResult with success status. On conflict resolution,
            output contains the actual branch name created.
        """
        result = await self.create_branch(branch_name, from_ref)
        if not result.success and "already exists" in (result.error or ""):
            timestamp = datetime.now().strftime(BRANCH_TIMESTAMP_FORMAT)
            fallback_name = f"{branch_name}-{timestamp}"
            fallback_result = await self.create_branch(fallback_name, from_ref)
            # Include the actual branch name in output for caller to know
            output = (
                fallback_name if fallback_result.success else fallback_result.output
            )
            return GitResult(
                success=fallback_result.success,
                output=output,
                error=fallback_result.error,
                duration_ms=result.duration_ms + fallback_result.duration_ms,
            )
        return result

    async def checkout(self, ref: str) -> GitResult:
        """Checkout an existing branch or commit.

        Args:
            ref: Branch name, tag, or commit SHA to checkout.

        Returns:
            GitResult with success status.
        """
        result = await self._runner.run(["git", "checkout", ref])
        return GitResult(
            success=result.success,
            output=result.stdout,
            error=result.stderr if not result.success else None,
            duration_ms=result.duration_ms,
        )

    async def commit(
        self,
        message: str,
        allow_empty: bool = False,
    ) -> GitResult:
        """Create a commit with staged changes.

        Args:
            message: Commit message.
            allow_empty: Allow commit with no changes.

        Returns:
            GitResult with success status.
        """
        cmd = ["git", "commit", "-m", message]
        if allow_empty:
            cmd.append("--allow-empty")
        result = await self._runner.run(cmd)
        return GitResult(
            success=result.success,
            output=result.stdout,
            error=result.stderr if not result.success else None,
            duration_ms=result.duration_ms,
        )

    async def push(
        self,
        remote: str = "origin",
        branch: str | None = None,
        force: bool = False,
        set_upstream: bool = False,
    ) -> GitResult:
        """Push commits to remote.

        Args:
            remote: Remote name (default: origin).
            branch: Branch to push (default: current branch).
            force: Force push (use with caution).
            set_upstream: Set upstream tracking.

        Returns:
            GitResult with success status.
        """
        cmd = ["git", "push"]
        if set_upstream:
            cmd.append("-u")
        if force:
            cmd.append("--force")
        cmd.append(remote)
        if branch:
            cmd.append(branch)
        result = await self._runner.run(cmd)
        return GitResult(
            success=result.success,
            output=result.stdout,
            error=result.stderr if not result.success else None,
            duration_ms=result.duration_ms,
        )

    async def diff(
        self,
        base: str = "HEAD",
        staged: bool = True,
    ) -> str:
        """Get diff output for commit message generation.

        Args:
            base: Base ref for diff comparison.
            staged: If True, show staged changes only.

        Returns:
            Diff output as string.
        """
        cmd = ["git", "diff"]
        if staged:
            cmd.append("--cached")
        else:
            cmd.append(base)
        result = await self._runner.run(cmd)
        return result.stdout

    async def add(
        self,
        paths: list[str] | None = None,
        add_all: bool = False,
    ) -> GitResult:
        """Stage files for commit.

        Args:
            paths: Specific paths to stage.
            add_all: Stage all changes (-A flag).

        Returns:
            GitResult with success status.
        """
        cmd = ["git", "add"]
        if add_all:
            cmd.append("-A")
        elif paths:
            cmd.extend(paths)
        else:
            # No paths and not add_all - add current directory
            cmd.append(".")
        result = await self._runner.run(cmd)
        return GitResult(
            success=result.success,
            output=result.stdout,
            error=result.stderr if not result.success else None,
            duration_ms=result.duration_ms,
        )

    async def status(self) -> GitResult:
        """Get repository status.

        Returns:
            GitResult with status output.
        """
        result = await self._runner.run(["git", "status", "--porcelain"])
        return GitResult(
            success=result.success,
            output=result.stdout,
            error=result.stderr if not result.success else None,
            duration_ms=result.duration_ms,
        )
