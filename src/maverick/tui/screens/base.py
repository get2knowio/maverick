"""Base screen class for Maverick TUI.

This module provides the MaverickScreen base class that all Maverick screens
inherit from. It provides common functionality for navigation and modal dialog
support.
"""

from __future__ import annotations

from typing import Any

from textual.binding import Binding
from textual.screen import Screen

from maverick.tui.utils.connectivity import ConnectivityMonitor


class MaverickScreen(Screen[None]):
    """Base class for all Maverick screens.

    Provides common functionality for navigation and modal dialogs.
    All Maverick screens should inherit from this class to ensure
    consistent behavior across the application.

    Features:
        - Back navigation via Escape key
        - Confirmation dialogs with await support
        - Error dialogs with optional details
        - Screen stack awareness
        - Network connectivity monitoring

    Example:
        ```python
        class MyScreen(MaverickScreen):
            def compose(self) -> ComposeResult:
                yield Static("My content")

            async def action_save(self) -> None:
                if await self.confirm("Save", "Save changes?"):
                    # User confirmed
                    self.save_data()
        ```
    """

    BINDINGS = [
        Binding("escape", "go_back", "Back", show=True),
        Binding("enter", "select", "Select", show=False),
    ]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the screen with connectivity monitoring."""
        super().__init__(*args, **kwargs)
        self._connectivity_monitor = ConnectivityMonitor()
        # Track whether we've established a connectivity baseline
        # Only show notifications after we've confirmed connectivity at least once
        self._connectivity_baseline_established = False

    @property
    def can_go_back(self) -> bool:
        """Whether back navigation is available.

        Returns:
            True if there are screens to go back to, False if this is the
            only screen on the stack.
        """
        return len(self.app.screen_stack) > 1

    def on_mount(self) -> None:
        """Initialize connectivity monitoring on screen mount.

        Starts periodic connectivity checks every 30 seconds to monitor
        GitHub API availability. Subclasses that override this method
        should call super().on_mount() to ensure connectivity monitoring
        is properly initialized.
        """
        # Start periodic connectivity checks (every 30 seconds)
        self.set_interval(30.0, self._check_connectivity)

    async def _check_connectivity(self) -> None:
        """Check network connectivity and handle changes.

        This method is called periodically to check if GitHub API is
        reachable. When connectivity status changes, it calls
        _handle_connectivity_change() to allow screens to respond.

        The check runs asynchronously and does not block the UI.

        Note:
            Notifications are only shown after a connectivity baseline
            has been established (i.e., after a successful check).
            This prevents false notifications when the monitor starts
            with an assumed-connected state.
        """
        was_connected = self._connectivity_monitor.is_connected()
        is_connected = await self._connectivity_monitor.check_connectivity()

        # Establish baseline on first successful check
        if is_connected and not self._connectivity_baseline_established:
            self._connectivity_baseline_established = True
            return  # Don't notify on initial baseline establishment

        # Only notify on state changes after baseline is established
        if self._connectivity_baseline_established and was_connected != is_connected:
            self._handle_connectivity_change(is_connected)

    async def confirm(self, title: str, message: str) -> bool:
        """Show confirmation dialog and return user choice.

        Displays a modal dialog with Yes/No buttons. The dialog blocks
        until the user makes a choice.

        Args:
            title: Dialog title text.
            message: Dialog message/question text.

        Returns:
            True if user confirmed (Yes), False if user cancelled (No/Escape).

        Example:
            ```python
            if await self.confirm("Delete", "Delete this item?"):
                self.delete_item()
            ```
        """
        # Lazy import to avoid circular dependencies
        from maverick.tui.widgets.modal import ConfirmDialog

        return await self.app.push_screen_wait(
            ConfirmDialog(title=title, message=message)
        )

    def show_error(self, message: str, details: str | None = None) -> None:
        """Show error dialog.

        Displays a modal error dialog with a message and optional details.
        The dialog is non-blocking and can be dismissed by the user.

        Args:
            message: Primary error message to display.
            details: Optional detailed error information (e.g., stack trace,
                error context). If provided, will be shown in a collapsed
                section.

        Example:
            ```python
            try:
                self.process_data()
            except Exception as e:
                self.show_error(
                    "Failed to process data",
                    details=str(e)
                )
            ```
        """
        # Lazy import to avoid circular dependencies
        from maverick.tui.widgets.modal import ErrorDialog

        self.app.push_screen(ErrorDialog(message=message, details=details))

    def go_back(self) -> None:
        """Navigate to previous screen.

        Pops this screen from the stack, returning to the previous screen.
        Does nothing if this is the only screen on the stack.

        This method is safe to call from any screen - it will only pop if
        there's a screen to return to.

        Example:
            ```python
            def action_cancel(self) -> None:
                self.go_back()
            ```
        """
        if self.can_go_back:
            self.app.pop_screen()

    def action_go_back(self) -> None:
        """Escape key handler for back navigation.

        This action is bound to the Escape key by default. Subclasses can
        override this method to add confirmation dialogs or custom behavior
        before navigating back.

        Example:
            ```python
            async def action_go_back(self) -> None:
                if self.has_unsaved_changes:
                    if await self.confirm("Discard", "Discard changes?"):
                        self.go_back()
                else:
                    self.go_back()
            ```
        """
        self.go_back()

    def navigate_to(self, screen_name: str, **params: Any) -> None:
        """Navigate to a named screen.

        This method provides a centralized way to navigate between screens
        using screen names. It handles dynamic screen class loading to avoid
        circular dependencies.

        Args:
            screen_name: Name of screen to navigate to. Valid names:
                "fly", "refuel", "settings", "review", "home".
            **params: Parameters to pass to screen constructor.

        Raises:
            ValueError: If screen_name is not recognized.

        Example:
            ```python
            # Navigate to settings screen
            self.navigate_to("settings")

            # Navigate to workflow screen with parameters
            self.navigate_to("fly", branch_name="feature-123")
            ```
        """
        screen_map = {
            "fly": ("maverick.tui.screens.fly", "FlyScreen"),
            "refuel": ("maverick.tui.screens.refuel", "RefuelScreen"),
            "settings": ("maverick.tui.screens.settings", "SettingsScreen"),
            "review": ("maverick.tui.screens.review", "ReviewScreen"),
            "home": ("maverick.tui.screens.home", "HomeScreen"),
        }

        if screen_name not in screen_map:
            raise ValueError(
                f"Unknown screen: {screen_name}. "
                f"Valid screens: {', '.join(screen_map.keys())}"
            )

        module_name, class_name = screen_map[screen_name]

        # Dynamic import to avoid circular dependencies
        import importlib

        module = importlib.import_module(module_name)
        screen_class = getattr(module, class_name)
        self.app.push_screen(screen_class(**params))

    async def prompt_input(self, title: str, prompt: str, **kwargs: Any) -> str | None:
        """Show input dialog and return entered text.

        Displays a modal input dialog and waits for the user to submit or
        cancel. This is a convenience wrapper around InputDialog that
        simplifies common input scenarios.

        Args:
            title: Dialog title text.
            prompt: Input prompt/question text.
            **kwargs: Additional InputDialog options (placeholder,
                initial_value, password).

        Returns:
            Entered text if submitted, None if cancelled.

        Example:
            ```python
            branch = await self.prompt_input(
                "Branch Name",
                "Enter the branch name:",
                placeholder="feature/my-feature"
            )
            if branch:
                # User entered a branch name
                self.start_workflow(branch)
            ```
        """
        from maverick.tui.widgets.modal import InputDialog

        return await self.app.push_screen_wait(
            InputDialog(title=title, prompt=prompt, **kwargs)
        )

    async def confirm_cancel_workflow(self) -> bool:
        """Show cancellation confirmation dialog.

        Displays a modal confirmation dialog warning the user that cancelling
        will lose progress. This is a convenience method specifically for
        workflow cancellation scenarios.

        Returns:
            True if user confirmed cancellation, False if user chose to
            continue the workflow.

        Example:
            ```python
            if await self.confirm_cancel_workflow():
                self._cancel_workflow()
            ```
        """
        return await self.confirm(
            "Cancel Workflow", "Are you sure you want to cancel? Progress will be lost."
        )

    def get_shortcut_footer(self) -> str:
        """Get formatted keyboard shortcuts for footer.

        Returns a formatted string of all visible keyboard bindings for this
        screen. Shortcuts are displayed as "[key] description" pairs separated
        by spaces. This can be used to show available keyboard shortcuts in
        a footer or help display.

        Returns:
            Formatted string of keyboard shortcuts, or empty string if no
            visible shortcuts are defined.

        Example:
            ```python
            # In a screen's compose method:
            footer_text = self.get_shortcut_footer()
            yield Static(footer_text, classes="shortcut-footer")
            ```

            # Output format: "[escape] Back  [ctrl+s] Save  [?] Help"
        """
        shortcuts = []
        for binding in self.BINDINGS:
            if isinstance(binding, Binding) and binding.show:
                # Format as [key] description
                shortcuts.append(f"[{binding.key}] {binding.description}")
        return "  ".join(shortcuts)

    def _handle_connectivity_change(self, connected: bool) -> None:
        """Handle connectivity status change.

        This method is called when network connectivity status changes. It
        provides a hook for screens to respond to connectivity changes, such
        as pausing workflows when disconnected or resuming when reconnected.

        This implementation displays notifications to inform the user of
        connectivity changes. Subclasses should override this method to
        implement additional connectivity-aware behavior such as pausing
        or resuming workflows.

        Args:
            connected: True if connected to GitHub, False if disconnected.

        Example:
            ```python
            class WorkflowScreen(MaverickScreen):
                def _handle_connectivity_change(self, connected: bool) -> None:
                    super()._handle_connectivity_change(connected)
                    if not connected:
                        self._pause_workflow()
                    else:
                        self._resume_workflow()
            ```

        Note:
            This method is called asynchronously and should not block.
            Long-running operations should be dispatched to workers.
        """
        if not connected:
            self.app.notify(
                "Network connection lost. Workflow will pause.",
                title="Connection Lost",
                severity="warning",
                timeout=8.0,
            )
        else:
            self.app.notify(
                "Network connection restored. Workflow will resume.",
                title="Connection Restored",
                severity="information",
                timeout=5.0,
            )


__all__ = [
    "MaverickScreen",
]
