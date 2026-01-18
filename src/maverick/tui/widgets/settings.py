"""Settings widgets for Maverick TUI.

This module provides widgets for the SettingsScreen, including:
- SettingsSection: Collapsible group of related settings
- SettingField: Individual configurable setting with type-specific input

These widgets work with the SettingDefinition and SettingValue models from
maverick.tui.models to provide a form-based settings interface.
"""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Input, Static, Switch

from maverick.tui.models import SettingType, SettingValue

__all__ = ["SettingsSection", "SettingField"]


class SettingField(Widget):
    """A single configurable setting with type-specific input.

    Renders different input widgets based on the setting type:
    - STRING: Input widget for text entry
    - BOOL: Switch widget for toggle
    - INT: Input widget with numeric validation
    - CHOICE: (future) Dropdown/select widget

    Attributes:
        value: The SettingValue containing definition and current/original values.
    """

    DEFAULT_CSS = """
    SettingField {
        height: auto;
        layout: vertical;
        margin-bottom: 1;
    }

    SettingField .setting-label {
        margin-bottom: 0;
        color: #e0e0e0;
    }

    SettingField .setting-description {
        color: #808080;
        margin-bottom: 1;
    }

    SettingField Input {
        margin-bottom: 0;
    }

    SettingField Switch {
        margin-bottom: 0;
    }

    SettingField .modified-indicator {
        color: #ff9800;
    }

    SettingField .validation-error {
        color: #f44336;
        margin-top: 0;
    }
    """

    class Changed(Message):
        """Posted when the setting value changes.

        Attributes:
            key: The setting key that changed.
            value: The new value.
        """

        def __init__(self, key: str, value: Any) -> None:
            self.key = key
            self.value = value
            super().__init__()

    def __init__(
        self,
        value: SettingValue,
        **kwargs: Any,
    ) -> None:
        """Initialize setting field.

        Args:
            value: SettingValue containing definition and values.
            **kwargs: Additional widget arguments.
        """
        super().__init__(**kwargs)
        self.value = value

    def compose(self) -> ComposeResult:
        """Compose the field widgets."""
        # Show modified indicator
        modified = " *" if self.value.is_modified else ""
        yield Static(
            f"{self.value.definition.display_name}{modified}",
            classes="setting-label",
        )
        yield Static(
            self.value.definition.description,
            classes="setting-description",
        )

        # Render type-specific input
        # Note: Replace dots with hyphens in IDs as Textual doesn't allow dots
        input_id = f"input-{self.value.definition.key.replace('.', '-')}"
        setting_type = self.value.definition.setting_type

        if setting_type == SettingType.BOOL:
            yield Switch(
                value=bool(self.value.current_value),
                id=input_id,
            )
        elif setting_type == SettingType.INT:
            yield Input(
                str(self.value.current_value),
                id=input_id,
                restrict=r"^-?[0-9]*$",
            )
        else:  # STRING or default
            yield Input(
                str(self.value.current_value),
                id=input_id,
            )

        # Show validation error if present
        if self.value.validation_error:
            yield Static(
                f"✗ {self.value.validation_error}",
                classes="validation-error",
            )

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input value changes.

        Args:
            event: The input changed event.
        """
        # Note: Replace dots with hyphens in IDs as Textual doesn't allow dots
        expected_id = f"input-{self.value.definition.key.replace('.', '-')}"
        if event.input.id != expected_id:
            return

        new_value: Any = event.value

        # Convert based on type
        setting_type = self.value.definition.setting_type
        validation_error: str | None = None

        if setting_type == SettingType.INT:
            try:
                new_value = int(event.value) if event.value else 0

                # Validate min/max
                if (
                    self.value.definition.min_value is not None
                    and new_value < self.value.definition.min_value
                ):
                    validation_error = (
                        f"Value must be at least {self.value.definition.min_value}"
                    )
                elif (
                    self.value.definition.max_value is not None
                    and new_value > self.value.definition.max_value
                ):
                    validation_error = (
                        f"Value must be at most {self.value.definition.max_value}"
                    )
            except ValueError:
                validation_error = "Invalid number"
                new_value = self.value.current_value

        # Update value
        self.value = SettingValue(
            definition=self.value.definition,
            current_value=new_value,
            original_value=self.value.original_value,
            validation_error=validation_error,
        )

        # Post change message
        self.post_message(self.Changed(self.value.definition.key, new_value))

        # Update display
        self.refresh(layout=True)

    def on_switch_changed(self, event: Switch.Changed) -> None:
        """Handle switch value changes.

        Args:
            event: The switch changed event.
        """
        # Note: Replace dots with hyphens in IDs as Textual doesn't allow dots
        expected_id = f"input-{self.value.definition.key.replace('.', '-')}"
        if event.switch.id != expected_id:
            return

        # Update value
        self.value = SettingValue(
            definition=self.value.definition,
            current_value=event.value,
            original_value=self.value.original_value,
        )

        # Post change message
        self.post_message(self.Changed(self.value.definition.key, event.value))

        # Update display
        self.refresh(layout=True)

    def reset(self) -> None:
        """Reset field to original value."""
        self.value = SettingValue(
            definition=self.value.definition,
            current_value=self.value.original_value,
            original_value=self.value.original_value,
        )
        self.refresh(layout=True)


class SettingsSection(Widget):
    """A collapsible section of related settings.

    Groups settings by category (e.g., "GitHub", "Notifications", "Agents")
    with expand/collapse functionality.

    Attributes:
        section_name: Display name for the section.
        expanded: Whether the section is expanded to show settings.
    """

    DEFAULT_CSS = """
    SettingsSection {
        height: auto;
        margin-bottom: 2;
    }

    SettingsSection .section-header {
        text-style: bold;
        margin-bottom: 1;
        color: #e0e0e0;
    }

    SettingsSection #section-content {
        height: auto;
    }

    SettingsSection #section-content.collapsed {
        display: none;
    }
    """

    expanded: reactive[bool] = reactive(True)

    def __init__(self, name: str, **kwargs: Any) -> None:
        """Initialize settings section.

        Args:
            name: Section display name.
            **kwargs: Additional widget arguments.
        """
        super().__init__(**kwargs)
        self.section_name = name

    def compose(self) -> ComposeResult:
        """Compose the section widgets."""
        icon = "▼" if self.expanded else "▶"
        yield Static(f"{icon} {self.section_name}", classes="section-header")
        content_classes = "" if self.expanded else "collapsed"
        yield Vertical(id="section-content", classes=content_classes)

    def watch_expanded(self, expanded: bool) -> None:
        """Update display when expanded state changes.

        Args:
            expanded: New expanded state.
        """
        # Update header icon
        try:
            header = self.query_one(".section-header", Static)
            icon = "▼" if expanded else "▶"
            header.update(f"{icon} {self.section_name}")

            # Update content visibility
            content = self.query_one("#section-content", Vertical)
            if expanded:
                content.remove_class("collapsed")
            else:
                content.add_class("collapsed")
        except Exception:
            # Not mounted yet
            pass
