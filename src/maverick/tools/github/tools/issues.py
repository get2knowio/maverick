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

    cmd_args = [
        "issue",
        "list",
        "--state",
        state,
        "--limit",
        str(limit),
        "--json",
        "number,title,labels,state,url",
    ]
    if label:
        cmd_args.extend(["--label", label])

    try:
        stdout, stderr, return_code = await run_gh_command(*cmd_args)

        if return_code != 0:
            message, error_code, retry_after = classify_error(stderr, stdout)
            logger.warning("Issue list failed: %s", message)
            return error_response(message, error_code, retry_after)

        issues_data = json.loads(stdout) if stdout else []
        # Transform labels from objects to strings
        issues = []
        for issue in issues_data:
            issues.append(
                {
                    "number": issue["number"],
                    "title": issue["title"],
                    "labels": [
                        lbl["name"] if isinstance(lbl, dict) else lbl
                        for lbl in issue.get("labels", [])
                    ],
                    "state": issue["state"],
                    "url": issue["url"],
                }
            )

        logger.info("Found %d issues", len(issues))
        return success_response({"issues": issues})

    except json.JSONDecodeError as e:
        logger.error("Failed to parse issue list: %s", e)
        return error_response(f"Failed to parse response: {e}", "INTERNAL_ERROR")
    except asyncio.TimeoutError:
        logger.error("Timeout listing issues")
        return error_response("Operation timed out", "TIMEOUT")
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

    fields = (
        "number,title,body,url,state,labels,assignees,"
        "author,comments,createdAt,updatedAt"
    )
    cmd_args = ["issue", "view", str(issue_number), "--json", fields]

    try:
        stdout, stderr, return_code = await run_gh_command(*cmd_args)

        if return_code != 0:
            message, error_code, retry_after = classify_error(stderr, stdout)
            if "not found" in (stderr or stdout).lower():
                message = f"Issue #{issue_number} not found"
                error_code = "NOT_FOUND"
            logger.warning("Get issue failed: %s", message)
            return error_response(message, error_code, retry_after)

        data = json.loads(stdout)
        issue = {
            "number": data["number"],
            "title": data["title"],
            "body": data.get("body", ""),
            "url": data["url"],
            "state": data["state"],
            "labels": [
                lbl["name"] if isinstance(lbl, dict) else lbl
                for lbl in data.get("labels", [])
            ],
            "assignees": [
                a["login"] if isinstance(a, dict) else a
                for a in data.get("assignees", [])
            ],
            "author": data.get("author", {}).get("login", "")
            if isinstance(data.get("author"), dict)
            else str(data.get("author", "")),
            "comments_count": len(data.get("comments", [])),
            "created_at": data.get("createdAt", ""),
            "updated_at": data.get("updatedAt", ""),
        }

        logger.info("Retrieved issue #%d: %s", issue_number, issue["title"])
        return success_response(issue)

    except json.JSONDecodeError as e:
        logger.error("Failed to parse issue: %s", e)
        return error_response(f"Failed to parse response: {e}", "INTERNAL_ERROR")
    except asyncio.TimeoutError:
        logger.error("Timeout getting issue #%d", issue_number)
        return error_response("Operation timed out", "TIMEOUT")
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
    issue_number = args["issue_number"]
    labels = args["labels"]

    # Validate
    if issue_number < 1:
        return error_response("Issue number must be positive", "INVALID_INPUT")
    if not labels:
        return error_response("Labels list cannot be empty", "INVALID_INPUT")

    logger.info("Adding labels to #%d: %s", issue_number, labels)

    cmd_args = ["issue", "edit", str(issue_number)]
    for label in labels:
        cmd_args.extend(["--add-label", str(label)])

    try:
        stdout, stderr, return_code = await run_gh_command(*cmd_args)

        if return_code != 0:
            message, error_code, retry_after = classify_error(stderr, stdout)
            if "not found" in (stderr or stdout).lower():
                message = f"Issue #{issue_number} not found"
                error_code = "NOT_FOUND"
            logger.warning("Add labels failed: %s", message)
            return error_response(message, error_code, retry_after)

        logger.info("Labels added to #%d: %s", issue_number, labels)
        return success_response(
            {
                "success": True,
                "issue_number": issue_number,
                "labels_added": labels,
            }
        )

    except asyncio.TimeoutError:
        logger.error("Timeout adding labels to #%d", issue_number)
        return error_response("Operation timed out", "TIMEOUT")
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
    issue_number = args["issue_number"]
    comment = args.get("comment")

    # Validate
    if issue_number < 1:
        return error_response("Issue number must be positive", "INVALID_INPUT")

    logger.info("Closing issue #%d (comment=%s)", issue_number, bool(comment))

    cmd_args = ["issue", "close", str(issue_number)]
    if comment:
        cmd_args.extend(["--comment", comment])

    try:
        stdout, stderr, return_code = await run_gh_command(*cmd_args)

        if return_code != 0:
            message, error_code, retry_after = classify_error(stderr, stdout)
            if "not found" in (stderr or stdout).lower():
                message = f"Issue #{issue_number} not found"
                error_code = "NOT_FOUND"
            # Already closed is not an error (idempotent)
            if "already closed" in (stderr or stdout).lower():
                logger.info("Issue #%d was already closed", issue_number)
                return success_response(
                    {
                        "success": True,
                        "issue_number": issue_number,
                        "state": "closed",
                    }
                )
            logger.warning("Close issue failed: %s", message)
            return error_response(message, error_code, retry_after)

        logger.info("Issue #%d closed", issue_number)
        return success_response(
            {
                "success": True,
                "issue_number": issue_number,
                "state": "closed",
            }
        )

    except asyncio.TimeoutError:
        logger.error("Timeout closing issue #%d", issue_number)
        return error_response("Operation timed out", "TIMEOUT")
    except Exception as e:
        logger.exception("Unexpected error closing issue")
        return error_response(str(e), "INTERNAL_ERROR")
