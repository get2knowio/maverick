"""Screen component interfaces for TUI interactive screens.

This module defines the Protocol interfaces for all screens in the Maverick TUI.
These protocols define the expected methods and properties for each screen type.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from maverick.tui.models import (
        ReviewFinding,
        WorkflowHistoryEntry,
    )


# =============================================================================
# Base Screen Protocol
# =============================================================================


@runtime_checkable
class MaverickScreenProtocol(Protocol):
    """Base protocol for all Maverick screens.

    All screens must implement these common methods for navigation
    and modal dialog support.
    """

    @property
    def can_go_back(self) -> bool:
        """Whether back navigation is available."""
        ...

    async def confirm(self, title: str, message: str) -> bool:
        """Show confirmation dialog and return user choice.

        Args:
            title: Dialog title.
            message: Dialog message.

        Returns:
            True if user confirmed, False otherwise.
        """
        ...

    def show_error(self, message: str, details: str | None = None) -> None:
        """Show error dialog.

        Args:
            message: Error message.
            details: Optional detailed error information.
        """
        ...

    def go_back(self) -> None:
        """Navigate to previous screen."""
        ...


# =============================================================================
# HomeScreen Protocol
# =============================================================================


@runtime_checkable
class HomeScreenProtocol(MaverickScreenProtocol, Protocol):
    """Protocol for the home screen.

    The home screen displays recent workflows and navigation options.
    """

    def load_history(self) -> None:
        """Load workflow history from storage.

        Populates recent_workflows state from ~/.config/maverick/history.json.
        """
        ...

    def refresh_history(self) -> None:
        """Refresh the workflow history display.

        Reloads from storage and updates the UI.
        """
        ...

    def select_workflow(self, index: int) -> None:
        """Select a workflow from the history list.

        Args:
            index: Index of workflow to select (0-based).
        """
        ...

    def navigate_to_fly(self) -> None:
        """Navigate to FlyScreen."""
        ...

    def navigate_to_refuel(self) -> None:
        """Navigate to RefuelScreen."""
        ...

    def navigate_to_settings(self) -> None:
        """Navigate to SettingsScreen."""
        ...

    def view_workflow_details(self, entry: WorkflowHistoryEntry) -> None:
        """View details of a historical workflow.

        Args:
            entry: The workflow history entry to view.
        """
        ...


# =============================================================================
# FlyScreen Protocol
# =============================================================================


@runtime_checkable
class FlyScreenProtocol(MaverickScreenProtocol, Protocol):
    """Protocol for the Fly workflow screen.

    The Fly screen allows users to configure and start a Fly workflow.
    """

    @property
    def branch_name(self) -> str:
        """Current branch name input value."""
        ...

    @property
    def is_valid(self) -> bool:
        """Whether the current configuration is valid."""
        ...

    @property
    def can_start(self) -> bool:
        """Whether the workflow can be started."""
        ...

    def set_branch_name(self, name: str) -> None:
        """Set the branch name.

        Triggers real-time validation.

        Args:
            name: Branch name to set.
        """
        ...

    def set_task_file(self, path: Path | None) -> None:
        """Set the optional task file path.

        Args:
            path: Path to task file, or None to clear.
        """
        ...

    async def validate_branch(self, name: str) -> None:
        """Validate the branch name.

        Checks for valid characters and whether branch exists.

        Args:
            name: Branch name to validate.
        """
        ...

    async def start_workflow(self) -> None:
        """Start the Fly workflow.

        Validates configuration and transitions to WorkflowScreen.
        """
        ...

    def cancel(self) -> None:
        """Cancel and return to home screen."""
        ...


# =============================================================================
# RefuelScreen Protocol
# =============================================================================


@runtime_checkable
class RefuelScreenProtocol(MaverickScreenProtocol, Protocol):
    """Protocol for the Refuel workflow screen.

    The Refuel screen allows users to select and process GitHub issues.
    """

    @property
    def label_filter(self) -> str:
        """Current label filter input value."""
        ...

    @property
    def selected_count(self) -> int:
        """Count of selected issues."""
        ...

    @property
    def can_start(self) -> bool:
        """Whether the workflow can be started."""
        ...

    def set_label_filter(self, label: str) -> None:
        """Set the label filter.

        Args:
            label: Label to filter issues by.
        """
        ...

    def set_issue_limit(self, limit: int) -> None:
        """Set the maximum issues to process.

        Args:
            limit: Maximum issues (1-10).
        """
        ...

    def set_parallel_mode(self, parallel: bool) -> None:
        """Set processing mode.

        Args:
            parallel: True for parallel, False for sequential.
        """
        ...

    async def fetch_issues(self) -> None:
        """Fetch GitHub issues matching the label filter.

        Populates the issue list for selection.
        """
        ...

    def toggle_issue_selection(self, index: int) -> None:
        """Toggle selection of an issue.

        Args:
            index: Index of issue to toggle.
        """
        ...

    def select_all_issues(self) -> None:
        """Select all visible issues."""
        ...

    def deselect_all_issues(self) -> None:
        """Deselect all issues."""
        ...

    async def start_workflow(self) -> None:
        """Start the Refuel workflow with selected issues.

        Validates selection and begins processing.
        """
        ...

    def cancel(self) -> None:
        """Cancel and return to home screen."""
        ...


# =============================================================================
# ReviewScreen Protocol
# =============================================================================


@runtime_checkable
class ReviewScreenProtocol(MaverickScreenProtocol, Protocol):
    """Protocol for the review screen.

    The review screen displays code review findings and allows actions.
    """

    @property
    def finding_count(self) -> int:
        """Total number of findings."""
        ...

    @property
    def selected_finding_count(self) -> int:
        """Count of selected findings."""
        ...

    @property
    def has_findings(self) -> bool:
        """Whether there are any findings."""
        ...

    def load_findings(self, findings: list[ReviewFinding]) -> None:
        """Load findings into the screen.

        Args:
            findings: List of review findings to display.
        """
        ...

    def select_finding(self, index: int) -> None:
        """Select a finding for viewing.

        Args:
            index: Index of finding to select.
        """
        ...

    def toggle_finding_selection(self, index: int) -> None:
        """Toggle selection of a finding for bulk actions.

        Args:
            index: Index of finding to toggle.
        """
        ...

    def expand_finding(self, index: int) -> None:
        """Expand a finding to show details.

        Args:
            index: Index of finding to expand.
        """
        ...

    async def show_code_context(self, finding: ReviewFinding) -> None:
        """Show code context for a finding.

        Displays the file diff in the side panel.

        Args:
            finding: Finding to show context for.
        """
        ...

    async def approve_review(self) -> None:
        """Approve the review.

        Shows confirmation dialog before approving.
        """
        ...

    async def request_changes(self, comment: str) -> None:
        """Request changes on the review.

        Args:
            comment: Comment explaining requested changes.
        """
        ...

    async def dismiss_finding(self, finding_id: str) -> None:
        """Dismiss a single finding.

        Args:
            finding_id: ID of finding to dismiss.
        """
        ...

    async def dismiss_selected(self) -> None:
        """Dismiss all selected findings."""
        ...

    async def fix_all(self) -> None:
        """Trigger automatic fix for all findings.

        Shows confirmation dialog and displays results.
        """
        ...


# =============================================================================
# SettingsScreen Protocol
# =============================================================================


@runtime_checkable
class SettingsScreenProtocol(MaverickScreenProtocol, Protocol):
    """Protocol for the settings screen.

    The settings screen allows configuration of Maverick options.
    """

    @property
    def has_unsaved_changes(self) -> bool:
        """Whether there are unsaved changes."""
        ...

    @property
    def can_save(self) -> bool:
        """Whether settings can be saved (valid and changed)."""
        ...

    def load_settings(self) -> None:
        """Load current settings from configuration.

        Populates the settings form with current values.
        """
        ...

    def update_setting(self, key: str, value: Any) -> None:
        """Update a setting value.

        Args:
            key: Setting key path (e.g., "github.owner").
            value: New value for the setting.
        """
        ...

    def validate_setting(self, key: str, value: Any) -> str | None:
        """Validate a setting value.

        Args:
            key: Setting key path.
            value: Value to validate.

        Returns:
            Error message if invalid, None if valid.
        """
        ...

    async def test_github_connection(self) -> None:
        """Test the GitHub CLI connection.

        Shows result status in the UI.
        """
        ...

    async def test_notification(self) -> None:
        """Send a test notification.

        Shows confirmation of success/failure.
        """
        ...

    async def save_settings(self) -> None:
        """Save current settings to configuration file.

        Validates all settings before saving.
        """
        ...

    async def discard_changes(self) -> None:
        """Discard unsaved changes.

        Shows confirmation dialog if changes exist.
        """
        ...

    async def navigate_away(self) -> bool:
        """Handle navigation away from settings.

        Shows confirmation dialog if unsaved changes exist.

        Returns:
            True if navigation should proceed, False to stay.
        """
        ...


# =============================================================================
# Modal Dialog Protocols
# =============================================================================


@runtime_checkable
class ConfirmDialogProtocol(Protocol):
    """Protocol for confirmation dialogs.

    Confirmation dialogs present a yes/no question to the user.
    """

    @property
    def title(self) -> str:
        """Dialog title."""
        ...

    @property
    def message(self) -> str:
        """Dialog message."""
        ...

    def confirm(self) -> None:
        """Handle user confirmation (dismiss with True)."""
        ...

    def cancel(self) -> None:
        """Handle user cancellation (dismiss with False)."""
        ...


@runtime_checkable
class ErrorDialogProtocol(Protocol):
    """Protocol for error dialogs.

    Error dialogs display an error message with optional retry.
    """

    @property
    def message(self) -> str:
        """Error message."""
        ...

    @property
    def details(self) -> str | None:
        """Optional error details."""
        ...

    @property
    def has_retry(self) -> bool:
        """Whether retry action is available."""
        ...

    def dismiss(self) -> None:
        """Dismiss the error dialog."""
        ...

    def retry(self) -> None:
        """Retry the failed action (if available)."""
        ...


@runtime_checkable
class InputDialogProtocol(Protocol):
    """Protocol for input dialogs.

    Input dialogs collect text input from the user.
    """

    @property
    def prompt(self) -> str:
        """Input prompt."""
        ...

    @property
    def value(self) -> str:
        """Current input value."""
        ...

    def submit(self, value: str) -> None:
        """Submit the input value (dismiss with value)."""
        ...

    def cancel(self) -> None:
        """Cancel input (dismiss with None)."""
        ...


# =============================================================================
# Workflow Session Protocol
# =============================================================================


@runtime_checkable
class WorkflowSessionProtocol(Protocol):
    """Protocol for active workflow session management.

    Tracks the state of a running workflow for display purposes.
    """

    @property
    def workflow_type(self) -> str:
        """Type of workflow ("fly" or "refuel")."""
        ...

    @property
    def branch_name(self) -> str:
        """Branch name for the workflow."""
        ...

    @property
    def current_stage(self) -> str:
        """Name of the current workflow stage."""
        ...

    @property
    def is_running(self) -> bool:
        """Whether the workflow is currently running."""
        ...

    @property
    def is_complete(self) -> bool:
        """Whether the workflow has completed."""
        ...

    @property
    def is_failed(self) -> bool:
        """Whether the workflow has failed."""
        ...

    @property
    def elapsed_seconds(self) -> float:
        """Elapsed time since workflow started."""
        ...

    def cancel(self) -> None:
        """Request workflow cancellation."""
        ...

    def get_stage_status(self, stage_name: str) -> str:
        """Get status of a specific stage.

        Args:
            stage_name: Name of the stage.

        Returns:
            Status string: "pending", "active", "completed", "failed".
        """
        ...
