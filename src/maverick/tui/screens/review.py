from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.widgets import Static

from maverick.tui.models import FixResult, ReviewAction, ReviewScreenActionState
from maverick.tui.screens.base import MaverickScreen

if TYPE_CHECKING:
    pass


class ReviewScreen(MaverickScreen):
    """Code review results screen.

    Displays organized review findings with severity indicators and
    navigation between issues. Supports review actions: approve, request
    changes, dismiss, and fix all.
    """

    TITLE = "Review"

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back", show=True),
        Binding("n", "next_issue", "Next Issue", show=True),
        Binding("p", "prev_issue", "Prev Issue", show=True),
        Binding("e", "filter_errors", "Errors Only", show=False),
        Binding("w", "filter_warnings", "Warnings Only", show=False),
        Binding("ctrl+a", "filter_all", "Show All", show=False),
        Binding("a", "approve", "Approve", show=True),
        Binding("r", "request_changes", "Request Changes", show=True),
        Binding("d", "dismiss", "Dismiss", show=True),
        Binding("f", "fix_all", "Fix All", show=True),
    ]

    # Reactive state for action handling
    action_state: reactive[ReviewScreenActionState] = reactive(
        ReviewScreenActionState()
    )
    has_new_findings: reactive[bool] = reactive(False)

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Initialize the review screen."""
        super().__init__(name=name, id=id, classes=classes)
        self._issues: list[dict[str, object]] = []
        self._selected_index: int = 0
        self._filter_severity: str | None = None

    def compose(self) -> ComposeResult:
        """Create the review screen layout.

        Yields:
            ComposeResult: Review results display with issue list and detail view.
        """
        yield Static("[bold]Code Review Results[/bold]", id="review-title")

        with Horizontal():
            # Left panel: Issue list
            with VerticalScroll(classes="issue-list", id="issue-list"):
                yield Static(
                    "[dim]No issues loaded[/dim]",
                    id="issue-list-placeholder",
                )

            # Right panel: Issue detail view
            with Vertical(classes="issue-detail", id="issue-detail"):
                yield Static(
                    (
                        "[bold]Issue Details[/bold]\n\n"
                        "[dim]Select an issue to view details[/dim]"
                    ),
                    id="issue-detail-content",
                )

    def load_issues(self, issues: list[dict[str, object]]) -> None:
        """Load review issues for display.

        Args:
            issues: List of issue dictionaries with file_path, line_number,
                   severity, message, and source fields.
        """
        self._issues = issues
        self._selected_index = 0 if issues else -1
        self._update_issue_list()
        if issues:
            self._update_detail_view()

    def filter_by_severity(self, severity: str | None) -> None:
        """Filter displayed issues by severity.

        Args:
            severity: Severity to filter ("error", "warning", "info",
                     "suggestion") or None for all issues.
        """
        self._filter_severity = severity
        self._selected_index = 0
        self._update_issue_list()
        filtered_issues = self._get_filtered_issues()
        if filtered_issues:
            self._update_detail_view()
        else:
            self._clear_detail_view()

    def navigate_to_issue(self, index: int) -> None:
        """Navigate to a specific issue.

        Args:
            index: Index of the issue in the filtered list.
        """
        filtered_issues = self._get_filtered_issues()
        if 0 <= index < len(filtered_issues):
            self._selected_index = index
            self._update_issue_list()
            self._update_detail_view()

    def action_next_issue(self) -> None:
        """Navigate to next issue."""
        filtered_issues = self._get_filtered_issues()
        if filtered_issues and self._selected_index < len(filtered_issues) - 1:
            self._selected_index += 1
            self._update_issue_list()
            self._update_detail_view()

    def action_prev_issue(self) -> None:
        """Navigate to previous issue."""
        if self._selected_index > 0:
            self._selected_index -= 1
            self._update_issue_list()
            self._update_detail_view()

    def action_filter_errors(self) -> None:
        """Filter to show only errors."""
        self.filter_by_severity("error")

    def action_filter_warnings(self) -> None:
        """Filter to show only warnings."""
        self.filter_by_severity("warning")

    def action_filter_all(self) -> None:
        """Show all issues."""
        self.filter_by_severity(None)

    def _get_filtered_issues(self) -> list[dict[str, object]]:
        """Get issues filtered by current severity filter.

        Returns:
            List of filtered issues.
        """
        if self._filter_severity is None:
            return self._issues
        return [
            issue
            for issue in self._issues
            if issue.get("severity") == self._filter_severity
        ]

    def _update_issue_list(self) -> None:
        """Update the issue list display."""
        issue_list = self.query_one("#issue-list", VerticalScroll)

        # Remove all children
        issue_list.remove_children()

        filtered_issues = self._get_filtered_issues()

        if not filtered_issues:
            placeholder_text = "[dim]No issues"
            if self._filter_severity:
                placeholder_text += f" with severity '{self._filter_severity}'"
            placeholder_text += "[/dim]"
            issue_list.mount(Static(placeholder_text, id="issue-list-placeholder"))
            return

        # Add issue items
        for idx, issue in enumerate(filtered_issues):
            issue_widget = self._create_issue_item(issue, idx)
            issue_list.mount(issue_widget)

    def _create_issue_item(self, issue: dict[str, object], index: int) -> Static:
        """Create a widget for an issue item.

        Args:
            issue: Issue dictionary.
            index: Index in the filtered list.

        Returns:
            Static widget displaying the issue summary.
        """
        severity = issue.get("severity", "info")
        file_path = issue.get("file_path", "unknown")
        line_number = issue.get("line_number", 0)
        message = issue.get("message", "")

        # Truncate message for list view
        msg_str = str(message)
        message_preview = msg_str if len(msg_str) <= 60 else f"{msg_str[:60]}..."

        # Create severity indicator with color
        severity_class = f"severity-{severity}"
        severity_icon = self._get_severity_icon(severity)

        content = (
            f"[{severity_class}]{severity_icon} {severity.upper()}[/{severity_class}] "
            f"[dim]{file_path}:{line_number}[/dim]\n"
            f"  {message_preview}"
        )

        classes = "issue-item"
        if index == self._selected_index:
            classes += " --selected"

        return Static(content, classes=classes, id=f"issue-item-{index}")

    def _get_severity_icon(self, severity: str) -> str:
        """Get icon for severity level.

        Args:
            severity: Severity level.

        Returns:
            Unicode icon character.
        """
        icons = {
            "error": "✗",
            "warning": "⚠",
            "info": "ℹ",
            "suggestion": "💡",
        }
        return icons.get(severity, "○")

    def _update_detail_view(self) -> None:
        """Update the detail view with the currently selected issue."""
        filtered_issues = self._get_filtered_issues()

        if not filtered_issues or self._selected_index >= len(filtered_issues):
            self._clear_detail_view()
            return

        issue = filtered_issues[self._selected_index]

        severity = issue.get("severity", "info")
        file_path = issue.get("file_path", "unknown")
        line_number = issue.get("line_number", 0)
        message = issue.get("message", "")
        source = issue.get("source", "unknown")

        severity_class = f"severity-{severity}"
        severity_icon = self._get_severity_icon(severity)

        # Build detailed content
        content_lines = [
            f"[bold]Issue {self._selected_index + 1} of {len(filtered_issues)}[/bold]",
            "",
            f"[{severity_class}]{severity_icon} {severity.upper()}[/{severity_class}]",
            "",
            f"[bold]Location:[/bold] {file_path}:{line_number}",
            f"[bold]Source:[/bold] {source}",
            "",
            "[bold]Message:[/bold]",
            f"{message}",
        ]

        content = "\n".join(content_lines)

        detail_widget = self.query_one("#issue-detail-content", Static)
        detail_widget.update(content)

    def _clear_detail_view(self) -> None:
        """Clear the detail view."""
        detail_widget = self.query_one("#issue-detail-content", Static)
        detail_widget.update(
            "[bold]Issue Details[/bold]\n\n[dim]No issue selected[/dim]"
        )

    # =========================================================================
    # Review Action Methods (T033-T042a)
    # =========================================================================

    async def action_approve(self) -> None:
        """Approve the review with confirmation.

        Shows a confirmation dialog before submitting the approval.
        """
        confirmed = await self.confirm(
            "Approve Review", "Are you sure you want to approve this review?"
        )
        if confirmed:
            self._submit_approval()

    async def action_request_changes(self) -> None:
        """Request changes with comment input.

        Prompts user for a comment explaining what changes are needed,
        then submits the request changes action.
        """
        comment = await self.prompt_input("Request Changes", "Enter your comments:")
        if comment:
            self._submit_request_changes(comment)

    def action_dismiss(self) -> None:
        """Dismiss the currently selected finding.

        Removes the selected issue from the view. If this is the last
        issue in the filtered list, clears the detail view.
        """
        if not self._issues or self._selected_index < 0:
            return

        filtered_issues = self._get_filtered_issues()
        if not filtered_issues or self._selected_index >= len(filtered_issues):
            return

        # Find the selected issue in the full list and remove it
        selected_issue = filtered_issues[self._selected_index]
        try:
            full_index = self._issues.index(selected_issue)
            self._issues.pop(full_index)
        except (ValueError, IndexError):
            return

        # Update selection index
        if len(self._issues) == 0:
            self._selected_index = -1
            self._update_issue_list()
            self._clear_detail_view()
        else:
            # Keep same index if possible, else move to previous
            new_filtered = self._get_filtered_issues()
            if self._selected_index >= len(new_filtered):
                self._selected_index = max(0, len(new_filtered) - 1)
            self._update_issue_list()
            if new_filtered:
                self._update_detail_view()
            else:
                self._clear_detail_view()

        # Log the dismiss action
        self._log_action(ReviewAction.DISMISS)

    async def action_fix_all(self) -> None:
        """Trigger automatic fix for all findings.

        Shows confirmation dialog, then attempts to automatically fix
        all issues using the IssueFixerAgent. Displays results after
        completion.
        """
        if not self._issues:
            return

        confirmed = await self.confirm(
            "Fix All Findings",
            "This will attempt to automatically fix all findings. Continue?",
        )
        if confirmed:
            await self._execute_fix_all()

    def _submit_approval(self) -> None:
        """Submit approval for the review.

        Updates action state to indicate approval is in progress and
        logs the action.
        """
        # Update state to show approval in progress
        self.action_state = ReviewScreenActionState(is_approving=True)

        # Log the action
        self._log_action(ReviewAction.APPROVE)

        # TODO: Integrate with GitHub PR review API
        # When implemented, update state to is_approving=False after completion

    def _submit_request_changes(self, comment: str) -> None:
        """Submit request changes action with comment.

        Args:
            comment: User's comment explaining required changes.
        """
        # Update state with comment
        self.action_state = ReviewScreenActionState(request_changes_comment=comment)

        # Log the action
        self._log_action(ReviewAction.REQUEST_CHANGES)

        # TODO: Integrate with GitHub PR review API
        # For now, just store the comment

    async def _execute_fix_all(self) -> None:
        """Execute fix all action.

        Attempts to automatically fix each finding using the IssueFixerAgent.
        Updates action state with results for each finding.
        """
        # Update action state to show fixing in progress
        self.action_state = ReviewScreenActionState(is_fixing=True)

        # TODO: Call IssueFixerAgent for each finding
        # For now, simulate results
        results: list[FixResult] = []
        for issue in self._issues:
            issue_id = str(issue.get("id", "unknown"))
            # Placeholder: simulate success for demonstration
            results.append(FixResult(finding_id=issue_id, success=True))

        # Update state with results
        self.action_state = ReviewScreenActionState(
            is_fixing=False, fix_results=tuple(results)
        )

        # Log the action
        self._log_action(ReviewAction.FIX_ALL)

    def _log_action(self, action: ReviewAction) -> None:
        """Log a review action.

        Args:
            action: The review action being performed.
        """
        # Update action state to reflect pending action
        current_state = self.action_state
        self.action_state = ReviewScreenActionState(
            pending_action=action,
            request_changes_comment=current_state.request_changes_comment,
            fix_results=current_state.fix_results,
            is_approving=current_state.is_approving,
            is_fixing=current_state.is_fixing,
        )

    def refresh_findings(self) -> None:
        """Refresh findings from the review source.

        Checks for new findings and updates the has_new_findings banner
        flag if new issues are available.
        """
        new_findings = self._fetch_new_findings()

        if new_findings:
            self.has_new_findings = True
        else:
            self.has_new_findings = False

        self._update_issue_list()

    def _fetch_new_findings(self) -> list[dict[str, object]]:
        """Fetch new findings from the review source.

        Returns:
            List of new finding dictionaries. Empty list if no new findings.

        Note:
            This is a placeholder implementation. In a production system,
            this would poll the review service (e.g., CodeRabbit API) for
            new findings.
        """
        # TODO: Integrate with actual review service polling
        # For now, return empty list
        return []
