"""Aggregate stats bar widget for workflow execution.

Displays a single-line summary of step statuses, total tokens, and total cost
during workflow execution. Designed to sit between the compact header and the
main execution area.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.widgets import Static

if TYPE_CHECKING:
    from maverick.tui.models.widget_state import UnifiedStreamState


class AggregateStatsBar(Static):
    """Single-line stats bar showing aggregate workflow statistics.

    Displays step status counts (running, completed, failed, pending),
    total tokens consumed, and total cost.

    Args:
        state: Reference to the UnifiedStreamState tracking workflow data.
        name: Widget name.
        id: Widget ID.
        classes: CSS classes.
    """

    def __init__(
        self,
        state: UnifiedStreamState,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._state = state

    def refresh_display(self) -> None:
        """Update the stats bar content from current state."""
        self.update(self._format_stats())

    def _format_stats(self) -> str:
        """Format the aggregate statistics string.

        Returns:
            Rich-markup formatted stats string.
        """
        state = self._state

        # Calculate pending and running counts
        total = state.total_steps
        completed = state.completed_steps
        failed = state.failed_steps
        finished = completed + failed

        # Determine running: 1 if a step is actively running, else 0
        running = 1 if state.current_step is not None and finished < total else 0
        pending = max(0, total - finished - running)

        parts: list[str] = []

        if running > 0:
            parts.append(f"[dodger_blue1]\u25cf {running} running[/]")
        if completed > 0:
            parts.append(f"[green]\u2713 {completed} completed[/]")
        if failed > 0:
            parts.append(f"[red]\u2717 {failed} failed[/]")
        if pending > 0:
            parts.append(f"[dim white]\u25cb {pending} pending[/]")

        if not parts:
            parts.append("[dim]No steps[/]")

        tokens = state.total_tokens
        cost = state.total_cost

        pipe = " \u2502 "
        joined = pipe.join(parts)
        return (
            f"  {joined}  \u2502  "
            f"[dim]Tokens:[/] {tokens:,}  \u2502  "
            f"[dim]Cost:[/] ${cost:.4f}"
        )
