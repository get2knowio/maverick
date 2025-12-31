"""Unit tests for TUI enum models.

Tests the enums used in the TUI:
- StageStatus
- IssueSeverity
- SidebarMode
- MessageType
- FindingSeverity
- ValidationStepStatus
- PRState
- CheckStatus
"""

from __future__ import annotations

import pytest

from maverick.tui.models import (
    CheckStatus,
    FindingSeverity,
    IssueSeverity,
    MessageType,
    PRState,
    SidebarMode,
    StageStatus,
    ValidationStepStatus,
)

# =============================================================================
# StageStatus Enum Tests
# =============================================================================


class TestStageStatus:
    """Tests for StageStatus enum."""

    def test_stage_status_pending_value(self) -> None:
        """Test StageStatus.PENDING has correct value."""
        assert StageStatus.PENDING.value == "pending"

    def test_stage_status_active_value(self) -> None:
        """Test StageStatus.ACTIVE has correct value."""
        assert StageStatus.ACTIVE.value == "active"

    def test_stage_status_completed_value(self) -> None:
        """Test StageStatus.COMPLETED has correct value."""
        assert StageStatus.COMPLETED.value == "completed"

    def test_stage_status_failed_value(self) -> None:
        """Test StageStatus.FAILED has correct value."""
        assert StageStatus.FAILED.value == "failed"

    def test_stage_status_is_string_enum(self) -> None:
        """Test StageStatus inherits from str."""
        assert isinstance(StageStatus.PENDING, str)
        assert isinstance(StageStatus.ACTIVE, str)
        assert isinstance(StageStatus.COMPLETED, str)
        assert isinstance(StageStatus.FAILED, str)

    def test_stage_status_string_comparison(self) -> None:
        """Test StageStatus can be compared to strings."""
        assert StageStatus.PENDING == "pending"
        assert StageStatus.ACTIVE == "active"
        assert StageStatus.COMPLETED == "completed"
        assert StageStatus.FAILED == "failed"

    def test_stage_status_from_string(self) -> None:
        """Test creating StageStatus from string value."""
        assert StageStatus("pending") == StageStatus.PENDING
        assert StageStatus("active") == StageStatus.ACTIVE
        assert StageStatus("completed") == StageStatus.COMPLETED
        assert StageStatus("failed") == StageStatus.FAILED

    def test_stage_status_from_string_case_sensitive(self) -> None:
        """Test StageStatus string conversion is case-sensitive."""
        with pytest.raises(ValueError):
            StageStatus("Pending")  # Capital P

        with pytest.raises(ValueError):
            StageStatus("ACTIVE")  # All caps

    def test_stage_status_invalid_value_raises(self) -> None:
        """Test invalid string raises ValueError."""
        with pytest.raises(ValueError):
            StageStatus("invalid")

        with pytest.raises(ValueError):
            StageStatus("running")

    def test_stage_status_iteration(self) -> None:
        """Test StageStatus is iterable."""
        statuses = list(StageStatus)

        assert len(statuses) == 4
        assert StageStatus.PENDING in statuses
        assert StageStatus.ACTIVE in statuses
        assert StageStatus.COMPLETED in statuses
        assert StageStatus.FAILED in statuses

    def test_stage_status_membership(self) -> None:
        """Test StageStatus membership checks."""
        assert StageStatus.PENDING in StageStatus
        assert StageStatus.COMPLETED in StageStatus

    def test_stage_status_name_attribute(self) -> None:
        """Test StageStatus has name attribute."""
        assert StageStatus.PENDING.name == "PENDING"
        assert StageStatus.ACTIVE.name == "ACTIVE"
        assert StageStatus.COMPLETED.name == "COMPLETED"
        assert StageStatus.FAILED.name == "FAILED"

    def test_stage_status_all_members(self) -> None:
        """Test all StageStatus members are present."""
        expected_statuses = {"pending", "active", "completed", "failed"}
        actual_statuses = {status.value for status in StageStatus}

        assert actual_statuses == expected_statuses

    def test_stage_status_unique_values(self) -> None:
        """Test each StageStatus has unique value."""
        values = [status.value for status in StageStatus]

        assert len(values) == len(set(values))


# =============================================================================
# IssueSeverity Enum Tests
# =============================================================================


class TestIssueSeverity:
    """Tests for IssueSeverity enum."""

    def test_issue_severity_error_value(self) -> None:
        """Test IssueSeverity.ERROR has correct value."""
        assert IssueSeverity.ERROR.value == "error"

    def test_issue_severity_warning_value(self) -> None:
        """Test IssueSeverity.WARNING has correct value."""
        assert IssueSeverity.WARNING.value == "warning"

    def test_issue_severity_info_value(self) -> None:
        """Test IssueSeverity.INFO has correct value."""
        assert IssueSeverity.INFO.value == "info"

    def test_issue_severity_suggestion_value(self) -> None:
        """Test IssueSeverity.SUGGESTION has correct value."""
        assert IssueSeverity.SUGGESTION.value == "suggestion"

    def test_issue_severity_is_string_enum(self) -> None:
        """Test IssueSeverity inherits from str."""
        assert isinstance(IssueSeverity.ERROR, str)
        assert isinstance(IssueSeverity.WARNING, str)
        assert isinstance(IssueSeverity.INFO, str)
        assert isinstance(IssueSeverity.SUGGESTION, str)

    def test_issue_severity_string_comparison(self) -> None:
        """Test IssueSeverity can be compared to strings."""
        assert IssueSeverity.ERROR == "error"
        assert IssueSeverity.WARNING == "warning"
        assert IssueSeverity.INFO == "info"
        assert IssueSeverity.SUGGESTION == "suggestion"

    def test_issue_severity_from_string(self) -> None:
        """Test creating IssueSeverity from string value."""
        assert IssueSeverity("error") == IssueSeverity.ERROR
        assert IssueSeverity("warning") == IssueSeverity.WARNING
        assert IssueSeverity("info") == IssueSeverity.INFO
        assert IssueSeverity("suggestion") == IssueSeverity.SUGGESTION

    def test_issue_severity_from_string_case_sensitive(self) -> None:
        """Test IssueSeverity string conversion is case-sensitive."""
        with pytest.raises(ValueError):
            IssueSeverity("Error")  # Capital E

        with pytest.raises(ValueError):
            IssueSeverity("WARNING")  # All caps

    def test_issue_severity_invalid_value_raises(self) -> None:
        """Test invalid string raises ValueError."""
        with pytest.raises(ValueError):
            IssueSeverity("invalid")

        with pytest.raises(ValueError):
            IssueSeverity("critical")

    def test_issue_severity_iteration(self) -> None:
        """Test IssueSeverity is iterable."""
        severities = list(IssueSeverity)

        assert len(severities) == 4
        assert IssueSeverity.ERROR in severities
        assert IssueSeverity.WARNING in severities
        assert IssueSeverity.INFO in severities
        assert IssueSeverity.SUGGESTION in severities

    def test_issue_severity_membership(self) -> None:
        """Test IssueSeverity membership checks."""
        assert IssueSeverity.ERROR in IssueSeverity
        assert IssueSeverity.INFO in IssueSeverity

    def test_issue_severity_name_attribute(self) -> None:
        """Test IssueSeverity has name attribute."""
        assert IssueSeverity.ERROR.name == "ERROR"
        assert IssueSeverity.WARNING.name == "WARNING"
        assert IssueSeverity.INFO.name == "INFO"
        assert IssueSeverity.SUGGESTION.name == "SUGGESTION"

    def test_issue_severity_all_members(self) -> None:
        """Test all IssueSeverity members are present."""
        expected_severities = {"error", "warning", "info", "suggestion"}
        actual_severities = {severity.value for severity in IssueSeverity}

        assert actual_severities == expected_severities

    def test_issue_severity_unique_values(self) -> None:
        """Test each IssueSeverity has unique value."""
        values = [severity.value for severity in IssueSeverity]

        assert len(values) == len(set(values))


# =============================================================================
# SidebarMode Enum Tests
# =============================================================================


class TestSidebarMode:
    """Tests for SidebarMode enum."""

    def test_sidebar_mode_navigation_value(self) -> None:
        """Test SidebarMode.NAVIGATION has correct value."""
        assert SidebarMode.NAVIGATION.value == "navigation"

    def test_sidebar_mode_workflow_value(self) -> None:
        """Test SidebarMode.WORKFLOW has correct value."""
        assert SidebarMode.WORKFLOW.value == "workflow"

    def test_sidebar_mode_is_string_enum(self) -> None:
        """Test SidebarMode inherits from str."""
        assert isinstance(SidebarMode.NAVIGATION, str)
        assert isinstance(SidebarMode.WORKFLOW, str)

    def test_sidebar_mode_string_comparison(self) -> None:
        """Test SidebarMode can be compared to strings."""
        assert SidebarMode.NAVIGATION == "navigation"
        assert SidebarMode.WORKFLOW == "workflow"

    def test_sidebar_mode_from_string(self) -> None:
        """Test creating SidebarMode from string value."""
        assert SidebarMode("navigation") == SidebarMode.NAVIGATION
        assert SidebarMode("workflow") == SidebarMode.WORKFLOW

    def test_sidebar_mode_from_string_case_sensitive(self) -> None:
        """Test SidebarMode string conversion is case-sensitive."""
        with pytest.raises(ValueError):
            SidebarMode("Navigation")  # Capital N

        with pytest.raises(ValueError):
            SidebarMode("WORKFLOW")  # All caps

    def test_sidebar_mode_invalid_value_raises(self) -> None:
        """Test invalid string raises ValueError."""
        with pytest.raises(ValueError):
            SidebarMode("invalid")

        with pytest.raises(ValueError):
            SidebarMode("menu")

    def test_sidebar_mode_iteration(self) -> None:
        """Test SidebarMode is iterable."""
        modes = list(SidebarMode)

        assert len(modes) == 2
        assert SidebarMode.NAVIGATION in modes
        assert SidebarMode.WORKFLOW in modes

    def test_sidebar_mode_membership(self) -> None:
        """Test SidebarMode membership checks."""
        assert SidebarMode.NAVIGATION in SidebarMode
        assert SidebarMode.WORKFLOW in SidebarMode

    def test_sidebar_mode_name_attribute(self) -> None:
        """Test SidebarMode has name attribute."""
        assert SidebarMode.NAVIGATION.name == "NAVIGATION"
        assert SidebarMode.WORKFLOW.name == "WORKFLOW"

    def test_sidebar_mode_all_members(self) -> None:
        """Test all SidebarMode members are present."""
        expected_modes = {"navigation", "workflow"}
        actual_modes = {mode.value for mode in SidebarMode}

        assert actual_modes == expected_modes

    def test_sidebar_mode_unique_values(self) -> None:
        """Test each SidebarMode has unique value."""
        values = [mode.value for mode in SidebarMode]

        assert len(values) == len(set(values))


# =============================================================================
# MessageType Enum Tests
# =============================================================================


class TestMessageType:
    """Tests for MessageType enum."""

    def test_message_type_text_value(self) -> None:
        """Test MessageType.TEXT has correct value."""
        assert MessageType.TEXT.value == "text"

    def test_message_type_code_value(self) -> None:
        """Test MessageType.CODE has correct value."""
        assert MessageType.CODE.value == "code"

    def test_message_type_tool_call_value(self) -> None:
        """Test MessageType.TOOL_CALL has correct value."""
        assert MessageType.TOOL_CALL.value == "tool_call"

    def test_message_type_tool_result_value(self) -> None:
        """Test MessageType.TOOL_RESULT has correct value."""
        assert MessageType.TOOL_RESULT.value == "tool_result"

    def test_message_type_is_string_enum(self) -> None:
        """Test MessageType inherits from str."""
        assert isinstance(MessageType.TEXT, str)
        assert isinstance(MessageType.CODE, str)
        assert isinstance(MessageType.TOOL_CALL, str)
        assert isinstance(MessageType.TOOL_RESULT, str)

    def test_message_type_string_comparison(self) -> None:
        """Test MessageType can be compared to strings."""
        assert MessageType.TEXT == "text"
        assert MessageType.CODE == "code"
        assert MessageType.TOOL_CALL == "tool_call"
        assert MessageType.TOOL_RESULT == "tool_result"

    def test_message_type_from_string(self) -> None:
        """Test creating MessageType from string value."""
        assert MessageType("text") == MessageType.TEXT
        assert MessageType("code") == MessageType.CODE
        assert MessageType("tool_call") == MessageType.TOOL_CALL
        assert MessageType("tool_result") == MessageType.TOOL_RESULT

    def test_message_type_all_members(self) -> None:
        """Test all MessageType members are present."""
        expected_types = {"text", "code", "tool_call", "tool_result"}
        actual_types = {msg_type.value for msg_type in MessageType}
        assert actual_types == expected_types


# =============================================================================
# FindingSeverity Enum Tests
# =============================================================================


class TestFindingSeverity:
    """Tests for FindingSeverity enum."""

    def test_finding_severity_error_value(self) -> None:
        """Test FindingSeverity.ERROR has correct value."""
        assert FindingSeverity.ERROR.value == "error"

    def test_finding_severity_warning_value(self) -> None:
        """Test FindingSeverity.WARNING has correct value."""
        assert FindingSeverity.WARNING.value == "warning"

    def test_finding_severity_suggestion_value(self) -> None:
        """Test FindingSeverity.SUGGESTION has correct value."""
        assert FindingSeverity.SUGGESTION.value == "suggestion"

    def test_finding_severity_is_string_enum(self) -> None:
        """Test FindingSeverity inherits from str."""
        assert isinstance(FindingSeverity.ERROR, str)
        assert isinstance(FindingSeverity.WARNING, str)
        assert isinstance(FindingSeverity.SUGGESTION, str)

    def test_finding_severity_string_comparison(self) -> None:
        """Test FindingSeverity can be compared to strings."""
        assert FindingSeverity.ERROR == "error"
        assert FindingSeverity.WARNING == "warning"
        assert FindingSeverity.SUGGESTION == "suggestion"

    def test_finding_severity_from_string(self) -> None:
        """Test creating FindingSeverity from string value."""
        assert FindingSeverity("error") == FindingSeverity.ERROR
        assert FindingSeverity("warning") == FindingSeverity.WARNING
        assert FindingSeverity("suggestion") == FindingSeverity.SUGGESTION

    def test_finding_severity_all_members(self) -> None:
        """Test all FindingSeverity members are present."""
        expected_severities = {"error", "warning", "suggestion"}
        actual_severities = {severity.value for severity in FindingSeverity}
        assert actual_severities == expected_severities


# =============================================================================
# ValidationStepStatus Enum Tests
# =============================================================================


class TestValidationStepStatus:
    """Tests for ValidationStepStatus enum."""

    def test_validation_step_status_pending_value(self) -> None:
        """Test ValidationStepStatus.PENDING has correct value."""
        assert ValidationStepStatus.PENDING.value == "pending"

    def test_validation_step_status_running_value(self) -> None:
        """Test ValidationStepStatus.RUNNING has correct value."""
        assert ValidationStepStatus.RUNNING.value == "running"

    def test_validation_step_status_passed_value(self) -> None:
        """Test ValidationStepStatus.PASSED has correct value."""
        assert ValidationStepStatus.PASSED.value == "passed"

    def test_validation_step_status_failed_value(self) -> None:
        """Test ValidationStepStatus.FAILED has correct value."""
        assert ValidationStepStatus.FAILED.value == "failed"

    def test_validation_step_status_is_string_enum(self) -> None:
        """Test ValidationStepStatus inherits from str."""
        assert isinstance(ValidationStepStatus.PENDING, str)
        assert isinstance(ValidationStepStatus.RUNNING, str)
        assert isinstance(ValidationStepStatus.PASSED, str)
        assert isinstance(ValidationStepStatus.FAILED, str)

    def test_validation_step_status_string_comparison(self) -> None:
        """Test ValidationStepStatus can be compared to strings."""
        assert ValidationStepStatus.PENDING == "pending"
        assert ValidationStepStatus.RUNNING == "running"
        assert ValidationStepStatus.PASSED == "passed"
        assert ValidationStepStatus.FAILED == "failed"

    def test_validation_step_status_from_string(self) -> None:
        """Test creating ValidationStepStatus from string value."""
        assert ValidationStepStatus("pending") == ValidationStepStatus.PENDING
        assert ValidationStepStatus("running") == ValidationStepStatus.RUNNING
        assert ValidationStepStatus("passed") == ValidationStepStatus.PASSED
        assert ValidationStepStatus("failed") == ValidationStepStatus.FAILED

    def test_validation_step_status_all_members(self) -> None:
        """Test all ValidationStepStatus members are present."""
        expected_statuses = {"pending", "running", "passed", "failed"}
        actual_statuses = {status.value for status in ValidationStepStatus}
        assert actual_statuses == expected_statuses


# =============================================================================
# PRState Enum Tests
# =============================================================================


class TestPRState:
    """Tests for PRState enum."""

    def test_pr_state_open_value(self) -> None:
        """Test PRState.OPEN has correct value."""
        assert PRState.OPEN.value == "open"

    def test_pr_state_merged_value(self) -> None:
        """Test PRState.MERGED has correct value."""
        assert PRState.MERGED.value == "merged"

    def test_pr_state_closed_value(self) -> None:
        """Test PRState.CLOSED has correct value."""
        assert PRState.CLOSED.value == "closed"

    def test_pr_state_is_string_enum(self) -> None:
        """Test PRState inherits from str."""
        assert isinstance(PRState.OPEN, str)
        assert isinstance(PRState.MERGED, str)
        assert isinstance(PRState.CLOSED, str)

    def test_pr_state_string_comparison(self) -> None:
        """Test PRState can be compared to strings."""
        assert PRState.OPEN == "open"
        assert PRState.MERGED == "merged"
        assert PRState.CLOSED == "closed"

    def test_pr_state_from_string(self) -> None:
        """Test creating PRState from string value."""
        assert PRState("open") == PRState.OPEN
        assert PRState("merged") == PRState.MERGED
        assert PRState("closed") == PRState.CLOSED

    def test_pr_state_all_members(self) -> None:
        """Test all PRState members are present."""
        expected_states = {"open", "merged", "closed"}
        actual_states = {state.value for state in PRState}
        assert actual_states == expected_states


# =============================================================================
# CheckStatus Enum Tests
# =============================================================================


class TestCheckStatus:
    """Tests for CheckStatus enum."""

    def test_check_status_pending_value(self) -> None:
        """Test CheckStatus.PENDING has correct value."""
        assert CheckStatus.PENDING.value == "pending"

    def test_check_status_passing_value(self) -> None:
        """Test CheckStatus.PASSING has correct value."""
        assert CheckStatus.PASSING.value == "passing"

    def test_check_status_failing_value(self) -> None:
        """Test CheckStatus.FAILING has correct value."""
        assert CheckStatus.FAILING.value == "failing"

    def test_check_status_is_string_enum(self) -> None:
        """Test CheckStatus inherits from str."""
        assert isinstance(CheckStatus.PENDING, str)
        assert isinstance(CheckStatus.PASSING, str)
        assert isinstance(CheckStatus.FAILING, str)

    def test_check_status_string_comparison(self) -> None:
        """Test CheckStatus can be compared to strings."""
        assert CheckStatus.PENDING == "pending"
        assert CheckStatus.PASSING == "passing"
        assert CheckStatus.FAILING == "failing"

    def test_check_status_from_string(self) -> None:
        """Test creating CheckStatus from string value."""
        assert CheckStatus("pending") == CheckStatus.PENDING
        assert CheckStatus("passing") == CheckStatus.PASSING
        assert CheckStatus("failing") == CheckStatus.FAILING

    def test_check_status_all_members(self) -> None:
        """Test all CheckStatus members are present."""
        expected_statuses = {"pending", "passing", "failing"}
        actual_statuses = {status.value for status in CheckStatus}
        assert actual_statuses == expected_statuses
