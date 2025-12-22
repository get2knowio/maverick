"""Fly workflow screen for Maverick TUI."""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.widgets import Button, Input, Static

from maverick.tui.history import WorkflowHistoryEntry, WorkflowHistoryStore
from maverick.tui.models import AgentMessage, MessageType, StageStatus, WorkflowStage
from maverick.tui.screens.base import MaverickScreen
from maverick.tui.widgets.agent_output import AgentOutput
from maverick.tui.widgets.form import BranchInputField
from maverick.tui.widgets.workflow_progress import WorkflowProgress
from maverick.workflows.fly import (
    FlyInputs,
    FlyProgressEvent,
    FlyStageCompleted,
    FlyStageStarted,
    FlyWorkflow,
    FlyWorkflowCompleted,
    FlyWorkflowFailed,
    FlyWorkflowStarted,
)
from maverick.workflows.fly import (
    WorkflowStage as FlyWorkflowStage,
)

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
    current_workflow_stage: reactive[str | None] = reactive(None)
    review_findings: reactive[list[dict[str, object]]] = reactive(
        [], always_update=True
    )
    show_workflow_view: reactive[bool] = reactive(False)

    def compose(self) -> ComposeResult:
        """Create the screen layout.

        Yields:
            ComposeResult: Screen components including title, form fields,
                action buttons, and workflow progress view.
        """
        yield Static("[bold]Start Fly Workflow[/bold]", id="title")

        # Configuration form (shown initially)
        with Vertical(id="form-container"):
            yield BranchInputField(label="Branch Name", id="branch-input")
            yield Static("Task File (optional):", classes="label")
            yield Input(id="task-file-input", placeholder="path/to/tasks.md")
            with Horizontal(id="buttons"):
                yield Button("Start", id="start-btn", variant="primary", disabled=True)
                yield Button("Cancel", id="cancel-btn")

        # Workflow progress view (shown after start, initially hidden)
        with Vertical(id="workflow-container", classes="hidden"):
            yield Static("[bold]Workflow Progress[/bold]", id="workflow-title")
            with Horizontal(id="workflow-content"):
                # Left: WorkflowProgress widget for stage status
                with Vertical(id="progress-panel", classes="workflow-panel"):
                    yield WorkflowProgress(id="workflow-progress")

                # Right: AgentOutput widget for streaming messages
                with VerticalScroll(id="output-panel", classes="workflow-panel"):
                    yield AgentOutput(id="agent-output")

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

        Hides the configuration form and shows the workflow progress view,
        then starts the workflow execution. The workflow name is set to "Fly"
        and the branch name is trimmed of whitespace.

        This action is bound to ctrl+enter and is also triggered by the
        Start button.

        Note:
            This action does nothing if validation fails or if the workflow
            is already starting.
        """
        if not self.is_valid or self.is_starting:
            return

        self.is_starting = True
        self.is_workflow_running = True
        self._update_start_button()

        # Hide form and show workflow view
        self._toggle_workflow_view(show=True)

        # Start workflow execution
        self._start_workflow_execution()

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
                # In a future implementation, this would signal the workflow
                # worker to resume

    def _toggle_workflow_view(self, show: bool) -> None:
        """Toggle between form view and workflow progress view.

        Args:
            show: True to show workflow view, False to show form view.
        """
        try:
            form_container = self.query_one("#form-container", Vertical)
            workflow_container = self.query_one("#workflow-container", Vertical)

            if show:
                form_container.add_class("hidden")
                workflow_container.remove_class("hidden")
                self.show_workflow_view = True
            else:
                workflow_container.add_class("hidden")
                form_container.remove_class("hidden")
                self.show_workflow_view = False
        except Exception:
            # Widgets not yet mounted
            pass

    def _start_workflow_execution(self) -> None:
        """Start the workflow execution in the background."""
        # Run workflow execution as a background task
        asyncio.create_task(self._run_workflow())

    async def _run_workflow(self) -> None:
        """Execute the FlyWorkflow and handle progress events."""
        try:
            # Create workflow inputs
            inputs = FlyInputs(
                branch_name=self.branch_name.strip(),
                task_file=self.task_file,
                dry_run=False,
            )

            # Create workflow instance
            workflow = FlyWorkflow()

            # Initialize stage list for WorkflowProgress widget
            self._initialize_workflow_stages()

            # Execute workflow and process events
            async for event in workflow.execute(inputs):
                await self._handle_workflow_event(event)

        except Exception as e:
            self.notify(
                f"Workflow execution failed: {e}",
                title="Workflow Error",
                severity="error",
            )
            self.is_workflow_running = False

    def _initialize_workflow_stages(self) -> None:
        """Initialize workflow stages in the WorkflowProgress widget."""

        # Define all workflow stages
        stage_definitions = [
            ("init", "Initialization"),
            ("implementation", "Implementation"),
            ("validation", "Validation"),
            ("code_review", "Code Review"),
            ("convention_update", "Convention Update"),
            ("pr_creation", "PR Creation"),
        ]

        stages = [
            WorkflowStage(
                name=name,
                display_name=display_name,
                status=StageStatus.PENDING,
            )
            for name, display_name in stage_definitions
        ]

        # Update WorkflowProgress widget
        try:
            progress_widget = self.query_one("#workflow-progress", WorkflowProgress)
            progress_widget.update_stages(stages)
        except Exception:
            # Widget not yet mounted
            pass

    async def _handle_workflow_event(self, event: FlyProgressEvent) -> None:
        """Handle workflow progress events.

        Args:
            event: Workflow progress event from FlyWorkflow.
        """

        if isinstance(event, FlyWorkflowStarted):
            self._add_agent_message(
                f"Starting Fly workflow for branch: {event.inputs.branch_name}",
                agent_name="FlyWorkflow",
            )

        elif isinstance(event, FlyStageStarted):
            self._update_stage_status(event.stage.value, "active")
            self.current_workflow_stage = event.stage.value
            self._add_agent_message(
                f"Starting stage: {event.stage.value}",
                agent_name="FlyWorkflow",
            )

        elif isinstance(event, FlyStageCompleted):
            self._update_stage_status(event.stage.value, "completed")
            self._add_agent_message(
                f"Completed stage: {event.stage.value}",
                agent_name="FlyWorkflow",
            )

            # Check if this is the code review stage
            if event.stage == FlyWorkflowStage.CODE_REVIEW:
                await self._handle_code_review_completion(event)

        elif isinstance(event, FlyWorkflowCompleted):
            self._add_agent_message(
                f"Workflow completed successfully: {event.result.summary}",
                agent_name="FlyWorkflow",
            )
            self.is_workflow_running = False
            self.notify(
                "Workflow completed successfully!",
                title="Success",
                severity="information",
            )

        elif isinstance(event, FlyWorkflowFailed):
            self._update_stage_status(
                event.state.stage.value, "failed", error_message=event.error
            )
            self._add_agent_message(
                f"Workflow failed: {event.error}",
                agent_name="FlyWorkflow",
            )
            self.is_workflow_running = False
            self.notify(
                f"Workflow failed: {event.error}",
                title="Workflow Failed",
                severity="error",
            )

    def _update_stage_status(
        self, stage_name: str, status: str, error_message: str | None = None
    ) -> None:
        """Update the status of a workflow stage.

        Args:
            stage_name: Name of the stage to update.
            status: New status ("pending", "active", "completed", "failed").
            error_message: Optional error message if status is "failed".
        """
        try:
            progress_widget = self.query_one("#workflow-progress", WorkflowProgress)
            progress_widget.update_stage_status(
                stage_name, status, error_message=error_message
            )
        except Exception:
            # Widget not yet mounted
            pass

    def _add_agent_message(self, content: str, agent_name: str = "System") -> None:
        """Add a message to the AgentOutput widget.

        Args:
            content: Message content.
            agent_name: Name of the agent sending the message.
        """
        import uuid
        from datetime import datetime

        try:
            output_widget = self.query_one("#agent-output", AgentOutput)
            message = AgentMessage(
                id=str(uuid.uuid4()),
                timestamp=datetime.now(),
                agent_id=agent_name.lower(),
                agent_name=agent_name,
                message_type=MessageType.TEXT,
                content=content,
            )
            output_widget.add_message(message)
        except Exception:
            # Widget not yet mounted
            pass

    async def _handle_code_review_completion(self, event: FlyStageCompleted) -> None:
        """Handle code review stage completion and auto-transition to ReviewScreen.

        Args:
            event: The stage completion event containing review results.
        """
        # Extract review findings from the event result
        result = event.result
        if isinstance(result, dict):
            # Check if we have review results
            review_results = result.get("review_results", [])
            if review_results:
                # Convert review results to findings format
                findings = self._convert_review_results_to_findings(review_results)
                self.review_findings = findings

                # Auto-transition to ReviewScreen with findings
                from maverick.tui.screens.review import ReviewScreen

                review_screen = ReviewScreen()
                review_screen.load_issues(findings)

                self.notify(
                    "Code review complete. Transitioning to ReviewScreen...",
                    title="Code Review",
                    severity="information",
                )

                # Push ReviewScreen
                self.app.push_screen(review_screen)

    def _convert_review_results_to_findings(
        self, review_results: list[object]
    ) -> list[dict[str, object]]:
        """Convert workflow review results to ReviewScreen findings format.

        Args:
            review_results: List of review results from the workflow.

        Returns:
            List of finding dictionaries compatible with ReviewScreen.
        """
        findings: list[dict[str, object]] = []

        for idx, result in enumerate(review_results):
            # Extract finding data based on the result structure
            # This is a placeholder - actual structure depends on AgentResult
            if hasattr(result, "findings"):
                for finding in result.findings:
                    findings.append(
                        {
                            "id": f"finding-{idx}",
                            "file_path": getattr(finding, "file_path", "unknown"),
                            "line_number": getattr(finding, "line_number", 0),
                            "severity": getattr(finding, "severity", "info"),
                            "message": getattr(finding, "message", ""),
                            "source": getattr(finding, "source", "review"),
                        }
                    )

        return findings


__all__ = [
    "FlyScreen",
]
