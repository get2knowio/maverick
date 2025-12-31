"""Type stubs for git_operations module.

This file defines the public API contract for the GitOperations class.
Implementation must match these signatures exactly.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# =============================================================================
# Value Objects (Return Types)
# =============================================================================

@dataclass(frozen=True, slots=True)
class GitStatus:
    """Repository status snapshot."""
    staged: tuple[str, ...]
    unstaged: tuple[str, ...]
    untracked: tuple[str, ...]
    branch: str
    ahead: int
    behind: int

@dataclass(frozen=True, slots=True)
class CommitInfo:
    """Single commit metadata."""
    hash: str
    short_hash: str
    message: str
    author: str
    date: str

@dataclass(frozen=True, slots=True)
class DiffStats:
    """Diff statistics between refs."""
    files_changed: int
    insertions: int
    deletions: int
    file_list: tuple[str, ...]

# =============================================================================
# Exception Types
# =============================================================================

class GitNotFoundError(Exception):
    """Git CLI not installed or not in PATH."""
    message: str
    ...

class NotARepositoryError(Exception):
    """Not inside a git repository."""
    message: str
    path: Path
    ...

class BranchExistsError(Exception):
    """Branch already exists."""
    message: str
    branch_name: str
    ...

class MergeConflictError(Exception):
    """Pull resulted in merge conflicts."""
    message: str
    conflicted_files: tuple[str, ...]
    ...

class PushRejectedError(Exception):
    """Remote rejected push."""
    message: str
    reason: str
    ...

# =============================================================================
# Main Class
# =============================================================================

class GitOperations:
    """Synchronous git operations wrapper.

    Thread-safe: only stores immutable _cwd.
    """

    def __init__(self, cwd: Path | str | None = None) -> None:
        """Initialize GitOperations.

        Args:
            cwd: Working directory for git commands. Defaults to cwd.
        """
        ...

    # -------------------------------------------------------------------------
    # Repository State (User Story 1)
    # -------------------------------------------------------------------------

    def current_branch(self) -> str:
        """Get current branch name.

        Returns:
            Branch name, or commit SHA if in detached HEAD state.

        Raises:
            GitNotFoundError: If git is not installed.
            NotARepositoryError: If not in a git repository.
        """
        ...

    def status(self) -> GitStatus:
        """Get repository status.

        Returns:
            GitStatus with staged, unstaged, untracked files and branch info.

        Raises:
            GitNotFoundError: If git is not installed.
            NotARepositoryError: If not in a git repository.
        """
        ...

    def log(self, n: int = 10) -> list[CommitInfo]:
        """Get recent commit history.

        Args:
            n: Number of commits to return (default 10).

        Returns:
            List of CommitInfo for the n most recent commits.

        Raises:
            GitNotFoundError: If git is not installed.
            NotARepositoryError: If not in a git repository.
        """
        ...

    # -------------------------------------------------------------------------
    # Branch Management (User Story 2)
    # -------------------------------------------------------------------------

    def create_branch(self, name: str, checkout: bool = True) -> None:
        """Create a new branch.

        Args:
            name: Branch name to create.
            checkout: If True, switch to the new branch.

        Raises:
            GitNotFoundError: If git is not installed.
            NotARepositoryError: If not in a git repository.
            BranchExistsError: If branch already exists.
        """
        ...

    def checkout(self, branch: str) -> None:
        """Switch to an existing branch.

        Args:
            branch: Branch name to checkout.

        Raises:
            GitNotFoundError: If git is not installed.
            NotARepositoryError: If not in a git repository.
            GitError: If branch doesn't exist or checkout fails.
        """
        ...

    # -------------------------------------------------------------------------
    # Committing and Pushing (User Story 3)
    # -------------------------------------------------------------------------

    def commit(self, message: str, add_all: bool = False) -> str:
        """Create a commit.

        Args:
            message: Commit message.
            add_all: If True, stage all changes before committing.

        Returns:
            The commit hash.

        Raises:
            GitNotFoundError: If git is not installed.
            NotARepositoryError: If not in a git repository.
            GitError: If nothing to commit or commit fails.
        """
        ...

    def push(
        self,
        remote: str = "origin",
        set_upstream: bool = False,
    ) -> None:
        """Push current branch to remote.

        Args:
            remote: Remote name (default "origin").
            set_upstream: If True, set upstream tracking branch.

        Raises:
            GitNotFoundError: If git is not installed.
            NotARepositoryError: If not in a git repository.
            PushRejectedError: If remote rejects the push.
        """
        ...

    def pull(
        self,
        remote: str = "origin",
        branch: str | None = None,
    ) -> None:
        """Pull changes from remote.

        Args:
            remote: Remote name (default "origin").
            branch: Branch to pull (default: current branch).

        Raises:
            GitNotFoundError: If git is not installed.
            NotARepositoryError: If not in a git repository.
            MergeConflictError: If pull results in conflicts.
            GitError: If remote/branch doesn't exist.
        """
        ...

    # -------------------------------------------------------------------------
    # Diff Analysis (User Story 4)
    # -------------------------------------------------------------------------

    def diff(self, base: str = "HEAD", head: str | None = None) -> str:
        """Get full diff between refs.

        Args:
            base: Base ref to diff from (default HEAD).
            head: Head ref to diff to (default: working tree).

        Returns:
            Full diff output as string.

        Raises:
            GitNotFoundError: If git is not installed.
            NotARepositoryError: If not in a git repository.
        """
        ...

    def diff_stats(self, base: str = "HEAD") -> DiffStats:
        """Get diff statistics.

        Args:
            base: Base ref to diff from (default HEAD).

        Returns:
            DiffStats with files changed, insertions, deletions.

        Raises:
            GitNotFoundError: If git is not installed.
            NotARepositoryError: If not in a git repository.
        """
        ...

    # -------------------------------------------------------------------------
    # Sync with Remote (User Story 5) - covered by pull() above
    # -------------------------------------------------------------------------

    # -------------------------------------------------------------------------
    # Stashing (User Story 6)
    # -------------------------------------------------------------------------

    def stash(self, message: str | None = None) -> None:
        """Stash uncommitted changes.

        Args:
            message: Optional stash message.

        Raises:
            GitNotFoundError: If git is not installed.
            NotARepositoryError: If not in a git repository.
        """
        ...

    def stash_pop(self) -> None:
        """Restore most recent stash.

        Raises:
            GitNotFoundError: If git is not installed.
            NotARepositoryError: If not in a git repository.
            GitError: If no stash exists.
        """
        ...
