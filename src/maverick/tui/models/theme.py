from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ThemeColors:
    """Color palette for a theme."""

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
