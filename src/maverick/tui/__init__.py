"""Maverick TUI package.

This module provides the terminal user interface for Maverick, built with Textual.
It exports the main MaverickApp class and supporting screens/widgets.
"""

from __future__ import annotations

from maverick.tui.app import MaverickApp
from maverick.tui.logging_handler import TUILoggingHandler, configure_tui_logging
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
from maverick.tui.workflow_runner import run_workflow_in_tui

__all__ = [
    # App
    "MaverickApp",
    # TUI Runner
    "run_workflow_in_tui",
    # Logging
    "TUILoggingHandler",
    "configure_tui_logging",
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
