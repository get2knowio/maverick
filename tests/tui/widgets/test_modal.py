"""Tests for modal dialog widgets (ConfirmDialog, ErrorDialog, InputDialog).

This module tests the modal dialog widgets using Textual pilot testing.
It demonstrates patterns for testing modal screens.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from textual.widgets import Button, Input, Static

from maverick.tui.widgets.modal import ConfirmDialog, ErrorDialog, InputDialog
from tests.tui.conftest import ScreenTestApp

if TYPE_CHECKING:
    from collections.abc import Callable


# =============================================================================
# Test Apps for Modal Dialogs
# =============================================================================


class ConfirmDialogTestApp(ScreenTestApp):
    """Test app for ConfirmDialog testing.

    Pushes the dialog on mount for testing. Uses push_screen without
    wait_for_dismiss for test compatibility.
    """

    def __init__(
        self,
        title: str = "Confirm",
        message: str = "Are you sure?",
        confirm_label: str = "Yes",
        cancel_label: str = "No",
    ) -> None:
        super().__init__()
        self._dialog_title = title
        self._dialog_message = message
        self._confirm_label = confirm_label
        self._cancel_label = cancel_label
        self.result: bool | None = None

    def on_mount(self) -> None:
        dialog = ConfirmDialog(
            title=self._dialog_title,
            message=self._dialog_message,
            confirm_label=self._confirm_label,
            cancel_label=self._cancel_label,
        )
        self.push_screen(dialog, callback=self._on_dialog_dismiss)

    def _on_dialog_dismiss(self, result: bool) -> None:
        self.result = result


class ErrorDialogTestApp(ScreenTestApp):
    """Test app for ErrorDialog testing."""

    def __init__(
        self,
        message: str = "An error occurred",
        details: str | None = None,
        title: str = "Error",
    ) -> None:
        super().__init__()
        self._error_message = message
        self._error_details = details
        self._error_title = title
        self.dismissed: bool = False

    def on_mount(self) -> None:
        dialog = ErrorDialog(
            message=self._error_message,
            details=self._error_details,
            title=self._error_title,
        )
        self.push_screen(dialog, callback=self._on_dialog_dismiss)

    def _on_dialog_dismiss(self, result: None) -> None:
        self.dismissed = True


class InputDialogTestApp(ScreenTestApp):
    """Test app for InputDialog testing."""

    def __init__(
        self,
        title: str = "Input",
        prompt: str = "Enter value:",
        placeholder: str = "",
        initial_value: str = "",
        password: bool = False,
    ) -> None:
        super().__init__()
        self._input_title = title
        self._input_prompt = prompt
        self._input_placeholder = placeholder
        self._input_initial = initial_value
        self._input_password = password
        self.result: str | None = None

    def on_mount(self) -> None:
        dialog = InputDialog(
            title=self._input_title,
            prompt=self._input_prompt,
            placeholder=self._input_placeholder,
            initial_value=self._input_initial,
            password=self._input_password,
        )
        self.push_screen(dialog, callback=self._on_dialog_dismiss)

    def _on_dialog_dismiss(self, result: str | None) -> None:
        self.result = result


# =============================================================================
# ConfirmDialog Tests
# =============================================================================


class TestConfirmDialog:
    """Tests for ConfirmDialog widget."""

    @pytest.mark.asyncio
    async def test_confirm_dialog_renders_title_and_message(self) -> None:
        """Test that ConfirmDialog displays title and message."""
        app = ConfirmDialogTestApp(title="Delete File", message="Delete this file?")

        async with app.run_test() as pilot:
            await pilot.pause()

            # Check title is rendered
            title_widget = pilot.app.query_one("#title", Static)
            assert "Delete File" in str(title_widget.renderable)

            # Check message is rendered
            message_widget = pilot.app.query_one("#message", Static)
            assert "Delete this file?" in str(message_widget.renderable)

            # Close dialog to let app exit
            await pilot.press("escape")

    @pytest.mark.asyncio
    async def test_confirm_dialog_yes_button_returns_true(self) -> None:
        """Test that clicking Yes returns True."""
        app = ConfirmDialogTestApp()

        async with app.run_test() as pilot:
            await pilot.pause()

            # Click Yes button
            await pilot.click("#yes")
            await pilot.pause()

            assert app.result is True

    @pytest.mark.asyncio
    async def test_confirm_dialog_no_button_returns_false(self) -> None:
        """Test that clicking No returns False."""
        app = ConfirmDialogTestApp()

        async with app.run_test() as pilot:
            await pilot.pause()

            # Click No button
            await pilot.click("#no")
            await pilot.pause()

            assert app.result is False

    @pytest.mark.asyncio
    async def test_confirm_dialog_y_key_confirms(self) -> None:
        """Test that pressing 'y' confirms the dialog."""
        app = ConfirmDialogTestApp()

        async with app.run_test() as pilot:
            await pilot.pause()

            # Press 'y' key
            await pilot.press("y")
            await pilot.pause()

            assert app.result is True

    @pytest.mark.asyncio
    async def test_confirm_dialog_n_key_cancels(self) -> None:
        """Test that pressing 'n' cancels the dialog."""
        app = ConfirmDialogTestApp()

        async with app.run_test() as pilot:
            await pilot.pause()

            # Press 'n' key
            await pilot.press("n")
            await pilot.pause()

            assert app.result is False

    @pytest.mark.asyncio
    async def test_confirm_dialog_escape_cancels(self) -> None:
        """Test that pressing Escape cancels the dialog."""
        app = ConfirmDialogTestApp()

        async with app.run_test() as pilot:
            await pilot.pause()

            # Press Escape
            await pilot.press("escape")
            await pilot.pause()

            assert app.result is False

    @pytest.mark.asyncio
    async def test_confirm_dialog_enter_confirms(self) -> None:
        """Test that pressing Enter confirms the dialog."""
        app = ConfirmDialogTestApp()

        async with app.run_test() as pilot:
            await pilot.pause()

            # Press Enter
            await pilot.press("enter")
            await pilot.pause()

            assert app.result is True

    @pytest.mark.asyncio
    async def test_confirm_dialog_custom_button_labels(self) -> None:
        """Test custom button labels are displayed."""
        app = ConfirmDialogTestApp(
            confirm_label="Proceed",
            cancel_label="Abort",
        )

        async with app.run_test() as pilot:
            await pilot.pause()

            # Check button labels
            yes_button = pilot.app.query_one("#yes", Button)
            no_button = pilot.app.query_one("#no", Button)

            assert str(yes_button.label) == "Proceed"
            assert str(no_button.label) == "Abort"

            # Close dialog
            await pilot.press("escape")

    @pytest.mark.asyncio
    async def test_confirm_dialog_yes_button_focused_on_mount(self) -> None:
        """Test that Yes button is focused when dialog opens."""
        app = ConfirmDialogTestApp()

        async with app.run_test() as pilot:
            await pilot.pause()

            # Check Yes button is focused
            yes_button = pilot.app.query_one("#yes", Button)
            assert yes_button.has_focus

            # Close dialog
            await pilot.press("escape")


# =============================================================================
# ErrorDialog Tests
# =============================================================================


class TestErrorDialog:
    """Tests for ErrorDialog widget."""

    @pytest.mark.asyncio
    async def test_error_dialog_renders_message(self) -> None:
        """Test that ErrorDialog displays the error message."""
        app = ErrorDialogTestApp(message="Connection failed")

        async with app.run_test() as pilot:
            await pilot.pause()

            # Check message is rendered
            message_widget = pilot.app.query_one("#message", Static)
            assert "Connection failed" in str(message_widget.renderable)

            # Close dialog
            await pilot.click("#dismiss")

    @pytest.mark.asyncio
    async def test_error_dialog_renders_details(self) -> None:
        """Test that ErrorDialog displays details when provided."""
        app = ErrorDialogTestApp(
            message="Database error",
            details="ConnectionError: timeout after 30s",
        )

        async with app.run_test() as pilot:
            await pilot.pause()

            # Check details are rendered
            details_widget = pilot.app.query_one("#details", Static)
            assert "ConnectionError" in str(details_widget.renderable)

            # Close dialog
            await pilot.click("#dismiss")

    @pytest.mark.asyncio
    async def test_error_dialog_no_details_when_none(self) -> None:
        """Test that details section is not shown when details is None."""
        app = ErrorDialogTestApp(message="Simple error")

        async with app.run_test() as pilot:
            await pilot.pause()

            # Details widget should not exist
            details_widgets = pilot.app.query("#details")
            assert len(details_widgets) == 0

            # Close dialog
            await pilot.click("#dismiss")

    @pytest.mark.asyncio
    async def test_error_dialog_custom_title(self) -> None:
        """Test custom title is displayed."""
        app = ErrorDialogTestApp(message="Failed", title="Critical Error")

        async with app.run_test() as pilot:
            await pilot.pause()

            # Check title is rendered
            title_widget = pilot.app.query_one("#title", Static)
            assert "Critical Error" in str(title_widget.renderable)

            # Close dialog
            await pilot.click("#dismiss")

    @pytest.mark.asyncio
    async def test_error_dialog_dismiss_button(self) -> None:
        """Test that clicking Dismiss closes the dialog."""
        app = ErrorDialogTestApp(message="Error")

        async with app.run_test() as pilot:
            await pilot.pause()

            # Click Dismiss button
            await pilot.click("#dismiss")
            await pilot.pause()

            assert app.dismissed is True

    @pytest.mark.asyncio
    async def test_error_dialog_escape_dismisses(self) -> None:
        """Test that pressing Escape closes the dialog."""
        app = ErrorDialogTestApp(message="Error")

        async with app.run_test() as pilot:
            await pilot.pause()

            # Press Escape
            await pilot.press("escape")
            await pilot.pause()

            assert app.dismissed is True

    @pytest.mark.asyncio
    async def test_error_dialog_enter_dismisses(self) -> None:
        """Test that pressing Enter closes the dialog."""
        app = ErrorDialogTestApp(message="Error")

        async with app.run_test() as pilot:
            await pilot.pause()

            # Press Enter
            await pilot.press("enter")
            await pilot.pause()

            assert app.dismissed is True


# =============================================================================
# InputDialog Tests
# =============================================================================


class TestInputDialog:
    """Tests for InputDialog widget."""

    @pytest.mark.asyncio
    async def test_input_dialog_renders_title_and_prompt(self) -> None:
        """Test that InputDialog displays title and prompt."""
        app = InputDialogTestApp(
            title="Branch Name",
            prompt="Enter the branch name:",
        )

        async with app.run_test() as pilot:
            await pilot.pause()

            # Check title is rendered
            title_widget = pilot.app.query_one("#title", Static)
            assert "Branch Name" in str(title_widget.renderable)

            # Check prompt is rendered
            prompt_widget = pilot.app.query_one("#prompt", Static)
            assert "Enter the branch name" in str(prompt_widget.renderable)

            # Close dialog
            await pilot.press("escape")

    @pytest.mark.asyncio
    async def test_input_dialog_placeholder(self) -> None:
        """Test that placeholder text is displayed."""
        app = InputDialogTestApp(placeholder="feature/my-feature")

        async with app.run_test() as pilot:
            await pilot.pause()

            # Check placeholder
            input_widget = pilot.app.query_one("#input", Input)
            assert input_widget.placeholder == "feature/my-feature"

            # Close dialog
            await pilot.press("escape")

    @pytest.mark.asyncio
    async def test_input_dialog_initial_value(self) -> None:
        """Test that initial value is pre-populated."""
        app = InputDialogTestApp(initial_value="default-branch")

        async with app.run_test() as pilot:
            await pilot.pause()

            # Check initial value
            input_widget = pilot.app.query_one("#input", Input)
            assert input_widget.value == "default-branch"

            # Close dialog
            await pilot.press("escape")

    @pytest.mark.asyncio
    async def test_input_dialog_submit_button_returns_value(self) -> None:
        """Test that clicking Submit returns the input value."""
        app = InputDialogTestApp(initial_value="test-input")

        async with app.run_test() as pilot:
            await pilot.pause()

            # Click Submit button
            await pilot.click("#submit")
            await pilot.pause()

            assert app.result == "test-input"

    @pytest.mark.asyncio
    async def test_input_dialog_cancel_button_returns_none(self) -> None:
        """Test that clicking Cancel returns None."""
        app = InputDialogTestApp(initial_value="test-input")

        async with app.run_test() as pilot:
            await pilot.pause()

            # Click Cancel button
            await pilot.click("#cancel")
            await pilot.pause()

            assert app.result is None

    @pytest.mark.asyncio
    async def test_input_dialog_escape_returns_none(self) -> None:
        """Test that pressing Escape returns None."""
        app = InputDialogTestApp(initial_value="test-input")

        async with app.run_test() as pilot:
            await pilot.pause()

            # Press Escape
            await pilot.press("escape")
            await pilot.pause()

            assert app.result is None

    @pytest.mark.asyncio
    async def test_input_dialog_empty_input_returns_none(self) -> None:
        """Test that submitting empty input returns None."""
        app = InputDialogTestApp()

        async with app.run_test() as pilot:
            await pilot.pause()

            # Make sure input is empty and submit
            input_widget = pilot.app.query_one("#input", Input)
            input_widget.value = ""
            await pilot.pause()

            await pilot.click("#submit")
            await pilot.pause()

            assert app.result is None

    @pytest.mark.asyncio
    async def test_input_dialog_whitespace_only_returns_none(self) -> None:
        """Test that submitting whitespace-only input returns None."""
        app = InputDialogTestApp()

        async with app.run_test() as pilot:
            await pilot.pause()

            # Set whitespace-only value
            input_widget = pilot.app.query_one("#input", Input)
            input_widget.value = "   "
            await pilot.pause()

            await pilot.click("#submit")
            await pilot.pause()

            assert app.result is None

    @pytest.mark.asyncio
    async def test_input_dialog_input_focused_on_mount(self) -> None:
        """Test that input field is focused when dialog opens."""
        app = InputDialogTestApp()

        async with app.run_test() as pilot:
            await pilot.pause()

            # Check input is focused
            input_widget = pilot.app.query_one("#input", Input)
            assert input_widget.has_focus

            # Close dialog
            await pilot.press("escape")

    @pytest.mark.asyncio
    async def test_input_dialog_password_mode(self) -> None:
        """Test that password mode masks input."""
        app = InputDialogTestApp(password=True)

        async with app.run_test() as pilot:
            await pilot.pause()

            # Check password mode
            input_widget = pilot.app.query_one("#input", Input)
            assert input_widget.password is True

            # Close dialog
            await pilot.press("escape")


# =============================================================================
# Factory Fixture Tests
# =============================================================================


class TestDialogFactories:
    """Tests for dialog factory fixtures."""

    @pytest.mark.asyncio
    async def test_confirm_dialog_factory(
        self, confirm_dialog_factory: Callable[..., ConfirmDialog]
    ) -> None:
        """Test confirm_dialog_factory fixture."""
        dialog = confirm_dialog_factory(title="Test", message="Factory test")
        assert dialog.title_text == "Test"
        assert dialog.message_text == "Factory test"

    @pytest.mark.asyncio
    async def test_error_dialog_factory(
        self, error_dialog_factory: Callable[..., ErrorDialog]
    ) -> None:
        """Test error_dialog_factory fixture."""
        dialog = error_dialog_factory(message="Factory error", details="Details")
        assert dialog.error_message == "Factory error"
        assert dialog.error_details == "Details"

    @pytest.mark.asyncio
    async def test_input_dialog_factory(
        self, input_dialog_factory: Callable[..., InputDialog]
    ) -> None:
        """Test input_dialog_factory fixture."""
        dialog = input_dialog_factory(prompt="Enter name:", initial_value="test")
        assert dialog.prompt_text == "Enter name:"
        assert dialog.initial_value == "test"
