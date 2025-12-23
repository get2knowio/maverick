from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from maverick.tui.models.enums import SidebarMode
from maverick.tui.models.workflow import StageState


@dataclass(frozen=True, slots=True)
class NavigationEntry:
    """Entry in navigation history.

    Attributes:
        screen_name: Name of the screen class.
        params: Parameters passed to screen constructor.
        timestamp: When screen was pushed.
    """

    screen_name: str
    params: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""  # ISO 8601


@dataclass(frozen=True, slots=True)
class NavigationItem:
    """A navigation menu item."""

    id: str
    label: str
    icon: str
    shortcut: str | None = None


@dataclass(frozen=True, slots=True)
class SidebarState:
    """State for the sidebar widget."""

    mode: SidebarMode = SidebarMode.NAVIGATION
    navigation_items: tuple[NavigationItem, ...] = (
        NavigationItem("home", "Home", "H", "Ctrl+H"),
        NavigationItem("workflows", "Workflows", "W"),
        NavigationItem("settings", "Settings", "S", "Ctrl+,"),
    )
    workflow_stages: tuple[StageState, ...] = ()
    selected_nav_index: int = 0


@dataclass(frozen=True, slots=True)
class NavigationContext:
    """Tracks screen navigation history.

    Attributes:
        history: Stack of navigation entries.
    """

    history: tuple[NavigationEntry, ...] = ()

    @property
    def current_screen(self) -> NavigationEntry | None:
        """Get current screen entry."""
        if self.history:
            return self.history[-1]
        return None

    @property
    def can_go_back(self) -> bool:
        """Check if back navigation is possible."""
        return len(self.history) > 1

    @property
    def current_depth(self) -> int:
        """Get current navigation depth."""
        return len(self.history)
