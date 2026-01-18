"""Dynamic shortcut footer widget for context-aware keybinding display.

This widget provides a LazyGit-style footer that shows available keyboard
shortcuts for the current screen/context.

Feature: TUI Dramatic Improvement
Date: 2026-01-12
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.widget import Widget
from textual.widgets import Static

if TYPE_CHECKING:
    pass


class ShortcutFooter(Widget):
    """Dynamic footer showing context-relevant keyboard shortcuts.

    This widget displays available shortcuts for the current screen,
    updating automatically when the screen changes. Format follows
    LazyGit style: [key]action [key]action ...

    Usage:
        # In app compose:
        yield ShortcutFooter()

        # Update when screen changes:
        footer = self.query_one(ShortcutFooter)
        footer.refresh_shortcuts()

    Attributes:
        max_shortcuts: Maximum number of shortcuts to display.
    """

    DEFAULT_CSS = """
    ShortcutFooter {
        dock: bottom;
        height: 1;
        background: #242424;
        padding: 0 1;
    }

    ShortcutFooter .shortcut-container {
        width: 100%;
        height: 1;
    }

    ShortcutFooter .shortcut-item {
        width: auto;
        margin-right: 2;
    }

    ShortcutFooter .shortcut-key {
        color: #00aaff;
        text-style: bold;
    }

    ShortcutFooter .shortcut-action {
        color: #808080;
    }

    ShortcutFooter .shortcut-separator {
        color: #606060;
        margin: 0 1;
    }
    """

    def __init__(
        self,
        max_shortcuts: int = 8,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Initialize the shortcut footer.

        Args:
            max_shortcuts: Maximum number of shortcuts to display.
            name: Widget name.
            id: Widget ID.
            classes: CSS classes.
        """
        super().__init__(name=name, id=id, classes=classes)
        self.max_shortcuts = max_shortcuts
        self._shortcuts: list[tuple[str, str]] = []

    def compose(self) -> ComposeResult:
        """Create the footer layout."""
        yield Static("", id="shortcut-display")

    def on_mount(self) -> None:
        """Refresh shortcuts when mounted."""
        self.refresh_shortcuts()

    def refresh_shortcuts(self) -> None:
        """Update displayed shortcuts based on current context.

        Call this method when the screen changes to update the
        footer with the new screen's shortcuts.
        """
        self._shortcuts = self._collect_shortcuts()
        self._update_display()

    def _collect_shortcuts(self) -> list[tuple[str, str]]:
        """Collect shortcuts from current screen and app.

        Returns:
            List of (key, description) tuples.
        """
        shortcuts: list[tuple[str, str]] = []

        # Get current screen's bindings
        if self.app and self.app.screen:
            screen = self.app.screen
            shortcuts.extend(self._extract_bindings(screen))

        # Get app-level bindings
        if self.app:
            shortcuts.extend(self._extract_bindings(self.app))

        # Deduplicate by key (screen bindings take precedence)
        seen_keys: set[str] = set()
        unique_shortcuts: list[tuple[str, str]] = []
        for key, desc in shortcuts:
            if key.lower() not in seen_keys:
                seen_keys.add(key.lower())
                unique_shortcuts.append((key, desc))

        return unique_shortcuts[: self.max_shortcuts]

    def _extract_bindings(self, source: object) -> list[tuple[str, str]]:
        """Extract displayable bindings from a screen or app.

        Args:
            source: Object with BINDINGS attribute.

        Returns:
            List of (key, description) tuples.
        """
        bindings: list[tuple[str, str]] = []

        if not hasattr(source, "BINDINGS"):
            return bindings

        for binding in source.BINDINGS:
            if isinstance(binding, Binding):
                # Only include bindings marked as shown
                if not binding.show:
                    continue
                key = self._format_key(binding.key)
                description = binding.description or binding.action
                bindings.append((key, description))
            elif isinstance(binding, tuple) and len(binding) >= 3:
                # Legacy tuple format: (key, action, description)
                key, action, description = binding[:3]
                key = self._format_key(key)
                bindings.append((key, description))

        return bindings

    def _format_key(self, key: str) -> str:
        """Format a key string for display.

        Args:
            key: Raw key string.

        Returns:
            Formatted key string.
        """
        replacements = {
            "ctrl+": "C-",
            "shift+": "S-",
            "alt+": "A-",
            "escape": "Esc",
            "enter": "Enter",
            "tab": "Tab",
        }

        result = key
        for old, new in replacements.items():
            result = result.replace(old, new)

        # Capitalize single letter keys
        if len(result) == 1:
            result = result.upper()

        return result

    def _update_display(self) -> None:
        """Update the footer display with current shortcuts."""
        if not self.is_mounted:
            return

        try:
            display = self.query_one("#shortcut-display", Static)
        except Exception:
            return

        if not self._shortcuts:
            display.update("")
            return

        # Build display string: [key]action [key]action ...
        parts: list[str] = []
        for key, description in self._shortcuts:
            # Truncate long descriptions
            if len(description) > 12:
                description = description[:10] + ".."
            parts.append(f"[cyan]{key}[/cyan][dim]{description}[/dim]")

        display.update("  ".join(parts))

    def set_shortcuts(self, shortcuts: list[tuple[str, str]]) -> None:
        """Manually set shortcuts to display.

        Use this method to override automatic shortcut collection
        with a specific set of shortcuts.

        Args:
            shortcuts: List of (key, description) tuples.
        """
        self._shortcuts = shortcuts[: self.max_shortcuts]
        self._update_display()
