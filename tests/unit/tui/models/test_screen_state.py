"""Unit tests for TUI screen state models."""

from __future__ import annotations

from datetime import datetime

import pytest

from maverick.tui.models import (
    ConfigOption,
    ConfigScreenState,
    HomeScreenState,
    IssueSeverity,
    RecentWorkflowEntry,
    ReviewIssue,
    ReviewScreenState,
    ScreenState,
    StageState,
    StageStatus,
    WorkflowScreenState,
)


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
