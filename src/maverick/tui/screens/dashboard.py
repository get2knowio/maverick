"""Dashboard screen for Maverick TUI.

This module provides the DashboardScreen, a LazyGit-inspired multi-pane
interface that serves as the main entry point for the application.

Layout:
    ┌──────────────┬──────────────────────┬───────────────────────────┐
    │ Workflows    │ Workflow Detail      │ Live Output               │
    │ (25%)        │ (35%)                │ (40%)                     │
    └──────────────┴──────────────────────┴───────────────────────────┘

Feature: TUI Dramatic Improvement
Date: 2026-01-12
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.css.query import NoMatches
from textual.reactive import reactive
from textual.widgets import Button, DataTable, Input, Static

from maverick.logging import get_logger
from maverick.tui.history import WorkflowHistoryEntry, WorkflowHistoryStore
from maverick.tui.input_history import get_input_history_store
from maverick.tui.models.widget_state import StreamingPanelState
from maverick.tui.screens.base import MaverickScreen
from maverick.tui.widgets.agent_streaming_panel import AgentStreamingPanel

if TYPE_CHECKING:
    from maverick.dsl.discovery.models import DiscoveredWorkflow, DiscoveryResult

logger = get_logger(__name__)

# Source display icons
SOURCE_ICONS = {
    "builtin": "\U0001f4e6",  # package emoji
    "user": "\U0001f464",  # person emoji
    "project": "\U0001f3e0",  # home emoji
}

# Pane identifiers for focus management
PANE_IDS = ["workflows-pane", "detail-pane", "output-pane"]


class DashboardScreen(MaverickScreen):
    """Multi-pane dashboard screen inspired by LazyGit.

    This screen provides a unified interface for:
    - Browsing and selecting workflows (left pane)
    - Viewing workflow details and inputs (center pane)
    - Monitoring live output and recent activity (right pane)

    Key design principles:
    - Zero context switching - all relevant info visible
    - Keyboard-first navigation with discoverable shortcuts
    - Tab between panes, vim-style movement within panes
    """

    TITLE = "Dashboard"

    BINDINGS = [
        # Pane navigation
        Binding("tab", "focus_next_pane", "Next Pane", show=True),
        Binding("shift+tab", "focus_previous_pane", "Prev Pane", show=False),
        # Workflow actions
        Binding("enter", "run_workflow", "Run", show=True),
        Binding("r", "quick_run", "Quick Run", show=True),
        Binding("e", "edit_inputs", "Edit Inputs", show=True),
        # Search and filter
        Binding("/", "focus_search", "Search", show=True),
        Binding("s", "cycle_source_filter", "Filter", show=False),
        # Navigation
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("g", "cursor_top", "Top", show=False),
        Binding("G", "cursor_bottom", "Bottom", show=False),
        # Global
        Binding("r", "refresh", "Refresh", show=True),
        Binding("?", "show_help", "Help", show=True),
        Binding("q", "quit_app", "Quit", show=True),
    ]

    # Reactive state
    source_filter: reactive[str] = reactive("all")
    search_query: reactive[str] = reactive("")
    loading: reactive[bool] = reactive(True)
    focused_pane: reactive[int] = reactive(0)

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Initialize the dashboard screen."""
        super().__init__(name=name, id=id, classes=classes)
        self._discovery_result: DiscoveryResult | None = None
        self._workflows: list[DiscoveredWorkflow] = []
        self._filtered_workflows: list[DiscoveredWorkflow] = []
        self._recent_entries: list[WorkflowHistoryEntry] = []
        self._streaming_state = StreamingPanelState(visible=True)

    def compose(self) -> ComposeResult:
        """Create the dashboard layout with three panes."""
        with Horizontal(id="dashboard-container"):
            # Left pane: Workflow list
            with Vertical(id="workflows-pane", classes="pane focused"):
                yield Static("[bold]Workflows[/bold]", classes="pane-header")
                yield Input(
                    placeholder="Search...",
                    id="search-input",
                    classes="search-input",
                )
                yield Static(
                    "All sources", id="source-filter-label", classes="filter-label"
                )
                with ScrollableContainer(id="workflow-table-container"):
                    table: DataTable[str] = DataTable(id="workflow-table")
                    table.cursor_type = "row"
                    table.zebra_stripes = True
                    yield table
                yield Static("", id="workflow-count", classes="count-label")

            # Center pane: Workflow detail
            with Vertical(id="detail-pane", classes="pane"):
                yield Static("[bold]Details[/bold]", classes="pane-header")
                with ScrollableContainer(id="detail-content"):
                    yield Static(
                        "[dim]Select a workflow to view details[/dim]",
                        id="detail-text",
                    )
                with Horizontal(id="detail-actions", classes="action-bar"):
                    yield Button("Run", id="run-btn", variant="primary")
                    yield Button("Edit Inputs", id="edit-btn", variant="default")

            # Right pane: Live output
            with Vertical(id="output-pane", classes="pane"):
                yield Static("[bold]Live Output[/bold]", classes="pane-header")
                yield AgentStreamingPanel(
                    self._streaming_state,
                    id="dashboard-streaming",
                )
                yield Static("[bold]Recent Runs[/bold]", classes="section-header")
                with ScrollableContainer(id="recent-container"):
                    yield Static(
                        "[dim]No recent runs[/dim]",
                        id="recent-list",
                    )

    def on_mount(self) -> None:
        """Initialize the dashboard and load data."""
        super().on_mount()

        # Set up the workflow table columns
        try:
            table = self.query_one("#workflow-table", DataTable)
            table.add_column("", key="source_icon", width=3)
            table.add_column("Name", key="name", width=20)
            table.add_column("Description", key="description")
        except NoMatches:
            pass

        # Load workflows and history
        self._load_workflows()
        self._load_history()

    def _load_workflows(self) -> None:
        """Load workflows from discovery system."""
        self.loading = True
        self.run_worker(
            self._discover_workflows(),
            name="workflow_discovery",
            exclusive=True,
        )

    async def _discover_workflows(self) -> None:
        """Discover workflows in a background thread."""
        from maverick.dsl.discovery import WorkflowDiscoveryError, create_discovery

        try:
            discovery = create_discovery()
            self._discovery_result = await asyncio.to_thread(discovery.discover)
            self._workflows = list(self._discovery_result.workflows)
            self._apply_filters()
        except WorkflowDiscoveryError as e:
            logger.error(
                "workflow_discovery_failed",
                error=str(e),
                error_type=type(e).__name__,
            )
            self._workflows = []
            self._filtered_workflows = []
        except OSError as e:
            logger.error(
                "workflow_discovery_io_error",
                error=str(e),
                error_type=type(e).__name__,
            )
            self._workflows = []
            self._filtered_workflows = []
        finally:
            self.loading = False
            self._update_table()

    def _load_history(self) -> None:
        """Load recent workflow runs from history store."""
        try:
            store = WorkflowHistoryStore()
            self._recent_entries = list(store.get_recent(5))
            self._update_recent_list()
        except Exception:
            self._recent_entries = []

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
        """Update the workflow table with filtered workflows."""
        try:
            table = self.query_one("#workflow-table", DataTable)
        except NoMatches:
            return

        table.clear()

        for workflow in self._filtered_workflows:
            source_icon = SOURCE_ICONS.get(workflow.source, "?")
            name = workflow.workflow.name
            description = workflow.workflow.description or "[dim]No description[/dim]"
            # Truncate description if too long
            if len(description) > 35:
                description = description[:32] + "..."

            table.add_row(
                source_icon,
                name,
                description,
                key=name,
            )

        # Update count label
        try:
            count_label = self.query_one("#workflow-count", Static)
            total = len(self._workflows)
            filtered = len(self._filtered_workflows)
            if filtered == total:
                count_label.update(f"[dim]{total} workflows[/dim]")
            else:
                count_label.update(f"[dim]{filtered}/{total}[/dim]")
        except NoMatches:
            pass

        # Update detail pane if we have selection
        self._update_detail_pane()

    def _update_detail_pane(self) -> None:
        """Update the detail pane with selected workflow info."""
        try:
            detail_text = self.query_one("#detail-text", Static)
            table = self.query_one("#workflow-table", DataTable)
        except NoMatches:
            return

        if not self._filtered_workflows:
            detail_text.update("[dim]No workflows available[/dim]")
            return

        # Get selected workflow
        row_idx = table.cursor_row
        if row_idx is None or row_idx >= len(self._filtered_workflows):
            detail_text.update("[dim]Select a workflow[/dim]")
            return

        workflow = self._filtered_workflows[row_idx]
        wf = workflow.workflow

        # Build detail content
        lines = [
            f"[bold]{wf.name}[/bold]",
            "",
            f"[dim]Source:[/dim] {workflow.source}",
            f"[dim]Path:[/dim] {workflow.file_path}",
            "",
        ]

        if wf.description:
            lines.append(f"{wf.description}")
            lines.append("")

        if wf.inputs:
            lines.append("[bold]Inputs:[/bold]")
            for name, inp in wf.inputs.items():
                required = "[red]*[/red]" if inp.required else ""
                default = f" = {inp.default}" if inp.default is not None else ""
                lines.append(f"  {required}{name}: {inp.type.value}{default}")
        else:
            lines.append("[dim]No inputs required[/dim]")

        detail_text.update("\n".join(lines))

    def _update_recent_list(self) -> None:
        """Update the recent runs list."""
        try:
            recent_list = self.query_one("#recent-list", Static)
        except NoMatches:
            return

        if not self._recent_entries:
            recent_list.update("[dim]No recent runs[/dim]")
            return

        lines = []
        for entry in self._recent_entries:
            status_icon = {
                "completed": "[green]\u2713[/green]",
                "failed": "[red]\u2717[/red]",
                "in_progress": "[yellow]\u25cf[/yellow]",
            }.get(entry.final_status, "[dim]\u25cb[/dim]")

            lines.append(f"{status_icon} [{entry.workflow_type}] {entry.branch_name}")

        recent_list.update("\n".join(lines))

    # --- Reactive watchers ---

    def watch_source_filter(self, new_filter: str) -> None:
        """React to source filter changes."""
        try:
            label = self.query_one("#source-filter-label", Static)
            filter_display = new_filter.capitalize() if new_filter != "all" else "All"
            label.update(f"{filter_display} sources")
        except NoMatches:
            pass

        self._apply_filters()
        self._update_table()

    def watch_search_query(self, new_query: str) -> None:
        """React to search query changes."""
        self._apply_filters()
        self._update_table()

    def watch_focused_pane(self, old_idx: int, new_idx: int) -> None:
        """Update visual focus indicator when pane changes."""
        for i, pane_id in enumerate(PANE_IDS):
            try:
                pane = self.query_one(f"#{pane_id}", Vertical)
                if i == new_idx:
                    pane.add_class("focused")
                else:
                    pane.remove_class("focused")
            except NoMatches:
                pass

    # --- Event handlers ---

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle search input changes."""
        if event.input.id == "search-input":
            self.search_query = event.value

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Handle workflow selection changes."""
        self._update_detail_pane()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "run-btn":
            self.action_run_workflow()
        elif event.button.id == "edit-btn":
            self.action_edit_inputs()

    # --- Actions ---

    def action_focus_next_pane(self) -> None:
        """Focus the next pane (Tab key)."""
        self.focused_pane = (self.focused_pane + 1) % len(PANE_IDS)
        self._focus_current_pane()

    def action_focus_previous_pane(self) -> None:
        """Focus the previous pane (Shift+Tab)."""
        self.focused_pane = (self.focused_pane - 1) % len(PANE_IDS)
        self._focus_current_pane()

    def _focus_current_pane(self) -> None:
        """Set focus to the appropriate widget in the current pane."""
        pane_id = PANE_IDS[self.focused_pane]
        try:
            if pane_id == "workflows-pane":
                table = self.query_one("#workflow-table", DataTable)
                table.focus()
            elif pane_id == "detail-pane":
                btn = self.query_one("#run-btn", Button)
                btn.focus()
            elif pane_id == "output-pane":
                container = self.query_one("#recent-container", ScrollableContainer)
                container.focus()
        except NoMatches:
            pass

    def action_focus_search(self) -> None:
        """Focus the search input (/ key)."""
        try:
            search_input = self.query_one("#search-input", Input)
            search_input.focus()
            self.focused_pane = 0  # Workflows pane
        except NoMatches:
            pass

    def action_cycle_source_filter(self) -> None:
        """Cycle through source filters (s key)."""
        filters = ["all", "builtin", "user", "project"]
        current_idx = filters.index(self.source_filter)
        next_idx = (current_idx + 1) % len(filters)
        self.source_filter = filters[next_idx]

    def action_run_workflow(self) -> None:
        """Run the selected workflow (Enter key)."""
        try:
            table = self.query_one("#workflow-table", DataTable)
        except NoMatches:
            return

        if not self._filtered_workflows:
            return

        row_idx = table.cursor_row
        if row_idx is None or row_idx >= len(self._filtered_workflows):
            return

        selected_workflow = self._filtered_workflows[row_idx]

        # If workflow has required inputs, go to input screen
        # Otherwise, go directly to execution
        from maverick.tui.screens.workflow_input import WorkflowInputScreen

        self.app.push_screen(WorkflowInputScreen(workflow=selected_workflow))

    def action_edit_inputs(self) -> None:
        """Edit inputs for the selected workflow (e key)."""
        # Same as run for now - input screen handles both
        self.action_run_workflow()

    def action_quick_run(self) -> None:
        """Quick run the selected workflow with previous inputs (r key).

        If the workflow has saved input history, runs directly with those inputs.
        Otherwise, falls back to the input screen.
        """
        try:
            table = self.query_one("#workflow-table", DataTable)
        except NoMatches:
            return

        if not self._filtered_workflows:
            return

        row_idx = table.cursor_row
        if row_idx is None or row_idx >= len(self._filtered_workflows):
            return

        selected_workflow = self._filtered_workflows[row_idx]
        workflow_name = selected_workflow.workflow.name

        # Check for input history
        history_store = get_input_history_store()
        last_entry = history_store.get_last_inputs(workflow_name)

        if last_entry:
            # Run directly with previous inputs
            from maverick.tui.screens.workflow_execution import WorkflowExecutionScreen

            # Save these inputs again (updates timestamp)
            history_store.save_inputs(workflow_name, last_entry.inputs)

            self.app.push_screen(
                WorkflowExecutionScreen(
                    workflow=selected_workflow.workflow,
                    inputs=last_entry.inputs,
                )
            )
            self.notify(
                f"Running with inputs from {last_entry.display_timestamp}",
                severity="information",
            )
        else:
            # No history, go to input screen
            from maverick.tui.screens.workflow_input import WorkflowInputScreen

            self.app.push_screen(WorkflowInputScreen(workflow=selected_workflow))
            self.notify(
                "No previous inputs found. Please configure inputs.",
                severity="warning",
            )

    def action_cursor_down(self) -> None:
        """Move cursor down (j key)."""
        if self.focused_pane == 0:
            try:
                table = self.query_one("#workflow-table", DataTable)
                table.action_cursor_down()
            except NoMatches:
                pass

    def action_cursor_up(self) -> None:
        """Move cursor up (k key)."""
        if self.focused_pane == 0:
            try:
                table = self.query_one("#workflow-table", DataTable)
                table.action_cursor_up()
            except NoMatches:
                pass

    def action_cursor_top(self) -> None:
        """Move cursor to top (g key)."""
        if self.focused_pane == 0:
            try:
                table = self.query_one("#workflow-table", DataTable)
                table.move_cursor(row=0)
            except NoMatches:
                pass

    def action_cursor_bottom(self) -> None:
        """Move cursor to bottom (G key)."""
        if self.focused_pane == 0:
            try:
                table = self.query_one("#workflow-table", DataTable)
                if self._filtered_workflows:
                    table.move_cursor(row=len(self._filtered_workflows) - 1)
            except NoMatches:
                pass

    def action_refresh(self) -> None:
        """Refresh workflows and history (r key)."""
        self._load_workflows()
        self._load_history()

    def action_show_help(self) -> None:
        """Show help panel (? key)."""
        # Will be implemented with HelpPanel widget
        # For now, show in log
        from maverick.tui.app import MaverickApp

        if isinstance(self.app, MaverickApp):
            self.app.add_log(
                "Help: Tab=switch panes, Enter=run, /=search, ?=help",
                "info",
                "dashboard",
            )
            self.app.add_log(
                "  j/k=up/down, g/G=top/bottom, s=filter source", "info", "dashboard"
            )
            self.app.add_log("  r=refresh, q=quit", "info", "dashboard")

    def action_quit_app(self) -> None:
        """Quit the application (q key)."""
        self.app.exit()

    # --- Public methods for external updates ---

    def add_streaming_entry(
        self, text: str, step_name: str = "", agent_name: str = ""
    ) -> None:
        """Add an entry to the live output panel.

        This method can be called from workflow runners to update
        the dashboard's live output pane.

        Args:
            text: The text to display.
            step_name: Name of the current step.
            agent_name: Name of the agent producing output.
        """
        import time

        from maverick.tui.models.enums import StreamChunkType
        from maverick.tui.models.widget_state import AgentStreamEntry

        entry = AgentStreamEntry(
            timestamp=time.time(),
            step_name=step_name,
            agent_name=agent_name,
            text=text,
            chunk_type=StreamChunkType.OUTPUT,
        )

        try:
            panel = self.query_one("#dashboard-streaming", AgentStreamingPanel)
            panel.append_chunk(entry)
        except NoMatches:
            pass

    def refresh_history(self) -> None:
        """Refresh the recent runs list.

        Called when a workflow completes to update the history display.
        """
        self._load_history()
