from __future__ import annotations

from pathlib import Path

from maverick.exceptions.agent import AgentError


class GitError(AgentError):
    """Exception for git operation failures.

    Raised when a git command fails, such as commit, stash, or branch operations.

    Attributes:
        message: Human-readable error message.
        operation: Git operation that failed (e.g., "commit", "stash").
        recoverable: True if error might be recoverable.
    """

    def __init__(
        self,
        message: str,
        operation: str | None = None,
        recoverable: bool = False,
    ) -> None:
        """Initialize the GitError.

        Args:
            message: Human-readable error message.
            operation: Git operation that failed.
            recoverable: True if error might be recoverable.
        """
        self.operation = operation
        self.recoverable = recoverable
        super().__init__(message)


class GitNotFoundError(GitError):
    """Exception raised when git CLI is not installed or not in PATH.

    Attributes:
        message: Human-readable error message.
    """

    def __init__(self, message: str = "Git CLI not found") -> None:
        """Initialize the GitNotFoundError.

        Args:
            message: Human-readable error message.
        """
        super().__init__(message, operation="git_check", recoverable=False)


class NotARepositoryError(GitError):
    """Exception raised when operating outside a git repository.

    Attributes:
        message: Human-readable error message.
        path: Directory that is not a repo.
    """

    def __init__(
        self,
        message: str,
        path: Path | str | None = None,
    ) -> None:
        """Initialize the NotARepositoryError.

        Args:
            message: Human-readable error message.
            path: Directory that is not a repo.
        """
        self.path = path
        super().__init__(message, operation="repo_check", recoverable=False)


class BranchExistsError(GitError):
    """Exception raised when creating a branch that already exists.

    Attributes:
        message: Human-readable error message.
        branch_name: Name of existing branch.
    """

    def __init__(self, message: str, branch_name: str) -> None:
        """Initialize the BranchExistsError.

        Args:
            message: Human-readable error message.
            branch_name: Name of existing branch.
        """
        self.branch_name = branch_name
        super().__init__(message, operation="create_branch", recoverable=False)


class MergeConflictError(GitError):
    """Exception raised when pull results in merge conflicts.

    Attributes:
        message: Human-readable error message.
        conflicted_files: Paths with conflicts.
    """

    def __init__(self, message: str, conflicted_files: tuple[str, ...] = ()) -> None:
        """Initialize the MergeConflictError.

        Args:
            message: Human-readable error message.
            conflicted_files: Paths with conflicts.
        """
        self.conflicted_files = conflicted_files
        super().__init__(message, operation="pull", recoverable=True)


class PushRejectedError(GitError):
    """Exception raised when remote rejects a push.

    Attributes:
        message: Human-readable error message.
        reason: Rejection reason from git.
    """

    def __init__(self, message: str, reason: str = "") -> None:
        """Initialize the PushRejectedError.

        Args:
            message: Human-readable error message.
            reason: Rejection reason from git.
        """
        self.reason = reason
        super().__init__(message, operation="push", recoverable=True)


class NothingToCommitError(GitError):
    """Exception raised when attempting to commit with no staged changes.

    Attributes:
        message: Human-readable error message.
    """

    def __init__(self, message: str = "Nothing to commit") -> None:
        """Initialize the NothingToCommitError.

        Args:
            message: Human-readable error message.
        """
        super().__init__(message, operation="commit", recoverable=False)


class NoStashError(GitError):
    """Exception raised when stash_pop is called with no stash entries.

    Attributes:
        message: Human-readable error message.
    """

    def __init__(self, message: str = "No stash entries found") -> None:
        """Initialize the NoStashError.

        Args:
            message: Human-readable error message.
        """
        super().__init__(message, operation="stash_pop", recoverable=False)


class CheckoutConflictError(GitError):
    """Exception raised when checkout would overwrite uncommitted changes.

    Attributes:
        message: Human-readable error message.
    """

    def __init__(
        self,
        message: str = "Checkout would overwrite uncommitted changes",
    ) -> None:
        """Initialize the CheckoutConflictError.

        Args:
            message: Human-readable error message.
        """
        super().__init__(message, operation="checkout", recoverable=True)


class GitToolsError(AgentError):
    """Exception for git MCP tools initialization failures.

    Raised when the git tools MCP server cannot be created due to missing
    prerequisites (git not installed, not in git repo).

    Attributes:
        message: Human-readable error message.
        check_failed: The specific prerequisite check that failed.
    """

    def __init__(
        self,
        message: str,
        check_failed: str | None = None,
    ) -> None:
        """Initialize the GitToolsError.

        Args:
            message: Human-readable error message.
            check_failed: The specific prerequisite check that failed.
        """
        self.check_failed = check_failed
        super().__init__(message)
