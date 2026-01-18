"""Workflow execution screen for running and monitoring workflows.

This screen executes a workflow using the DSL executor and displays
real-time progress updates for each step.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.css.query import NoMatches
from textual.reactive import reactive
from textual.widgets import Button, ProgressBar, Static
from textual.worker import Worker, WorkerState

from maverick.logging import get_logger
from maverick.tui.models.enums import IterationStatus, StreamChunkType
from maverick.tui.models.widget_state import (
    AgentStreamEntry,
    LoopIterationItem,
    LoopIterationState,
    StreamingPanelState,
)
from maverick.tui.screens.base import MaverickScreen
from maverick.tui.step_durations import ETACalculator, StepDurationStore
from maverick.tui.widgets.agent_streaming_panel import AgentStreamingPanel
from maverick.tui.widgets.iteration_progress import IterationProgress
from maverick.tui.widgets.timeline import ProgressTimeline, TimelineStep

if TYPE_CHECKING:
    from maverick.dsl.events import (
        AgentStreamChunk,
        LoopIterationCompleted,
        LoopIterationStarted,
    )
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

# Debounce interval for UI updates (50ms per SC-003)
DEBOUNCE_INTERVAL_SECONDS = 0.050


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
        Binding("s", "toggle_streaming_panel", "Toggle streaming", show=True),
        Binding("l", "toggle_log_panel", "Toggle logs", show=True),
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
        self._loop_states: dict[str, LoopIterationState] = {}
        self._cancel_requested = False
        self._executor_worker: Worker[WorkflowResult] | None = None
        self._result: WorkflowResult | None = None
        self._start_time: datetime | None = None
        # T030/T033: Initialize streaming state with visible=True by default
        # T036: Streaming entries persist after workflow completion for debugging.
        # This state is never cleared during the workflow lifecycle, allowing users
        # to scroll back and review agent output after completion or failure.
        self._streaming_state = StreamingPanelState(visible=True)

        # T042: Debounce tracking for UI updates (50ms minimum per SC-003)
        self._last_iteration_update: float = 0.0
        self._last_streaming_update: float = 0.0
        self._pending_iteration_update: asyncio.Task[None] | None = None
        self._pending_streaming_update: asyncio.Task[None] | None = None
        self._pending_iteration_step: str | None = None
        # Track which streaming entries have been displayed
        self._last_displayed_entry_index: int = 0

        # Sprint 2: ETA tracking and step duration history
        self._duration_store = StepDurationStore()
        self._eta_calculator = ETACalculator(
            store=self._duration_store,
            workflow_name=workflow.name,
        )
        self._step_start_times: dict[str, datetime] = {}
        self._completed_steps: set[str] = set()
        self._current_running_step: str | None = None

    def compose(self) -> ComposeResult:
        """Create the execution screen layout with split-view.

        Layout:
            ┌────────────────────────────┬────────────────────────────────────┐
            │ Steps (40%)                │ Agent Output (60%)                 │
            │ ─────                      │ ────────────                       │
            │ ✓ validate      (1.2s)     │ [implementer] Analyzing task...    │
            │ ● implement     (running)  │ > Reading src/maverick/cli/...     │
            │ ○ review                   │ > Applying changes...              │
            └────────────────────────────┴────────────────────────────────────┘
        """
        # Header with workflow info and progress
        yield Static(
            f"[bold]Workflow: {self._workflow.name}[/bold]",
            id="execution-title",
        )
        yield Static(
            self._workflow.description or "",
            id="execution-description",
        )

        # Progress indicator with ETA
        with Horizontal(id="progress-header"):
            yield Static(
                "[dim]Preparing...[/dim]",
                id="progress-text",
            )
            yield Static(
                "",
                id="eta-display",
            )
        yield ProgressBar(id="progress-bar", total=100, show_eta=False)

        # Progress timeline showing step durations
        yield ProgressTimeline(
            show_labels=True,
            show_durations=True,
            id="progress-timeline",
        )

        # Split-view: Steps (left) | Agent Output (right)
        with Horizontal(id="execution-split"):
            # Left pane: Steps list
            with Vertical(id="execution-steps", classes="execution-pane"):
                yield Static("[bold]Steps[/bold]", classes="pane-header")
                with ScrollableContainer(id="step-list"):
                    for step in self._workflow.steps:
                        step_type_str = (
                            step.type.value
                            if hasattr(step.type, "value")
                            else str(step.type)
                        )
                        step_widget = StepWidget(
                            step_name=step.name,
                            step_type=step_type_str,
                            id=f"step-{step.name}",
                            classes="step-item",
                        )
                        self._step_widgets[step.name] = step_widget
                        yield step_widget

            # Right pane: Agent streaming output (always visible)
            with Vertical(id="execution-output", classes="execution-pane"):
                yield Static("[bold]Agent Output[/bold]", classes="pane-header")
                yield AgentStreamingPanel(
                    self._streaming_state,
                    id="streaming-panel",
                )

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

        # Initialize the progress timeline with workflow steps
        self._initialize_timeline()

        # Start elapsed time timer (also updates ETA)
        self.set_interval(1.0, self._update_elapsed_time)

        # Start workflow execution
        self._start_execution()

    def _initialize_timeline(self) -> None:
        """Initialize the progress timeline with workflow steps."""
        try:
            timeline = self.query_one("#progress-timeline", ProgressTimeline)
            steps = []
            for step in self._workflow.steps:
                # Get estimated duration from history
                estimated = self._eta_calculator.get_step_estimate(step.name)
                steps.append(
                    TimelineStep(
                        name=step.name,
                        status="pending",
                        estimated_seconds=estimated,
                    )
                )
            timeline.set_steps(steps)
        except Exception:
            pass

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
            AgentStreamChunk,
            LoopIterationCompleted,
            LoopIterationStarted,
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
                        self._mark_step_failed(
                            event.step_name, event.duration_ms, event.error
                        )
                        # Update status and show error when step fails
                        self._update_status(f"Step '{event.step_name}' failed")
                        if event.error:
                            self._show_error(event.error)

                elif isinstance(event, WorkflowCompleted):
                    self.success = event.success
                    self.is_complete = True
                    self.is_running = False
                    self._show_completion(event.success, event.total_duration_ms)

                elif isinstance(event, LoopIterationStarted):
                    await self._handle_iteration_started(event)

                elif isinstance(event, LoopIterationCompleted):
                    await self._handle_iteration_completed(event)

                elif isinstance(event, AgentStreamChunk):
                    await self._handle_stream_chunk(event)

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
        """Log status message (UI status bar was removed for cleaner layout).

        Args:
            message: Status message to log.
        """
        logger.debug("workflow_status", message=message)

    def _update_progress(self) -> None:
        """Update the progress display."""
        try:
            progress_text = self.query_one("#progress-text", Static)
            progress_bar = self.query_one("#progress-bar", ProgressBar)

            if self.total_steps > 0:
                percent = self.current_step / self.total_steps * 100
            else:
                percent = 0.0
            text = f"[{self.current_step}/{self.total_steps}] {percent:.0f}%"
            progress_text.update(text)
            progress_bar.update(progress=percent)
        except NoMatches:
            # Screen is being unmounted, widgets no longer exist
            pass

    def _mark_step_running(self, step_name: str) -> None:
        """Mark a step as running."""
        if step_name in self._step_widgets:
            self._step_widgets[step_name].set_running()

        # Track start time for duration calculation
        self._step_start_times[step_name] = datetime.now()
        self._current_running_step = step_name

        # Update timeline
        self._update_timeline_step(step_name, "running")

    def _mark_step_completed(self, step_name: str, duration_ms: int) -> None:
        """Mark a step as completed."""
        if step_name in self._step_widgets:
            self._step_widgets[step_name].set_completed(duration_ms)

        # Track completion and record duration for future ETA calculations
        self._completed_steps.add(step_name)
        if self._current_running_step == step_name:
            self._current_running_step = None

        # Record duration in history for future ETA estimates
        duration_seconds = duration_ms / 1000.0
        self._duration_store.record_duration(
            self._workflow.name, step_name, duration_seconds
        )

        # Update timeline with actual duration
        self._update_timeline_step(
            step_name, "completed", duration_seconds=duration_seconds
        )

    def _mark_step_failed(
        self, step_name: str, duration_ms: int, error: str | None = None
    ) -> None:
        """Mark a step as failed."""
        if step_name in self._step_widgets:
            self._step_widgets[step_name].set_failed(duration_ms, error)

        # Track as completed (failed) and clear running state
        self._completed_steps.add(step_name)
        if self._current_running_step == step_name:
            self._current_running_step = None

        # Update timeline
        duration_seconds = duration_ms / 1000.0
        self._update_timeline_step(
            step_name, "failed", duration_seconds=duration_seconds
        )

    def _show_error(self, error: str) -> None:
        """Show an error message."""
        try:
            error_widget = self.query_one("#error-display", Static)
            error_widget.update(f"[red]{error}[/red]")
        except NoMatches:
            # Screen is being unmounted, widget no longer exists
            pass

    def _show_completion(self, success: bool, total_duration_ms: int) -> None:
        """Show completion status.

        Note: Streaming panel entries are intentionally preserved after workflow
        completion (not cleared) to allow users to scroll back and review agent
        output for debugging failed workflows. This is a deliberate design decision
        per User Story 3 (T036) of 030-tui-execution-visibility.
        """
        try:
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
        except NoMatches:
            # Screen is being unmounted, widgets no longer exist
            pass

    def _update_elapsed_time(self) -> None:
        """Update the elapsed time display in the top-right header."""
        if self._start_time is None:
            return

        try:
            elapsed = datetime.now() - self._start_time
            total_seconds = int(elapsed.total_seconds())
            minutes = total_seconds // 60
            seconds = total_seconds % 60

            # Display elapsed time in the top-right header (eta-display element)
            elapsed_widget = self.query_one("#eta-display", Static)
            elapsed_widget.update(f"[dim]Elapsed: {minutes:02d}:{seconds:02d}[/dim]")
        except NoMatches:
            # Screen is being unmounted, widget no longer exists
            pass

    def _update_timeline_step(
        self,
        step_name: str,
        status: str,
        duration_seconds: float | None = None,
    ) -> None:
        """Update a step's status in the progress timeline.

        Args:
            step_name: Name of the step to update.
            status: New status (pending, running, completed, failed).
            duration_seconds: Actual duration in seconds (if completed).
        """
        try:
            timeline = self.query_one("#progress-timeline", ProgressTimeline)
            timeline.update_step(step_name, status, duration_seconds)
        except Exception:
            pass

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
                # Update iteration states for all active loops
                self._mark_iterations_cancelled()
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

    async def _handle_iteration_started(
        self,
        event: LoopIterationStarted,
    ) -> None:
        """Handle loop iteration started event.

        Creates or updates the LoopIterationState for the given loop step,
        marks the current iteration as running, and refreshes the UI.

        Args:
            event: The LoopIterationStarted event containing iteration details.
        """
        # Get or create loop state
        if event.step_name not in self._loop_states:
            self._loop_states[event.step_name] = LoopIterationState(
                step_name=event.step_name,
                iterations=[
                    LoopIterationItem(
                        index=i,
                        total=event.total_iterations,
                        label="",
                        status=IterationStatus.PENDING,
                    )
                    for i in range(event.total_iterations)
                ],
                nesting_level=self._compute_nesting(event.parent_step_name),
            )
            # Mount the widget for this loop
            self._mount_iteration_widget(event.step_name)

        # Update iteration to running
        state = self._loop_states[event.step_name]
        if 0 <= event.iteration_index < len(state.iterations):
            item = state.iterations[event.iteration_index]
            item.label = event.item_label
            item.status = IterationStatus.RUNNING
            item.started_at = event.timestamp

        # Trigger UI update
        self._refresh_iteration_widget(event.step_name)

    async def _handle_iteration_completed(
        self,
        event: LoopIterationCompleted,
    ) -> None:
        """Handle loop iteration completed event.

        Updates the iteration status to completed or failed based on the event,
        and refreshes the UI.

        Args:
            event: The LoopIterationCompleted event containing result details.
        """
        state = self._loop_states.get(event.step_name)
        if not state:
            return

        if 0 <= event.iteration_index < len(state.iterations):
            item = state.iterations[event.iteration_index]
            item.status = (
                IterationStatus.COMPLETED if event.success else IterationStatus.FAILED
            )
            item.duration_ms = event.duration_ms
            item.error = event.error
            item.completed_at = event.timestamp

        self._refresh_iteration_widget(event.step_name)

    def _mark_iterations_cancelled(self) -> None:
        """Mark all running iterations as CANCELLED and pending as SKIPPED.

        Called when the workflow is cancelled to ensure iteration states
        accurately reflect the final state.
        """
        for step_name, state in self._loop_states.items():
            updated = False
            for item in state.iterations:
                if item.status == IterationStatus.RUNNING:
                    item.status = IterationStatus.CANCELLED
                    updated = True
                elif item.status == IterationStatus.PENDING:
                    item.status = IterationStatus.SKIPPED
                    updated = True
            if updated:
                self._refresh_iteration_widget(step_name)

    def _compute_nesting(self, parent_step_name: str | None) -> int:
        """Compute nesting level for a loop based on its parent.

        Args:
            parent_step_name: Name of the parent loop step, or None if top-level.

        Returns:
            Nesting level (0 for top-level, 1 for first nested, etc.).
        """
        if parent_step_name is None:
            return 0

        parent_state = self._loop_states.get(parent_step_name)
        if parent_state is None:
            return 0

        return parent_state.nesting_level + 1

    def _mount_iteration_widget(self, step_name: str) -> None:
        """Mount an IterationProgress widget for the given loop step.

        The widget is mounted after the corresponding step widget if it exists,
        otherwise it's appended to the step list container.

        Args:
            step_name: Name of the loop step to mount widget for.
        """
        state = self._loop_states.get(step_name)
        if not state:
            return

        widget_id = f"iteration-{step_name}"

        # Check if already mounted
        try:
            self.query_one(f"#{widget_id}", IterationProgress)
            return  # Already exists
        except NoMatches:
            pass  # Not found, need to mount

        # Create the widget
        widget = IterationProgress(
            state=state,
            id=widget_id,
            classes="iteration-progress",
        )

        # Mount after the corresponding step widget if it exists
        step_widget = self._step_widgets.get(step_name)
        parent = step_widget.parent if step_widget else None
        if parent is not None and isinstance(parent, ScrollableContainer):
            parent.mount(widget, after=step_widget)
        else:
            # Fallback: append to step list
            try:
                container = self.query_one("#step-list", ScrollableContainer)
                container.mount(widget)
            except NoMatches:
                pass

    def _refresh_iteration_widget(self, step_name: str) -> None:
        """Refresh the IterationProgress widget for the given loop step.

        Updates the widget with the current state from _loop_states.
        Uses 50ms debouncing to prevent flickering (SC-003).

        Args:
            step_name: Name of the loop step whose widget should be refreshed.
        """
        now = time.time()
        elapsed = now - self._last_iteration_update

        # Track which step needs updating
        self._pending_iteration_step = step_name

        if elapsed < DEBOUNCE_INTERVAL_SECONDS:
            # Cancel any pending update and schedule a new one
            if (
                self._pending_iteration_update is not None
                and not self._pending_iteration_update.done()
            ):
                self._pending_iteration_update.cancel()
            self._pending_iteration_update = asyncio.create_task(
                self._delayed_iteration_refresh()
            )
            return

        self._last_iteration_update = now
        self._do_iteration_refresh(step_name)

    async def _delayed_iteration_refresh(self) -> None:
        """Execute a delayed iteration widget refresh after debounce period."""
        await asyncio.sleep(DEBOUNCE_INTERVAL_SECONDS)
        self._last_iteration_update = time.time()
        if self._pending_iteration_step:
            self._do_iteration_refresh(self._pending_iteration_step)

    def _do_iteration_refresh(self, step_name: str) -> None:
        """Perform the actual iteration widget refresh.

        Args:
            step_name: Name of the loop step whose widget should be refreshed.
        """
        state = self._loop_states.get(step_name)
        if not state:
            return

        widget_id = f"iteration-{step_name}"
        try:
            widget = self.query_one(f"#{widget_id}", IterationProgress)
            widget.update_state(state)
        except NoMatches:
            # Widget not found, try to mount it
            self._mount_iteration_widget(step_name)

    async def _handle_stream_chunk(self, event: AgentStreamChunk) -> None:
        """Handle agent stream chunk event.

        Creates an AgentStreamEntry from the event and adds it to the
        streaming state, then refreshes the streaming panel.

        Args:
            event: The AgentStreamChunk event containing streaming data.
        """
        # Convert chunk_type string to enum
        try:
            chunk_type = StreamChunkType(event.chunk_type)
        except ValueError:
            # Default to OUTPUT for unknown chunk types
            chunk_type = StreamChunkType.OUTPUT

        entry = AgentStreamEntry(
            timestamp=event.timestamp,
            step_name=event.step_name,
            agent_name=event.agent_name,
            text=event.text,
            chunk_type=chunk_type,
        )
        self._streaming_state.add_entry(entry)
        self._refresh_streaming_panel()

    def _refresh_streaming_panel(self) -> None:
        """Refresh the streaming panel with new content.

        Updates the AgentStreamingPanel widget with the latest entry
        from the streaming state. Uses 50ms debouncing to prevent
        flickering (SC-003).
        """
        now = time.time()
        elapsed = now - self._last_streaming_update

        if elapsed < DEBOUNCE_INTERVAL_SECONDS:
            # Cancel any pending update and schedule a new one
            if (
                self._pending_streaming_update is not None
                and not self._pending_streaming_update.done()
            ):
                self._pending_streaming_update.cancel()
            self._pending_streaming_update = asyncio.create_task(
                self._delayed_streaming_refresh()
            )
            return

        self._last_streaming_update = now
        self._do_streaming_refresh()

    async def _delayed_streaming_refresh(self) -> None:
        """Execute a delayed streaming panel refresh after debounce period."""
        await asyncio.sleep(DEBOUNCE_INTERVAL_SECONDS)
        self._last_streaming_update = time.time()
        self._do_streaming_refresh()

    def _do_streaming_refresh(self) -> None:
        """Perform the actual streaming panel refresh.

        Appends all new entries since the last refresh to the panel.
        This ensures no events are lost during debouncing.
        """
        try:
            panel = self.query_one("#streaming-panel", AgentStreamingPanel)
            content = panel.query_one(".content", ScrollableContainer)

            # Append all entries since last displayed
            entries = self._streaming_state.entries
            total = len(entries)
            while self._last_displayed_entry_index < total:
                entry = entries[self._last_displayed_entry_index]
                # Mount directly instead of calling append_chunk to avoid
                # double-adding to state
                content.mount(
                    Static(
                        entry.text,
                        classes=f"chunk chunk-{entry.chunk_type.value}",
                    )
                )
                self._last_displayed_entry_index += 1

            # Auto-scroll if enabled
            if self._streaming_state.auto_scroll:
                content.scroll_end(animate=False)
        except NoMatches:
            # Panel not found (widget not mounted yet)
            pass

    def action_toggle_streaming_panel(self) -> None:
        """Toggle the streaming panel visibility (bound to 's' key)."""
        try:
            panel = self.query_one("#streaming-panel", AgentStreamingPanel)
            panel.toggle_visibility()
        except NoMatches:
            # Panel not found
            pass

    def action_toggle_log_panel(self) -> None:
        """Toggle the log panel visibility (bound to 'l' key).

        The LogPanel is mounted in the main MaverickApp, so we access it
        through self.app.query_one(). This provides consistent log panel
        behavior across all screens.
        """
        from maverick.tui.widgets.log_panel import LogPanel

        try:
            log_panel = self.app.query_one(LogPanel)
            log_panel.toggle()
        except NoMatches:
            # Panel not found (widget not mounted yet)
            pass
