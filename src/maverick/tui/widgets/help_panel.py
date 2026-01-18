"""Help panel widget for context-aware keybinding display.

This widget provides a LazyGit-style help overlay that shows available
keyboard shortcuts for the current screen/context.

Feature: TUI Dramatic Improvement
Date: 2026-01-12
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import ScrollableContainer, Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

if TYPE_CHECKING:
    from textual.screen import Screen


@dataclass
class HelpSection:
    """A section of help content with related keybindings."""

    title: str
    bindings: list[tuple[str, str]]  # (key, description)


class HelpPanel(ModalScreen[None]):
    """Modal help panel showing context-aware keybindings.

    This panel displays available keyboard shortcuts organized by category.
    It queries the current screen and app for bindings and presents them
    in a readable format.

    Usage:
        # From any screen or app action:
        self.app.push_screen(HelpPanel())

    The panel can be dismissed with Escape or ? key.
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Close", show=True),
        Binding("?", "dismiss", "Close", show=False),
        Binding("q", "dismiss", "Close", show=False),
    ]

    DEFAULT_CSS = """
    HelpPanel {
        align: center middle;
    }

    HelpPanel > Vertical {
        width: 60%;
        max-width: 80;
        max-height: 80%;
        background: #242424;
        border: solid #00aaff;
        padding: 1 2;
    }

    HelpPanel .help-title {
        text-style: bold;
        color: #00aaff;
        text-align: center;
        margin-bottom: 1;
    }

    HelpPanel .help-subtitle {
        color: #808080;
        text-align: center;
        margin-bottom: 1;
    }

    HelpPanel .help-content {
        height: auto;
        max-height: 100%;
    }

    HelpPanel .help-section {
        margin-bottom: 1;
    }

    HelpPanel .help-section-title {
        text-style: bold;
        color: #e0e0e0;
        margin-bottom: 0;
    }

    HelpPanel .help-row {
        height: 1;
    }

    HelpPanel .help-key {
        width: 15;
        color: #00aaff;
    }

    HelpPanel .help-description {
        color: #808080;
    }

    HelpPanel .help-footer {
        margin-top: 1;
        color: #606060;
        text-align: center;
    }
    """

    def __init__(
        self,
        context_screen: Screen[None] | None = None,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Initialize the help panel.

        Args:
            context_screen: The screen to show help for. If None, uses
                the current screen from the app.
            name: Widget name.
            id: Widget ID.
            classes: CSS classes.
        """
        super().__init__(name=name, id=id, classes=classes)
        self._context_screen = context_screen

    def compose(self) -> ComposeResult:
        """Create the help panel layout."""
        with Vertical():
            yield Static("[bold]Keyboard Shortcuts[/bold]", classes="help-title")
            yield Static(
                f"[dim]{self._get_screen_title()}[/dim]",
                classes="help-subtitle",
            )
            with ScrollableContainer(classes="help-content"):
                for section in self._get_help_sections():
                    yield self._compose_section(section)
            yield Static(
                "[dim]Press ? or Esc to close[/dim]",
                classes="help-footer",
            )

    def _get_screen_title(self) -> str:
        """Get the title of the context screen."""
        screen = self._context_screen or self._get_current_screen()
        if screen and hasattr(screen, "TITLE"):
            title = screen.TITLE
            if title is not None:
                return str(title)
        return "Help"

    def _get_current_screen(self) -> Screen[None] | None:
        """Get the current screen from the app stack."""
        if not self.app:
            return None
        # Get the screen below this help panel
        stack = list(self.app.screen_stack)
        if len(stack) >= 2:
            return stack[-2]
        return None

    def _get_help_sections(self) -> list[HelpSection]:
        """Collect help sections from current context."""
        sections: list[HelpSection] = []

        # Get screen-specific bindings
        screen = self._context_screen or self._get_current_screen()
        if screen:
            screen_bindings = self._extract_bindings(screen)
            if screen_bindings:
                sections.append(
                    HelpSection(
                        title="Current Screen",
                        bindings=screen_bindings,
                    )
                )

        # Get app-level bindings
        if self.app:
            app_bindings = self._extract_bindings(self.app)
            if app_bindings:
                sections.append(
                    HelpSection(
                        title="Global",
                        bindings=app_bindings,
                    )
                )

        # Add navigation section
        sections.append(
            HelpSection(
                title="Navigation",
                bindings=[
                    ("Tab", "Next pane/widget"),
                    ("Shift+Tab", "Previous pane/widget"),
                    ("j / Down", "Move down"),
                    ("k / Up", "Move up"),
                    ("Enter", "Select/Confirm"),
                    ("Escape", "Back/Cancel"),
                ],
            )
        )

        return sections

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
                # Skip bindings marked as not shown
                if not binding.show:
                    continue
                # Format the key display
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
            key: Raw key string (e.g., "ctrl+l", "shift+r").

        Returns:
            Formatted key string (e.g., "Ctrl+L", "Shift+R").
        """
        # Handle common key names
        replacements = {
            "ctrl+": "Ctrl+",
            "shift+": "Shift+",
            "alt+": "Alt+",
            "escape": "Esc",
            "enter": "Enter",
            "tab": "Tab",
            "space": "Space",
            "up": "Up",
            "down": "Down",
            "left": "Left",
            "right": "Right",
        }

        result = key
        for old, new in replacements.items():
            result = result.replace(old, new)

        # Capitalize single letter keys
        if len(result) == 1:
            result = result.upper()

        return result

    def _compose_section(self, section: HelpSection) -> Vertical:
        """Compose a help section widget.

        Args:
            section: The help section to render.

        Returns:
            A Vertical container with the section content.
        """
        container = Vertical(classes="help-section")
        container.compose_add_child(
            Static(f"[bold]{section.title}[/bold]", classes="help-section-title")
        )
        for key, description in section.bindings:
            row = Static(
                f"[cyan]{key:<12}[/cyan] [dim]{description}[/dim]",
                classes="help-row",
            )
            container.compose_add_child(row)
        return container

    async def action_dismiss(self, result: None = None) -> None:
        """Dismiss the help panel.

        Args:
            result: Unused result parameter (required by ModalScreen signature).
        """
        self.dismiss(result)
