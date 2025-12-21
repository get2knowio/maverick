"""GitHub actions for workflow execution."""

from __future__ import annotations

import json
import logging
import subprocess
from typing import Any

logger = logging.getLogger(__name__)


async def create_github_pr(
    base_branch: str,
    draft: bool,
    title: str | None,
    generated_title: str | None,
    generated_body: str,
) -> dict[str, Any]:
    """Create a pull request via GitHub CLI.

    Args:
        base_branch: Target branch for PR
        draft: Create as draft PR
        title: User-provided title (optional)
        generated_title: Auto-generated title (optional)
        generated_body: Auto-generated PR body

    Returns:
        PRCreationResult as dict
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

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )

        # Parse PR URL from output
        pr_url = result.stdout.strip()

        # Extract PR number from URL
        pr_number = None
        if pr_url:
            parts = pr_url.rstrip("/").split("/")
            if parts and parts[-1].isdigit():
                pr_number = int(parts[-1])

        return {
            "success": True,
            "pr_number": pr_number,
            "pr_url": pr_url,
            "title": pr_title,
            "draft": draft,
            "base_branch": base_branch,
            "error": None,
        }

    except subprocess.CalledProcessError as e:
        logger.error(f"PR creation failed: {e.stderr}")
        return {
            "success": False,
            "pr_number": None,
            "pr_url": None,
            "title": pr_title,
            "draft": draft,
            "base_branch": base_branch,
            "error": e.stderr or str(e),
        }


async def fetch_github_issues(
    label: str,
    limit: int = 5,
    state: str = "open",
) -> dict[str, Any]:
    """Fetch issues from GitHub with label filter.

    Args:
        label: Label to filter issues by
        limit: Maximum number of issues to fetch
        state: Issue state filter ("open", "closed", "all")

    Returns:
        FetchIssuesResult as dict
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

        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        issues_data = json.loads(result.stdout)

        issues = []
        for issue in issues_data:
            issues.append(
                {
                    "number": issue["number"],
                    "title": issue["title"],
                    "body": issue.get("body"),
                    "labels": tuple(
                        label["name"] for label in issue.get("labels", [])
                    ),
                    "assignee": (
                        issue.get("assignees", [{}])[0].get("login")
                        if issue.get("assignees")
                        else None
                    ),
                    "url": issue["url"],
                    "state": issue["state"],
                }
            )

        return {
            "success": True,
            "issues": tuple(issues),
            "total_count": len(issues),
            "error": None,
        }

    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to fetch GitHub issues: {e.stderr}")
        return {
            "success": False,
            "issues": (),
            "total_count": 0,
            "error": e.stderr or str(e),
        }


async def fetch_github_issue(issue_number: int) -> dict[str, Any]:
    """Fetch a single issue from GitHub.

    Args:
        issue_number: GitHub issue number

    Returns:
        FetchSingleIssueResult as dict
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

        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        issue = json.loads(result.stdout)

        return {
            "success": True,
            "issue": {
                "number": issue["number"],
                "title": issue["title"],
                "body": issue.get("body"),
                "labels": tuple(
                    label["name"] for label in issue.get("labels", [])
                ),
                "assignee": (
                    issue.get("assignees", [{}])[0].get("login")
                    if issue.get("assignees")
                    else None
                ),
                "url": issue["url"],
                "state": issue["state"],
            },
            "error": None,
        }

    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to fetch GitHub issue #{issue_number}: {e.stderr}")
        return {
            "success": False,
            "issue": None,
            "error": e.stderr or str(e),
        }
