"""Maverick TUI screens package.

This module exports all screen classes for the Maverick TUI application.

NOTE: FlyScreen and RefuelScreen have been removed. Workflows are now
executed through the unified DSL-based workflow system via WorkflowScreen.
"""

from __future__ import annotations

from maverick.tui.screens.base import MaverickScreen
from maverick.tui.screens.config import ConfigScreen
from maverick.tui.screens.history_review import HistoricalReviewScreen
from maverick.tui.screens.home import HomeScreen
from maverick.tui.screens.review import ReviewScreen
from maverick.tui.screens.settings import SettingsScreen
from maverick.tui.screens.workflow import WorkflowScreen

__all__ = [
    "MaverickScreen",
    "ConfigScreen",
    "HistoricalReviewScreen",
    "HomeScreen",
    "ReviewScreen",
    "SettingsScreen",
    "WorkflowScreen",
]
