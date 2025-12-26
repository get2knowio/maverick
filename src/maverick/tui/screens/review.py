from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.widgets import Static

from maverick.agents.issue_fixer import IssueFixerAgent
from maverick.logging import get_logger
from maverick.models.issue_fix import IssueFixerContext
from maverick.tui.models import FixResult, ReviewAction, ReviewScreenActionState
from maverick.tui.screens.base import MaverickScreen
from maverick.tui.widgets import DiffPanel

if TYPE_CHECKING:
    from textual.timer import Timer

logger = get_logger(__name__)

__all__ = ["ReviewScreen"]


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
        Binding("c", "request_changes", "Request Changes", show=True),
        Binding("d", "dismiss", "Dismiss", show=True),
        Binding("f", "fix_all", "Fix All", show=True),
        Binding("r", "refresh_findings", "Refresh", show=True),
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
        self._poll_timer: Timer | None = None
        self._findings_hash: str = ""

    def compose(self) -> ComposeResult:
        """Create the review screen layout.

        Yields:
            ComposeResult: Review results display with issue list, detail view,
                          and diff panel.
        """
        yield Static("[bold]Code Review Results[/bold]", id="review-title")

        # New findings banner (initially hidden)
        yield Static(
            (
                "[yellow]⚠ New findings available[/yellow] "
                "[dim]Press [bold]r[/bold] to refresh[/dim]"
            ),
            id="new-findings-banner",
            classes="hidden",
        )

        with Horizontal(id="review-main-container"):
            # Left panel: Issue list
            with VerticalScroll(classes="issue-list", id="issue-list"):
                yield Static(
                    "[dim]No issues loaded[/dim]",
                    id="issue-list-placeholder",
                )

            # Middle panel: Issue detail view
            with Vertical(classes="issue-detail", id="issue-detail"):
                yield Static(
                    (
                        "[bold]Issue Details[/bold]\n\n"
                        "[dim]Select an issue to view details[/dim]"
                    ),
                    id="issue-detail-content",
                )

            # Right panel: Diff panel
            yield DiffPanel(id="diff-panel")

    def on_mount(self) -> None:
        """Start polling timer when screen is mounted."""
        # Start polling every 30 seconds
        self._poll_timer = self.set_interval(30.0, self._check_for_new_findings)
        # Calculate initial hash
        self._findings_hash = self._compute_findings_hash()

    def on_unmount(self) -> None:
        """Stop polling timer when screen is unmounted."""
        if self._poll_timer:
            self._poll_timer.stop()
            self._poll_timer = None

    def watch_has_new_findings(self, value: bool) -> None:
        """Show or hide the new findings banner when has_new_findings changes.

        Args:
            value: True if new findings are available, False otherwise.
        """
        try:
            banner = self.query_one("#new-findings-banner", Static)
            if value:
                banner.remove_class("hidden")
            else:
                banner.add_class("hidden")
        except Exception:
            # Banner widget not yet mounted or already removed
            pass

    def load_issues(self, issues: list[dict[str, object]]) -> None:
        """Load review issues for display.

        Args:
            issues: List of issue dictionaries with file_path, line_number,
                   severity, message, and source fields.
        """
        self._issues = issues
        self._selected_index = 0 if issues else -1
        self._findings_hash = self._compute_findings_hash()
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

    def action_refresh_findings(self) -> None:
        """Refresh findings from the review source.

        Manually triggers a refresh of findings and clears the new findings banner.
        This method reloads the current findings while preserving the selection.
        """
        # Store the current selected index
        current_index = self._selected_index

        # Fetch new findings
        self.refresh_findings()

        # Clear the banner since we've refreshed
        self.has_new_findings = False

        # Restore selection if still valid
        filtered = self._get_filtered_issues()
        if filtered and current_index >= 0:
            if current_index < len(filtered):
                self._selected_index = current_index
            else:
                self._selected_index = len(filtered) - 1
            self._update_detail_view()

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
        """Update the issue list display with grouped severities."""
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

        # Group issues by severity
        severity_order = ["error", "warning", "suggestion", "info"]
        grouped: dict[str, list[dict[str, object]]] = {s: [] for s in severity_order}

        for issue in filtered_issues:
            severity = str(issue.get("severity", "info")).lower()
            if severity in grouped:
                grouped[severity].append(issue)
            else:
                # Fallback to info for unknown severities
                grouped["info"].append(issue)

        # Track global index across all groups
        global_index = 0

        # Add grouped issue items with headers
        for severity in severity_order:
            issues_in_group = grouped[severity]
            if not issues_in_group:
                continue

            # Add severity group header
            severity_icon = self._get_severity_icon(severity)
            severity_class = f"severity-{severity}"
            header_text = (
                f"[{severity_class} bold]"
                f"{severity_icon} {severity.upper()} ({len(issues_in_group)})"
                f"[/{severity_class} bold]"
            )
            header_widget = Static(
                header_text, classes="severity-header", id=f"severity-header-{severity}"
            )
            issue_list.mount(header_widget)

            # Add issues in this severity group
            for issue in issues_in_group:
                issue_widget = self._create_issue_item(issue, global_index)
                issue_list.mount(issue_widget)
                global_index += 1

    def _create_issue_item(self, issue: dict[str, object], index: int) -> Static:
        """Create a widget for an issue item.

        Args:
            issue: Issue dictionary.
            index: Index in the filtered list.

        Returns:
            Static widget displaying the issue summary.
        """
        severity_raw = issue.get("severity", "info")
        severity = str(severity_raw)
        file_path = str(issue.get("file_path", "unknown"))
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

        severity_raw = issue.get("severity", "info")
        severity = str(severity_raw)
        file_path = str(issue.get("file_path", "unknown"))
        line_number_raw = issue.get("line_number", 0)
        # Ensure line_number is int or str
        line_number: int | str = (
            int(line_number_raw) if isinstance(line_number_raw, (int, str)) else 0
        )
        message = str(issue.get("message", ""))
        source = str(issue.get("source", "unknown"))

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

        # Update the diff panel with file content
        self._update_diff_panel(file_path, line_number)

    def _clear_detail_view(self) -> None:
        """Clear the detail view and diff panel."""
        detail_widget = self.query_one("#issue-detail-content", Static)
        detail_widget.update(
            "[bold]Issue Details[/bold]\n\n[dim]No issue selected[/dim]"
        )

        # Clear the diff panel
        try:
            diff_panel = self.query_one("#diff-panel", DiffPanel)
            diff_panel.update_diff()
        except Exception:
            pass

    def _update_diff_panel(self, file_path: str, line_number: int | str) -> None:
        """Update the diff panel with the file content for the selected issue.

        Args:
            file_path: Path to the file containing the issue.
            line_number: Line number of the issue (can be int or str).
        """
        try:
            # Convert line_number to int if it's a string
            if isinstance(line_number, str):
                try:
                    line_num = int(line_number)
                except ValueError:
                    line_num = 0
            else:
                line_num = int(line_number) if line_number else 0

            # Update the diff panel
            diff_panel = self.query_one("#diff-panel", DiffPanel)
            diff_panel.update_diff(
                file_path=file_path,
                line_number=line_num,
                working_directory=Path.cwd(),
            )
        except Exception as e:
            logger.warning("Failed to update diff panel: %s", e)

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

    async def action_dismiss(self, result: None = None) -> None:
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

        # Execute IssueFixerAgent for each finding sequentially to avoid git conflicts
        results: list[FixResult] = []

        for idx, finding in enumerate(self._issues, start=1):
            finding_id = str(finding.get("id", f"finding-{idx}"))

            try:
                # Log progress
                logger.info(
                    "Fixing finding %d/%d: %s",
                    idx,
                    len(self._issues),
                    finding.get("message", "Unknown issue"),
                )

                # Create IssueFixerAgent
                agent = IssueFixerAgent()

                # Construct synthetic IssueFixerContext for this finding
                # Use a synthetic issue number (1000000 + idx) to satisfy validation
                synthetic_number = 1000000 + idx

                # Build issue data from finding
                file_path = finding.get("file_path", "unknown")
                line_number = finding.get("line_number", 0)
                message = finding.get("message", "")
                source = finding.get("source", "")
                severity = finding.get("severity", "")

                issue_data = {
                    "number": synthetic_number,
                    "title": f"Fix {severity} finding in {file_path}",
                    "body": (
                        f"**Message:** {message}\n\n"
                        f"**Location:** {file_path}:{line_number}\n\n"
                        f"**Source:** {source}\n\n"
                        f"**Code:**\n```\n{source}\n```"
                    ),
                    "labels": [],
                }

                context = IssueFixerContext(
                    issue_data=issue_data,
                    cwd=Path.cwd(),
                    skip_validation=True,  # Skip validation for review findings
                    dry_run=False,
                )

                # Execute the agent
                agent_result = await agent.execute(context)

                # Convert agent FixResult to TUI FixResult
                if agent_result.success:
                    results.append(FixResult(finding_id=finding_id, success=True))
                    logger.info("Successfully fixed finding %s", finding_id)
                else:
                    error_msg = (
                        "; ".join(agent_result.errors)
                        if agent_result.errors
                        else "Unknown error"
                    )
                    results.append(
                        FixResult(
                            finding_id=finding_id,
                            success=False,
                            error_message=error_msg,
                        )
                    )
                    logger.warning(
                        "Failed to fix finding %s: %s", finding_id, error_msg
                    )

            except Exception as e:
                # Handle any errors during fixing
                error_msg = f"Error fixing finding: {e}"
                logger.exception("Error executing fix for finding %s", finding_id)
                results.append(
                    FixResult(
                        finding_id=finding_id,
                        success=False,
                        error_message=error_msg,
                    )
                )

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

    def _compute_findings_hash(self) -> str:
        """Compute a hash of the current findings for change detection.

        Returns:
            SHA256 hash of the findings data.
        """
        import hashlib
        import json

        # Create a stable representation of findings for hashing
        # Sort by file_path and line_number for consistent ordering
        def _sort_key(x: dict[str, object]) -> tuple[str, int]:
            file_path = str(x.get("file_path", ""))
            line_num_val = x.get("line_number", 0)
            line_num = int(line_num_val) if isinstance(line_num_val, (int, str)) else 0
            return (file_path, line_num)

        sorted_issues = sorted(self._issues, key=_sort_key)

        # Create a JSON representation of key fields
        findings_data = [
            {
                "file_path": issue.get("file_path"),
                "line_number": issue.get("line_number"),
                "severity": issue.get("severity"),
                "message": issue.get("message"),
                "source": issue.get("source"),
            }
            for issue in sorted_issues
        ]

        # Compute hash
        findings_json = json.dumps(findings_data, sort_keys=True)
        return hashlib.sha256(findings_json.encode()).hexdigest()

    async def _check_for_new_findings(self) -> None:
        """Poll for new findings and update banner if changes detected.

        This method is called periodically by the polling timer to check
        if new findings have been added to the review.
        """
        # Fetch new findings from the source
        new_findings = self._fetch_new_findings()

        # If no new findings returned, nothing to check
        if not new_findings:
            return

        # Compute hash of new findings
        # Temporarily store current issues
        original_issues = self._issues
        original_hash = self._findings_hash

        # Set new issues to compute their hash
        self._issues = new_findings
        new_hash = self._compute_findings_hash()

        # Restore original issues
        self._issues = original_issues

        # If hashes differ, we have new findings
        if new_hash != original_hash:
            self.has_new_findings = True
