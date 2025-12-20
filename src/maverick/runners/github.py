"""GitHub CLI runner for interacting with GitHub via gh CLI."""

from __future__ import annotations

import json
import shutil

from maverick.exceptions import GitHubAuthError, GitHubCLINotFoundError
from maverick.runners.command import CommandRunner
from maverick.runners.models import CheckStatus, GitHubIssue, PullRequest

__all__ = ["GitHubCLIRunner"]


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

    async def _run_gh_command(
        self, *args: str
    ) -> dict[str, object] | list[dict[str, object]]:
        """Run gh command and parse JSON output."""
        result = await self._command_runner.run(["gh", *args])
        if not result.success:
            raise RuntimeError(f"gh command failed: {result.stderr}")
        parsed: dict[str, object] | list[dict[str, object]] = (
            json.loads(result.stdout) if result.stdout.strip() else {}
        )
        return parsed

    async def get_issue(self, number: int) -> GitHubIssue:
        """Get a single issue by number."""
        await self._ensure_authenticated()
        result = await self._run_gh_command(
            "issue",
            "view",
            str(number),
            "--json",
            "number,title,body,labels,state,assignees,url",
        )
        # Result is a dict for single issue view
        data = result if isinstance(result, dict) else {}
        labels_raw = data.get("labels", [])
        labels_list = labels_raw if isinstance(labels_raw, list) else []
        assignees_raw = data.get("assignees", [])
        assignees_list = assignees_raw if isinstance(assignees_raw, list) else []
        state_raw = data.get("state", "open")
        state_str = str(state_raw).lower() if state_raw else "open"
        number_val = data.get("number", 0)
        return GitHubIssue(
            number=int(str(number_val)) if number_val else 0,
            title=str(data.get("title", "")),
            body=str(data.get("body", "")),
            labels=tuple(
                str(label.get("name", "")) if isinstance(label, dict) else str(label)
                for label in labels_list
            ),
            state=state_str,
            assignees=tuple(
                str(a.get("login", "")) if isinstance(a, dict) else str(a)
                for a in assignees_list
            ),
            url=str(data.get("url", "")),
        )

    async def list_issues(
        self,
        label: str | None = None,
        state: str = "open",
        limit: int = 30,
    ) -> list[GitHubIssue]:
        """List issues with optional filters."""
        await self._ensure_authenticated()
        fields = "number,title,body,labels,state,assignees,url"
        args = ["issue", "list", "--json", fields]
        args.extend(["--state", state, "--limit", str(limit)])
        if label:
            args.extend(["--label", label])

        result = await self._run_gh_command(*args)
        # Result is a list for issue list
        data = result if isinstance(result, list) else []
        issues: list[GitHubIssue] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            labels_raw = item.get("labels", [])
            labels_list = labels_raw if isinstance(labels_raw, list) else []
            assignees_raw = item.get("assignees", [])
            assignees_list = assignees_raw if isinstance(assignees_raw, list) else []
            state_raw = item.get("state", "open")
            state_str = str(state_raw).lower() if state_raw else "open"
            number_val = item.get("number", 0)
            issues.append(
                GitHubIssue(
                    number=int(str(number_val)) if number_val else 0,
                    title=str(item.get("title", "")),
                    body=str(item.get("body", "")),
                    labels=tuple(
                        str(label.get("name", ""))
                        if isinstance(label, dict)
                        else str(label)
                        for label in labels_list
                    ),
                    state=state_str,
                    assignees=tuple(
                        str(a.get("login", "")) if isinstance(a, dict) else str(a)
                        for a in assignees_list
                    ),
                    url=str(item.get("url", "")),
                )
            )
        return issues

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
        """Get a pull request by number."""
        await self._ensure_authenticated()
        fields = "number,title,body,state,url,headRefName,baseRefName,mergeable,isDraft"
        result = await self._run_gh_command("pr", "view", str(number), "--json", fields)
        # Result is a dict for single PR view
        data = result if isinstance(result, dict) else {}
        state_raw = data.get("state", "open")
        state_str = str(state_raw).lower() if state_raw else "open"
        mergeable_raw = data.get("mergeable")
        mergeable_val = bool(mergeable_raw) if mergeable_raw is not None else None
        number_val = data.get("number", 0)
        return PullRequest(
            number=int(str(number_val)) if number_val else 0,
            title=str(data.get("title", "")),
            body=str(data.get("body", "")),
            state=state_str,
            url=str(data.get("url", "")),
            head_branch=str(data.get("headRefName", "")),
            base_branch=str(data.get("baseRefName", "")),
            mergeable=mergeable_val,
            draft=bool(data.get("isDraft", False)),
        )

    async def get_pr_checks(self, pr_number: int) -> list[CheckStatus]:
        """Get CI check statuses for a PR."""
        await self._ensure_authenticated()
        result = await self._run_gh_command(
            "pr", "checks", str(pr_number), "--json", "name,state,conclusion,detailsUrl"
        )
        # Result is a list for checks
        data = result if isinstance(result, list) else []
        checks: list[CheckStatus] = []
        for check in data:
            if not isinstance(check, dict):
                continue
            conclusion_raw = check.get("conclusion")
            state_raw = check.get("state", "queued")
            checks.append(
                CheckStatus(
                    name=str(check.get("name", "")),
                    status=(
                        "completed"
                        if conclusion_raw
                        else str(state_raw).lower()
                        if state_raw
                        else "queued"
                    ),
                    conclusion=(
                        str(conclusion_raw).lower() if conclusion_raw else None
                    ),
                    url=(
                        str(check.get("detailsUrl", ""))
                        if check.get("detailsUrl")
                        else None
                    ),
                )
            )
        return checks
