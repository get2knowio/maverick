from enum import Enum


class StageStatus(str, Enum):
    """Status of a workflow stage."""

    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"


class IssueSeverity(str, Enum):
    """Severity level of a review issue."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    SUGGESTION = "suggestion"


class SidebarMode(str, Enum):
    """Display mode for the sidebar."""

    NAVIGATION = "navigation"
    WORKFLOW = "workflow"


class MessageType(str, Enum):
    """Type of agent message content."""

    TEXT = "text"
    CODE = "code"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"


class FindingSeverity(str, Enum):
    """Severity level of a code review finding."""

    ERROR = "error"
    WARNING = "warning"
    SUGGESTION = "suggestion"


class ValidationStepStatus(str, Enum):
    """Status of a validation step."""

    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"


class PRState(str, Enum):
    """State of a pull request."""

    OPEN = "open"
    MERGED = "merged"
    CLOSED = "closed"


class CheckStatus(str, Enum):
    """Status of a CI/CD status check."""

    PENDING = "pending"
    PASSING = "passing"
    FAILING = "failing"


class BranchValidationStatus(str, Enum):
    """Status of branch name validation."""

    EMPTY = "empty"
    INVALID_CHARS = "invalid_chars"
    EXISTS_LOCAL = "exists_local"
    EXISTS_REMOTE = "exists_remote"
    VALID_NEW = "valid_new"
    VALID_EXISTING = "valid_existing"
    CHECKING = "checking"


class ProcessingMode(str, Enum):
    """Issue processing mode."""

    PARALLEL = "parallel"
    SEQUENTIAL = "sequential"


class ReviewAction(str, Enum):
    """Available review actions."""

    APPROVE = "approve"
    REQUEST_CHANGES = "request_changes"
    DISMISS = "dismiss"
    FIX_ALL = "fix_all"


class SettingType(str, Enum):
    """Type of setting value."""

    STRING = "string"
    BOOL = "bool"
    INT = "int"
    CHOICE = "choice"
