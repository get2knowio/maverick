"""Widget contracts for Maverick TUI.

This module defines the Protocol interfaces for TUI widgets. These contracts
establish the expected interface for reusable components.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from textual.app import ComposeResult


@runtime_checkable
class WidgetProtocol(Protocol):
    """Base protocol for all TUI widgets.

    Widgets must implement compose() or render() to define their appearance.
    """

    def compose(self) -> ComposeResult:
        """Compose the widget's children.

        Returns:
            ComposeResult yielding child widgets.
        """
        ...


@runtime_checkable
class LogPanelProtocol(Protocol):
    """Protocol for the collapsible log panel.

    The log panel displays streaming agent output with syntax highlighting
    and level-based coloring.
    """

    @property
    def visible(self) -> bool:
        """Whether the log panel is currently visible."""
        ...

    @visible.setter
    def visible(self, value: bool) -> None:
        """Set log panel visibility."""
        ...

    def add_log(self, message: str, level: str = "info", source: str = "") -> None:
        """Add a log entry to the panel.

        Args:
            message: Log message content.
            level: Log level ("info", "success", "warning", "error").
            source: Source component/agent name.
        """
        ...

    def clear(self) -> None:
        """Clear all log entries."""
        ...

    def toggle(self) -> None:
        """Toggle visibility of the log panel."""
        ...


@runtime_checkable
class SidebarProtocol(Protocol):
    """Protocol for the sidebar widget.

    The sidebar displays either navigation menu (when no workflow active)
    or workflow stages with status indicators (during workflow execution).
    """

    @property
    def mode(self) -> str:
        """Current display mode ("navigation" or "workflow")."""
        ...

    def set_navigation_mode(self) -> None:
        """Switch to navigation menu mode."""
        ...

    def set_workflow_mode(self, stages: list[dict[str, object]]) -> None:
        """Switch to workflow stages mode.

        Args:
            stages: List of stage dictionaries with name, display_name,
                   and status fields.
        """
        ...

    def update_stage_status(self, stage_name: str, status: str) -> None:
        """Update the status of a workflow stage.

        Args:
            stage_name: Name of the stage.
            status: New status ("pending", "active", "completed", "failed").
        """
        ...

    def select_item(self, index: int) -> None:
        """Select a navigation item or stage by index.

        Args:
            index: Item index (0-based).
        """
        ...


@runtime_checkable
class StageIndicatorProtocol(Protocol):
    """Protocol for individual stage status indicators.

    Displays a single workflow stage with icon, name, and status styling.
    """

    @property
    def status(self) -> str:
        """Current stage status."""
        ...

    @status.setter
    def status(self, value: str) -> None:
        """Update the stage status.

        Updates the icon and styling based on status:
        - pending: ○ (muted)
        - active: ◉ (accent, bold)
        - completed: ✓ (success)
        - failed: ✗ (error)
        """
        ...


@runtime_checkable
class WorkflowListProtocol(Protocol):
    """Protocol for the recent workflows list widget.

    Displays a list of recent workflow runs with status and metadata.
    """

    def set_workflows(self, workflows: list[dict[str, object]]) -> None:
        """Set the list of workflows to display.

        Args:
            workflows: List of workflow dictionaries with branch_name,
                      workflow_type, status, started_at, and pr_url fields.
        """
        ...

    def select(self, index: int) -> None:
        """Select a workflow by index.

        Args:
            index: Workflow index (0-based).
        """
        ...

    @property
    def selected_index(self) -> int:
        """Currently selected workflow index."""
        ...
