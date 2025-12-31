"""Example TUI screen test demonstrating testing patterns.

This module demonstrates how to test Textual TUI screens using the utilities
provided in tests/tui/conftest.py. It shows patterns for:
1. Creating a minimal test app for a screen/widget
2. Using async with app.run_test() as pilot
3. Querying widgets and asserting on their state
4. Using test utilities from conftest.py

Note: This example demonstrates widget-level testing patterns. For full screen
testing with navigation, see the tests in tests/unit/tui/screens/.
"""

from __future__ import annotations

from collections.abc import Iterable

import pytest
from textual.widget import Widget
from textual.widgets import Static

from maverick.tui.widgets.workflow_list import WorkflowList
from tests.tui.conftest import TUITestApp, assert_has_class, assert_widget_count

# =============================================================================
# Test App
# =============================================================================


class WorkflowListTestApp(TUITestApp):
    """Test app for WorkflowList widget.

    This minimal app demonstrates the pattern of creating a test harness
    for a specific widget. The app composes the widget directly so we can
    test widget-specific behavior.
    """

    def compose(self) -> Iterable[Widget]:
        """Compose the test app with a WorkflowList widget."""
        yield Static("[bold]Test Workflow List[/bold]", id="header")
        yield WorkflowList(id="test-workflow-list")


# =============================================================================
# Basic Widget Tests
# =============================================================================


@pytest.mark.asyncio
async def test_workflow_list_renders_header() -> None:
    """Test that the test app renders the header.

    This demonstrates:
    - Creating a test app instance
    - Using async with app.run_test() as pilot
    - Querying for a widget by ID
    - Asserting on widget content
    """
    app = WorkflowListTestApp()

    async with app.run_test() as pilot:
        # Header should be present
        header = pilot.app.query_one("#header", Static)
        assert "Test Workflow List" in str(header.renderable)


@pytest.mark.asyncio
async def test_workflow_list_widget_present() -> None:
    """Test that WorkflowList widget is present.

    This demonstrates:
    - Querying for a specific widget type
    - Asserting widget exists and has correct ID
    """
    app = WorkflowListTestApp()

    async with app.run_test() as pilot:
        # WorkflowList widget should be present
        workflow_list = pilot.app.query_one(WorkflowList)
        assert workflow_list.id == "test-workflow-list"


@pytest.mark.asyncio
async def test_workflow_list_widget_count() -> None:
    """Test that the app has the expected number of widgets.

    This demonstrates:
    - Using assert_widget_count utility from conftest.py
    - Querying by widget type and CSS selectors
    """
    app = WorkflowListTestApp()

    async with app.run_test() as pilot:
        # Should have exactly 1 Static widget (header)
        assert_widget_count(pilot.app, "Static", 2)  # header + empty message

        # Should have exactly 1 WorkflowList
        assert_widget_count(pilot.app, "WorkflowList", 1)


# =============================================================================
# Widget Interaction Tests
# =============================================================================


@pytest.mark.asyncio
async def test_workflow_list_sets_workflows() -> None:
    """Test that WorkflowList can display workflows.

    This demonstrates:
    - Accessing widgets and calling methods
    - Asserting on widget state changes
    - Using await pilot.pause() for UI updates
    """
    app = WorkflowListTestApp()

    async with app.run_test() as pilot:
        workflow_list = pilot.app.query_one(WorkflowList)

        # Create sample workflows
        workflows = [
            {
                "branch_name": "feature/test-1",
                "workflow_type": "fly",
                "status": "completed",
                "started_at": "2025-12-17T10:00:00",
                "pr_url": "https://github.com/test/test/pull/1",
            },
            {
                "branch_name": "feature/test-2",
                "workflow_type": "refuel",
                "status": "failed",
                "started_at": "2025-12-17T11:00:00",
            },
        ]

        # Update workflows
        workflow_list.set_workflows(workflows)

        # WorkflowList should now show workflow items
        # Wait for UI to update
        await pilot.pause()

        # Should have 2 workflow items
        workflow_items = pilot.app.query(".workflow-item")
        assert len(workflow_items) == 2


@pytest.mark.asyncio
async def test_workflow_list_selection() -> None:
    """Test workflow selection.

    This demonstrates:
    - Simulating user interactions (selection)
    - Using assert_has_class utility from conftest.py
    - Verifying CSS classes are applied correctly
    """
    app = WorkflowListTestApp()

    async with app.run_test() as pilot:
        workflow_list = pilot.app.query_one(WorkflowList)

        # Create sample workflows
        workflows = [
            {
                "branch_name": "feature/test-1",
                "workflow_type": "fly",
                "status": "completed",
                "started_at": "2025-12-17T10:00:00",
            },
            {
                "branch_name": "feature/test-2",
                "workflow_type": "refuel",
                "status": "in_progress",
                "started_at": "2025-12-17T11:00:00",
            },
        ]

        workflow_list.set_workflows(workflows)
        await pilot.pause()

        # First item should be selected by default
        first_item = pilot.app.query_one(".workflow-item-0", Static)
        assert_has_class(first_item, "--selected")

        # Select second workflow
        workflow_list.select(1)
        await pilot.pause()

        # Second item should now be selected
        second_item = pilot.app.query_one(".workflow-item-1", Static)
        assert_has_class(second_item, "--selected")


@pytest.mark.asyncio
async def test_workflow_list_empty_state() -> None:
    """Test that WorkflowList displays empty state correctly.

    This demonstrates:
    - Testing empty/edge cases
    - Querying by CSS class
    - Asserting on message content
    """
    app = WorkflowListTestApp()

    async with app.run_test() as pilot:
        workflow_list = pilot.app.query_one(WorkflowList)

        # Set empty workflow list
        workflow_list.set_workflows([])
        await pilot.pause()

        # Should display empty message
        empty_message = pilot.app.query_one(".workflow-empty-message", Static)
        assert "No workflows available" in str(empty_message.renderable)


# =============================================================================
# Action/Binding Tests
# =============================================================================


@pytest.mark.asyncio
async def test_workflow_list_navigation_actions() -> None:
    """Test workflow list navigation actions.

    This demonstrates:
    - Testing widget actions
    - Calling action methods directly
    - Verifying state changes after actions
    """
    app = WorkflowListTestApp()

    async with app.run_test() as pilot:
        workflow_list = pilot.app.query_one(WorkflowList)

        # Set workflows
        workflows = [
            {
                "branch_name": "feature/test-1",
                "workflow_type": "fly",
                "status": "completed",
                "started_at": "2025-12-17T10:00:00",
            },
            {
                "branch_name": "feature/test-2",
                "workflow_type": "refuel",
                "status": "in_progress",
                "started_at": "2025-12-17T11:00:00",
            },
            {
                "branch_name": "feature/test-3",
                "workflow_type": "fly",
                "status": "failed",
                "started_at": "2025-12-17T12:00:00",
            },
        ]
        workflow_list.set_workflows(workflows)
        await pilot.pause()

        # Verify initial selection (should be 0)
        assert workflow_list.selected_index == 0

        # Move down
        workflow_list.action_select_next()
        await pilot.pause()
        assert workflow_list.selected_index == 1

        # Move down again
        workflow_list.action_select_next()
        await pilot.pause()
        assert workflow_list.selected_index == 2

        # Try to move beyond last item (should stay at 2)
        workflow_list.action_select_next()
        await pilot.pause()
        assert workflow_list.selected_index == 2

        # Move up
        workflow_list.action_select_previous()
        await pilot.pause()
        assert workflow_list.selected_index == 1

        # Move up again
        workflow_list.action_select_previous()
        await pilot.pause()
        assert workflow_list.selected_index == 0

        # Try to move before first item (should stay at 0)
        workflow_list.action_select_previous()
        await pilot.pause()
        assert workflow_list.selected_index == 0


# =============================================================================
# Pattern Summary
# =============================================================================

"""
Key Testing Patterns Demonstrated:

1. Test App Creation:
   - Extend TUITestApp for widget testing
   - Extend ScreenTestApp for screen testing (with push_screen in on_mount)
   - Compose the widget/screen under test in compose() or on_mount()
   - Keep app minimal and focused on the component being tested

2. Test Structure:
   - Use @pytest.mark.asyncio for all async tests
   - Use async with app.run_test() as pilot
   - Query widgets using pilot.app.query_one() or pilot.app.query()
   - Always await pilot.pause() after state changes

3. Widget Queries:
   - By ID: pilot.app.query_one("#widget-id", WidgetType)
   - By CSS class: pilot.app.query(".css-class")
   - By widget type: pilot.app.query_one(WidgetType)
   - Multiple widgets: pilot.app.query(selector) returns list

4. Assertions:
   - Use assert_has_class(widget, "class-name") for CSS class checks
   - Use assert_widget_count(app, "selector", count) for counting widgets
   - Access widget.content for content checks (Static widgets)
   - Use standard Python assertions for state/property checks

5. Timing and Synchronization:
   - Use await pilot.pause() to let UI updates complete
   - This is crucial after:
     - Calling widget methods that change state
     - Triggering actions
     - Setting reactive properties
   - Without pause(), assertions may fail due to race conditions

6. Testing Best Practices:
   - Test empty states and edge cases
   - Test selection boundaries (first/last item)
   - Test widget initialization and defaults
   - Test actions and their side effects
   - Verify CSS classes are applied correctly

7. Actions and Interactions:
   - Call action_* methods directly on widget/screen
   - Use pilot.press("key") for keyboard simulation (advanced)
   - Use pilot.click(selector) for mouse simulation (advanced)
   - Verify state changes after each action

8. Common Patterns:
   - Create sample data in test or fixtures
   - Call widget methods to update state
   - await pilot.pause() to let UI render
   - Query for expected widgets/elements
   - Assert on their state/content/classes

Example Test Structure:
   ```python
   @pytest.mark.asyncio
   async def test_widget_behavior() -> None:
       app = MyWidgetTestApp()

       async with app.run_test() as pilot:
           # Get widget under test
           widget = pilot.app.query_one(MyWidget)

           # Change state
           widget.set_data(sample_data)
           await pilot.pause()

           # Assert on results
           assert widget.some_property == expected_value
           assert_has_class(widget, "expected-class")
   ```

For full integration tests with screen navigation, mocking, and complex
interactions, see the tests in tests/unit/tui/screens/ and
tests/unit/tui/widgets/.
"""
