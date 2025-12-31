from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ConfirmDialogConfig:
    """Configuration for confirmation dialog.

    Attributes:
        title: Dialog title.
        message: Dialog message.
        confirm_label: Label for confirm button.
        cancel_label: Label for cancel button.
        confirm_variant: Button variant for confirm button.
    """

    title: str
    message: str
    confirm_label: str = "Yes"
    cancel_label: str = "No"
    confirm_variant: str = "primary"  # "primary" | "warning" | "error"


@dataclass(frozen=True, slots=True)
class ErrorDialogConfig:
    """Configuration for error dialog.

    Attributes:
        title: Dialog title.
        message: Error message.
        details: Optional detailed error information.
        dismiss_label: Label for dismiss button.
        retry_action: Optional retry callback name.
    """

    title: str = "Error"
    message: str = ""
    details: str | None = None
    dismiss_label: str = "Dismiss"
    retry_action: str | None = None


@dataclass(frozen=True, slots=True)
class InputDialogConfig:
    """Configuration for input dialog.

    Attributes:
        title: Dialog title.
        prompt: Input prompt.
        placeholder: Input placeholder.
        initial_value: Initial input value.
        submit_label: Label for submit button.
        cancel_label: Label for cancel button.
    """

    title: str
    prompt: str
    placeholder: str = ""
    initial_value: str = ""
    submit_label: str = "Submit"
    cancel_label: str = "Cancel"
