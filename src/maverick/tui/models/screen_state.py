from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from maverick.tui.models.enums import (
    IssueSeverity,
    ProcessingMode,
    ReviewAction,
    StageStatus,
)
from maverick.tui.models.findings import FixResult, ReviewIssue
from maverick.tui.models.github import GitHubIssue, IssueSelectionItem
from maverick.tui.models.settings import ConfigOption, SettingsSection, SettingValue
from maverick.tui.models.workflow import (
    BranchValidation,
    RecentWorkflowEntry,
    RefuelResultItem,
    StageState,
)


@dataclass(frozen=True, slots=True)
class ScreenState:
    """Base state shared by all screens."""

    title: str
    can_go_back: bool = True
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class HomeScreenState(ScreenState):
    """State for the home screen."""

    recent_workflows: tuple[RecentWorkflowEntry, ...] = ()
    selected_index: int = 0
    loading: bool = False

    @property
    def selected_workflow(self) -> RecentWorkflowEntry | None:
        """Get the currently selected workflow entry."""
        if 0 <= self.selected_index < len(self.recent_workflows):
            return self.recent_workflows[self.selected_index]
        return None

    @property
    def is_empty(self) -> bool:
        """Check if there are no recent workflows."""
        return len(self.recent_workflows) == 0 and not self.loading


@dataclass(frozen=True, slots=True)
class WorkflowScreenState(ScreenState):
    """State for the workflow progress screen."""

    workflow_name: str = ""
    branch_name: str = ""
    stages: tuple[StageState, ...] = ()
    elapsed_seconds: float = 0.0
    current_stage_index: int = 0

    @property
    def current_stage(self) -> StageState | None:
        """Get the currently active stage."""
        for stage in self.stages:
            if stage.status == StageStatus.ACTIVE:
                return stage
        return None

    @property
    def progress_percent(self) -> float:
        """Calculate overall progress percentage."""
        if not self.stages:
            return 0.0
        completed = sum(1 for s in self.stages if s.status == StageStatus.COMPLETED)
        return (completed / len(self.stages)) * 100


@dataclass(frozen=True, slots=True)
class ReviewScreenState(ScreenState):
    """State for the review results screen."""

    issues: tuple[ReviewIssue, ...] = ()
    selected_issue_index: int = 0
    filter_severity: IssueSeverity | None = None

    @property
    def filtered_issues(self) -> tuple[ReviewIssue, ...]:
        """Get issues filtered by severity."""
        if self.filter_severity is None:
            return self.issues
        return tuple(i for i in self.issues if i.severity == self.filter_severity)

    @property
    def issue_counts(self) -> dict[IssueSeverity, int]:
        """Count issues by severity."""
        counts = dict.fromkeys(IssueSeverity, 0)
        for issue in self.issues:
            counts[issue.severity] += 1
        return counts


@dataclass(frozen=True, slots=True)
class ConfigScreenState(ScreenState):
    """State for the config screen."""

    options: tuple[ConfigOption, ...] = ()
    selected_option_index: int = 0
    editing: bool = False
    edit_value: str = ""

    @property
    def selected_option(self) -> ConfigOption | None:
        """Get the currently selected option."""
        if 0 <= self.selected_option_index < len(self.options):
            return self.options[self.selected_option_index]
        return None


@dataclass(frozen=True, slots=True)
class FlyScreenState:
    """State for the FlyScreen workflow launcher.

    Attributes:
        branch_name: Current branch name input value.
        branch_validation: Validation result for branch name.
        task_file: Optional path to task file.
        is_starting: Whether workflow is being started.
        error_message: Error to display (if any).
    """

    branch_name: str = ""
    branch_validation: BranchValidation = field(default_factory=BranchValidation.empty)
    task_file: Path | None = None
    is_starting: bool = False
    error_message: str | None = None

    @property
    def can_start(self) -> bool:
        """Whether the Start button should be enabled."""
        return self.branch_validation.is_valid and not self.is_starting

    @property
    def start_button_label(self) -> str:
        """Label for the start button."""
        if self.is_starting:
            return "Starting..."
        return "Start"


@dataclass(frozen=True, slots=True)
class RefuelScreenState:
    """State for the RefuelScreen issue processor.

    Attributes:
        label_filter: Current label filter input.
        issue_limit: Maximum issues to process (1-10).
        processing_mode: Parallel or sequential.
        issues: Fetched issues with selection state.
        focused_index: Currently focused issue index.
        is_fetching: Whether issues are being fetched.
        is_processing: Whether workflow is running.
        results: Processing results (after completion).
        error_message: Error to display (if any).
    """

    label_filter: str = ""
    issue_limit: int = 3
    processing_mode: ProcessingMode = ProcessingMode.PARALLEL
    issues: tuple[IssueSelectionItem, ...] = ()
    focused_index: int = 0
    is_fetching: bool = False
    is_processing: bool = False
    results: tuple[RefuelResultItem, ...] | None = None
    error_message: str | None = None

    @property
    def selected_issues(self) -> tuple[GitHubIssue, ...]:
        """Get all selected issues."""
        return tuple(item.issue for item in self.issues if item.selected)

    @property
    def selected_count(self) -> int:
        """Count of selected issues."""
        return sum(1 for item in self.issues if item.selected)

    @property
    def can_start(self) -> bool:
        """Whether the Start button should be enabled."""
        return (
            self.selected_count > 0 and not self.is_processing and not self.is_fetching
        )

    @property
    def is_empty(self) -> bool:
        """Check if no issues are loaded."""
        return len(self.issues) == 0 and not self.is_fetching

    @property
    def has_results(self) -> bool:
        """Check if results are available."""
        return self.results is not None


@dataclass(frozen=True, slots=True)
class ReviewScreenActionState:
    """State for ReviewScreen action handling.

    Extends base ReviewScreenState with action-specific state.

    Attributes:
        pending_action: Action being processed (if any).
        request_changes_comment: Comment for request changes action.
        fix_results: Results of fix all action.
        is_approving: Whether approval is in progress.
        is_fixing: Whether fix all is in progress.
        confirmation_pending: Action awaiting confirmation.
    """

    pending_action: ReviewAction | None = None
    request_changes_comment: str = ""
    fix_results: tuple[FixResult, ...] | None = None
    is_approving: bool = False
    is_fixing: bool = False
    confirmation_pending: ReviewAction | None = None

    @property
    def is_action_in_progress(self) -> bool:
        """Check if any action is in progress."""
        return self.is_approving or self.is_fixing

    @property
    def has_fix_results(self) -> bool:
        """Check if fix results are available."""
        return self.fix_results is not None

    @property
    def fix_success_count(self) -> int:
        """Count of successful fixes."""
        if not self.fix_results:
            return 0
        return sum(1 for r in self.fix_results if r.success)

    @property
    def fix_failure_count(self) -> int:
        """Count of failed fixes."""
        if not self.fix_results:
            return 0
        return sum(1 for r in self.fix_results if not r.success)


@dataclass(frozen=True, slots=True)
class SettingsScreenState:
    """State for the SettingsScreen configuration editor.

    Attributes:
        sections: Configuration sections.
        focused_section_index: Currently focused section.
        focused_setting_index: Currently focused setting within section.
        editing: Whether a setting is being edited.
        edit_value: Current edit value (string representation).
        test_github_status: Result of GitHub connection test.
        test_notification_status: Result of notification test.
        is_testing_github: Whether GitHub test is running.
        is_testing_notification: Whether notification test is running.
        load_error: Error loading configuration (if any).
    """

    sections: tuple[SettingsSection, ...] = ()
    focused_section_index: int = 0
    focused_setting_index: int = 0
    editing: bool = False
    edit_value: str = ""
    test_github_status: str | None = None
    test_notification_status: str | None = None
    is_testing_github: bool = False
    is_testing_notification: bool = False
    load_error: str | None = None

    @property
    def current_section(self) -> SettingsSection | None:
        """Get currently focused section."""
        if 0 <= self.focused_section_index < len(self.sections):
            return self.sections[self.focused_section_index]
        return None

    @property
    def current_setting(self) -> SettingValue | None:
        """Get currently focused setting."""
        section = self.current_section
        if section and 0 <= self.focused_setting_index < len(section.settings):
            return section.settings[self.focused_setting_index]
        return None

    @property
    def has_unsaved_changes(self) -> bool:
        """Check if any settings have been modified."""
        return any(
            setting.is_modified
            for section in self.sections
            for setting in section.settings
        )

    @property
    def has_validation_errors(self) -> bool:
        """Check if any settings have validation errors."""
        return any(
            not setting.is_valid
            for section in self.sections
            for setting in section.settings
        )

    @property
    def can_save(self) -> bool:
        """Whether settings can be saved."""
        return self.has_unsaved_changes and not self.has_validation_errors
