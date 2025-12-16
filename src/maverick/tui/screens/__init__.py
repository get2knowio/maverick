"""Maverick TUI screens package.

This module exports all screen classes for the Maverick TUI application.
"""

from __future__ import annotations

from maverick.tui.screens.config import ConfigScreen
from maverick.tui.screens.home import HomeScreen
from maverick.tui.screens.review import ReviewScreen
from maverick.tui.screens.workflow import WorkflowScreen

__all__ = [
    "ConfigScreen",
    "HomeScreen",
    "ReviewScreen",
    "WorkflowScreen",
]
