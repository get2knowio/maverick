"""Maverick TUI application.

This module provides the main MaverickApp class, the entry point for the
Maverick terminal user interface built with Textual.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.command import Hit, Hits, Provider
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Footer, Header, Static

from maverick.tui.widgets.log_panel import LogPanel
from maverick.tui.widgets.sidebar import Sidebar

if TYPE_CHECKING:
    pass


class MaverickCommands(Provider):
    """Command palette provider for Maverick commands."""

    async def search(self, query: str) -> Hits:
        """Search for Maverick commands.

        Args:
            query: Search query string.

        Yields:
            Command hits matching the query.
        """
        app = self.app
        assert isinstance(app, MaverickApp)

        commands = [
            ("Go to Home", "Navigate to the home screen", app.action_go_home),
            ("Go to Settings", "Navigate to settings", app.action_show_config),
            ("Toggle Log Panel", "Show or hide log panel", app.action_toggle_log),
            ("Start Workflow", "Start a new workflow", app.action_start_workflow),
            ("Show Help", "Display keybinding help", app.action_show_help),
        ]

        query_lower = query.lower()
        for name, description, callback in commands:
            if query_lower in name.lower() or query_lower in description.lower():
                yield Hit(
                    score=1,
                    match_display=name,
                    command=callback,
                    text=name,
                    help=description,
                )


class MaverickApp(App[None]):
    """Maverick TUI application.

    The main application class for the Maverick terminal user interface.
    Provides the base layout with header, sidebar, content area, log panel,
    and footer.
    """

    CSS_PATH = Path(__file__).parent / "maverick.tcss"
    TITLE = "Maverick"
    ENABLE_COMMAND_PALETTE = True
    COMMANDS = {MaverickCommands}

    # Minimum terminal size requirements
    MIN_WIDTH = 80
    MIN_HEIGHT = 24

    BINDINGS = [
        Binding("ctrl+l", "toggle_log", "Toggle Log", show=True),
        Binding("escape", "pop_screen", "Back", show=True),
        Binding("q", "quit", "Quit", show=True),
        Binding("?", "show_help", "Help", show=False),
        Binding("ctrl+comma", "show_config", "Settings", show=False),
    ]

    def __init__(self) -> None:
        """Initialize the MaverickApp."""
        super().__init__()
        self._timer_start: float | None = None
        self._timer_running: bool = False

    def compose(self) -> ComposeResult:
        """Create the app layout.

        Yields:
            ComposeResult: Header, main container with sidebar and content,
                          log panel, footer, and size warning overlay.
        """
        yield Header()
        with Horizontal(id="main-container"):
            yield Sidebar(id="sidebar")
            yield Vertical(id="content-area")
        yield LogPanel(id="log-panel")
        yield Footer()
        # Minimum size warning overlay (hidden by default)
        with Container(id="min-size-warning"):
            yield Static(
                (
                    "[bold red]Terminal Too Small[/bold red]\n\n"
                    f"Minimum size: {self.MIN_WIDTH}x{self.MIN_HEIGHT}\n"
                    "Please resize your terminal."
                ),
                id="min-size-warning-text",
            )

    async def on_mount(self) -> None:
        """Initialize the app with HomeScreen."""
        from maverick.tui.screens.home import HomeScreen

        # Check initial terminal size
        self._check_terminal_size()
        await self.push_screen(HomeScreen())

    def on_resize(self) -> None:
        """Handle terminal resize events.

        Shows warning overlay if terminal is below minimum size (80x24).
        """
        self._check_terminal_size()

    def _check_terminal_size(self) -> None:
        """Check terminal size and show/hide warning overlay.

        Shows a warning overlay when terminal is smaller than MIN_WIDTH x MIN_HEIGHT.
        """
        width = self.size.width
        height = self.size.height

        warning = self.query_one("#min-size-warning", Container)

        if width < self.MIN_WIDTH or height < self.MIN_HEIGHT:
            warning.add_class("visible")
        else:
            warning.remove_class("visible")

    def action_toggle_log(self) -> None:
        """Toggle log panel visibility (Ctrl+L)."""
        log_panel = self.query_one(LogPanel)
        log_panel.toggle()

    def action_pop_screen(self) -> None:
        """Go back to previous screen (Escape)."""
        if len(self.screen_stack) > 1:
            self.pop_screen()

    def action_quit(self) -> None:
        """Quit the application (q)."""
        self.exit()

    def action_show_help(self) -> None:
        """Show keybindings help (?)."""
        self.add_log("Help: Press Ctrl+P for command palette", "info", "app")
        self.add_log("  Ctrl+L: Toggle log panel", "info", "app")
        self.add_log("  Escape: Go back", "info", "app")
        self.add_log("  q: Quit application", "info", "app")
        self.add_log("  Ctrl+,: Settings", "info", "app")
        # Make sure log panel is visible to show help
        log_panel = self.query_one(LogPanel)
        if not log_panel.visible:
            log_panel.toggle()

    def action_go_home(self) -> None:
        """Navigate to home screen."""
        # Pop all screens and push home
        while len(self.screen_stack) > 1:
            self.pop_screen()

    def action_start_workflow(self) -> None:
        """Start a new workflow."""
        from maverick.tui.screens.workflow import WorkflowScreen

        self.push_screen(
            WorkflowScreen(workflow_name="New Workflow", branch_name="main")
        )

    def action_show_config(self) -> None:
        """Navigate to config screen (Ctrl+,)."""
        from maverick.tui.screens.config import ConfigScreen

        self.push_screen(ConfigScreen())

    def add_log(
        self,
        message: str,
        level: str = "info",
        source: str = "",
    ) -> None:
        """Add a log entry to the log panel.

        Convenience method that delegates to the LogPanel widget.

        Args:
            message: Log message content.
            level: Log level ("info", "success", "warning", "error").
            source: Source component/agent name.
        """
        log_panel = self.query_one(LogPanel)
        log_panel.add_log(message, level, source)

    def start_timer(self) -> None:
        """Start the elapsed time timer.

        Called when a workflow starts to track execution time.
        """
        self._timer_start = time.time()
        self._timer_running = True

    def stop_timer(self) -> None:
        """Stop the elapsed time timer.

        Called when a workflow completes or fails.
        """
        self._timer_running = False

    @property
    def elapsed_time(self) -> float:
        """Get current elapsed time in seconds.

        Returns:
            Elapsed time in seconds, or 0.0 if timer not started.
        """
        if self._timer_start is None:
            return 0.0
        if self._timer_running:
            return time.time() - self._timer_start
        return 0.0

    def get_sidebar(self) -> Sidebar:
        """Get the sidebar widget.

        Returns:
            The Sidebar widget instance.
        """
        return self.query_one(Sidebar)

    def set_workflow_info(self, workflow_name: str, branch_name: str = "") -> None:
        """Set the current workflow info in the header.

        Updates the header subtitle with the workflow name and elapsed time.

        Args:
            workflow_name: Name of the workflow being executed.
            branch_name: Git branch name (optional).
        """
        self._current_workflow = workflow_name
        self._current_branch = branch_name
        self._update_header_subtitle()

    def clear_workflow_info(self) -> None:
        """Clear the workflow info from the header."""
        self._current_workflow = ""
        self._current_branch = ""
        header = self.query_one(Header)
        header.sub_title = ""

    def _update_header_subtitle(self) -> None:
        """Update the header subtitle with workflow info and elapsed time."""
        if hasattr(self, "_current_workflow") and self._current_workflow:
            elapsed = self.elapsed_time
            minutes = int(elapsed // 60)
            seconds = int(elapsed % 60)
            time_str = f"{minutes:02d}:{seconds:02d}"
            subtitle = f"{self._current_workflow}"
            if hasattr(self, "_current_branch") and self._current_branch:
                subtitle += f" ({self._current_branch})"
            subtitle += f" - {time_str}"
            header = self.query_one(Header)
            header.sub_title = subtitle
