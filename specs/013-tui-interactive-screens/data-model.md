# Data Model: TUI Interactive Screens

**Feature**: 013-tui-interactive-screens
**Date**: 2025-12-17

## Entity Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Screen Layer                                   │
├──────────────────┬──────────────────┬──────────────────┬────────────────┤
│   HomeScreen     │   FlyScreen      │  RefuelScreen    │  ReviewScreen  │
│   SettingsScreen │                  │                  │                │
├──────────────────┴──────────────────┴──────────────────┴────────────────┤
│                         Screen State Models                              │
├──────────────────┬──────────────────┬──────────────────┬────────────────┤
│ HomeScreenState  │ FlyScreenState   │ RefuelScreenState│ ReviewScreen-  │
│ SettingsScreen-  │                  │                  │ ActionState    │
│ State            │                  │                  │                │
├──────────────────┴──────────────────┴──────────────────┴────────────────┤
│                         Widget Layer                                     │
├──────────────────┬──────────────────┬───────────────────────────────────┤
│   ConfirmDialog  │   ErrorDialog    │   InputDialog                     │
│   IssueList      │   FormField      │   (existing widgets from 012)     │
├──────────────────┴──────────────────┴───────────────────────────────────┤
│                         Persistence Layer                                │
├─────────────────────────────────────────────────────────────────────────┤
│   WorkflowHistoryEntry   │   WorkflowHistoryStore                       │
└─────────────────────────────────────────────────────────────────────────┘
```

## Screen State Models

### HomeScreenState (extends existing)

Extends the existing `HomeScreenState` from `models.py` with history display capabilities.

```python
from dataclasses import dataclass
from datetime import datetime

@dataclass(frozen=True, slots=True)
class WorkflowHistoryEntry:
    """Persisted record of a completed workflow.

    Stored in ~/.config/maverick/history.json with FIFO eviction at 50 entries.

    Attributes:
        id: Unique identifier (UUID).
        workflow_type: "fly" or "refuel".
        branch_name: Git branch name for the workflow.
        timestamp: When the workflow started (ISO 8601).
        final_status: "completed" or "failed".
        stages_completed: List of stage names that completed successfully.
        finding_counts: Count of findings by severity.
        pr_link: URL to the created PR (if any).
    """
    id: str
    workflow_type: str  # Literal["fly", "refuel"]
    branch_name: str
    timestamp: str  # ISO 8601 format
    final_status: str  # Literal["completed", "failed"]
    stages_completed: tuple[str, ...]
    finding_counts: dict[str, int]  # {"error": int, "warning": int, "suggestion": int}
    pr_link: str | None = None

    @property
    def display_status(self) -> str:
        """Human-readable status with icon."""
        if self.final_status == "completed":
            return "✓ Completed"
        return "✗ Failed"

    @property
    def display_timestamp(self) -> str:
        """Human-readable relative time."""
        dt = datetime.fromisoformat(self.timestamp)
        # Implementation would calculate relative time
        return dt.strftime("%Y-%m-%d %H:%M")


@dataclass(frozen=True, slots=True)
class HomeScreenState:
    """State for the enhanced home screen.

    Attributes:
        recent_workflows: Last 10 workflow runs from history.
        selected_index: Currently highlighted workflow index.
        loading: Whether history is being loaded.
    """
    recent_workflows: tuple[WorkflowHistoryEntry, ...] = ()
    selected_index: int = 0
    loading: bool = False

    @property
    def selected_workflow(self) -> WorkflowHistoryEntry | None:
        """Get the currently selected workflow entry."""
        if 0 <= self.selected_index < len(self.recent_workflows):
            return self.recent_workflows[self.selected_index]
        return None

    @property
    def is_empty(self) -> bool:
        """Check if there are no recent workflows."""
        return len(self.recent_workflows) == 0 and not self.loading
```

### FlyScreenState

```python
from dataclasses import dataclass
from pathlib import Path
from enum import Enum

class BranchValidationStatus(str, Enum):
    """Status of branch name validation."""
    EMPTY = "empty"
    INVALID_CHARS = "invalid_chars"
    EXISTS_LOCAL = "exists_local"
    EXISTS_REMOTE = "exists_remote"
    VALID_NEW = "valid_new"
    VALID_EXISTING = "valid_existing"
    CHECKING = "checking"


@dataclass(frozen=True, slots=True)
class BranchValidation:
    """Result of branch name validation.

    Attributes:
        status: Validation status.
        message: User-facing message.
        is_valid: Whether the branch name can be used.
    """
    status: BranchValidationStatus
    message: str
    is_valid: bool

    @classmethod
    def empty(cls) -> "BranchValidation":
        return cls(
            status=BranchValidationStatus.EMPTY,
            message="Branch name cannot be empty",
            is_valid=False
        )

    @classmethod
    def invalid_chars(cls, chars: str) -> "BranchValidation":
        return cls(
            status=BranchValidationStatus.INVALID_CHARS,
            message=f"Invalid characters: {chars}",
            is_valid=False
        )

    @classmethod
    def valid_new(cls) -> "BranchValidation":
        return cls(
            status=BranchValidationStatus.VALID_NEW,
            message="Valid - new branch",
            is_valid=True
        )

    @classmethod
    def valid_existing(cls) -> "BranchValidation":
        return cls(
            status=BranchValidationStatus.VALID_EXISTING,
            message="Branch exists - will continue existing work",
            is_valid=True
        )


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
    branch_validation: BranchValidation = BranchValidation.empty()
    task_file: Path | None = None
    is_starting: bool = False
    error_message: str | None = None

    @property
    def can_start(self) -> bool:
        """Whether the Start button should be enabled."""
        return (
            self.branch_validation.is_valid
            and not self.is_starting
        )

    @property
    def start_button_label(self) -> str:
        """Label for the start button."""
        if self.is_starting:
            return "Starting..."
        return "Start"
```

### RefuelScreenState

```python
from dataclasses import dataclass
from enum import Enum

class ProcessingMode(str, Enum):
    """Issue processing mode."""
    PARALLEL = "parallel"
    SEQUENTIAL = "sequential"


@dataclass(frozen=True, slots=True)
class GitHubIssue:
    """GitHub issue for selection.

    Attributes:
        number: Issue number.
        title: Issue title.
        labels: Issue labels.
        url: URL to the issue.
        state: Open/closed state.
    """
    number: int
    title: str
    labels: tuple[str, ...]
    url: str
    state: str = "open"

    @property
    def display_labels(self) -> str:
        """Formatted labels for display."""
        return ", ".join(self.labels) if self.labels else "No labels"


@dataclass(frozen=True, slots=True)
class IssueSelectionItem:
    """Issue with selection state.

    Attributes:
        issue: The GitHub issue.
        selected: Whether this issue is selected for processing.
    """
    issue: GitHubIssue
    selected: bool = False


@dataclass(frozen=True, slots=True)
class RefuelResultItem:
    """Result of processing a single issue.

    Attributes:
        issue_number: The issue number.
        success: Whether processing succeeded.
        pr_url: URL to created PR (if successful).
        error_message: Error message (if failed).
    """
    issue_number: int
    success: bool
    pr_url: str | None = None
    error_message: str | None = None


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
            self.selected_count > 0
            and not self.is_processing
            and not self.is_fetching
        )

    @property
    def is_empty(self) -> bool:
        """Check if no issues are loaded."""
        return len(self.issues) == 0 and not self.is_fetching

    @property
    def has_results(self) -> bool:
        """Check if results are available."""
        return self.results is not None
```

### ReviewScreenActionState

Extends the existing ReviewScreen with action capabilities.

```python
from dataclasses import dataclass
from enum import Enum

class ReviewAction(str, Enum):
    """Available review actions."""
    APPROVE = "approve"
    REQUEST_CHANGES = "request_changes"
    DISMISS = "dismiss"
    FIX_ALL = "fix_all"


@dataclass(frozen=True, slots=True)
class FixResult:
    """Result of fixing a single finding.

    Attributes:
        finding_id: ID of the finding.
        success: Whether fix succeeded.
        error_message: Error message (if failed).
    """
    finding_id: str
    success: bool
    error_message: str | None = None


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
```

### SettingsScreenState

```python
from dataclasses import dataclass
from enum import Enum
from typing import Any

class SettingType(str, Enum):
    """Type of setting value."""
    STRING = "string"
    BOOL = "bool"
    INT = "int"
    CHOICE = "choice"


@dataclass(frozen=True, slots=True)
class SettingDefinition:
    """Definition of a configurable setting.

    Attributes:
        key: Configuration key path (e.g., "github.owner").
        display_name: Human-readable name.
        description: Help text.
        setting_type: Type of value.
        choices: Available choices (for CHOICE type).
        min_value: Minimum value (for INT type).
        max_value: Maximum value (for INT type).
    """
    key: str
    display_name: str
    description: str
    setting_type: SettingType
    choices: tuple[str, ...] | None = None
    min_value: int | None = None
    max_value: int | None = None


@dataclass(frozen=True, slots=True)
class SettingValue:
    """Current value of a setting.

    Attributes:
        definition: The setting definition.
        current_value: Current value.
        original_value: Value when screen was opened.
        validation_error: Validation error (if any).
    """
    definition: SettingDefinition
    current_value: Any
    original_value: Any
    validation_error: str | None = None

    @property
    def is_modified(self) -> bool:
        """Check if value has changed."""
        return self.current_value != self.original_value

    @property
    def is_valid(self) -> bool:
        """Check if value is valid."""
        return self.validation_error is None


@dataclass(frozen=True, slots=True)
class SettingsSection:
    """Group of related settings.

    Attributes:
        name: Section name (e.g., "GitHub", "Notifications").
        settings: Settings in this section.
    """
    name: str
    settings: tuple[SettingValue, ...]


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
```

## Modal Dialog Models

### ConfirmDialogConfig

```python
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class ConfirmDialogConfig:
    """Configuration for confirmation dialog.

    Attributes:
        title: Dialog title.
        message: Dialog message.
        confirm_label: Label for confirm button.
        cancel_label: Label for cancel button.
        confirm_variant: Button variant for confirm button.
    """
    title: str
    message: str
    confirm_label: str = "Yes"
    cancel_label: str = "No"
    confirm_variant: str = "primary"  # "primary" | "warning" | "error"


@dataclass(frozen=True, slots=True)
class ErrorDialogConfig:
    """Configuration for error dialog.

    Attributes:
        title: Dialog title.
        message: Error message.
        details: Optional detailed error information.
        dismiss_label: Label for dismiss button.
        retry_action: Optional retry callback name.
    """
    title: str = "Error"
    message: str = ""
    details: str | None = None
    dismiss_label: str = "Dismiss"
    retry_action: str | None = None


@dataclass(frozen=True, slots=True)
class InputDialogConfig:
    """Configuration for input dialog.

    Attributes:
        title: Dialog title.
        prompt: Input prompt.
        placeholder: Input placeholder.
        initial_value: Initial input value.
        submit_label: Label for submit button.
        cancel_label: Label for cancel button.
    """
    title: str
    prompt: str
    placeholder: str = ""
    initial_value: str = ""
    submit_label: str = "Submit"
    cancel_label: str = "Cancel"
```

## Navigation Context

```python
from dataclasses import dataclass, field
from typing import Any

@dataclass(frozen=True, slots=True)
class NavigationEntry:
    """Entry in navigation history.

    Attributes:
        screen_name: Name of the screen class.
        params: Parameters passed to screen constructor.
        timestamp: When screen was pushed.
    """
    screen_name: str
    params: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""  # ISO 8601


@dataclass(frozen=True, slots=True)
class NavigationContext:
    """Tracks screen navigation history.

    Attributes:
        history: Stack of navigation entries.
        current_depth: Current stack depth.
    """
    history: tuple[NavigationEntry, ...] = ()

    @property
    def current_screen(self) -> NavigationEntry | None:
        """Get current screen entry."""
        if self.history:
            return self.history[-1]
        return None

    @property
    def can_go_back(self) -> bool:
        """Check if back navigation is possible."""
        return len(self.history) > 1

    @property
    def current_depth(self) -> int:
        """Get current navigation depth."""
        return len(self.history)
```

## Workflow History Persistence

### WorkflowHistoryStore

```python
from dataclasses import dataclass, asdict
from pathlib import Path
import json

HISTORY_PATH = Path.home() / ".config" / "maverick" / "history.json"
MAX_ENTRIES = 50


@dataclass
class WorkflowHistoryStore:
    """Persistent storage for workflow history.

    Manages the workflow history JSON file with FIFO eviction.

    Attributes:
        path: Path to history file.
        max_entries: Maximum entries to retain.
    """
    path: Path = HISTORY_PATH
    max_entries: int = MAX_ENTRIES

    def load(self) -> list[WorkflowHistoryEntry]:
        """Load history entries from disk.

        Returns:
            List of history entries, empty if file doesn't exist.
        """
        if not self.path.exists():
            return []
        with open(self.path) as f:
            data = json.load(f)
        return [
            WorkflowHistoryEntry(
                id=entry["id"],
                workflow_type=entry["workflow_type"],
                branch_name=entry["branch_name"],
                timestamp=entry["timestamp"],
                final_status=entry["final_status"],
                stages_completed=tuple(entry["stages_completed"]),
                finding_counts=entry["finding_counts"],
                pr_link=entry.get("pr_link"),
            )
            for entry in data
        ]

    def save(self, entries: list[WorkflowHistoryEntry]) -> None:
        """Save history entries to disk.

        Enforces max_entries limit with FIFO eviction.

        Args:
            entries: List of history entries to save.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        trimmed = entries[-self.max_entries:]
        data = [
            {
                "id": e.id,
                "workflow_type": e.workflow_type,
                "branch_name": e.branch_name,
                "timestamp": e.timestamp,
                "final_status": e.final_status,
                "stages_completed": list(e.stages_completed),
                "finding_counts": e.finding_counts,
                "pr_link": e.pr_link,
            }
            for e in trimmed
        ]
        with open(self.path, "w") as f:
            json.dump(data, f, indent=2)

    def add(self, entry: WorkflowHistoryEntry) -> None:
        """Add a new history entry.

        Loads existing entries, appends new one, saves with FIFO eviction.

        Args:
            entry: New history entry to add.
        """
        entries = self.load()
        entries.append(entry)
        self.save(entries)

    def clear(self) -> None:
        """Clear all history entries."""
        if self.path.exists():
            self.path.unlink()

    def get_recent(self, count: int = 10) -> list[WorkflowHistoryEntry]:
        """Get most recent entries.

        Args:
            count: Number of entries to return.

        Returns:
            Most recent entries, newest first.
        """
        entries = self.load()
        return list(reversed(entries[-count:]))
```

## State Transitions

### FlyScreen State Machine

```
[Initial] -> [Branch Input] -> [Validating] -> [Valid/Invalid]
                                    |
                                    v
                              [Starting] -> [WorkflowScreen]
                                    |
                                    v
                              [Error Modal]
```

### RefuelScreen State Machine

```
[Initial] -> [Label Input] -> [Fetching Issues] -> [Issue List]
                                                        |
                                                        v
                                                  [Selecting Issues]
                                                        |
                                                        v
                                                  [Processing] -> [Results Summary]
                                                        |
                                                        v
                                                  [Error Modal]
```

### ReviewScreen Action State Machine

```
[Viewing Findings] -> [Selecting Findings] -> [Action Selected]
                                                     |
                          ┌──────────────────────────┼──────────────────────────┐
                          v                          v                          v
                    [Approving]              [Requesting Changes]         [Fixing All]
                          |                          |                          |
                          v                          v                          v
                    [Approved]               [Changes Requested]         [Fix Results]
```

### SettingsScreen State Machine

```
[Loading] -> [Viewing] -> [Editing] -> [Viewing (modified)]
                              |               |
                              v               v
                        [Validation Error]  [Save] -> [Saved]
                                               |
                                               v
                                          [Error Modal]

[Viewing (modified)] -> [Navigate Away] -> [Confirm Discard] -> [Discard/Stay]
```

## Validation Rules

### Branch Name Validation

| Rule | Pattern | Error Message |
|------|---------|---------------|
| Not empty | `.+` | "Branch name cannot be empty" |
| Valid characters | `^[a-zA-Z0-9._/-]+$` | "Invalid characters: {chars}" |
| No double dots | `^(?!.*\.\.)+$` | "Branch name cannot contain '..'" |
| No trailing dot | `^.*[^.]$` | "Branch name cannot end with '.'" |
| Max length | `{1,255}` | "Branch name too long (max 255)" |

### Settings Validation

| Setting | Validation | Error Message |
|---------|------------|---------------|
| github.owner | Non-empty string | "GitHub owner required" |
| github.repo | Non-empty string | "GitHub repo required" |
| notifications.topic | Non-empty if enabled | "Notification topic required when enabled" |
| parallel.max_agents | 1-10 | "Max agents must be 1-10" |
| parallel.max_tasks | 1-20 | "Max tasks must be 1-20" |
| model.max_tokens | 1-200000 | "Max tokens must be 1-200000" |
| model.temperature | 0.0-1.0 | "Temperature must be 0.0-1.0" |
