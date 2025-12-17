"""Maverick TUI screens package.

This module exports all screen classes for the Maverick TUI application.
"""

from __future__ import annotations

from maverick.tui.screens.base import MaverickScreen
from maverick.tui.screens.config import ConfigScreen
from maverick.tui.screens.fly import FlyScreen
from maverick.tui.screens.history_review import HistoricalReviewScreen
from maverick.tui.screens.home import HomeScreen
from maverick.tui.screens.refuel import RefuelScreen
from maverick.tui.screens.review import ReviewScreen
from maverick.tui.screens.settings import SettingsScreen
from maverick.tui.screens.workflow import WorkflowScreen

__all__ = [
    "MaverickScreen",
    "ConfigScreen",
    "FlyScreen",
    "HistoricalReviewScreen",
    "HomeScreen",
    "RefuelScreen",
    "ReviewScreen",
    "SettingsScreen",
    "WorkflowScreen",
]
