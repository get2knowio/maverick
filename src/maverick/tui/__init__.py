"""Maverick TUI package.

This module provides the terminal user interface for Maverick, built with Textual.
It exports the main MaverickApp class and supporting screens/widgets.
"""

from __future__ import annotations

from maverick.tui.models import (
    DARK_THEME,
    LIGHT_THEME,
    ConfigOption,
    ConfigScreenState,
    HomeScreenState,
    IssueSeverity,
    LogEntry,
    LogPanelState,
    NavigationItem,
    RecentWorkflowEntry,
    ReviewIssue,
    ReviewScreenState,
    ScreenState,
    SidebarMode,
    SidebarState,
    StageState,
    StageStatus,
    ThemeColors,
    WorkflowScreenState,
)

__all__ = [
    # Models
    "StageStatus",
    "IssueSeverity",
    "SidebarMode",
    "ScreenState",
    "RecentWorkflowEntry",
    "HomeScreenState",
    "StageState",
    "WorkflowScreenState",
    "ReviewIssue",
    "ReviewScreenState",
    "ConfigOption",
    "ConfigScreenState",
    "LogEntry",
    "LogPanelState",
    "NavigationItem",
    "SidebarState",
    "ThemeColors",
    "DARK_THEME",
    "LIGHT_THEME",
]
