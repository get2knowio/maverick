"""Unit tests for TUI settings models."""

from __future__ import annotations

import pytest

from maverick.tui.models import ConfigOption


class TestConfigOption:
    """Tests for ConfigOption dataclass."""

    def test_creation_with_required_fields(self) -> None:
        """Test creating ConfigOption with required fields."""
        option = ConfigOption(
            key="debug_mode",
            display_name="Debug Mode",
            value=True,
            description="Enable debug logging",
            option_type="bool",
        )

        assert option.key == "debug_mode"
        assert option.display_name == "Debug Mode"
        assert option.value is True
        assert option.description == "Enable debug logging"
        assert option.option_type == "bool"
        assert option.choices is None  # default

    def test_creation_with_all_fields(self) -> None:
        """Test creating ConfigOption with all fields."""
        option = ConfigOption(
            key="theme",
            display_name="Theme",
            value="dark",
            description="UI theme",
            option_type="choice",
            choices=("dark", "light"),
        )

        assert option.key == "theme"
        assert option.display_name == "Theme"
        assert option.value == "dark"
        assert option.description == "UI theme"
        assert option.option_type == "choice"
        assert option.choices == ("dark", "light")

    def test_bool_option(self) -> None:
        """Test ConfigOption with bool value."""
        option = ConfigOption(
            key="enabled",
            display_name="Enabled",
            value=False,
            description="Enable feature",
            option_type="bool",
        )

        assert isinstance(option.value, bool)
        assert option.value is False

    def test_string_option(self) -> None:
        """Test ConfigOption with string value."""
        option = ConfigOption(
            key="api_key",
            display_name="API Key",
            value="secret123",
            description="API key",
            option_type="string",
        )

        assert isinstance(option.value, str)
        assert option.value == "secret123"

    def test_int_option(self) -> None:
        """Test ConfigOption with int value."""
        option = ConfigOption(
            key="timeout",
            display_name="Timeout",
            value=30,
            description="Timeout in seconds",
            option_type="int",
        )

        assert isinstance(option.value, int)
        assert option.value == 30

    def test_choice_option(self) -> None:
        """Test ConfigOption with choices."""
        option = ConfigOption(
            key="log_level",
            display_name="Log Level",
            value="info",
            description="Logging level",
            option_type="choice",
            choices=("debug", "info", "warning", "error"),
        )

        assert option.option_type == "choice"
        assert option.choices is not None
        assert len(option.choices) == 4
        assert "info" in option.choices

    def test_config_option_is_frozen(self) -> None:
        """Test ConfigOption is immutable (frozen)."""
        option = ConfigOption(
            key="test",
            display_name="Test",
            value="value",
            description="Test option",
            option_type="string",
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            option.value = "new_value"  # type: ignore[misc]


# =============================================================================
# ConfigScreenState Tests
