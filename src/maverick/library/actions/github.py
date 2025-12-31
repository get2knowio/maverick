"""GitHub actions for workflow execution."""

from __future__ import annotations

import json

from maverick.library.actions.types import (
    FetchedIssue,
    FetchIssuesResult,
    FetchSingleIssueResult,
    PRCreationResult,
)
from maverick.logging import get_logger
from maverick.runners.command import CommandRunner

logger = get_logger(__name__)

# Shared runner instance for GitHub actions
_runner = CommandRunner(timeout=60.0)


async def create_github_pr(
    base_branch: str,
    draft: bool,
    title: str | None,
    generated_title: str | None,
    generated_body: str,
) -> PRCreationResult:
    """Create a pull request via GitHub CLI.

    Args:
        base_branch: Target branch for PR
        draft: Create as draft PR
        title: User-provided title (optional)
        generated_title: Auto-generated title (optional)
        generated_body: Auto-generated PR body

    Returns:
        PRCreationResult dataclass instance
    """
    # Use provided title or generated title
    pr_title = title or generated_title or "Update"

    try:
        cmd = [
            "gh",
            "pr",
            "create",
            "--base",
            base_branch,
            "--title",
            pr_title,
            "--body",
            generated_body,
        ]

        if draft:
            cmd.append("--draft")

        result = await _runner.run(cmd)

        if not result.success:
            logger.error(f"PR creation failed: {result.stderr}")
            return PRCreationResult(
                success=False,
                pr_number=None,
                pr_url=None,
                title=pr_title,
                draft=draft,
                base_branch=base_branch,
                error=result.stderr or f"Command failed with code {result.returncode}",
            )

        # Parse PR URL from output
        pr_url = result.stdout.strip()

        # Extract PR number from URL
        pr_number = None
        if pr_url:
            parts = pr_url.rstrip("/").split("/")
            if parts and parts[-1].isdigit():
                pr_number = int(parts[-1])

        return PRCreationResult(
            success=True,
            pr_number=pr_number,
            pr_url=pr_url,
            title=pr_title,
            draft=draft,
            base_branch=base_branch,
            error=None,
        )

    except Exception as e:
        logger.error(f"PR creation failed: {e}")
        return PRCreationResult(
            success=False,
            pr_number=None,
            pr_url=None,
            title=pr_title,
            draft=draft,
            base_branch=base_branch,
            error=str(e),
        )


async def fetch_github_issues(
    label: str,
    limit: int = 5,
    state: str = "open",
) -> FetchIssuesResult:
    """Fetch issues from GitHub with label filter.

    Args:
        label: Label to filter issues by
        limit: Maximum number of issues to fetch
        state: Issue state filter ("open", "closed", "all")

    Returns:
        FetchIssuesResult dataclass instance
    """
    try:
        cmd = [
            "gh",
            "issue",
            "list",
            "--label",
            label,
            "--limit",
            str(limit),
            "--state",
            state,
            "--json",
            "number,title,body,labels,assignees,url,state",
        ]

        result = await _runner.run(cmd)

        if not result.success:
            logger.error(f"Failed to fetch GitHub issues: {result.stderr}")
            return FetchIssuesResult(
                success=False,
                issues=(),
                total_count=0,
                error=result.stderr or f"Command failed with code {result.returncode}",
            )

        issues_data = json.loads(result.stdout)

        issues: list[FetchedIssue] = []
        for issue in issues_data:
            issues.append(
                FetchedIssue(
                    number=issue["number"],
                    title=issue["title"],
                    body=issue.get("body"),
                    labels=tuple(label["name"] for label in issue.get("labels", [])),
                    assignee=(
                        issue.get("assignees", [{}])[0].get("login")
                        if issue.get("assignees")
                        else None
                    ),
                    url=issue["url"],
                    state=issue["state"],
                )
            )

        return FetchIssuesResult(
            success=True,
            issues=tuple(issues),
            total_count=len(issues),
            error=None,
        )

    except Exception as e:
        logger.error(f"Failed to fetch GitHub issues: {e}")
        return FetchIssuesResult(
            success=False,
            issues=(),
            total_count=0,
            error=str(e),
        )


async def fetch_github_issue(issue_number: int) -> FetchSingleIssueResult:
    """Fetch a single issue from GitHub.

    Args:
        issue_number: GitHub issue number

    Returns:
        FetchSingleIssueResult dataclass instance
    """
    try:
        cmd = [
            "gh",
            "issue",
            "view",
            str(issue_number),
            "--json",
            "number,title,body,labels,assignees,url,state",
        ]

        result = await _runner.run(cmd)

        if not result.success:
            logger.error(
                f"Failed to fetch GitHub issue #{issue_number}: {result.stderr}"
            )
            return FetchSingleIssueResult(
                success=False,
                issue=None,
                error=result.stderr or f"Command failed with code {result.returncode}",
            )

        issue = json.loads(result.stdout)

        fetched_issue = FetchedIssue(
            number=issue["number"],
            title=issue["title"],
            body=issue.get("body"),
            labels=tuple(label["name"] for label in issue.get("labels", [])),
            assignee=(
                issue.get("assignees", [{}])[0].get("login")
                if issue.get("assignees")
                else None
            ),
            url=issue["url"],
            state=issue["state"],
        )

        return FetchSingleIssueResult(
            success=True,
            issue=fetched_issue,
            error=None,
        )

    except Exception as e:
        logger.error(f"Failed to fetch GitHub issue #{issue_number}: {e}")
        return FetchSingleIssueResult(
            success=False,
            issue=None,
            error=str(e),
        )
