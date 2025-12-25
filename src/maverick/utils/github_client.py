"""GitHub client module using PyGithub with gh CLI authentication.

This module provides a PyGithub client authenticated via `gh auth token`
and async-friendly wrapper functions for common GitHub operations.
"""

from __future__ import annotations

import asyncio
import subprocess
from typing import TYPE_CHECKING

from github import Auth, Github, GithubException
from github.Issue import Issue
from github.PullRequest import PullRequest as GHPullRequest

from maverick.exceptions import GitHubAuthError, GitHubCLINotFoundError, GitHubError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from github.CheckRun import CheckRun
    from github.Repository import Repository


__all__ = [
    "get_github_token",
    "get_github_client",
    "GitHubClient",
]


def get_github_token() -> str:
    """Get GitHub authentication token from gh CLI.

    Returns:
        GitHub authentication token string.

    Raises:
        GitHubCLINotFoundError: If gh CLI is not installed.
        GitHubAuthError: If gh CLI is not authenticated.
    """
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        token = result.stdout.strip()
        if not token:
            raise GitHubAuthError()
        return token
    except FileNotFoundError as e:
        raise GitHubCLINotFoundError() from e
    except subprocess.CalledProcessError as e:
        raise GitHubAuthError() from e
    except subprocess.TimeoutExpired as e:
        raise GitHubAuthError() from e


def get_github_client() -> Github:
    """Create a PyGithub client authenticated via gh CLI.

    Returns:
        Authenticated PyGithub Github instance.

    Raises:
        GitHubCLINotFoundError: If gh CLI is not installed.
        GitHubAuthError: If gh CLI is not authenticated.
    """
    token = get_github_token()
    auth = Auth.Token(token)
    return Github(auth=auth)


class GitHubClient:
    """Async-friendly wrapper around PyGithub for common operations.

    This class provides async methods that wrap PyGithub's synchronous API,
    running blocking operations in a thread pool to avoid blocking the event loop.

    Attributes:
        github: The underlying PyGithub client instance.
    """

    def __init__(self, github: Github | None = None) -> None:
        """Initialize the GitHubClient.

        Args:
            github: Optional PyGithub client. If not provided, one will be
                created using gh CLI authentication.

        Raises:
            GitHubCLINotFoundError: If gh CLI is not installed.
            GitHubAuthError: If gh CLI is not authenticated.
        """
        self._github: Github | None = github
        self._lazy_init = github is None

    @property
    def github(self) -> Github:
        """Get the PyGithub client, initializing lazily if needed."""
        if self._github is None:
            self._github = get_github_client()
        return self._github

    def _get_repo(self, repo_name: str) -> Repository:
        """Get a repository by full name (owner/repo)."""
        return self.github.get_repo(repo_name)

    # =========================================================================
    # Issue Operations
    # =========================================================================

    async def list_issues(
        self,
        repo_name: str,
        state: str = "open",
        labels: Sequence[str] | None = None,
        limit: int = 30,
    ) -> list[Issue]:
        """List issues from a repository.

        Args:
            repo_name: Full repository name (owner/repo).
            state: Issue state filter ("open", "closed", "all").
            labels: Optional list of label names to filter by.
            limit: Maximum number of issues to return.

        Returns:
            List of Issue objects.

        Raises:
            GitHubError: On API errors.
        """

        def _list_issues() -> list[Issue]:
            try:
                repo = self._get_repo(repo_name)
                if labels:
                    issues = repo.get_issues(state=state, labels=list(labels))
                else:
                    issues = repo.get_issues(state=state)
                return list(issues[:limit])
            except GithubException as e:
                raise GitHubError(f"Failed to list issues: {e}") from e

        return await asyncio.to_thread(_list_issues)

    async def get_issue(self, repo_name: str, issue_number: int) -> Issue:
        """Get a single issue by number.

        Args:
            repo_name: Full repository name (owner/repo).
            issue_number: Issue number to fetch.

        Returns:
            Issue object.

        Raises:
            GitHubError: On API errors or if issue not found.
        """

        def _get_issue() -> Issue:
            try:
                repo = self._get_repo(repo_name)
                return repo.get_issue(issue_number)
            except GithubException as e:
                if e.status == 404:
                    raise GitHubError(
                        f"Issue #{issue_number} not found",
                        issue_number=issue_number,
                    ) from e
                raise GitHubError(
                    f"Failed to get issue #{issue_number}: {e}",
                    issue_number=issue_number,
                ) from e

        return await asyncio.to_thread(_get_issue)

    async def add_issue_comment(
        self,
        repo_name: str,
        issue_number: int,
        body: str,
    ) -> None:
        """Add a comment to an issue.

        Args:
            repo_name: Full repository name (owner/repo).
            issue_number: Issue number to comment on.
            body: Comment body text (markdown supported).

        Raises:
            GitHubError: On API errors.
        """

        def _add_comment() -> None:
            try:
                repo = self._get_repo(repo_name)
                issue = repo.get_issue(issue_number)
                issue.create_comment(body)
            except GithubException as e:
                raise GitHubError(
                    f"Failed to add comment to issue #{issue_number}: {e}",
                    issue_number=issue_number,
                ) from e

        await asyncio.to_thread(_add_comment)

    # =========================================================================
    # Pull Request Operations
    # =========================================================================

    async def create_pr(
        self,
        repo_name: str,
        title: str,
        body: str,
        head: str,
        base: str = "main",
        draft: bool = False,
    ) -> GHPullRequest:
        """Create a new pull request.

        Args:
            repo_name: Full repository name (owner/repo).
            title: PR title.
            body: PR body/description.
            head: Source branch name.
            base: Target branch name.
            draft: Whether to create as draft PR.

        Returns:
            PullRequest object.

        Raises:
            GitHubError: On API errors.
        """

        def _create_pr() -> GHPullRequest:
            try:
                repo = self._get_repo(repo_name)
                return repo.create_pull(
                    title=title,
                    body=body,
                    head=head,
                    base=base,
                    draft=draft,
                )
            except GithubException as e:
                raise GitHubError(f"Failed to create PR: {e}") from e

        return await asyncio.to_thread(_create_pr)

    async def get_pr(self, repo_name: str, pr_number: int) -> GHPullRequest:
        """Get a pull request by number.

        Args:
            repo_name: Full repository name (owner/repo).
            pr_number: Pull request number.

        Returns:
            PullRequest object.

        Raises:
            GitHubError: On API errors or if PR not found.
        """

        def _get_pr() -> GHPullRequest:
            try:
                repo = self._get_repo(repo_name)
                return repo.get_pull(pr_number)
            except GithubException as e:
                if e.status == 404:
                    raise GitHubError(f"PR #{pr_number} not found") from e
                raise GitHubError(f"Failed to get PR #{pr_number}: {e}") from e

        return await asyncio.to_thread(_get_pr)

    async def update_pr(
        self,
        repo_name: str,
        pr_number: int,
        title: str | None = None,
        body: str | None = None,
    ) -> GHPullRequest:
        """Update an existing pull request.

        Args:
            repo_name: Full repository name (owner/repo).
            pr_number: Pull request number to update.
            title: New title (optional).
            body: New body (optional).

        Returns:
            Updated PullRequest object.

        Raises:
            GitHubError: On API errors.
        """

        def _update_pr() -> GHPullRequest:
            try:
                repo = self._get_repo(repo_name)
                pr = repo.get_pull(pr_number)
                if title is not None and body is not None:
                    pr.edit(title=title, body=body)
                elif title is not None:
                    pr.edit(title=title)
                elif body is not None:
                    pr.edit(body=body)
                return pr
            except GithubException as e:
                raise GitHubError(f"Failed to update PR #{pr_number}: {e}") from e

        return await asyncio.to_thread(_update_pr)

    async def get_pr_checks(
        self,
        repo_name: str,
        pr_number: int,
    ) -> list[CheckRun]:
        """Get CI check statuses for a pull request.

        Args:
            repo_name: Full repository name (owner/repo).
            pr_number: Pull request number.

        Returns:
            List of CheckRun objects.

        Raises:
            GitHubError: On API errors.
        """

        def _get_checks() -> list[CheckRun]:
            try:
                repo = self._get_repo(repo_name)
                pr = repo.get_pull(pr_number)
                # Get the latest commit's check runs
                commits = pr.get_commits()
                if commits.totalCount == 0:
                    return []
                head_commit = commits.reversed[0]
                check_runs = head_commit.get_check_runs()
                return list(check_runs)
            except GithubException as e:
                raise GitHubError(
                    f"Failed to get checks for PR #{pr_number}: {e}"
                ) from e

        return await asyncio.to_thread(_get_checks)

    # =========================================================================
    # Repository Operations
    # =========================================================================

    async def get_repo_info(self, repo_name: str) -> Repository:
        """Get repository information.

        Args:
            repo_name: Full repository name (owner/repo).

        Returns:
            Repository object.

        Raises:
            GitHubError: On API errors or if repo not found.
        """

        def _get_repo() -> Repository:
            try:
                return self._get_repo(repo_name)
            except GithubException as e:
                if e.status == 404:
                    raise GitHubError(f"Repository {repo_name} not found") from e
                raise GitHubError(f"Failed to get repository: {e}") from e

        return await asyncio.to_thread(_get_repo)

    def close(self) -> None:
        """Close the underlying GitHub client connection."""
        if self._github is not None:
            self._github.close()
            self._github = None
