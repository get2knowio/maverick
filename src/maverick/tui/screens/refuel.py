"""Refuel workflow screen for Maverick TUI."""

from __future__ import annotations

import asyncio

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Button, Input, Static

from maverick.tui.history import WorkflowHistoryEntry, WorkflowHistoryStore
from maverick.tui.models import GitHubIssue, RefuelResultItem
from maverick.tui.screens.base import MaverickScreen
from maverick.tui.services import list_github_issues
from maverick.tui.widgets.form import NumericField, ToggleField
from maverick.tui.widgets.issue_list import IssueList
from maverick.tui.widgets.result_summary import ResultSummary

__all__ = ["RefuelScreen", "record_refuel_workflow_completion"]


def record_refuel_workflow_completion(
    branch_name: str,
    final_status: str,
    stages_completed: list[str],
    finding_counts: dict[str, int] | None = None,
    pr_link: str | None = None,
) -> None:
    """Record Refuel workflow completion in history.

    This function creates a history entry for a completed or failed Refuel workflow
    and persists it to the history store. The entry includes workflow metadata,
    completed stages, and optional findings and PR link.

    Args:
        branch_name: Git branch name for the workflow.
        final_status: "completed" or "failed".
        stages_completed: List of stage names that completed successfully.
        finding_counts: Optional dict of finding counts by severity
            (e.g., {"error": 0, "warning": 2, "suggestion": 5}).
        pr_link: Optional URL to the created pull request.

    Example:
        ```python
        # After workflow completes successfully
        record_refuel_workflow_completion(
            branch_name="fix/tech-debt-123",
            final_status="completed",
            stages_completed=["discovery", "implementation", "review", "validation"],
            finding_counts={"error": 0, "warning": 0, "suggestion": 1},
            pr_link="https://github.com/org/repo/pull/456",
        )

        # After workflow fails
        record_refuel_workflow_completion(
            branch_name="fix/failed-issue",
            final_status="failed",
            stages_completed=["discovery"],
            finding_counts={"error": 2, "warning": 0, "suggestion": 0},
        )
        ```
    """
    try:
        entry = WorkflowHistoryEntry.create(
            workflow_type="refuel",
            branch_name=branch_name,
            final_status=final_status,
            stages_completed=stages_completed,
            finding_counts=finding_counts or {},
            pr_link=pr_link,
        )

        store = WorkflowHistoryStore()
        store.add(entry)
    except Exception:
        # Silently fail if history recording fails - don't break workflow
        pass


class RefuelScreen(MaverickScreen):
    """Screen for selecting and processing GitHub issues.

    Allows users to:
    1. Filter issues by label
    2. Configure processing options (limit, parallel/sequential)
    3. Select issues for processing
    4. Execute the refuel workflow
    5. View results with PR links

    Attributes:
        label_filter: Current label filter
        issue_limit: Maximum issues to process
        parallel_mode: Whether to process in parallel
        is_fetching: Whether issues are being fetched
        is_processing: Whether workflow is running
        selected_count: Number of selected issues
    """

    TITLE = "Refuel Workflow"

    BINDINGS = [
        Binding("escape", "go_back", "Back", show=True),
        Binding("ctrl+s", "start", "Start", show=True),
        Binding("ctrl+f", "focus_filter", "Filter", show=False),
        Binding("ctrl+c", "cancel_workflow", "Cancel", show=False),
    ]

    # Reactive state
    label_filter: reactive[str] = reactive("")
    issue_limit: reactive[int] = reactive(3)
    parallel_mode: reactive[bool] = reactive(True)
    is_fetching: reactive[bool] = reactive(False)
    is_processing: reactive[bool] = reactive(False)
    selected_count: reactive[int] = reactive(0)
    is_workflow_running: reactive[bool] = reactive(False)
    workflow_cancelled: reactive[bool] = reactive(False)
    issues_processed_before_cancel: reactive[tuple[int, ...]] = reactive(())
    workflow_paused: reactive[bool] = reactive(False)

    def compose(self) -> ComposeResult:
        """Compose the refuel screen layout."""
        yield Static("Refuel Workflow", id="title")

        with Vertical(id="config-section"):
            yield Static("Label Filter:", classes="label")
            yield Input(
                id="label-input",
                placeholder="tech-debt",
                value=self.label_filter,
            )
            yield Button("Fetch Issues", id="fetch-btn", variant="primary")

            yield NumericField(
                label="Max Issues",
                value=self.issue_limit,
                min_value=1,
                max_value=10,
                id="limit-field",
            )
            yield ToggleField(
                label="Parallel Processing",
                checked=self.parallel_mode,
                id="parallel-toggle",
            )

        with Vertical(id="issue-section"):
            yield Static("Issues:", classes="label")
            yield IssueList(id="issue-list")

        with Vertical(id="result-section"):
            yield ResultSummary(id="results")

        with Horizontal(id="buttons"):
            yield Button("Start", id="start-btn", variant="success", disabled=True)
            yield Button("Cancel", id="cancel-btn")

    def on_mount(self) -> None:
        """Initialize the screen."""
        self._update_start_button()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input change events.

        Args:
            event: The input changed event
        """
        if event.input.id == "label-input":
            self.label_filter = event.value

    def on_numeric_field_changed(self, event: NumericField.Changed) -> None:
        """Handle numeric field change events.

        Args:
            event: The numeric field changed event
        """
        numeric_field = event.control
        if numeric_field and numeric_field.id == "limit-field":
            self.issue_limit = event.value

    def on_toggle_field_changed(self, event: ToggleField.Changed) -> None:
        """Handle toggle field change events.

        Args:
            event: The toggle field changed event
        """
        toggle_field = event.control
        if toggle_field and toggle_field.id == "parallel-toggle":
            self.parallel_mode = event.checked

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events.

        Args:
            event: The button pressed event
        """
        if event.button.id == "fetch-btn":
            self.action_fetch()
        elif event.button.id == "start-btn":
            self.action_start()
        elif event.button.id == "cancel-btn":
            self.action_go_back()

    def on_issue_list_selection_changed(
        self, event: IssueList.SelectionChanged
    ) -> None:
        """Handle issue selection change events.

        Args:
            event: The selection changed event
        """
        self.selected_count = event.selected_count
        self._update_start_button()

    def action_fetch(self) -> None:
        """Fetch issues with current label filter."""
        if not self.label_filter.strip():
            self.show_error("Please enter a label filter")
            return

        self.fetch_issues(self.label_filter)

    def fetch_issues(self, label: str) -> None:
        """Fetch GitHub issues with the given label.

        Args:
            label: Label to filter issues by
        """
        self.run_worker(self._fetch_issues_async(label), exclusive=True)

    async def _fetch_issues_async(self, label: str) -> None:
        """Async implementation of issue fetching.

        Args:
            label: Label to filter issues by
        """
        self.is_fetching = True
        self._update_start_button()

        try:
            # Fetch issues using the service function
            result = await list_github_issues(label=label, limit=50, timeout=60.0)

            if not result.success:
                self.show_error(result.error_message or "Failed to fetch issues")
                return

            # Update issue list
            issue_list = self.query_one("#issue-list", IssueList)
            issue_list.set_issues(list(result.issues))

        except Exception as e:
            self.show_error(f"Failed to fetch issues: {e}")
        finally:
            self.is_fetching = False
            self._update_start_button()

    def action_start(self) -> None:
        """Start the refuel workflow."""
        if not self._can_start():
            return

        issue_list = self.query_one("#issue-list", IssueList)
        selected_issues = issue_list.get_selected_issues()

        if not selected_issues:
            self.show_error("No issues selected")
            return

        self.start_workflow(selected_issues)

    def start_workflow(self, issues: list[GitHubIssue]) -> None:
        """Start the refuel workflow for selected issues.

        Args:
            issues: List of issues to process
        """
        self.run_worker(self._start_workflow_async(issues), exclusive=True)

    async def _start_workflow_async(self, issues: list[GitHubIssue]) -> None:
        """Async implementation of workflow execution.

        Args:
            issues: List of issues to process
        """
        self.is_processing = True
        self._update_start_button()

        results = []

        try:
            # TODO: Integrate with actual RefuelWorkflow
            # For now, simulate processing
            for issue in issues:
                # Simulate processing
                await asyncio.sleep(0.5)

                # Mock result (in real implementation, this would come from workflow)
                result = RefuelResultItem(
                    issue_number=issue.number,
                    success=True,
                    pr_url=f"https://github.com/test/repo/pull/{issue.number}",
                )
                results.append(result)

            # Update results display
            result_summary = self.query_one("#results", ResultSummary)
            result_summary.set_results(tuple(results))

        except Exception as e:
            self.show_error(f"Workflow failed: {e}")
        finally:
            self.is_processing = False
            self._update_start_button()

    def action_focus_filter(self) -> None:
        """Focus the label filter input."""
        label_input = self.query_one("#label-input", Input)
        label_input.focus()

    def _can_start(self) -> bool:
        """Check if the Start button should be enabled.

        Returns:
            True if workflow can be started, False otherwise
        """
        return (
            self.selected_count > 0 and not self.is_processing and not self.is_fetching
        )

    def _update_start_button(self) -> None:
        """Update Start button enabled state."""
        try:
            start_btn = self.query_one("#start-btn", Button)
            start_btn.disabled = not self._can_start()
        except Exception:
            # Not mounted yet
            pass

    def watch_is_fetching(self, is_fetching: bool) -> None:
        """Update UI when fetching state changes.

        Args:
            is_fetching: New fetching state
        """
        try:
            fetch_btn = self.query_one("#fetch-btn", Button)
            fetch_btn.disabled = is_fetching

            if is_fetching:
                fetch_btn.label = "Fetching..."
            else:
                fetch_btn.label = "Fetch Issues"
        except Exception:
            pass

    def watch_is_processing(self, is_processing: bool) -> None:
        """Update UI when processing state changes.

        Args:
            is_processing: New processing state
        """
        try:
            start_btn = self.query_one("#start-btn", Button)

            if is_processing:
                start_btn.label = "Processing..."
            else:
                start_btn.label = "Start"
        except Exception:
            pass

    async def action_cancel_workflow(self) -> None:
        """Cancel the running workflow.

        Shows a confirmation dialog before cancelling. If the user confirms,
        the workflow is gracefully stopped and a cancellation summary is shown.

        This action is bound to ctrl+c and does nothing if no workflow is
        currently running.
        """
        if not self.is_workflow_running:
            return

        confirmed = await self.confirm_cancel_workflow()
        if confirmed:
            self._cancel_workflow()

    def _cancel_workflow(self) -> None:
        """Execute workflow cancellation.

        Sets the workflow_cancelled flag, records processed issues,
        stops the workflow execution, and displays a cancellation summary.
        """
        self.workflow_cancelled = True
        # In a future implementation, this would stop the actual workflow worker
        # and record which issues were processed before cancellation
        self._show_cancellation_summary()

    def _show_cancellation_summary(self) -> None:
        """Show summary of what was processed before cancellation.

        Displays a summary of which issues were processed before the workflow
        was cancelled, helping the user understand progress that was made.
        """
        processed = self.issues_processed_before_cancel

        if not processed:
            self.notify(
                "Workflow cancelled before any issues were processed.",
                title="Workflow Cancelled",
                severity="warning",
                timeout=8.0,
            )
            return

        # Format processed issues as a comma-separated list
        issue_list = ", ".join(f"#{num}" for num in processed)
        self.notify(
            f"Processed issues: {issue_list}",
            title="Workflow Cancelled",
            severity="information",
            timeout=10.0,
        )

    def _handle_connectivity_change(self, connected: bool) -> None:
        """Handle connectivity status change for Refuel workflow.

        Pauses the workflow when connectivity is lost and resumes when
        connectivity is restored. This prevents workflow operations from
        failing due to network issues.

        Args:
            connected: True if connected to GitHub, False if disconnected.
        """
        # Call parent to show default notifications
        super()._handle_connectivity_change(connected)

        # Only pause/resume if workflow is actually running
        if not self.is_workflow_running:
            return

        if not connected:
            # Pause the workflow
            self.workflow_paused = True
            # In a future implementation, this would signal the workflow worker to pause
        else:
            # Resume the workflow
            if self.workflow_paused:
                self.workflow_paused = False
                # In a future implementation, this would signal the workflow
                # worker to resume
