"""Progress timeline widget for workflow execution visualization.

This widget provides a visual timeline showing step durations as
horizontal bars, with color-coded status and current step highlighting.

Feature: TUI Dramatic Improvement - Sprint 2
Date: 2026-01-12
"""

from __future__ import annotations

from dataclasses import dataclass

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widget import Widget
from textual.widgets import Static


@dataclass(frozen=True, slots=True)
class TimelineStep:
    """A step in the timeline."""

    name: str
    status: str  # pending, running, completed, failed, skipped
    duration_seconds: float | None = None
    estimated_seconds: float | None = None


class ProgressTimeline(Widget):
    """Visual timeline showing step durations as horizontal bars.

    This widget displays a compact horizontal timeline where each step
    is represented by a bar whose width is proportional to its duration.
    Color indicates status.

    Example:
        timeline = ProgressTimeline()
        timeline.set_steps([
            TimelineStep("validate", "completed", duration_seconds=1.5),
            TimelineStep("implement", "running", estimated_seconds=30),
            TimelineStep("review", "pending", estimated_seconds=10),
        ])

    Visual representation:
        [====validate====][=======implement=======][==review==]
         (green, 1.5s)    (yellow, running)        (dim, pending)
    """

    DEFAULT_CSS = """
    ProgressTimeline {
        height: 3;
        width: 100%;
        padding: 0 1;
    }

    ProgressTimeline .timeline-header {
        height: 1;
        width: 100%;
    }

    ProgressTimeline .timeline-bar-container {
        height: 1;
        width: 100%;
    }

    ProgressTimeline .timeline-bar {
        height: 1;
    }

    ProgressTimeline .timeline-labels {
        height: 1;
        width: 100%;
    }

    /* Status colors for bars */
    ProgressTimeline .bar-pending {
        background: $surface-elevated;
        color: $text-dim;
    }

    ProgressTimeline .bar-running {
        background: $accent;
        color: $text;
    }

    ProgressTimeline .bar-completed {
        background: $success;
        color: $text;
    }

    ProgressTimeline .bar-failed {
        background: $error;
        color: $text;
    }

    ProgressTimeline .bar-skipped {
        background: $text-dim;
        color: $text-muted;
    }
    """

    def __init__(
        self,
        *,
        show_labels: bool = True,
        show_durations: bool = True,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Initialize the progress timeline.

        Args:
            show_labels: Show step names below bars.
            show_durations: Show duration/estimate on bars.
            name: Widget name.
            id: Widget ID.
            classes: CSS classes.
        """
        super().__init__(name=name, id=id, classes=classes)
        self._steps: list[TimelineStep] = []
        self._show_labels = show_labels
        self._show_durations = show_durations

    def compose(self) -> ComposeResult:
        """Create the timeline layout."""
        yield Static("", id="timeline-header", classes="timeline-header")
        yield Horizontal(id="timeline-bars", classes="timeline-bar-container")
        if self._show_labels:
            yield Static("", id="timeline-labels", classes="timeline-labels")

    def on_mount(self) -> None:
        """Render initial state."""
        self._update_display()

    def set_steps(self, steps: list[TimelineStep]) -> None:
        """Set the steps to display.

        Args:
            steps: List of TimelineStep objects.
        """
        self._steps = steps
        self._update_display()

    def update_step(
        self,
        name: str,
        status: str | None = None,
        duration_seconds: float | None = None,
    ) -> None:
        """Update a single step's status or duration.

        Args:
            name: Step name to update.
            status: New status (if changing).
            duration_seconds: Actual duration (if known).
        """
        for i, step in enumerate(self._steps):
            if step.name == name:
                self._steps[i] = TimelineStep(
                    name=step.name,
                    status=status if status is not None else step.status,
                    duration_seconds=(
                        duration_seconds
                        if duration_seconds is not None
                        else step.duration_seconds
                    ),
                    estimated_seconds=step.estimated_seconds,
                )
                break
        self._update_display()

    def _update_display(self) -> None:
        """Update the timeline display."""
        if not self.is_mounted:
            return

        self._update_header()
        self._update_bars()
        if self._show_labels:
            self._update_labels()

    def _update_header(self) -> None:
        """Update the header with total duration."""
        try:
            header = self.query_one("#timeline-header", Static)
        except Exception:
            return

        if not self._steps:
            header.update("[dim]No steps[/dim]")
            return

        # Calculate totals
        completed = sum(1 for s in self._steps if s.status == "completed")
        total = len(self._steps)
        total_duration = sum(
            s.duration_seconds for s in self._steps if s.duration_seconds
        )

        # Find current step
        current = next((s for s in self._steps if s.status == "running"), None)
        current_str = f" | Current: {current.name}" if current else ""

        header.update(
            f"Progress: {completed}/{total} steps | "
            f"Elapsed: {self._format_duration(total_duration)}{current_str}"
        )

    def _update_bars(self) -> None:
        """Update the bar display."""
        try:
            container = self.query_one("#timeline-bars", Horizontal)
        except Exception:
            return

        # Clear existing bars
        for child in list(container.children):
            child.remove()

        if not self._steps:
            return

        # Calculate total time for proportional widths
        total_time = self._get_total_time()
        if total_time <= 0:
            total_time = len(self._steps)  # Equal widths if no durations

        # Create bars
        for step in self._steps:
            step_time = self._get_step_time(step)
            # Calculate width as percentage (minimum 5% for visibility)
            width_pct = max(5, int((step_time / total_time) * 100))

            # Build bar content
            if self._show_durations and step.duration_seconds:
                label = f" {self._format_duration(step.duration_seconds)} "
            elif self._show_durations and step.status == "running":
                label = " ... "
            else:
                label = ""

            # Truncate label if needed
            bar = Static(
                label,
                classes=f"timeline-bar bar-{step.status}",
            )
            bar.styles.width = f"{width_pct}%"
            container.mount(bar)

    def _update_labels(self) -> None:
        """Update the labels display."""
        try:
            labels = self.query_one("#timeline-labels", Static)
        except Exception:
            return

        if not self._steps:
            labels.update("")
            return

        # Build label string
        total_time = self._get_total_time()
        if total_time <= 0:
            total_time = len(self._steps)

        parts = []
        for step in self._steps:
            step_time = self._get_step_time(step)
            width_pct = max(5, int((step_time / total_time) * 100))
            # Truncate name to fit width (rough estimate: 1 char per 2%)
            max_len = max(3, width_pct // 3)
            name = step.name[:max_len] if len(step.name) > max_len else step.name
            parts.append(name.center(max(5, width_pct // 2)))

        labels.update(" ".join(parts))

    def _get_total_time(self) -> float:
        """Get total time for all steps."""
        total = 0.0
        for step in self._steps:
            total += self._get_step_time(step)
        return total

    def _get_step_time(self, step: TimelineStep) -> float:
        """Get time for a single step (actual or estimated)."""
        if step.duration_seconds is not None:
            return step.duration_seconds
        if step.estimated_seconds is not None:
            return step.estimated_seconds
        return 1.0  # Default 1 second for unknown

    def _format_duration(self, seconds: float | None) -> str:
        """Format duration for display."""
        if seconds is None or seconds == 0:
            return "0s"
        if seconds < 1:
            return f"{int(seconds * 1000)}ms"
        if seconds < 60:
            return f"{seconds:.1f}s"
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}m{secs}s"

    @property
    def total_duration(self) -> float:
        """Get total actual duration of completed steps."""
        return sum(s.duration_seconds for s in self._steps if s.duration_seconds) or 0.0

    @property
    def estimated_remaining(self) -> float:
        """Get estimated remaining time based on pending/running steps."""
        remaining = 0.0
        for step in self._steps:
            if step.status in ("pending", "running"):
                if step.estimated_seconds:
                    remaining += step.estimated_seconds
                else:
                    remaining += 1.0  # Default estimate
        return remaining
