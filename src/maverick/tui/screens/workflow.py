from __future__ import annotations

import time
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Static

from maverick.tui.widgets.stage_indicator import StageIndicator

if TYPE_CHECKING:
    pass


class WorkflowScreen(Screen):
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
        self._elapsed_time: float = 0.0
        self._start_time: float = time.time()

    @property
    def workflow_name(self) -> str:
        """Get the current workflow name."""
        return self._workflow_name

    @property
    def elapsed_time(self) -> float:
        """Get elapsed time in seconds."""
        return time.time() - self._start_time

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

    def update_stage(self, stage_name: str, status: str) -> None:
        """Update the status of a workflow stage.

        Args:
            stage_name: Name of the stage to update.
            status: New status ("pending", "active", "completed", "failed").
        """
        # Find the stage indicator widget and update its status
        stage_widget = self.query_one(f"#stage-{stage_name}", StageIndicator)
        stage_widget.status = status

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
