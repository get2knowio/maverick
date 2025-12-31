"""Unit tests for cross-model integration."""

from __future__ import annotations

from datetime import datetime

from maverick.tui.models import (
    HomeScreenState,
    IssueSeverity,
    LogEntry,
    LogPanelState,
    RecentWorkflowEntry,
    ReviewIssue,
    ReviewScreenState,
    SidebarMode,
    SidebarState,
    StageState,
    StageStatus,
    WorkflowScreenState,
)


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
