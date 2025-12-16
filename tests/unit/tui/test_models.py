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
    ConfigOption,
    ConfigScreenState,
    HomeScreenState,
    IssueSeverity,
    LogEntry,
    LogPanelState,
    NavigationItem,
    RecentWorkflowEntry,
    ReviewIssue,
    ReviewScreenState,
    ScreenState,
    SidebarMode,
    SidebarState,
    StageState,
    StageStatus,
    ThemeColors,
    WorkflowScreenState,
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
