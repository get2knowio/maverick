"""Unit tests for TUI theme models.

Tests for:
- ThemeColors
- DARK_THEME constant
- LIGHT_THEME constant
"""

from __future__ import annotations

import pytest

from maverick.tui.models import (
    DARK_THEME,
    LIGHT_THEME,
    ThemeColors,
)

# =============================================================================
# ThemeColors Tests
# =============================================================================


class TestThemeColors:
    """Tests for ThemeColors dataclass."""

    def test_creation_with_defaults(self) -> None:
        """Test creating ThemeColors with default values."""
        theme = ThemeColors()

        # Backgrounds
        assert theme.background == "#1a1a1a"
        assert theme.surface == "#242424"
        assert theme.surface_elevated == "#2d2d2d"

        # Borders
        assert theme.border == "#3a3a3a"
        assert theme.border_focus == "#00aaff"

        # Text
        assert theme.text == "#e0e0e0"
        assert theme.text_muted == "#808080"
        assert theme.text_dim == "#606060"

        # Status
        assert theme.success == "#4caf50"
        assert theme.warning == "#ff9800"
        assert theme.error == "#f44336"
        assert theme.info == "#2196f3"

        # Accent
        assert theme.accent == "#00aaff"
        assert theme.accent_muted == "#0077aa"

    def test_creation_with_custom_colors(self) -> None:
        """Test creating ThemeColors with custom colors."""
        theme = ThemeColors(
            background="#ffffff",
            text="#000000",
            success="#00ff00",
        )

        assert theme.background == "#ffffff"
        assert theme.text == "#000000"
        assert theme.success == "#00ff00"

        # Other fields should still have defaults
        assert theme.surface == "#242424"
        assert theme.border == "#3a3a3a"

    def test_theme_colors_is_frozen(self) -> None:
        """Test ThemeColors is immutable (frozen)."""
        theme = ThemeColors()

        with pytest.raises(Exception):  # FrozenInstanceError
            theme.background = "#ffffff"  # type: ignore[misc]

    def test_theme_colors_has_slots(self) -> None:
        """Test ThemeColors uses slots for memory efficiency."""
        theme = ThemeColors()

        # Frozen dataclasses with slots raise TypeError when setting new attributes
        with pytest.raises((AttributeError, TypeError)):
            theme.extra_color = "#123456"  # type: ignore[attr-defined]


# =============================================================================
# Theme Constants Tests
# =============================================================================


class TestThemeConstants:
    """Tests for DARK_THEME and LIGHT_THEME constants."""

    def test_dark_theme_constant(self) -> None:
        """Test DARK_THEME constant has correct values."""
        assert DARK_THEME.background == "#1a1a1a"
        assert DARK_THEME.surface == "#242424"
        assert DARK_THEME.text == "#e0e0e0"
        assert DARK_THEME.success == "#4caf50"

    def test_light_theme_constant(self) -> None:
        """Test LIGHT_THEME constant has correct values."""
        assert LIGHT_THEME.background == "#f5f5f5"
        assert LIGHT_THEME.surface == "#ffffff"
        assert LIGHT_THEME.surface_elevated == "#fafafa"
        assert LIGHT_THEME.border == "#e0e0e0"
        assert LIGHT_THEME.border_focus == "#0066cc"
        assert LIGHT_THEME.text == "#1a1a1a"
        assert LIGHT_THEME.text_muted == "#606060"
        assert LIGHT_THEME.text_dim == "#909090"
        assert LIGHT_THEME.success == "#388e3c"
        assert LIGHT_THEME.warning == "#f57c00"
        assert LIGHT_THEME.error == "#d32f2f"
        assert LIGHT_THEME.info == "#1976d2"
        assert LIGHT_THEME.accent == "#0066cc"
        assert LIGHT_THEME.accent_muted == "#004499"

    def test_dark_theme_is_theme_colors_instance(self) -> None:
        """Test DARK_THEME is a ThemeColors instance."""
        assert isinstance(DARK_THEME, ThemeColors)

    def test_light_theme_is_theme_colors_instance(self) -> None:
        """Test LIGHT_THEME is a ThemeColors instance."""
        assert isinstance(LIGHT_THEME, ThemeColors)

    def test_themes_are_different(self) -> None:
        """Test DARK_THEME and LIGHT_THEME have different values."""
        assert DARK_THEME.background != LIGHT_THEME.background
        assert DARK_THEME.text != LIGHT_THEME.text
        assert DARK_THEME.accent != LIGHT_THEME.accent

    def test_themes_are_frozen(self) -> None:
        """Test theme constants are immutable."""
        with pytest.raises(Exception):  # FrozenInstanceError
            DARK_THEME.background = "#000000"  # type: ignore[misc]

        with pytest.raises(Exception):  # FrozenInstanceError
            LIGHT_THEME.background = "#ffffff"  # type: ignore[misc]
