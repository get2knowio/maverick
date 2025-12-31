from __future__ import annotations

from datetime import datetime

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import RichLog


class LogPanel(Widget):
    """Collapsible log panel for agent output.

    Features:
    - Timestamped log entries with level-based coloring
    - Source prefix for agent identification
    - Auto-scroll behavior (scrolls to bottom on new entries)
    - 1000-line buffer limit to prevent memory issues
    - Toggle visibility with CSS-based transitions
    """

    DEFAULT_CSS = """
    LogPanel {
        height: 15;
    }
    """

    MAX_LINES = 1000

    panel_visible: reactive[bool] = reactive(False)
    auto_scroll: reactive[bool] = reactive(True)

    def compose(self) -> ComposeResult:
        """Create the log panel with RichLog widget.

        RichLog automatically:
        - Enforces MAX_LINES buffer limit (1000 lines)
        - Supports Rich markup for colored output
        - Provides efficient scrolling
        - Removes oldest lines when buffer exceeds max_lines

        The max_lines parameter ensures memory efficiency during long workflows
        by maintaining a rolling window of the most recent 1000 log entries.
        """
        yield RichLog(
            highlight=True,
            markup=True,
            max_lines=self.MAX_LINES,  # 1000-line buffer limit enforced by RichLog
            id="log-content",
        )

    def toggle(self) -> None:
        """Toggle visibility.

        Uses CSS class toggle for fast response time (<200ms).
        """
        self.panel_visible = not self.panel_visible

    def watch_panel_visible(self, panel_visible: bool) -> None:
        """Update CSS class on visibility change.

        This triggers CSS transitions for smooth show/hide.
        """
        self.set_class(panel_visible, "visible")

    def add_log(
        self,
        message: str,
        level: str = "info",
        source: str = "",
    ) -> None:
        """Add a log entry with timestamp, source, and level-based coloring.

        Args:
            message: The log message to display
            level: Log level (info, success, warning, error)
            source: Source identifier (e.g., agent name)

        The log format is:
            [dim]HH:MM:SS[/dim] [color][source] message[/color]

        Auto-scrolls to bottom if auto_scroll is enabled.
        Buffer automatically maintained at MAX_LINES by RichLog.
        """
        log = self.query_one(RichLog)

        # Level-based color mapping
        color = {
            "info": "blue",
            "success": "green",
            "warning": "yellow",
            "error": "red",
        }.get(level, "white")

        # Format: [dim]timestamp[/dim] [color][source] message[/color]
        timestamp = datetime.now().strftime("%H:%M:%S")
        prefix = f"[{source}] " if source else ""
        formatted_message = (
            f"[dim]{timestamp}[/dim] [{color}]{prefix}{message}[/{color}]"
        )

        # Write to log
        log.write(formatted_message)

        # Auto-scroll to bottom if enabled
        if self.auto_scroll:
            log.scroll_end(animate=False)

    def clear(self) -> None:
        """Clear all logs."""
        log = self.query_one(RichLog)
        log.clear()
