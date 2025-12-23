"""Helper utilities for the Refuel Workflow.

This module provides conversion functions and small utilities used by the
refuel workflow.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from maverick.workflows.refuel.models import GitHubIssue

if TYPE_CHECKING:
    from maverick.runners.models import GitHubIssue as RunnerGitHubIssue

__all__ = [
    "convert_runner_issue_to_workflow_issue",
]


def convert_runner_issue_to_workflow_issue(
    runner_issue: RunnerGitHubIssue,
) -> GitHubIssue:
    """Convert runner GitHubIssue to workflow GitHubIssue.

    Args:
        runner_issue: GitHubIssue from the runner module.

    Returns:
        GitHubIssue instance for use in the workflow.
    """
    return GitHubIssue(
        number=runner_issue.number,
        title=runner_issue.title,
        body=runner_issue.body,
        labels=list(runner_issue.labels),
        assignee=runner_issue.assignees[0] if runner_issue.assignees else None,
        url=runner_issue.url,
    )
