"""Service functions for Maverick TUI.

This module provides service functions that encapsulate external system interactions
for the TUI layer. The TUI should only call these services rather than executing
subprocess commands directly. This maintains separation of concerns and allows
for proper testing.

Services provided:
- GitHub authentication checking
- Issue listing and fetching
- Notification delivery

All services are async and return typed results, following the pattern established
by the runners module.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from typing import Literal

from maverick.runners.command import CommandRunner
from maverick.tui.models import GitHubIssue

__all__ = [
    "GitHubConnectionResult",
    "NotificationResult",
    "IssueListResult",
    "check_github_connection",
    "list_github_issues",
    "send_test_notification",
]


# =============================================================================
# Result Types
# =============================================================================


@dataclass(frozen=True, slots=True)
class GitHubConnectionResult:
    """Result of GitHub connection check.

    Attributes:
        connected: True if authenticated and connected.
        message: Status message for display.
        status: Status category for UI styling.
    """

    connected: bool
    message: str
    status: Literal["success", "error", "timeout"]


@dataclass(frozen=True, slots=True)
class NotificationResult:
    """Result of notification delivery test.

    Attributes:
        sent: True if notification was sent successfully.
        message: Status message for display.
        status: Status category for UI styling.
    """

    sent: bool
    message: str
    status: Literal["success", "error", "timeout", "disabled"]


@dataclass(frozen=True, slots=True)
class IssueListResult:
    """Result of issue list operation.

    Attributes:
        issues: List of fetched issues (empty on error).
        success: True if fetch succeeded.
        error_message: Error message if fetch failed.
    """

    issues: tuple[GitHubIssue, ...]
    success: bool
    error_message: str | None = None


# =============================================================================
# Service Functions
# =============================================================================


async def check_github_connection(
    timeout: float = 30.0,
) -> GitHubConnectionResult:
    """Check GitHub CLI authentication status.

    Runs `gh auth status` to verify authentication.

    Args:
        timeout: Timeout in seconds for the operation.

    Returns:
        GitHubConnectionResult with connection status and message.
    """
    # Check if gh CLI is available
    if shutil.which("gh") is None:
        return GitHubConnectionResult(
            connected=False,
            message="✗ GitHub CLI (gh) not found",
            status="error",
        )

    runner = CommandRunner(timeout=timeout)

    try:
        result = await runner.run(["gh", "auth", "status"])

        if result.timed_out:
            return GitHubConnectionResult(
                connected=False,
                message="✗ Connection timed out",
                status="timeout",
            )

        if result.success:
            return GitHubConnectionResult(
                connected=True,
                message="✓ Connected",
                status="success",
            )

        # Extract error message from stderr
        error_msg = result.stderr.strip() if result.stderr else "Connection failed"
        return GitHubConnectionResult(
            connected=False,
            message=f"✗ {error_msg}",
            status="error",
        )

    except Exception as e:
        return GitHubConnectionResult(
            connected=False,
            message=f"✗ Error: {e}",
            status="error",
        )


async def send_test_notification(
    topic: str,
    message: str = "Test notification from Maverick",
    timeout: float = 30.0,
) -> NotificationResult:
    """Send a test notification via ntfy.

    Args:
        topic: The ntfy topic to send to.
        message: The notification message.
        timeout: Timeout in seconds for the operation.

    Returns:
        NotificationResult with delivery status and message.
    """
    # Check if curl is available
    if shutil.which("curl") is None:
        return NotificationResult(
            sent=False,
            message="✗ curl not found",
            status="error",
        )

    runner = CommandRunner(timeout=timeout)

    try:
        result = await runner.run(["curl", "-d", message, f"https://ntfy.sh/{topic}"])

        if result.timed_out:
            return NotificationResult(
                sent=False,
                message="✗ Notification timed out",
                status="timeout",
            )

        if result.success:
            return NotificationResult(
                sent=True,
                message="✓ Test notification sent",
                status="success",
            )

        return NotificationResult(
            sent=False,
            message="✗ Failed to send notification",
            status="error",
        )

    except Exception as e:
        return NotificationResult(
            sent=False,
            message=f"✗ Error: {e}",
            status="error",
        )


async def list_github_issues(
    label: str,
    limit: int = 50,
    timeout: float = 60.0,
) -> IssueListResult:
    """List GitHub issues with the given label.

    Args:
        label: Label to filter issues by.
        limit: Maximum number of issues to return.
        timeout: Timeout in seconds for the operation.

    Returns:
        IssueListResult with fetched issues or error message.
    """
    import json

    # Check if gh CLI is available
    if shutil.which("gh") is None:
        return IssueListResult(
            issues=(),
            success=False,
            error_message="GitHub CLI (gh) not found",
        )

    runner = CommandRunner(timeout=timeout)

    try:
        result = await runner.run(
            [
                "gh",
                "issue",
                "list",
                "-l",
                label,
                "--json",
                "number,title,labels,url,state",
                "--limit",
                str(limit),
            ]
        )

        if result.timed_out:
            return IssueListResult(
                issues=(),
                success=False,
                error_message="GitHub CLI timed out",
            )

        if not result.success:
            error_msg = result.stderr if result.stderr else "Failed to fetch issues"
            return IssueListResult(
                issues=(),
                success=False,
                error_message=f"GitHub CLI error: {error_msg}",
            )

        # Parse JSON response
        issues_data = json.loads(result.stdout)

        # Convert to GitHubIssue objects
        issues = []
        for issue_data in issues_data:
            label_list = issue_data.get("labels", [])
            labels = tuple(label_obj["name"] for label_obj in label_list)
            issue = GitHubIssue(
                number=issue_data["number"],
                title=issue_data["title"],
                labels=labels,
                url=issue_data["url"],
                state=issue_data.get("state", "open"),
            )
            issues.append(issue)

        return IssueListResult(
            issues=tuple(issues),
            success=True,
            error_message=None,
        )

    except json.JSONDecodeError as e:
        return IssueListResult(
            issues=(),
            success=False,
            error_message=f"Failed to parse issue data: {e}",
        )
    except Exception as e:
        return IssueListResult(
            issues=(),
            success=False,
            error_message=f"Failed to fetch issues: {e}",
        )
