"""Historical workflow review screen for Maverick TUI.

This module provides a read-only view of completed workflow runs from history.
Users can review past workflow details including status, stages, findings, and PR links.
"""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Static

from maverick.tui.history import WorkflowHistoryEntry
from maverick.tui.screens.base import MaverickScreen

__all__ = ["HistoricalReviewScreen"]


class HistoricalReviewScreen(MaverickScreen):
    """Read-only view of a historical workflow.

    Displays detailed information about a completed workflow run including:
    - Workflow type (Fly/Refuel)
    - Branch name
    - Final status (completed/failed)
    - Timestamp
    - Stages completed
    - Finding counts by severity
    - PR link (if available)

    Attributes:
        entry: The workflow history entry to display.

    Example:
        ```python
        # From HomeScreen, when user selects a history entry
        entry = self.recent_workflows[selected_index]
        self.app.push_screen(HistoricalReviewScreen(entry=entry))
        ```
    """

    TITLE = "Workflow History"

    BINDINGS = [
        Binding("escape", "go_back", "Back", show=True),
    ]

    def __init__(self, entry: WorkflowHistoryEntry, **kwargs: Any) -> None:
        """Initialize the historical review screen.

        Args:
            entry: The workflow history entry to display.
            **kwargs: Additional arguments passed to MaverickScreen.
        """
        super().__init__(**kwargs)
        self.entry = entry

    def compose(self) -> ComposeResult:
        """Create the screen layout.

        Yields:
            ComposeResult: Screen components displaying workflow history details.
        """
        with VerticalScroll(id="content-container"):
            # Header section
            with Vertical(id="header"):
                yield Static(
                    f"[bold]{self.entry.workflow_type.title()} Workflow[/bold]",
                    classes="title",
                )
                yield Static(f"Branch: [bold]{self.entry.branch_name}[/bold]")
                yield Static(f"Status: {self.entry.display_status}")
                yield Static(f"Date: {self.entry.display_timestamp}")

            # Details section
            with Vertical(id="details"):
                yield Static("Details", classes="section-title")

                if self.entry.pr_link:
                    pr_text = f"Pull Request: {self.entry.pr_link}"
                    yield Static(
                        f"[link={self.entry.pr_link}]{pr_text}[/link]",
                        classes="detail-line",
                    )
                else:
                    yield Static(
                        "Pull Request: [dim]Not available[/dim]",
                        classes="detail-line",
                    )

            # Stages section
            with Vertical(id="stages"):
                yield Static("Stages Completed", classes="section-title")

                if self.entry.stages_completed:
                    for stage in self.entry.stages_completed:
                        yield Static(f"✓ {stage}", classes="detail-line")
                else:
                    yield Static(
                        "[dim]No stages completed[/dim]",
                        classes="detail-line",
                    )

            # Findings section
            with Vertical(id="findings"):
                yield Static("Findings Summary", classes="section-title")

                error_count = self.entry.finding_counts.get("error", 0)
                warning_count = self.entry.finding_counts.get("warning", 0)
                suggestion_count = self.entry.finding_counts.get("suggestion", 0)

                if error_count > 0:
                    yield Static(
                        f"[red]✗ Errors:[/red] {error_count}",
                        classes="detail-line",
                    )
                if warning_count > 0:
                    yield Static(
                        f"[yellow]! Warnings:[/yellow] {warning_count}",
                        classes="detail-line",
                    )
                if suggestion_count > 0:
                    yield Static(
                        f"[blue]→ Suggestions:[/blue] {suggestion_count}",
                        classes="detail-line",
                    )

                if error_count == 0 and warning_count == 0 and suggestion_count == 0:
                    yield Static(
                        "[green]No findings[/green]",
                        classes="detail-line",
                    )

        # Action buttons
        with Horizontal(id="actions"):
            yield Button("Back", id="back-btn", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events.

        Args:
            event: The button pressed event.
        """
        if event.button.id == "back-btn":
            self.action_go_back()


__all__ = [
    "HistoricalReviewScreen",
]
