"""Workflow execution screen for running and monitoring workflows.

This screen executes a workflow using the DSL executor and displays
real-time progress updates for each step.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING, Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import ScrollableContainer, Vertical
from textual.reactive import reactive
from textual.widgets import Button, ProgressBar, Static
from textual.worker import Worker, WorkerState

from maverick.logging import get_logger
from maverick.tui.screens.base import MaverickScreen

if TYPE_CHECKING:
    from maverick.dsl.results import WorkflowResult
    from maverick.dsl.serialization.schema import WorkflowFile


# Step type icons
STEP_TYPE_ICONS = {
    "python": "\u2699",  # gear
    "agent": "\U0001f916",  # robot
    "generate": "\u270d",  # writing hand
    "validate": "\u2713",  # checkmark
    "checkpoint": "\U0001f4be",  # floppy disk
    "subworkflow": "\U0001f500",  # shuffle
    "branch": "\U0001f500",  # shuffle
    "loop": "\U0001f501",  # repeat
}

# Status icons
STATUS_ICONS = {
    "pending": "\u25cb",  # empty circle
    "running": "\u25cf",  # filled circle (will be animated)
    "completed": "\u2713",  # checkmark
    "failed": "\u2717",  # X mark
    "skipped": "\u2014",  # em dash
}

# Module logger
logger = get_logger(__name__)


class StepWidget(Static):
    """Widget to display a single workflow step with status."""

    def __init__(
        self,
        step_name: str,
        step_type: str,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Initialize the step widget.

        Args:
            step_name: Name of the workflow step.
            step_type: Type of the step (python, agent, etc.).
            name: Widget name.
            id: Widget ID.
            classes: CSS classes.
        """
        super().__init__(name=name, id=id, classes=classes)
        self._step_name = step_name
        self._step_type = step_type
        self._status = "pending"
        self._duration_ms: int | None = None
        self._error: str | None = None
        self._update_display()

    def _update_display(self) -> None:
        """Update the displayed content based on status."""
        type_icon = STEP_TYPE_ICONS.get(self._step_type, "?")
        status_icon = STATUS_ICONS.get(self._status, "?")

        # Build status color
        if self._status == "running":
            status_class = "step-running"
            status_icon = "\u25cf"  # Will animate in CSS
        elif self._status == "completed":
            status_class = "step-completed"
        elif self._status == "failed":
            status_class = "step-failed"
        elif self._status == "skipped":
            status_class = "step-skipped"
        else:
            status_class = "step-pending"

        # Build duration string
        duration_str = ""
        if self._duration_ms is not None:
            if self._duration_ms >= 60000:
                minutes = self._duration_ms // 60000
                seconds = (self._duration_ms % 60000) // 1000
                duration_str = f" ({minutes}m {seconds}s)"
            elif self._duration_ms >= 1000:
                duration_str = f" ({self._duration_ms / 1000:.1f}s)"
            else:
                duration_str = f" ({self._duration_ms}ms)"

        # Error indicator
        error_str = ""
        if self._error:
            error_str = f"\n  [red]{self._error}[/red]"

        self.update(
            f"[{status_class}]{status_icon}[/{status_class}] "
            f"{type_icon} {self._step_name}{duration_str}{error_str}"
        )

    def set_running(self) -> None:
        """Mark the step as running."""
        self._status = "running"
        self._update_display()

    def set_completed(self, duration_ms: int) -> None:
        """Mark the step as completed.

        Args:
            duration_ms: Duration in milliseconds.
        """
        self._status = "completed"
        self._duration_ms = duration_ms
        self._update_display()

    def set_failed(self, duration_ms: int, error: str | None = None) -> None:
        """Mark the step as failed.

        Args:
            duration_ms: Duration in milliseconds.
            error: Error message.
        """
        self._status = "failed"
        self._duration_ms = duration_ms
        self._error = error
        self._update_display()

    def set_skipped(self) -> None:
        """Mark the step as skipped."""
        self._status = "skipped"
        self._update_display()


class WorkflowExecutionScreen(MaverickScreen):
    """Execute workflow and display real-time progress.

    This screen runs a workflow using WorkflowFileExecutor and displays
    step-by-step progress with status indicators and timing information.
    """

    TITLE = "Running Workflow"

    BINDINGS = [
        Binding("escape", "cancel_workflow", "Cancel", show=True),
        Binding("q", "go_home", "Home", show=False),
    ]

    # Reactive state
    is_running: reactive[bool] = reactive(False)
    is_complete: reactive[bool] = reactive(False)
    current_step: reactive[int] = reactive(0)
    total_steps: reactive[int] = reactive(0)
    success: reactive[bool | None] = reactive(None)

    def __init__(
        self,
        workflow: WorkflowFile,
        inputs: dict[str, Any],
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Initialize the workflow execution screen.

        Args:
            workflow: The workflow to execute.
            inputs: Input values for the workflow.
            name: Widget name.
            id: Widget ID.
            classes: CSS classes.
        """
        super().__init__(name=name, id=id, classes=classes)
        self._workflow = workflow
        self._inputs = inputs
        self._step_widgets: dict[str, StepWidget] = {}
        self._cancel_requested = False
        self._executor_worker: Worker[WorkflowResult] | None = None
        self._result: WorkflowResult | None = None
        self._start_time: datetime | None = None

    def compose(self) -> ComposeResult:
        """Create the execution screen layout."""
        yield Static(
            f"[bold]Workflow: {self._workflow.name}[/bold]",
            id="execution-title",
        )
        yield Static(
            self._workflow.description or "",
            id="execution-description",
        )

        # Progress indicator
        yield Static(
            "[dim]Preparing...[/dim]",
            id="progress-text",
        )
        yield ProgressBar(id="progress-bar", total=100, show_eta=False)

        # Step list
        with ScrollableContainer(id="step-list"):
            for step in self._workflow.steps:
                step_type_str = (
                    step.type.value if hasattr(step.type, "value") else str(step.type)
                )
                step_widget = StepWidget(
                    step_name=step.name,
                    step_type=step_type_str,
                    id=f"step-{step.name}",
                    classes="step-item",
                )
                self._step_widgets[step.name] = step_widget
                yield step_widget

        # Status bar
        with Vertical(id="status-bar"):
            yield Static("", id="status-message")
            yield Static("", id="elapsed-time")

        # Error display
        yield Static("", id="error-display")

        # Action buttons (hidden during execution)
        with Vertical(id="completion-buttons", classes="hidden"):
            yield Button("Back to Home", id="home-btn", variant="primary")

    def on_mount(self) -> None:
        """Start workflow execution when mounted."""
        super().on_mount()
        self.total_steps = len(self._workflow.steps)
        self._start_time = datetime.now()

        # Start elapsed time timer
        self.set_interval(1.0, self._update_elapsed_time)

        # Start workflow execution
        self._start_execution()

    def _start_execution(self) -> None:
        """Start the workflow execution in a background worker."""
        self.is_running = True
        self._executor_worker = self.run_worker(
            self._execute_workflow(),
            name="workflow_executor",
            exclusive=True,
        )

    async def _execute_workflow(self) -> WorkflowResult:
        """Execute the workflow and handle events.

        Returns:
            The workflow result.
        """
        from maverick.cli.common import create_registered_registry
        from maverick.dsl.events import (
            StepCompleted,
            StepStarted,
            ValidationCompleted,
            ValidationFailed,
            ValidationStarted,
            WorkflowCompleted,
            WorkflowStarted,
        )
        from maverick.dsl.serialization import WorkflowFileExecutor

        registry = create_registered_registry()
        executor = WorkflowFileExecutor(registry=registry)

        try:
            async for event in executor.execute(self._workflow, self._inputs):
                if self._cancel_requested:
                    break

                # Handle events
                if isinstance(event, ValidationStarted):
                    self._update_status("Validating workflow...")

                elif isinstance(event, ValidationCompleted):
                    warnings = event.warnings_count
                    if warnings > 0:
                        self._update_status(f"Validation passed ({warnings} warnings)")
                    else:
                        self._update_status("Validation passed")

                elif isinstance(event, ValidationFailed):
                    self._update_status("Validation failed")
                    error_msg = "\n".join(event.errors)
                    self._show_error(error_msg)

                elif isinstance(event, WorkflowStarted):
                    self._update_status(f"Running {event.workflow_name}...")

                elif isinstance(event, StepStarted):
                    self.current_step += 1
                    self._update_progress()
                    self._mark_step_running(event.step_name)

                elif isinstance(event, StepCompleted):
                    if event.success:
                        self._mark_step_completed(event.step_name, event.duration_ms)
                    else:
                        self._mark_step_failed(event.step_name, event.duration_ms)

                elif isinstance(event, WorkflowCompleted):
                    self.success = event.success
                    self.is_complete = True
                    self.is_running = False
                    self._show_completion(event.success, event.total_duration_ms)

            return executor.get_result()

        except asyncio.CancelledError:
            self._update_status("Workflow cancelled")
            self.is_running = False
            self.is_complete = True
            self.success = False
            raise

        except Exception as e:
            logger.error(
                "workflow_execution_failed",
                workflow_name=self._workflow.name,
                error=str(e),
                error_type=type(e).__name__,
            )
            self._show_error(str(e))
            self.is_running = False
            self.is_complete = True
            self.success = False
            raise

    def _update_status(self, message: str) -> None:
        """Update the status message.

        Args:
            message: Status message to display.
        """
        status_widget = self.query_one("#status-message", Static)
        status_widget.update(message)

    def _update_progress(self) -> None:
        """Update the progress display."""
        progress_text = self.query_one("#progress-text", Static)
        progress_bar = self.query_one("#progress-bar", ProgressBar)

        if self.total_steps > 0:
            percent = self.current_step / self.total_steps * 100
        else:
            percent = 0.0
        progress_text.update(f"[{self.current_step}/{self.total_steps}] {percent:.0f}%")
        progress_bar.update(progress=percent)

    def _mark_step_running(self, step_name: str) -> None:
        """Mark a step as running."""
        if step_name in self._step_widgets:
            self._step_widgets[step_name].set_running()

    def _mark_step_completed(self, step_name: str, duration_ms: int) -> None:
        """Mark a step as completed."""
        if step_name in self._step_widgets:
            self._step_widgets[step_name].set_completed(duration_ms)

    def _mark_step_failed(
        self, step_name: str, duration_ms: int, error: str | None = None
    ) -> None:
        """Mark a step as failed."""
        if step_name in self._step_widgets:
            self._step_widgets[step_name].set_failed(duration_ms, error)

    def _show_error(self, error: str) -> None:
        """Show an error message."""
        error_widget = self.query_one("#error-display", Static)
        error_widget.update(f"[red]{error}[/red]")

    def _show_completion(self, success: bool, total_duration_ms: int) -> None:
        """Show completion status."""
        # Update progress to 100%
        progress_text = self.query_one("#progress-text", Static)
        progress_bar = self.query_one("#progress-bar", ProgressBar)

        duration_sec = total_duration_ms / 1000
        if success:
            msg = f"[green]\u2713 Completed[/green] ({duration_sec:.1f}s)"
        else:
            msg = f"[red]\u2717 Failed[/red] ({duration_sec:.1f}s)"
        progress_text.update(msg)

        progress_bar.update(progress=100)

        # Show completion buttons
        buttons = self.query_one("#completion-buttons", Vertical)
        buttons.remove_class("hidden")

    def _update_elapsed_time(self) -> None:
        """Update the elapsed time display."""
        if self._start_time is None:
            return

        elapsed = datetime.now() - self._start_time
        total_seconds = int(elapsed.total_seconds())
        minutes = total_seconds // 60
        seconds = total_seconds % 60

        elapsed_widget = self.query_one("#elapsed-time", Static)
        elapsed_widget.update(f"[dim]Elapsed: {minutes:02d}:{seconds:02d}[/dim]")

    def action_cancel_workflow(self) -> None:
        """Request workflow cancellation."""
        if not self.is_running:
            # If not running, go back
            self.app.pop_screen()
            return

        self._cancel_requested = True
        self._update_status("Cancelling...")

        if self._executor_worker is not None:
            self._executor_worker.cancel()

    def action_go_home(self) -> None:
        """Navigate back to home screen."""
        # Pop all workflow screens to get back to home
        while len(self.app.screen_stack) > 1:
            self.app.pop_screen()

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """Handle worker state changes."""
        if event.worker.name == "workflow_executor":
            if event.state == WorkerState.SUCCESS:
                self._result = event.worker.result
            elif event.state == WorkerState.CANCELLED:
                self.is_running = False
                self.is_complete = True
                self.success = False
                self._update_status("Workflow cancelled")
                self._show_completion(False, 0)
            elif event.state == WorkerState.ERROR:
                self.is_running = False
                self.is_complete = True
                self.success = False
                if event.worker.error:
                    self._show_error(str(event.worker.error))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "home-btn":
            self.action_go_home()
