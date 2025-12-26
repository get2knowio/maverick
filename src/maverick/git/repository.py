"""GitPython-based repository operations for Maverick.

This module provides a unified interface for git operations using GitPython,
replacing the subprocess-based implementations in runners/git.py and
utils/git_operations.py.

Key features:
- Uses GitPython's Repo class for all operations
- Provides both sync and async APIs (async via asyncio.to_thread)
- Integrates Tenacity for retry logic on network operations
- Maintains backward compatibility with existing interfaces

Example:
    ```python
    from maverick.git import GitRepository, AsyncGitRepository

    # Sync usage
    repo = GitRepository("/path/to/repo")
    status = repo.status()
    repo.add_all()
    repo.commit("feat: add feature")
    repo.push()

    # Async usage
    async_repo = AsyncGitRepository("/path/to/repo")
    status = await async_repo.status()
    await async_repo.commit("feat: add feature", add_all=True)
    await async_repo.push()
    ```
"""

from __future__ import annotations

import asyncio
import re
import warnings
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from git import GitCommandError, InvalidGitRepositoryError, Repo
from git.exc import GitCommandNotFound
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from maverick.exceptions import (
    BranchExistsError,
    CheckoutConflictError,
    GitError,
    GitNotFoundError,
    MergeConflictError,
    NoStashError,
    NotARepositoryError,
    NothingToCommitError,
    PushRejectedError,
)
from maverick.logging import get_logger

logger = get_logger(__name__)

__all__ = [
    "AsyncGitRepository",
    "CommitInfo",
    "DiffStats",
    "GitRepository",
    "GitStatus",
]

# =============================================================================
# Constants
# =============================================================================

#: Branch name validation pattern
_INVALID_BRANCH_CHARS = re.compile(r"[~^: ?*\[\]\\]")

#: Default timeout for network operations in seconds
DEFAULT_NETWORK_TIMEOUT: float = 60.0

#: Maximum retries for network operations
MAX_NETWORK_RETRIES: int = 3

#: Branch timestamp format for fallback naming
BRANCH_TIMESTAMP_FORMAT = "%Y%m%d%H%M%S"

#: Patterns indicating recoverable errors
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


# =============================================================================
# Value Objects (Return Types)
# =============================================================================


@dataclass(frozen=True, slots=True)
class GitStatus:
    """Repository status snapshot.

    Attributes:
        staged: Files staged for commit.
        unstaged: Modified but unstaged files.
        untracked: Untracked files.
        branch: Current branch name.
        ahead: Commits ahead of upstream.
        behind: Commits behind upstream.
    """

    staged: tuple[str, ...]
    unstaged: tuple[str, ...]
    untracked: tuple[str, ...]
    branch: str
    ahead: int
    behind: int


@dataclass(frozen=True, slots=True)
class CommitInfo:
    """Single commit metadata.

    Attributes:
        sha: Full 40-character SHA.
        short_sha: Abbreviated SHA (7 chars).
        message: First line of commit message.
        author: Author name.
        date: ISO 8601 date string.
    """

    sha: str
    short_sha: str
    message: str
    author: str
    date: str


@dataclass(frozen=True, slots=True)
class DiffStats:
    """Diff statistics between refs.

    Attributes:
        files_changed: Number of files with changes.
        insertions: Total lines added.
        deletions: Total lines removed.
        file_list: Paths of changed files.
        per_file: Dict mapping file paths to (added, removed) tuples.
    """

    files_changed: int
    insertions: int
    deletions: int
    file_list: tuple[str, ...]
    per_file: Mapping[str, tuple[int, int]] = field(default_factory=dict)


# =============================================================================
# Helper Functions
# =============================================================================


def _validate_branch_name(name: str) -> None:
    """Validate branch name according to git ref rules.

    Args:
        name: Branch name to validate.

    Raises:
        ValueError: If branch name is invalid.
    """
    if not name or name.isspace():
        raise ValueError("Branch name cannot be empty")
    if name.startswith("-") or name.endswith("."):
        raise ValueError(f"Invalid branch name: {name}")
    if _INVALID_BRANCH_CHARS.search(name):
        raise ValueError(f"Branch name contains invalid characters: {name}")
    if ".." in name or name.endswith(".lock"):
        raise ValueError(f"Invalid branch name: {name}")


def is_recoverable_error(error_message: str) -> bool:
    """Check if a git error is potentially recoverable.

    Args:
        error_message: Error message from git command.

    Returns:
        True if the error might be recoverable with retry or cleanup.
    """
    error_lower = error_message.lower()
    return any(pattern in error_lower for pattern in RECOVERABLE_ERROR_PATTERNS)


def _convert_git_error(exc: GitCommandError, operation: str) -> GitError:
    """Convert GitPython exception to Maverick exception.

    Args:
        exc: GitPython exception.
        operation: Name of the git operation that failed.

    Returns:
        Appropriate Maverick exception.
    """
    stderr = str(exc.stderr or exc.stdout or str(exc))
    stderr_lower = stderr.lower()

    # Branch already exists
    if "already exists" in stderr_lower and operation == "create_branch":
        # Extract branch name from error message
        return BranchExistsError(str(exc), branch_name="")

    # Nothing to commit
    if "nothing to commit" in stderr_lower:
        return NothingToCommitError()

    # Checkout conflict
    checkout_conflict = (
        "would be overwritten" in stderr_lower
        or "overwritten by checkout" in stderr_lower
    )
    if checkout_conflict:
        return CheckoutConflictError()

    # Push rejected
    if "rejected" in stderr_lower or "failed to push" in stderr_lower:
        return PushRejectedError(str(exc), reason=stderr)

    # Merge conflict
    if "conflict" in stderr_lower:
        return MergeConflictError(str(exc))

    # No stash
    if "no stash" in stderr_lower:
        return NoStashError()

    # Generic git error
    return GitError(
        str(exc),
        operation=operation,
        recoverable=is_recoverable_error(stderr),
    )


# =============================================================================
# Network retry decorator
# =============================================================================


def _is_network_error(exc: BaseException) -> bool:
    """Check if exception is a network-related error that should be retried."""
    if not isinstance(exc, GitCommandError):
        return False
    stderr = str(exc.stderr or "").lower()
    network_patterns = [
        "could not resolve host",
        "connection refused",
        "connection timed out",
        "network unreachable",
        "temporary failure",
        "unable to access",
        "ssl",
        "tls",
    ]
    return any(pattern in stderr for pattern in network_patterns)


# Retry decorator for network operations
network_retry = retry(
    retry=retry_if_exception_type(GitCommandError),
    stop=stop_after_attempt(MAX_NETWORK_RETRIES),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)


# =============================================================================
# Main Class: GitRepository
# =============================================================================


class GitRepository:
    """GitPython-based repository operations.

    Thread-safe: only stores immutable configuration and Repo instance.

    Example:
        ```python
        repo = GitRepository("/path/to/repo")
        branch = repo.current_branch()
        repo.create_branch("feature-x", checkout=True)
        repo.commit("Add feature", add_all=True)
        repo.push(set_upstream=True)
        ```
    """

    def __init__(self, path: Path | str | None = None) -> None:
        """Initialize GitRepository.

        Args:
            path: Path to the git repository. Defaults to current directory.

        Raises:
            GitNotFoundError: If git is not installed.
            NotARepositoryError: If path is not a git repository.
        """
        resolved_path = Path.cwd() if path is None else Path(path)

        self._path = resolved_path

        try:
            self._repo = Repo(resolved_path)
        except GitCommandNotFound as e:
            raise GitNotFoundError("Git CLI not found. Please install git.") from e
        except InvalidGitRepositoryError as e:
            raise NotARepositoryError(
                f"Not a git repository: {path}",
                path=path,
            ) from e

    @property
    def path(self) -> Path:
        """Path to the repository root."""
        return self._path

    @property
    def repo(self) -> Repo:
        """Underlying GitPython Repo instance."""
        return self._repo

    # -------------------------------------------------------------------------
    # Repository State
    # -------------------------------------------------------------------------

    def current_branch(self) -> str:
        """Get current branch name.

        Returns:
            Branch name, or commit SHA if in detached HEAD state.
        """
        if self._repo.head.is_detached:
            return self._repo.head.commit.hexsha
        return self._repo.active_branch.name

    def status(self) -> GitStatus:
        """Get repository status.

        Returns:
            GitStatus with staged, unstaged, untracked files and branch info.
        """
        # Get current branch
        branch = self.current_branch()

        # Get file status
        staged: list[str] = []
        unstaged: list[str] = []
        untracked: list[str] = list(self._repo.untracked_files)

        # Get diff for staged changes
        if self._repo.head.is_valid():
            staged_diff = self._repo.index.diff(self._repo.head.commit)
            staged = [
                d.a_path or d.b_path or "" for d in staged_diff if d.a_path or d.b_path
            ]

            # Get diff for unstaged changes
            unstaged_diff = self._repo.index.diff(None)
            unstaged = [
                d.a_path or d.b_path or ""
                for d in unstaged_diff
                if d.a_path or d.b_path
            ]
        else:
            # Initial commit case - all index entries are staged
            staged = [str(entry.path) for entry in self._repo.index.entries.values()]

        # Get ahead/behind counts
        ahead = 0
        behind = 0
        try:
            tracking = self._repo.active_branch.tracking_branch()
            if tracking:
                ahead = len(list(self._repo.iter_commits(f"{tracking}..HEAD")))
                behind = len(list(self._repo.iter_commits(f"HEAD..{tracking}")))
        except (TypeError, ValueError):
            # No tracking branch or detached HEAD
            pass

        return GitStatus(
            staged=tuple(staged),
            unstaged=tuple(unstaged),
            untracked=tuple(untracked),
            branch=branch,
            ahead=ahead,
            behind=behind,
        )

    def log(self, n: int = 10) -> list[CommitInfo]:
        """Get recent commit history.

        Args:
            n: Number of commits to return (default 10).

        Returns:
            List of CommitInfo for the n most recent commits.
        """
        commits: list[CommitInfo] = []

        try:
            for commit in self._repo.iter_commits(max_count=n):
                # Handle bytes vs str message
                msg = commit.message
                if isinstance(msg, bytes):
                    msg = msg.decode("utf-8", errors="replace")
                first_line = msg.split("\n")[0]

                # Handle author name
                author_name = commit.author.name
                if author_name is None:
                    author_name = "Unknown"

                commits.append(
                    CommitInfo(
                        sha=commit.hexsha,
                        short_sha=commit.hexsha[:7],
                        message=first_line,
                        author=author_name,
                        date=commit.authored_datetime.isoformat(),
                    )
                )
        except ValueError:
            # Empty repository
            pass

        return commits

    def is_dirty(self) -> bool:
        """Check if repository has uncommitted changes.

        Returns:
            True if there are uncommitted changes (staged or unstaged).
        """
        return self._repo.is_dirty(untracked_files=True)

    # -------------------------------------------------------------------------
    # Branch Management
    # -------------------------------------------------------------------------

    def create_branch(
        self,
        name: str,
        checkout: bool = True,
        from_ref: str = "HEAD",
    ) -> None:
        """Create a new branch.

        Args:
            name: Branch name to create.
            checkout: If True, switch to the new branch.
            from_ref: Starting point for the branch.

        Raises:
            BranchExistsError: If branch already exists.
            ValueError: If branch name is invalid.
        """
        _validate_branch_name(name)

        # Check if branch exists
        if name in [b.name for b in self._repo.branches]:
            raise BranchExistsError(
                f"Branch '{name}' already exists",
                branch_name=name,
            )

        try:
            # Create the branch
            start_commit = self._repo.commit(from_ref)
            new_branch = self._repo.create_head(name, start_commit)

            if checkout:
                new_branch.checkout()

            logger.info("Created branch: %s", name)
        except GitCommandError as e:
            raise _convert_git_error(e, "create_branch") from e

    def create_branch_with_fallback(
        self,
        name: str,
        from_ref: str = "HEAD",
    ) -> str:
        """Create branch with timestamp suffix fallback on conflict.

        Args:
            name: Preferred branch name.
            from_ref: Starting point for the branch.

        Returns:
            Actual branch name created.
        """
        try:
            self.create_branch(name, checkout=True, from_ref=from_ref)
            return name
        except BranchExistsError:
            timestamp = datetime.now().strftime(BRANCH_TIMESTAMP_FORMAT)
            fallback_name = f"{name}-{timestamp}"
            self.create_branch(fallback_name, checkout=True, from_ref=from_ref)
            return fallback_name

    def checkout(self, branch: str) -> None:
        """Switch to an existing branch.

        Args:
            branch: Branch name to checkout.

        Raises:
            CheckoutConflictError: If uncommitted changes would be overwritten.
            GitError: If branch doesn't exist or checkout fails.
            ValueError: If branch name is invalid.
        """
        _validate_branch_name(branch)

        try:
            self._repo.git.checkout(branch)
            logger.info("Checked out branch: %s", branch)
        except GitCommandError as e:
            raise _convert_git_error(e, "checkout") from e

    def get_head_sha(self, short: bool = False) -> str:
        """Get current HEAD commit SHA.

        Args:
            short: If True, return short (7-char) SHA.

        Returns:
            Full or short commit SHA.
        """
        sha = self._repo.head.commit.hexsha
        return sha[:7] if short else sha

    # -------------------------------------------------------------------------
    # Staging and Committing
    # -------------------------------------------------------------------------

    def add(self, paths: list[str] | None = None) -> None:
        """Stage files for commit.

        Args:
            paths: Specific paths to stage. If None, stages all changes.
        """
        if paths:
            self._repo.index.add(paths)
        else:
            self._repo.git.add("-A")

    def add_all(self) -> None:
        """Stage all changes for commit."""
        self._repo.git.add("-A")

    def commit(
        self,
        message: str,
        add_all: bool = False,
        allow_empty: bool = False,
    ) -> str:
        """Create a commit.

        Args:
            message: Commit message.
            add_all: If True, stage all changes before committing.
            allow_empty: If True, allow empty commits.

        Returns:
            The commit SHA.

        Raises:
            NothingToCommitError: If nothing to commit.
        """
        if add_all:
            self.add_all()

        # Check if there's anything to commit
        if not allow_empty and not self._repo.is_dirty():
            raise NothingToCommitError("Nothing to commit")

        try:
            if allow_empty:
                self._repo.git.commit("-m", message, "--allow-empty")
            else:
                self._repo.index.commit(message)

            sha = self._repo.head.commit.hexsha
            logger.info("Commit created: %s", sha[:7])
            return sha
        except GitCommandError as e:
            raise _convert_git_error(e, "commit") from e

    # -------------------------------------------------------------------------
    # Remote Operations (with retry)
    # -------------------------------------------------------------------------

    @network_retry
    def push(
        self,
        remote: str = "origin",
        branch: str | None = None,
        force: bool = False,
        set_upstream: bool = False,
    ) -> None:
        """Push commits to remote.

        Args:
            remote: Remote name (default: origin).
            branch: Branch to push (default: current branch).
            force: Force push (use with caution).
            set_upstream: Set upstream tracking branch.

        Raises:
            PushRejectedError: If remote rejects the push.
        """
        try:
            branch_name = branch or self.current_branch()

            # Build push arguments
            args: list[str] = []
            if set_upstream:
                args.append("-u")
            if force:
                args.append("--force")
            args.append(remote)
            args.append(branch_name)

            # Use git.push directly for more control
            self._repo.git.push(*args)

            logger.info("Push completed to %s/%s", remote, branch_name)
        except GitCommandError as e:
            raise _convert_git_error(e, "push") from e

    @network_retry
    def pull(
        self,
        remote: str = "origin",
        branch: str | None = None,
    ) -> None:
        """Pull changes from remote.

        Args:
            remote: Remote name (default: origin).
            branch: Branch to pull (default: current branch).

        Raises:
            MergeConflictError: If pull results in conflicts.
        """
        try:
            branch_name = branch or self.current_branch()
            # Use git.pull directly for consistency
            self._repo.git.pull(remote, branch_name)
            logger.info("Pull completed from %s/%s", remote, branch_name)
        except GitCommandError as e:
            raise _convert_git_error(e, "pull") from e

    @network_retry
    def fetch(self, remote: str = "origin") -> None:
        """Fetch updates from remote.

        Args:
            remote: Remote name (default: origin).
        """
        try:
            remote_obj = self._repo.remote(remote)
            remote_obj.fetch()
            logger.info("Fetch completed from %s", remote)
        except GitCommandError as e:
            raise _convert_git_error(e, "fetch") from e

    # -------------------------------------------------------------------------
    # Diff Operations
    # -------------------------------------------------------------------------

    def diff(
        self,
        base: str = "HEAD",
        head: str | None = None,
        staged: bool = False,
    ) -> str:
        """Get diff output.

        Args:
            base: Base ref to diff from (default: HEAD).
            head: Head ref to diff to (default: working tree).
            staged: If True, show staged changes only.

        Returns:
            Diff output as string.
        """
        result: str
        if staged:
            result = str(self._repo.git.diff("--cached"))
        elif head:
            result = str(self._repo.git.diff(base, head))
        else:
            result = str(self._repo.git.diff(base))
        return result

    def diff_stats(self, base: str = "HEAD") -> DiffStats:
        """Get diff statistics.

        Args:
            base: Base ref to diff from (default: HEAD).

        Returns:
            DiffStats with file counts and per-file statistics.
        """
        # Get numstat output
        numstat_output = self._repo.git.diff("--numstat", base)

        files: list[str] = []
        per_file: dict[str, tuple[int, int]] = {}
        insertions = 0
        deletions = 0

        for line in numstat_output.split("\n"):
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) >= 3:
                ins = int(parts[0]) if parts[0] != "-" else 0
                dels = int(parts[1]) if parts[1] != "-" else 0
                filename = parts[2]

                files.append(filename)
                per_file[filename] = (ins, dels)
                insertions += ins
                deletions += dels

        return DiffStats(
            files_changed=len(files),
            insertions=insertions,
            deletions=deletions,
            file_list=tuple(files),
            per_file=per_file,
        )

    def get_changed_files(self, ref: str = "HEAD") -> list[str]:
        """Get list of changed file paths.

        Args:
            ref: Git reference to diff against.

        Returns:
            List of changed file paths.
        """
        output = self._repo.git.diff("--name-only", ref)
        if not output:
            return []
        return [line.strip() for line in output.split("\n") if line.strip()]

    # -------------------------------------------------------------------------
    # Stash Operations
    # -------------------------------------------------------------------------

    def stash(self, message: str | None = None) -> bool:
        """Stash uncommitted changes.

        Args:
            message: Optional stash message.

        Returns:
            True if changes were stashed, False if nothing to stash.
        """
        if not self.is_dirty():
            return False

        if message:
            self._repo.git.stash("push", "-m", message)
        else:
            self._repo.git.stash("push")

        logger.debug("Stashed changes")
        return True

    def stash_pop(self, stash_ref: str | None = None) -> None:
        """Restore stashed changes.

        Args:
            stash_ref: Specific stash reference (e.g., "stash@{0}").

        Raises:
            NoStashError: If no stash exists.
        """
        try:
            if stash_ref:
                self._repo.git.stash("pop", stash_ref)
            else:
                self._repo.git.stash("pop")
            logger.debug("Popped stash")
        except GitCommandError as e:
            if "no stash" in str(e).lower():
                raise NoStashError() from e
            raise _convert_git_error(e, "stash_pop") from e

    def stash_list(self) -> list[str]:
        """List all stashes.

        Returns:
            List of stash entries.
        """
        output = self._repo.git.stash("list")
        if not output:
            return []
        return [line.strip() for line in output.split("\n") if line.strip()]

    def stash_pop_by_message(self, message: str) -> bool:
        """Restore stash by matching message.

        Args:
            message: Stash message to match.

        Returns:
            True if stash was popped, False if not found.
        """
        stashes = self.stash_list()
        for stash_line in stashes:
            if message in stash_line:
                stash_ref = stash_line.split(":")[0]
                self.stash_pop(stash_ref)
                return True
        return False

    # -------------------------------------------------------------------------
    # Repository Information
    # -------------------------------------------------------------------------

    def get_remote_url(self, remote: str = "origin") -> str | None:
        """Get URL of a remote.

        Args:
            remote: Remote name (default: origin).

        Returns:
            Remote URL or None if not found.
        """
        try:
            return self._repo.remote(remote).url
        except ValueError:
            return None

    def get_repo_root(self) -> Path:
        """Get repository root directory.

        Returns:
            Path to repository root.
        """
        return Path(self._repo.working_dir)

    # -------------------------------------------------------------------------
    # Commit Message Retrieval
    # -------------------------------------------------------------------------

    def commit_messages(self, limit: int = 10) -> list[str]:
        """Get recent commit messages (subject lines only).

        Args:
            limit: Maximum number of commits to retrieve.

        Returns:
            List of commit subject lines.
        """
        output = self._repo.git.log(f"-{limit}", "--pretty=format:%s")
        if not output:
            return []
        return [line.strip() for line in output.split("\n") if line.strip()]

    def commit_messages_since(self, ref: str) -> list[str]:
        """Get commit messages (subject lines) since a reference.

        Args:
            ref: Git reference to compare against (e.g., "main").

        Returns:
            List of commit subject lines on current branch since ref.
        """
        try:
            output = self._repo.git.log(f"{ref}..HEAD", "--pretty=format:%s")
            if not output:
                return []
            return [line.strip() for line in output.split("\n") if line.strip()]
        except GitCommandError:
            return []


# =============================================================================
# Async Wrapper
# =============================================================================


class AsyncGitRepository:
    """Async wrapper for GitRepository.

    Delegates all operations to a synchronous GitRepository running in
    a thread pool, ensuring TUI responsiveness during git commands.

    Example:
        ```python
        repo = AsyncGitRepository("/path/to/repo")
        branch = await repo.current_branch()
        await repo.commit("Add feature", add_all=True)
        await repo.push()
        ```
    """

    def __init__(self, path: Path | str | None = None) -> None:
        """Initialize AsyncGitRepository.

        Args:
            path: Path to the git repository. Defaults to current directory.

        Raises:
            GitNotFoundError: If git is not installed.
            NotARepositoryError: If path is not a git repository.
        """
        self._sync = GitRepository(path)

    @property
    def path(self) -> Path:
        """Path to the repository root."""
        return self._sync.path

    async def current_branch(self) -> str:
        """Get current branch name."""
        return await asyncio.to_thread(self._sync.current_branch)

    async def status(self) -> GitStatus:
        """Get repository status."""
        return await asyncio.to_thread(self._sync.status)

    async def log(self, n: int = 10) -> list[CommitInfo]:
        """Get recent commit history."""
        return await asyncio.to_thread(self._sync.log, n)

    async def is_dirty(self) -> bool:
        """Check if repository has uncommitted changes."""
        return await asyncio.to_thread(self._sync.is_dirty)

    async def create_branch(
        self,
        name: str,
        checkout: bool = True,
        from_ref: str = "HEAD",
    ) -> None:
        """Create a new branch."""
        return await asyncio.to_thread(
            self._sync.create_branch, name, checkout, from_ref
        )

    async def create_branch_with_fallback(
        self,
        name: str,
        from_ref: str = "HEAD",
    ) -> str:
        """Create branch with timestamp suffix fallback on conflict."""
        return await asyncio.to_thread(
            self._sync.create_branch_with_fallback, name, from_ref
        )

    async def checkout(self, branch: str) -> None:
        """Switch to an existing branch."""
        return await asyncio.to_thread(self._sync.checkout, branch)

    async def get_head_sha(self, short: bool = False) -> str:
        """Get current HEAD commit SHA."""
        return await asyncio.to_thread(self._sync.get_head_sha, short)

    async def add(self, paths: list[str] | None = None) -> None:
        """Stage files for commit."""
        return await asyncio.to_thread(self._sync.add, paths)

    async def add_all(self) -> None:
        """Stage all changes for commit."""
        return await asyncio.to_thread(self._sync.add_all)

    async def commit(
        self,
        message: str,
        add_all: bool = False,
        allow_empty: bool = False,
    ) -> str:
        """Create a commit."""
        return await asyncio.to_thread(self._sync.commit, message, add_all, allow_empty)

    async def push(
        self,
        remote: str = "origin",
        branch: str | None = None,
        force: bool = False,
        set_upstream: bool = False,
    ) -> None:
        """Push commits to remote."""
        return await asyncio.to_thread(
            self._sync.push, remote, branch, force, set_upstream
        )

    async def pull(
        self,
        remote: str = "origin",
        branch: str | None = None,
    ) -> None:
        """Pull changes from remote."""
        return await asyncio.to_thread(self._sync.pull, remote, branch)

    async def fetch(self, remote: str = "origin") -> None:
        """Fetch updates from remote."""
        return await asyncio.to_thread(self._sync.fetch, remote)

    async def diff(
        self,
        base: str = "HEAD",
        head: str | None = None,
        staged: bool = False,
    ) -> str:
        """Get diff output."""
        return await asyncio.to_thread(self._sync.diff, base, head, staged)

    async def diff_stats(self, base: str = "HEAD") -> DiffStats:
        """Get diff statistics."""
        return await asyncio.to_thread(self._sync.diff_stats, base)

    async def get_changed_files(self, ref: str = "HEAD") -> list[str]:
        """Get list of changed file paths."""
        return await asyncio.to_thread(self._sync.get_changed_files, ref)

    async def stash(self, message: str | None = None) -> bool:
        """Stash uncommitted changes."""
        return await asyncio.to_thread(self._sync.stash, message)

    async def stash_pop(self, stash_ref: str | None = None) -> None:
        """Restore stashed changes."""
        return await asyncio.to_thread(self._sync.stash_pop, stash_ref)

    async def stash_list(self) -> list[str]:
        """List all stashes."""
        return await asyncio.to_thread(self._sync.stash_list)

    async def stash_pop_by_message(self, message: str) -> bool:
        """Restore stash by matching message."""
        return await asyncio.to_thread(self._sync.stash_pop_by_message, message)

    async def get_remote_url(self, remote: str = "origin") -> str | None:
        """Get URL of a remote."""
        return await asyncio.to_thread(self._sync.get_remote_url, remote)

    async def get_repo_root(self) -> Path:
        """Get repository root directory."""
        return await asyncio.to_thread(self._sync.get_repo_root)

    async def commit_messages(self, limit: int = 10) -> list[str]:
        """Get recent commit messages (subject lines only)."""
        return await asyncio.to_thread(self._sync.commit_messages, limit)

    async def commit_messages_since(self, ref: str) -> list[str]:
        """Get commit messages (subject lines) since a reference."""
        return await asyncio.to_thread(self._sync.commit_messages_since, ref)


# =============================================================================
# Backward Compatibility Aliases
# =============================================================================


# Deprecated aliases - will be removed in future versions
def _deprecated_alias(name: str, new_module: str) -> None:
    """Issue deprecation warning for old import paths."""
    warnings.warn(
        f"{name} is deprecated. Import from {new_module} instead.",
        DeprecationWarning,
        stacklevel=3,
    )
