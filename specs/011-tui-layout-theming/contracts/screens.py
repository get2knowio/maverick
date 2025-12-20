"""Screen contracts for Maverick TUI.

This module defines the Protocol interfaces for TUI screens. These contracts
establish the expected interface without dictating implementation details.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from textual.app import ComposeResult
    from textual.binding import Binding


@runtime_checkable
class ScreenProtocol(Protocol):
    """Protocol for all TUI screens.

    All screens must implement compose() to define their layout and may
    optionally define BINDINGS for screen-specific keybindings.
    """

    BINDINGS: list[Binding]

    def compose(self) -> ComposeResult:
        """Compose the screen's widget tree.

        Returns:
            ComposeResult yielding child widgets.
        """
        ...

    async def on_mount(self) -> None:
        """Called when screen is mounted to the app.

        Use for initialization that requires the screen to be attached
        to the app, such as querying widgets or starting timers.
        """
        ...


@runtime_checkable
class HomeScreenProtocol(ScreenProtocol, Protocol):
    """Protocol for the home screen.

    The home screen displays workflow selection options and recent workflow
    runs. It serves as the application's landing page.
    """

    def refresh_recent_workflows(self) -> None:
        """Refresh the list of recent workflow runs.

        Loads the 10 most recent workflow entries and updates the display.
        """
        ...

    def select_workflow(self, index: int) -> None:
        """Select a workflow from the recent list.

        Args:
            index: Index of the workflow to select (0-based).
        """
        ...


@runtime_checkable
class WorkflowScreenProtocol(ScreenProtocol, Protocol):
    """Protocol for the workflow progress screen.

    Displays active workflow stages with status indicators, elapsed time,
    and current stage details.
    """

    @property
    def workflow_name(self) -> str:
        """Get the current workflow name."""
        ...

    @property
    def elapsed_time(self) -> float:
        """Get elapsed time in seconds."""
        ...

    def update_stage(self, stage_name: str, status: str) -> None:
        """Update the status of a workflow stage.

        Args:
            stage_name: Name of the stage to update.
            status: New status ("pending", "active", "completed", "failed").
        """
        ...

    def show_stage_error(self, stage_name: str, error: str) -> None:
        """Display an error for a failed stage.

        Args:
            stage_name: Name of the failed stage.
            error: Error message to display.
        """
        ...


@runtime_checkable
class ReviewScreenProtocol(ScreenProtocol, Protocol):
    """Protocol for the code review results screen.

    Displays organized review findings with severity indicators and
    navigation between issues.
    """

    def load_issues(self, issues: list[dict[str, object]]) -> None:
        """Load review issues for display.

        Args:
            issues: List of issue dictionaries with file_path, line_number,
                   severity, message, and source fields.
        """
        ...

    def filter_by_severity(self, severity: str | None) -> None:
        """Filter displayed issues by severity.

        Args:
            severity: Severity to filter ("error", "warning", "info",
                     "suggestion") or None for all issues.
        """
        ...

    def navigate_to_issue(self, index: int) -> None:
        """Navigate to a specific issue.

        Args:
            index: Index of the issue in the filtered list.
        """
        ...


@runtime_checkable
class ConfigScreenProtocol(ScreenProtocol, Protocol):
    """Protocol for the configuration screen.

    Displays application settings organized by category with inline
    editing capabilities.
    """

    def load_config(self) -> None:
        """Load current configuration values for display."""
        ...

    def edit_option(self, key: str) -> None:
        """Enter edit mode for a configuration option.

        Args:
            key: Configuration key to edit.
        """
        ...

    def save_option(self, key: str, value: object) -> None:
        """Save a modified configuration value.

        Args:
            key: Configuration key.
            value: New value (type depends on option).
        """
        ...

    def cancel_edit(self) -> None:
        """Cancel the current edit operation."""
        ...
