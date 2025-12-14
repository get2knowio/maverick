"""GitHub MCP tools for Maverick agents.

This module provides MCP tools for GitHub operations using the gh CLI.
Tools are async functions decorated with @tool that return MCP-formatted responses.

Usage:
    from maverick.tools.github import create_github_tools_server

    server = create_github_tools_server()  # Raises GitHubToolsError if prerequisites not met
    agent = MaverickAgent(mcp_servers={"github-tools": server})
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

from maverick.exceptions import GitHubToolsError

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

#: Default timeout for GitHub CLI operations in seconds
DEFAULT_TIMEOUT: float = 30.0

#: Default max diff size in bytes (100KB)
DEFAULT_MAX_DIFF_SIZE: int = 102400

#: MCP Server configuration
SERVER_NAME: str = "github-tools"
SERVER_VERSION: str = "1.0.0"


# =============================================================================
# Helper Functions (T005-T007)
# =============================================================================


async def _run_gh_command(
    *args: str,
    cwd: Path | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> tuple[str, str, int]:
    """Run a gh CLI command asynchronously.

    Args:
        *args: gh command arguments (without 'gh' prefix).
        cwd: Working directory for the command.
        timeout: Timeout in seconds.

    Returns:
        Tuple of (stdout, stderr, return_code).

    Raises:
        asyncio.TimeoutError: If command times out.
    """
    process = await asyncio.create_subprocess_exec(
        "gh",
        *args,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        raise

    stdout = stdout_bytes.decode().strip()
    stderr = stderr_bytes.decode().strip()
    return_code = process.returncode or 0

    return stdout, stderr, return_code


def _parse_rate_limit_wait(stderr: str) -> int | None:
    """Parse rate limit wait time from error message (T006).

    Args:
        stderr: Standard error output from gh command.

    Returns:
        Seconds to wait, or None if not a rate limit error.
    """
    patterns = [
        r"retry after (\d+)",
        r"wait (\d+)\s*s",
        r"(\d+)\s*seconds",
    ]

    stderr_lower = stderr.lower()
    if "rate limit" not in stderr_lower:
        return None

    for pattern in patterns:
        match = re.search(pattern, stderr_lower)
        if match:
            return int(match.group(1))

    # Default wait time if rate limited but no specific time given
    return 60


def _success_response(data: dict[str, Any]) -> dict[str, Any]:
    """Create MCP success response (T007).

    Args:
        data: Response data to JSON-serialize.

    Returns:
        MCP-formatted success response.
    """
    return {"content": [{"type": "text", "text": json.dumps(data)}]}


def _error_response(
    message: str,
    error_code: str,
    retry_after_seconds: int | None = None,
) -> dict[str, Any]:
    """Create MCP error response (T007).

    Args:
        message: Human-readable error message.
        error_code: Machine-readable error code.
        retry_after_seconds: Seconds to wait (for rate limits).

    Returns:
        MCP-formatted error response.
    """
    error_data: dict[str, Any] = {
        "isError": True,
        "message": message,
        "error_code": error_code,
    }
    if retry_after_seconds is not None:
        error_data["retry_after_seconds"] = retry_after_seconds
    return {"content": [{"type": "text", "text": json.dumps(error_data)}]}


def _classify_error(stderr: str, stdout: str = "") -> tuple[str, str, int | None]:
    """Classify gh CLI error and return (message, error_code, retry_after).

    Args:
        stderr: Standard error output.
        stdout: Standard output (sometimes contains error info).

    Returns:
        Tuple of (message, error_code, retry_after_seconds).
    """
    error_text = (stderr or stdout).lower()

    if "not found" in error_text or "could not find" in error_text:
        return stderr or stdout or "Resource not found", "NOT_FOUND", None

    if "rate limit" in error_text:
        retry_after = _parse_rate_limit_wait(stderr or stdout)
        msg = f"GitHub API rate limit exceeded. Retry after {retry_after} seconds"
        return msg, "RATE_LIMIT", retry_after

    if "authentication" in error_text or "unauthorized" in error_text:
        return "GitHub CLI not authenticated. Run: gh auth login", "AUTH_ERROR", None

    if "network" in error_text or "connection" in error_text:
        return f"Network error: {stderr or stdout}", "NETWORK_ERROR", None

    if "timeout" in error_text:
        return f"Operation timed out: {stderr or stdout}", "TIMEOUT", None

    # Generic error
    return stderr or stdout or "Unknown error", "INTERNAL_ERROR", None


# =============================================================================
# Prerequisite Verification (T004)
# =============================================================================


async def _verify_prerequisites(cwd: Path | None = None) -> None:
    """Verify gh CLI and git repo prerequisites (T004).

    Args:
        cwd: Working directory to check.

    Raises:
        GitHubToolsError: If any prerequisite check fails.
    """
    working_dir = cwd or Path.cwd()

    # Check 1: gh CLI installed
    try:
        process = await asyncio.create_subprocess_exec(
            "gh",
            "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(process.communicate(), timeout=5.0)
        if process.returncode != 0:
            raise GitHubToolsError(
                "GitHub CLI (gh) not installed. Install: https://cli.github.com/",
                check_failed="gh_installed",
            )
    except FileNotFoundError:
        raise GitHubToolsError(
            "GitHub CLI (gh) not installed. Install: https://cli.github.com/",
            check_failed="gh_installed",
        )
    except asyncio.TimeoutError:
        raise GitHubToolsError(
            "GitHub CLI check timed out",
            check_failed="gh_installed",
        )

    # Check 2: gh CLI authenticated
    stdout, stderr, return_code = await _run_gh_command(
        "auth",
        "status",
        cwd=working_dir,
        timeout=10.0,
    )
    if return_code != 0:
        raise GitHubToolsError(
            "GitHub CLI not authenticated. Run: gh auth login",
            check_failed="gh_authenticated",
        )

    # Check 3: Inside git repository
    try:
        process = await asyncio.create_subprocess_exec(
            "git",
            "rev-parse",
            "--git-dir",
            cwd=working_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(process.communicate(), timeout=5.0)
        if process.returncode != 0:
            raise GitHubToolsError(
                "Not inside a git repository",
                check_failed="git_repo",
            )
    except FileNotFoundError:
        raise GitHubToolsError(
            "Git not installed",
            check_failed="git_installed",
        )
    except asyncio.TimeoutError:
        raise GitHubToolsError(
            "Git check timed out",
            check_failed="git_repo",
        )

    # Check 4: Has remote configured
    try:
        process = await asyncio.create_subprocess_exec(
            "git",
            "remote",
            "get-url",
            "origin",
            cwd=working_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(process.communicate(), timeout=5.0)
        if process.returncode != 0:
            raise GitHubToolsError(
                "No git remote 'origin' configured",
                check_failed="git_remote",
            )
    except asyncio.TimeoutError:
        raise GitHubToolsError(
            "Git remote check timed out",
            check_failed="git_remote",
        )

    logger.debug("GitHub tools prerequisites verified successfully")


# =============================================================================
# Tool Implementations (Phase 3-8)
# =============================================================================


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

    logger.info("Creating PR: %s (head=%s -> base=%s, draft=%s)", title, head, base, draft)

    cmd_args = ["pr", "create", "--title", title, "--body", body, "--base", base, "--head", head]
    if draft:
        cmd_args.append("--draft")

    try:
        stdout, stderr, return_code = await _run_gh_command(*cmd_args)

        if return_code != 0:
            message, error_code, retry_after = _classify_error(stderr, stdout)
            # Check for branch-specific errors
            if "head" in stderr.lower() and "not found" in stderr.lower():
                message = f"Branch '{head}' not found"
                error_code = "BRANCH_NOT_FOUND"
            elif "base" in stderr.lower() and "not found" in stderr.lower():
                message = f"Branch '{base}' not found"
                error_code = "BRANCH_NOT_FOUND"
            logger.warning("PR creation failed: %s", message)
            return _error_response(message, error_code, retry_after)

        # Parse PR URL to extract number
        pr_url = stdout.strip()
        pr_number = int(pr_url.rstrip("/").split("/")[-1])

        logger.info("PR #%d created: %s", pr_number, pr_url)
        return _success_response({
            "pr_number": pr_number,
            "url": pr_url,
            "state": "draft" if draft else "open",
            "title": title,
        })

    except asyncio.TimeoutError:
        logger.error("PR creation timed out")
        return _error_response("Operation timed out", "TIMEOUT")
    except Exception as e:
        logger.exception("Unexpected error creating PR")
        return _error_response(str(e), "INTERNAL_ERROR")


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
        return _error_response(
            f"Invalid state '{state}'. Must be 'open', 'closed', or 'all'",
            "INVALID_INPUT",
        )

    # Validate limit
    if limit < 1:
        return _error_response("Limit must be positive", "INVALID_INPUT")

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
        stdout, stderr, return_code = await _run_gh_command(*cmd_args)

        if return_code != 0:
            message, error_code, retry_after = _classify_error(stderr, stdout)
            logger.warning("Issue list failed: %s", message)
            return _error_response(message, error_code, retry_after)

        issues_data = json.loads(stdout) if stdout else []
        # Transform labels from objects to strings
        issues = []
        for issue in issues_data:
            issues.append({
                "number": issue["number"],
                "title": issue["title"],
                "labels": [lbl["name"] if isinstance(lbl, dict) else lbl for lbl in issue.get("labels", [])],
                "state": issue["state"],
                "url": issue["url"],
            })

        logger.info("Found %d issues", len(issues))
        return _success_response({"issues": issues})

    except json.JSONDecodeError as e:
        logger.error("Failed to parse issue list: %s", e)
        return _error_response(f"Failed to parse response: {e}", "INTERNAL_ERROR")
    except asyncio.TimeoutError:
        logger.error("Issue list timed out")
        return _error_response("Operation timed out", "TIMEOUT")
    except Exception as e:
        logger.exception("Unexpected error listing issues")
        return _error_response(str(e), "INTERNAL_ERROR")


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
        return _error_response("Issue number must be positive", "INVALID_INPUT")

    logger.info("Getting issue #%d", issue_number)

    fields = "number,title,body,url,state,labels,assignees,author,comments,createdAt,updatedAt"
    cmd_args = ["issue", "view", str(issue_number), "--json", fields]

    try:
        stdout, stderr, return_code = await _run_gh_command(*cmd_args)

        if return_code != 0:
            message, error_code, retry_after = _classify_error(stderr, stdout)
            if "not found" in (stderr or stdout).lower():
                message = f"Issue #{issue_number} not found"
                error_code = "NOT_FOUND"
            logger.warning("Get issue failed: %s", message)
            return _error_response(message, error_code, retry_after)

        data = json.loads(stdout)
        issue = {
            "number": data["number"],
            "title": data["title"],
            "body": data.get("body", ""),
            "url": data["url"],
            "state": data["state"],
            "labels": [lbl["name"] if isinstance(lbl, dict) else lbl for lbl in data.get("labels", [])],
            "assignees": [a["login"] if isinstance(a, dict) else a for a in data.get("assignees", [])],
            "author": data.get("author", {}).get("login", "") if isinstance(data.get("author"), dict) else str(data.get("author", "")),
            "comments_count": len(data.get("comments", [])),
            "created_at": data.get("createdAt", ""),
            "updated_at": data.get("updatedAt", ""),
        }

        logger.info("Retrieved issue #%d: %s", issue_number, issue["title"])
        return _success_response(issue)

    except json.JSONDecodeError as e:
        logger.error("Failed to parse issue: %s", e)
        return _error_response(f"Failed to parse response: {e}", "INTERNAL_ERROR")
    except asyncio.TimeoutError:
        logger.error("Get issue timed out")
        return _error_response("Operation timed out", "TIMEOUT")
    except Exception as e:
        logger.exception("Unexpected error getting issue")
        return _error_response(str(e), "INTERNAL_ERROR")


@tool(
    "github_get_pr_diff",
    "Get the diff content for a pull request",
    {"pr_number": int, "max_size": int},
)
async def github_get_pr_diff(args: dict[str, Any]) -> dict[str, Any]:
    """Get PR diff with truncation (T034-T036)."""
    pr_number = args["pr_number"]
    max_size = args.get("max_size", DEFAULT_MAX_DIFF_SIZE)

    # Validate
    if pr_number < 1:
        return _error_response("PR number must be positive", "INVALID_INPUT")
    if max_size < 1:
        return _error_response("Max size must be positive", "INVALID_INPUT")

    logger.info("Getting diff for PR #%d (max_size=%d)", pr_number, max_size)

    cmd_args = ["pr", "diff", str(pr_number)]

    try:
        stdout, stderr, return_code = await _run_gh_command(*cmd_args)

        if return_code != 0:
            message, error_code, retry_after = _classify_error(stderr, stdout)
            if "not found" in (stderr or stdout).lower():
                message = f"PR #{pr_number} not found"
                error_code = "NOT_FOUND"
            logger.warning("Get PR diff failed: %s", message)
            return _error_response(message, error_code, retry_after)

        diff = stdout
        original_size = len(diff.encode("utf-8"))
        truncated = original_size > max_size

        if truncated:
            # Truncate at byte boundary (approximate)
            diff = diff[:max_size]
            logger.info("Diff truncated from %d to %d bytes", original_size, max_size)
            return _success_response({
                "diff": diff,
                "truncated": True,
                "warning": f"Diff truncated at {max_size // 1024}KB",
                "original_size_bytes": original_size,
            })

        logger.info("Retrieved diff for PR #%d (%d bytes)", pr_number, original_size)
        return _success_response({"diff": diff, "truncated": False})

    except asyncio.TimeoutError:
        logger.error("Get PR diff timed out")
        return _error_response("Operation timed out", "TIMEOUT")
    except Exception as e:
        logger.exception("Unexpected error getting PR diff")
        return _error_response(str(e), "INTERNAL_ERROR")


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
        return _error_response("PR number must be positive", "INVALID_INPUT")

    logger.info("Getting status for PR #%d", pr_number)

    fields = "number,state,mergeable,mergeStateStatus,reviews,statusCheckRollup,headRefName,baseRefName"
    cmd_args = ["pr", "view", str(pr_number), "--json", fields]

    try:
        stdout, stderr, return_code = await _run_gh_command(*cmd_args)

        if return_code != 0:
            message, error_code, retry_after = _classify_error(stderr, stdout)
            if "not found" in (stderr or stdout).lower():
                message = f"PR #{pr_number} not found"
                error_code = "NOT_FOUND"
            logger.warning("Get PR status failed: %s", message)
            return _error_response(message, error_code, retry_after)

        data = json.loads(stdout)

        # Parse reviews
        reviews = []
        for review in data.get("reviews", []):
            if isinstance(review, dict):
                author = review.get("author", {})
                reviews.append({
                    "author": author.get("login", "") if isinstance(author, dict) else str(author),
                    "state": review.get("state", "PENDING"),
                })

        # Parse checks
        checks = []
        rollup = data.get("statusCheckRollup", []) or []
        for check in rollup:
            if isinstance(check, dict):
                checks.append({
                    "name": check.get("name", check.get("context", "unknown")),
                    "status": check.get("status", "queued").lower(),
                    "conclusion": check.get("conclusion"),
                })

        # Determine merge state
        mergeable_raw = data.get("mergeable")
        merge_state = data.get("mergeStateStatus", "unknown")
        if isinstance(merge_state, str):
            merge_state = merge_state.lower()

        # Convert mergeable to boolean (API returns "MERGEABLE", "CONFLICTING", "UNKNOWN", or null)
        if mergeable_raw in (True, "MERGEABLE"):
            mergeable = True
        elif mergeable_raw in (False, "CONFLICTING"):
            mergeable = False
        else:
            mergeable = None  # UNKNOWN or null

        # Detect conflicts
        has_conflicts = merge_state in ("dirty", "conflicting") or mergeable_raw == "CONFLICTING"

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
        return _success_response(status)

    except json.JSONDecodeError as e:
        logger.error("Failed to parse PR status: %s", e)
        return _error_response(f"Failed to parse response: {e}", "INTERNAL_ERROR")
    except asyncio.TimeoutError:
        logger.error("Get PR status timed out")
        return _error_response("Operation timed out", "TIMEOUT")
    except Exception as e:
        logger.exception("Unexpected error getting PR status")
        return _error_response(str(e), "INTERNAL_ERROR")


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
        return _error_response("Issue number must be positive", "INVALID_INPUT")
    if not labels:
        return _error_response("Labels list cannot be empty", "INVALID_INPUT")

    logger.info("Adding labels to #%d: %s", issue_number, labels)

    cmd_args = ["issue", "edit", str(issue_number)]
    for label in labels:
        cmd_args.extend(["--add-label", str(label)])

    try:
        stdout, stderr, return_code = await _run_gh_command(*cmd_args)

        if return_code != 0:
            message, error_code, retry_after = _classify_error(stderr, stdout)
            if "not found" in (stderr or stdout).lower():
                message = f"Issue #{issue_number} not found"
                error_code = "NOT_FOUND"
            logger.warning("Add labels failed: %s", message)
            return _error_response(message, error_code, retry_after)

        logger.info("Labels added to #%d: %s", issue_number, labels)
        return _success_response({
            "success": True,
            "issue_number": issue_number,
            "labels_added": labels,
        })

    except asyncio.TimeoutError:
        logger.error("Add labels timed out")
        return _error_response("Operation timed out", "TIMEOUT")
    except Exception as e:
        logger.exception("Unexpected error adding labels")
        return _error_response(str(e), "INTERNAL_ERROR")


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
        return _error_response("Issue number must be positive", "INVALID_INPUT")

    logger.info("Closing issue #%d (comment=%s)", issue_number, bool(comment))

    cmd_args = ["issue", "close", str(issue_number)]
    if comment:
        cmd_args.extend(["--comment", comment])

    try:
        stdout, stderr, return_code = await _run_gh_command(*cmd_args)

        if return_code != 0:
            message, error_code, retry_after = _classify_error(stderr, stdout)
            if "not found" in (stderr or stdout).lower():
                message = f"Issue #{issue_number} not found"
                error_code = "NOT_FOUND"
            # Already closed is not an error (idempotent)
            if "already closed" in (stderr or stdout).lower():
                logger.info("Issue #%d was already closed", issue_number)
                return _success_response({
                    "success": True,
                    "issue_number": issue_number,
                    "state": "closed",
                })
            logger.warning("Close issue failed: %s", message)
            return _error_response(message, error_code, retry_after)

        logger.info("Issue #%d closed", issue_number)
        return _success_response({
            "success": True,
            "issue_number": issue_number,
            "state": "closed",
        })

    except asyncio.TimeoutError:
        logger.error("Close issue timed out")
        return _error_response("Operation timed out", "TIMEOUT")
    except Exception as e:
        logger.exception("Unexpected error closing issue")
        return _error_response(str(e), "INTERNAL_ERROR")


# =============================================================================
# Factory Function (T008)
# =============================================================================


def create_github_tools_server(
    cwd: Path | None = None,
    skip_verification: bool = False,
) -> Any:
    """Create MCP server with all GitHub tools registered (T008).

    This factory function creates an MCP server instance with all 7 GitHub
    tools registered. By default, it verifies prerequisites (gh CLI installed,
    authenticated, in git repo) before creating the server.

    Args:
        cwd: Working directory for prerequisite checks. Defaults to cwd.
        skip_verification: Skip prerequisite checks (for testing).

    Returns:
        Configured MCP server instance.

    Raises:
        GitHubToolsError: If prerequisites not met (unless skip_verification=True).

    Example:
        ```python
        from maverick.tools.github import create_github_tools_server

        server = create_github_tools_server()
        agent = MaverickAgent(
            mcp_servers={"github-tools": server},
            allowed_tools=["mcp__github-tools__github_create_pr"],
        )
        ```
    """
    # Verify prerequisites (fail fast)
    if not skip_verification:
        import asyncio

        try:
            asyncio.get_event_loop().run_until_complete(_verify_prerequisites(cwd))
        except RuntimeError:
            # No event loop running - create one
            asyncio.run(_verify_prerequisites(cwd))

    logger.info("Creating GitHub tools MCP server (version %s)", SERVER_VERSION)

    # Create and return MCP server with all tools
    server = create_sdk_mcp_server(
        name=SERVER_NAME,
        version=SERVER_VERSION,
        tools=[
            github_create_pr,
            github_list_issues,
            github_get_issue,
            github_get_pr_diff,
            github_pr_status,
            github_add_labels,
            github_close_issue,
        ],
    )

    return server
