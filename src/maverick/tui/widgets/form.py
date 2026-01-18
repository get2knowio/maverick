"""Form field widgets for Maverick TUI."""

from __future__ import annotations

import re
from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Button, Input, Static, Switch

__all__ = [
    "BranchInputField",
    "NumericField",
    "SelectField",
    "ToggleField",
]


class BranchInputField(Widget):
    """Branch name input with real-time validation.

    Validates branch names for git compatibility:
    - Not empty
    - Valid characters only: a-z, A-Z, 0-9, ., _, /, -
    - No double dots
    - No trailing dots
    - Max 255 chars

    Attributes:
        value: Current input value
        error_message: Validation error message (empty if valid)
        is_valid: Whether current value is valid
        is_checking: Whether async validation is in progress
    """

    DEFAULT_CSS = """
    BranchInputField {
        height: auto;
        layout: vertical;
    }

    BranchInputField .label {
        margin-bottom: 1;
        color: #e0e0e0;
    }

    BranchInputField Input {
        margin-bottom: 1;
    }

    BranchInputField .validation-status {
        height: 1;
    }

    BranchInputField .error {
        color: #f44336;
    }

    BranchInputField .valid {
        color: #4caf50;
    }

    BranchInputField .checking {
        color: #ff9800;
    }
    """

    # Reactive state
    value: reactive[str] = reactive("")
    error_message: reactive[str] = reactive("")
    is_valid: reactive[bool] = reactive(False)
    is_checking: reactive[bool] = reactive(False)

    class Changed(Message):
        """Posted when the value changes.

        Attributes:
            value: The new input value
            is_valid: Whether the new value is valid
        """

        def __init__(self, value: str, is_valid: bool) -> None:
            self.value = value
            self.is_valid = is_valid
            super().__init__()

    def __init__(
        self,
        label: str = "Branch Name",
        placeholder: str = "feature/my-feature",
        **kwargs: Any,
    ) -> None:
        """Initialize branch input field.

        Args:
            label: Field label text
            placeholder: Input placeholder text
            **kwargs: Additional widget arguments
        """
        super().__init__(**kwargs)
        self.label_text = label
        self.placeholder = placeholder

    def compose(self) -> ComposeResult:
        """Compose the field widgets."""
        yield Static(self.label_text, classes="label")
        yield Input(id="branch-input", placeholder=self.placeholder)
        yield Static("", classes="validation-status")

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input change events.

        Args:
            event: The input changed event
        """
        if event.input.id == "branch-input":
            self.value = event.value
            self._validate()

    def _validate(self) -> None:
        """Validate branch name against git rules."""
        name = self.value.strip()

        if not name:
            self.error_message = "Branch name cannot be empty"
            self.is_valid = False
        elif not re.match(r"^[a-zA-Z0-9._/-]+$", name):
            # Extract invalid characters for helpful error message
            invalid = set(re.sub(r"[a-zA-Z0-9._/-]", "", name))
            self.error_message = f"Invalid characters: {', '.join(sorted(invalid))}"
            self.is_valid = False
        elif ".." in name:
            self.error_message = "Branch name cannot contain '..'"
            self.is_valid = False
        elif name.endswith("."):
            self.error_message = "Branch name cannot end with '.'"
            self.is_valid = False
        elif len(name) > 255:
            self.error_message = "Branch name too long (max 255 characters)"
            self.is_valid = False
        else:
            self.error_message = ""
            self.is_valid = True

        self.post_message(self.Changed(self.value, self.is_valid))

    def watch_error_message(self, message: str) -> None:
        """Update validation status display when error message changes.

        Args:
            message: New error message
        """
        status = self.query_one(".validation-status", Static)
        status.remove_class("error", "valid", "checking")

        if self.is_checking:
            status.update("[dim]⟳ Checking...[/dim]")
            status.add_class("checking")
        elif message:
            status.update(f"✗ {message}")
            status.add_class("error")
        elif self.value:
            status.update("✓ Valid")
            status.add_class("valid")
        else:
            status.update("")

    def focus_input(self) -> None:
        """Focus the input element."""
        self.query_one("#branch-input", Input).focus()


class NumericField(Widget):
    """Numeric input with increment/decrement and min/max bounds.

    Attributes:
        label: Field label text
        int_value: Current integer value
        min_value: Minimum allowed value
        max_value: Maximum allowed value
        error_message: Validation error message (empty if valid)
        is_valid: Whether current value is valid
    """

    DEFAULT_CSS = """
    NumericField {
        height: auto;
        layout: vertical;
    }

    NumericField .label {
        margin-bottom: 1;
        color: #e0e0e0;
    }

    NumericField .input-row {
        height: 3;
        margin-bottom: 1;
    }

    NumericField Input {
        width: 1fr;
    }

    NumericField Button {
        width: 5;
    }

    NumericField .validation-status {
        height: 1;
    }

    NumericField .error {
        color: #f44336;
    }

    NumericField .valid {
        color: #4caf50;
    }
    """

    BINDINGS = [
        Binding("up", "increment", "Increment", show=False),
        Binding("down", "decrement", "Decrement", show=False),
    ]

    # Reactive state
    int_value: reactive[int] = reactive(0)
    min_value: reactive[int] = reactive(0)
    max_value: reactive[int] = reactive(100)
    error_message: reactive[str] = reactive("")
    is_valid: reactive[bool] = reactive(True)

    class Changed(Message):
        """Posted when the value changes.

        Attributes:
            value: The new integer value
            is_valid: Whether the new value is valid
        """

        def __init__(self, value: int, is_valid: bool) -> None:
            self.value = value
            self.is_valid = is_valid
            super().__init__()

    def __init__(
        self,
        label: str = "Value",
        value: int = 0,
        min_value: int = 0,
        max_value: int = 100,
        **kwargs: Any,
    ) -> None:
        """Initialize numeric field.

        Args:
            label: Field label text
            value: Initial value
            min_value: Minimum allowed value
            max_value: Maximum allowed value
            **kwargs: Additional widget arguments
        """
        super().__init__(**kwargs)
        self.label_text = label
        self.min_value = min_value
        self.max_value = max_value
        self.int_value = value

    def compose(self) -> ComposeResult:
        """Compose the field widgets."""
        yield Static(self.label_text, classes="label")
        with Horizontal(classes="input-row"):
            yield Button("-", id="decrement-btn", variant="default")
            yield Input(
                id="numeric-input",
                value=str(self.int_value),
                restrict=r"^-?[0-9]*$",
            )
            yield Button("+", id="increment-btn", variant="default")
        yield Static("", classes="validation-status")

    def on_mount(self) -> None:
        """Update display after mount."""
        self._update_display()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses.

        Args:
            event: The button pressed event
        """
        if event.button.id == "increment-btn":
            self.increment()
        elif event.button.id == "decrement-btn":
            self.decrement()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input change events.

        Args:
            event: The input changed event
        """
        if event.input.id == "numeric-input":
            self._parse_and_validate(event.value)

    def _parse_and_validate(self, value: str) -> None:
        """Parse and validate numeric input.

        Args:
            value: Input string to parse
        """
        if not value or value == "-":
            # Allow empty or just minus sign during typing
            self.error_message = "Please enter a number"
            self.is_valid = False
            return

        try:
            num = int(value)
            if num < self.min_value:
                self.error_message = f"Value must be at least {self.min_value}"
                self.is_valid = False
            elif num > self.max_value:
                self.error_message = f"Value must be at most {self.max_value}"
                self.is_valid = False
            else:
                self.int_value = num
                self.error_message = ""
                self.is_valid = True
                self.post_message(self.Changed(self.int_value, self.is_valid))
        except ValueError:
            self.error_message = "Invalid number"
            self.is_valid = False

    def increment(self) -> None:
        """Increment value by 1 (clamped to max)."""
        if self.int_value < self.max_value:
            self.int_value += 1
            self._update_display()
            self.post_message(self.Changed(self.int_value, self.is_valid))

    def decrement(self) -> None:
        """Decrement value by 1 (clamped to min)."""
        if self.int_value > self.min_value:
            self.int_value -= 1
            self._update_display()
            self.post_message(self.Changed(self.int_value, self.is_valid))

    def action_increment(self) -> None:
        """Handle increment keybinding."""
        self.increment()

    def action_decrement(self) -> None:
        """Handle decrement keybinding."""
        self.decrement()

    def _update_display(self) -> None:
        """Update input display with current value."""
        try:
            input_widget = self.query_one("#numeric-input", Input)
            input_widget.value = str(self.int_value)
            self.error_message = ""
            self.is_valid = True
        except Exception:
            # Not mounted yet
            pass

    def watch_error_message(self, message: str) -> None:
        """Update validation status display when error message changes.

        Args:
            message: New error message
        """
        try:
            status = self.query_one(".validation-status", Static)
            status.remove_class("error", "valid")

            if message:
                status.update(f"✗ {message}")
                status.add_class("error")
            else:
                status.update("")
        except Exception:
            # Not mounted yet
            pass

    def focus_input(self) -> None:
        """Focus the input element."""
        self.query_one("#numeric-input", Input).focus()


class ToggleField(Widget):
    """Boolean toggle/switch field.

    Attributes:
        label: Field label text
        description: Optional description text
        checked: Whether the toggle is checked
    """

    DEFAULT_CSS = """
    ToggleField {
        height: auto;
        layout: horizontal;
        align: left middle;
    }

    ToggleField Switch {
        margin-right: 2;
    }

    ToggleField .toggle-label {
        width: auto;
        margin-right: 2;
    }

    ToggleField .toggle-description {
        width: auto;
        color: #808080;
    }
    """

    BINDINGS = [
        Binding("space", "toggle_switch", "Toggle", show=False),
        Binding("enter", "toggle_switch", "Toggle", show=False),
    ]

    # Reactive state
    checked: reactive[bool] = reactive(False)

    class Changed(Message):
        """Posted when the checked state changes.

        Attributes:
            checked: The new checked state
        """

        def __init__(self, checked: bool) -> None:
            self.checked = checked
            super().__init__()

    def __init__(
        self,
        label: str = "Option",
        description: str = "",
        checked: bool = False,
        **kwargs: Any,
    ) -> None:
        """Initialize toggle field.

        Args:
            label: Field label text
            description: Optional description text
            checked: Initial checked state
            **kwargs: Additional widget arguments
        """
        super().__init__(**kwargs)
        self.label_text = label
        self.description_text = description
        self.checked = checked

    def compose(self) -> ComposeResult:
        """Compose the field widgets."""
        yield Switch(id="toggle-switch", value=self.checked)
        yield Static(self.label_text, classes="toggle-label")
        if self.description_text:
            yield Static(f"({self.description_text})", classes="toggle-description")

    def on_switch_changed(self, event: Switch.Changed) -> None:
        """Handle switch change events.

        Args:
            event: The switch changed event
        """
        if event.switch.id == "toggle-switch":
            self.checked = event.value
            self.post_message(self.Changed(self.checked))

    def toggle(self) -> None:
        """Toggle the current value."""
        switch = self.query_one("#toggle-switch", Switch)
        switch.toggle()

    def action_toggle_switch(self) -> None:
        """Handle toggle keybinding."""
        self.toggle()

    def focus_switch(self) -> None:
        """Focus the switch element."""
        self.query_one("#toggle-switch", Switch).focus()


class SelectField(Widget):
    """Selection dropdown field.

    Attributes:
        label: Field label text
        options: Tuple of available options
        selected_index: Index of currently selected option
        selected_value: Value of currently selected option
    """

    DEFAULT_CSS = """
    SelectField {
        height: auto;
        layout: vertical;
    }

    SelectField .label {
        margin-bottom: 1;
        color: #e0e0e0;
    }

    SelectField .select-container {
        height: 3;
        layout: horizontal;
        margin-bottom: 1;
    }

    SelectField Button {
        width: 3;
    }

    SelectField .select-display {
        width: 1fr;
        height: 3;
        border: solid #00aaff;
        background: #242424;
        padding: 0 1;
        content-align: left middle;
    }

    SelectField .select-display:focus {
        border: solid #00aaff;
    }

    SelectField .options-list {
        height: auto;
        max-height: 10;
        border: solid #00aaff;
        background: #242424;
        display: none;
    }

    SelectField .options-list.expanded {
        display: block;
    }

    SelectField .option-item {
        height: 1;
        padding: 0 1;
    }

    SelectField .option-item.selected {
        background: #00aaff;
        color: #e0e0e0;
    }

    SelectField .option-item.focused {
        background: #00aaff;
        color: #e0e0e0;
    }
    """

    BINDINGS = [
        Binding("up", "select_previous", "Previous", show=False),
        Binding("down", "select_next", "Next", show=False),
        Binding("enter", "confirm_selection", "Select", show=False),
        Binding("escape", "close_dropdown", "Close", show=False),
    ]

    # Reactive state
    selected_index: reactive[int] = reactive(0)
    _expanded: reactive[bool] = reactive(False)

    class Changed(Message):
        """Posted when the selection changes.

        Attributes:
            value: The newly selected value
            index: The index of the selected option
        """

        def __init__(self, value: str, index: int) -> None:
            self.value = value
            self.index = index
            super().__init__()

    def __init__(
        self,
        label: str = "Select",
        options: tuple[str, ...] | list[str] = (),
        selected_index: int = 0,
        **kwargs: Any,
    ) -> None:
        """Initialize select field.

        Args:
            label: Field label text
            options: Available options
            selected_index: Initial selected index
            **kwargs: Additional widget arguments
        """
        super().__init__(**kwargs)
        self.label_text = label
        self.options = tuple(options) if options else ()
        self.selected_index = max(0, min(selected_index, len(self.options) - 1))

    def compose(self) -> ComposeResult:
        """Compose the field widgets."""
        yield Static(self.label_text, classes="label")
        with Horizontal(classes="select-container"):
            yield Button("<", id="prev-btn", variant="default")
            yield Static(
                self.selected_value,
                id="select-display",
                classes="select-display",
            )
            yield Button(">", id="next-btn", variant="default")

    @property
    def selected_value(self) -> str:
        """Get the currently selected value.

        Returns:
            The selected option string, or empty string if no options
        """
        if not self.options or self.selected_index < 0:
            return ""
        return self.options[self.selected_index]

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses.

        Args:
            event: The button pressed event
        """
        if event.button.id == "next-btn":
            self.select_next()
        elif event.button.id == "prev-btn":
            self.select_previous()

    def select(self, index: int) -> None:
        """Select option by index.

        Args:
            index: Index of option to select
        """
        if not self.options:
            return

        # Clamp to valid range
        index = max(0, min(index, len(self.options) - 1))

        if index != self.selected_index:
            self.selected_index = index
            self._update_display()
            self.post_message(self.Changed(self.selected_value, self.selected_index))

    def select_next(self) -> None:
        """Select next option (wraps to beginning)."""
        if not self.options:
            return
        next_index = (self.selected_index + 1) % len(self.options)
        self.select(next_index)

    def select_previous(self) -> None:
        """Select previous option (wraps to end)."""
        if not self.options:
            return
        prev_index = (self.selected_index - 1) % len(self.options)
        self.select(prev_index)

    def action_select_next(self) -> None:
        """Handle next keybinding."""
        self.select_next()

    def action_select_previous(self) -> None:
        """Handle previous keybinding."""
        self.select_previous()

    def action_confirm_selection(self) -> None:
        """Handle enter keybinding."""
        # Already selected, just post message again for confirmation
        self.post_message(self.Changed(self.selected_value, self.selected_index))

    def action_close_dropdown(self) -> None:
        """Handle escape keybinding."""
        self._expanded = False

    def _update_display(self) -> None:
        """Update display with current selection."""
        try:
            display = self.query_one("#select-display", Static)
            display.update(self.selected_value)
        except Exception:
            # Not mounted yet
            pass

    def watch_selected_index(self, old_index: int, new_index: int) -> None:
        """Update display when selected index changes.

        Args:
            old_index: Previous selected index
            new_index: New selected index
        """
        self._update_display()

    def focus_select(self) -> None:
        """Focus the select display element."""
        self.query_one("#select-display", Static).focus()
