"""Maverick TUI application.

This module provides the main MaverickApp class, the entry point for the
Maverick terminal user interface built with Textual.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.command import Hit, Hits, Provider
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Header, Static

from maverick.tui.models import NavigationContext, NavigationEntry
from maverick.tui.widgets.log_panel import LogPanel
from maverick.tui.widgets.shortcut_footer import ShortcutFooter
from maverick.tui.widgets.sidebar import Sidebar

if TYPE_CHECKING:
    from textual.screen import Screen as TextualScreen

    # Type alias for Textual Screen without result type (Screen[None])
    Screen = TextualScreen[None]


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
            (
                "Go to Settings",
                "Navigate to settings",
                app.action_show_config,
            ),
            ("Go to Review", "Navigate to review screen", app.action_go_review),
            (
                "Go to Workflow",
                "Navigate to workflow screen",
                app.action_go_workflow,
            ),
            (
                "Settings",
                "Navigate to settings screen",
                app.action_show_settings,
            ),
            (
                "Toggle Log Panel",
                "Show or hide log panel",
                app.action_toggle_log,
            ),
            (
                "Start Workflow",
                "Start a new workflow",
                app.action_start_workflow,
            ),
            ("Refresh", "Refresh current screen", app.action_refresh),
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
        Binding("?", "show_help_panel", "Help", show=True),
        Binding("ctrl+comma", "show_config", "Settings", show=False),
        Binding("ctrl+h", "go_home", "Home", show=False),
    ]

    def __init__(self) -> None:
        """Initialize the MaverickApp."""
        super().__init__()
        self._timer_start: float | None = None
        self._timer_running: bool = False
        self._current_workflow: str = ""
        self._current_branch: str = ""
        self._navigation_context = NavigationContext()

    def compose(self) -> ComposeResult:
        """Create the app layout.

        Yields:
            ComposeResult: Header, main container with sidebar and content,
                          log panel, shortcut footer, and size warning overlay.
        """
        yield Header()
        with Horizontal(id="main-container"):
            yield Sidebar(id="sidebar")
            yield Vertical(id="content-area")
        yield LogPanel(id="log-panel")
        yield ShortcutFooter(id="shortcut-footer")
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
        """Initialize the app with DashboardScreen."""
        from maverick.tui.screens.dashboard import DashboardScreen

        # Check initial terminal size and set layout class
        self._check_terminal_size()
        self._update_layout_class()
        # Set up timer interval to update header subtitle every second
        self.set_interval(1.0, self._update_header_subtitle)
        await self.push_screen(DashboardScreen())

    # Responsive layout breakpoints (terminal width in columns)
    LAYOUT_COMPACT_THRESHOLD = 100
    LAYOUT_WIDE_THRESHOLD = 150

    def on_resize(self) -> None:
        """Handle terminal resize events.

        Shows warning overlay if terminal is below minimum size (80x24).
        Also updates responsive layout classes based on terminal width.
        """
        self._check_terminal_size()
        self._update_layout_class()

    def on_screen_resume(self) -> None:
        """Handle screen resume (screen becomes active after pop).

        Refreshes the shortcut footer to show current screen's shortcuts.
        """
        self._refresh_shortcut_footer()

    def _refresh_shortcut_footer(self) -> None:
        """Refresh the shortcut footer with current screen's bindings."""
        try:
            footer = self.query_one("#shortcut-footer", ShortcutFooter)
            footer.refresh_shortcuts()
        except Exception:
            # Footer not mounted yet
            pass

    def _check_terminal_size(self) -> None:
        """Check terminal size and show/hide warning overlay.

        Shows a warning overlay when terminal is smaller than MIN_WIDTH x MIN_HEIGHT.
        """
        width = self.size.width
        height = self.size.height

        try:
            warning = self.query_one("#min-size-warning", Container)
            if width < self.MIN_WIDTH or height < self.MIN_HEIGHT:
                warning.add_class("visible")
            else:
                warning.remove_class("visible")
        except Exception:
            # Widget not yet mounted, skip size check
            pass

    def _update_layout_class(self) -> None:
        """Update responsive layout class based on terminal width.

        Applies one of three layout modes:
        - layout-compact: < 100 columns (narrower panels, hide secondary content)
        - layout-normal: 100-150 columns (default 3-pane layout)
        - layout-wide: > 150 columns (wider panels, more detail space)

        The corresponding CSS classes adjust panel widths and visibility
        to provide graceful degradation on narrow terminals.
        """
        width = self.size.width

        # Remove existing layout classes
        self.remove_class("layout-compact", "layout-normal", "layout-wide")

        # Apply appropriate layout class based on width
        if width < self.LAYOUT_COMPACT_THRESHOLD:
            self.add_class("layout-compact")
        elif width > self.LAYOUT_WIDE_THRESHOLD:
            self.add_class("layout-wide")
        else:
            self.add_class("layout-normal")

    def action_toggle_log(self) -> None:
        """Toggle log panel visibility (Ctrl+L)."""
        try:
            log_panel = self.query_one(LogPanel)
            log_panel.toggle()
        except Exception:
            # Widget not yet mounted, skip toggle
            pass

    async def action_pop_screen(self) -> None:
        """Go back to previous screen (Escape)."""
        if len(self.screen_stack) > 1:
            self.pop_screen()

    @property
    def navigation_context(self) -> NavigationContext:
        """Get the current navigation context."""
        return self._navigation_context

    def push_screen_tracked(
        self, screen: Screen, params: dict[str, Any] | None = None
    ) -> None:
        """Push a screen with navigation tracking.

        Updates the navigation context history.

        Args:
            screen: Screen to push.
            params: Optional parameters passed to the screen.
        """
        from datetime import datetime

        entry = NavigationEntry(
            screen_name=type(screen).__name__,
            params=params or {},
            timestamp=datetime.now().isoformat(),
        )
        self._navigation_context = NavigationContext(
            history=self._navigation_context.history + (entry,)
        )
        self.push_screen(screen)

    def pop_screen_tracked(self) -> None:
        """Pop a screen with navigation tracking.

        Updates the navigation context history.
        """
        if self._navigation_context.can_go_back:
            self._navigation_context = NavigationContext(
                history=self._navigation_context.history[:-1]
            )
        self.pop_screen()

    async def action_quit(self) -> None:
        """Quit the application (q)."""
        self.exit()

    def action_show_help_panel(self) -> None:
        """Show the help panel overlay (?)."""
        from maverick.tui.widgets.help_panel import HelpPanel

        self.push_screen(HelpPanel())

    def action_show_help(self) -> None:
        """Show keybindings help in log (legacy)."""
        self.add_log("Help: Press Ctrl+P for command palette", "info", "app")
        self.add_log("  Ctrl+L: Toggle log panel", "info", "app")
        self.add_log("  Escape: Go back", "info", "app")
        self.add_log("  q: Quit application", "info", "app")
        self.add_log("  Ctrl+,: Settings", "info", "app")
        # Make sure log panel is visible to show help
        try:
            log_panel = self.query_one(LogPanel)
            if not log_panel.panel_visible:
                log_panel.toggle()
        except Exception:
            # Widget not yet mounted, skip toggle
            pass

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

        self.push_screen_tracked(ConfigScreen())

    def action_go_review(self) -> None:
        """Navigate to review screen."""
        from maverick.tui.screens.review import ReviewScreen

        self.push_screen_tracked(ReviewScreen())

    def action_go_workflow(self) -> None:
        """Navigate to workflow screen."""
        from maverick.tui.screens.workflow import WorkflowScreen

        self.push_screen_tracked(
            WorkflowScreen(workflow_name="New Workflow", branch_name="main"),
            params={"workflow_name": "New Workflow", "branch_name": "main"},
        )

    def action_refresh(self) -> None:
        """Refresh the current screen."""
        # Trigger a refresh by removing and re-adding the current screen
        if hasattr(self.screen, "refresh"):
            self.screen.refresh()
        else:
            # Generic refresh - just log it
            self.add_log("Screen refreshed", "info", "app")

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
        try:
            log_panel = self.query_one(LogPanel)
            log_panel.add_log(message, level, source)
        except Exception:
            # Widget not yet mounted, skip logging
            pass

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

    def get_sidebar(self) -> Sidebar | None:
        """Get the sidebar widget.

        Returns:
            The Sidebar widget instance, or None if not mounted.
        """
        try:
            return self.query_one(Sidebar)
        except Exception:
            return None

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
        try:
            header = self.query_one(Header)
            header.subtitle = ""  # type: ignore[attr-defined]
        except Exception:
            # Widget not yet mounted, skip clear
            pass

    def action_show_settings(self) -> None:
        """Navigate to settings screen."""
        from maverick.tui.screens.settings import SettingsScreen

        self.push_screen_tracked(SettingsScreen())

    def _update_header_subtitle(self) -> None:
        """Update the header subtitle with workflow info and elapsed time."""
        if self._current_workflow:
            elapsed = self.elapsed_time
            minutes = int(elapsed // 60)
            seconds = int(elapsed % 60)
            time_str = f"{minutes:02d}:{seconds:02d}"
            subtitle = f"{self._current_workflow}"
            if self._current_branch:
                subtitle += f" ({self._current_branch})"
            subtitle += f" - {time_str}"
            try:
                header = self.query_one(Header)
                header.subtitle = subtitle  # type: ignore[attr-defined]
            except Exception:
                # Widget not yet mounted, skip update
                pass

    def push_screen_timed(self, screen: Screen) -> float:
        """Push screen and return transition time in milliseconds.

        Measures the time taken to push a screen onto the stack and logs a
        warning if the transition exceeds 300ms. This helps identify slow
        screen transitions that may impact user experience.

        Args:
            screen: Screen to push onto the stack.

        Returns:
            Elapsed time in milliseconds for the screen push operation.

        Example:
            ```python
            # Push screen with timing measurement
            elapsed = app.push_screen_timed(SettingsScreen())

            # Log will show: "Slow transition: 450ms" if > 300ms
            ```

        Note:
            A transition time over 300ms is considered slow and will generate
            a warning log entry. Target response time is <200ms per SC-003
            performance requirements.
        """
        start = time.perf_counter()
        self.push_screen(screen)
        elapsed = (time.perf_counter() - start) * 1000

        if elapsed > 300:
            self.add_log(
                f"Slow screen transition: {elapsed:.0f}ms (target: <300ms)",
                "warning",
                "performance",
            )

        return elapsed
