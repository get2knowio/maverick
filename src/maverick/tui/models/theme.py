"""Theme customization infrastructure for Maverick TUI.

This module provides the foundation for theme customization including:
- Color palette definitions (ThemeColors)
- Predefined themes (dark, light)
- Accent color presets
- Theme manager for runtime switching (ThemeManager)
- CSS variable generation for Textual

Feature: TUI Dramatic Improvement - Sprint 3
Date: 2026-01-12
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class ThemeMode(str, Enum):
    """Available theme modes."""

    DARK = "dark"
    LIGHT = "light"
    SYSTEM = "system"  # Future: follow system preference


class AccentColor(str, Enum):
    """Predefined accent color options."""

    BLUE = "blue"
    GREEN = "green"
    PURPLE = "purple"
    ORANGE = "orange"
    PINK = "pink"
    CYAN = "cyan"


# Accent color definitions (primary, muted)
ACCENT_COLORS: dict[AccentColor, tuple[str, str]] = {
    AccentColor.BLUE: ("#00aaff", "#0077aa"),
    AccentColor.GREEN: ("#4caf50", "#388e3c"),
    AccentColor.PURPLE: ("#9c27b0", "#7b1fa2"),
    AccentColor.ORANGE: ("#ff9800", "#f57c00"),
    AccentColor.PINK: ("#e91e63", "#c2185b"),
    AccentColor.CYAN: ("#00bcd4", "#0097a7"),
}


@dataclass(frozen=True, slots=True)
class ThemeColors:
    """Color palette for a theme.

    All colors are hex strings suitable for CSS. The palette is designed
    to maintain WCAG AA contrast ratios against the background color.

    Attributes:
        background: Main background color.
        surface: Elevated surface (cards, panels).
        surface_elevated: Further elevated surfaces.
        border: Default border color.
        border_focus: Border color when focused.
        text: Primary text color.
        text_muted: Secondary/muted text.
        text_dim: Tertiary/dim text.
        success: Success state color.
        warning: Warning state color.
        error: Error state color.
        info: Info state color.
        accent: Primary accent color.
        accent_muted: Muted accent variant.
    """

    # Backgrounds
    background: str = "#1a1a1a"
    surface: str = "#242424"
    surface_elevated: str = "#2d2d2d"

    # Borders
    border: str = "#3a3a3a"
    border_focus: str = "#00aaff"

    # Text
    text: str = "#e0e0e0"
    text_muted: str = "#808080"
    text_dim: str = "#606060"

    # Status
    success: str = "#4caf50"
    warning: str = "#ff9800"
    error: str = "#f44336"
    info: str = "#2196f3"

    # Accent
    accent: str = "#00aaff"
    accent_muted: str = "#0077aa"

    def with_accent(self, accent_color: AccentColor) -> ThemeColors:
        """Create a new ThemeColors with different accent.

        Args:
            accent_color: The accent color preset to use.

        Returns:
            New ThemeColors instance with updated accent colors.
        """
        primary, muted = ACCENT_COLORS[accent_color]
        return replace(self, accent=primary, accent_muted=muted, border_focus=primary)

    def to_css_variables(self) -> str:
        """Generate CSS variable definitions for this theme.

        Returns:
            CSS string with variable definitions.
        """
        return f"""
$background: {self.background};
$surface: {self.surface};
$surface-elevated: {self.surface_elevated};
$border: {self.border};
$border-focus: {self.border_focus};
$text: {self.text};
$text-muted: {self.text_muted};
$text-dim: {self.text_dim};
$success: {self.success};
$warning: {self.warning};
$error: {self.error};
$info: {self.info};
$accent: {self.accent};
$accent-muted: {self.accent_muted};
"""


# Default theme instances
DARK_THEME = ThemeColors()

LIGHT_THEME = ThemeColors(
    background="#f5f5f5",
    surface="#ffffff",
    surface_elevated="#fafafa",
    border="#e0e0e0",
    border_focus="#0066cc",
    text="#1a1a1a",
    text_muted="#606060",
    text_dim="#909090",
    success="#388e3c",
    warning="#f57c00",
    error="#d32f2f",
    info="#1976d2",
    accent="#0066cc",
    accent_muted="#004499",
)

# Theme registry
THEMES: dict[ThemeMode, ThemeColors] = {
    ThemeMode.DARK: DARK_THEME,
    ThemeMode.LIGHT: LIGHT_THEME,
    ThemeMode.SYSTEM: DARK_THEME,  # Default to dark for now
}


@dataclass
class ThemePreferences:
    """User's theme preferences.

    Attributes:
        mode: Selected theme mode (dark/light/system).
        accent: Selected accent color.
    """

    mode: ThemeMode = ThemeMode.DARK
    accent: AccentColor = AccentColor.BLUE

    def to_dict(self) -> dict[str, str]:
        """Convert to dictionary for persistence."""
        return {
            "mode": self.mode.value,
            "accent": self.accent.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> ThemePreferences:
        """Create from dictionary.

        Args:
            data: Dictionary with mode and accent keys.

        Returns:
            ThemePreferences instance.
        """
        mode = ThemeMode(data.get("mode", "dark"))
        accent = AccentColor(data.get("accent", "blue"))
        return cls(mode=mode, accent=accent)


@dataclass
class ThemeManager:
    """Manages theme state and switching.

    This class provides the infrastructure for runtime theme switching.
    It maintains the current theme and notifies listeners when changes occur.

    Example:
        manager = ThemeManager()
        manager.add_listener(lambda colors: app.refresh_css())
        manager.set_mode(ThemeMode.LIGHT)
        manager.set_accent(AccentColor.GREEN)

    Attributes:
        preferences: Current theme preferences.
    """

    preferences: ThemePreferences = field(default_factory=ThemePreferences)
    _listeners: list[Callable[[ThemeColors], None]] = field(
        default_factory=list, repr=False
    )

    @property
    def current_theme(self) -> ThemeColors:
        """Get the current theme colors with accent applied."""
        base = THEMES[self.preferences.mode]
        return base.with_accent(self.preferences.accent)

    def add_listener(self, callback: Callable[[ThemeColors], None]) -> None:
        """Add a listener for theme changes.

        Args:
            callback: Function called with new ThemeColors when theme changes.
        """
        self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[ThemeColors], None]) -> None:
        """Remove a theme change listener.

        Args:
            callback: The callback to remove.
        """
        if callback in self._listeners:
            self._listeners.remove(callback)

    def _notify_listeners(self) -> None:
        """Notify all listeners of theme change."""
        theme = self.current_theme
        for listener in self._listeners:
            listener(theme)

    def set_mode(self, mode: ThemeMode) -> None:
        """Set the theme mode.

        Args:
            mode: New theme mode.
        """
        if self.preferences.mode != mode:
            self.preferences = ThemePreferences(
                mode=mode,
                accent=self.preferences.accent,
            )
            self._notify_listeners()

    def set_accent(self, accent: AccentColor) -> None:
        """Set the accent color.

        Args:
            accent: New accent color.
        """
        if self.preferences.accent != accent:
            self.preferences = ThemePreferences(
                mode=self.preferences.mode,
                accent=accent,
            )
            self._notify_listeners()

    def set_preferences(self, preferences: ThemePreferences) -> None:
        """Set full preferences at once.

        Args:
            preferences: New preferences.
        """
        if self.preferences != preferences:
            self.preferences = preferences
            self._notify_listeners()


# Global theme manager instance (singleton pattern)
_theme_manager: ThemeManager | None = None


def get_theme_manager() -> ThemeManager:
    """Get the global theme manager instance.

    Returns:
        The global ThemeManager singleton.
    """
    global _theme_manager
    if _theme_manager is None:
        _theme_manager = ThemeManager()
    return _theme_manager


def get_current_theme() -> ThemeColors:
    """Get the current active theme colors.

    Convenience function for accessing theme colors without
    directly accessing the manager.

    Returns:
        Current ThemeColors.
    """
    return get_theme_manager().current_theme
