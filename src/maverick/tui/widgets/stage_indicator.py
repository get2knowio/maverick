from __future__ import annotations

from textual.reactive import reactive
from textual.widget import Widget


class StageIndicator(Widget):
    """Displays a workflow stage with status icon."""

    DEFAULT_CSS = """
    StageIndicator {
        height: 1;
    }
    """

    ICONS = {
        "pending": "○",
        "active": "◉",
        "completed": "✓",
        "failed": "✗",
    }

    name: reactive[str] = reactive("")
    status: reactive[str] = reactive("pending")

    def __init__(
        self,
        name: str,
        status: str = "pending",
        *,
        id: str | None = None,
    ) -> None:
        super().__init__(id=id)
        self.name = name
        self.status = status

    def render(self) -> str:
        """Render the stage indicator."""
        icon = self.ICONS.get(self.status, "○")
        return f"{icon} {self.name}"

    def watch_status(self, old_status: str, new_status: str) -> None:
        """Update CSS class when status changes."""
        self.remove_class(old_status)
        self.add_class(new_status)
