"""Unit tests for WorkflowList widget."""

from __future__ import annotations

from datetime import datetime

import pytest
from textual.app import App
from textual.widgets import Static

from maverick.tui.widgets.workflow_list import WorkflowList

# =============================================================================
# Test App for WorkflowList Testing
# =============================================================================


class WorkflowListTestApp(App):
    """Test app for WorkflowList widget testing."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.messages: list[WorkflowList.WorkflowSelected] = []

    def compose(self):
        """Compose the test app."""
        yield WorkflowList()

    def on_workflow_list_workflow_selected(
        self, message: WorkflowList.WorkflowSelected
    ) -> None:
        """Capture WorkflowSelected messages."""
        self.messages.append(message)


# =============================================================================
# WorkflowList Initialization Tests
# =============================================================================


class TestWorkflowListInitialization:
    """Tests for WorkflowList initialization."""

    @pytest.mark.asyncio
    async def test_initialization_defaults(self) -> None:
        """Test WorkflowList initializes with default values."""
        async with WorkflowListTestApp().run_test() as pilot:
            workflow_list = pilot.app.query_one(WorkflowList)

            assert workflow_list.selected_index == 0
            assert workflow_list._workflows == []

    @pytest.mark.asyncio
    async def test_compose_creates_empty_message(self) -> None:
        """Test compose creates empty message when no workflows."""
        async with WorkflowListTestApp().run_test() as pilot:
            workflow_list = pilot.app.query_one(WorkflowList)

            # Check empty message exists
            empty_message = workflow_list.query_one(".workflow-empty-message", Static)
            assert empty_message is not None


# =============================================================================
# Set Workflows Tests
# =============================================================================


class TestWorkflowListSetWorkflows:
    """Tests for WorkflowList set_workflows method."""

    @pytest.mark.asyncio
    async def test_set_workflows_with_empty_list(self) -> None:
        """Test set_workflows with empty list."""
        async with WorkflowListTestApp().run_test() as pilot:
            workflow_list = pilot.app.query_one(WorkflowList)

            workflow_list.set_workflows([])
            await pilot.pause()

            assert workflow_list._workflows == []
            assert workflow_list.selected_index == 0

            # Empty message should be shown
            empty_message = workflow_list.query_one(".workflow-empty-message", Static)
            assert empty_message is not None

    @pytest.mark.asyncio
    async def test_set_workflows_with_single_workflow(self) -> None:
        """Test set_workflows with single workflow."""
        async with WorkflowListTestApp().run_test() as pilot:
            workflow_list = pilot.app.query_one(WorkflowList)

            workflows = [
                {
                    "branch_name": "feature/test",
                    "workflow_type": "fly",
                    "status": "completed",
                    "started_at": datetime.now(),
                }
            ]
            workflow_list.set_workflows(workflows)

            assert len(workflow_list._workflows) == 1
            assert workflow_list.selected_index == 0

            # Verify workflow item exists
            item = workflow_list.query_one(".workflow-item-0", Static)
            assert item is not None

    @pytest.mark.asyncio
    async def test_set_workflows_with_multiple_workflows(self) -> None:
        """Test set_workflows with multiple workflows."""
        async with WorkflowListTestApp().run_test() as pilot:
            workflow_list = pilot.app.query_one(WorkflowList)

            workflows = [
                {
                    "branch_name": "feature/test1",
                    "workflow_type": "fly",
                    "status": "completed",
                    "started_at": datetime.now(),
                },
                {
                    "branch_name": "feature/test2",
                    "workflow_type": "refuel",
                    "status": "in_progress",
                    "started_at": datetime.now(),
                },
                {
                    "branch_name": "feature/test3",
                    "workflow_type": "fly",
                    "status": "failed",
                    "started_at": datetime.now(),
                },
            ]
            workflow_list.set_workflows(workflows)

            assert len(workflow_list._workflows) == 3
            assert workflow_list.selected_index == 0

            # Verify all items exist
            for i in range(3):
                item = workflow_list.query_one(f".workflow-item-{i}", Static)
                assert item is not None

    @pytest.mark.asyncio
    async def test_set_workflows_limits_to_10(self) -> None:
        """Test set_workflows limits to 10 most recent workflows."""
        async with WorkflowListTestApp().run_test() as pilot:
            workflow_list = pilot.app.query_one(WorkflowList)

            # Create 15 workflows
            workflows = [
                {
                    "branch_name": f"feature/test{i}",
                    "workflow_type": "fly",
                    "status": "completed",
                    "started_at": datetime.now(),
                }
                for i in range(15)
            ]
            workflow_list.set_workflows(workflows)

            # Should only keep first 10
            assert len(workflow_list._workflows) == 10

    @pytest.mark.asyncio
    async def test_set_workflows_resets_selected_index(self) -> None:
        """Test set_workflows resets selected_index to 0."""
        async with WorkflowListTestApp().run_test() as pilot:
            workflow_list = pilot.app.query_one(WorkflowList)

            # Set some workflows and select the second one
            workflows = [
                {
                    "branch_name": f"feature/test{i}",
                    "workflow_type": "fly",
                    "status": "completed",
                    "started_at": datetime.now(),
                }
                for i in range(3)
            ]
            workflow_list.set_workflows(workflows)
            await pilot.pause()
            workflow_list.selected_index = 2

            # Set new workflows
            workflow_list.set_workflows(workflows)
            await pilot.pause()

            # Index should be reset
            assert workflow_list.selected_index == 0

    @pytest.mark.asyncio
    async def test_set_workflows_with_pr_url(self) -> None:
        """Test set_workflows with PR URL."""
        async with WorkflowListTestApp().run_test() as pilot:
            workflow_list = pilot.app.query_one(WorkflowList)

            workflows = [
                {
                    "branch_name": "feature/test",
                    "workflow_type": "fly",
                    "status": "completed",
                    "started_at": datetime.now(),
                    "pr_url": "https://github.com/org/repo/pull/123",
                }
            ]
            workflow_list.set_workflows(workflows)

            assert workflow_list._workflows[0]["pr_url"] == (
                "https://github.com/org/repo/pull/123"
            )


# =============================================================================
# Selection Tests
# =============================================================================


class TestWorkflowListSelection:
    """Tests for WorkflowList selection functionality."""

    @pytest.mark.asyncio
    async def test_select_valid_index(self) -> None:
        """Test select with valid index."""
        async with WorkflowListTestApp().run_test() as pilot:
            workflow_list = pilot.app.query_one(WorkflowList)

            workflows = [
                {
                    "branch_name": f"feature/test{i}",
                    "workflow_type": "fly",
                    "status": "completed",
                    "started_at": datetime.now(),
                }
                for i in range(3)
            ]
            workflow_list.set_workflows(workflows)
            await pilot.pause()

            # Select index 1
            workflow_list.select(1)
            await pilot.pause()

            assert workflow_list.selected_index == 1

            # Check message was posted
            assert len(pilot.app.messages) == 1
            message = pilot.app.messages[0]
            assert isinstance(message, WorkflowList.WorkflowSelected)
            assert message.index == 1
            assert message.workflow == workflows[1]

    @pytest.mark.asyncio
    async def test_select_out_of_range_index(self) -> None:
        """Test select with out of range index does nothing."""
        async with WorkflowListTestApp().run_test() as pilot:
            workflow_list = pilot.app.query_one(WorkflowList)

            workflows = [
                {
                    "branch_name": "feature/test",
                    "workflow_type": "fly",
                    "status": "completed",
                    "started_at": datetime.now(),
                }
            ]
            workflow_list.set_workflows(workflows)

            # Try to select out of range
            workflow_list.select(5)

            # Selection should not change
            assert workflow_list.selected_index == 0

            # No message should be posted
            assert len(pilot.app.messages) == 0

    @pytest.mark.asyncio
    async def test_select_negative_index(self) -> None:
        """Test select with negative index does nothing."""
        async with WorkflowListTestApp().run_test() as pilot:
            workflow_list = pilot.app.query_one(WorkflowList)

            workflows = [
                {
                    "branch_name": "feature/test",
                    "workflow_type": "fly",
                    "status": "completed",
                    "started_at": datetime.now(),
                }
            ]
            workflow_list.set_workflows(workflows)

            # Try to select negative index
            workflow_list.select(-1)

            # Selection should not change
            assert workflow_list.selected_index == 0

            # No message should be posted
            assert len(pilot.app.messages) == 0

    @pytest.mark.asyncio
    async def test_watch_selected_index_updates_selection(self) -> None:
        """Test watch_selected_index updates visual selection."""
        async with WorkflowListTestApp().run_test() as pilot:
            workflow_list = pilot.app.query_one(WorkflowList)

            workflows = [
                {
                    "branch_name": f"feature/test{i}",
                    "workflow_type": "fly",
                    "status": "completed",
                    "started_at": datetime.now(),
                }
                for i in range(3)
            ]
            workflow_list.set_workflows(workflows)

            # Initially item 0 is selected
            item_0 = workflow_list.query_one(".workflow-item-0", Static)
            assert item_0.has_class("--selected")

            # Change selected_index
            workflow_list.selected_index = 1
            await pilot.pause()

            # Item 0 should no longer be selected
            assert not item_0.has_class("--selected")

            # Item 1 should be selected
            item_1 = workflow_list.query_one(".workflow-item-1", Static)
            assert item_1.has_class("--selected")


# =============================================================================
# WorkflowSelected Message Tests
# =============================================================================


class TestWorkflowSelectedMessage:
    """Tests for WorkflowSelected message."""

    def test_message_initialization(self) -> None:
        """Test WorkflowSelected message initialization."""
        workflow = {
            "branch_name": "feature/test",
            "workflow_type": "fly",
            "status": "completed",
            "started_at": datetime.now(),
        }
        message = WorkflowList.WorkflowSelected(index=2, workflow=workflow)

        assert message.index == 2
        assert message.workflow == workflow

    @pytest.mark.asyncio
    async def test_message_posted_on_select(self) -> None:
        """Test WorkflowSelected message is posted on select."""
        async with WorkflowListTestApp().run_test() as pilot:
            workflow_list = pilot.app.query_one(WorkflowList)

            workflows = [
                {
                    "branch_name": "feature/test",
                    "workflow_type": "fly",
                    "status": "completed",
                    "started_at": datetime.now(),
                }
            ]
            workflow_list.set_workflows(workflows)
            await pilot.pause()

            # Select workflow
            workflow_list.select(0)
            await pilot.pause()

            # Check message was posted
            assert len(pilot.app.messages) == 1
            message = pilot.app.messages[0]
            assert message.index == 0
            assert message.workflow == workflows[0]


# =============================================================================
# Status Display Tests
# =============================================================================


class TestWorkflowListStatusDisplay:
    """Tests for workflow status display."""

    @pytest.mark.asyncio
    async def test_get_status_display_completed(self) -> None:
        """Test _get_status_display for completed status."""
        async with WorkflowListTestApp().run_test() as pilot:
            workflow_list = pilot.app.query_one(WorkflowList)

            status_display = workflow_list._get_status_display("completed")
            assert status_display == "[green]✓[/green]"

    @pytest.mark.asyncio
    async def test_get_status_display_failed(self) -> None:
        """Test _get_status_display for failed status."""
        async with WorkflowListTestApp().run_test() as pilot:
            workflow_list = pilot.app.query_one(WorkflowList)

            status_display = workflow_list._get_status_display("failed")
            assert status_display == "[red]✗[/red]"

    @pytest.mark.asyncio
    async def test_get_status_display_in_progress(self) -> None:
        """Test _get_status_display for in_progress status."""
        async with WorkflowListTestApp().run_test() as pilot:
            workflow_list = pilot.app.query_one(WorkflowList)

            status_display = workflow_list._get_status_display("in_progress")
            assert status_display == "[yellow]◉[/yellow]"

    @pytest.mark.asyncio
    async def test_get_status_display_unknown(self) -> None:
        """Test _get_status_display for unknown status."""
        async with WorkflowListTestApp().run_test() as pilot:
            workflow_list = pilot.app.query_one(WorkflowList)

            status_display = workflow_list._get_status_display("unknown")
            assert status_display == "[dim]○[/dim]"


# =============================================================================
# Action Tests
# =============================================================================


class TestWorkflowListActions:
    """Tests for WorkflowList actions."""

    @pytest.mark.asyncio
    async def test_action_select_next(self) -> None:
        """Test action_select_next moves selection down."""
        async with WorkflowListTestApp().run_test() as pilot:
            workflow_list = pilot.app.query_one(WorkflowList)

            workflows = [
                {
                    "branch_name": f"feature/test{i}",
                    "workflow_type": "fly",
                    "status": "completed",
                    "started_at": datetime.now(),
                }
                for i in range(3)
            ]
            workflow_list.set_workflows(workflows)

            # Start at 0
            assert workflow_list.selected_index == 0

            # Move to next
            workflow_list.action_select_next()
            assert workflow_list.selected_index == 1

            # Move to next again
            workflow_list.action_select_next()
            assert workflow_list.selected_index == 2

    @pytest.mark.asyncio
    async def test_action_select_next_at_end(self) -> None:
        """Test action_select_next at end stays at end."""
        async with WorkflowListTestApp().run_test() as pilot:
            workflow_list = pilot.app.query_one(WorkflowList)

            workflows = [
                {
                    "branch_name": f"feature/test{i}",
                    "workflow_type": "fly",
                    "status": "completed",
                    "started_at": datetime.now(),
                }
                for i in range(3)
            ]
            workflow_list.set_workflows(workflows)

            # Move to end
            workflow_list.selected_index = 2

            # Try to move next
            workflow_list.action_select_next()

            # Should stay at 2
            assert workflow_list.selected_index == 2

    @pytest.mark.asyncio
    async def test_action_select_previous(self) -> None:
        """Test action_select_previous moves selection up."""
        async with WorkflowListTestApp().run_test() as pilot:
            workflow_list = pilot.app.query_one(WorkflowList)

            workflows = [
                {
                    "branch_name": f"feature/test{i}",
                    "workflow_type": "fly",
                    "status": "completed",
                    "started_at": datetime.now(),
                }
                for i in range(3)
            ]
            workflow_list.set_workflows(workflows)

            # Start at end
            workflow_list.selected_index = 2

            # Move to previous
            workflow_list.action_select_previous()
            assert workflow_list.selected_index == 1

            # Move to previous again
            workflow_list.action_select_previous()
            assert workflow_list.selected_index == 0

    @pytest.mark.asyncio
    async def test_action_select_previous_at_start(self) -> None:
        """Test action_select_previous at start stays at start."""
        async with WorkflowListTestApp().run_test() as pilot:
            workflow_list = pilot.app.query_one(WorkflowList)

            workflows = [
                {
                    "branch_name": f"feature/test{i}",
                    "workflow_type": "fly",
                    "status": "completed",
                    "started_at": datetime.now(),
                }
                for i in range(3)
            ]
            workflow_list.set_workflows(workflows)

            # Start at 0
            assert workflow_list.selected_index == 0

            # Try to move previous
            workflow_list.action_select_previous()

            # Should stay at 0
            assert workflow_list.selected_index == 0

    @pytest.mark.asyncio
    async def test_action_confirm_selection(self) -> None:
        """Test action_confirm_selection posts message."""
        async with WorkflowListTestApp().run_test() as pilot:
            workflow_list = pilot.app.query_one(WorkflowList)

            workflows = [
                {
                    "branch_name": "feature/test",
                    "workflow_type": "fly",
                    "status": "completed",
                    "started_at": datetime.now(),
                }
            ]
            workflow_list.set_workflows(workflows)
            await pilot.pause()

            # Confirm selection
            workflow_list.action_confirm_selection()
            await pilot.pause()

            # Check message was posted
            assert len(pilot.app.messages) == 1
            message = pilot.app.messages[0]
            assert message.index == 0
            assert message.workflow == workflows[0]

    @pytest.mark.asyncio
    async def test_actions_with_empty_workflows(self) -> None:
        """Test actions with empty workflows list."""
        async with WorkflowListTestApp().run_test() as pilot:
            workflow_list = pilot.app.query_one(WorkflowList)

            # No workflows
            workflow_list.set_workflows([])
            await pilot.pause()

            # Actions should not crash
            workflow_list.action_select_next()
            workflow_list.action_select_previous()
            workflow_list.action_confirm_selection()
            await pilot.pause()

            # No messages should be posted
            assert len(pilot.app.messages) == 0


# =============================================================================
# Integration Tests
# =============================================================================


class TestWorkflowListIntegration:
    """Integration tests for WorkflowList."""

    @pytest.mark.asyncio
    async def test_typical_usage_flow(self) -> None:
        """Test typical usage flow of WorkflowList."""
        async with WorkflowListTestApp().run_test() as pilot:
            workflow_list = pilot.app.query_one(WorkflowList)

            # Start with no workflows
            assert len(workflow_list._workflows) == 0

            # Add workflows
            workflows = [
                {
                    "branch_name": "feature/auth",
                    "workflow_type": "fly",
                    "status": "completed",
                    "started_at": datetime(2025, 12, 16, 10, 0),
                    "pr_url": "https://github.com/org/repo/pull/1",
                },
                {
                    "branch_name": "feature/api",
                    "workflow_type": "refuel",
                    "status": "in_progress",
                    "started_at": datetime(2025, 12, 16, 11, 0),
                },
                {
                    "branch_name": "bugfix/crash",
                    "workflow_type": "fly",
                    "status": "failed",
                    "started_at": datetime(2025, 12, 16, 12, 0),
                },
            ]
            workflow_list.set_workflows(workflows)
            await pilot.pause()

            # Navigate through list
            assert workflow_list.selected_index == 0

            workflow_list.action_select_next()
            assert workflow_list.selected_index == 1

            workflow_list.action_select_next()
            assert workflow_list.selected_index == 2

            # Can't go further
            workflow_list.action_select_next()
            assert workflow_list.selected_index == 2

            # Navigate back
            workflow_list.action_select_previous()
            assert workflow_list.selected_index == 1

            # Select current
            workflow_list.action_confirm_selection()
            await pilot.pause()

            # Check message
            assert len(pilot.app.messages) == 1
            message = pilot.app.messages[0]
            assert message.index == 1
            assert message.workflow["branch_name"] == "feature/api"

    @pytest.mark.asyncio
    async def test_workflow_display_formats(self) -> None:
        """Test different workflow display formats."""
        async with WorkflowListTestApp().run_test() as pilot:
            workflow_list = pilot.app.query_one(WorkflowList)

            workflows = [
                {
                    "branch_name": "feature/test1",
                    "workflow_type": "fly",
                    "status": "completed",
                    "started_at": datetime.now(),
                    "pr_url": "https://github.com/org/repo/pull/1",
                },
                {
                    "branch_name": "feature/test2",
                    "workflow_type": "refuel",
                    "status": "in_progress",
                    "started_at": datetime.now(),
                },
            ]
            workflow_list.set_workflows(workflows)

            # Verify items exist
            item_0 = workflow_list.query_one(".workflow-item-0", Static)
            item_1 = workflow_list.query_one(".workflow-item-1", Static)

            assert item_0 is not None
            assert item_1 is not None

    @pytest.mark.asyncio
    async def test_updating_workflows_multiple_times(self) -> None:
        """Test updating workflows multiple times."""
        async with WorkflowListTestApp().run_test() as pilot:
            workflow_list = pilot.app.query_one(WorkflowList)

            # First set
            workflows1 = [
                {
                    "branch_name": "feature/test1",
                    "workflow_type": "fly",
                    "status": "completed",
                    "started_at": datetime.now(),
                }
            ]
            workflow_list.set_workflows(workflows1)
            await pilot.pause()
            assert len(workflow_list._workflows) == 1

            # Second set
            workflows2 = [
                {
                    "branch_name": "feature/test2",
                    "workflow_type": "refuel",
                    "status": "in_progress",
                    "started_at": datetime.now(),
                },
                {
                    "branch_name": "feature/test3",
                    "workflow_type": "fly",
                    "status": "failed",
                    "started_at": datetime.now(),
                },
            ]
            workflow_list.set_workflows(workflows2)
            await pilot.pause()
            assert len(workflow_list._workflows) == 2
            assert workflow_list.selected_index == 0

            # Third set (empty)
            workflow_list.set_workflows([])
            await pilot.pause()
            assert len(workflow_list._workflows) == 0

            # Empty message should be shown
            empty_message = workflow_list.query_one(".workflow-empty-message", Static)
            assert empty_message is not None
