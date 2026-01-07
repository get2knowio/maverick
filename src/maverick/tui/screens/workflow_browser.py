"""Workflow browser screen for discovering and selecting workflows.

This screen displays all discovered workflows from builtin, user, and project
locations, allowing users to search, filter, and select workflows to run.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.reactive import reactive
from textual.widgets import DataTable, Input, Static

from maverick.logging import get_logger
from maverick.tui.screens.base import MaverickScreen

logger = get_logger(__name__)

if TYPE_CHECKING:
    from maverick.dsl.discovery.models import DiscoveredWorkflow, DiscoveryResult


# Source display icons
SOURCE_ICONS = {
    "builtin": "\U0001f4e6",  # package emoji
    "user": "\U0001f464",  # person emoji
    "project": "\U0001f3e0",  # home emoji
}


class WorkflowBrowserScreen(MaverickScreen):
    """Browse and select workflows from discovered locations.

    This screen provides a searchable, filterable list of all available
    workflows discovered from builtin, user, and project locations.
    """

    TITLE = "Workflows"

    BINDINGS = [
        Binding("enter", "select_workflow", "Select", show=True),
        Binding("s", "cycle_source_filter", "Filter Source", show=True),
        Binding("/", "focus_search", "Search", show=True),
        Binding("escape", "go_back", "Back", show=True),
        Binding("r", "refresh", "Refresh", show=True),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
    ]

    # Reactive state
    source_filter: reactive[str] = reactive("all")
    search_query: reactive[str] = reactive("")
    loading: reactive[bool] = reactive(True)

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Initialize the workflow browser screen."""
        super().__init__(name=name, id=id, classes=classes)
        self._discovery_result: DiscoveryResult | None = None
        self._workflows: list[DiscoveredWorkflow] = []
        self._filtered_workflows: list[DiscoveredWorkflow] = []

    def compose(self) -> ComposeResult:
        """Create the workflow browser layout."""
        yield Static(
            "[bold]Select a Workflow[/bold]",
            id="browser-title",
        )
        yield Static(
            "[dim]Press / to search, s to filter by source[/dim]",
            id="browser-help",
        )
        yield Input(
            placeholder="Search workflows...",
            id="search-input",
        )
        yield Static(
            "Source: All",
            id="source-filter-label",
        )

        with Vertical(id="workflow-table-container"):
            table: DataTable[str] = DataTable(id="workflow-table")
            table.cursor_type = "row"
            table.zebra_stripes = True
            yield table

        yield Static("", id="workflow-count")

    def on_mount(self) -> None:
        """Initialize the screen and load workflows."""
        super().on_mount()

        # Set up the table columns
        table = self.query_one("#workflow-table", DataTable)
        table.add_column("", key="source_icon", width=3)
        table.add_column("Name", key="name", width=25)
        table.add_column("Description", key="description")
        table.add_column("Inputs", key="inputs", width=8)

        # Load workflows
        self._load_workflows()

    def _load_workflows(self) -> None:
        """Load workflows from discovery system.

        Uses a background worker to avoid blocking the UI while discovering
        workflows from filesystem locations.
        """
        self.loading = True
        self.run_worker(
            self._discover_workflows(),
            name="workflow_discovery",
            exclusive=True,
        )

    async def _discover_workflows(self) -> None:
        """Discover workflows in a background thread.

        This method runs the synchronous discovery process in a background
        thread using asyncio.to_thread() to avoid blocking the event loop.
        """
        from maverick.dsl.discovery import WorkflowDiscoveryError, create_discovery

        try:
            discovery = create_discovery()
            # Run synchronous discovery in a background thread
            self._discovery_result = await asyncio.to_thread(discovery.discover)
            self._workflows = list(self._discovery_result.workflows)
            self._apply_filters()
        except WorkflowDiscoveryError as e:
            logger.error(
                "workflow_discovery_failed",
                error=str(e),
                error_type=type(e).__name__,
            )
            self.show_error(
                "Failed to discover workflows",
                details=str(e),
            )
            self._workflows = []
            self._filtered_workflows = []
        except OSError as e:
            logger.error(
                "workflow_discovery_io_error",
                error=str(e),
                error_type=type(e).__name__,
            )
            self.show_error(
                "Failed to read workflow files",
                details=str(e),
            )
            self._workflows = []
            self._filtered_workflows = []
        finally:
            self.loading = False
            self._update_table()

    def _apply_filters(self) -> None:
        """Apply source filter and search query to workflow list."""
        workflows = self._workflows

        # Filter by source
        if self.source_filter != "all":
            workflows = [w for w in workflows if w.source == self.source_filter]

        # Filter by search query
        if self.search_query:
            query = self.search_query.lower()
            workflows = [
                w
                for w in workflows
                if query in w.workflow.name.lower()
                or query in (w.workflow.description or "").lower()
            ]

        self._filtered_workflows = workflows

    def _update_table(self) -> None:
        """Update the table with filtered workflows."""
        table = self.query_one("#workflow-table", DataTable)
        table.clear()

        for workflow in self._filtered_workflows:
            source_icon = SOURCE_ICONS.get(workflow.source, "?")
            name = workflow.workflow.name
            description = workflow.workflow.description or "[dim]No description[/dim]"
            # Truncate description if too long
            if len(description) > 50:
                description = description[:47] + "..."
            input_count = len(workflow.workflow.inputs)

            table.add_row(
                source_icon,
                name,
                description,
                str(input_count),
                key=name,
            )

        # Update count label
        count_label = self.query_one("#workflow-count", Static)
        total = len(self._workflows)
        filtered = len(self._filtered_workflows)
        if filtered == total:
            count_label.update(f"[dim]{total} workflows[/dim]")
        else:
            count_label.update(f"[dim]{filtered} of {total} workflows[/dim]")

    def watch_source_filter(self, new_filter: str) -> None:
        """React to source filter changes."""
        # Update label
        label = self.query_one("#source-filter-label", Static)
        filter_display = new_filter.capitalize() if new_filter != "all" else "All"
        label.update(f"Source: {filter_display}")

        # Re-apply filters
        self._apply_filters()
        self._update_table()

    def watch_search_query(self, new_query: str) -> None:
        """React to search query changes."""
        self._apply_filters()
        self._update_table()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle search input changes."""
        if event.input.id == "search-input":
            self.search_query = event.value

    def action_focus_search(self) -> None:
        """Focus the search input."""
        search_input = self.query_one("#search-input", Input)
        search_input.focus()

    def action_cycle_source_filter(self) -> None:
        """Cycle through source filters."""
        filters = ["all", "builtin", "user", "project"]
        current_idx = filters.index(self.source_filter)
        next_idx = (current_idx + 1) % len(filters)
        self.source_filter = filters[next_idx]

    def action_select_workflow(self) -> None:
        """Select the highlighted workflow and navigate to input screen."""
        table = self.query_one("#workflow-table", DataTable)

        if not self._filtered_workflows:
            return

        # Get selected row
        row_key = table.cursor_row
        if row_key is None or row_key >= len(self._filtered_workflows):
            return

        selected_workflow = self._filtered_workflows[row_key]

        # Navigate to input screen
        from maverick.tui.screens.workflow_input import WorkflowInputScreen

        self.app.push_screen(WorkflowInputScreen(workflow=selected_workflow))

    def action_go_back(self) -> None:
        """Go back to previous screen."""
        self.app.pop_screen()

    def action_refresh(self) -> None:
        """Refresh the workflow list."""
        self._load_workflows()

    def action_cursor_down(self) -> None:
        """Move cursor down in the table."""
        table = self.query_one("#workflow-table", DataTable)
        table.action_cursor_down()

    def action_cursor_up(self) -> None:
        """Move cursor up in the table."""
        table = self.query_one("#workflow-table", DataTable)
        table.action_cursor_up()
