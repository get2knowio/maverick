"""BreadcrumbBar widget for showing current scope path.

Displays the current filter scope as clickable breadcrumb segments:
    All steps > implement_by_phase > [0] > validate_phase
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Static


class BreadcrumbBar(Widget):
    """Single-line breadcrumb showing the current scope path.

    Posts ``BreadcrumbSegmentClicked`` when a segment is clicked.
    Hidden when no scope is active.
    """

    class BreadcrumbSegmentClicked(Message):
        """Posted when a breadcrumb segment is clicked."""

        def __init__(self, path: str | None) -> None:
            self.path = path
            super().__init__()

    DEFAULT_CSS = """
    BreadcrumbBar {
        height: 1;
        width: 100%;
        padding: 0 1;
        background: $surface;
        color: $text-muted;
    }

    BreadcrumbBar.hidden {
        display: none;
    }
    """

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)
        self._current_path: str | None = None
        self._label = Static("", id="breadcrumb-label")

    def compose(self) -> ComposeResult:
        yield self._label

    def set_path(self, path: str | None) -> None:
        """Update the displayed breadcrumb path.

        Args:
            path: Current filter path, or None to hide.
        """
        self._current_path = path

        if path is None:
            self.add_class("hidden")
            self._label.update("")
            return

        self.remove_class("hidden")
        segments = path.split("/")
        # Build breadcrumb: "All steps > seg1 > seg2 > ..."
        parts = ["[bold]All steps[/bold]"]
        for seg in segments:
            parts.append(f"[dim]>[/dim] {seg}")
        self._label.update("  ".join(parts))

    def navigate_up(self) -> str | None:
        """Navigate up one level in the breadcrumb.

        Returns:
            The new path after navigating up, or None if at root.
        """
        if self._current_path is None:
            return None

        parts = self._current_path.rsplit("/", 1)
        if len(parts) <= 1:
            # At top level — clear scope entirely
            return None
        return parts[0]
