"""Unit tests for HomeScreen."""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock, patch

from maverick.tui.history import WorkflowHistoryEntry, WorkflowHistoryStore
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
            {
                "branch_name": f"branch-{i}",
                "workflow_type": "fly",
                "status": "completed",
            }
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

        with (
            patch.object(
                type(screen), "app", new_callable=PropertyMock, return_value=mock_app
            ),
            patch(
                "maverick.tui.screens.workflow.WorkflowScreen",
                return_value=mock_workflow_screen,
            ),
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

        with (
            patch.object(
                type(screen), "app", new_callable=PropertyMock, return_value=mock_app
            ),
            patch(
                "maverick.tui.screens.workflow.WorkflowScreen",
                return_value=mock_workflow_screen,
            ) as mock_workflow_class,
        ):
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

        with (
            patch.object(
                type(screen), "app", new_callable=PropertyMock, return_value=mock_app
            ),
            patch(
                "maverick.tui.screens.workflow.WorkflowScreen",
                return_value=mock_workflow_screen,
            ) as mock_workflow_class,
        ):
            screen.on_workflow_list_workflow_selected(event)

        mock_workflow_class.assert_called_once_with(
            workflow_name="Workflow", branch_name="main"
        )
        mock_app.push_screen.assert_called_once_with(mock_workflow_screen)


# =============================================================================
# HomeScreen Workflow History Tests
# =============================================================================


class TestHomeScreenHistoryDisplay:
    """Tests for workflow history display in HomeScreen."""

    def test_on_mount_loads_history(self) -> None:
        """Test on_mount loads workflow history from store."""
        screen = HomeScreen()
        mock_workflow_list = MagicMock(spec=WorkflowList)

        # Create mock history entries
        entry1 = WorkflowHistoryEntry.create(
            workflow_type="fly",
            branch_name="feature/test",
            final_status="completed",
            stages_completed=["setup", "implementation"],
            finding_counts={"error": 0, "warning": 1, "suggestion": 2},
            pr_link="https://github.com/test/repo/pull/123",
        )
        entry2 = WorkflowHistoryEntry.create(
            workflow_type="refuel",
            branch_name="fix/bug",
            final_status="failed",
            stages_completed=["setup"],
            finding_counts={"error": 1, "warning": 0, "suggestion": 0},
        )

        mock_store = MagicMock(spec=WorkflowHistoryStore)
        mock_store.get_recent.return_value = [entry1, entry2]

        with (
            patch.object(screen, "query_one", return_value=mock_workflow_list),
            patch(
                "maverick.tui.screens.home.WorkflowHistoryStore",
                return_value=mock_store,
            ),
        ):
            # _load_history is called in on_mount
            screen._load_history()
            screen.refresh_recent_workflows()

        # Verify history was loaded and converted to workflow list format
        mock_store.get_recent.assert_called_with(10)
        assert mock_workflow_list.set_workflows.called

    def test_refresh_loads_history_from_store(self) -> None:
        """Test refresh_recent_workflows loads from history store when no
        workflows provided.
        """
        screen = HomeScreen()
        mock_workflow_list = MagicMock(spec=WorkflowList)

        entry1 = WorkflowHistoryEntry.create(
            workflow_type="fly",
            branch_name="feature/test",
            final_status="completed",
            stages_completed=[],
            finding_counts={},
        )

        mock_store = MagicMock(spec=WorkflowHistoryStore)
        mock_store.get_recent.return_value = [entry1]

        with (
            patch.object(screen, "query_one", return_value=mock_workflow_list),
            patch(
                "maverick.tui.screens.home.WorkflowHistoryStore",
                return_value=mock_store,
            ),
        ):
            screen.refresh_recent_workflows()

        mock_store.get_recent.assert_called_once_with(10)

    def test_history_entries_converted_to_workflow_dict(self) -> None:
        """Test history entries are converted to workflow dict format for
        WorkflowList.
        """
        screen = HomeScreen()
        mock_workflow_list = MagicMock(spec=WorkflowList)

        entry = WorkflowHistoryEntry.create(
            workflow_type="fly",
            branch_name="feature/test",
            final_status="completed",
            stages_completed=["setup", "implementation"],
            finding_counts={"error": 0, "warning": 1, "suggestion": 2},
            pr_link="https://github.com/test/repo/pull/123",
        )

        mock_store = MagicMock(spec=WorkflowHistoryStore)
        mock_store.get_recent.return_value = [entry]

        with (
            patch.object(screen, "query_one", return_value=mock_workflow_list),
            patch(
                "maverick.tui.screens.home.WorkflowHistoryStore",
                return_value=mock_store,
            ),
        ):
            screen._load_history()
            screen.refresh_recent_workflows()

        # Verify workflows were set with correct format
        assert mock_workflow_list.set_workflows.called
        call_args = mock_workflow_list.set_workflows.call_args[0][0]
        assert len(call_args) == 1
        workflow = call_args[0]
        assert workflow["branch_name"] == "feature/test"
        assert workflow["workflow_type"] == "fly"
        assert workflow["status"] == "completed"
        assert workflow["pr_url"] == "https://github.com/test/repo/pull/123"

    def test_failed_status_mapped_correctly(self) -> None:
        """Test failed workflow status is mapped correctly."""
        screen = HomeScreen()
        mock_workflow_list = MagicMock(spec=WorkflowList)

        entry = WorkflowHistoryEntry.create(
            workflow_type="refuel",
            branch_name="fix/bug",
            final_status="failed",
            stages_completed=[],
            finding_counts={},
        )

        mock_store = MagicMock(spec=WorkflowHistoryStore)
        mock_store.get_recent.return_value = [entry]

        with (
            patch.object(screen, "query_one", return_value=mock_workflow_list),
            patch(
                "maverick.tui.screens.home.WorkflowHistoryStore",
                return_value=mock_store,
            ),
        ):
            screen._load_history()
            screen.refresh_recent_workflows()

        call_args = mock_workflow_list.set_workflows.call_args[0][0]
        workflow = call_args[0]
        assert workflow["status"] == "failed"

    def test_empty_history_shows_no_workflows(self) -> None:
        """Test empty history results in empty workflow list."""
        screen = HomeScreen()
        mock_workflow_list = MagicMock(spec=WorkflowList)

        mock_store = MagicMock(spec=WorkflowHistoryStore)
        mock_store.get_recent.return_value = []

        with (
            patch.object(screen, "query_one", return_value=mock_workflow_list),
            patch(
                "maverick.tui.screens.home.WorkflowHistoryStore",
                return_value=mock_store,
            ),
        ):
            screen._load_history()
            screen.refresh_recent_workflows()

        mock_workflow_list.set_workflows.assert_called_once_with([])


class TestHomeScreenHistorySelection:
    """Tests for selecting historical workflow entries."""

    def test_select_history_entry_pushes_historical_review_screen(self) -> None:
        """Test selecting a history entry navigates to HistoricalReviewScreen."""
        screen = HomeScreen()
        mock_app = MagicMock()
        mock_workflow_list = MagicMock(spec=WorkflowList)
        mock_workflow_list.selected_index = 0

        # Create a history entry
        entry = WorkflowHistoryEntry.create(
            workflow_type="fly",
            branch_name="feature/test",
            final_status="completed",
            stages_completed=["setup", "implementation"],
            finding_counts={"error": 0, "warning": 1, "suggestion": 2},
            pr_link="https://github.com/test/repo/pull/123",
        )

        # Set up screen state with history
        screen.recent_workflows = (entry,)

        mock_review_screen = MagicMock()

        with (
            patch.object(
                type(screen), "app", new_callable=PropertyMock, return_value=mock_app
            ),
            patch.object(screen, "query_one", return_value=mock_workflow_list),
            patch(
                "maverick.tui.screens.history_review.HistoricalReviewScreen",
                return_value=mock_review_screen,
            ) as mock_review_class,
        ):
            screen.action_view_history_entry()

        # Verify HistoricalReviewScreen was created with the entry
        mock_review_class.assert_called_once_with(entry=entry)
        mock_app.push_screen.assert_called_once_with(mock_review_screen)

    def test_view_history_entry_with_invalid_index(self) -> None:
        """Test viewing history entry with invalid index does nothing."""
        screen = HomeScreen()
        mock_app = MagicMock()
        mock_workflow_list = MagicMock(spec=WorkflowList)
        mock_workflow_list.selected_index = 5  # Out of bounds

        entry = WorkflowHistoryEntry.create(
            workflow_type="fly",
            branch_name="test",
            final_status="completed",
            stages_completed=[],
            finding_counts={},
        )

        screen.recent_workflows = (entry,)

        with (
            patch.object(
                type(screen), "app", new_callable=PropertyMock, return_value=mock_app
            ),
            patch.object(screen, "query_one", return_value=mock_workflow_list),
            patch(
                "maverick.tui.screens.history_review.HistoricalReviewScreen"
            ) as mock_review_class,
        ):
            screen.action_view_history_entry()

        # Should not push any screen
        mock_review_class.assert_not_called()
        mock_app.push_screen.assert_not_called()

    def test_view_history_entry_with_empty_history(self) -> None:
        """Test viewing history entry with empty history does nothing."""
        screen = HomeScreen()
        mock_app = MagicMock()
        mock_workflow_list = MagicMock(spec=WorkflowList)
        mock_workflow_list.selected_index = 0

        screen.recent_workflows = ()

        with (
            patch.object(
                type(screen), "app", new_callable=PropertyMock, return_value=mock_app
            ),
            patch.object(screen, "query_one", return_value=mock_workflow_list),
            patch(
                "maverick.tui.screens.history_review.HistoricalReviewScreen"
            ) as mock_review_class,
        ):
            screen.action_view_history_entry()

        mock_review_class.assert_not_called()
        mock_app.push_screen.assert_not_called()
