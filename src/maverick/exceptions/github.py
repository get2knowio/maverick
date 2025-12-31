from __future__ import annotations

from maverick.exceptions.agent import AgentError


class GitHubError(AgentError):
    """Exception for GitHub API/CLI failures.

    Raised when GitHub operations fail, such as creating issues, PRs, or fetching data.

    Attributes:
        message: Human-readable error message.
        issue_number: Issue number (if applicable).
        retry_after: Seconds to wait for rate limit (if applicable).
    """

    def __init__(
        self,
        message: str,
        issue_number: int | None = None,
        retry_after: int | None = None,
    ) -> None:
        """Initialize the GitHubError.

        Args:
            message: Human-readable error message.
            issue_number: Issue number (if applicable).
            retry_after: Seconds to wait for rate limit (if applicable).
        """
        self.issue_number = issue_number
        self.retry_after = retry_after
        super().__init__(message)


class GitHubToolsError(AgentError):
    """Exception for GitHub MCP tools initialization failures.

    Raised when the GitHub tools MCP server cannot be created due to missing
    prerequisites (gh CLI not installed, not authenticated, not in git repo).

    Attributes:
        message: Human-readable error message.
        check_failed: The specific prerequisite check that failed.
    """

    def __init__(
        self,
        message: str,
        check_failed: str | None = None,
    ) -> None:
        """Initialize the GitHubToolsError.

        Args:
            message: Human-readable error message.
            check_failed: The specific prerequisite check that failed.
        """
        self.check_failed = check_failed
        super().__init__(message)


class GitHubCLINotFoundError(GitHubError):
    """GitHub CLI (gh) is not installed.

    Provides installation instructions in the message.
    Inherits from GitHubError to allow catching all GitHub-related errors.
    """

    def __init__(self) -> None:
        """Initialize the GitHubCLINotFoundError."""
        super().__init__(
            "GitHub CLI (gh) not installed. Install from: https://cli.github.com/"
        )


class GitHubAuthError(GitHubError):
    """GitHub CLI is not authenticated.

    Provides authentication instructions in the message.
    Inherits from GitHubError to allow catching all GitHub-related errors.

    Attributes:
        message: Custom error message (optional, default provides auth instructions).
    """

    def __init__(self, message: str | None = None) -> None:
        """Initialize the GitHubAuthError.

        Args:
            message: Custom error message. Defaults to auth instruction.
        """
        super().__init__(message or "GitHub CLI not authenticated. Run: gh auth login")
