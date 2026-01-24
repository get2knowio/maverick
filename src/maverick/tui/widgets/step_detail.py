"""Step detail panel widget for displaying current step information.

This widget displays detailed information about the currently executing
workflow step, including token usage and cost tracking for agent steps.

Feature: TUI Step Detail Panel with Token/Cost Tracking
Date: 2026-01-24
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Static

from maverick.tui.models.widget_state import UnifiedStreamState


class StepDetailPanel(Widget):
    """Panel showing details about the current/selected workflow step.

    Displays:
    - Step name and type
    - Status (running/completed/failed)
    - Elapsed time
    - Token usage and cost (for agent steps)
    - Aggregate workflow metrics

    Attributes:
        _state: Reference to the UnifiedStreamState for data.

    Example:
        state = UnifiedStreamState(workflow_name="fly-workflow", total_steps=5)
        panel = StepDetailPanel(state)

        # State is updated externally, then panel refreshes
        state.start_step("implement_task", "agent")
        panel.refresh_display()
    """

    DEFAULT_CSS = """
    StepDetailPanel {
        height: auto;
        max-height: 12;
        padding: 1;
        border: solid $surface-lighten-1;
        border-title-color: $text;
    }

    StepDetailPanel .detail-header {
        text-style: bold;
    }

    StepDetailPanel .detail-metrics {
        margin-top: 1;
        color: $text-muted;
    }

    StepDetailPanel .detail-aggregate {
        margin-top: 1;
        padding-top: 1;
    }

    StepDetailPanel .no-selection {
        color: $text-muted;
        text-style: italic;
    }

    StepDetailPanel .metric-label {
        color: $text-muted;
    }

    StepDetailPanel .metric-value {
        color: $text;
    }

    StepDetailPanel .metric-cost {
        color: $success;
    }
    """

    def __init__(
        self,
        state: UnifiedStreamState,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Initialize the StepDetailPanel.

        Args:
            state: Reference to the UnifiedStreamState for data.
            name: Widget name.
            id: Widget ID.
            classes: CSS classes.
        """
        super().__init__(name=name, id=id, classes=classes)
        self._state = state
        self.border_title = "Detail"

    def compose(self) -> ComposeResult:
        """Compose the panel layout.

        Returns:
            ComposeResult containing the panel components.
        """
        with Vertical():
            yield Static(id="detail-content")

    def on_mount(self) -> None:
        """Update content when mounted."""
        self._update_content()

    def _update_content(self) -> None:
        """Update the detail content based on current state."""
        content = self.query_one("#detail-content", Static)

        if self._state.current_step is None:
            content.update("[dim italic]No step selected[/dim italic]")
            return

        lines: list[str] = []

        # Header: step name and type
        step_type = self._state.current_step_type or "unknown"
        step_type_icon = self._get_step_type_icon(step_type)
        lines.append(
            f"[bold]{step_type_icon} {self._state.current_step}[/bold] "
            f"[dim]({step_type})[/dim]"
        )

        # Metrics row: elapsed, tokens, cost
        elapsed = self._state.current_step_elapsed_formatted
        tokens = self._format_tokens(self._state.current_step_tokens)
        cost = self._format_cost(self._state.current_step_cost)

        lines.append("")
        lines.append(
            f"[dim]Elapsed:[/dim] {elapsed}  "
            f"[dim]Tokens:[/dim] {tokens}  "
            f"[dim]Cost:[/dim] {cost}"
        )

        # Separator
        lines.append("")
        lines.append("[dim]" + "-" * 40 + "[/dim]")

        # Aggregate metrics
        step_progress = (
            f"{self._state.completed_steps + self._state.failed_steps}"
            f"/{self._state.total_steps}"
        )
        if self._state.failed_steps > 0:
            step_progress += f" [red]({self._state.failed_steps} failed)[/red]"

        total_tokens = self._format_tokens(self._state.total_tokens)
        total_cost = self._format_cost(self._state.total_cost)

        lines.append("")
        lines.append(
            f"[dim]Workflow:[/dim] {step_progress}  "
            f"[dim]Total tokens:[/dim] {total_tokens}  "
            f"[dim]Total cost:[/dim] {total_cost}"
        )

        content.update("\n".join(lines))

    def _get_step_type_icon(self, step_type: str) -> str:
        """Get an icon for the step type.

        Args:
            step_type: The type of step.

        Returns:
            An emoji/icon representing the step type.
        """
        icons = {
            "python": "\u2699",  # gear
            "agent": "\U0001f916",  # robot
            "generate": "\u270d",  # writing hand
            "validate": "\u2713",  # checkmark
            "checkpoint": "\U0001f4be",  # floppy disk
            "subworkflow": "\U0001f500",  # shuffle
            "branch": "\U0001f500",  # shuffle
            "loop": "\U0001f501",  # repeat
        }
        return icons.get(step_type, "\u2022")  # bullet as default

    def _format_tokens(self, tokens: int) -> str:
        """Format token count for display.

        Args:
            tokens: Number of tokens.

        Returns:
            Formatted string with comma separators or "--" if zero.
        """
        if tokens <= 0:
            return "--"
        return f"{tokens:,}"

    def _format_cost(self, cost: float) -> str:
        """Format cost for display.

        Args:
            cost: Cost in USD.

        Returns:
            Formatted string with dollar sign or "--" if zero.
        """
        if cost <= 0:
            return "--"
        return f"[green]${cost:.4f}[/green]"

    def refresh_display(self) -> None:
        """Refresh the panel display with current state."""
        if self.is_mounted:
            self._update_content()
