"""Unit tests for HomeScreen."""
from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from maverick.tui.screens.home import HomeScreen
from maverick.tui.widgets.workflow_list import WorkflowList


# =============================================================================
# HomeScreen Initialization Tests
# =============================================================================


class TestHomeScreenInitialization:
    """Tests for HomeScreen initialization."""

    def test_initialization_with_defaults(self) -> None:
        """Test screen creation with default parameters."""
        screen = HomeScreen()
        assert screen.TITLE == "Home"
        assert len(screen.BINDINGS) > 0

    def test_initialization_with_custom_parameters(self) -> None:
        """Test screen creation with custom parameters."""
        screen = HomeScreen(name="custom-home", id="home-1", classes="custom")
        assert screen.name == "custom-home"
        assert screen.id == "home-1"


# =============================================================================
# HomeScreen Public Methods Tests
# =============================================================================


class TestHomeScreenRefreshRecentWorkflows:
    """Tests for refresh_recent_workflows method."""

    def test_refresh_with_none_clears_list(self) -> None:
        """Test that passing None clears the workflow list."""
        screen = HomeScreen()
        mock_workflow_list = MagicMock(spec=WorkflowList)

        with patch.object(screen, "query_one", return_value=mock_workflow_list):
            screen.refresh_recent_workflows(None)

        mock_workflow_list.set_workflows.assert_called_once_with([])

    def test_refresh_with_empty_list(self) -> None:
        """Test refreshing with an empty workflow list."""
        screen = HomeScreen()
        mock_workflow_list = MagicMock(spec=WorkflowList)

        with patch.object(screen, "query_one", return_value=mock_workflow_list):
            screen.refresh_recent_workflows([])

        mock_workflow_list.set_workflows.assert_called_once_with([])

    def test_refresh_with_workflows(self) -> None:
        """Test refreshing with actual workflow data."""
        screen = HomeScreen()
        mock_workflow_list = MagicMock(spec=WorkflowList)

        workflows = [
            {
                "branch_name": "feature/test",
                "workflow_type": "fly",
                "status": "completed",
                "started_at": "2025-01-01T00:00:00",
            },
            {
                "branch_name": "fix/bug",
                "workflow_type": "refuel",
                "status": "failed",
                "started_at": "2025-01-02T00:00:00",
            },
        ]

        with patch.object(screen, "query_one", return_value=mock_workflow_list):
            screen.refresh_recent_workflows(workflows)

        mock_workflow_list.set_workflows.assert_called_once_with(workflows)

    def test_refresh_with_multiple_workflows(self) -> None:
        """Test refreshing with multiple workflows."""
        screen = HomeScreen()
        mock_workflow_list = MagicMock(spec=WorkflowList)

        workflows = [
            {"branch_name": f"branch-{i}", "workflow_type": "fly", "status": "completed"}
            for i in range(5)
        ]

        with patch.object(screen, "query_one", return_value=mock_workflow_list):
            screen.refresh_recent_workflows(workflows)

        mock_workflow_list.set_workflows.assert_called_once_with(workflows)


class TestHomeScreenSelectWorkflow:
    """Tests for select_workflow method."""

    def test_select_workflow_by_index(self) -> None:
        """Test selecting a workflow by index."""
        screen = HomeScreen()
        mock_workflow_list = MagicMock(spec=WorkflowList)

        with patch.object(screen, "query_one", return_value=mock_workflow_list):
            screen.select_workflow(2)

        mock_workflow_list.select.assert_called_once_with(2)

    def test_select_first_workflow(self) -> None:
        """Test selecting the first workflow (index 0)."""
        screen = HomeScreen()
        mock_workflow_list = MagicMock(spec=WorkflowList)

        with patch.object(screen, "query_one", return_value=mock_workflow_list):
            screen.select_workflow(0)

        mock_workflow_list.select.assert_called_once_with(0)


# =============================================================================
# HomeScreen Actions Tests
# =============================================================================


class TestHomeScreenActions:
    """Tests for HomeScreen action methods."""

    def test_action_select_workflow(self) -> None:
        """Test action_select_workflow calls workflow list confirmation."""
        screen = HomeScreen()
        mock_workflow_list = MagicMock(spec=WorkflowList)

        with patch.object(screen, "query_one", return_value=mock_workflow_list):
            screen.action_select_workflow()

        mock_workflow_list.action_confirm_selection.assert_called_once()

    def test_action_start_workflow(self) -> None:
        """Test action_start_workflow pushes WorkflowScreen."""
        screen = HomeScreen()
        mock_app = MagicMock()
        mock_workflow_screen = MagicMock()

        with patch.object(
            type(screen), "app", new_callable=PropertyMock, return_value=mock_app
        ), patch(
            "maverick.tui.screens.workflow.WorkflowScreen", return_value=mock_workflow_screen
        ):
            screen.action_start_workflow()

        mock_app.push_screen.assert_called_once_with(mock_workflow_screen)

    def test_action_refresh(self) -> None:
        """Test action_refresh calls refresh_recent_workflows."""
        screen = HomeScreen()
        mock_workflow_list = MagicMock(spec=WorkflowList)

        with patch.object(screen, "query_one", return_value=mock_workflow_list):
            screen.action_refresh()

        # Should clear the list when no workflows provided
        mock_workflow_list.set_workflows.assert_called_once_with([])

    def test_action_move_down(self) -> None:
        """Test action_move_down delegates to workflow list."""
        screen = HomeScreen()
        mock_workflow_list = MagicMock(spec=WorkflowList)

        with patch.object(screen, "query_one", return_value=mock_workflow_list):
            screen.action_move_down()

        mock_workflow_list.action_select_next.assert_called_once()

    def test_action_move_up(self) -> None:
        """Test action_move_up delegates to workflow list."""
        screen = HomeScreen()
        mock_workflow_list = MagicMock(spec=WorkflowList)

        with patch.object(screen, "query_one", return_value=mock_workflow_list):
            screen.action_move_up()

        mock_workflow_list.action_select_previous.assert_called_once()


# =============================================================================
# HomeScreen Event Handling Tests
# =============================================================================


class TestHomeScreenEventHandling:
    """Tests for HomeScreen event handling."""

    def test_on_workflow_list_workflow_selected(self) -> None:
        """Test handling workflow selection event."""
        screen = HomeScreen()
        mock_app = MagicMock()
        mock_workflow_screen = MagicMock()

        # Create a mock event
        workflow = {
            "workflow_type": "fly",
            "branch_name": "feature/test",
        }
        event = WorkflowList.WorkflowSelected(index=0, workflow=workflow)

        with patch.object(
            type(screen), "app", new_callable=PropertyMock, return_value=mock_app
        ), patch(
            "maverick.tui.screens.workflow.WorkflowScreen", return_value=mock_workflow_screen
        ) as mock_workflow_class:
            screen.on_workflow_list_workflow_selected(event)

        mock_workflow_class.assert_called_once_with(
            workflow_name="fly", branch_name="feature/test"
        )
        mock_app.push_screen.assert_called_once_with(mock_workflow_screen)

    def test_on_workflow_list_workflow_selected_with_defaults(self) -> None:
        """Test handling workflow selection with missing fields."""
        screen = HomeScreen()
        mock_app = MagicMock()
        mock_workflow_screen = MagicMock()

        # Create event with empty workflow
        event = WorkflowList.WorkflowSelected(index=0, workflow={})

        with patch.object(
            type(screen), "app", new_callable=PropertyMock, return_value=mock_app
        ), patch(
            "maverick.tui.screens.workflow.WorkflowScreen", return_value=mock_workflow_screen
        ) as mock_workflow_class:
            screen.on_workflow_list_workflow_selected(event)

        mock_workflow_class.assert_called_once_with(
            workflow_name="Workflow", branch_name="main"
        )
        mock_app.push_screen.assert_called_once_with(mock_workflow_screen)
