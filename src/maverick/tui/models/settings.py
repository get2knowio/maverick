from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from maverick.tui.models.enums import SettingType


@dataclass(frozen=True, slots=True)
class SettingDefinition:
    """Definition of a configurable setting.

    Attributes:
        key: Configuration key path (e.g., "github.owner").
        display_name: Human-readable name.
        description: Help text.
        setting_type: Type of value.
        choices: Available choices (for CHOICE type).
        min_value: Minimum value (for INT type).
        max_value: Maximum value (for INT type).
    """

    key: str
    display_name: str
    description: str
    setting_type: SettingType
    choices: tuple[str, ...] | None = None
    min_value: int | None = None
    max_value: int | None = None


@dataclass(frozen=True, slots=True)
class SettingValue:
    """Current value of a setting.

    Attributes:
        definition: The setting definition.
        current_value: Current value.
        original_value: Value when screen was opened.
        validation_error: Validation error (if any).
    """

    definition: SettingDefinition
    current_value: Any
    original_value: Any
    validation_error: str | None = None

    @property
    def is_modified(self) -> bool:
        """Check if value has changed."""
        return bool(self.current_value != self.original_value)

    @property
    def is_valid(self) -> bool:
        """Check if value is valid."""
        return self.validation_error is None


@dataclass(frozen=True, slots=True)
class SettingsSection:
    """Group of related settings.

    Attributes:
        name: Section name (e.g., "GitHub", "Notifications").
        settings: Settings in this section.
    """

    name: str
    settings: tuple[SettingValue, ...]


@dataclass(frozen=True, slots=True)
class ConfigOption:
    """A single configuration option."""

    key: str
    display_name: str
    value: str | bool | int
    description: str
    option_type: str  # "bool" | "string" | "int" | "choice"
    choices: tuple[str, ...] | None = None
