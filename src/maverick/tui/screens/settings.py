"""Settings screen for Maverick TUI.

This module provides the SettingsScreen for configuring Maverick settings.
The screen provides:
- Form-based settings interface organized by sections
- Type-specific input validation
- Unsaved changes tracking with confirmation prompts
- Connection testing (GitHub, notifications)
- Save/cancel operations

Settings are loaded from and saved to the Maverick configuration system.
"""

from __future__ import annotations

from typing import Any

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.reactive import reactive
from textual.widgets import Button, Static

from maverick.tui.models import (
    SettingDefinition,
    SettingType,
    SettingValue,
)
from maverick.tui.screens.base import MaverickScreen
from maverick.tui.services import (
    check_github_connection,
    send_test_notification,
)
from maverick.tui.widgets.settings import SettingField, SettingsSection

__all__ = ["SettingsScreen"]


class SettingsScreen(MaverickScreen):
    """Screen for configuring Maverick settings.

    Provides a form-based interface for editing settings organized by
    category (GitHub, Notifications, Agents). Tracks unsaved changes
    and prompts before navigation.

    Features:
    - Type-specific input fields (string, bool, int)
    - Real-time validation with error display
    - Unsaved changes tracking
    - Connection testing (GitHub CLI, notifications)
    - Save/cancel operations
    - Confirmation prompt on navigation with unsaved changes

    Key bindings:
    - Escape: Cancel edit or go back (with confirmation if unsaved)
    - Ctrl+S: Save settings
    """

    TITLE = "Settings"

    BINDINGS = [
        Binding("escape", "go_back_safe", "Back", show=True),
        Binding("ctrl+s", "save", "Save", show=True),
    ]

    # Reactive state
    has_unsaved_changes: reactive[bool] = reactive(False)
    github_status: reactive[str] = reactive("")
    notification_status: reactive[str] = reactive("")

    def __init__(self, **kwargs: Any) -> None:
        """Initialize settings screen.

        Args:
            **kwargs: Additional screen arguments.
        """
        super().__init__(**kwargs)
        self._settings_fields: dict[str, SettingField] = {}
        self._original_values: dict[str, Any] = {}

    def compose(self) -> ComposeResult:
        """Compose the settings screen layout.

        Yields:
            Screen widgets including title, settings sections, test buttons,
            and action buttons.
        """
        yield Static("[bold]Settings[/bold]", id="title")

        with ScrollableContainer(id="settings-container"):
            # GitHub section
            github_section = SettingsSection("GitHub", id="github-section")
            yield github_section

            # Notifications section
            notifications_section = SettingsSection(
                "Notifications", id="notifications-section"
            )
            yield notifications_section

            # Agents section
            agents_section = SettingsSection("Agents", id="agents-section")
            yield agents_section

        # Action buttons
        with Horizontal(id="buttons"):
            yield Button("Save", id="save-btn", variant="primary")
            yield Button("Cancel", id="cancel-btn")

    def on_mount(self) -> None:
        """Load settings when screen is mounted."""
        self._load_settings()

    def _load_settings(self) -> None:
        """Load settings from configuration and populate fields."""
        # GitHub settings
        github_fields = [
            SettingValue(
                definition=SettingDefinition(
                    key="github.owner",
                    display_name="Owner",
                    description="GitHub repository owner",
                    setting_type=SettingType.STRING,
                ),
                current_value="",
                original_value="",
            ),
            SettingValue(
                definition=SettingDefinition(
                    key="github.repo",
                    display_name="Repository",
                    description="GitHub repository name",
                    setting_type=SettingType.STRING,
                ),
                current_value="",
                original_value="",
            ),
        ]

        # Notifications settings
        notification_fields = [
            SettingValue(
                definition=SettingDefinition(
                    key="notifications.enabled",
                    display_name="Enabled",
                    description="Enable push notifications",
                    setting_type=SettingType.BOOL,
                ),
                current_value=False,
                original_value=False,
            ),
            SettingValue(
                definition=SettingDefinition(
                    key="notifications.topic",
                    display_name="Topic",
                    description="ntfy.sh topic for notifications",
                    setting_type=SettingType.STRING,
                ),
                current_value="",
                original_value="",
            ),
        ]

        # Agent settings
        agent_fields = [
            SettingValue(
                definition=SettingDefinition(
                    key="agents.max_parallel",
                    display_name="Max Parallel Agents",
                    description="Maximum agents to run in parallel",
                    setting_type=SettingType.INT,
                    min_value=1,
                    max_value=10,
                ),
                current_value=3,
                original_value=3,
            ),
        ]

        # Mount fields to sections
        self._mount_section_fields("github-section", github_fields)
        self._mount_section_fields("notifications-section", notification_fields)
        self._mount_section_fields("agents-section", agent_fields)

    def _mount_section_fields(
        self, section_id: str, fields: list[SettingValue]
    ) -> None:
        """Mount setting fields to a section.

        Args:
            section_id: ID of the section to mount to.
            fields: List of SettingValue objects to create fields for.
        """
        try:
            section = self.query_one(f"#{section_id}", SettingsSection)
            content = section.query_one("#section-content", Vertical)

            for field_value in fields:
                field = SettingField(value=field_value)
                self._settings_fields[field_value.definition.key] = field
                self._original_values[field_value.definition.key] = (
                    field_value.original_value
                )
                content.mount(field)

            # Add test buttons for GitHub and Notifications sections
            if section_id == "github-section":
                content.mount(Button("Test Connection", id="test-github-btn"))
                content.mount(Static("", id="github-status"))
            elif section_id == "notifications-section":
                content.mount(Button("Test Notification", id="test-notification-btn"))
                content.mount(Static("", id="notification-status"))

        except Exception:
            # Section not mounted yet
            pass

    def on_setting_field_changed(self, message: SettingField.Changed) -> None:
        """Handle setting field changes.

        Args:
            message: Field changed message.
        """
        # Update unsaved changes flag
        self._update_unsaved_changes_flag()

    def _update_unsaved_changes_flag(self) -> None:
        """Update the unsaved changes flag based on field states."""
        has_changes = any(
            field.value.is_modified for field in self._settings_fields.values()
        )
        self.has_unsaved_changes = has_changes

    async def action_go_back_safe(self) -> None:
        """Navigate back, prompting if unsaved changes exist.

        Shows a confirmation dialog if there are unsaved changes.
        """
        if self.has_unsaved_changes:
            confirmed = await self.confirm(
                "Unsaved Changes", "You have unsaved changes. Discard them?"
            )
            if not confirmed:
                return

        self.go_back()

    async def action_save(self) -> None:
        """Save settings to configuration.

        Validates all fields before saving. Shows error if validation fails.
        """
        # Check for validation errors
        has_errors = any(
            not field.value.is_valid for field in self._settings_fields.values()
        )

        if has_errors:
            self.show_error(
                "Cannot save settings",
                details="Some fields have validation errors. Please fix them first.",
            )
            return

        # Save settings
        # TODO: Persist to actual MaverickConfig
        # For now, just update original values to match current
        for key, field in self._settings_fields.items():
            self._original_values[key] = field.value.current_value
            field.value = SettingValue(
                definition=field.value.definition,
                current_value=field.value.current_value,
                original_value=field.value.current_value,
            )

        # Clear unsaved changes flag
        self.has_unsaved_changes = False

        # Refresh fields to remove modified indicators
        for field in self._settings_fields.values():
            field.refresh(layout=True)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses.

        Args:
            event: Button pressed event.
        """
        if event.button.id == "save-btn":
            self.run_worker(self.action_save())
        elif event.button.id == "cancel-btn":
            self._cancel_changes()
        elif event.button.id == "test-github-btn":
            self.test_github_connection()
        elif event.button.id == "test-notification-btn":
            self.test_notification()

    def _cancel_changes(self) -> None:
        """Cancel changes and reset all fields to original values."""
        for field in self._settings_fields.values():
            field.reset()

        self.has_unsaved_changes = False

    @work(exclusive=True)
    async def test_github_connection(self) -> None:
        """Test GitHub CLI connection.

        Calls the GitHub connection service to verify authentication.
        Updates github_status reactive with result.
        """
        result = await check_github_connection(timeout=60.0)
        self.github_status = result.message
        self._update_status_display("github-status", self.github_status)

    @work(exclusive=True)
    async def test_notification(self) -> None:
        """Test notification delivery.

        Calls the notification service to send a test notification.
        Updates notification_status reactive with result.
        """
        # Get notification topic from settings
        topic_field = self._settings_fields.get("notifications.topic")
        enabled_field = self._settings_fields.get("notifications.enabled")

        if not enabled_field or not enabled_field.value.current_value:
            self.notification_status = "✗ Notifications are disabled"
            self._update_status_display("notification-status", self.notification_status)
            return

        if not topic_field or not topic_field.value.current_value:
            self.notification_status = "✗ No topic configured"
            self._update_status_display("notification-status", self.notification_status)
            return

        topic = topic_field.value.current_value

        # Send test notification using service
        result = await send_test_notification(
            topic=topic,
            message="Test notification from Maverick",
            timeout=60.0,
        )
        self.notification_status = result.message
        self._update_status_display("notification-status", self.notification_status)

    def _update_status_display(self, status_id: str, message: str) -> None:
        """Update a status display widget.

        Args:
            status_id: ID of the status Static widget.
            message: Status message to display.
        """
        try:
            status = self.query_one(f"#{status_id}", Static)
            status.update(message)
        except Exception:
            # Widget not found
            pass

    def watch_github_status(self, status: str) -> None:
        """Update GitHub status display when status changes.

        Args:
            status: New status message.
        """
        self._update_status_display("github-status", status)

    def watch_notification_status(self, status: str) -> None:
        """Update notification status display when status changes.

        Args:
            status: New status message.
        """
        self._update_status_display("notification-status", status)
