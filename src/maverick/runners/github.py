"""GitHub CLI runner for interacting with GitHub via gh CLI."""

from __future__ import annotations

import shutil

from pydantic import BaseModel, Field, TypeAdapter

from maverick.exceptions import GitHubAuthError, GitHubCLINotFoundError
from maverick.runners.command import CommandRunner
from maverick.runners.models import CheckStatus, GitHubIssue, PullRequest

__all__ = ["GitHubCLIRunner"]


# =============================================================================
# Response Models (Internal - for parsing GitHub CLI JSON output)
# =============================================================================


class GitHubLabelResponse(BaseModel):
    """GitHub API label response."""

    name: str


class GitHubUserResponse(BaseModel):
    """GitHub API user response."""

    login: str


class GitHubIssueResponse(BaseModel):
    """GitHub API issue response.

    Parses JSON output from 'gh issue view/list --json ...' commands.
    """

    number: int
    title: str
    body: str
    state: str
    url: str
    labels: list[GitHubLabelResponse] = Field(default_factory=list)
    assignees: list[GitHubUserResponse] = Field(default_factory=list)


class GitHubPRResponse(BaseModel):
    """GitHub API pull request response.

    Parses JSON output from 'gh pr view --json ...' commands.
    """

    number: int
    title: str
    body: str
    state: str
    url: str
    head_ref_name: str = Field(alias="headRefName")
    base_ref_name: str = Field(alias="baseRefName")
    is_draft: bool = Field(alias="isDraft")
    mergeable: bool | None = None


class GitHubCheckResponse(BaseModel):
    """GitHub API check response.

    Parses JSON output from 'gh pr checks --json ...' commands.
    """

    name: str
    state: str
    conclusion: str | None = None
    details_url: str | None = Field(default=None, alias="detailsUrl")


class GitHubCLIRunner:
    """Execute GitHub operations via the gh CLI."""

    def __init__(self) -> None:
        """Initialize the GitHubCLIRunner.

        Raises:
            GitHubCLINotFoundError: If gh CLI is not installed.
            GitHubAuthError: If gh CLI is not authenticated (checked on first use).
        """
        self._command_runner = CommandRunner()
        self._check_gh_available()
        self._auth_checked = False

    def _check_gh_available(self) -> None:
        """Check if gh CLI is installed."""
        if shutil.which("gh") is None:
            raise GitHubCLINotFoundError()

    async def _check_gh_auth(self) -> None:
        """Check if gh CLI is authenticated."""
        result = await self._command_runner.run(["gh", "auth", "status"])
        if not result.success:
            raise GitHubAuthError()

    async def _ensure_authenticated(self) -> None:
        """Check authentication status on first use (fail-fast).

        Raises:
            GitHubAuthError: If gh CLI is not authenticated.
        """
        if not self._auth_checked:
            await self._check_gh_auth()
            self._auth_checked = True

    async def _run_gh_command(self, *args: str) -> str:
        """Run gh command and return raw JSON output.

        Returns:
            Raw JSON string from gh CLI stdout.

        Raises:
            RuntimeError: If gh command fails.
        """
        import asyncio
        import logging

        logger = logging.getLogger(__name__)
        max_retries = 3
        last_error = None

        for attempt in range(max_retries):
            result = await self._command_runner.run(["gh", *args])
            if result.success:
                return result.stdout.strip() if result.stdout.strip() else "{}"

            # Check if it's a network/transient error (generic check)
            # We retry on any failure for now as gh cli often fails on network
            last_error = result.stderr
            logger.warning(
                f"gh command failed (attempt {attempt + 1}/{max_retries}): {last_error}"
            )

            if attempt < max_retries - 1:
                await asyncio.sleep(2**attempt)

        raise RuntimeError(
            f"gh command failed after {max_retries} attempts: {last_error}"
        )

    async def get_issue(self, number: int) -> GitHubIssue:
        """Get a single issue by number.

        Args:
            number: GitHub issue number to fetch.

        Returns:
            GitHubIssue instance with parsed issue data.

        Raises:
            RuntimeError: If gh command fails.
            pydantic.ValidationError: If response JSON doesn't match expected schema.
        """
        await self._ensure_authenticated()
        json_output = await self._run_gh_command(
            "issue",
            "view",
            str(number),
            "--json",
            "number,title,body,labels,state,assignees,url",
        )
        # Parse response using Pydantic
        response = GitHubIssueResponse.model_validate_json(json_output)

        return GitHubIssue(
            number=response.number,
            title=response.title,
            body=response.body,
            labels=tuple(label.name for label in response.labels),
            state=response.state.lower(),
            assignees=tuple(user.login for user in response.assignees),
            url=response.url,
        )

    async def list_issues(
        self,
        label: str | None = None,
        state: str = "open",
        limit: int = 30,
    ) -> list[GitHubIssue]:
        """List issues with optional filters.

        Args:
            label: Filter by label name (optional).
            state: Filter by state ("open", "closed", or "all").
            limit: Maximum number of issues to return.

        Returns:
            List of GitHubIssue instances.

        Raises:
            RuntimeError: If gh command fails.
            pydantic.ValidationError: If response JSON doesn't match expected schema.
        """
        await self._ensure_authenticated()
        fields = "number,title,body,labels,state,assignees,url"
        args = ["issue", "list", "--json", fields]
        args.extend(["--state", state, "--limit", str(limit)])
        if label:
            args.extend(["--label", label])

        json_output = await self._run_gh_command(*args)
        # Parse response list using Pydantic TypeAdapter
        adapter = TypeAdapter(list[GitHubIssueResponse])
        responses = adapter.validate_json(json_output)

        return [
            GitHubIssue(
                number=response.number,
                title=response.title,
                body=response.body,
                labels=tuple(label.name for label in response.labels),
                state=response.state.lower(),
                assignees=tuple(user.login for user in response.assignees),
                url=response.url,
            )
            for response in responses
        ]

    async def create_pr(
        self,
        title: str,
        body: str,
        base: str = "main",
        head: str | None = None,
        draft: bool = False,
    ) -> PullRequest:
        """Create a new pull request."""
        await self._ensure_authenticated()
        args = ["pr", "create", "--title", title, "--body", body, "--base", base]
        if head:
            args.extend(["--head", head])
        if draft:
            args.append("--draft")

        # Create PR and get JSON output
        result = await self._command_runner.run(["gh", *args])
        if not result.success:
            raise RuntimeError(f"Failed to create PR: {result.stderr}")

        # The create command outputs the PR URL, need to get full details
        pr_url = result.stdout.strip()
        # Extract PR number from URL
        pr_number = int(pr_url.split("/")[-1])

        return await self.get_pr(pr_number)

    async def get_pr(self, number: int) -> PullRequest:
        """Get a pull request by number.

        Args:
            number: Pull request number to fetch.

        Returns:
            PullRequest instance with parsed PR data.

        Raises:
            RuntimeError: If gh command fails.
            pydantic.ValidationError: If response JSON doesn't match expected schema.
        """
        await self._ensure_authenticated()
        fields = "number,title,body,state,url,headRefName,baseRefName,mergeable,isDraft"
        json_output = await self._run_gh_command(
            "pr", "view", str(number), "--json", fields
        )
        # Parse response using Pydantic
        response = GitHubPRResponse.model_validate_json(json_output)

        return PullRequest(
            number=response.number,
            title=response.title,
            body=response.body,
            state=response.state.lower(),
            url=response.url,
            head_branch=response.head_ref_name,
            base_branch=response.base_ref_name,
            mergeable=response.mergeable,
            draft=response.is_draft,
        )

    async def get_pr_checks(self, pr_number: int) -> list[CheckStatus]:
        """Get CI check statuses for a PR.

        Args:
            pr_number: Pull request number to get checks for.

        Returns:
            List of CheckStatus instances.

        Raises:
            RuntimeError: If gh command fails.
            pydantic.ValidationError: If response JSON doesn't match expected schema.
        """
        await self._ensure_authenticated()
        json_output = await self._run_gh_command(
            "pr", "checks", str(pr_number), "--json", "name,state,conclusion,detailsUrl"
        )
        # Parse response list using Pydantic TypeAdapter
        adapter = TypeAdapter(list[GitHubCheckResponse])
        responses = adapter.validate_json(json_output)

        return [
            CheckStatus(
                name=response.name,
                status=(
                    "completed"
                    if response.conclusion
                    else response.state.lower()
                    if response.state
                    else "queued"
                ),
                conclusion=response.conclusion.lower() if response.conclusion else None,
                url=response.details_url if response.details_url else None,
            )
            for response in responses
        ]
