"""Synchronous git operations wrapper for Maverick workflows.

This module provides a type-safe, synchronous wrapper around git CLI commands.
All operations use explicit argument lists (no shell=True) for security.
Thread-safe: only stores immutable _cwd.

Example:
    ```python
    from maverick.utils.git_operations import GitOperations

    ops = GitOperations()
    print(ops.current_branch())  # "main"
    status = ops.status()
    print(status.staged)  # ("file.py",)
    ```
"""
from __future__ import annotations

import subprocess
import threading
import re
from dataclasses import dataclass
from pathlib import Path

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

# =============================================================================
# Constants & Validators
# =============================================================================

_INVALID_BRANCH_CHARS = re.compile(r'[~^: ?*\[\]\\]')


def _validate_branch_name(name: str) -> None:
    """Validate branch name according to git ref rules.

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
        hash: Full 40-character SHA.
        short_hash: Abbreviated SHA (7 chars).
        message: First line of commit message.
        author: Author name.
        date: ISO 8601 date string.
    """

    hash: str
    short_hash: str
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
    """

    files_changed: int
    insertions: int
    deletions: int
    file_list: tuple[str, ...]


# =============================================================================
# Main Class
# =============================================================================


class GitOperations:
    """Synchronous git operations wrapper.

    Thread-safe: only stores immutable _cwd.

    Example:
        ```python
        ops = GitOperations("/path/to/repo")
        branch = ops.current_branch()
        ops.create_branch("feature-x", checkout=True)
        ops.commit("Add feature", add_all=True)
        ops.push(set_upstream=True)
        ```
    """

    def __init__(self, cwd: Path | str | None = None) -> None:
        """Initialize GitOperations.

        Args:
            cwd: Working directory for git commands. Defaults to cwd.
        """
        if cwd is None:
            self._cwd = Path.cwd()
        else:
            self._cwd = Path(cwd)
        self._git_checked: bool = False
        self._check_lock = threading.Lock()

    # -------------------------------------------------------------------------
    # Private Helpers
    # -------------------------------------------------------------------------

    def _run(
        self,
        args: list[str],
        *,
        check: bool = True,
        capture_output: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        """Run a git command.

        Args:
            args: Command arguments (git is prepended).
            check: If True, raise on non-zero exit.
            capture_output: If True, capture stdout/stderr.

        Returns:
            CompletedProcess with stdout/stderr as strings.

        Raises:
            GitNotFoundError: If git is not installed.
            subprocess.CalledProcessError: If check=True and command fails.
        """
        if not self._git_checked:
            with self._check_lock:
                if not self._git_checked:  # Double-check pattern
                    self._check_git_installed()
                    self._git_checked = True

        cmd = ["git", *args]
        return subprocess.run(
            cmd,
            cwd=self._cwd,
            check=check,
            capture_output=capture_output,
            text=True,
        )

    def _check_git_installed(self) -> None:
        """Check that git CLI is installed.

        Raises:
            GitNotFoundError: If git is not installed.
        """
        try:
            subprocess.run(
                ["git", "--version"],
                capture_output=True,
                check=True,
                text=True,
            )
        except FileNotFoundError as e:
            raise GitNotFoundError(
                "Git CLI not found. Please install git.",
            ) from e

    def _check_repository(self) -> None:
        """Check that cwd is inside a git repository.

        Raises:
            NotARepositoryError: If not in a git repository.
        """
        result = self._run(["rev-parse", "--git-dir"], check=False)
        if result.returncode != 0:
            raise NotARepositoryError(
                f"Not a git repository: {self._cwd}",
                path=self._cwd,
            )

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
        self._check_repository()
        result = self._run(["rev-parse", "--abbrev-ref", "HEAD"])
        branch = result.stdout.strip()
        if branch == "HEAD":
            # Detached HEAD - return full SHA
            result = self._run(["rev-parse", "HEAD"])
            return result.stdout.strip()
        return branch

    def status(self) -> GitStatus:
        """Get repository status.

        Returns:
            GitStatus with staged, unstaged, untracked files and branch info.

        Raises:
            GitNotFoundError: If git is not installed.
            NotARepositoryError: If not in a git repository.
        """
        self._check_repository()

        # Get branch info
        branch = self.current_branch()

        # Get ahead/behind counts
        ahead = 0
        behind = 0
        result = self._run(["status", "--branch", "--porcelain=v2"], check=False)
        for line in result.stdout.splitlines():
            if line.startswith("# branch.ab"):
                # Format: # branch.ab +N -M
                parts = line.split()
                for part in parts[2:]:
                    if part.startswith("+"):
                        ahead = int(part[1:])
                    elif part.startswith("-"):
                        behind = int(part[1:])

        # Get file status
        result = self._run(["status", "--porcelain"])
        staged: list[str] = []
        unstaged: list[str] = []
        untracked: list[str] = []

        for line in result.stdout.splitlines():
            if len(line) < 3:
                continue
            index_status = line[0]
            worktree_status = line[1]
            filename = line[3:]

            # Handle renames (format: "R  old -> new")
            if " -> " in filename:
                filename = filename.split(" -> ")[1]

            if index_status == "?":
                untracked.append(filename)
            else:
                if index_status not in (" ", "?"):
                    staged.append(filename)
                if worktree_status not in (" ", "?"):
                    unstaged.append(filename)

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

        Raises:
            GitNotFoundError: If git is not installed.
            NotARepositoryError: If not in a git repository.
        """
        self._check_repository()

        # Use pipe delimiter for parsing
        # Format: full_hash|short_hash|subject|author|ISO date
        fmt = "%H|%h|%s|%an|%aI"
        result = self._run(["log", f"-{n}", f"--format={fmt}"], check=False)

        commits: list[CommitInfo] = []
        for line in result.stdout.splitlines():
            if not line.strip():
                continue
            parts = line.split("|", 4)
            if len(parts) >= 5:
                commits.append(
                    CommitInfo(
                        hash=parts[0],
                        short_hash=parts[1],
                        message=parts[2],
                        author=parts[3],
                        date=parts[4],
                    )
                )

        return commits

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
            ValueError: If branch name is invalid.
        """
        self._check_repository()
        _validate_branch_name(name)

        # Check if branch exists
        result = self._run(["branch", "--list", name])
        if result.stdout.strip():
            raise BranchExistsError(
                f"Branch '{name}' already exists",
                branch_name=name,
            )

        if checkout:
            self._run(["checkout", "-b", name])
        else:
            self._run(["branch", name])

    def checkout(self, branch: str) -> None:
        """Switch to an existing branch.

        Args:
            branch: Branch name to checkout.

        Raises:
            GitNotFoundError: If git is not installed.
            NotARepositoryError: If not in a git repository.
            CheckoutConflictError: If uncommitted changes would be overwritten.
            GitError: If branch doesn't exist or checkout fails.
            ValueError: If branch name is invalid.
        """
        self._check_repository()
        _validate_branch_name(branch)

        result = self._run(["checkout", branch], check=False)
        if result.returncode != 0:
            stderr = result.stderr.lower()
            if "overwritten by checkout" in stderr or "would be overwritten" in stderr:
                raise CheckoutConflictError(
                    "Checkout would overwrite uncommitted changes",
                )
            elif "did not match any" in stderr or "pathspec" in stderr:
                raise GitError(
                    f"Branch '{branch}' does not exist",
                    operation="checkout",
                )
            else:
                raise GitError(
                    f"Checkout failed: {result.stderr.strip()}",
                    operation="checkout",
                )

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
            NothingToCommitError: If nothing to commit.
        """
        self._check_repository()

        if add_all:
            self._run(["add", "-A"])

        result = self._run(["commit", "-m", message], check=False)
        if result.returncode != 0:
            stderr = result.stderr.lower()
            stdout = result.stdout.lower()
            if "nothing to commit" in stderr or "nothing to commit" in stdout:
                raise NothingToCommitError("Nothing to commit")
            raise GitError(
                f"Commit failed: {result.stderr.strip()}",
                operation="commit",
            )

        # Get the commit hash
        result = self._run(["rev-parse", "HEAD"])
        return result.stdout.strip()

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
        self._check_repository()

        branch = self.current_branch()
        args = ["push"]
        if set_upstream:
            args.extend(["-u", remote, branch])
        else:
            args.append(remote)

        result = self._run(args, check=False)
        if result.returncode != 0:
            stderr = result.stderr
            if "rejected" in stderr.lower() or "failed to push" in stderr.lower():
                raise PushRejectedError(
                    f"Push rejected: {stderr.strip()}",
                    reason=stderr.strip(),
                )
            if "does not appear to be a git repository" in stderr.lower():
                raise GitError(
                    f"Remote '{remote}' not found or not accessible",
                    operation="push",
                )
            raise GitError(
                f"Push failed: {stderr.strip()}",
                operation="push",
            )

    # -------------------------------------------------------------------------
    # Sync with Remote (User Story 5)
    # -------------------------------------------------------------------------

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
        self._check_repository()

        # If branch is not specified, explicitly use the current branch
        target_branch = branch if branch else self.current_branch()
        args = ["pull", remote, target_branch]

        result = self._run(args, check=False)
        if result.returncode != 0:
            stderr = result.stderr
            stdout = result.stdout

            # Check for merge conflicts
            if "CONFLICT" in stdout or "merge conflict" in stderr.lower():
                # Get conflicted files
                status_result = self._run(["status", "--porcelain"])
                conflicted = []
                for line in status_result.stdout.splitlines():
                    if line.startswith("UU ") or line.startswith("AA "):
                        conflicted.append(line[3:])
                raise MergeConflictError(
                    "Pull resulted in merge conflicts",
                    conflicted_files=tuple(conflicted),
                )

            if "couldn't find remote ref" in stderr.lower():
                raise GitError(
                    "Remote branch not found",
                    operation="pull",
                )
            if "does not appear to be a git repository" in stderr.lower():
                raise GitError(
                    f"Remote '{remote}' not found or not accessible",
                    operation="pull",
                )

            raise GitError(
                f"Pull failed: {stderr.strip()}",
                operation="pull",
            )

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
        self._check_repository()

        args = ["diff", base]
        if head:
            args.append(head)

        result = self._run(args)
        return result.stdout

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
        self._check_repository()

        result = self._run(["diff", "--numstat", base])

        files: list[str] = []
        insertions = 0
        deletions = 0

        for line in result.stdout.splitlines():
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) >= 3:
                # Format: insertions\tdeletions\tfilename
                ins = parts[0]
                dels = parts[1]
                filename = parts[2]

                # Binary files show "-" for ins/dels
                if ins != "-":
                    insertions += int(ins)
                if dels != "-":
                    deletions += int(dels)
                files.append(filename)

        return DiffStats(
            files_changed=len(files),
            insertions=insertions,
            deletions=deletions,
            file_list=tuple(files),
        )

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
        self._check_repository()

        args = ["stash", "push"]
        if message:
            args.extend(["-m", message])

        self._run(args)

    def stash_pop(self) -> None:
        """Restore most recent stash.

        Raises:
            GitNotFoundError: If git is not installed.
            NotARepositoryError: If not in a git repository.
            NoStashError: If no stash exists.
        """
        self._check_repository()

        result = self._run(["stash", "pop"], check=False)
        if result.returncode != 0:
            stderr = result.stderr.lower()
            if "no stash entries" in stderr or "no stash found" in stderr:
                raise NoStashError("No stash entries found")
            raise GitError(
                f"Stash pop failed: {result.stderr.strip()}",
                operation="stash_pop",
            )


# =============================================================================
# Module Exports
# =============================================================================

__all__ = [
    "CommitInfo",
    "DiffStats",
    "GitOperations",
    "GitStatus",
]
