"""Maverick TUI package.

This module provides the terminal user interface for Maverick, built with Textual.
It exports the main MaverickApp class and supporting screens/widgets.
"""

from __future__ import annotations

from maverick.tui.app import MaverickApp
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
from maverick.tui.screens import ConfigScreen, HomeScreen, ReviewScreen, WorkflowScreen
from maverick.tui.widgets import LogPanel, Sidebar, StageIndicator, WorkflowList

__all__ = [
    # App
    "MaverickApp",
    # Screens
    "HomeScreen",
    "WorkflowScreen",
    "ReviewScreen",
    "ConfigScreen",
    # Widgets
    "Sidebar",
    "LogPanel",
    "StageIndicator",
    "WorkflowList",
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
