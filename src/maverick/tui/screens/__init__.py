"""Maverick TUI screens package.

This module exports all screen classes for the Maverick TUI application.

The workflow system uses three screens:
- WorkflowBrowserScreen: Discover and select workflows
- WorkflowInputScreen: Configure workflow inputs
- WorkflowExecutionScreen: Execute and monitor workflow progress
"""

from __future__ import annotations

from maverick.tui.screens.base import MaverickScreen
from maverick.tui.screens.config import ConfigScreen
from maverick.tui.screens.dashboard import DashboardScreen
from maverick.tui.screens.history_review import HistoricalReviewScreen
from maverick.tui.screens.home import HomeScreen
from maverick.tui.screens.review import ReviewScreen
from maverick.tui.screens.settings import SettingsScreen
from maverick.tui.screens.workflow import WorkflowScreen
from maverick.tui.screens.workflow_browser import WorkflowBrowserScreen
from maverick.tui.screens.workflow_execution import WorkflowExecutionScreen
from maverick.tui.screens.workflow_input import WorkflowInputScreen

__all__ = [
    "MaverickScreen",
    "ConfigScreen",
    "DashboardScreen",
    "HistoricalReviewScreen",
    "HomeScreen",
    "ReviewScreen",
    "SettingsScreen",
    "WorkflowScreen",
    "WorkflowBrowserScreen",
    "WorkflowExecutionScreen",
    "WorkflowInputScreen",
]
