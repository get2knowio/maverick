from __future__ import annotations

from typing import TYPE_CHECKING, Any

from claude_agent_sdk import tool

from maverick.exceptions import GitHubAuthError, GitHubCLINotFoundError, GitHubError
from maverick.logging import get_logger
from maverick.tools.github.responses import error_response, success_response
from maverick.utils.github_client import GitHubClient

if TYPE_CHECKING:
    from github.Issue import Issue

logger = get_logger(__name__)

# Module-level client for lazy initialization
_github_client: GitHubClient | None = None


def _get_client() -> GitHubClient:
    """Get or create the module-level GitHubClient.

    Returns:
        GitHubClient instance.

    Raises:
        GitHubCLINotFoundError: If gh CLI is not installed.
        GitHubAuthError: If gh CLI is not authenticated.
    """
    global _github_client
    if _github_client is None:
        _github_client = GitHubClient()
    return _github_client


async def _get_repo_name_async() -> str:
    """Get the current repository name from git remote asynchronously.

    Uses shared utility from runner module per CLAUDE.md.

    Returns:
        Repository name in 'owner/repo' format.

    Raises:
        GitHubError: If unable to determine repository name.
    """
    from maverick.tools.github.runner import get_repo_name_async

    return await get_repo_name_async()


def _issue_to_dict(issue: Issue, include_details: bool = False) -> dict[str, Any]:
    """Convert a PyGithub Issue to a dictionary.

    Args:
        issue: PyGithub Issue object.
        include_details: Include additional details (body, comments, dates).

    Returns:
        Dictionary representation of the issue.
    """
    result: dict[str, Any] = {
        "number": issue.number,
        "title": issue.title,
        "labels": [label.name for label in issue.labels],
        "state": issue.state,
        "url": issue.html_url,
    }

    if include_details:
        result.update(
            {
                "body": issue.body or "",
                "assignees": [a.login for a in issue.assignees],
                "author": issue.user.login if issue.user else "",
                "comments_count": issue.comments,
                "created_at": issue.created_at.isoformat() if issue.created_at else "",
                "updated_at": issue.updated_at.isoformat() if issue.updated_at else "",
            }
        )

    return result


@tool(
    "github_list_issues",
    "List GitHub issues with optional filtering by label and state",
    {"label": str, "state": str, "limit": int},
)
async def github_list_issues(args: dict[str, Any]) -> dict[str, Any]:
    """List issues with filtering (T021, T023-T024)."""
    label = args.get("label")
    state = args.get("state", "open")
    limit = args.get("limit", 30)

    # Validate state
    if state not in ("open", "closed", "all"):
        return error_response(
            f"Invalid state '{state}'. Must be 'open', 'closed', or 'all'",
            "INVALID_INPUT",
        )

    # Validate limit
    if limit < 1:
        return error_response("Limit must be positive", "INVALID_INPUT")

    logger.info("Listing issues: state=%s, label=%s, limit=%d", state, label, limit)

    try:
        client = _get_client()
        repo_name = await _get_repo_name_async()

        # Convert label to list format for GitHubClient
        labels = [label] if label else None

        issues = await client.list_issues(
            repo_name=repo_name,
            state=state,
            labels=labels,
            limit=limit,
        )

        # Convert to response format
        issues_list = [_issue_to_dict(issue) for issue in issues]

        logger.info("Found %d issues", len(issues_list))
        return success_response({"issues": issues_list})

    except GitHubCLINotFoundError:
        logger.error("GitHub CLI not found")
        return error_response(
            "GitHub CLI (gh) not installed. Install from: https://cli.github.com/",
            "AUTH_ERROR",
        )
    except GitHubAuthError as e:
        logger.error("GitHub authentication failed: %s", e)
        return error_response(str(e), "AUTH_ERROR")
    except GitHubError as e:
        logger.warning("Issue list failed: %s", e)
        return error_response(str(e), "INTERNAL_ERROR", e.retry_after)
    except Exception as e:
        logger.exception("Unexpected error listing issues")
        return error_response(str(e), "INTERNAL_ERROR")


@tool(
    "github_get_issue",
    "Get detailed information about a specific GitHub issue",
    {"issue_number": int},
)
async def github_get_issue(args: dict[str, Any]) -> dict[str, Any]:
    """Get issue details (T022-T024)."""
    issue_number = args["issue_number"]

    # Validate
    if issue_number < 1:
        return error_response("Issue number must be positive", "INVALID_INPUT")

    logger.info("Getting issue #%d", issue_number)

    try:
        client = _get_client()
        repo_name = await _get_repo_name_async()

        issue = await client.get_issue(repo_name=repo_name, issue_number=issue_number)

        # Convert to detailed response format
        issue_dict = _issue_to_dict(issue, include_details=True)

        logger.info("Retrieved issue #%d: %s", issue_number, issue_dict["title"])
        return success_response(issue_dict)

    except GitHubCLINotFoundError:
        logger.error("GitHub CLI not found")
        return error_response(
            "GitHub CLI (gh) not installed. Install from: https://cli.github.com/",
            "AUTH_ERROR",
        )
    except GitHubAuthError as e:
        logger.error("GitHub authentication failed: %s", e)
        return error_response(str(e), "AUTH_ERROR")
    except GitHubError as e:
        # Check if it's a not found error
        if "not found" in str(e).lower():
            logger.warning("Issue #%d not found", issue_number)
            return error_response(f"Issue #{issue_number} not found", "NOT_FOUND")
        logger.warning("Get issue failed: %s", e)
        return error_response(str(e), "INTERNAL_ERROR", e.retry_after)
    except Exception as e:
        logger.exception("Unexpected error getting issue")
        return error_response(str(e), "INTERNAL_ERROR")


@tool(
    "github_add_labels",
    "Add labels to an issue or pull request",
    {"issue_number": int, "labels": list},
)
async def github_add_labels(args: dict[str, Any]) -> dict[str, Any]:
    """Add labels to issue/PR (T039-T041)."""
    import asyncio

    from github import GithubException

    issue_number = args["issue_number"]
    labels = args["labels"]

    # Validate
    if issue_number < 1:
        return error_response("Issue number must be positive", "INVALID_INPUT")
    if not labels:
        return error_response("Labels list cannot be empty", "INVALID_INPUT")

    logger.info("Adding labels to #%d: %s", issue_number, labels)

    try:
        client = _get_client()
        repo_name = await _get_repo_name_async()

        def _add_labels() -> None:
            repo = client.github.get_repo(repo_name)
            issue = repo.get_issue(issue_number)
            # Add labels (PyGithub accepts list of label names)
            for label in labels:
                issue.add_to_labels(str(label))

        await asyncio.to_thread(_add_labels)

        logger.info("Labels added to #%d: %s", issue_number, labels)
        return success_response(
            {
                "success": True,
                "issue_number": issue_number,
                "labels_added": labels,
            }
        )

    except GitHubCLINotFoundError:
        logger.error("GitHub CLI not found")
        return error_response(
            "GitHub CLI (gh) not installed. Install from: https://cli.github.com/",
            "AUTH_ERROR",
        )
    except GitHubAuthError as e:
        logger.error("GitHub authentication failed: %s", e)
        return error_response(str(e), "AUTH_ERROR")
    except GithubException as e:
        if e.status == 404:
            logger.warning("Issue #%d not found", issue_number)
            return error_response(f"Issue #{issue_number} not found", "NOT_FOUND")
        logger.warning("Add labels failed: %s", e)
        return error_response(f"Failed to add labels: {e}", "INTERNAL_ERROR")
    except GitHubError as e:
        logger.warning("Add labels failed: %s", e)
        return error_response(str(e), "INTERNAL_ERROR", e.retry_after)
    except Exception as e:
        logger.exception("Unexpected error adding labels")
        return error_response(str(e), "INTERNAL_ERROR")


@tool(
    "github_close_issue",
    "Close a GitHub issue with an optional comment",
    {"issue_number": int, "comment": str},
)
async def github_close_issue(args: dict[str, Any]) -> dict[str, Any]:
    """Close issue with optional comment (T045-T047)."""
    import asyncio

    from github import GithubException

    issue_number = args["issue_number"]
    comment = args.get("comment")

    # Validate
    if issue_number < 1:
        return error_response("Issue number must be positive", "INVALID_INPUT")

    logger.info("Closing issue #%d (comment=%s)", issue_number, bool(comment))

    try:
        client = _get_client()
        repo_name = await _get_repo_name_async()

        def _close_issue() -> str:
            """Close the issue and return its state."""
            repo = client.github.get_repo(repo_name)
            issue = repo.get_issue(issue_number)

            # Check if already closed (idempotent behavior)
            if issue.state == "closed":
                return "already_closed"

            # Add comment if provided
            if comment:
                issue.create_comment(comment)

            # Close the issue
            issue.edit(state="closed")
            return "closed"

        result = await asyncio.to_thread(_close_issue)

        if result == "already_closed":
            logger.info("Issue #%d was already closed", issue_number)

        logger.info("Issue #%d closed", issue_number)
        return success_response(
            {
                "success": True,
                "issue_number": issue_number,
                "state": "closed",
            }
        )

    except GitHubCLINotFoundError:
        logger.error("GitHub CLI not found")
        return error_response(
            "GitHub CLI (gh) not installed. Install from: https://cli.github.com/",
            "AUTH_ERROR",
        )
    except GitHubAuthError as e:
        logger.error("GitHub authentication failed: %s", e)
        return error_response(str(e), "AUTH_ERROR")
    except GithubException as e:
        if e.status == 404:
            logger.warning("Issue #%d not found", issue_number)
            return error_response(f"Issue #{issue_number} not found", "NOT_FOUND")
        logger.warning("Close issue failed: %s", e)
        return error_response(f"Failed to close issue: {e}", "INTERNAL_ERROR")
    except GitHubError as e:
        logger.warning("Close issue failed: %s", e)
        return error_response(str(e), "INTERNAL_ERROR", e.retry_after)
    except Exception as e:
        logger.exception("Unexpected error closing issue")
        return error_response(str(e), "INTERNAL_ERROR")
