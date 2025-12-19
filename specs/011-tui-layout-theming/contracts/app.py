"""Application contracts for Maverick TUI.

This module defines the Protocol interface for the main MaverickApp class.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from textual.app import ComposeResult
    from textual.binding import Binding
    from textual.screen import Screen


@runtime_checkable
class MaverickAppProtocol(Protocol):
    """Protocol for the main Maverick TUI application.

    Defines the public interface for the MaverickApp class, including
    navigation, keybindings, and global state management.
    """

    # Class-level attributes
    CSS_PATH: str
    TITLE: str
    ENABLE_COMMAND_PALETTE: bool
    BINDINGS: list[Binding]

    def compose(self) -> ComposeResult:
        """Compose the app's base layout.

        Returns:
            ComposeResult yielding Header, main content container, Footer.
        """
        ...

    async def on_mount(self) -> None:
        """Called when app is mounted.

        Initializes the app by pushing the HomeScreen.
        """
        ...

    # Navigation actions
    def action_toggle_log(self) -> None:
        """Toggle the log panel visibility (Ctrl+L)."""
        ...

    def action_pop_screen(self) -> None:
        """Go back to previous screen (Escape)."""
        ...

    def action_quit(self) -> None:
        """Quit the application (q)."""
        ...

    def action_show_help(self) -> None:
        """Show keybindings help (?)."""
        ...

    # Screen management
    def push_screen(self, screen: Screen) -> None:
        """Push a screen onto the stack.

        Args:
            screen: Screen instance to push.
        """
        ...

    def pop_screen(self) -> Screen:
        """Pop the current screen from the stack.

        Returns:
            The popped screen.
        """
        ...

    # Log panel access
    def add_log(self, message: str, level: str = "info", source: str = "") -> None:
        """Add a log entry to the log panel.

        Convenience method that delegates to the LogPanel widget.

        Args:
            message: Log message content.
            level: Log level ("info", "success", "warning", "error").
            source: Source component/agent name.
        """
        ...

    # Timer for elapsed time
    def start_timer(self) -> None:
        """Start the elapsed time timer.

        Called when a workflow starts to track execution time.
        """
        ...

    def stop_timer(self) -> None:
        """Stop the elapsed time timer.

        Called when a workflow completes or fails.
        """
        ...

    @property
    def elapsed_time(self) -> float:
        """Get current elapsed time in seconds."""
        ...
