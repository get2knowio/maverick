"""Home screen for Maverick TUI.

This module provides the HomeScreen, the landing page that displays
workflow selection options and recent workflow runs.
"""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.reactive import reactive
from textual.widgets import Static

from maverick.tui.history import WorkflowHistoryEntry, WorkflowHistoryStore
from maverick.tui.screens.base import MaverickScreen
from maverick.tui.widgets.workflow_list import WorkflowList


class HomeScreen(MaverickScreen):
    """Home screen with workflow selection.

    The home screen displays a welcome message and recent workflow runs.
    Users can select workflows from here or navigate to other screens.
    """

    TITLE = "Home"

    BINDINGS = [
        Binding("enter", "select_workflow", "Select", show=True),
        Binding("f", "navigate_fly", "Fly", show=True),
        Binding("r", "navigate_refuel", "Refuel", show=True),
        Binding("s", "navigate_settings", "Settings", show=True),
        Binding("shift+r", "refresh", "Refresh", show=True),
        Binding("w", "start_workflow", "Start Workflow", show=True),
        Binding("h", "view_history_entry", "View History", show=False),
        Binding("j", "move_down", "Down", show=False),
        Binding("k", "move_up", "Up", show=False),
    ]

    # Reactive state for history
    recent_workflows: reactive[tuple[WorkflowHistoryEntry, ...]] = reactive(())

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

    def on_mount(self) -> None:
        """Initialize the home screen and load workflow history."""
        self._load_history()
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

    def _load_history(self) -> None:
        """Load recent workflows from history store.

        Loads the last 10 workflow runs from the persistent history store
        and converts them to the format expected by WorkflowList.
        """
        try:
            store = WorkflowHistoryStore()
            entries = store.get_recent(10)
            self.recent_workflows = tuple(entries)
        except Exception:
            # If history loading fails, proceed with empty history
            self.recent_workflows = ()

    def _convert_history_to_workflows(
        self, entries: list[WorkflowHistoryEntry]
    ) -> list[dict[str, Any]]:
        """Convert history entries to workflow dict format for WorkflowList.

        Args:
            entries: List of workflow history entries.

        Returns:
            List of workflow dictionaries compatible with WorkflowList widget.
        """
        workflows = []
        for entry in entries:
            workflow = {
                "branch_name": entry.branch_name,
                "workflow_type": entry.workflow_type,
                "status": entry.final_status,
                "started_at": entry.timestamp,
            }
            if entry.pr_link:
                workflow["pr_url"] = entry.pr_link
            workflows.append(workflow)
        return workflows

    @property
    def selected_history_index(self) -> int:
        """Get the currently selected workflow index from WorkflowList.

        Returns:
            The selected index (0-based).
        """
        try:
            workflow_list = self.query_one(WorkflowList)
            return workflow_list.selected_index
        except Exception:
            return 0

    def refresh_recent_workflows(
        self, workflows: list[dict[str, Any]] | None = None
    ) -> None:
        """Refresh the list of recent workflow runs.

        This method updates the workflow list display with provided workflow data
        or loads from history store if no workflows provided.

        Args:
            workflows: Optional list of workflow dictionaries containing workflow
                metadata (branch_name, workflow_type, status, started_at, etc.).
                If None, workflows will be loaded from history store.
        """
        workflow_list = self.query_one(WorkflowList)

        if workflows is None:
            # Load from history store
            self._load_history()
            workflows = self._convert_history_to_workflows(list(self.recent_workflows))

        workflow_list.set_workflows(workflows)

    def select_workflow(self, index: int) -> None:
        """Select a workflow from the recent list.

        Args:
            index: Index of the workflow to select (0-based).
        """
        workflow_list = self.query_one(WorkflowList)
        workflow_list.select(index)

    def action_navigate_fly(self) -> None:
        """Navigate to FlyScreen.

        Bound to 'f' key. Starts a new Fly workflow by navigating to the
        FlyScreen where the user can configure and launch the workflow.
        """
        try:
            self.navigate_to("fly")
        except (ImportError, ModuleNotFoundError):
            # FlyScreen not yet implemented
            self.show_error(
                "FlyScreen not available",
                details="The Fly workflow screen has not been implemented yet.",
            )

    def action_navigate_refuel(self) -> None:
        """Navigate to RefuelScreen.

        Bound to 'r' key. Starts a new Refuel workflow by navigating to the
        RefuelScreen where the user can select and process tech debt issues.
        """
        try:
            self.navigate_to("refuel")
        except (ImportError, ModuleNotFoundError):
            # RefuelScreen not yet implemented
            self.show_error(
                "RefuelScreen not available",
                details="The Refuel workflow screen has not been implemented yet.",
            )

    def action_navigate_settings(self) -> None:
        """Navigate to SettingsScreen.

        Bound to 's' key. Opens the application settings screen where users
        can configure GitHub integration, notifications, and agent settings.
        """
        try:
            self.navigate_to("settings")
        except (ImportError, ModuleNotFoundError):
            # SettingsScreen not yet implemented
            self.show_error(
                "SettingsScreen not available",
                details="The Settings screen has not been implemented yet.",
            )

    def action_view_history_entry(self) -> None:
        """View the selected history entry.

        Bound to 'h' key. Opens the HistoricalReviewScreen for the currently
        selected workflow from the history list, providing a read-only view
        of the workflow's details, stages, findings, and PR link.
        """
        if not self.recent_workflows:
            return

        index = self.selected_history_index
        if 0 <= index < len(self.recent_workflows):
            entry = self.recent_workflows[index]
            from maverick.tui.screens.history_review import HistoricalReviewScreen

            self.app.push_screen(HistoricalReviewScreen(entry=entry))
