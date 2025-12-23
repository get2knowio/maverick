"""Git runner for async git operations.

This module provides the GitRunner class for executing git CLI operations
asynchronously without AI involvement. It wraps git commands via CommandRunner
and returns structured GitResult objects.

This is the canonical implementation for git operations in Maverick.
Other modules (utils/git.py, tools/git.py, dsl/context_builders.py) should
use this class instead of implementing their own git subprocess calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from maverick.runners.command import CommandRunner

if TYPE_CHECKING:
    pass

__all__ = [
    "GitResult",
    "GitRunner",
    "DiffStats",
    "CommitInfo",
]

# Constants
BRANCH_TIMESTAMP_FORMAT = "%Y%m%d%H%M%S"

#: Default timeout for git operations in seconds
DEFAULT_GIT_TIMEOUT: float = 30.0

#: Maximum retries for recoverable git errors
MAX_GIT_RETRIES: int = 3

#: Patterns that indicate a recoverable git error
RECOVERABLE_ERROR_PATTERNS: tuple[str, ...] = (
    "dirty",
    "uncommitted changes",
    "not staged",
    "pre-commit hook",
    "hook failed",
    "lock file",
    "unable to create",
    ".git/index.lock",
    "cannot lock ref",
)


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


@dataclass(frozen=True, slots=True)
class DiffStats:
    """Statistics about file changes in a diff.

    Attributes:
        files_changed: Total number of files changed.
        insertions: Total lines added.
        deletions: Total lines removed.
        per_file: Dict mapping file paths to (added, removed) tuples.
    """

    files_changed: int
    insertions: int
    deletions: int
    per_file: dict[str, tuple[int, int]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CommitInfo:
    """Information about a git commit.

    Attributes:
        sha: Full commit SHA.
        short_sha: Short (7-char) commit SHA.
        message: Commit subject line.
        author: Author name.
        date: Commit date as ISO string.
    """

    sha: str
    short_sha: str
    message: str
    author: str
    date: str


class GitRunner:
    """Execute git operations via subprocess.

    Provides async git operations without AI involvement:
    - Branch creation and checkout
    - Committing changes
    - Pushing to remote
    - Getting diff output for commit message generation
    - Stash operations for handling uncommitted changes
    - Repository state queries (is_dirty, get_head_sha, etc.)

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

        # Check for uncommitted changes
        if await runner.is_dirty():
            await runner.stash("before-switch")
            await runner.checkout("main")
            await runner.stash_pop()
        ```
    """

    def __init__(
        self,
        cwd: Path | None = None,
        command_runner: CommandRunner | None = None,
        timeout: float = DEFAULT_GIT_TIMEOUT,
    ) -> None:
        """Initialize GitRunner.

        Args:
            cwd: Working directory for git operations.
            command_runner: Optional CommandRunner instance (for testing).
            timeout: Default timeout for git operations in seconds.
        """
        self._cwd = cwd
        self._timeout = timeout
        self._runner = command_runner or CommandRunner(
            cwd=cwd, timeout=timeout)

    @property
    def cwd(self) -> Path | None:
        """Working directory for git operations."""
        return self._cwd

    @property
    def timeout(self) -> float:
        """Default timeout for git operations in seconds."""
        return self._timeout

    # =========================================================================
    # Helper Methods
    # =========================================================================

    @staticmethod
    def is_recoverable_error(error_message: str) -> bool:
        """Check if a git error is potentially recoverable.

        Recoverable errors include:
        - Dirty working directory
        - Uncommitted changes
        - Pre-commit hook failures
        - Lock file issues (index.lock, ref locks)

        Args:
            error_message: Error message from git command.

        Returns:
            True if the error might be recoverable with retry or cleanup.

        Example:
            ```python
            result = await runner.commit("test")
            if not result.success:
                if GitRunner.is_recoverable_error(result.error or ""):
                    # Try recovery actions
                    pass
            ```
        """
        error_lower = error_message.lower()
        return any(pattern in error_lower for pattern in RECOVERABLE_ERROR_PATTERNS)

    def _make_result(
        self,
        success: bool,
        output: str,
        error: str | None,
        duration_ms: int,
    ) -> GitResult:
        """Create a GitResult from command output.

        Args:
            success: Whether the command succeeded.
            output: stdout from the command.
            error: stderr if failed, None if succeeded.
            duration_ms: Command duration in milliseconds.

        Returns:
            GitResult with the provided values.
        """
        return GitResult(
            success=success,
            output=output,
            error=error,
            duration_ms=duration_ms,
        )

    # =========================================================================
    # Branch Operations
    # =========================================================================

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
        return self._make_result(
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
            return self._make_result(
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
        return self._make_result(
            success=result.success,
            output=result.stdout,
            error=result.stderr if not result.success else None,
            duration_ms=result.duration_ms,
        )

    async def get_current_branch(self) -> str:
        """Get the current branch name.

        Returns:
            Branch name, or "(detached)" if in detached HEAD state.

        Example:
            ```python
            branch = await runner.get_current_branch()
            if branch == "(detached)":
                print("Not on a branch")
            ```
        """
        result = await self._runner.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"]
        )
        branch = result.stdout.strip()
        return branch if branch != "HEAD" else "(detached)"

    # =========================================================================
    # Commit Operations
    # =========================================================================

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
        return self._make_result(
            success=result.success,
            output=result.stdout,
            error=result.stderr if not result.success else None,
            duration_ms=result.duration_ms,
        )

    async def get_head_sha(self, short: bool = False) -> str:
        """Get the current HEAD commit SHA.

        Args:
            short: If True, return short (7-char) SHA.

        Returns:
            Full or short commit SHA.

        Example:
            ```python
            sha = await runner.get_head_sha()
            short_sha = await runner.get_head_sha(short=True)
            ```
        """
        cmd = ["git", "rev-parse"]
        if short:
            cmd.append("--short")
        cmd.append("HEAD")
        result = await self._runner.run(cmd)
        return result.stdout.strip()

    # =========================================================================
    # Push Operations
    # =========================================================================

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
        return self._make_result(
            success=result.success,
            output=result.stdout,
            error=result.stderr if not result.success else None,
            duration_ms=result.duration_ms,
        )

    # =========================================================================
    # Diff Operations
    # =========================================================================

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

    async def get_diff_output(
        self,
        ref: str = "HEAD",
        staged: bool = False,
    ) -> str:
        """Get full diff output as a string.

        This is an alias for diff() with different default parameters,
        designed for context builders that need the full diff text.

        Args:
            ref: Git reference to diff against.
            staged: If True, get staged changes only.

        Returns:
            Git diff output as string.

        Example:
            ```python
            # Get diff against HEAD (unstaged changes)
            diff = await runner.get_diff_output()

            # Get staged changes
            staged_diff = await runner.get_diff_output(staged=True)

            # Get diff against a branch
            diff = await runner.get_diff_output(ref="main")
            ```
        """
        cmd = ["git", "diff"]
        if staged:
            cmd.append("--staged")
        else:
            cmd.append(ref)
        result = await self._runner.run(cmd)
        return result.stdout

    async def get_diff_stats(self, ref: str = "HEAD") -> DiffStats:
        """Get diff statistics showing lines added/removed per file.

        Args:
            ref: Git reference to diff against (default: HEAD).

        Returns:
            DiffStats with file counts and per-file statistics.

        Example:
            ```python
            stats = await runner.get_diff_stats("main")
            print(f"{stats.files_changed} files, +{stats.insertions}/-{stats.deletions}")
            for file, (added, removed) in stats.per_file.items():
                print(f"  {file}: +{added}/-{removed}")
            ```
        """
        # Get per-file stats using --numstat
        numstat_result = await self._runner.run(
            ["git", "diff", "--numstat", ref]
        )

        per_file: dict[str, tuple[int, int]] = {}
        total_insertions = 0
        total_deletions = 0

        if numstat_result.success and numstat_result.stdout:
            for line in numstat_result.stdout.split("\n"):
                if not line.strip():
                    continue
                parts = line.split("\t")
                if len(parts) >= 3:
                    # Binary files show "-" for additions/deletions
                    added = int(parts[0]) if parts[0] != "-" else 0
                    removed = int(parts[1]) if parts[1] != "-" else 0
                    file_path = parts[2]
                    per_file[file_path] = (added, removed)
                    total_insertions += added
                    total_deletions += removed

        return DiffStats(
            files_changed=len(per_file),
            insertions=total_insertions,
            deletions=total_deletions,
            per_file=per_file,
        )

    async def get_changed_files(self, ref: str = "HEAD") -> list[str]:
        """Get list of changed file paths against a reference.

        Args:
            ref: Git reference to diff against.

        Returns:
            List of changed file paths.

        Example:
            ```python
            files = await runner.get_changed_files("main")
            for f in files:
                print(f"Changed: {f}")
            ```
        """
        result = await self._runner.run(["git", "diff", "--name-only", ref])
        if not result.success or not result.stdout:
            return []
        return [line.strip() for line in result.stdout.split("\n") if line.strip()]

    # =========================================================================
    # Staging Operations
    # =========================================================================

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
        return self._make_result(
            success=result.success,
            output=result.stdout,
            error=result.stderr if not result.success else None,
            duration_ms=result.duration_ms,
        )

    # =========================================================================
    # Status Operations
    # =========================================================================

    async def status(self) -> GitResult:
        """Get repository status.

        Returns:
            GitResult with status output in porcelain format.
        """
        result = await self._runner.run(["git", "status", "--porcelain"])
        return self._make_result(
            success=result.success,
            output=result.stdout,
            error=result.stderr if not result.success else None,
            duration_ms=result.duration_ms,
        )

    async def is_dirty(self) -> bool:
        """Check if the working directory has uncommitted changes.

        This includes both staged and unstaged changes.

        Returns:
            True if there are uncommitted changes.

        Example:
            ```python
            if await runner.is_dirty():
                print("There are uncommitted changes")
                await runner.stash()
            ```
        """
        result = await self._runner.run(["git", "status", "--porcelain"])
        return bool(result.stdout.strip())

    # =========================================================================
    # Stash Operations
    # =========================================================================

    async def stash(self, message: str = "maverick-auto-stash") -> GitResult:
        """Stash uncommitted changes.

        Args:
            message: Stash message for identification.

        Returns:
            GitResult with success status. If no changes to stash,
            returns success but output indicates nothing was stashed.

        Example:
            ```python
            result = await runner.stash("before-branch-switch")
            if result.success:
                await runner.checkout("other-branch")
                # ... do work ...
                await runner.stash_pop()
            ```
        """
        # Check if there are changes to stash
        if not await self.is_dirty():
            return self._make_result(
                success=True,
                output="No changes to stash",
                error=None,
                duration_ms=0,
            )

        result = await self._runner.run(
            ["git", "stash", "push", "-m", message]
        )
        return self._make_result(
            success=result.success,
            output=result.stdout,
            error=result.stderr if not result.success else None,
            duration_ms=result.duration_ms,
        )

    async def stash_pop(self, stash_ref: str | None = None) -> GitResult:
        """Restore stashed changes.

        Args:
            stash_ref: Specific stash reference (e.g., "stash@{0}").
                      If None, pops the most recent stash.

        Returns:
            GitResult with success status.

        Example:
            ```python
            # Pop most recent stash
            result = await runner.stash_pop()

            # Pop specific stash
            result = await runner.stash_pop("stash@{1}")
            ```
        """
        cmd = ["git", "stash", "pop"]
        if stash_ref:
            cmd.append(stash_ref)
        result = await self._runner.run(cmd)
        return self._make_result(
            success=result.success,
            output=result.stdout,
            error=result.stderr if not result.success else None,
            duration_ms=result.duration_ms,
        )

    async def stash_list(self) -> list[str]:
        """List all stashes.

        Returns:
            List of stash entries (e.g., ["stash@{0}: On main: message"]).

        Example:
            ```python
            stashes = await runner.stash_list()
            for stash in stashes:
                print(stash)
            ```
        """
        result = await self._runner.run(["git", "stash", "list"])
        if not result.success or not result.stdout:
            return []
        return [line.strip() for line in result.stdout.split("\n") if line.strip()]

    async def stash_pop_by_message(
        self,
        message: str = "maverick-auto-stash",
    ) -> GitResult:
        """Restore stashed changes by matching the stash message.

        Finds the first stash with a matching message and pops it.

        Args:
            message: Stash message to match.

        Returns:
            GitResult with success status. If no matching stash found,
            returns success=False with appropriate error message.

        Example:
            ```python
            await runner.stash("before-feature-x")
            # ... do other work ...
            await runner.stash_pop_by_message("before-feature-x")
            ```
        """
        stashes = await self.stash_list()

        for stash_line in stashes:
            if message in stash_line:
                # Extract stash ref (e.g., "stash@{0}")
                stash_ref = stash_line.split(":")[0]
                return await self.stash_pop(stash_ref)

        return self._make_result(
            success=False,
            output="",
            error=f"No stash found with message: {message}",
            duration_ms=0,
        )

    # =========================================================================
    # Commit History Operations
    # =========================================================================

    async def get_commit_history(
        self,
        limit: int = 10,
        format_str: str = "%H|%h|%s|%an|%aI",
    ) -> list[CommitInfo]:
        """Get recent commit history.

        Args:
            limit: Maximum number of commits to retrieve.
            format_str: Git log format string (default provides full info).

        Returns:
            List of CommitInfo objects for recent commits.

        Example:
            ```python
            commits = await runner.get_commit_history(limit=5)
            for commit in commits:
                print(f"{commit.short_sha}: {commit.message}")
            ```
        """
        result = await self._runner.run(
            ["git", "log", f"-{limit}", f"--pretty=format:{format_str}"]
        )
        if not result.success or not result.stdout:
            return []

        commits = []
        for line in result.stdout.split("\n"):
            if not line.strip():
                continue
            parts = line.split("|", 4)
            if len(parts) >= 5:
                commits.append(
                    CommitInfo(
                        sha=parts[0],
                        short_sha=parts[1],
                        message=parts[2],
                        author=parts[3],
                        date=parts[4],
                    )
                )
        return commits

    async def get_commit_messages(self, limit: int = 10) -> list[str]:
        """Get recent commit messages (subject lines only).

        Args:
            limit: Maximum number of commits to retrieve.

        Returns:
            List of commit subject lines.

        Example:
            ```python
            messages = await runner.get_commit_messages(limit=5)
            for msg in messages:
                print(f"- {msg}")
            ```
        """
        result = await self._runner.run(
            ["git", "log", f"-{limit}", "--pretty=format:%s"]
        )
        if not result.success or not result.stdout:
            return []
        return [line.strip() for line in result.stdout.split("\n") if line.strip()]

    async def get_commits_since(
        self,
        ref: str,
        format_str: str = "%H|%h|%s|%an|%aI",
    ) -> list[CommitInfo]:
        """Get all commits since a reference (e.g., since branching from main).

        Args:
            ref: Git reference to compare against (e.g., "main", "origin/main").
            format_str: Git log format string.

        Returns:
            List of CommitInfo objects for commits since the reference.

        Example:
            ```python
            # Get all commits on current branch since main
            commits = await runner.get_commits_since("main")
            print(f"{len(commits)} commits since main")
            ```
        """
        result = await self._runner.run(
            ["git", "log", f"{ref}..HEAD", f"--pretty=format:{format_str}"]
        )
        if not result.success or not result.stdout:
            return []

        commits = []
        for line in result.stdout.split("\n"):
            if not line.strip():
                continue
            parts = line.split("|", 4)
            if len(parts) >= 5:
                commits.append(
                    CommitInfo(
                        sha=parts[0],
                        short_sha=parts[1],
                        message=parts[2],
                        author=parts[3],
                        date=parts[4],
                    )
                )
        return commits

    async def get_commit_messages_since(self, ref: str) -> list[str]:
        """Get commit messages (subject lines) since a reference.

        Args:
            ref: Git reference to compare against.

        Returns:
            List of commit subject lines.

        Example:
            ```python
            messages = await runner.get_commit_messages_since("main")
            ```
        """
        result = await self._runner.run(
            ["git", "log", f"{ref}..HEAD", "--pretty=format:%s"]
        )
        if not result.success or not result.stdout:
            return []
        return [line.strip() for line in result.stdout.split("\n") if line.strip()]

    # =========================================================================
    # Repository Information
    # =========================================================================

    async def get_remote_url(self, remote: str = "origin") -> str | None:
        """Get the URL of a remote.

        Args:
            remote: Remote name (default: origin).

        Returns:
            Remote URL or None if not found.
        """
        result = await self._runner.run(["git", "remote", "get-url", remote])
        if result.success:
            return result.stdout.strip()
        return None

    async def is_inside_repo(self) -> bool:
        """Check if the current directory is inside a git repository.

        Returns:
            True if inside a git repository.
        """
        result = await self._runner.run(["git", "rev-parse", "--git-dir"])
        return result.success

    async def get_repo_root(self) -> Path | None:
        """Get the root directory of the git repository.

        Returns:
            Path to repository root, or None if not in a repo.
        """
        result = await self._runner.run(
            ["git", "rev-parse", "--show-toplevel"]
        )
        if result.success and result.stdout.strip():
            return Path(result.stdout.strip())
        return None
