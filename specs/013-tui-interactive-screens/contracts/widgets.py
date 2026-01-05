"""Widget component interfaces for TUI interactive screens.

This module defines the Protocol interfaces for new widgets needed by
the interactive screens feature.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    pass


# =============================================================================
# Modal Dialog Widgets
# =============================================================================


@runtime_checkable
class ConfirmDialogWidgetProtocol(Protocol):
    """Protocol for confirmation dialog widget.

    A modal dialog that presents a yes/no question and returns the result.
    Extends ModalScreen[bool].
    """

    title: str
    message: str
    confirm_label: str
    cancel_label: str

    def compose(self) -> ComposeResult:
        """Create dialog layout with title, message, and buttons."""
        ...

    def on_mount(self) -> None:
        """Focus confirm button by default."""
        ...

    def action_confirm(self) -> None:
        """Handle confirmation (dismiss with True)."""
        ...

    def action_cancel(self) -> None:
        """Handle cancellation (dismiss with False)."""
        ...


@runtime_checkable
class ErrorDialogWidgetProtocol(Protocol):
    """Protocol for error dialog widget.

    A modal dialog that displays an error message with optional retry.
    Extends ModalScreen[None] or ModalScreen[bool] if retry available.
    """

    message: str
    details: str | None
    retry_action: str | None

    def compose(self) -> ComposeResult:
        """Create dialog layout with error message and buttons."""
        ...

    def on_mount(self) -> None:
        """Focus dismiss button by default."""
        ...

    def action_dismiss(self) -> None:
        """Dismiss the error dialog."""
        ...

    def action_retry(self) -> None:
        """Retry the failed action (if available)."""
        ...


@runtime_checkable
class InputDialogWidgetProtocol(Protocol):
    """Protocol for input dialog widget.

    A modal dialog that collects text input from the user.
    Extends ModalScreen[str | None].
    """

    prompt: str
    placeholder: str
    initial_value: str

    def compose(self) -> ComposeResult:
        """Create dialog layout with prompt, input, and buttons."""
        ...

    def on_mount(self) -> None:
        """Focus input field by default."""
        ...

    def action_submit(self) -> None:
        """Submit current input value (dismiss with value)."""
        ...

    def action_cancel(self) -> None:
        """Cancel input (dismiss with None)."""
        ...


# =============================================================================
# Form Widgets
# =============================================================================


@runtime_checkable
class FormFieldProtocol(Protocol):
    """Protocol for a generic form field widget.

    Base protocol for form fields with label, input, and validation.
    """

    label: str
    value: str
    error_message: str | None
    is_valid: bool

    def set_value(self, value: str) -> None:
        """Set the field value.

        Args:
            value: New value for the field.
        """
        ...

    def validate(self) -> bool:
        """Validate the current value.

        Returns:
            True if valid, False otherwise.
        """
        ...

    def focus_input(self) -> None:
        """Focus the input element."""
        ...


@runtime_checkable
class BranchInputFieldProtocol(FormFieldProtocol, Protocol):
    """Protocol for branch name input field.

    Extended form field with branch-specific validation and status display.
    """

    validation_status: str  # BranchValidationStatus value
    is_checking: bool

    async def check_branch_exists(self, name: str) -> bool:
        """Check if branch exists locally or remotely.

        Args:
            name: Branch name to check.

        Returns:
            True if branch exists, False otherwise.
        """
        ...


@runtime_checkable
class NumericFieldProtocol(FormFieldProtocol, Protocol):
    """Protocol for numeric input field.

    Form field for integer values with min/max constraints.
    """

    min_value: int
    max_value: int
    int_value: int

    def increment(self) -> None:
        """Increment value by 1 (clamped to max)."""
        ...

    def decrement(self) -> None:
        """Decrement value by 1 (clamped to min)."""
        ...


@runtime_checkable
class ToggleFieldProtocol(Protocol):
    """Protocol for toggle/switch field.

    Form field for boolean values.
    """

    label: str
    checked: bool

    def toggle(self) -> None:
        """Toggle the current value."""
        ...


@runtime_checkable
class SelectFieldProtocol(Protocol):
    """Protocol for selection/dropdown field.

    Form field for choosing from predefined options.
    """

    label: str
    options: tuple[str, ...]
    selected_index: int
    selected_value: str

    def select(self, index: int) -> None:
        """Select option by index.

        Args:
            index: Index of option to select.
        """
        ...

    def select_next(self) -> None:
        """Select next option."""
        ...

    def select_previous(self) -> None:
        """Select previous option."""
        ...


# =============================================================================
# Issue List Widget
# =============================================================================


@runtime_checkable
class IssueListItemProtocol(Protocol):
    """Protocol for a single issue in the issue list.

    Represents a GitHub issue with selection state.
    """

    issue_number: int
    title: str
    labels: tuple[str, ...]
    selected: bool

    def toggle_selection(self) -> None:
        """Toggle selection state."""
        ...

    def render(self) -> str:
        """Render the issue item."""
        ...


@runtime_checkable
class IssueListWidgetProtocol(Protocol):
    """Protocol for GitHub issue list widget.

    Displays a list of GitHub issues with selection checkboxes.
    """

    focused_index: int
    selected_count: int
    is_empty: bool

    def set_issues(self, issues: list[dict]) -> None:
        """Set the issues to display.

        Args:
            issues: List of issue dictionaries from GitHub API.
        """
        ...

    def clear(self) -> None:
        """Clear all issues."""
        ...

    def select_focused(self) -> None:
        """Toggle selection of focused issue."""
        ...

    def select_all(self) -> None:
        """Select all issues."""
        ...

    def deselect_all(self) -> None:
        """Deselect all issues."""
        ...

    def move_up(self) -> None:
        """Move focus up."""
        ...

    def move_down(self) -> None:
        """Move focus down."""
        ...

    def get_selected_issues(self) -> list[dict]:
        """Get all selected issues.

        Returns:
            List of selected issue dictionaries.
        """
        ...


# =============================================================================
# Settings Widgets
# =============================================================================


@runtime_checkable
class SettingsSectionWidgetProtocol(Protocol):
    """Protocol for settings section widget.

    Groups related settings with a header.
    """

    section_name: str
    expanded: bool

    def compose(self) -> ComposeResult:
        """Create section layout with header and settings."""
        ...

    def toggle_expanded(self) -> None:
        """Toggle section expansion."""
        ...

    def add_setting(self, setting: SettingFieldProtocol) -> None:
        """Add a setting to the section.

        Args:
            setting: Setting field widget to add.
        """
        ...


@runtime_checkable
class SettingFieldProtocol(Protocol):
    """Protocol for a single setting field.

    Displays setting name, value, and description.
    """

    key: str
    display_name: str
    description: str
    is_modified: bool
    is_valid: bool

    def get_value(self) -> str | bool | int:
        """Get the current value."""
        ...

    def set_value(self, value: str | bool | int) -> None:
        """Set the value.

        Args:
            value: New value for the setting.
        """
        ...

    def reset(self) -> None:
        """Reset to original value."""
        ...


# =============================================================================
# Result Summary Widgets
# =============================================================================


@runtime_checkable
class ResultItemProtocol(Protocol):
    """Protocol for a single result item.

    Displays success/failure status for an operation.
    """

    label: str
    success: bool
    error_message: str | None
    link: str | None

    def render(self) -> str:
        """Render the result item."""
        ...


@runtime_checkable
class ResultSummaryWidgetProtocol(Protocol):
    """Protocol for result summary widget.

    Displays a summary of operation results (e.g., fix results, processing results).
    """

    success_count: int
    failure_count: int
    total_count: int

    def set_results(self, results: list[dict]) -> None:
        """Set the results to display.

        Args:
            results: List of result dictionaries with success/failure info.
        """
        ...

    def clear(self) -> None:
        """Clear all results."""
        ...


# =============================================================================
# Type Stubs for Textual
# =============================================================================


# These are type stubs to satisfy the Protocol definitions above
# In actual implementation, import from textual


class ComposeResult:
    """Stub for textual.app.ComposeResult."""

    pass
