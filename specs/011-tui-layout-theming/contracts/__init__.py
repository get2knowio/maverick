"""TUI contracts for Maverick.

This package defines Protocol interfaces for the TUI layer. These contracts
establish expected interfaces without dictating implementation details,
enabling:

1. Clear API boundaries between components
2. Type checking for implementations
3. Documentation of expected behavior
4. Test mock generation

Usage:
    from maverick.tui.contracts import MaverickAppProtocol, ScreenProtocol

    def create_mock_app() -> MaverickAppProtocol:
        ...
"""

from __future__ import annotations

from .app import MaverickAppProtocol
from .screens import (
    ConfigScreenProtocol,
    HomeScreenProtocol,
    ReviewScreenProtocol,
    ScreenProtocol,
    WorkflowScreenProtocol,
)
from .widgets import (
    LogPanelProtocol,
    SidebarProtocol,
    StageIndicatorProtocol,
    WidgetProtocol,
    WorkflowListProtocol,
)

__all__ = [
    # App
    "MaverickAppProtocol",
    # Screens
    "ScreenProtocol",
    "HomeScreenProtocol",
    "WorkflowScreenProtocol",
    "ReviewScreenProtocol",
    "ConfigScreenProtocol",
    # Widgets
    "WidgetProtocol",
    "LogPanelProtocol",
    "SidebarProtocol",
    "StageIndicatorProtocol",
    "WorkflowListProtocol",
]
