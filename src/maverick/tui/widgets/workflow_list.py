"""Workflow list widget for Maverick TUI.

This module provides the WorkflowList widget that displays recent workflow
runs with status indicators and selection support.
"""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static


class WorkflowList(Widget):
    """Widget displaying a list of recent workflow runs.

    Shows workflow entries with branch name, type, status, and optional PR URL.
    Supports keyboard navigation and selection.
    """

    DEFAULT_CSS = """
    WorkflowList {
        height: auto;
        max-height: 100%;
        width: 100%;
    }
    """

    class WorkflowSelected(Message):
        """Message sent when a workflow is selected."""

        def __init__(self, index: int, workflow: dict[str, Any]) -> None:
            """Initialize the message.

            Args:
                index: Index of the selected workflow.
                workflow: The workflow data dictionary.
            """
            self.index = index
            self.workflow = workflow
            super().__init__()

    selected_index: reactive[int] = reactive(0)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the workflow list widget."""
        super().__init__(*args, **kwargs)
        self._workflows: list[dict[str, Any]] = []

    def compose(self) -> ComposeResult:
        """Create the workflow list layout."""
        with Vertical(id="workflow-list-container"):
            yield Static(
                "[dim]No workflows available[/dim]",
                classes="workflow-empty-message",
            )

    def set_workflows(self, workflows: list[dict[str, Any]]) -> None:
        """Set the list of workflows to display.

        Args:
            workflows: List of workflow dictionaries with:
                - branch_name (str): Git branch name
                - workflow_type (str): "fly" or "refuel"
                - status (str): "completed", "failed", "in_progress"
                - started_at (datetime or str): When workflow started
                - pr_url (str, optional): Pull request URL
        """
        self._workflows = workflows[:10]  # Limit to 10 most recent
        self.selected_index = 0
        self._rebuild_list()

    def select(self, index: int) -> None:
        """Select a workflow by index.

        Args:
            index: Workflow index (0-based).
        """
        if 0 <= index < len(self._workflows):
            self.selected_index = index
            self._update_selection()
            self.post_message(self.WorkflowSelected(index, self._workflows[index]))

    def watch_selected_index(self, old_index: int, new_index: int) -> None:
        """Handle selection changes."""
        self._update_selection()

    def _rebuild_list(self) -> None:
        """Rebuild the workflow list display."""
        container = self.query_one("#workflow-list-container", Vertical)
        # Remove children properly to clear ID registry
        for child in list(container.children):
            child.remove()

        if not self._workflows:
            container.mount(
                Static(
                    "[dim]No workflows available[/dim]",
                    classes="workflow-empty-message",
                )
            )
            return

        for i, workflow in enumerate(self._workflows):
            branch = workflow.get("branch_name", "unknown")
            wf_type = workflow.get("workflow_type", "unknown")
            status = workflow.get("status", "unknown")
            pr_url = workflow.get("pr_url", "")

            # Status icon and color
            status_display = self._get_status_display(status)

            # Format the entry
            pr_indicator = " [link]" if pr_url else ""
            text = f"{status_display} [{wf_type}] {branch}{pr_indicator}"

            classes = f"workflow-item workflow-item-{i}"
            if i == self.selected_index:
                classes += " --selected"

            container.mount(
                Static(
                    text,
                    classes=classes,
                )
            )

    def _get_status_display(self, status: str) -> str:
        """Get the display string for a status.

        Args:
            status: Workflow status string.

        Returns:
            Formatted status with icon and color.
        """
        status_map = {
            "completed": "[green]✓[/green]",
            "failed": "[red]✗[/red]",
            "in_progress": "[yellow]◉[/yellow]",
        }
        return status_map.get(status, "[dim]○[/dim]")

    def _update_selection(self) -> None:
        """Update the visual selection indicator."""
        for i in range(len(self._workflows)):
            try:
                item = self.query_one(f".workflow-item-{i}", Static)
                if i == self.selected_index:
                    item.add_class("--selected")
                else:
                    item.remove_class("--selected")
            except Exception:
                pass

    def action_select_next(self) -> None:
        """Select the next workflow."""
        if self._workflows:
            self.selected_index = min(self.selected_index + 1, len(self._workflows) - 1)

    def action_select_previous(self) -> None:
        """Select the previous workflow."""
        if self._workflows:
            self.selected_index = max(self.selected_index - 1, 0)

    def action_confirm_selection(self) -> None:
        """Confirm the current selection."""
        if self._workflows:
            self.select(self.selected_index)
