"""Collapsible step group widget for workflow execution.

This widget provides a collapsible container for step widgets that:
- Auto-collapses when all contained steps are completed
- Expands when a step starts running or fails
- Shows a summary when collapsed

Feature: TUI Dramatic Improvement - Sprint 2
Date: 2026-01-12
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Collapsible, Static

if TYPE_CHECKING:
    pass


class StepGroupStatus(str, Enum):
    """Status of a step group."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    MIXED = "mixed"  # Some completed, some failed


@dataclass(frozen=True, slots=True)
class StepSummary:
    """Summary of steps in a group."""

    total: int
    completed: int
    failed: int
    running: int
    pending: int

    @property
    def status(self) -> StepGroupStatus:
        """Determine overall group status."""
        if self.running > 0:
            return StepGroupStatus.RUNNING
        if self.failed > 0 and self.completed > 0:
            return StepGroupStatus.MIXED
        if self.failed > 0:
            return StepGroupStatus.FAILED
        if self.completed == self.total:
            return StepGroupStatus.COMPLETED
        if self.pending == self.total:
            return StepGroupStatus.PENDING
        return StepGroupStatus.RUNNING

    @property
    def display_text(self) -> str:
        """Generate display text for collapsed state."""
        parts = []
        if self.completed > 0:
            parts.append(f"[green]{self.completed} completed[/green]")
        if self.failed > 0:
            parts.append(f"[red]{self.failed} failed[/red]")
        if self.running > 0:
            parts.append(f"[yellow]{self.running} running[/yellow]")
        if self.pending > 0:
            parts.append(f"[dim]{self.pending} pending[/dim]")
        return ", ".join(parts) if parts else "[dim]No steps[/dim]"


class StepGroup(Widget):
    """Collapsible container for workflow steps.

    This widget groups related steps and provides:
    - Collapsible header with group name
    - Auto-collapse when all steps complete successfully
    - Auto-expand when a step fails or starts running
    - Summary display in collapsed state

    Example:
        group = StepGroup(name="Implementation", auto_collapse=True)

        # Add steps
        group.add_step("validate", "completed")
        group.add_step("implement", "running")

        # Update step status
        group.update_step("implement", "completed")
    """

    DEFAULT_CSS = """
    StepGroup {
        height: auto;
        width: 100%;
        margin: 0 0 1 0;
    }

    StepGroup .group-header {
        height: auto;
        padding: 0 1;
    }

    StepGroup .group-title {
        text-style: bold;
    }

    StepGroup .group-summary {
        color: $text-muted;
        margin-left: 2;
    }

    StepGroup .group-content {
        padding: 0 0 0 2;
    }

    StepGroup .step-item {
        height: 1;
        padding: 0 1;
    }

    /* Status colors */
    StepGroup.status-pending .group-title {
        color: $text-muted;
    }

    StepGroup.status-running .group-title {
        color: $accent;
    }

    StepGroup.status-completed .group-title {
        color: $success;
    }

    StepGroup.status-failed .group-title {
        color: $error;
    }

    StepGroup.status-mixed .group-title {
        color: $warning;
    }
    """

    class StepStatusChanged(Message):
        """Message sent when a step's status changes."""

        def __init__(self, group_name: str, step_name: str, status: str) -> None:
            super().__init__()
            self.group_name = group_name
            self.step_name = step_name
            self.status = status

    class GroupExpanded(Message):
        """Message sent when group is expanded."""

        def __init__(self, group_name: str) -> None:
            super().__init__()
            self.group_name = group_name

    class GroupCollapsed(Message):
        """Message sent when group is collapsed."""

        def __init__(self, group_name: str) -> None:
            super().__init__()
            self.group_name = group_name

    # Reactive state
    collapsed: reactive[bool] = reactive(False)

    def __init__(
        self,
        name: str,
        *,
        auto_collapse: bool = True,
        initially_collapsed: bool = False,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Initialize the step group.

        Args:
            name: Display name for the group.
            auto_collapse: Auto-collapse when all steps complete.
            initially_collapsed: Start in collapsed state.
            id: Widget ID.
            classes: CSS classes.
        """
        super().__init__(id=id, classes=classes)
        self._group_name: str = name
        self._auto_collapse = auto_collapse
        self._steps: dict[str, str] = {}  # step_name -> status
        self._step_durations: dict[str, float] = {}  # step_name -> duration_seconds
        self.collapsed = initially_collapsed

    def compose(self) -> ComposeResult:
        """Create the step group layout."""
        with (
            Collapsible(title=self._build_title(), collapsed=self.collapsed),
            Vertical(classes="group-content"),
        ):
            yield Static("[dim]No steps[/dim]", id="steps-placeholder")

    def _build_title(self) -> str:
        """Build the collapsible title with summary."""
        summary = self._get_summary()
        icon = self._get_status_icon(summary.status)
        if self.collapsed and self._steps:
            return f"{icon} {self._group_name} ({summary.display_text})"
        return f"{icon} {self._group_name}"

    def _get_status_icon(self, status: StepGroupStatus) -> str:
        """Get icon for status."""
        icons = {
            StepGroupStatus.PENDING: "[dim]\u25cb[/dim]",
            StepGroupStatus.RUNNING: "[yellow]\u25cf[/yellow]",
            StepGroupStatus.COMPLETED: "[green]\u2713[/green]",
            StepGroupStatus.FAILED: "[red]\u2717[/red]",
            StepGroupStatus.MIXED: "[yellow]\u26a0[/yellow]",
        }
        return icons.get(status, "[dim]\u25cb[/dim]")

    def _get_summary(self) -> StepSummary:
        """Calculate step summary."""
        completed = sum(1 for s in self._steps.values() if s == "completed")
        failed = sum(1 for s in self._steps.values() if s == "failed")
        running = sum(1 for s in self._steps.values() if s == "running")
        pending = sum(1 for s in self._steps.values() if s == "pending")
        return StepSummary(
            total=len(self._steps),
            completed=completed,
            failed=failed,
            running=running,
            pending=pending,
        )

    def _update_status_class(self) -> None:
        """Update CSS class based on current status."""
        summary = self._get_summary()
        # Remove all status classes
        for status in StepGroupStatus:
            self.remove_class(f"status-{status.value}")
        # Add current status class
        self.add_class(f"status-{summary.status.value}")

    def _update_title(self) -> None:
        """Update the collapsible title."""
        try:
            collapsible = self.query_one(Collapsible)
            collapsible.title = self._build_title()
        except Exception:
            pass

    def _rebuild_steps(self) -> None:
        """Rebuild the step list display."""
        try:
            content = self.query_one(".group-content", Vertical)
        except Exception:
            return

        # Clear existing content
        for child in list(content.children):
            child.remove()

        if not self._steps:
            content.mount(Static("[dim]No steps[/dim]", id="steps-placeholder"))
            return

        # Add step items
        for step_name, status in self._steps.items():
            icon = self._get_step_icon(status)
            duration = self._step_durations.get(step_name)
            duration_str = f" ({self._format_duration(duration)})" if duration else ""
            text = f"{icon} {step_name}{duration_str}"
            content.mount(Static(text, classes="step-item"))

    def _get_step_icon(self, status: str) -> str:
        """Get icon for step status."""
        icons = {
            "pending": "[dim]\u25cb[/dim]",
            "running": "[yellow]\u25cf[/yellow]",
            "completed": "[green]\u2713[/green]",
            "failed": "[red]\u2717[/red]",
            "skipped": "[dim]-[/dim]",
        }
        return icons.get(status, "[dim]\u25cb[/dim]")

    def _format_duration(self, seconds: float | None) -> str:
        """Format duration for display."""
        if seconds is None:
            return ""
        if seconds < 1:
            return f"{int(seconds * 1000)}ms"
        if seconds < 60:
            return f"{seconds:.1f}s"
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}m{secs}s"

    def watch_collapsed(self, collapsed: bool) -> None:
        """Handle collapse state changes."""
        self._update_title()
        if collapsed:
            self.post_message(self.GroupCollapsed(self._group_name))
        else:
            self.post_message(self.GroupExpanded(self._group_name))

    def on_collapsible_toggled(self, event: Collapsible.Toggled) -> None:
        """Handle collapsible toggle."""
        self.collapsed = event.collapsible.collapsed

    # --- Public API ---

    def add_step(self, step_name: str, status: str = "pending") -> None:
        """Add a step to the group.

        Args:
            step_name: Name of the step.
            status: Initial status (pending, running, completed, failed, skipped).
        """
        self._steps[step_name] = status
        self._rebuild_steps()
        self._update_title()
        self._update_status_class()

    def update_step(
        self, step_name: str, status: str, duration: float | None = None
    ) -> None:
        """Update a step's status.

        Args:
            step_name: Name of the step.
            status: New status.
            duration: Optional duration in seconds.
        """
        if step_name not in self._steps:
            self.add_step(step_name, status)
            return

        self._steps[step_name] = status

        if duration is not None:
            self._step_durations[step_name] = duration

        self._rebuild_steps()
        self._update_title()
        self._update_status_class()

        # Post status change message
        self.post_message(self.StepStatusChanged(self._group_name, step_name, status))

        # Auto-collapse/expand logic
        if self._auto_collapse:
            summary = self._get_summary()
            if status in ("running", "failed") and self.collapsed:
                # Expand when a step starts running or fails
                self.collapsed = False
                try:
                    collapsible = self.query_one(Collapsible)
                    collapsible.collapsed = False
                except Exception:
                    pass
            elif summary.status == StepGroupStatus.COMPLETED and not self.collapsed:
                # Collapse when all steps complete successfully
                self.collapsed = True
                try:
                    collapsible = self.query_one(Collapsible)
                    collapsible.collapsed = True
                except Exception:
                    pass

    def remove_step(self, step_name: str) -> None:
        """Remove a step from the group.

        Args:
            step_name: Name of the step to remove.
        """
        self._steps.pop(step_name, None)
        self._step_durations.pop(step_name, None)
        self._rebuild_steps()
        self._update_title()
        self._update_status_class()

    def expand_group(self) -> None:
        """Expand the group."""
        self.collapsed = False
        try:
            collapsible = self.query_one(Collapsible)
            collapsible.collapsed = False
        except Exception:
            pass

    def collapse_group(self) -> None:
        """Collapse the group."""
        self.collapsed = True
        try:
            collapsible = self.query_one(Collapsible)
            collapsible.collapsed = True
        except Exception:
            pass

    @property
    def summary(self) -> StepSummary:
        """Get current step summary."""
        return self._get_summary()

    @property
    def total_duration(self) -> float:
        """Get total duration of all steps."""
        return sum(self._step_durations.values())
