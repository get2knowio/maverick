"""Workflow execution screen for running and monitoring workflows.

This screen executes a workflow using the DSL executor and displays
real-time progress updates for each step.

Updated: 2026-01-17 - Streaming-first layout with unified event stream.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.css.query import NoMatches
from textual.reactive import reactive
from textual.widgets import Static
from textual.worker import Worker, WorkerState

from maverick.logging import get_logger
from maverick.tui.models.enums import IterationStatus, StreamChunkType, StreamEntryType
from maverick.tui.models.step_tree import StepTreeState
from maverick.tui.models.widget_state import (
    AgentStreamEntry,
    LoopIterationItem,
    LoopIterationState,
    StreamingPanelState,
    UnifiedStreamEntry,
    UnifiedStreamState,
)
from maverick.tui.screens.base import MaverickScreen
from maverick.tui.step_durations import ETACalculator, StepDurationStore
from maverick.tui.widgets.agent_streaming_panel import AgentStreamingPanel
from maverick.tui.widgets.aggregate_stats import AggregateStatsBar
from maverick.tui.widgets.breadcrumb import BreadcrumbBar
from maverick.tui.widgets.iteration_progress import IterationProgress
from maverick.tui.widgets.step_detail import StepDetailPanel
from maverick.tui.widgets.step_tree import StepTreeWidget
from maverick.tui.widgets.unified_stream import UnifiedStreamWidget

if TYPE_CHECKING:
    from maverick.dsl.events import (
        AgentStreamChunk,
        LoopIterationCompleted,
        LoopIterationStarted,
        StepOutput,
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


class WorkflowExecutionScreen(MaverickScreen):
    """Execute workflow and display real-time progress.

    This screen runs a workflow using WorkflowFileExecutor and displays
    step-by-step progress with status indicators and timing information.
    """

    TITLE = "Running Workflow"

    BINDINGS = [
        Binding("escape", "cancel_workflow", "Cancel/Exit", show=True),
        Binding("q", "exit_app", "Exit", show=True),
        Binding("f", "toggle_follow", "Follow", show=True),
        Binding("s", "toggle_steps_panel", "Steps", show=True),
        Binding("l", "toggle_log_panel", "Logs", show=True),
        Binding("g", "scroll_top", "Top", show=False),
        Binding("G", "scroll_bottom", "Bottom", show=False),
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
        self._loop_states: dict[str, LoopIterationState] = {}
        self._cancel_requested = False
        self._executor_worker: Worker[WorkflowResult] | None = None
        self._result: WorkflowResult | None = None
        self._start_time: datetime | None = None

        # Step tree state for hierarchical step display
        self._tree_state = StepTreeState()

        # Unified stream state for the streaming-first layout
        self._unified_state = UnifiedStreamState(
            workflow_name=workflow.name,
            total_steps=len(workflow.steps),
        )

        # Legacy streaming state (kept for backward compatibility)
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

        # UI toggle states
        self._steps_panel_visible: bool = True

        # Step selection state for stream filtering
        self._selected_step: str | None = None

        # Sentence-boundary buffering for streaming text
        # Buffers text until a newline is reached for readable display
        self._stream_buffers: dict[str, str] = {}  # agent_key -> buffered text
        self._stream_buffer_timestamps: dict[
            str, float
        ] = {}  # agent_key -> last update
        self._stream_buffer_paths: dict[
            str, str | None
        ] = {}  # agent_key -> step_path (for filtering)
        self._stream_buffer_flush_delay: float = 0.3  # Flush stale buffers after 300ms
        self._stream_buffer_flush_task: asyncio.Task[None] | None = None

    def compose(self) -> ComposeResult:
        """Create the streaming-first execution screen layout.

        Minimal chrome, maximum content - follows constitution principles:
        - Single-line compact header with workflow name, step, and elapsed time
        - UnifiedStreamWidget as the sole primary content area
        - No separate progress bar, timeline, or error display

        Layout:
            ┌───────────────────────────────────────────────────────────────┐
            │ workflow-name  Step 3/8: review  [01:23]                      │
            ├───────────────────────────────────────────────────────────────┤
            │ 12:34:05 [STEP] implement_task started                        │
            │ 12:34:06 [implementer] Analyzing task requirements...         │
            │          > Reading src/maverick/cli/main.py                   │
            │ 12:34:22 [OK] implement_task completed (16.2s)                │
            │ 12:34:23 [STEP] review_code started                           │
            │ ...                                                           │
            ├───────────────────────────────────────────────────────────────┤
            │ [ESC] [F]Follow [S]Steps [L]Logs                              │
            └───────────────────────────────────────────────────────────────┘
        """
        # Single-line compact header: workflow-name | Step X/Y: step_name | [elapsed]
        yield Static(
            self._format_compact_header(),
            id="compact-header",
        )

        # Aggregate stats bar: step counts, tokens, cost
        yield AggregateStatsBar(
            self._unified_state,
            id="stats-bar",
        )

        # Main content area with optional steps panel
        with Horizontal(id="execution-main"):
            # Steps panel (toggleable with 's') - tree widget
            with Vertical(id="execution-steps", classes="execution-pane"):
                yield Static("[bold]Steps[/bold]", classes="pane-header")
                # Tree widget for hierarchical step display
                yield StepTreeWidget(
                    self._tree_state,
                    id="step-tree",
                )

            # Main content: breadcrumb + detail panel + unified stream
            with Vertical(id="execution-content"):
                # Breadcrumb bar (hidden when no scope active)
                yield BreadcrumbBar(
                    id="breadcrumb-bar",
                    classes="hidden",
                )

                # Step detail panel (shows current step info, tokens, cost)
                yield StepDetailPanel(
                    self._unified_state,
                    id="step-detail-panel",
                )

                # Unified stream widget (primary content)
                yield UnifiedStreamWidget(
                    self._unified_state,
                    id="unified-stream",
                )

    def on_mount(self) -> None:
        """Start workflow execution when mounted."""
        super().on_mount()
        self.total_steps = len(self._workflow.steps)
        self._start_time = datetime.now()

        # Initialize the unified stream state with start time
        self._unified_state.start_time = time.time()
        self._unified_state.workflow_name = self._workflow.name
        self._unified_state.total_steps = self.total_steps

        # Pre-populate tree with all workflow steps (status=pending)
        for step in self._workflow.steps:
            step_type_str = (
                step.type.value if hasattr(step.type, "value") else str(step.type)
            )
            self._tree_state.upsert_node(
                step.name, step_type=step_type_str, status="pending"
            )
        self._refresh_step_tree()

        # Start elapsed time timer (updates compact header and unified stream)
        self.set_interval(1.0, self._update_elapsed_time)

        # Start workflow execution
        self._start_execution()

    def _format_compact_header(self) -> str:
        """Format the single-line compact header.

        Format: workflow-name | Step X/Y: step_name | [MM:SS]

        Returns:
            Formatted header string.
        """
        name = self._workflow.name
        step_info = f"Step {self.current_step}/{self.total_steps}"
        if self._current_running_step:
            step_info = (
                f"Step {self.current_step}/{self.total_steps}: "
                f"{self._current_running_step}"
            )

        # Calculate elapsed time
        if self._start_time:
            elapsed = datetime.now() - self._start_time
            minutes = int(elapsed.total_seconds()) // 60
            seconds = int(elapsed.total_seconds()) % 60
            elapsed_str = f"\\[{minutes:02d}:{seconds:02d}]"
        else:
            elapsed_str = "\\[00:00]"

        return f"[bold]{name}[/bold]  {step_info}  [dim]{elapsed_str}[/dim]"

    def _update_compact_header(self) -> None:
        """Update the compact header with current status.

        Skips update if workflow is complete (completion status is shown).
        """
        if self.is_complete:
            return

        try:
            header = self.query_one("#compact-header", Static)
            header.update(self._format_compact_header())
        except NoMatches:
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
            StepOutput,
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
                    step_type_str = (
                        event.step_type.value
                        if hasattr(event.step_type, "value")
                        else str(event.step_type)
                    )
                    self._mark_step_running(
                        event.step_name, step_type_str, step_path=event.step_path
                    )

                elif isinstance(event, StepCompleted):
                    if event.success:
                        self._mark_step_completed(
                            event.step_name,
                            event.duration_ms,
                            input_tokens=event.input_tokens,
                            output_tokens=event.output_tokens,
                            cost_usd=event.cost_usd,
                            step_path=event.step_path,
                        )
                    else:
                        self._mark_step_failed(
                            event.step_name,
                            event.duration_ms,
                            event.error,
                            step_path=event.step_path,
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

                elif isinstance(event, StepOutput):
                    await self._handle_step_output(event)

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
        """Update the progress display (compact header)."""
        self._update_compact_header()

    def _mark_step_running(
        self,
        step_name: str,
        step_type: str = "unknown",
        step_path: str | None = None,
    ) -> None:
        """Mark a step as running.

        Args:
            step_name: Name of the step.
            step_type: Type of the step (agent, python, etc.).
            step_path: Hierarchical path for tree navigation.
        """
        # Track start time for duration calculation
        self._step_start_times[step_name] = datetime.now()
        self._current_running_step = step_name

        # Update tree state
        path = step_path or step_name
        self._tree_state.upsert_node(path, step_type=step_type, status="running")
        self._refresh_step_tree()

        # Update unified state with step start (for detail panel)
        self._unified_state.start_step(step_name, step_type)

        # Update compact header with current step
        self._update_compact_header()

        # Refresh detail panel and stats bar
        self._refresh_detail_panel()
        self._refresh_stats_bar()

        # Add to unified stream
        entry = UnifiedStreamEntry(
            timestamp=time.time(),
            entry_type=StreamEntryType.STEP_START,
            source=step_name,
            content=f"{step_name} started",
            step_name=step_name,
            step_path=path,
        )
        self._add_unified_entry(entry)

    def _mark_step_completed(
        self,
        step_name: str,
        duration_ms: int,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        cost_usd: float | None = None,
        step_path: str | None = None,
    ) -> None:
        """Mark a step as completed.

        Args:
            step_name: Name of the step.
            duration_ms: Duration in milliseconds.
            input_tokens: Input tokens consumed (agent steps only).
            output_tokens: Output tokens generated (agent steps only).
            cost_usd: Cost in USD (agent steps only).
            step_path: Hierarchical path for tree navigation.
        """
        # Flush any remaining buffered streaming text for this step
        self._flush_all_stream_buffers()

        # Track completion and record duration for future ETA calculations
        self._completed_steps.add(step_name)
        if self._current_running_step == step_name:
            self._current_running_step = None

        # Update tree state
        path = step_path or step_name
        self._tree_state.upsert_node(path, status="completed", duration_ms=duration_ms)
        self._tree_state.auto_collapse_completed(path)
        self._refresh_step_tree()

        # Record duration in history for future ETA estimates
        duration_seconds = duration_ms / 1000.0
        self._duration_store.record_duration(
            self._workflow.name, step_name, duration_seconds
        )

        # Update unified state with completion (for detail panel)
        self._unified_state.complete_step(
            success=True,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
        )

        # Refresh detail panel and stats bar
        self._refresh_detail_panel()
        self._refresh_stats_bar()

        # Add to unified stream
        entry = UnifiedStreamEntry(
            timestamp=time.time(),
            entry_type=StreamEntryType.STEP_COMPLETE,
            source=step_name,
            content=f"{step_name} completed",
            level="success",
            duration_ms=duration_ms,
            step_name=step_name,
            step_path=path,
        )
        self._add_unified_entry(entry)

    def _mark_step_failed(
        self,
        step_name: str,
        duration_ms: int,
        error: str | None = None,
        step_path: str | None = None,
    ) -> None:
        """Mark a step as failed."""
        # Flush any remaining buffered streaming text for this step
        self._flush_all_stream_buffers()

        # Track as completed (failed) and clear running state
        self._completed_steps.add(step_name)
        if self._current_running_step == step_name:
            self._current_running_step = None

        # Update tree state
        path = step_path or step_name
        self._tree_state.upsert_node(path, status="failed", duration_ms=duration_ms)
        self._refresh_step_tree()

        # Update unified state with failure (for detail panel)
        self._unified_state.complete_step(success=False)

        # Refresh detail panel and stats bar
        self._refresh_detail_panel()
        self._refresh_stats_bar()

        # Add to unified stream
        content = f"{step_name} failed"
        if error:
            content = f"{step_name} failed: {error}"
        entry = UnifiedStreamEntry(
            timestamp=time.time(),
            entry_type=StreamEntryType.STEP_FAILED,
            source=step_name,
            content=content,
            level="error",
            duration_ms=duration_ms,
            step_name=step_name,
            step_path=path,
        )
        self._add_unified_entry(entry)

    def _show_error(self, error: str) -> None:
        """Log an error message (errors are shown in the unified stream)."""
        logger.error("workflow_error", error=error)

    def _show_completion(self, success: bool, total_duration_ms: int) -> None:
        """Show completion status.

        Note: Streaming panel entries are intentionally preserved after workflow
        completion (not cleared) to allow users to scroll back and review agent
        output for debugging failed workflows. This is a deliberate design decision
        per User Story 3 (T036) of 030-tui-execution-visibility.
        """
        try:
            # Update header with completion status
            header = self.query_one("#compact-header", Static)
            duration_sec = total_duration_ms / 1000
            if success:
                header.update(
                    f"[bold]{self._workflow.name}[/bold]  "
                    f"[green]✓ Completed[/green] ({duration_sec:.1f}s)"
                )
            else:
                header.update(
                    f"[bold]{self._workflow.name}[/bold]  "
                    f"[red]✗ Failed[/red] ({duration_sec:.1f}s)"
                )

        except NoMatches:
            # Screen is being unmounted, widgets no longer exist
            pass

        # Refresh stats bar with final counts
        self._refresh_stats_bar()

    def _update_elapsed_time(self) -> None:
        """Update the elapsed time display in headers."""
        if self._start_time is None:
            return

        # Update compact header
        self._update_compact_header()

        try:
            # Update unified stream widget header
            stream_widget = self.query_one("#unified-stream", UnifiedStreamWidget)
            stream_widget.update_elapsed()
        except NoMatches:
            # Screen is being unmounted, widget no longer exists
            pass

        # Update detail panel (for step elapsed time)
        self._refresh_detail_panel()

        # Update stats bar (for token/cost counters)
        self._refresh_stats_bar()

    def action_cancel_workflow(self) -> None:
        """Request workflow cancellation or exit if complete.

        When a scope is active, Escape navigates up one level instead.
        """
        # If a scope is active, navigate up instead of cancelling
        if self._selected_step is not None:
            try:
                breadcrumb = self.query_one("#breadcrumb-bar", BreadcrumbBar)
                new_path = breadcrumb.navigate_up()
                self._apply_scope(new_path)
                return
            except NoMatches:
                pass

        if not self.is_running:
            # If not running (workflow complete or not started), exit the app
            self.app.exit()
            return

        self._cancel_requested = True
        self._update_status("Cancelling...")

        if self._executor_worker is not None:
            self._executor_worker.cancel()

    def action_exit_app(self) -> None:
        """Exit the application."""
        self.app.exit()

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

        # Update tree state with iteration node
        if event.step_path:
            self._tree_state.upsert_node(
                event.step_path,
                label=event.item_label or f"[{event.iteration_index}]",
                status="running",
            )
            self._refresh_step_tree()

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

        # Update tree state
        if event.step_path:
            status = "completed" if event.success else "failed"
            self._tree_state.upsert_node(
                event.step_path,
                status=status,
                duration_ms=event.duration_ms,
            )
            self._tree_state.auto_collapse_completed(event.step_path)
            self._refresh_step_tree()

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

        # Mount into the tree content container
        try:
            container = self.query_one("#tree-content", ScrollableContainer)
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
        """Handle agent stream chunk event with newline-based buffering.

        Buffers incoming text chunks until a newline is reached, then
        flushes complete lines to the unified stream. This produces
        readable output without breaking lines mid-sentence.

        Flush triggers:
        - A newline appears (flush everything up to and including the newline)
        - Buffer timeout elapsed (300ms with no new input) - flushes partial text

        Args:
            event: The AgentStreamChunk event containing streaming data.
        """
        # Convert chunk_type string to enum
        try:
            chunk_type = StreamChunkType(event.chunk_type)
        except ValueError:
            chunk_type = StreamChunkType.OUTPUT

        agent_key = f"{event.step_name}:{event.agent_name}"

        # Append to buffer and track step_path for filtering
        current_buffer = self._stream_buffers.get(agent_key, "")
        current_buffer += event.text
        self._stream_buffers[agent_key] = current_buffer
        self._stream_buffer_timestamps[agent_key] = time.time()
        if event.step_path is not None:
            self._stream_buffer_paths[agent_key] = event.step_path

        # Determine what to flush based on sentence boundaries
        text_to_flush = self._extract_flushable_text(agent_key)

        if text_to_flush:
            await self._flush_stream_text(
                text_to_flush,
                event,
                chunk_type,
            )

        # Schedule a timeout flush for any remaining buffered text
        self._schedule_buffer_flush_timeout()

    def _extract_flushable_text(self, agent_key: str) -> str:
        """Extract text that can be flushed from the buffer.

        Returns text up to and including the last newline character.
        Keeps any incomplete line in the buffer for later flushing
        (either by a subsequent newline or the 300ms timeout).

        Only newlines trigger a flush — not sentence-ending punctuation.
        This prevents mid-paragraph line breaks where each sentence
        would otherwise appear as a separate visual entry with its
        own badge prefix.

        Args:
            agent_key: The buffer key (step_name:agent_name).

        Returns:
            Text to flush, or empty string if no newline found.
        """
        buffer = self._stream_buffers.get(agent_key, "")
        if not buffer:
            return ""

        # Find the last newline
        last_newline = buffer.rfind("\n")

        if last_newline >= 0:
            # Flush up to and including the newline
            text_to_flush = buffer[: last_newline + 1]
            self._stream_buffers[agent_key] = buffer[last_newline + 1 :]
            return text_to_flush

        return ""

    def _schedule_buffer_flush_timeout(self) -> None:
        """Schedule a timeout flush for stale buffers.

        If no sentence boundary is reached within the flush delay,
        this ensures buffered text is still displayed to the user.
        Cancels any previously scheduled flush to avoid duplicates.
        """
        # Cancel any existing scheduled flush
        if (
            self._stream_buffer_flush_task is not None
            and not self._stream_buffer_flush_task.done()
        ):
            self._stream_buffer_flush_task.cancel()

        # Schedule a new flush after the delay
        with contextlib.suppress(RuntimeError):
            self._stream_buffer_flush_task = asyncio.create_task(
                self._delayed_buffer_flush()
            )

    async def _delayed_buffer_flush(self) -> None:
        """Flush stale buffers after a delay.

        Waits for the configured flush delay, then flushes any buffers
        that haven't been updated recently. This ensures text is displayed
        even when no sentence boundary is reached (e.g., partial output).
        """
        await asyncio.sleep(self._stream_buffer_flush_delay)

        now = time.time()
        stale_threshold = self._stream_buffer_flush_delay

        for agent_key, last_update in list(self._stream_buffer_timestamps.items()):
            if now - last_update >= stale_threshold:
                buffer = self._stream_buffers.get(agent_key, "")
                if buffer.strip():
                    # Flush the entire buffer as-is
                    parts = agent_key.split(":", 1)
                    step_name = parts[0] if len(parts) > 0 else "unknown"
                    agent_name = parts[1] if len(parts) > 1 else "unknown"
                    step_path = self._stream_buffer_paths.get(agent_key)

                    unified_entry = UnifiedStreamEntry(
                        timestamp=now,
                        entry_type=StreamEntryType.AGENT_OUTPUT,
                        source=agent_name,
                        content=buffer.rstrip(),
                        level="info",
                        step_name=step_name,
                        step_path=step_path,
                    )
                    self._add_unified_entry(unified_entry)

                    legacy_entry = AgentStreamEntry(
                        timestamp=now,
                        step_name=step_name,
                        agent_name=agent_name,
                        text=buffer.rstrip(),
                        chunk_type=StreamChunkType.OUTPUT,
                    )
                    self._streaming_state.add_entry(legacy_entry)

                    # Clear this buffer
                    self._stream_buffers[agent_key] = ""

    async def _flush_stream_text(
        self,
        text: str,
        event: AgentStreamChunk,
        chunk_type: StreamChunkType,
    ) -> None:
        """Flush buffered text to the unified stream.

        Args:
            text: The text to flush.
            event: The original event (for metadata).
            chunk_type: The type of chunk.
        """
        # Skip whitespace-only flushes to prevent empty stream entries
        if not text.strip():
            return

        # Map StreamChunkType to StreamEntryType
        if chunk_type == StreamChunkType.THINKING:
            entry_type = StreamEntryType.AGENT_THINKING
        elif chunk_type == StreamChunkType.ERROR:
            entry_type = StreamEntryType.ERROR
        else:
            entry_type = StreamEntryType.AGENT_OUTPUT

        # Create unified stream entry
        unified_entry = UnifiedStreamEntry(
            timestamp=event.timestamp,
            entry_type=entry_type,
            source=event.agent_name,
            content=text.rstrip(),  # Remove trailing whitespace for cleaner display
            level="error" if chunk_type == StreamChunkType.ERROR else "info",
            step_name=event.step_name,
            step_path=event.step_path,
        )
        self._add_unified_entry(unified_entry)

        # Also add to legacy streaming state
        legacy_entry = AgentStreamEntry(
            timestamp=event.timestamp,
            step_name=event.step_name,
            agent_name=event.agent_name,
            text=text.rstrip(),
            chunk_type=chunk_type,
        )
        self._streaming_state.add_entry(legacy_entry)

    def _flush_all_stream_buffers(self) -> None:
        """Flush all remaining text in stream buffers.

        Called when a step completes to ensure no text is left unbuffered.
        """
        for agent_key, buffer in list(self._stream_buffers.items()):
            if buffer.strip():
                # Create a minimal entry for the remaining text
                parts = agent_key.split(":", 1)
                step_name = parts[0] if len(parts) > 0 else "unknown"
                agent_name = parts[1] if len(parts) > 1 else "unknown"
                step_path = self._stream_buffer_paths.get(agent_key)

                unified_entry = UnifiedStreamEntry(
                    timestamp=time.time(),
                    entry_type=StreamEntryType.AGENT_OUTPUT,
                    source=agent_name,
                    content=buffer.rstrip(),
                    level="info",
                    step_name=step_name,
                    step_path=step_path,
                )
                self._add_unified_entry(unified_entry)

                legacy_entry = AgentStreamEntry(
                    timestamp=time.time(),
                    step_name=step_name,
                    agent_name=agent_name,
                    text=buffer.rstrip(),
                    chunk_type=StreamChunkType.OUTPUT,
                )
                self._streaming_state.add_entry(legacy_entry)

        # Clear all buffers
        self._stream_buffers.clear()
        self._stream_buffer_timestamps.clear()
        self._stream_buffer_paths.clear()

    async def _handle_step_output(self, event: StepOutput) -> None:
        """Handle generic step output event.

        Creates a UnifiedStreamEntry from the StepOutput event and adds it
        to the unified stream. This allows any step type (Python actions,
        validation steps, GitHub operations, etc.) to contribute to the
        unified stream widget.

        Args:
            event: The StepOutput event containing step output data.
        """
        # Create unified stream entry with source from event
        # The source can be a subsystem identifier like "github" or "git"
        unified_entry = UnifiedStreamEntry(
            timestamp=event.timestamp,
            entry_type=StreamEntryType.STEP_OUTPUT,
            source=event.source or event.step_name,
            content=event.message,
            level=event.level,
            metadata=event.metadata,
            step_name=event.step_name,
            step_path=event.step_path,
        )
        self._add_unified_entry(unified_entry)

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

    def _add_unified_entry(self, entry: UnifiedStreamEntry) -> None:
        """Add an entry to the unified stream with debounced refresh.

        Args:
            entry: The unified stream entry to add.
        """
        self._unified_state.add_entry(entry)
        self._refresh_unified_stream()

    def _refresh_unified_stream(self) -> None:
        """Refresh the unified stream widget with debouncing."""
        now = time.time()
        elapsed = now - self._last_streaming_update

        if elapsed < DEBOUNCE_INTERVAL_SECONDS:
            # Cancel any pending update and schedule a new one
            if (
                self._pending_streaming_update is not None
                and not self._pending_streaming_update.done()
            ):
                self._pending_streaming_update.cancel()
            try:
                self._pending_streaming_update = asyncio.create_task(
                    self._delayed_unified_refresh()
                )
            except RuntimeError:
                # No running event loop (e.g., in sync tests) - do immediate refresh
                self._last_streaming_update = now
                self._do_unified_refresh()
            return

        self._last_streaming_update = now
        self._do_unified_refresh()

    async def _delayed_unified_refresh(self) -> None:
        """Execute a delayed unified stream refresh after debounce period."""
        await asyncio.sleep(DEBOUNCE_INTERVAL_SECONDS)
        self._last_streaming_update = time.time()
        self._do_unified_refresh()

    def _do_unified_refresh(self) -> None:
        """Perform the actual unified stream widget refresh."""
        try:
            stream_widget = self.query_one("#unified-stream", UnifiedStreamWidget)
            stream_widget.refresh_entries()
        except NoMatches:
            pass

    def _refresh_detail_panel(self) -> None:
        """Refresh the step detail panel with current state."""
        try:
            detail_panel = self.query_one("#step-detail-panel", StepDetailPanel)
            detail_panel.refresh_display()
        except NoMatches:
            pass

    def _refresh_stats_bar(self) -> None:
        """Refresh the aggregate stats bar with current state."""
        try:
            stats_bar = self.query_one("#stats-bar", AggregateStatsBar)
            stats_bar.refresh_display()
        except NoMatches:
            pass

    def _refresh_step_tree(self) -> None:
        """Refresh the step tree widget."""
        try:
            tree_widget = self.query_one("#step-tree", StepTreeWidget)
            tree_widget.refresh_tree()
        except NoMatches:
            pass

    def action_toggle_follow(self) -> None:
        """Toggle auto-scroll/follow mode (bound to 'f' key)."""
        try:
            stream_widget = self.query_one("#unified-stream", UnifiedStreamWidget)
            stream_widget.toggle_auto_scroll()
        except NoMatches:
            pass

    def action_toggle_steps_panel(self) -> None:
        """Toggle the steps panel visibility (bound to 's' key)."""
        try:
            steps_panel = self.query_one("#execution-steps", Vertical)
            self._steps_panel_visible = not self._steps_panel_visible
            if self._steps_panel_visible:
                steps_panel.remove_class("hidden")
            else:
                steps_panel.add_class("hidden")
        except NoMatches:
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
            pass

    def action_scroll_top(self) -> None:
        """Scroll to top of stream (bound to 'g' key)."""
        try:
            stream_widget = self.query_one("#unified-stream", UnifiedStreamWidget)
            stream_widget.scroll_to_top()
        except NoMatches:
            pass

    def action_scroll_bottom(self) -> None:
        """Scroll to bottom of stream (bound to 'G' key)."""
        try:
            stream_widget = self.query_one("#unified-stream", UnifiedStreamWidget)
            stream_widget.scroll_to_bottom()
        except NoMatches:
            pass

    def on_step_tree_widget_step_tree_node_selected(
        self, message: StepTreeWidget.StepTreeNodeSelected
    ) -> None:
        """Handle tree node click for stream filtering.

        Clicking a node filters the stream to that subtree. Clicking
        the same node again clears the filter.

        Args:
            message: The StepTreeNodeSelected message with the path.
        """
        if self._selected_step == message.path:
            # Toggle off: clear scope
            self._apply_scope(None)
        else:
            self._apply_scope(message.path)

    def on_breadcrumb_bar_breadcrumb_segment_clicked(
        self, message: BreadcrumbBar.BreadcrumbSegmentClicked
    ) -> None:
        """Handle breadcrumb segment click."""
        self._apply_scope(message.path)

    def _apply_scope(self, path: str | None) -> None:
        """Apply a scope filter to the stream and update tree/breadcrumb.

        Args:
            path: Step path to scope to, or None to show all.
        """
        self._selected_step = path
        self._tree_state.selected_path = path

        # Update tree visual
        self._refresh_step_tree()

        # Update breadcrumb
        try:
            breadcrumb = self.query_one("#breadcrumb-bar", BreadcrumbBar)
            breadcrumb.set_path(path)
        except NoMatches:
            pass

        # Apply filter to stream widget
        try:
            stream_widget = self.query_one("#unified-stream", UnifiedStreamWidget)
            stream_widget.filter_path = path
        except NoMatches:
            pass
