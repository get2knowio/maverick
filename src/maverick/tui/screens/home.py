"""Home screen for Maverick TUI.

This module provides the HomeScreen, the landing page that displays
workflow selection options and recent workflow runs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Static

from maverick.tui.widgets.workflow_list import WorkflowList

if TYPE_CHECKING:
    pass


class HomeScreen(Screen):
    """Home screen with workflow selection.

    The home screen displays a welcome message and recent workflow runs.
    Users can select workflows from here or navigate to other screens.
    """

    TITLE = "Home"

    BINDINGS = [
        Binding("enter", "select_workflow", "Select", show=True),
        Binding("r", "refresh", "Refresh", show=True),
        Binding("w", "start_workflow", "Start Workflow", show=True),
        Binding("j", "move_down", "Down", show=False),
        Binding("k", "move_up", "Up", show=False),
    ]

    def compose(self) -> ComposeResult:
        """Create the home screen layout.

        Yields:
            ComposeResult: Welcome message and workflow list.
        """
        yield Static(
            "[bold]Welcome to Maverick[/bold]\n\n"
            "AI-powered development workflow automation",
            id="welcome",
        )
        yield Static("Recent Workflows:", id="recent-label")
        yield WorkflowList(id="workflow-list")

    async def on_mount(self) -> None:
        """Initialize the home screen."""
        self.refresh_recent_workflows()

    def on_workflow_list_workflow_selected(
        self, event: WorkflowList.WorkflowSelected
    ) -> None:
        """Handle workflow selection from the list.

        Args:
            event: The workflow selected event.
        """
        from maverick.tui.screens.workflow import WorkflowScreen

        workflow = event.workflow
        self.app.push_screen(
            WorkflowScreen(
                workflow_name=str(workflow.get("workflow_type", "Workflow")),
                branch_name=str(workflow.get("branch_name", "main")),
            )
        )

    def action_select_workflow(self) -> None:
        """Handle workflow selection."""
        workflow_list = self.query_one(WorkflowList)
        workflow_list.action_confirm_selection()

    def action_start_workflow(self) -> None:
        """Start a new workflow."""
        from maverick.tui.screens.workflow import WorkflowScreen

        self.app.push_screen(
            WorkflowScreen(workflow_name="New Workflow", branch_name="main")
        )

    def action_refresh(self) -> None:
        """Refresh recent workflows list."""
        self.refresh_recent_workflows()

    def action_move_down(self) -> None:
        """Move selection down."""
        workflow_list = self.query_one(WorkflowList)
        workflow_list.action_select_next()

    def action_move_up(self) -> None:
        """Move selection up."""
        workflow_list = self.query_one(WorkflowList)
        workflow_list.action_select_previous()

    def refresh_recent_workflows(
        self, workflows: list[dict[str, Any]] | None = None
    ) -> None:
        """Refresh the list of recent workflow runs.

        This method updates the workflow list display with provided workflow data.
        Per the separation of concerns principle, the TUI layer should receive
        workflow data from external sources (e.g., a workflow manager or service
        layer), not generate it internally.

        Args:
            workflows: Optional list of workflow dictionaries containing workflow
                metadata (branch_name, workflow_type, status, started_at, etc.).
                If None, the workflow list will be cleared/show empty state.

        Note:
            In production, workflow data should be provided by a workflow manager
            or persistence layer, not generated within the TUI.
        """
        workflow_list = self.query_one(WorkflowList)

        if workflows is None:
            # Clear the list if no workflows provided
            workflow_list.set_workflows([])
        else:
            workflow_list.set_workflows(workflows)

    def select_workflow(self, index: int) -> None:
        """Select a workflow from the recent list.

        Args:
            index: Index of the workflow to select (0-based).
        """
        workflow_list = self.query_one(WorkflowList)
        workflow_list.select(index)
