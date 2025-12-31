from __future__ import annotations

from dataclasses import dataclass

from maverick.tui.models.enums import CheckStatus, PRState


@dataclass(frozen=True, slots=True)
class StatusCheck:
    """A CI/CD status check on a PR.

    Attributes:
        name: Name of the check (e.g., "CI / build").
        status: Current status.
        url: Link to the check details.
    """

    name: str
    status: CheckStatus
    url: str | None = None


@dataclass(frozen=True, slots=True)
class PRInfo:
    """Pull request metadata.

    Attributes:
        number: PR number.
        title: PR title.
        description: Full PR description/body.
        state: Open, merged, or closed.
        url: URL to the PR on GitHub.
        checks: Status checks on the PR.
        branch: Source branch name.
        base_branch: Target branch name.
    """

    number: int
    title: str
    description: str
    state: PRState
    url: str
    checks: tuple[StatusCheck, ...] = ()
    branch: str = ""
    base_branch: str = "main"

    @property
    def description_preview(self) -> str:
        """Get truncated description for preview."""
        max_length = 200
        if len(self.description) <= max_length:
            return self.description
        return self.description[:max_length].rsplit(" ", 1)[0] + "..."


@dataclass(frozen=True, slots=True)
class GitHubIssue:
    """GitHub issue for selection.

    Attributes:
        number: Issue number.
        title: Issue title.
        labels: Issue labels.
        url: URL to the issue.
        state: str = "open"
    """

    number: int
    title: str
    labels: tuple[str, ...]
    url: str
    state: str = "open"

    @property
    def display_labels(self) -> str:
        """Formatted labels for display."""
        return ", ".join(self.labels) if self.labels else "No labels"


@dataclass(frozen=True, slots=True)
class IssueSelectionItem:
    """Issue with selection state.

    Attributes:
        issue: The GitHub issue.
        selected: Whether this issue is selected for processing.
    """

    issue: GitHubIssue
    selected: bool = False
