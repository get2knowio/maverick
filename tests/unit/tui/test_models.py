"""Unit tests for TUI data models.

Tests the enums, dataclasses, and theme constants used in the TUI:
- StageStatus enum
- IssueSeverity enum
- SidebarMode enum
- ScreenState and screen-specific states
- Widget state models
- Theme models and constants
"""
from __future__ import annotations

from datetime import datetime

import pytest

from maverick.tui.models import (
    DARK_THEME,
    LIGHT_THEME,
    AgentMessage,
    AgentOutputState,
    CheckStatus,
    CodeContext,
    CodeLocation,
    ConfigOption,
    ConfigScreenState,
    FindingSeverity,
    HomeScreenState,
    IssueSeverity,
    LogEntry,
    LogPanelState,
    MessageType,
    NavigationItem,
    PRInfo,
    PRState,
    PRSummaryState,
    RecentWorkflowEntry,
    ReviewFinding,
    ReviewFindingItem,
    ReviewFindingsState,
    ReviewIssue,
    ReviewScreenState,
    ScreenState,
    SidebarMode,
    SidebarState,
    StageState,
    StageStatus,
    StatusCheck,
    ThemeColors,
    ToolCallInfo,
    ValidationStatusState,
    ValidationStep,
    ValidationStepStatus,
    WorkflowProgressState,
    WorkflowScreenState,
    WorkflowStage,
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
# ScreenState Tests
# =============================================================================


class TestScreenState:
    """Tests for ScreenState base class."""

    def test_creation_with_required_fields(self) -> None:
        """Test creating ScreenState with required fields only."""
        state = ScreenState(title="Test Screen")

        assert state.title == "Test Screen"
        assert state.can_go_back is True  # default
        assert state.error_message is None  # default

    def test_creation_with_all_fields(self) -> None:
        """Test creating ScreenState with all fields."""
        state = ScreenState(
            title="Error Screen",
            can_go_back=False,
            error_message="Something went wrong",
        )

        assert state.title == "Error Screen"
        assert state.can_go_back is False
        assert state.error_message == "Something went wrong"

    def test_can_go_back_defaults_to_true(self) -> None:
        """Test can_go_back defaults to True."""
        state = ScreenState(title="Screen")

        assert state.can_go_back is True

    def test_error_message_defaults_to_none(self) -> None:
        """Test error_message defaults to None."""
        state = ScreenState(title="Screen")

        assert state.error_message is None

    def test_screen_state_is_frozen(self) -> None:
        """Test ScreenState is immutable (frozen)."""
        state = ScreenState(title="Screen")

        with pytest.raises(Exception):  # FrozenInstanceError
            state.title = "Modified"  # type: ignore[misc]

    def test_screen_state_has_slots(self) -> None:
        """Test ScreenState uses slots for memory efficiency."""
        state = ScreenState(title="Screen")

        # Frozen dataclasses with slots raise TypeError when setting new attributes
        with pytest.raises((AttributeError, TypeError)):
            state.extra_field = "value"  # type: ignore[attr-defined]


# =============================================================================
# RecentWorkflowEntry Tests
# =============================================================================


class TestRecentWorkflowEntry:
    """Tests for RecentWorkflowEntry dataclass."""

    def test_creation_with_required_fields(self) -> None:
        """Test creating RecentWorkflowEntry with required fields."""
        now = datetime.now()
        entry = RecentWorkflowEntry(
            branch_name="feature/auth",
            workflow_type="fly",
            status="completed",
            started_at=now,
        )

        assert entry.branch_name == "feature/auth"
        assert entry.workflow_type == "fly"
        assert entry.status == "completed"
        assert entry.started_at == now
        assert entry.completed_at is None  # default
        assert entry.pr_url is None  # default

    def test_creation_with_all_fields(self) -> None:
        """Test creating RecentWorkflowEntry with all fields."""
        started = datetime(2025, 1, 1, 10, 0, 0)
        completed = datetime(2025, 1, 1, 10, 30, 0)

        entry = RecentWorkflowEntry(
            branch_name="feature/payments",
            workflow_type="refuel",
            status="completed",
            started_at=started,
            completed_at=completed,
            pr_url="https://github.com/org/repo/pull/123",
        )

        assert entry.branch_name == "feature/payments"
        assert entry.workflow_type == "refuel"
        assert entry.status == "completed"
        assert entry.started_at == started
        assert entry.completed_at == completed
        assert entry.pr_url == "https://github.com/org/repo/pull/123"

    def test_completed_at_defaults_to_none(self) -> None:
        """Test completed_at defaults to None."""
        entry = RecentWorkflowEntry(
            branch_name="feature/test",
            workflow_type="fly",
            status="in_progress",
            started_at=datetime.now(),
        )

        assert entry.completed_at is None

    def test_pr_url_defaults_to_none(self) -> None:
        """Test pr_url defaults to None."""
        entry = RecentWorkflowEntry(
            branch_name="feature/test",
            workflow_type="fly",
            status="in_progress",
            started_at=datetime.now(),
        )

        assert entry.pr_url is None

    def test_recent_workflow_entry_is_frozen(self) -> None:
        """Test RecentWorkflowEntry is immutable (frozen)."""
        entry = RecentWorkflowEntry(
            branch_name="feature/test",
            workflow_type="fly",
            status="completed",
            started_at=datetime.now(),
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            entry.status = "failed"  # type: ignore[misc]

    def test_workflow_types(self) -> None:
        """Test different workflow types."""
        for workflow_type in ["fly", "refuel"]:
            entry = RecentWorkflowEntry(
                branch_name="branch",
                workflow_type=workflow_type,
                status="completed",
                started_at=datetime.now(),
            )
            assert entry.workflow_type == workflow_type

    def test_workflow_statuses(self) -> None:
        """Test different workflow statuses."""
        for status in ["completed", "failed", "in_progress"]:
            entry = RecentWorkflowEntry(
                branch_name="branch",
                workflow_type="fly",
                status=status,
                started_at=datetime.now(),
            )
            assert entry.status == status


# =============================================================================
# HomeScreenState Tests
# =============================================================================


class TestHomeScreenState:
    """Tests for HomeScreenState dataclass."""

    def test_creation_with_required_fields(self) -> None:
        """Test creating HomeScreenState with required fields."""
        state = HomeScreenState(title="Home")

        assert state.title == "Home"
        assert state.recent_workflows == ()  # default
        assert state.selected_index == 0  # default

    def test_creation_with_all_fields(self) -> None:
        """Test creating HomeScreenState with all fields."""
        workflow1 = RecentWorkflowEntry(
            branch_name="feature/test1",
            workflow_type="fly",
            status="completed",
            started_at=datetime.now(),
        )
        workflow2 = RecentWorkflowEntry(
            branch_name="feature/test2",
            workflow_type="refuel",
            status="failed",
            started_at=datetime.now(),
        )

        state = HomeScreenState(
            title="Home",
            recent_workflows=(workflow1, workflow2),
            selected_index=1,
            can_go_back=False,
        )

        assert state.title == "Home"
        assert len(state.recent_workflows) == 2
        assert state.selected_index == 1
        assert state.can_go_back is False

    def test_recent_workflows_defaults_to_empty_tuple(self) -> None:
        """Test recent_workflows defaults to empty tuple."""
        state = HomeScreenState(title="Home")

        assert state.recent_workflows == ()
        assert isinstance(state.recent_workflows, tuple)

    def test_selected_index_defaults_to_zero(self) -> None:
        """Test selected_index defaults to 0."""
        state = HomeScreenState(title="Home")

        assert state.selected_index == 0

    def test_selected_workflow_property_valid_index(self) -> None:
        """Test selected_workflow property with valid index."""
        workflow = RecentWorkflowEntry(
            branch_name="feature/test",
            workflow_type="fly",
            status="completed",
            started_at=datetime.now(),
        )

        state = HomeScreenState(
            title="Home",
            recent_workflows=(workflow,),
            selected_index=0,
        )

        assert state.selected_workflow == workflow

    def test_selected_workflow_property_invalid_index(self) -> None:
        """Test selected_workflow property with invalid index."""
        workflow = RecentWorkflowEntry(
            branch_name="feature/test",
            workflow_type="fly",
            status="completed",
            started_at=datetime.now(),
        )

        state = HomeScreenState(
            title="Home",
            recent_workflows=(workflow,),
            selected_index=5,  # Out of bounds
        )

        assert state.selected_workflow is None

    def test_selected_workflow_property_negative_index(self) -> None:
        """Test selected_workflow property with negative index."""
        workflow = RecentWorkflowEntry(
            branch_name="feature/test",
            workflow_type="fly",
            status="completed",
            started_at=datetime.now(),
        )

        state = HomeScreenState(
            title="Home",
            recent_workflows=(workflow,),
            selected_index=-1,
        )

        assert state.selected_workflow is None

    def test_selected_workflow_property_empty_workflows(self) -> None:
        """Test selected_workflow property with no workflows."""
        state = HomeScreenState(title="Home", selected_index=0)

        assert state.selected_workflow is None

    def test_home_screen_state_is_frozen(self) -> None:
        """Test HomeScreenState is immutable (frozen)."""
        state = HomeScreenState(title="Home")

        with pytest.raises(Exception):  # FrozenInstanceError
            state.selected_index = 1  # type: ignore[misc]


# =============================================================================
# StageState Tests
# =============================================================================


class TestStageState:
    """Tests for StageState dataclass."""

    def test_creation_with_required_fields(self) -> None:
        """Test creating StageState with required fields."""
        state = StageState(
            name="setup",
            display_name="Setup",
        )

        assert state.name == "setup"
        assert state.display_name == "Setup"
        assert state.status == StageStatus.PENDING  # default
        assert state.started_at is None  # default
        assert state.completed_at is None  # default
        assert state.error_message is None  # default

    def test_creation_with_all_fields(self) -> None:
        """Test creating StageState with all fields."""
        started = datetime(2025, 1, 1, 10, 0, 0)
        completed = datetime(2025, 1, 1, 10, 5, 0)

        state = StageState(
            name="validation",
            display_name="Validation",
            status=StageStatus.COMPLETED,
            started_at=started,
            completed_at=completed,
            error_message=None,
        )

        assert state.name == "validation"
        assert state.display_name == "Validation"
        assert state.status == StageStatus.COMPLETED
        assert state.started_at == started
        assert state.completed_at == completed
        assert state.error_message is None

    def test_status_defaults_to_pending(self) -> None:
        """Test status defaults to PENDING."""
        state = StageState(name="test", display_name="Test")

        assert state.status == StageStatus.PENDING

    def test_started_at_defaults_to_none(self) -> None:
        """Test started_at defaults to None."""
        state = StageState(name="test", display_name="Test")

        assert state.started_at is None

    def test_completed_at_defaults_to_none(self) -> None:
        """Test completed_at defaults to None."""
        state = StageState(name="test", display_name="Test")

        assert state.completed_at is None

    def test_error_message_defaults_to_none(self) -> None:
        """Test error_message defaults to None."""
        state = StageState(name="test", display_name="Test")

        assert state.error_message is None

    def test_stage_state_with_error(self) -> None:
        """Test StageState with error message."""
        state = StageState(
            name="build",
            display_name="Build",
            status=StageStatus.FAILED,
            error_message="Build failed: syntax error",
        )

        assert state.status == StageStatus.FAILED
        assert state.error_message == "Build failed: syntax error"

    def test_stage_state_is_frozen(self) -> None:
        """Test StageState is immutable (frozen)."""
        state = StageState(name="test", display_name="Test")

        with pytest.raises(Exception):  # FrozenInstanceError
            state.status = StageStatus.COMPLETED  # type: ignore[misc]


# =============================================================================
# WorkflowScreenState Tests
# =============================================================================


class TestWorkflowScreenState:
    """Tests for WorkflowScreenState dataclass."""

    def test_creation_with_required_fields(self) -> None:
        """Test creating WorkflowScreenState with required fields."""
        state = WorkflowScreenState(title="Workflow")

        assert state.title == "Workflow"
        assert state.workflow_name == ""  # default
        assert state.branch_name == ""  # default
        assert state.stages == ()  # default
        assert state.elapsed_seconds == 0.0  # default
        assert state.current_stage_index == 0  # default

    def test_creation_with_all_fields(self) -> None:
        """Test creating WorkflowScreenState with all fields."""
        stage1 = StageState(
            name="setup",
            display_name="Setup",
            status=StageStatus.COMPLETED,
        )
        stage2 = StageState(
            name="build",
            display_name="Build",
            status=StageStatus.ACTIVE,
        )

        state = WorkflowScreenState(
            title="Fly Workflow",
            workflow_name="fly",
            branch_name="feature/auth",
            stages=(stage1, stage2),
            elapsed_seconds=45.5,
            current_stage_index=1,
        )

        assert state.title == "Fly Workflow"
        assert state.workflow_name == "fly"
        assert state.branch_name == "feature/auth"
        assert len(state.stages) == 2
        assert state.elapsed_seconds == 45.5
        assert state.current_stage_index == 1

    def test_current_stage_property_with_active_stage(self) -> None:
        """Test current_stage property returns active stage."""
        stage1 = StageState(
            name="setup",
            display_name="Setup",
            status=StageStatus.COMPLETED,
        )
        stage2 = StageState(
            name="build",
            display_name="Build",
            status=StageStatus.ACTIVE,
        )
        stage3 = StageState(
            name="test",
            display_name="Test",
            status=StageStatus.PENDING,
        )

        state = WorkflowScreenState(
            title="Workflow",
            stages=(stage1, stage2, stage3),
        )

        assert state.current_stage == stage2
        assert state.current_stage.status == StageStatus.ACTIVE

    def test_current_stage_property_no_active_stage(self) -> None:
        """Test current_stage property when no stage is active."""
        stage1 = StageState(
            name="setup",
            display_name="Setup",
            status=StageStatus.COMPLETED,
        )
        stage2 = StageState(
            name="build",
            display_name="Build",
            status=StageStatus.PENDING,
        )

        state = WorkflowScreenState(
            title="Workflow",
            stages=(stage1, stage2),
        )

        assert state.current_stage is None

    def test_current_stage_property_empty_stages(self) -> None:
        """Test current_stage property with no stages."""
        state = WorkflowScreenState(title="Workflow")

        assert state.current_stage is None

    def test_progress_percent_property_all_completed(self) -> None:
        """Test progress_percent with all stages completed."""
        stages = tuple(
            StageState(
                name=f"stage{i}",
                display_name=f"Stage {i}",
                status=StageStatus.COMPLETED,
            )
            for i in range(5)
        )

        state = WorkflowScreenState(title="Workflow", stages=stages)

        assert state.progress_percent == 100.0

    def test_progress_percent_property_partial_completion(self) -> None:
        """Test progress_percent with partial completion."""
        stages = (
            StageState(
                name="stage1",
                display_name="Stage 1",
                status=StageStatus.COMPLETED,
            ),
            StageState(
                name="stage2",
                display_name="Stage 2",
                status=StageStatus.COMPLETED,
            ),
            StageState(
                name="stage3",
                display_name="Stage 3",
                status=StageStatus.ACTIVE,
            ),
            StageState(
                name="stage4",
                display_name="Stage 4",
                status=StageStatus.PENDING,
            ),
        )

        state = WorkflowScreenState(title="Workflow", stages=stages)

        # 2 out of 4 completed = 50%
        assert state.progress_percent == 50.0

    def test_progress_percent_property_no_completion(self) -> None:
        """Test progress_percent with no stages completed."""
        stages = (
            StageState(
                name="stage1",
                display_name="Stage 1",
                status=StageStatus.PENDING,
            ),
            StageState(
                name="stage2",
                display_name="Stage 2",
                status=StageStatus.PENDING,
            ),
        )

        state = WorkflowScreenState(title="Workflow", stages=stages)

        assert state.progress_percent == 0.0

    def test_progress_percent_property_empty_stages(self) -> None:
        """Test progress_percent with no stages."""
        state = WorkflowScreenState(title="Workflow")

        assert state.progress_percent == 0.0

    def test_workflow_screen_state_is_frozen(self) -> None:
        """Test WorkflowScreenState is immutable (frozen)."""
        state = WorkflowScreenState(title="Workflow")

        with pytest.raises(Exception):  # FrozenInstanceError
            state.workflow_name = "fly"  # type: ignore[misc]


# =============================================================================
# ReviewIssue Tests
# =============================================================================


class TestReviewIssue:
    """Tests for ReviewIssue dataclass."""

    def test_creation_with_all_fields(self) -> None:
        """Test creating ReviewIssue with all fields."""
        issue = ReviewIssue(
            file_path="src/main.py",
            line_number=42,
            severity=IssueSeverity.ERROR,
            message="Undefined variable 'x'",
            source="architecture",
        )

        assert issue.file_path == "src/main.py"
        assert issue.line_number == 42
        assert issue.severity == IssueSeverity.ERROR
        assert issue.message == "Undefined variable 'x'"
        assert issue.source == "architecture"

    def test_creation_with_none_line_number(self) -> None:
        """Test creating ReviewIssue with None line_number."""
        issue = ReviewIssue(
            file_path="src/main.py",
            line_number=None,
            severity=IssueSeverity.WARNING,
            message="File-level warning",
            source="coderabbit",
        )

        assert issue.file_path == "src/main.py"
        assert issue.line_number is None
        assert issue.severity == IssueSeverity.WARNING
        assert issue.message == "File-level warning"
        assert issue.source == "coderabbit"

    def test_different_severities(self) -> None:
        """Test ReviewIssue with different severities."""
        for severity in IssueSeverity:
            issue = ReviewIssue(
                file_path="test.py",
                line_number=1,
                severity=severity,
                message="Test message",
                source="validation",
            )
            assert issue.severity == severity

    def test_different_sources(self) -> None:
        """Test ReviewIssue with different sources."""
        for source in ["architecture", "coderabbit", "validation"]:
            issue = ReviewIssue(
                file_path="test.py",
                line_number=1,
                severity=IssueSeverity.INFO,
                message="Test message",
                source=source,
            )
            assert issue.source == source

    def test_review_issue_is_frozen(self) -> None:
        """Test ReviewIssue is immutable (frozen)."""
        issue = ReviewIssue(
            file_path="test.py",
            line_number=1,
            severity=IssueSeverity.ERROR,
            message="Test",
            source="validation",
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            issue.severity = IssueSeverity.WARNING  # type: ignore[misc]


# =============================================================================
# ReviewScreenState Tests
# =============================================================================


class TestReviewScreenState:
    """Tests for ReviewScreenState dataclass."""

    def test_creation_with_required_fields(self) -> None:
        """Test creating ReviewScreenState with required fields."""
        state = ReviewScreenState(title="Review")

        assert state.title == "Review"
        assert state.issues == ()  # default
        assert state.selected_issue_index == 0  # default
        assert state.filter_severity is None  # default

    def test_creation_with_all_fields(self) -> None:
        """Test creating ReviewScreenState with all fields."""
        issue1 = ReviewIssue(
            file_path="test.py",
            line_number=1,
            severity=IssueSeverity.ERROR,
            message="Error",
            source="validation",
        )
        issue2 = ReviewIssue(
            file_path="test.py",
            line_number=2,
            severity=IssueSeverity.WARNING,
            message="Warning",
            source="validation",
        )

        state = ReviewScreenState(
            title="Review",
            issues=(issue1, issue2),
            selected_issue_index=1,
            filter_severity=IssueSeverity.ERROR,
        )

        assert state.title == "Review"
        assert len(state.issues) == 2
        assert state.selected_issue_index == 1
        assert state.filter_severity == IssueSeverity.ERROR

    def test_filtered_issues_property_no_filter(self) -> None:
        """Test filtered_issues property with no filter."""
        issue1 = ReviewIssue(
            file_path="test.py",
            line_number=1,
            severity=IssueSeverity.ERROR,
            message="Error",
            source="validation",
        )
        issue2 = ReviewIssue(
            file_path="test.py",
            line_number=2,
            severity=IssueSeverity.WARNING,
            message="Warning",
            source="validation",
        )

        state = ReviewScreenState(
            title="Review",
            issues=(issue1, issue2),
            filter_severity=None,
        )

        assert state.filtered_issues == (issue1, issue2)

    def test_filtered_issues_property_with_filter(self) -> None:
        """Test filtered_issues property with severity filter."""
        issue1 = ReviewIssue(
            file_path="test.py",
            line_number=1,
            severity=IssueSeverity.ERROR,
            message="Error",
            source="validation",
        )
        issue2 = ReviewIssue(
            file_path="test.py",
            line_number=2,
            severity=IssueSeverity.WARNING,
            message="Warning",
            source="validation",
        )
        issue3 = ReviewIssue(
            file_path="test.py",
            line_number=3,
            severity=IssueSeverity.ERROR,
            message="Another error",
            source="validation",
        )

        state = ReviewScreenState(
            title="Review",
            issues=(issue1, issue2, issue3),
            filter_severity=IssueSeverity.ERROR,
        )

        filtered = state.filtered_issues
        assert len(filtered) == 2
        assert issue1 in filtered
        assert issue3 in filtered
        assert issue2 not in filtered

    def test_issue_counts_property(self) -> None:
        """Test issue_counts property."""
        issues = (
            ReviewIssue(
                file_path="test.py",
                line_number=1,
                severity=IssueSeverity.ERROR,
                message="Error 1",
                source="validation",
            ),
            ReviewIssue(
                file_path="test.py",
                line_number=2,
                severity=IssueSeverity.ERROR,
                message="Error 2",
                source="validation",
            ),
            ReviewIssue(
                file_path="test.py",
                line_number=3,
                severity=IssueSeverity.WARNING,
                message="Warning",
                source="validation",
            ),
            ReviewIssue(
                file_path="test.py",
                line_number=4,
                severity=IssueSeverity.INFO,
                message="Info",
                source="validation",
            ),
        )

        state = ReviewScreenState(title="Review", issues=issues)

        counts = state.issue_counts
        assert counts[IssueSeverity.ERROR] == 2
        assert counts[IssueSeverity.WARNING] == 1
        assert counts[IssueSeverity.INFO] == 1
        assert counts[IssueSeverity.SUGGESTION] == 0

    def test_issue_counts_property_empty_issues(self) -> None:
        """Test issue_counts property with no issues."""
        state = ReviewScreenState(title="Review")

        counts = state.issue_counts
        assert counts[IssueSeverity.ERROR] == 0
        assert counts[IssueSeverity.WARNING] == 0
        assert counts[IssueSeverity.INFO] == 0
        assert counts[IssueSeverity.SUGGESTION] == 0

    def test_review_screen_state_is_frozen(self) -> None:
        """Test ReviewScreenState is immutable (frozen)."""
        state = ReviewScreenState(title="Review")

        with pytest.raises(Exception):  # FrozenInstanceError
            state.selected_issue_index = 1  # type: ignore[misc]


# =============================================================================
# ConfigOption Tests
# =============================================================================


class TestConfigOption:
    """Tests for ConfigOption dataclass."""

    def test_creation_with_required_fields(self) -> None:
        """Test creating ConfigOption with required fields."""
        option = ConfigOption(
            key="debug_mode",
            display_name="Debug Mode",
            value=True,
            description="Enable debug logging",
            option_type="bool",
        )

        assert option.key == "debug_mode"
        assert option.display_name == "Debug Mode"
        assert option.value is True
        assert option.description == "Enable debug logging"
        assert option.option_type == "bool"
        assert option.choices is None  # default

    def test_creation_with_all_fields(self) -> None:
        """Test creating ConfigOption with all fields."""
        option = ConfigOption(
            key="theme",
            display_name="Theme",
            value="dark",
            description="UI theme",
            option_type="choice",
            choices=("dark", "light"),
        )

        assert option.key == "theme"
        assert option.display_name == "Theme"
        assert option.value == "dark"
        assert option.description == "UI theme"
        assert option.option_type == "choice"
        assert option.choices == ("dark", "light")

    def test_bool_option(self) -> None:
        """Test ConfigOption with bool value."""
        option = ConfigOption(
            key="enabled",
            display_name="Enabled",
            value=False,
            description="Enable feature",
            option_type="bool",
        )

        assert isinstance(option.value, bool)
        assert option.value is False

    def test_string_option(self) -> None:
        """Test ConfigOption with string value."""
        option = ConfigOption(
            key="api_key",
            display_name="API Key",
            value="secret123",
            description="API key",
            option_type="string",
        )

        assert isinstance(option.value, str)
        assert option.value == "secret123"

    def test_int_option(self) -> None:
        """Test ConfigOption with int value."""
        option = ConfigOption(
            key="timeout",
            display_name="Timeout",
            value=30,
            description="Timeout in seconds",
            option_type="int",
        )

        assert isinstance(option.value, int)
        assert option.value == 30

    def test_choice_option(self) -> None:
        """Test ConfigOption with choices."""
        option = ConfigOption(
            key="log_level",
            display_name="Log Level",
            value="info",
            description="Logging level",
            option_type="choice",
            choices=("debug", "info", "warning", "error"),
        )

        assert option.option_type == "choice"
        assert option.choices is not None
        assert len(option.choices) == 4
        assert "info" in option.choices

    def test_config_option_is_frozen(self) -> None:
        """Test ConfigOption is immutable (frozen)."""
        option = ConfigOption(
            key="test",
            display_name="Test",
            value="value",
            description="Test option",
            option_type="string",
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            option.value = "new_value"  # type: ignore[misc]


# =============================================================================
# ConfigScreenState Tests
# =============================================================================


class TestConfigScreenState:
    """Tests for ConfigScreenState dataclass."""

    def test_creation_with_required_fields(self) -> None:
        """Test creating ConfigScreenState with required fields."""
        state = ConfigScreenState(title="Settings")

        assert state.title == "Settings"
        assert state.options == ()  # default
        assert state.selected_option_index == 0  # default
        assert state.editing is False  # default
        assert state.edit_value == ""  # default

    def test_creation_with_all_fields(self) -> None:
        """Test creating ConfigScreenState with all fields."""
        option1 = ConfigOption(
            key="debug",
            display_name="Debug",
            value=True,
            description="Debug mode",
            option_type="bool",
        )
        option2 = ConfigOption(
            key="theme",
            display_name="Theme",
            value="dark",
            description="UI theme",
            option_type="choice",
            choices=("dark", "light"),
        )

        state = ConfigScreenState(
            title="Settings",
            options=(option1, option2),
            selected_option_index=1,
            editing=True,
            edit_value="light",
        )

        assert state.title == "Settings"
        assert len(state.options) == 2
        assert state.selected_option_index == 1
        assert state.editing is True
        assert state.edit_value == "light"

    def test_selected_option_property_valid_index(self) -> None:
        """Test selected_option property with valid index."""
        option = ConfigOption(
            key="test",
            display_name="Test",
            value="value",
            description="Test",
            option_type="string",
        )

        state = ConfigScreenState(
            title="Settings",
            options=(option,),
            selected_option_index=0,
        )

        assert state.selected_option == option

    def test_selected_option_property_invalid_index(self) -> None:
        """Test selected_option property with invalid index."""
        option = ConfigOption(
            key="test",
            display_name="Test",
            value="value",
            description="Test",
            option_type="string",
        )

        state = ConfigScreenState(
            title="Settings",
            options=(option,),
            selected_option_index=5,
        )

        assert state.selected_option is None

    def test_selected_option_property_empty_options(self) -> None:
        """Test selected_option property with no options."""
        state = ConfigScreenState(title="Settings")

        assert state.selected_option is None

    def test_config_screen_state_is_frozen(self) -> None:
        """Test ConfigScreenState is immutable (frozen)."""
        state = ConfigScreenState(title="Settings")

        with pytest.raises(Exception):  # FrozenInstanceError
            state.editing = True  # type: ignore[misc]


# =============================================================================
# LogEntry Tests
# =============================================================================


class TestLogEntry:
    """Tests for LogEntry dataclass."""

    def test_creation_with_all_fields(self) -> None:
        """Test creating LogEntry with all fields."""
        timestamp = datetime(2025, 1, 1, 12, 0, 0)

        entry = LogEntry(
            timestamp=timestamp,
            source="agent",
            level="info",
            message="Task completed successfully",
        )

        assert entry.timestamp == timestamp
        assert entry.source == "agent"
        assert entry.level == "info"
        assert entry.message == "Task completed successfully"

    def test_different_log_levels(self) -> None:
        """Test LogEntry with different levels."""
        for level in ["info", "success", "warning", "error"]:
            entry = LogEntry(
                timestamp=datetime.now(),
                source="test",
                level=level,
                message="Test message",
            )
            assert entry.level == level

    def test_different_sources(self) -> None:
        """Test LogEntry with different sources."""
        for source in ["agent", "workflow", "tool", "system"]:
            entry = LogEntry(
                timestamp=datetime.now(),
                source=source,
                level="info",
                message="Test message",
            )
            assert entry.source == source

    def test_log_entry_is_frozen(self) -> None:
        """Test LogEntry is immutable (frozen)."""
        entry = LogEntry(
            timestamp=datetime.now(),
            source="test",
            level="info",
            message="Test",
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            entry.level = "error"  # type: ignore[misc]


# =============================================================================
# LogPanelState Tests
# =============================================================================


class TestLogPanelState:
    """Tests for LogPanelState dataclass."""

    def test_creation_with_defaults(self) -> None:
        """Test creating LogPanelState with default values."""
        state = LogPanelState()

        assert state.visible is False
        assert state.entries == []
        assert state.max_entries == 1000
        assert state.auto_scroll is True

    def test_creation_with_custom_values(self) -> None:
        """Test creating LogPanelState with custom values."""
        entry = LogEntry(
            timestamp=datetime.now(),
            source="test",
            level="info",
            message="Test",
        )

        state = LogPanelState(
            visible=True,
            entries=[entry],
            max_entries=500,
            auto_scroll=False,
        )

        assert state.visible is True
        assert len(state.entries) == 1
        assert state.max_entries == 500
        assert state.auto_scroll is False

    def test_add_entry_method(self) -> None:
        """Test add_entry method adds entries."""
        state = LogPanelState()

        entry1 = LogEntry(
            timestamp=datetime.now(),
            source="test",
            level="info",
            message="First",
        )
        entry2 = LogEntry(
            timestamp=datetime.now(),
            source="test",
            level="info",
            message="Second",
        )

        state.add_entry(entry1)
        state.add_entry(entry2)

        assert len(state.entries) == 2
        assert state.entries[0] == entry1
        assert state.entries[1] == entry2

    def test_add_entry_respects_max_entries(self) -> None:
        """Test add_entry maintains buffer limit."""
        state = LogPanelState(max_entries=3)

        # Add 5 entries
        for i in range(5):
            entry = LogEntry(
                timestamp=datetime.now(),
                source="test",
                level="info",
                message=f"Message {i}",
            )
            state.add_entry(entry)

        # Should keep only last 3
        assert len(state.entries) == 3
        assert state.entries[0].message == "Message 2"
        assert state.entries[1].message == "Message 3"
        assert state.entries[2].message == "Message 4"

    def test_log_panel_state_is_mutable(self) -> None:
        """Test LogPanelState is mutable (not frozen)."""
        state = LogPanelState()

        # Should allow modification
        state.visible = True
        assert state.visible is True

        state.auto_scroll = False
        assert state.auto_scroll is False

    def test_log_panel_state_has_slots(self) -> None:
        """Test LogPanelState uses slots for memory efficiency."""
        state = LogPanelState()

        # Mutable dataclasses with slots raise AttributeError when setting new attributes
        with pytest.raises((AttributeError, TypeError)):
            state.extra_field = "value"  # type: ignore[attr-defined]


# =============================================================================
# NavigationItem Tests
# =============================================================================


class TestNavigationItem:
    """Tests for NavigationItem dataclass."""

    def test_creation_with_required_fields(self) -> None:
        """Test creating NavigationItem with required fields."""
        item = NavigationItem(
            id="home",
            label="Home",
            icon="H",
        )

        assert item.id == "home"
        assert item.label == "Home"
        assert item.icon == "H"
        assert item.shortcut is None  # default

    def test_creation_with_all_fields(self) -> None:
        """Test creating NavigationItem with all fields."""
        item = NavigationItem(
            id="settings",
            label="Settings",
            icon="S",
            shortcut="Ctrl+,",
        )

        assert item.id == "settings"
        assert item.label == "Settings"
        assert item.icon == "S"
        assert item.shortcut == "Ctrl+,"

    def test_shortcut_defaults_to_none(self) -> None:
        """Test shortcut defaults to None."""
        item = NavigationItem(id="test", label="Test", icon="T")

        assert item.shortcut is None

    def test_navigation_item_is_frozen(self) -> None:
        """Test NavigationItem is immutable (frozen)."""
        item = NavigationItem(id="test", label="Test", icon="T")

        with pytest.raises(Exception):  # FrozenInstanceError
            item.label = "Modified"  # type: ignore[misc]


# =============================================================================
# SidebarState Tests
# =============================================================================


class TestSidebarState:
    """Tests for SidebarState dataclass."""

    def test_creation_with_defaults(self) -> None:
        """Test creating SidebarState with default values."""
        state = SidebarState()

        assert state.mode == SidebarMode.NAVIGATION
        assert len(state.navigation_items) == 3
        assert state.workflow_stages == ()
        assert state.selected_nav_index == 0

    def test_default_navigation_items(self) -> None:
        """Test default navigation items are set correctly."""
        state = SidebarState()

        assert len(state.navigation_items) == 3

        home = state.navigation_items[0]
        assert home.id == "home"
        assert home.label == "Home"
        assert home.icon == "H"
        assert home.shortcut == "Ctrl+H"

        workflows = state.navigation_items[1]
        assert workflows.id == "workflows"
        assert workflows.label == "Workflows"
        assert workflows.icon == "W"
        assert workflows.shortcut is None

        settings = state.navigation_items[2]
        assert settings.id == "settings"
        assert settings.label == "Settings"
        assert settings.icon == "S"
        assert settings.shortcut == "Ctrl+,"

    def test_creation_with_custom_values(self) -> None:
        """Test creating SidebarState with custom values."""
        custom_nav = (
            NavigationItem(id="dashboard", label="Dashboard", icon="D"),
            NavigationItem(id="logs", label="Logs", icon="L"),
        )

        stage = StageState(name="build", display_name="Build")

        state = SidebarState(
            mode=SidebarMode.WORKFLOW,
            navigation_items=custom_nav,
            workflow_stages=(stage,),
            selected_nav_index=1,
        )

        assert state.mode == SidebarMode.WORKFLOW
        assert len(state.navigation_items) == 2
        assert len(state.workflow_stages) == 1
        assert state.selected_nav_index == 1

    def test_workflow_mode(self) -> None:
        """Test SidebarState in workflow mode."""
        stages = (
            StageState(name="setup", display_name="Setup"),
            StageState(name="build", display_name="Build"),
            StageState(name="test", display_name="Test"),
        )

        state = SidebarState(
            mode=SidebarMode.WORKFLOW,
            workflow_stages=stages,
        )

        assert state.mode == SidebarMode.WORKFLOW
        assert len(state.workflow_stages) == 3

    def test_sidebar_state_is_frozen(self) -> None:
        """Test SidebarState is immutable (frozen)."""
        state = SidebarState()

        with pytest.raises(Exception):  # FrozenInstanceError
            state.mode = SidebarMode.WORKFLOW  # type: ignore[misc]


# =============================================================================
# ThemeColors Tests
# =============================================================================


class TestThemeColors:
    """Tests for ThemeColors dataclass."""

    def test_creation_with_defaults(self) -> None:
        """Test creating ThemeColors with default values."""
        theme = ThemeColors()

        # Backgrounds
        assert theme.background == "#1a1a1a"
        assert theme.surface == "#242424"
        assert theme.surface_elevated == "#2d2d2d"

        # Borders
        assert theme.border == "#3a3a3a"
        assert theme.border_focus == "#00aaff"

        # Text
        assert theme.text == "#e0e0e0"
        assert theme.text_muted == "#808080"
        assert theme.text_dim == "#606060"

        # Status
        assert theme.success == "#4caf50"
        assert theme.warning == "#ff9800"
        assert theme.error == "#f44336"
        assert theme.info == "#2196f3"

        # Accent
        assert theme.accent == "#00aaff"
        assert theme.accent_muted == "#0077aa"

    def test_creation_with_custom_colors(self) -> None:
        """Test creating ThemeColors with custom colors."""
        theme = ThemeColors(
            background="#ffffff",
            text="#000000",
            success="#00ff00",
        )

        assert theme.background == "#ffffff"
        assert theme.text == "#000000"
        assert theme.success == "#00ff00"

        # Other fields should still have defaults
        assert theme.surface == "#242424"
        assert theme.border == "#3a3a3a"

    def test_theme_colors_is_frozen(self) -> None:
        """Test ThemeColors is immutable (frozen)."""
        theme = ThemeColors()

        with pytest.raises(Exception):  # FrozenInstanceError
            theme.background = "#ffffff"  # type: ignore[misc]

    def test_theme_colors_has_slots(self) -> None:
        """Test ThemeColors uses slots for memory efficiency."""
        theme = ThemeColors()

        # Frozen dataclasses with slots raise TypeError when setting new attributes
        with pytest.raises((AttributeError, TypeError)):
            theme.extra_color = "#123456"  # type: ignore[attr-defined]


# =============================================================================
# Theme Constants Tests
# =============================================================================


class TestThemeConstants:
    """Tests for DARK_THEME and LIGHT_THEME constants."""

    def test_dark_theme_constant(self) -> None:
        """Test DARK_THEME constant has correct values."""
        assert DARK_THEME.background == "#1a1a1a"
        assert DARK_THEME.surface == "#242424"
        assert DARK_THEME.text == "#e0e0e0"
        assert DARK_THEME.success == "#4caf50"

    def test_light_theme_constant(self) -> None:
        """Test LIGHT_THEME constant has correct values."""
        assert LIGHT_THEME.background == "#f5f5f5"
        assert LIGHT_THEME.surface == "#ffffff"
        assert LIGHT_THEME.surface_elevated == "#fafafa"
        assert LIGHT_THEME.border == "#e0e0e0"
        assert LIGHT_THEME.border_focus == "#0066cc"
        assert LIGHT_THEME.text == "#1a1a1a"
        assert LIGHT_THEME.text_muted == "#606060"
        assert LIGHT_THEME.text_dim == "#909090"
        assert LIGHT_THEME.success == "#388e3c"
        assert LIGHT_THEME.warning == "#f57c00"
        assert LIGHT_THEME.error == "#d32f2f"
        assert LIGHT_THEME.info == "#1976d2"
        assert LIGHT_THEME.accent == "#0066cc"
        assert LIGHT_THEME.accent_muted == "#004499"

    def test_dark_theme_is_theme_colors_instance(self) -> None:
        """Test DARK_THEME is a ThemeColors instance."""
        assert isinstance(DARK_THEME, ThemeColors)

    def test_light_theme_is_theme_colors_instance(self) -> None:
        """Test LIGHT_THEME is a ThemeColors instance."""
        assert isinstance(LIGHT_THEME, ThemeColors)

    def test_themes_are_different(self) -> None:
        """Test DARK_THEME and LIGHT_THEME have different values."""
        assert DARK_THEME.background != LIGHT_THEME.background
        assert DARK_THEME.text != LIGHT_THEME.text
        assert DARK_THEME.accent != LIGHT_THEME.accent

    def test_themes_are_frozen(self) -> None:
        """Test theme constants are immutable."""
        with pytest.raises(Exception):  # FrozenInstanceError
            DARK_THEME.background = "#000000"  # type: ignore[misc]

        with pytest.raises(Exception):  # FrozenInstanceError
            LIGHT_THEME.background = "#ffffff"  # type: ignore[misc]


# =============================================================================
# New Enum Tests (012-workflow-widgets)
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


# =============================================================================
# Helper Dataclass Tests (012-workflow-widgets)
# =============================================================================


class TestToolCallInfo:
    """Tests for ToolCallInfo dataclass."""

    def test_creation_with_required_fields(self) -> None:
        """Test creating ToolCallInfo with required fields."""
        tool_call = ToolCallInfo(
            tool_name="read_file",
            arguments="file_path=/path/to/file",
        )

        assert tool_call.tool_name == "read_file"
        assert tool_call.arguments == "file_path=/path/to/file"
        assert tool_call.result is None  # default

    def test_creation_with_all_fields(self) -> None:
        """Test creating ToolCallInfo with all fields."""
        tool_call = ToolCallInfo(
            tool_name="write_file",
            arguments="file_path=/path/to/file, content=...",
            result="File written successfully",
        )

        assert tool_call.tool_name == "write_file"
        assert tool_call.arguments == "file_path=/path/to/file, content=..."
        assert tool_call.result == "File written successfully"

    def test_result_defaults_to_none(self) -> None:
        """Test result defaults to None."""
        tool_call = ToolCallInfo(tool_name="test", arguments="arg=value")
        assert tool_call.result is None

    def test_tool_call_info_is_frozen(self) -> None:
        """Test ToolCallInfo is immutable (frozen)."""
        tool_call = ToolCallInfo(tool_name="test", arguments="args")

        with pytest.raises(Exception):  # FrozenInstanceError
            tool_call.result = "modified"  # type: ignore[misc]


class TestStatusCheck:
    """Tests for StatusCheck dataclass."""

    def test_creation_with_required_fields(self) -> None:
        """Test creating StatusCheck with required fields."""
        check = StatusCheck(name="CI / build", status=CheckStatus.PASSING)

        assert check.name == "CI / build"
        assert check.status == CheckStatus.PASSING
        assert check.url is None  # default

    def test_creation_with_all_fields(self) -> None:
        """Test creating StatusCheck with all fields."""
        check = StatusCheck(
            name="CI / test",
            status=CheckStatus.FAILING,
            url="https://github.com/org/repo/runs/123",
        )

        assert check.name == "CI / test"
        assert check.status == CheckStatus.FAILING
        assert check.url == "https://github.com/org/repo/runs/123"

    def test_url_defaults_to_none(self) -> None:
        """Test url defaults to None."""
        check = StatusCheck(name="lint", status=CheckStatus.PASSING)
        assert check.url is None

    def test_different_statuses(self) -> None:
        """Test StatusCheck with different statuses."""
        for status in CheckStatus:
            check = StatusCheck(name="test", status=status)
            assert check.status == status

    def test_status_check_is_frozen(self) -> None:
        """Test StatusCheck is immutable (frozen)."""
        check = StatusCheck(name="test", status=CheckStatus.PENDING)

        with pytest.raises(Exception):  # FrozenInstanceError
            check.status = CheckStatus.PASSING  # type: ignore[misc]


class TestCodeLocation:
    """Tests for CodeLocation dataclass."""

    def test_creation_with_required_fields(self) -> None:
        """Test creating CodeLocation with required fields."""
        location = CodeLocation(file_path="src/main.py", line_number=42)

        assert location.file_path == "src/main.py"
        assert location.line_number == 42
        assert location.end_line is None  # default

    def test_creation_with_all_fields(self) -> None:
        """Test creating CodeLocation with all fields."""
        location = CodeLocation(
            file_path="src/utils.py", line_number=10, end_line=20
        )

        assert location.file_path == "src/utils.py"
        assert location.line_number == 10
        assert location.end_line == 20

    def test_end_line_defaults_to_none(self) -> None:
        """Test end_line defaults to None."""
        location = CodeLocation(file_path="test.py", line_number=1)
        assert location.end_line is None

    def test_single_line_location(self) -> None:
        """Test single-line location (no end_line)."""
        location = CodeLocation(file_path="src/app.py", line_number=100)
        assert location.line_number == 100
        assert location.end_line is None

    def test_multi_line_location(self) -> None:
        """Test multi-line location with end_line."""
        location = CodeLocation(
            file_path="src/app.py", line_number=100, end_line=110
        )
        assert location.line_number == 100
        assert location.end_line == 110

    def test_code_location_is_frozen(self) -> None:
        """Test CodeLocation is immutable (frozen)."""
        location = CodeLocation(file_path="test.py", line_number=1)

        with pytest.raises(Exception):  # FrozenInstanceError
            location.line_number = 2  # type: ignore[misc]


class TestCodeContext:
    """Tests for CodeContext dataclass."""

    def test_creation_with_all_fields(self) -> None:
        """Test creating CodeContext with all fields."""
        code = "def foo():\n    pass\n    return 42"
        context = CodeContext(
            file_path="src/main.py",
            start_line=10,
            end_line=12,
            content=code,
            highlight_line=11,
        )

        assert context.file_path == "src/main.py"
        assert context.start_line == 10
        assert context.end_line == 12
        assert context.content == code
        assert context.highlight_line == 11

    def test_multiline_content(self) -> None:
        """Test CodeContext with multi-line content."""
        code = "line1\nline2\nline3"
        context = CodeContext(
            file_path="test.py",
            start_line=1,
            end_line=3,
            content=code,
            highlight_line=2,
        )

        assert context.content == code
        assert context.start_line == 1
        assert context.end_line == 3

    def test_code_context_is_frozen(self) -> None:
        """Test CodeContext is immutable (frozen)."""
        context = CodeContext(
            file_path="test.py",
            start_line=1,
            end_line=1,
            content="code",
            highlight_line=1,
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            context.highlight_line = 2  # type: ignore[misc]


class TestReviewFinding:
    """Tests for ReviewFinding dataclass."""

    def test_creation_with_required_fields(self) -> None:
        """Test creating ReviewFinding with required fields."""
        location = CodeLocation(file_path="src/main.py", line_number=42)
        finding = ReviewFinding(
            id="finding-001",
            severity=FindingSeverity.ERROR,
            location=location,
            title="Undefined variable",
            description="Variable 'x' is used before being defined",
        )

        assert finding.id == "finding-001"
        assert finding.severity == FindingSeverity.ERROR
        assert finding.location == location
        assert finding.title == "Undefined variable"
        assert finding.description == "Variable 'x' is used before being defined"
        assert finding.suggested_fix is None  # default
        assert finding.source == "review"  # default

    def test_creation_with_all_fields(self) -> None:
        """Test creating ReviewFinding with all fields."""
        location = CodeLocation(file_path="src/app.py", line_number=10)
        finding = ReviewFinding(
            id="finding-002",
            severity=FindingSeverity.WARNING,
            location=location,
            title="Unused variable",
            description="Variable 'temp' is assigned but never used",
            suggested_fix="Remove unused variable 'temp'",
            source="coderabbit",
        )

        assert finding.id == "finding-002"
        assert finding.severity == FindingSeverity.WARNING
        assert finding.location == location
        assert finding.title == "Unused variable"
        assert finding.suggested_fix == "Remove unused variable 'temp'"
        assert finding.source == "coderabbit"

    def test_suggested_fix_defaults_to_none(self) -> None:
        """Test suggested_fix defaults to None."""
        location = CodeLocation(file_path="test.py", line_number=1)
        finding = ReviewFinding(
            id="test",
            severity=FindingSeverity.SUGGESTION,
            location=location,
            title="Title",
            description="Description",
        )
        assert finding.suggested_fix is None

    def test_source_defaults_to_review(self) -> None:
        """Test source defaults to 'review'."""
        location = CodeLocation(file_path="test.py", line_number=1)
        finding = ReviewFinding(
            id="test",
            severity=FindingSeverity.ERROR,
            location=location,
            title="Title",
            description="Description",
        )
        assert finding.source == "review"

    def test_different_severities(self) -> None:
        """Test ReviewFinding with different severities."""
        location = CodeLocation(file_path="test.py", line_number=1)
        for severity in FindingSeverity:
            finding = ReviewFinding(
                id=f"test-{severity.value}",
                severity=severity,
                location=location,
                title="Test",
                description="Test finding",
            )
            assert finding.severity == severity

    def test_review_finding_is_frozen(self) -> None:
        """Test ReviewFinding is immutable (frozen)."""
        location = CodeLocation(file_path="test.py", line_number=1)
        finding = ReviewFinding(
            id="test",
            severity=FindingSeverity.ERROR,
            location=location,
            title="Title",
            description="Description",
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            finding.title = "Modified"  # type: ignore[misc]


class TestReviewFindingItem:
    """Tests for ReviewFindingItem dataclass."""

    def test_creation_with_required_fields(self) -> None:
        """Test creating ReviewFindingItem with required fields."""
        location = CodeLocation(file_path="src/main.py", line_number=42)
        finding = ReviewFinding(
            id="finding-001",
            severity=FindingSeverity.ERROR,
            location=location,
            title="Test",
            description="Test finding",
        )
        item = ReviewFindingItem(finding=finding)

        assert item.finding == finding
        assert item.selected is False  # default

    def test_creation_with_all_fields(self) -> None:
        """Test creating ReviewFindingItem with all fields."""
        location = CodeLocation(file_path="src/main.py", line_number=42)
        finding = ReviewFinding(
            id="finding-001",
            severity=FindingSeverity.ERROR,
            location=location,
            title="Test",
            description="Test finding",
        )
        item = ReviewFindingItem(finding=finding, selected=True)

        assert item.finding == finding
        assert item.selected is True

    def test_selected_defaults_to_false(self) -> None:
        """Test selected defaults to False."""
        location = CodeLocation(file_path="test.py", line_number=1)
        finding = ReviewFinding(
            id="test",
            severity=FindingSeverity.ERROR,
            location=location,
            title="Test",
            description="Test",
        )
        item = ReviewFindingItem(finding=finding)
        assert item.selected is False

    def test_review_finding_item_is_frozen(self) -> None:
        """Test ReviewFindingItem is immutable (frozen)."""
        location = CodeLocation(file_path="test.py", line_number=1)
        finding = ReviewFinding(
            id="test",
            severity=FindingSeverity.ERROR,
            location=location,
            title="Test",
            description="Test",
        )
        item = ReviewFindingItem(finding=finding)

        with pytest.raises(Exception):  # FrozenInstanceError
            item.selected = True  # type: ignore[misc]


class TestPRInfo:
    """Tests for PRInfo dataclass."""

    def test_creation_with_required_fields(self) -> None:
        """Test creating PRInfo with required fields."""
        pr = PRInfo(
            number=123,
            title="Add new feature",
            description="This PR adds a new feature to the app",
            state=PRState.OPEN,
            url="https://github.com/org/repo/pull/123",
        )

        assert pr.number == 123
        assert pr.title == "Add new feature"
        assert pr.description == "This PR adds a new feature to the app"
        assert pr.state == PRState.OPEN
        assert pr.url == "https://github.com/org/repo/pull/123"
        assert pr.checks == ()  # default
        assert pr.branch == ""  # default
        assert pr.base_branch == "main"  # default

    def test_creation_with_all_fields(self) -> None:
        """Test creating PRInfo with all fields."""
        check1 = StatusCheck(name="CI / build", status=CheckStatus.PASSING)
        check2 = StatusCheck(name="CI / test", status=CheckStatus.FAILING)

        pr = PRInfo(
            number=456,
            title="Fix bug",
            description="Fixes issue #123",
            state=PRState.MERGED,
            url="https://github.com/org/repo/pull/456",
            checks=(check1, check2),
            branch="feature/bug-fix",
            base_branch="develop",
        )

        assert pr.number == 456
        assert pr.title == "Fix bug"
        assert pr.description == "Fixes issue #123"
        assert pr.state == PRState.MERGED
        assert len(pr.checks) == 2
        assert pr.branch == "feature/bug-fix"
        assert pr.base_branch == "develop"

    def test_checks_defaults_to_empty_tuple(self) -> None:
        """Test checks defaults to empty tuple."""
        pr = PRInfo(
            number=1,
            title="Test",
            description="Test PR",
            state=PRState.OPEN,
            url="https://github.com/org/repo/pull/1",
        )
        assert pr.checks == ()

    def test_branch_defaults_to_empty_string(self) -> None:
        """Test branch defaults to empty string."""
        pr = PRInfo(
            number=1,
            title="Test",
            description="Test PR",
            state=PRState.OPEN,
            url="https://github.com/org/repo/pull/1",
        )
        assert pr.branch == ""

    def test_base_branch_defaults_to_main(self) -> None:
        """Test base_branch defaults to 'main'."""
        pr = PRInfo(
            number=1,
            title="Test",
            description="Test PR",
            state=PRState.OPEN,
            url="https://github.com/org/repo/pull/1",
        )
        assert pr.base_branch == "main"

    def test_description_preview_property_short_description(self) -> None:
        """Test description_preview with short description."""
        pr = PRInfo(
            number=1,
            title="Test",
            description="This is a short description",
            state=PRState.OPEN,
            url="https://github.com/org/repo/pull/1",
        )
        assert pr.description_preview == "This is a short description"

    def test_description_preview_property_long_description(self) -> None:
        """Test description_preview with long description."""
        long_desc = "This is a very long description " * 20  # > 200 chars
        pr = PRInfo(
            number=1,
            title="Test",
            description=long_desc,
            state=PRState.OPEN,
            url="https://github.com/org/repo/pull/1",
        )

        preview = pr.description_preview
        assert len(preview) <= 204  # 200 + "..."
        assert preview.endswith("...")
        assert preview in long_desc or long_desc.startswith(preview[:-3])

    def test_description_preview_property_exactly_200_chars(self) -> None:
        """Test description_preview with exactly 200 characters."""
        desc = "x" * 200
        pr = PRInfo(
            number=1,
            title="Test",
            description=desc,
            state=PRState.OPEN,
            url="https://github.com/org/repo/pull/1",
        )
        assert pr.description_preview == desc

    def test_different_states(self) -> None:
        """Test PRInfo with different states."""
        for state in PRState:
            pr = PRInfo(
                number=1,
                title="Test",
                description="Test",
                state=state,
                url="https://github.com/org/repo/pull/1",
            )
            assert pr.state == state

    def test_pr_info_is_frozen(self) -> None:
        """Test PRInfo is immutable (frozen)."""
        pr = PRInfo(
            number=1,
            title="Test",
            description="Test",
            state=PRState.OPEN,
            url="https://github.com/org/repo/pull/1",
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            pr.state = PRState.MERGED  # type: ignore[misc]


class TestWorkflowStage:
    """Tests for WorkflowStage dataclass."""

    def test_creation_with_required_fields(self) -> None:
        """Test creating WorkflowStage with required fields."""
        stage = WorkflowStage(
            name="setup", display_name="Setup", status=StageStatus.PENDING
        )

        assert stage.name == "setup"
        assert stage.display_name == "Setup"
        assert stage.status == StageStatus.PENDING
        assert stage.started_at is None  # default
        assert stage.completed_at is None  # default
        assert stage.detail_content is None  # default
        assert stage.error_message is None  # default

    def test_creation_with_all_fields(self) -> None:
        """Test creating WorkflowStage with all fields."""
        started = datetime(2025, 1, 1, 10, 0, 0)
        completed = datetime(2025, 1, 1, 10, 5, 30)

        stage = WorkflowStage(
            name="implementation",
            display_name="Implementation",
            status=StageStatus.COMPLETED,
            started_at=started,
            completed_at=completed,
            detail_content="Implementation details...",
            error_message=None,
        )

        assert stage.name == "implementation"
        assert stage.display_name == "Implementation"
        assert stage.status == StageStatus.COMPLETED
        assert stage.started_at == started
        assert stage.completed_at == completed
        assert stage.detail_content == "Implementation details..."
        assert stage.error_message is None

    def test_duration_seconds_property_with_times(self) -> None:
        """Test duration_seconds property with start and end times."""
        started = datetime(2025, 1, 1, 10, 0, 0)
        completed = datetime(2025, 1, 1, 10, 5, 30)

        stage = WorkflowStage(
            name="test",
            display_name="Test",
            status=StageStatus.COMPLETED,
            started_at=started,
            completed_at=completed,
        )

        assert stage.duration_seconds == 330.0  # 5 minutes 30 seconds

    def test_duration_seconds_property_no_start(self) -> None:
        """Test duration_seconds property when not started."""
        stage = WorkflowStage(
            name="test", display_name="Test", status=StageStatus.PENDING
        )
        assert stage.duration_seconds is None

    def test_duration_seconds_property_no_completion(self) -> None:
        """Test duration_seconds property when not completed."""
        stage = WorkflowStage(
            name="test",
            display_name="Test",
            status=StageStatus.ACTIVE,
            started_at=datetime.now(),
        )
        assert stage.duration_seconds is None

    def test_duration_display_property_seconds(self) -> None:
        """Test duration_display property for durations under 60 seconds."""
        started = datetime(2025, 1, 1, 10, 0, 0)
        completed = datetime(2025, 1, 1, 10, 0, 45)

        stage = WorkflowStage(
            name="test",
            display_name="Test",
            status=StageStatus.COMPLETED,
            started_at=started,
            completed_at=completed,
        )

        assert stage.duration_display == "45s"

    def test_duration_display_property_minutes_seconds(self) -> None:
        """Test duration_display property for durations over 60 seconds."""
        started = datetime(2025, 1, 1, 10, 0, 0)
        completed = datetime(2025, 1, 1, 10, 2, 30)

        stage = WorkflowStage(
            name="test",
            display_name="Test",
            status=StageStatus.COMPLETED,
            started_at=started,
            completed_at=completed,
        )

        assert stage.duration_display == "2m 30s"

    def test_duration_display_property_exact_minutes(self) -> None:
        """Test duration_display property for exact minutes."""
        started = datetime(2025, 1, 1, 10, 0, 0)
        completed = datetime(2025, 1, 1, 10, 3, 0)

        stage = WorkflowStage(
            name="test",
            display_name="Test",
            status=StageStatus.COMPLETED,
            started_at=started,
            completed_at=completed,
        )

        assert stage.duration_display == "3m 0s"

    def test_duration_display_property_no_duration(self) -> None:
        """Test duration_display property when no duration available."""
        stage = WorkflowStage(
            name="test", display_name="Test", status=StageStatus.PENDING
        )
        assert stage.duration_display == ""

    def test_workflow_stage_with_error(self) -> None:
        """Test WorkflowStage with error message."""
        stage = WorkflowStage(
            name="build",
            display_name="Build",
            status=StageStatus.FAILED,
            error_message="Build failed: compilation error",
        )

        assert stage.status == StageStatus.FAILED
        assert stage.error_message == "Build failed: compilation error"

    def test_workflow_stage_is_frozen(self) -> None:
        """Test WorkflowStage is immutable (frozen)."""
        stage = WorkflowStage(
            name="test", display_name="Test", status=StageStatus.PENDING
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            stage.status = StageStatus.COMPLETED  # type: ignore[misc]


class TestValidationStep:
    """Tests for ValidationStep dataclass."""

    def test_creation_with_required_fields(self) -> None:
        """Test creating ValidationStep with required fields."""
        step = ValidationStep(
            name="format",
            display_name="Format",
            status=ValidationStepStatus.PENDING,
        )

        assert step.name == "format"
        assert step.display_name == "Format"
        assert step.status == ValidationStepStatus.PENDING
        assert step.error_output is None  # default
        assert step.command is None  # default

    def test_creation_with_all_fields(self) -> None:
        """Test creating ValidationStep with all fields."""
        step = ValidationStep(
            name="lint",
            display_name="Lint",
            status=ValidationStepStatus.FAILED,
            error_output="Line 42: undefined variable 'x'",
            command="ruff check src/",
        )

        assert step.name == "lint"
        assert step.display_name == "Lint"
        assert step.status == ValidationStepStatus.FAILED
        assert step.error_output == "Line 42: undefined variable 'x'"
        assert step.command == "ruff check src/"

    def test_error_output_defaults_to_none(self) -> None:
        """Test error_output defaults to None."""
        step = ValidationStep(
            name="test", display_name="Test", status=ValidationStepStatus.PASSED
        )
        assert step.error_output is None

    def test_command_defaults_to_none(self) -> None:
        """Test command defaults to None."""
        step = ValidationStep(
            name="test", display_name="Test", status=ValidationStepStatus.PASSED
        )
        assert step.command is None

    def test_different_statuses(self) -> None:
        """Test ValidationStep with different statuses."""
        for status in ValidationStepStatus:
            step = ValidationStep(
                name="test", display_name="Test", status=status
            )
            assert step.status == status

    def test_validation_step_is_frozen(self) -> None:
        """Test ValidationStep is immutable (frozen)."""
        step = ValidationStep(
            name="test", display_name="Test", status=ValidationStepStatus.PENDING
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            step.status = ValidationStepStatus.PASSED  # type: ignore[misc]


class TestAgentMessage:
    """Tests for AgentMessage dataclass."""

    def test_creation_with_required_fields(self) -> None:
        """Test creating AgentMessage with required fields."""
        timestamp = datetime(2025, 1, 1, 10, 0, 0)
        message = AgentMessage(
            id="msg-001",
            timestamp=timestamp,
            agent_id="agent-1",
            agent_name="CodeReviewer",
            message_type=MessageType.TEXT,
            content="Starting code review...",
        )

        assert message.id == "msg-001"
        assert message.timestamp == timestamp
        assert message.agent_id == "agent-1"
        assert message.agent_name == "CodeReviewer"
        assert message.message_type == MessageType.TEXT
        assert message.content == "Starting code review..."
        assert message.language is None  # default
        assert message.tool_call is None  # default

    def test_creation_with_all_fields(self) -> None:
        """Test creating AgentMessage with all fields."""
        timestamp = datetime(2025, 1, 1, 10, 0, 0)
        tool_call = ToolCallInfo(
            tool_name="read_file",
            arguments="file_path=/src/main.py",
            result="File contents...",
        )

        message = AgentMessage(
            id="msg-002",
            timestamp=timestamp,
            agent_id="agent-2",
            agent_name="Implementer",
            message_type=MessageType.TOOL_CALL,
            content="Reading file...",
            language="python",
            tool_call=tool_call,
        )

        assert message.id == "msg-002"
        assert message.timestamp == timestamp
        assert message.agent_id == "agent-2"
        assert message.agent_name == "Implementer"
        assert message.message_type == MessageType.TOOL_CALL
        assert message.content == "Reading file..."
        assert message.language == "python"
        assert message.tool_call == tool_call

    def test_language_defaults_to_none(self) -> None:
        """Test language defaults to None."""
        message = AgentMessage(
            id="test",
            timestamp=datetime.now(),
            agent_id="agent",
            agent_name="Agent",
            message_type=MessageType.TEXT,
            content="Test",
        )
        assert message.language is None

    def test_tool_call_defaults_to_none(self) -> None:
        """Test tool_call defaults to None."""
        message = AgentMessage(
            id="test",
            timestamp=datetime.now(),
            agent_id="agent",
            agent_name="Agent",
            message_type=MessageType.TEXT,
            content="Test",
        )
        assert message.tool_call is None

    def test_different_message_types(self) -> None:
        """Test AgentMessage with different message types."""
        for msg_type in MessageType:
            message = AgentMessage(
                id=f"msg-{msg_type.value}",
                timestamp=datetime.now(),
                agent_id="agent",
                agent_name="Agent",
                message_type=msg_type,
                content="Test content",
            )
            assert message.message_type == msg_type

    def test_code_message_with_language(self) -> None:
        """Test AgentMessage with CODE type and language."""
        message = AgentMessage(
            id="code-msg",
            timestamp=datetime.now(),
            agent_id="agent",
            agent_name="Agent",
            message_type=MessageType.CODE,
            content="def foo():\n    pass",
            language="python",
        )

        assert message.message_type == MessageType.CODE
        assert message.language == "python"
        assert "def foo()" in message.content

    def test_agent_message_is_frozen(self) -> None:
        """Test AgentMessage is immutable (frozen)."""
        message = AgentMessage(
            id="test",
            timestamp=datetime.now(),
            agent_id="agent",
            agent_name="Agent",
            message_type=MessageType.TEXT,
            content="Test",
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            message.content = "Modified"  # type: ignore[misc]


# =============================================================================
# Widget State Model Tests (012-workflow-widgets)
# =============================================================================


class TestAgentOutputState:
    """Tests for AgentOutputState dataclass."""

    def test_creation_with_defaults(self) -> None:
        """Test creating AgentOutputState with default values."""
        state = AgentOutputState()

        assert state.messages == []
        assert state.max_messages == 1000
        assert state.auto_scroll is True
        assert state.search_query is None
        assert state.search_matches == []
        assert state.filter_agent is None
        assert state.truncated is False

    def test_creation_with_custom_values(self) -> None:
        """Test creating AgentOutputState with custom values."""
        message = AgentMessage(
            id="msg-1",
            timestamp=datetime.now(),
            agent_id="agent-1",
            agent_name="Agent",
            message_type=MessageType.TEXT,
            content="Test",
        )

        state = AgentOutputState(
            messages=[message],
            max_messages=500,
            auto_scroll=False,
            search_query="test",
            search_matches=[0],
            filter_agent="agent-1",
            truncated=True,
        )

        assert len(state.messages) == 1
        assert state.max_messages == 500
        assert state.auto_scroll is False
        assert state.search_query == "test"
        assert state.search_matches == [0]
        assert state.filter_agent == "agent-1"
        assert state.truncated is True

    def test_add_message_method(self) -> None:
        """Test add_message method adds messages."""
        state = AgentOutputState()

        msg1 = AgentMessage(
            id="msg-1",
            timestamp=datetime.now(),
            agent_id="agent",
            agent_name="Agent",
            message_type=MessageType.TEXT,
            content="First",
        )
        msg2 = AgentMessage(
            id="msg-2",
            timestamp=datetime.now(),
            agent_id="agent",
            agent_name="Agent",
            message_type=MessageType.TEXT,
            content="Second",
        )

        state.add_message(msg1)
        state.add_message(msg2)

        assert len(state.messages) == 2
        assert state.messages[0] == msg1
        assert state.messages[1] == msg2

    def test_add_message_respects_max_messages(self) -> None:
        """Test add_message maintains buffer limit."""
        state = AgentOutputState(max_messages=3)

        # Add 5 messages
        for i in range(5):
            msg = AgentMessage(
                id=f"msg-{i}",
                timestamp=datetime.now(),
                agent_id="agent",
                agent_name="Agent",
                message_type=MessageType.TEXT,
                content=f"Message {i}",
            )
            state.add_message(msg)

        # Should keep only last 3
        assert len(state.messages) == 3
        assert state.messages[0].content == "Message 2"
        assert state.messages[1].content == "Message 3"
        assert state.messages[2].content == "Message 4"
        assert state.truncated is True

    def test_filtered_messages_property_no_filter(self) -> None:
        """Test filtered_messages property with no filter."""
        msg1 = AgentMessage(
            id="msg-1",
            timestamp=datetime.now(),
            agent_id="agent-1",
            agent_name="Agent1",
            message_type=MessageType.TEXT,
            content="Test",
        )
        msg2 = AgentMessage(
            id="msg-2",
            timestamp=datetime.now(),
            agent_id="agent-2",
            agent_name="Agent2",
            message_type=MessageType.TEXT,
            content="Test",
        )

        state = AgentOutputState(messages=[msg1, msg2])
        assert len(state.filtered_messages) == 2

    def test_filtered_messages_property_with_agent_filter(self) -> None:
        """Test filtered_messages property with agent filter."""
        msg1 = AgentMessage(
            id="msg-1",
            timestamp=datetime.now(),
            agent_id="agent-1",
            agent_name="Agent1",
            message_type=MessageType.TEXT,
            content="Test",
        )
        msg2 = AgentMessage(
            id="msg-2",
            timestamp=datetime.now(),
            agent_id="agent-2",
            agent_name="Agent2",
            message_type=MessageType.TEXT,
            content="Test",
        )
        msg3 = AgentMessage(
            id="msg-3",
            timestamp=datetime.now(),
            agent_id="agent-1",
            agent_name="Agent1",
            message_type=MessageType.TEXT,
            content="Test",
        )

        state = AgentOutputState(
            messages=[msg1, msg2, msg3], filter_agent="agent-1"
        )

        filtered = state.filtered_messages
        assert len(filtered) == 2
        assert filtered[0] == msg1
        assert filtered[1] == msg3

    def test_is_empty_property_when_empty(self) -> None:
        """Test is_empty property when no messages."""
        state = AgentOutputState()
        assert state.is_empty is True

    def test_is_empty_property_when_not_empty(self) -> None:
        """Test is_empty property when messages exist."""
        msg = AgentMessage(
            id="msg-1",
            timestamp=datetime.now(),
            agent_id="agent",
            agent_name="Agent",
            message_type=MessageType.TEXT,
            content="Test",
        )
        state = AgentOutputState(messages=[msg])
        assert state.is_empty is False

    def test_agent_output_state_is_mutable(self) -> None:
        """Test AgentOutputState is mutable (not frozen)."""
        state = AgentOutputState()

        # Should allow modification
        state.auto_scroll = False
        assert state.auto_scroll is False

        state.search_query = "test"
        assert state.search_query == "test"


class TestWorkflowProgressState:
    """Tests for WorkflowProgressState dataclass."""

    def test_creation_with_defaults(self) -> None:
        """Test creating WorkflowProgressState with default values."""
        state = WorkflowProgressState()

        assert state.stages == ()
        assert state.loading is False
        assert state.expanded_stage is None

    def test_creation_with_custom_values(self) -> None:
        """Test creating WorkflowProgressState with custom values."""
        stage1 = WorkflowStage(
            name="setup", display_name="Setup", status=StageStatus.COMPLETED
        )
        stage2 = WorkflowStage(
            name="build", display_name="Build", status=StageStatus.ACTIVE
        )

        state = WorkflowProgressState(
            stages=(stage1, stage2), loading=True, expanded_stage="setup"
        )

        assert len(state.stages) == 2
        assert state.loading is True
        assert state.expanded_stage == "setup"

    def test_current_stage_property_with_active_stage(self) -> None:
        """Test current_stage property returns active stage."""
        stage1 = WorkflowStage(
            name="setup", display_name="Setup", status=StageStatus.COMPLETED
        )
        stage2 = WorkflowStage(
            name="build", display_name="Build", status=StageStatus.ACTIVE
        )
        stage3 = WorkflowStage(
            name="test", display_name="Test", status=StageStatus.PENDING
        )

        state = WorkflowProgressState(stages=(stage1, stage2, stage3))

        assert state.current_stage == stage2
        assert state.current_stage.status == StageStatus.ACTIVE

    def test_current_stage_property_no_active_stage(self) -> None:
        """Test current_stage property when no stage is active."""
        stage1 = WorkflowStage(
            name="setup", display_name="Setup", status=StageStatus.COMPLETED
        )
        stage2 = WorkflowStage(
            name="build", display_name="Build", status=StageStatus.PENDING
        )

        state = WorkflowProgressState(stages=(stage1, stage2))
        assert state.current_stage is None

    def test_current_stage_property_empty_stages(self) -> None:
        """Test current_stage property with no stages."""
        state = WorkflowProgressState()
        assert state.current_stage is None

    def test_is_empty_property_when_empty(self) -> None:
        """Test is_empty property when no stages."""
        state = WorkflowProgressState()
        assert state.is_empty is True

    def test_is_empty_property_when_not_empty(self) -> None:
        """Test is_empty property when stages exist."""
        stage = WorkflowStage(
            name="setup", display_name="Setup", status=StageStatus.PENDING
        )
        state = WorkflowProgressState(stages=(stage,))
        assert state.is_empty is False

    def test_is_empty_property_when_loading(self) -> None:
        """Test is_empty property when loading."""
        state = WorkflowProgressState(loading=True)
        assert state.is_empty is False

    def test_workflow_progress_state_is_frozen(self) -> None:
        """Test WorkflowProgressState is immutable (frozen)."""
        state = WorkflowProgressState()

        with pytest.raises(Exception):  # FrozenInstanceError
            state.loading = True  # type: ignore[misc]


class TestReviewFindingsState:
    """Tests for ReviewFindingsState dataclass."""

    def test_creation_with_defaults(self) -> None:
        """Test creating ReviewFindingsState with default values."""
        state = ReviewFindingsState()

        assert state.findings == ()
        assert state.expanded_index is None
        assert state.code_context is None
        assert state.focused_index == 0

    def test_creation_with_custom_values(self) -> None:
        """Test creating ReviewFindingsState with custom values."""
        location = CodeLocation(file_path="test.py", line_number=1)
        finding = ReviewFinding(
            id="test",
            severity=FindingSeverity.ERROR,
            location=location,
            title="Test",
            description="Test",
        )
        item = ReviewFindingItem(finding=finding, selected=True)

        context = CodeContext(
            file_path="test.py",
            start_line=1,
            end_line=3,
            content="code",
            highlight_line=2,
        )

        state = ReviewFindingsState(
            findings=(item,),
            expanded_index=0,
            code_context=context,
            focused_index=0,
        )

        assert len(state.findings) == 1
        assert state.expanded_index == 0
        assert state.code_context == context
        assert state.focused_index == 0

    def test_selected_findings_property_with_selections(self) -> None:
        """Test selected_findings property with selected items."""
        location = CodeLocation(file_path="test.py", line_number=1)
        finding1 = ReviewFinding(
            id="f1",
            severity=FindingSeverity.ERROR,
            location=location,
            title="Test 1",
            description="Test",
        )
        finding2 = ReviewFinding(
            id="f2",
            severity=FindingSeverity.WARNING,
            location=location,
            title="Test 2",
            description="Test",
        )
        finding3 = ReviewFinding(
            id="f3",
            severity=FindingSeverity.SUGGESTION,
            location=location,
            title="Test 3",
            description="Test",
        )

        item1 = ReviewFindingItem(finding=finding1, selected=True)
        item2 = ReviewFindingItem(finding=finding2, selected=False)
        item3 = ReviewFindingItem(finding=finding3, selected=True)

        state = ReviewFindingsState(findings=(item1, item2, item3))

        selected = state.selected_findings
        assert len(selected) == 2
        assert finding1 in selected
        assert finding3 in selected
        assert finding2 not in selected

    def test_selected_findings_property_no_selections(self) -> None:
        """Test selected_findings property with no selections."""
        location = CodeLocation(file_path="test.py", line_number=1)
        finding = ReviewFinding(
            id="test",
            severity=FindingSeverity.ERROR,
            location=location,
            title="Test",
            description="Test",
        )
        item = ReviewFindingItem(finding=finding, selected=False)

        state = ReviewFindingsState(findings=(item,))
        assert state.selected_findings == ()

    def test_selected_count_property(self) -> None:
        """Test selected_count property."""
        location = CodeLocation(file_path="test.py", line_number=1)
        finding1 = ReviewFinding(
            id="f1",
            severity=FindingSeverity.ERROR,
            location=location,
            title="Test 1",
            description="Test",
        )
        finding2 = ReviewFinding(
            id="f2",
            severity=FindingSeverity.WARNING,
            location=location,
            title="Test 2",
            description="Test",
        )

        item1 = ReviewFindingItem(finding=finding1, selected=True)
        item2 = ReviewFindingItem(finding=finding2, selected=True)

        state = ReviewFindingsState(findings=(item1, item2))
        assert state.selected_count == 2

    def test_selected_count_property_no_selections(self) -> None:
        """Test selected_count property with no selections."""
        state = ReviewFindingsState()
        assert state.selected_count == 0

    def test_findings_by_severity_property(self) -> None:
        """Test findings_by_severity property groups correctly."""
        location = CodeLocation(file_path="test.py", line_number=1)

        error1 = ReviewFinding(
            id="e1",
            severity=FindingSeverity.ERROR,
            location=location,
            title="Error 1",
            description="Test",
        )
        error2 = ReviewFinding(
            id="e2",
            severity=FindingSeverity.ERROR,
            location=location,
            title="Error 2",
            description="Test",
        )
        warning = ReviewFinding(
            id="w1",
            severity=FindingSeverity.WARNING,
            location=location,
            title="Warning 1",
            description="Test",
        )
        suggestion = ReviewFinding(
            id="s1",
            severity=FindingSeverity.SUGGESTION,
            location=location,
            title="Suggestion 1",
            description="Test",
        )

        item1 = ReviewFindingItem(finding=error1)
        item2 = ReviewFindingItem(finding=error2)
        item3 = ReviewFindingItem(finding=warning)
        item4 = ReviewFindingItem(finding=suggestion)

        state = ReviewFindingsState(findings=(item1, item2, item3, item4))

        grouped = state.findings_by_severity
        assert len(grouped[FindingSeverity.ERROR]) == 2
        assert len(grouped[FindingSeverity.WARNING]) == 1
        assert len(grouped[FindingSeverity.SUGGESTION]) == 1

    def test_findings_by_severity_property_empty(self) -> None:
        """Test findings_by_severity property with no findings."""
        state = ReviewFindingsState()

        grouped = state.findings_by_severity
        assert len(grouped[FindingSeverity.ERROR]) == 0
        assert len(grouped[FindingSeverity.WARNING]) == 0
        assert len(grouped[FindingSeverity.SUGGESTION]) == 0

    def test_is_empty_property_when_empty(self) -> None:
        """Test is_empty property when no findings."""
        state = ReviewFindingsState()
        assert state.is_empty is True

    def test_is_empty_property_when_not_empty(self) -> None:
        """Test is_empty property when findings exist."""
        location = CodeLocation(file_path="test.py", line_number=1)
        finding = ReviewFinding(
            id="test",
            severity=FindingSeverity.ERROR,
            location=location,
            title="Test",
            description="Test",
        )
        item = ReviewFindingItem(finding=finding)

        state = ReviewFindingsState(findings=(item,))
        assert state.is_empty is False

    def test_review_findings_state_is_frozen(self) -> None:
        """Test ReviewFindingsState is immutable (frozen)."""
        state = ReviewFindingsState()

        with pytest.raises(Exception):  # FrozenInstanceError
            state.focused_index = 1  # type: ignore[misc]


class TestValidationStatusState:
    """Tests for ValidationStatusState dataclass."""

    def test_creation_with_defaults(self) -> None:
        """Test creating ValidationStatusState with default values."""
        state = ValidationStatusState()

        assert state.steps == ()
        assert state.expanded_step is None
        assert state.loading is False
        assert state.running_step is None

    def test_creation_with_custom_values(self) -> None:
        """Test creating ValidationStatusState with custom values."""
        step1 = ValidationStep(
            name="format",
            display_name="Format",
            status=ValidationStepStatus.PASSED,
        )
        step2 = ValidationStep(
            name="lint",
            display_name="Lint",
            status=ValidationStepStatus.RUNNING,
        )

        state = ValidationStatusState(
            steps=(step1, step2),
            expanded_step="format",
            loading=True,
            running_step="lint",
        )

        assert len(state.steps) == 2
        assert state.expanded_step == "format"
        assert state.loading is True
        assert state.running_step == "lint"

    def test_all_passed_property_when_all_passed(self) -> None:
        """Test all_passed property when all steps passed."""
        steps = (
            ValidationStep(
                name="format",
                display_name="Format",
                status=ValidationStepStatus.PASSED,
            ),
            ValidationStep(
                name="lint",
                display_name="Lint",
                status=ValidationStepStatus.PASSED,
            ),
            ValidationStep(
                name="test",
                display_name="Test",
                status=ValidationStepStatus.PASSED,
            ),
        )

        state = ValidationStatusState(steps=steps)
        assert state.all_passed is True

    def test_all_passed_property_when_some_failed(self) -> None:
        """Test all_passed property when some steps failed."""
        steps = (
            ValidationStep(
                name="format",
                display_name="Format",
                status=ValidationStepStatus.PASSED,
            ),
            ValidationStep(
                name="lint",
                display_name="Lint",
                status=ValidationStepStatus.FAILED,
            ),
        )

        state = ValidationStatusState(steps=steps)
        assert state.all_passed is False

    def test_all_passed_property_when_some_pending(self) -> None:
        """Test all_passed property when some steps pending."""
        steps = (
            ValidationStep(
                name="format",
                display_name="Format",
                status=ValidationStepStatus.PASSED,
            ),
            ValidationStep(
                name="lint",
                display_name="Lint",
                status=ValidationStepStatus.PENDING,
            ),
        )

        state = ValidationStatusState(steps=steps)
        assert state.all_passed is False

    def test_has_failures_property_when_failures(self) -> None:
        """Test has_failures property when steps failed."""
        steps = (
            ValidationStep(
                name="format",
                display_name="Format",
                status=ValidationStepStatus.PASSED,
            ),
            ValidationStep(
                name="lint",
                display_name="Lint",
                status=ValidationStepStatus.FAILED,
            ),
        )

        state = ValidationStatusState(steps=steps)
        assert state.has_failures is True

    def test_has_failures_property_when_no_failures(self) -> None:
        """Test has_failures property when no failures."""
        steps = (
            ValidationStep(
                name="format",
                display_name="Format",
                status=ValidationStepStatus.PASSED,
            ),
            ValidationStep(
                name="lint",
                display_name="Lint",
                status=ValidationStepStatus.RUNNING,
            ),
        )

        state = ValidationStatusState(steps=steps)
        assert state.has_failures is False

    def test_is_running_property_when_running(self) -> None:
        """Test is_running property when steps are running."""
        steps = (
            ValidationStep(
                name="format",
                display_name="Format",
                status=ValidationStepStatus.PASSED,
            ),
            ValidationStep(
                name="lint",
                display_name="Lint",
                status=ValidationStepStatus.RUNNING,
            ),
        )

        state = ValidationStatusState(steps=steps)
        assert state.is_running is True

    def test_is_running_property_when_not_running(self) -> None:
        """Test is_running property when no steps running."""
        steps = (
            ValidationStep(
                name="format",
                display_name="Format",
                status=ValidationStepStatus.PASSED,
            ),
            ValidationStep(
                name="lint",
                display_name="Lint",
                status=ValidationStepStatus.PENDING,
            ),
        )

        state = ValidationStatusState(steps=steps)
        assert state.is_running is False

    def test_is_empty_property_when_empty(self) -> None:
        """Test is_empty property when no steps."""
        state = ValidationStatusState()
        assert state.is_empty is True

    def test_is_empty_property_when_not_empty(self) -> None:
        """Test is_empty property when steps exist."""
        step = ValidationStep(
            name="format",
            display_name="Format",
            status=ValidationStepStatus.PASSED,
        )
        state = ValidationStatusState(steps=(step,))
        assert state.is_empty is False

    def test_is_empty_property_when_loading(self) -> None:
        """Test is_empty property when loading."""
        state = ValidationStatusState(loading=True)
        assert state.is_empty is False

    def test_validation_status_state_is_frozen(self) -> None:
        """Test ValidationStatusState is immutable (frozen)."""
        state = ValidationStatusState()

        with pytest.raises(Exception):  # FrozenInstanceError
            state.loading = True  # type: ignore[misc]


class TestPRSummaryState:
    """Tests for PRSummaryState dataclass."""

    def test_creation_with_defaults(self) -> None:
        """Test creating PRSummaryState with default values."""
        state = PRSummaryState()

        assert state.pr is None
        assert state.description_expanded is False
        assert state.loading is False

    def test_creation_with_custom_values(self) -> None:
        """Test creating PRSummaryState with custom values."""
        pr = PRInfo(
            number=123,
            title="Test PR",
            description="Test description",
            state=PRState.OPEN,
            url="https://github.com/org/repo/pull/123",
        )

        state = PRSummaryState(
            pr=pr, description_expanded=True, loading=False
        )

        assert state.pr == pr
        assert state.description_expanded is True
        assert state.loading is False

    def test_is_empty_property_when_empty(self) -> None:
        """Test is_empty property when no PR data."""
        state = PRSummaryState()
        assert state.is_empty is True

    def test_is_empty_property_when_not_empty(self) -> None:
        """Test is_empty property when PR data exists."""
        pr = PRInfo(
            number=123,
            title="Test PR",
            description="Test description",
            state=PRState.OPEN,
            url="https://github.com/org/repo/pull/123",
        )
        state = PRSummaryState(pr=pr)
        assert state.is_empty is False

    def test_is_empty_property_when_loading(self) -> None:
        """Test is_empty property when loading."""
        state = PRSummaryState(loading=True)
        assert state.is_empty is False

    def test_pr_summary_state_is_frozen(self) -> None:
        """Test PRSummaryState is immutable (frozen)."""
        state = PRSummaryState()

        with pytest.raises(Exception):  # FrozenInstanceError
            state.loading = True  # type: ignore[misc]


# =============================================================================
# Cross-Model Integration Tests
# =============================================================================


class TestCrossModelIntegration:
    """Tests for interactions between different models."""

    def test_workflow_screen_with_review_issues(self) -> None:
        """Test combining workflow and review states."""
        # Create workflow state
        workflow_state = WorkflowScreenState(
            title="Code Review",
            workflow_name="fly",
            branch_name="feature/auth",
        )

        # Create review issues
        issue = ReviewIssue(
            file_path="src/auth.py",
            line_number=42,
            severity=IssueSeverity.ERROR,
            message="Security issue",
            source="architecture",
        )

        review_state = ReviewScreenState(
            title="Review Results",
            issues=(issue,),
        )

        assert workflow_state.workflow_name == "fly"
        assert review_state.issues[0].severity == IssueSeverity.ERROR

    def test_home_screen_with_recent_workflows(self) -> None:
        """Test home screen with multiple recent workflows."""
        workflows = tuple(
            RecentWorkflowEntry(
                branch_name=f"feature/task{i}",
                workflow_type="fly" if i % 2 == 0 else "refuel",
                status="completed",
                started_at=datetime.now(),
            )
            for i in range(5)
        )

        home_state = HomeScreenState(
            title="Home",
            recent_workflows=workflows,
            selected_index=2,
        )

        assert len(home_state.recent_workflows) == 5
        assert home_state.selected_workflow is not None
        assert home_state.selected_workflow.branch_name == "feature/task2"

    def test_sidebar_with_workflow_stages(self) -> None:
        """Test sidebar showing workflow stages."""
        stages = (
            StageState(
                name="setup",
                display_name="Setup",
                status=StageStatus.COMPLETED,
            ),
            StageState(
                name="implementation",
                display_name="Implementation",
                status=StageStatus.ACTIVE,
            ),
            StageState(
                name="review",
                display_name="Code Review",
                status=StageStatus.PENDING,
            ),
        )

        sidebar = SidebarState(
            mode=SidebarMode.WORKFLOW,
            workflow_stages=stages,
        )

        assert sidebar.mode == SidebarMode.WORKFLOW
        assert len(sidebar.workflow_stages) == 3
        assert sidebar.workflow_stages[1].status == StageStatus.ACTIVE

    def test_log_panel_with_multiple_entries(self) -> None:
        """Test log panel with multiple log entries."""
        log_state = LogPanelState(visible=True, max_entries=10)

        # Add various log entries
        log_state.add_entry(
            LogEntry(
                timestamp=datetime.now(),
                source="agent",
                level="info",
                message="Started task",
            )
        )
        log_state.add_entry(
            LogEntry(
                timestamp=datetime.now(),
                source="workflow",
                level="success",
                message="Stage completed",
            )
        )
        log_state.add_entry(
            LogEntry(
                timestamp=datetime.now(),
                source="tool",
                level="error",
                message="Validation failed",
            )
        )

        assert len(log_state.entries) == 3
        assert log_state.entries[0].level == "info"
        assert log_state.entries[1].level == "success"
        assert log_state.entries[2].level == "error"
