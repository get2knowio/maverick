from __future__ import annotations

from typing import cast

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Static

from maverick.tui.widgets.sidebar import StageDict
from maverick.tui.widgets.stage_indicator import StageIndicator


class WorkflowScreen(Screen[None]):
    """Workflow progress screen.

    Displays active workflow stages with status indicators, elapsed time,
    and current stage details.
    """

    TITLE = "Workflow"

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back", show=True),
    ]

    def __init__(
        self,
        workflow_name: str = "",
        branch_name: str = "",
        stages: list[str] | None = None,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Initialize the workflow screen.

        Args:
            workflow_name: Name of the workflow being executed.
            branch_name: Git branch name for the workflow.
            stages: List of stage names to display
                (e.g., ["setup", "implementation", "review"]).
            name: Widget name.
            id: Widget ID.
            classes: CSS classes.
        """
        super().__init__(name=name, id=id, classes=classes)
        self._workflow_name = workflow_name
        self._branch_name = branch_name
        self._stages = stages or [
            "setup",
            "implementation",
            "review",
            "validation",
            "pr_management",
        ]

    @property
    def workflow_name(self) -> str:
        """Get the current workflow name.

        Returns:
            The name of the workflow being executed.
        """
        return self._workflow_name

    @property
    def elapsed_time(self) -> float:
        """Get elapsed time in seconds.

        Returns:
            Elapsed time in seconds since workflow started, delegated to app timer.
        """
        from maverick.tui.app import MaverickApp

        app = cast(MaverickApp, self.app)
        return app.elapsed_time

    def compose(self) -> ComposeResult:
        """Create the workflow screen layout.

        Yields:
            ComposeResult: Workflow progress display.
        """
        yield Static(
            f"[bold]Workflow: {self._workflow_name or 'Unknown'}[/bold]",
            id="workflow-title",
            classes="workflow-name",
        )
        yield Static(
            f"Branch: {self._branch_name or 'N/A'}",
            id="workflow-branch",
        )
        yield Static(
            "Elapsed: 0.0s",
            id="workflow-elapsed",
        )

        # Container for stage indicators
        with Vertical(id="workflow-stages"):
            for stage_name in self._stages:
                yield StageIndicator(
                    name=stage_name.replace("_", " ").title(),
                    status="pending",
                    id=f"stage-{stage_name}",
                )

        # Container for error messages
        yield Static("", id="workflow-errors")

    def on_mount(self) -> None:
        """Initialize the workflow screen.

        Sets up sidebar to display workflow stages and starts the app-level timer
        for tracking workflow execution time.
        """
        from maverick.tui.app import MaverickApp

        app = cast(MaverickApp, self.app)

        # Start the app-level timer for elapsed time tracking
        app.start_timer()

        # Configure sidebar to display workflow stages
        sidebar = app.get_sidebar()
        stages_data: list[StageDict] = [
            {
                "name": stage_name,
                "display_name": stage_name.replace("_", " ").title(),
                "status": "pending",
            }
            for stage_name in self._stages
        ]
        if sidebar is not None:
            sidebar.set_workflow_mode(stages_data)

    def cleanup_sidebar(self) -> None:
        """Reset sidebar to navigation mode.

        Should be called when exiting the workflow screen to restore
        the sidebar to its default navigation menu state.
        """
        from maverick.tui.app import MaverickApp

        app = cast(MaverickApp, self.app)
        sidebar = app.get_sidebar()
        if sidebar is not None:
            sidebar.set_navigation_mode()

    def update_stage(self, stage_name: str, status: str) -> None:
        """Update the status of a workflow stage.

        Updates both the on-screen stage indicator and the sidebar's workflow
        stage display.

        Args:
            stage_name: Name of the stage to update.
            status: New status ("pending", "active", "completed", "failed").
        """
        from maverick.tui.app import MaverickApp

        # Find the stage indicator widget and update its status
        stage_widget = self.query_one(f"#stage-{stage_name}", StageIndicator)
        stage_widget.status = status

        # Update sidebar stage indicator as well
        app = cast(MaverickApp, self.app)
        sidebar = app.get_sidebar()
        if sidebar is not None:
            sidebar.update_stage_status(stage_name, status)

        # Update elapsed time display
        elapsed = self.elapsed_time
        elapsed_widget = self.query_one("#workflow-elapsed", Static)
        elapsed_widget.update(f"Elapsed: {elapsed:.1f}s")

    def show_stage_error(self, stage_name: str, error: str) -> None:
        """Display an error for a failed stage.

        Args:
            stage_name: Name of the failed stage.
            error: Error message to display.
        """
        # Update the stage to failed status
        self.update_stage(stage_name, "failed")

        # Display error message
        error_widget = self.query_one("#workflow-errors", Static)
        error_text = f"[red][bold]Error in {stage_name}:[/bold] {error}[/red]"
        error_widget.update(error_text)
