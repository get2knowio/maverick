from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import ScrollableContainer, Vertical
from textual.screen import Screen
from textual.widgets import Input, Static


class ConfigScreen(Screen[None]):
    """Configuration screen.

    Displays application settings organized by category with inline
    editing capabilities.
    """

    TITLE = "Settings"

    BINDINGS = [
        Binding("escape", "cancel_or_back", "Back/Cancel", show=True),
        Binding("enter", "edit_selected", "Edit", show=True),
        Binding("j", "move_down", "Down", show=False),
        Binding("k", "move_up", "Up", show=False),
    ]

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Initialize the config screen.

        Args:
            name: Optional screen name for identification.
            id: Optional screen ID for identification.
            classes: Optional CSS class names to apply.
        """
        super().__init__(name=name, id=id, classes=classes)
        # TODO: Replace dict-based options with ConfigOption dataclass from models.py
        # This will provide better type safety and alignment with the spec
        self._options: list[dict[str, Any]] = []
        self._selected_index: int = 0
        self._editing: bool = False
        self._edit_value: str = ""
        self._editing_key: str | None = None

    def compose(self) -> ComposeResult:
        """Create the config screen layout.

        Yields:
            ComposeResult: Settings display with scrollable options list.
        """
        yield Static("[bold]Settings[/bold]", id="config-title")
        yield Static(
            (
                "[dim]Use arrow keys (j/k) to navigate, "
                "Enter to edit, Escape to cancel[/dim]"
            ),
            id="config-help",
        )
        with ScrollableContainer(classes="config-list"):
            yield Vertical(id="config-options")

    def on_mount(self) -> None:
        """Load configuration when screen is mounted.

        Called by Textual framework when the screen is added to the DOM.
        Initializes the configuration options and renders the display.
        """
        self.load_config()

    def load_config(self) -> None:
        """Load current configuration values for display.

        Creates sample config options for demonstration. In the future,
        this will load actual MaverickConfig values.
        """
        # Sample configuration options for Phase 8
        self._options = [
            {
                "key": "notifications_enabled",
                "label": "Notifications Enabled",
                "value": True,
                "type": "bool",
                "description": "Enable push notifications via ntfy",
            },
            {
                "key": "log_level",
                "label": "Log Level",
                "value": "info",
                "type": "choice",
                "choices": ["debug", "info", "warning", "error"],
                "description": "Logging verbosity level",
            },
            {
                "key": "max_parallel_agents",
                "label": "Max Parallel Agents",
                "value": 3,
                "type": "int",
                "min": 1,
                "max": 10,
                "description": "Maximum number of agents running concurrently",
            },
        ]
        self._render_options()

    def _render_options(self) -> None:
        """Render the configuration options list."""
        container = self.query_one("#config-options", Vertical)
        container.remove_children()

        for idx, option in enumerate(self._options):
            is_selected = idx == self._selected_index
            is_editing = self._editing and is_selected

            # Format the value based on type
            value_str = self._format_value(option)

            # Create the option display
            classes = "config-item"
            if is_selected:
                classes += " --selected"
            if is_editing:
                classes += " editing"

            label = option["label"]
            desc = option.get("description", "")

            if is_editing:
                # Show input widget when editing
                option_widget = Input(
                    value=self._edit_value,
                    placeholder=f"Enter {label}",
                    id=f"config-input-{option['key']}",
                    classes=classes,
                )
                container.mount(option_widget)
                option_widget.focus()
            else:
                # Show static display
                marker = "▶" if is_selected else " "
                content = (
                    f"{marker} [bold]{label}:[/bold] {value_str}\n  [dim]{desc}[/dim]"
                )
                container.mount(Static(content, classes=classes))

    def _format_value(self, option: dict[str, Any]) -> str:
        """Format an option value for display.

        Args:
            option: The option dictionary.

        Returns:
            Formatted value string.
        """
        value = option["value"]
        opt_type = option["type"]

        if opt_type == "bool":
            return "[green]enabled[/green]" if value else "[red]disabled[/red]"
        elif opt_type == "choice":
            return f"[cyan]{value}[/cyan]"
        elif opt_type == "int":
            return f"[yellow]{value}[/yellow]"
        else:
            return str(value)

    def edit_option(self, key: str) -> None:
        """Enter edit mode for a configuration option.

        For boolean options, toggles the value immediately.
        For choice options, cycles to the next choice.
        For other types (int, string), enters input mode.

        Args:
            key: Configuration key to edit.
        """
        option = next((opt for opt in self._options if opt["key"] == key), None)
        if not option:
            return

        self._editing = True
        self._editing_key = key

        # Dispatch to type-specific handlers
        option_type = option["type"]
        if option_type == "bool":
            self._toggle_bool_option(option)
        elif option_type == "choice":
            self._cycle_choice_option(option)
        else:
            self._enter_input_mode(option)

    def _toggle_bool_option(self, option: dict[str, Any]) -> None:
        """Toggle a boolean option and immediately save.

        Args:
            option: The option dictionary to toggle.
        """
        option["value"] = not option["value"]
        self._editing = False
        self._editing_key = None
        self._render_options()

    def _cycle_choice_option(self, option: dict[str, Any]) -> None:
        """Cycle a choice option to the next value and immediately save.

        Args:
            option: The option dictionary to cycle.
        """
        choices = option["choices"]
        current_idx = choices.index(option["value"])
        next_idx = (current_idx + 1) % len(choices)
        option["value"] = choices[next_idx]
        self._editing = False
        self._editing_key = None
        self._render_options()

    def _enter_input_mode(self, option: dict[str, Any]) -> None:
        """Enter input mode for text/numeric options.

        Args:
            option: The option dictionary to edit.
        """
        self._edit_value = str(option["value"])
        self._render_options()

    def save_option(self, key: str, value: object) -> None:
        """Save a modified configuration value.

        Args:
            key: Configuration key.
            value: New value (type depends on option).
        """
        # Find the option and update its value
        option = next((opt for opt in self._options if opt["key"] == key), None)
        if not option:
            return

        # Validate and convert value based on type
        try:
            if option["type"] == "int":
                # value is validated as string from Input widget
                new_value = int(str(value))
                # Check min/max if specified
                if "min" in option and new_value < option["min"]:
                    new_value = option["min"]
                if "max" in option and new_value > option["max"]:
                    new_value = option["max"]
                option["value"] = new_value
            elif option["type"] == "choice":
                if value in option["choices"]:
                    option["value"] = value
            elif option["type"] == "bool":
                option["value"] = bool(value)
            else:
                option["value"] = value

            # TODO: In the future, persist to actual MaverickConfig
            # For now, just update in-memory option

        except (ValueError, TypeError):
            # Invalid value, don't save
            pass

        self._editing = False
        self._editing_key = None
        self._edit_value = ""
        self._render_options()

    def cancel_edit(self) -> None:
        """Cancel the current edit operation."""
        self._editing = False
        self._editing_key = None
        self._edit_value = ""
        self._render_options()

    def action_cancel_or_back(self) -> None:
        """Cancel edit or go back."""
        if self._editing:
            self.cancel_edit()
        else:
            self.app.pop_screen()

    def action_edit_selected(self) -> None:
        """Edit the selected option."""
        if self._options and not self._editing:
            option = self._options[self._selected_index]
            self.edit_option(str(option.get("key", "")))

    def action_move_down(self) -> None:
        """Move selection down."""
        if self._options and not self._editing:
            self._selected_index = min(self._selected_index + 1, len(self._options) - 1)
            self._render_options()

    def action_move_up(self) -> None:
        """Move selection up."""
        if self._options and not self._editing:
            self._selected_index = max(self._selected_index - 1, 0)
            self._render_options()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle input submission when editing a config option.

        Args:
            event: The input submission event.
        """
        if self._editing and self._editing_key:
            self.save_option(self._editing_key, event.value)
