from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from claude_agent_sdk import tool
from github import GithubException

from maverick.exceptions import GitHubAuthError, GitHubCLINotFoundError, GitHubError
from maverick.logging import get_logger
from maverick.tools.github.responses import error_response, success_response
from maverick.utils.github_client import GitHubClient

if TYPE_CHECKING:
    pass

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


@tool(
    "github_create_pr",
    "Create a pull request on GitHub",
    {"title": str, "body": str, "base": str, "head": str, "draft": bool},
)
async def github_create_pr(args: dict[str, Any]) -> dict[str, Any]:
    """Create a pull request (T014-T016)."""
    title = args["title"]
    body = args["body"]
    base = args["base"]
    head = args["head"]
    draft = args.get("draft", False)

    # Validate inputs
    if not title or not title.strip():
        return error_response("PR title cannot be empty", "INVALID_INPUT")
    if not body or not body.strip():
        return error_response("PR body cannot be empty", "INVALID_INPUT")

    logger.info(
        "Creating PR: %s (head=%s -> base=%s, draft=%s)", title, head, base, draft
    )

    try:
        client = _get_client()
        repo_name = await _get_repo_name_async()

        pr = await client.create_pr(
            repo_name=repo_name,
            title=title,
            body=body,
            head=head,
            base=base,
            draft=draft,
        )

        logger.info("PR #%d created: %s", pr.number, pr.html_url)
        return success_response(
            {
                "pr_number": pr.number,
                "url": pr.html_url,
                "state": "draft" if draft else "open",
                "title": title,
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
    except GitHubError as e:
        error_msg = str(e).lower()
        # Check for branch-specific errors
        if "head" in error_msg and "not found" in error_msg:
            logger.warning("PR creation failed: branch '%s' not found", head)
            return error_response(f"Branch '{head}' not found", "BRANCH_NOT_FOUND")
        if "base" in error_msg and "not found" in error_msg:
            logger.warning("PR creation failed: branch '%s' not found", base)
            return error_response(f"Branch '{base}' not found", "BRANCH_NOT_FOUND")
        logger.warning("PR creation failed: %s", e)
        return error_response(str(e), "INTERNAL_ERROR", e.retry_after)
    except Exception as e:
        logger.exception("Unexpected error creating PR")
        return error_response(str(e), "INTERNAL_ERROR")


@tool(
    "github_pr_status",
    "Get PR status including checks, reviews, and merge readiness",
    {"pr_number": int},
)
async def github_pr_status(args: dict[str, Any]) -> dict[str, Any]:
    """Get PR merge status (T028-T030)."""
    pr_number = args["pr_number"]

    # Validate
    if pr_number < 1:
        return error_response("PR number must be positive", "INVALID_INPUT")

    logger.info("Getting status for PR #%d", pr_number)

    try:
        client = _get_client()
        repo_name = await _get_repo_name_async()

        # Get the PR
        pr = await client.get_pr(repo_name=repo_name, pr_number=pr_number)

        # Get checks for the PR
        check_runs = await client.get_pr_checks(
            repo_name=repo_name, pr_number=pr_number
        )

        def _get_pr_details() -> dict[str, Any]:
            """Get PR details including reviews and merge state."""
            # Get reviews
            reviews_list = []
            for review in pr.get_reviews():
                reviews_list.append(
                    {
                        "author": review.user.login if review.user else "",
                        "state": review.state,
                    }
                )

            # Parse checks
            checks_list = []
            for check in check_runs:
                checks_list.append(
                    {
                        "name": check.name,
                        "status": check.status.lower() if check.status else "queued",
                        "conclusion": check.conclusion,
                    }
                )

            # Determine merge state
            # PyGithub's mergeable attribute can be True, False, or None (unknown)
            mergeable = pr.mergeable

            # Get merge state status (PyGithub returns "MERGEABLE", "CONFLICTING", etc.)
            mergeable_state = pr.mergeable_state or "unknown"
            if isinstance(mergeable_state, str):
                mergeable_state = mergeable_state.lower()

            # Detect conflicts
            has_conflicts = (
                mergeable_state in ("dirty", "conflicting") or mergeable is False
            )

            return {
                "pr_number": pr_number,
                "state": pr.state.lower() if pr.state else "unknown",
                "mergeable": mergeable,
                "merge_state_status": mergeable_state,
                "has_conflicts": has_conflicts,
                "reviews": reviews_list,
                "checks": checks_list,
            }

        status = await asyncio.to_thread(_get_pr_details)

        logger.info(
            "PR #%d status: state=%s, mergeable=%s, conflicts=%s",
            pr_number,
            status["state"],
            status["mergeable"],
            status["has_conflicts"],
        )
        return success_response(status)

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
            logger.warning("PR #%d not found", pr_number)
            return error_response(f"PR #{pr_number} not found", "NOT_FOUND")
        logger.warning("Get PR status failed: %s", e)
        return error_response(f"Failed to get PR status: {e}", "INTERNAL_ERROR")
    except GitHubError as e:
        # Check if it's a not found error
        if "not found" in str(e).lower():
            logger.warning("PR #%d not found", pr_number)
            return error_response(f"PR #{pr_number} not found", "NOT_FOUND")
        logger.warning("Get PR status failed: %s", e)
        return error_response(str(e), "INTERNAL_ERROR", e.retry_after)
    except Exception as e:
        logger.exception("Unexpected error getting PR status")
        return error_response(str(e), "INTERNAL_ERROR")
