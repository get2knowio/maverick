from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from claude_agent_sdk import tool

from maverick.tools.github.errors import classify_error
from maverick.tools.github.responses import error_response, success_response
from maverick.tools.github.runner import run_gh_command

logger = logging.getLogger(__name__)


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

    cmd_args = [
        "pr",
        "create",
        "--title",
        title,
        "--body",
        body,
        "--base",
        base,
        "--head",
        head,
    ]
    if draft:
        cmd_args.append("--draft")

    try:
        stdout, stderr, return_code = await run_gh_command(*cmd_args)

        if return_code != 0:
            message, error_code, retry_after = classify_error(stderr, stdout)
            # Check for branch-specific errors
            if "head" in stderr.lower() and "not found" in stderr.lower():
                message = f"Branch '{head}' not found"
                error_code = "BRANCH_NOT_FOUND"
            elif "base" in stderr.lower() and "not found" in stderr.lower():
                message = f"Branch '{base}' not found"
                error_code = "BRANCH_NOT_FOUND"
            logger.warning("PR creation failed: %s", message)
            return error_response(message, error_code, retry_after)

        # Parse PR URL to extract number
        pr_url = stdout.strip()
        pr_number = int(pr_url.rstrip("/").split("/")[-1])

        logger.info("PR #%d created: %s", pr_number, pr_url)
        return success_response(
            {
                "pr_number": pr_number,
                "url": pr_url,
                "state": "draft" if draft else "open",
                "title": title,
            }
        )

    except asyncio.TimeoutError:
        logger.error("Timeout creating PR")
        return error_response("Operation timed out", "TIMEOUT")
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

    fields = (
        "number,state,mergeable,mergeStateStatus,reviews,"
        "statusCheckRollup,headRefName,baseRefName"
    )
    cmd_args = ["pr", "view", str(pr_number), "--json", fields]

    try:
        stdout, stderr, return_code = await run_gh_command(*cmd_args)

        if return_code != 0:
            message, error_code, retry_after = classify_error(stderr, stdout)
            if "not found" in (stderr or stdout).lower():
                message = f"PR #{pr_number} not found"
                error_code = "NOT_FOUND"
            logger.warning("Get PR status failed: %s", message)
            return error_response(message, error_code, retry_after)

        data = json.loads(stdout)

        # Parse reviews
        reviews = []
        for review in data.get("reviews", []):
            if isinstance(review, dict):
                author = review.get("author", {})
                reviews.append(
                    {
                        "author": author.get("login", "")
                        if isinstance(author, dict)
                        else str(author),
                        "state": review.get("state", "PENDING"),
                    }
                )

        # Parse checks
        checks = []
        rollup = data.get("statusCheckRollup", []) or []
        for check in rollup:
            if isinstance(check, dict):
                checks.append(
                    {
                        "name": check.get("name", check.get("context", "unknown")),
                        "status": check.get("status", "queued").lower(),
                        "conclusion": check.get("conclusion"),
                    }
                )

        # Determine merge state
        mergeable_raw = data.get("mergeable")
        merge_state = data.get("mergeStateStatus", "unknown")
        if isinstance(merge_state, str):
            merge_state = merge_state.lower()

        # Convert mergeable to boolean
        # API returns "MERGEABLE", "CONFLICTING", "UNKNOWN", or null
        if mergeable_raw in (True, "MERGEABLE"):
            mergeable = True
        elif mergeable_raw in (False, "CONFLICTING"):
            mergeable = False
        else:
            mergeable = None  # UNKNOWN or null

        # Detect conflicts
        has_conflicts = (
            merge_state in ("dirty", "conflicting") or mergeable_raw == "CONFLICTING"
        )

        status = {
            "pr_number": pr_number,
            "state": data.get("state", "unknown").lower(),
            "mergeable": mergeable,
            "merge_state_status": merge_state,
            "has_conflicts": has_conflicts,
            "reviews": reviews,
            "checks": checks,
        }

        logger.info(
            "PR #%d status: state=%s, mergeable=%s, conflicts=%s",
            pr_number,
            status["state"],
            status["mergeable"],
            status["has_conflicts"],
        )
        return success_response(status)

    except json.JSONDecodeError as e:
        logger.error("Failed to parse PR status: %s", e)
        return error_response(f"Failed to parse response: {e}", "INTERNAL_ERROR")
    except asyncio.TimeoutError:
        logger.error("Timeout getting PR #%d status", pr_number)
        return error_response("Operation timed out", "TIMEOUT")
    except Exception as e:
        logger.exception("Unexpected error getting PR status")
        return error_response(str(e), "INTERNAL_ERROR")
