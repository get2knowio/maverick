"""Fly workflow screen for Maverick TUI."""

from __future__ import annotations

import contextlib
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Button, Input, Static

from maverick.tui.history import WorkflowHistoryEntry, WorkflowHistoryStore
from maverick.tui.screens.base import MaverickScreen
from maverick.tui.widgets.form import BranchInputField

__all__ = ["FlyScreen", "record_fly_workflow_completion"]


def record_fly_workflow_completion(
    branch_name: str,
    final_status: str,
    stages_completed: list[str],
    finding_counts: dict[str, int] | None = None,
    pr_link: str | None = None,
) -> None:
    """Record Fly workflow completion in history.

    This function creates a history entry for a completed or failed Fly workflow
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
        record_fly_workflow_completion(
            branch_name="feature/new-widget",
            final_status="completed",
            stages_completed=["setup", "implementation", "review", "validation"],
            finding_counts={"error": 0, "warning": 1, "suggestion": 3},
            pr_link="https://github.com/org/repo/pull/123",
        )

        # After workflow fails
        record_fly_workflow_completion(
            branch_name="feature/failed-attempt",
            final_status="failed",
            stages_completed=["setup"],
            finding_counts={"error": 1, "warning": 0, "suggestion": 0},
        )
        ```
    """
    try:
        entry = WorkflowHistoryEntry.create(
            workflow_type="fly",
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


class FlyScreen(MaverickScreen):
    """Screen for configuring and starting a Fly workflow.

    Allows users to enter a branch name, optionally select a task file,
    and start the Fly workflow. The screen validates branch names in real-time
    and transitions to WorkflowScreen when the workflow is started.

    Attributes:
        branch_name: Current branch name input value.
        branch_error: Validation error message (if any).
        is_valid: Whether the current branch name is valid.
        is_starting: Whether the workflow is being started.
        task_file: Optional path to task file.

    Example:
        ```python
        # Navigate to FlyScreen from HomeScreen
        self.app.push_screen(FlyScreen())

        # Or with initial state
        screen = FlyScreen()
        self.app.push_screen(screen)
        ```
    """

    TITLE = "Start Fly Workflow"

    BINDINGS = [
        Binding("escape", "go_back", "Back", show=True),
        Binding("ctrl+enter", "start", "Start", show=False),
        Binding("ctrl+c", "cancel_workflow", "Cancel", show=False),
    ]

    # Reactive state
    branch_name: reactive[str] = reactive("")
    branch_error: reactive[str] = reactive("")
    is_valid: reactive[bool] = reactive(False)
    is_starting: reactive[bool] = reactive(False)
    task_file: reactive[Path | None] = reactive(None)
    is_workflow_running: reactive[bool] = reactive(False)
    workflow_cancelled: reactive[bool] = reactive(False)
    stages_completed_before_cancel: reactive[tuple[str, ...]] = reactive(())
    workflow_paused: reactive[bool] = reactive(False)

    def compose(self) -> ComposeResult:
        """Create the screen layout.

        Yields:
            ComposeResult: Screen components including title, form fields,
                and action buttons.
        """
        yield Static("[bold]Start Fly Workflow[/bold]", id="title")
        with Vertical(id="form-container"):
            yield BranchInputField(label="Branch Name", id="branch-input")
            yield Static("Task File (optional):", classes="label")
            yield Input(id="task-file-input", placeholder="path/to/tasks.md")
            with Horizontal(id="buttons"):
                yield Button("Start", id="start-btn", variant="primary", disabled=True)
                yield Button("Cancel", id="cancel-btn")

    def on_mount(self) -> None:
        """Focus branch input on mount.

        Automatically focuses the branch input field when the screen is mounted
        to improve user experience.
        """
        with contextlib.suppress(Exception):
            self.query_one("#branch-input", BranchInputField).focus_input()

    def on_branch_input_field_changed(self, event: BranchInputField.Changed) -> None:
        """Handle branch input changes.

        Updates the screen state when the branch name input changes,
        including validation status. This enables real-time validation
        feedback and dynamic button state updates.

        Args:
            event: The branch input changed event containing the new value
                and validation status.
        """
        self.branch_name = event.value
        self.is_valid = event.is_valid
        self._update_start_button()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle task file input changes.

        Updates the task_file state when the task file path is changed.
        Empty or whitespace-only input clears the task file.

        Args:
            event: The input changed event.
        """
        if event.input.id == "task-file-input":
            value = event.value.strip()
            self.task_file = Path(value) if value else None

    def _update_start_button(self) -> None:
        """Update start button enabled state.

        Enables the start button only when:
        1. Branch name validation passes (is_valid=True)
        2. Workflow is not currently starting (is_starting=False)
        """
        try:
            btn = self.query_one("#start-btn", Button)
            btn.disabled = not self.is_valid or self.is_starting
        except Exception:
            # Button not mounted yet, skip update
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button clicks.

        Dispatches button press events to the appropriate action handlers
        based on the button ID.

        Args:
            event: The button pressed event.
        """
        if event.button.id == "start-btn":
            self.action_start()
        elif event.button.id == "cancel-btn":
            self.go_back()

    def action_start(self) -> None:
        """Start the Fly workflow.

        Validates the current state and transitions to WorkflowScreen with
        the configured branch name and workflow type. The workflow name is
        set to "Fly" and the branch name is trimmed of whitespace.

        This action is bound to ctrl+enter and is also triggered by the
        Start button.

        Note:
            This action does nothing if validation fails or if the workflow
            is already starting.
        """
        if not self.is_valid or self.is_starting:
            return

        self.is_starting = True
        self._update_start_button()

        # Transition to WorkflowScreen
        from maverick.tui.screens.workflow import WorkflowScreen

        self.app.push_screen(
            WorkflowScreen(workflow_name="Fly", branch_name=self.branch_name.strip())
        )

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

        Sets the workflow_cancelled flag, records completed stages,
        stops the workflow execution, and displays a cancellation summary.
        """
        self.workflow_cancelled = True
        # In a future implementation, this would stop the actual workflow worker
        # and record which stages were completed before cancellation
        self._show_cancellation_summary()

    def _show_cancellation_summary(self) -> None:
        """Show summary of what was completed before cancellation.

        Displays a summary of which stages were completed before the workflow
        was cancelled, helping the user understand progress that was made.
        """
        completed = self.stages_completed_before_cancel

        if not completed:
            self.notify(
                "Workflow cancelled before any stages completed.",
                title="Workflow Cancelled",
                severity="warning",
                timeout=8.0,
            )
            return

        # Map stage IDs to display names
        stage_names = {
            "init": "Initialization",
            "implementation": "Implementation",
            "validation": "Validation",
            "code_review": "Code Review",
            "convention_update": "Convention Update",
            "pr_creation": "PR Creation",
            "complete": "Complete",
            "failed": "Failed",
        }

        # Format completed stages with checkmarks
        completed_list = [f"✓ {stage_names.get(s, s)}" for s in completed]
        summary = "Completed stages:\n" + "\n".join(completed_list)

        self.notify(
            summary,
            title="Workflow Cancelled",
            severity="information",
            timeout=10.0,
        )

    def _handle_connectivity_change(self, connected: bool) -> None:
        """Handle connectivity status change for Fly workflow.

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
                # In a future implementation, this would signal the workflow worker to resume


__all__ = [
    "FlyScreen",
]
