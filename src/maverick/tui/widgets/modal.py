"""Modal dialog widgets for Maverick TUI."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static

__all__ = [
    "ConfirmDialog",
    "ErrorDialog",
    "InputDialog",
]


class ConfirmDialog(ModalScreen[bool]):
    """Confirmation dialog with Yes/No buttons.

    A modal dialog that prompts the user to confirm or cancel an action.
    Returns True if the user confirms, False if they cancel.

    Args:
        title: The dialog title text.
        message: The confirmation message to display.
        confirm_label: Label for the confirm button (default: "Yes").
        cancel_label: Label for the cancel button (default: "No").

    Returns:
        bool: True if confirmed, False if canceled.

    Example:
        >>> result = await self.app.push_screen_wait(
        ...     ConfirmDialog(
        ...         title="Confirm Action",
        ...         message="Are you sure you want to continue?"
        ...     )
        ... )
        >>> if result:
        ...     # User confirmed
    """

    DEFAULT_CSS = """
    ConfirmDialog {
        align: center middle;
    }

    ConfirmDialog > Container {
        width: 60;
        height: auto;
        border: solid $accent;
        background: $surface;
        padding: 1 2;
    }

    ConfirmDialog #title {
        margin-bottom: 1;
    }

    ConfirmDialog #message {
        margin-bottom: 1;
    }

    ConfirmDialog #buttons {
        height: auto;
        margin-top: 1;
        align: center middle;
    }

    ConfirmDialog Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("y", "confirm", "Yes", show=True),
        Binding("n", "cancel", "No", show=True),
        Binding("escape", "cancel", "Cancel", show=True),
        Binding("enter", "confirm", "Confirm", show=False),
    ]

    def __init__(
        self,
        title: str = "Confirm",
        message: str = "",
        confirm_label: str = "Yes",
        cancel_label: str = "No",
    ) -> None:
        """Initialize the confirmation dialog.

        Args:
            title: The dialog title text.
            message: The confirmation message to display.
            confirm_label: Label for the confirm button.
            cancel_label: Label for the cancel button.
        """
        super().__init__()
        self.title_text = title
        self.message_text = message
        self.confirm_label = confirm_label
        self.cancel_label = cancel_label

    def compose(self) -> ComposeResult:
        """Compose the dialog widgets.

        Yields:
            Static: Title widget.
            Static: Message widget.
            Horizontal: Container with Yes/No buttons.
        """
        with Container():
            yield Static(f"[bold]{self.title_text}[/bold]", id="title")
            yield Static(self.message_text, id="message")
            with Horizontal(id="buttons"):
                yield Button(self.confirm_label, id="yes", variant="primary")
                yield Button(self.cancel_label, id="no")

    def on_mount(self) -> None:
        """Focus the Yes button when the dialog is mounted."""
        self.query_one("#yes", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events.

        Args:
            event: The button press event.
        """
        self.dismiss(event.button.id == "yes")

    def action_confirm(self) -> None:
        """Action handler for confirm binding (y, enter)."""
        self.dismiss(True)

    def action_cancel(self) -> None:
        """Action handler for cancel binding (n, escape)."""
        self.dismiss(False)


class ErrorDialog(ModalScreen[None]):
    """Error dialog with dismiss button and optional details.

    A modal dialog that displays an error message with optional detailed
    information. The dialog can be dismissed via button click, Enter key,
    or Escape key.

    Args:
        message: The main error message to display.
        details: Optional detailed error information (e.g., stack trace).
        title: The dialog title (default: "Error").

    Returns:
        None: Always returns None when dismissed.

    Example:
        >>> self.app.push_screen(
        ...     ErrorDialog(
        ...         message="Failed to load configuration",
        ...         details="FileNotFoundError: config.yaml not found"
        ...     )
        ... )
    """

    DEFAULT_CSS = """
    ErrorDialog {
        align: center middle;
    }

    ErrorDialog > Container {
        width: 70;
        height: auto;
        border: solid $error;
        background: $surface;
        padding: 1 2;
    }

    ErrorDialog #title {
        color: $error;
        margin-bottom: 1;
    }

    ErrorDialog #message {
        margin-bottom: 1;
    }

    ErrorDialog #details {
        color: $text-muted;
        margin-bottom: 1;
        max-height: 10;
        overflow-y: auto;
    }

    ErrorDialog #buttons {
        height: auto;
        margin-top: 1;
        align: center middle;
    }

    ErrorDialog Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Close", show=True),
        Binding("enter", "dismiss", "Close", show=False),
    ]

    def __init__(
        self,
        message: str,
        details: str | None = None,
        title: str = "Error",
    ) -> None:
        """Initialize the error dialog.

        Args:
            message: The main error message to display.
            details: Optional detailed error information.
            title: The dialog title.
        """
        super().__init__()
        self.error_message = message
        self.error_details = details
        self.title_text = title

    def compose(self) -> ComposeResult:
        """Compose the dialog widgets.

        Yields:
            Static: Title widget.
            Static: Message widget.
            Static: Details widget (if details provided).
            Horizontal: Container with dismiss button.
        """
        with Container():
            yield Static(f"[bold red]{self.title_text}[/bold red]", id="title")
            yield Static(self.error_message, id="message")
            if self.error_details:
                yield Static(self.error_details, id="details")
            with Horizontal(id="buttons"):
                yield Button("Dismiss", id="dismiss")

    def on_mount(self) -> None:
        """Focus the dismiss button when the dialog is mounted."""
        self.query_one("#dismiss", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events.

        Args:
            event: The button press event.
        """
        self.dismiss(None)


class InputDialog(ModalScreen[str | None]):
    """Input dialog that collects text from the user.

    A modal dialog that prompts the user to enter text. Returns the entered
    text if submitted, or None if canceled.

    Args:
        title: The dialog title text.
        prompt: The prompt message to display above the input.
        placeholder: Placeholder text for the input field.
        initial_value: Initial value to populate the input field.
        password: Whether to mask the input (for passwords).

    Returns:
        str | None: The entered text if submitted, None if canceled.

    Example:
        >>> result = await self.app.push_screen_wait(
        ...     InputDialog(
        ...         title="Enter Branch Name",
        ...         prompt="Please enter the branch name:",
        ...         placeholder="feature/my-feature"
        ...     )
        ... )
        >>> if result:
        ...     # User entered text
    """

    DEFAULT_CSS = """
    InputDialog {
        align: center middle;
    }

    InputDialog > Container {
        width: 60;
        height: auto;
        border: solid $accent;
        background: $surface;
        padding: 1 2;
    }

    InputDialog #title {
        margin-bottom: 1;
    }

    InputDialog #prompt {
        margin-bottom: 1;
    }

    InputDialog #input {
        margin-bottom: 1;
    }

    InputDialog #buttons {
        height: auto;
        margin-top: 1;
        align: center middle;
    }

    InputDialog Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=True),
        Binding("ctrl+enter", "submit", "Submit", show=True),
    ]

    def __init__(
        self,
        title: str = "Input",
        prompt: str = "",
        placeholder: str = "",
        initial_value: str = "",
        password: bool = False,
    ) -> None:
        """Initialize the input dialog.

        Args:
            title: The dialog title text.
            prompt: The prompt message to display.
            placeholder: Placeholder text for the input field.
            initial_value: Initial value for the input field.
            password: Whether to mask the input.
        """
        super().__init__()
        self.title_text = title
        self.prompt_text = prompt
        self.placeholder_text = placeholder
        self.initial_value = initial_value
        self.is_password = password

    def compose(self) -> ComposeResult:
        """Compose the dialog widgets.

        Yields:
            Static: Title widget.
            Static: Prompt widget.
            Input: Text input field.
            Horizontal: Container with Submit/Cancel buttons.
        """
        with Container():
            yield Static(f"[bold]{self.title_text}[/bold]", id="title")
            yield Static(self.prompt_text, id="prompt")
            yield Input(
                value=self.initial_value,
                placeholder=self.placeholder_text,
                password=self.is_password,
                id="input",
            )
            with Horizontal(id="buttons"):
                yield Button("Submit", id="submit", variant="primary")
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        """Focus the input field when the dialog is mounted."""
        self.query_one("#input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events.

        Args:
            event: The button press event.
        """
        if event.button.id == "submit":
            self.action_submit()
        else:
            self.action_cancel()

    def action_submit(self) -> None:
        """Action handler for submit binding (ctrl+enter, submit button)."""
        value = self.query_one("#input", Input).value
        self.dismiss(value if value.strip() else None)

    def action_cancel(self) -> None:
        """Action handler for cancel binding (escape, cancel button)."""
        self.dismiss(None)
