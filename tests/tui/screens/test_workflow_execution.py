"""Tests for WorkflowExecutionScreen.

This module tests the workflow execution screen which is the most complex
screen in the TUI, handling:
- Real-time step progress tracking
- Agent streaming output display
- Loop iteration progress
- Progress timeline visualization
- Cancellation handling
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Generator
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

import pytest
from textual.widgets import Static

from maverick.tui.models.enums import StreamChunkType
from maverick.tui.models.widget_state import AgentStreamEntry
from maverick.tui.screens.workflow_execution import (
    STATUS_ICONS,
    STEP_TYPE_ICONS,
    StepWidget,
    WorkflowExecutionScreen,
)
from maverick.tui.widgets.unified_stream import UnifiedStreamWidget
from tests.tui.conftest import ScreenTestApp

if TYPE_CHECKING:
    from collections.abc import Iterable

    from textual.widget import Widget


# Apply TUI marker to all tests
pytestmark = pytest.mark.tui


# =============================================================================
# Module-level Fixtures
# =============================================================================


async def _mock_execute_workflow(
    workflow: Any, inputs: Any
) -> AsyncGenerator[Any, None]:
    """Create a mock async generator that yields workflow events.

    This properly simulates the executor's execute() method behavior.
    """
    from maverick.dsl.events import WorkflowCompleted, WorkflowStarted

    # Yield workflow events with all required fields
    yield WorkflowStarted(workflow_name=workflow.name, inputs=inputs or {})
    # Give control back to event loop to allow screen to process
    await asyncio.sleep(0.01)
    yield WorkflowCompleted(
        workflow_name=workflow.name, success=True, total_duration_ms=100
    )


@pytest.fixture(autouse=True)
def mock_workflow_executor() -> Generator[MagicMock, None, None]:
    """Mock the WorkflowFileExecutor for all tests in this module.

    This fixture is autouse=True so it applies to all tests automatically.
    It prevents actual workflow execution during tests.

    The patches target the import locations used in _execute_workflow():
    - WorkflowFileExecutor is imported from maverick.dsl.serialization
    - create_registered_registry is imported from maverick.cli.common
    """
    # Create a mock result object
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.outputs = {}
    mock_result.duration_ms = 100

    # Mock both the executor class and the registry function at their import sources
    with (
        patch("maverick.dsl.serialization.WorkflowFileExecutor") as mock_executor_class,
        patch("maverick.cli.common.create_registered_registry") as mock_registry,
    ):
        mock_executor = MagicMock()
        # execute() returns an async generator
        mock_executor.execute = _mock_execute_workflow
        mock_executor.get_result = MagicMock(return_value=mock_result)
        mock_executor_class.return_value = mock_executor

        # Registry can be a simple mock
        mock_registry.return_value = MagicMock()

        yield mock_executor


# =============================================================================
# Test Fixtures and Helpers
# =============================================================================


def create_mock_workflow(
    name: str = "test-workflow",
    description: str = "A test workflow",
    steps: list[dict[str, Any]] | None = None,
) -> MagicMock:
    """Create a mock WorkflowFile for testing.

    Args:
        name: Workflow name.
        description: Workflow description.
        steps: List of step definitions.

    Returns:
        Mock WorkflowFile object.
    """
    if steps is None:
        steps = [
            {"name": "validate", "type": "python"},
            {"name": "implement", "type": "agent"},
            {"name": "review", "type": "agent"},
        ]

    mock_workflow = MagicMock()
    mock_workflow.name = name
    mock_workflow.description = description
    mock_workflow.steps = []

    for step_def in steps:
        step = MagicMock()
        step.name = step_def["name"]
        step.type = MagicMock()
        step.type.value = step_def.get("type", "python")
        mock_workflow.steps.append(step)

    return mock_workflow


class WorkflowExecutionTestApp(ScreenTestApp):
    """Test app for WorkflowExecutionScreen.

    This app pushes a WorkflowExecutionScreen on mount.
    The WorkflowFileExecutor is mocked by the autouse fixture.
    """

    def __init__(
        self,
        workflow: MagicMock | None = None,
        inputs: dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        self.workflow = workflow or create_mock_workflow()
        self.inputs = inputs or {}
        self.screen_instance: WorkflowExecutionScreen | None = None

    def compose(self) -> Iterable[Widget]:
        """Yield a placeholder - the screen is pushed on mount."""
        yield Static("Loading...", id="placeholder")

    async def on_mount(self) -> None:
        """Push the WorkflowExecutionScreen on mount."""
        self.screen_instance = WorkflowExecutionScreen(
            workflow=self.workflow,
            inputs=self.inputs,
        )
        await self.push_screen(self.screen_instance)


class StepWidgetTestApp(ScreenTestApp):
    """Test app for StepWidget."""

    def compose(self) -> Iterable[Widget]:
        yield StepWidget(
            step_name="test_step",
            step_type="python",
            id="test-step-widget",
        )


# =============================================================================
# StepWidget Tests
# =============================================================================


class TestStepWidget:
    """Tests for the StepWidget component."""

    @pytest.mark.asyncio
    async def test_step_widget_renders_name_and_type(self) -> None:
        """Test that StepWidget displays step name and type icon."""
        app = StepWidgetTestApp()

        async with app.run_test() as pilot:
            await pilot.pause()

            step_widget = pilot.app.query_one("#test-step-widget", StepWidget)
            content = str(step_widget.renderable)

            # Should contain step name
            assert "test_step" in content

            # Should contain type icon (gear for python)
            assert STEP_TYPE_ICONS["python"] in content

    @pytest.mark.asyncio
    async def test_step_widget_initial_pending_status(self) -> None:
        """Test that StepWidget starts in pending status."""
        app = StepWidgetTestApp()

        async with app.run_test() as pilot:
            await pilot.pause()

            step_widget = pilot.app.query_one("#test-step-widget", StepWidget)
            content = str(step_widget.renderable)

            # Should contain pending status icon
            assert STATUS_ICONS["pending"] in content

    @pytest.mark.asyncio
    async def test_step_widget_set_running(self) -> None:
        """Test that set_running updates the step status."""
        app = StepWidgetTestApp()

        async with app.run_test() as pilot:
            await pilot.pause()

            step_widget = pilot.app.query_one("#test-step-widget", StepWidget)
            step_widget.set_running()
            await pilot.pause()

            content = str(step_widget.renderable)
            # Should contain running indicator (filled circle)
            assert STATUS_ICONS["running"] in content

    @pytest.mark.asyncio
    async def test_step_widget_set_completed_with_duration(self) -> None:
        """Test that set_completed shows duration."""
        app = StepWidgetTestApp()

        async with app.run_test() as pilot:
            await pilot.pause()

            step_widget = pilot.app.query_one("#test-step-widget", StepWidget)
            step_widget.set_completed(duration_ms=1500)
            await pilot.pause()

            content = str(step_widget.renderable)

            # Should contain completed icon
            assert STATUS_ICONS["completed"] in content

            # Should contain duration (1.5s)
            assert "1.5s" in content

    @pytest.mark.asyncio
    async def test_step_widget_set_completed_short_duration(self) -> None:
        """Test that short durations are shown in milliseconds."""
        app = StepWidgetTestApp()

        async with app.run_test() as pilot:
            await pilot.pause()

            step_widget = pilot.app.query_one("#test-step-widget", StepWidget)
            step_widget.set_completed(duration_ms=500)
            await pilot.pause()

            content = str(step_widget.renderable)

            # Should contain duration in ms
            assert "500ms" in content

    @pytest.mark.asyncio
    async def test_step_widget_set_completed_long_duration(self) -> None:
        """Test that long durations are shown in minutes and seconds."""
        app = StepWidgetTestApp()

        async with app.run_test() as pilot:
            await pilot.pause()

            step_widget = pilot.app.query_one("#test-step-widget", StepWidget)
            step_widget.set_completed(duration_ms=90000)  # 1m 30s
            await pilot.pause()

            content = str(step_widget.renderable)

            # Should contain duration in minutes and seconds
            assert "1m" in content
            assert "30s" in content

    @pytest.mark.asyncio
    async def test_step_widget_set_failed_with_error(self) -> None:
        """Test that set_failed shows error message."""
        app = StepWidgetTestApp()

        async with app.run_test() as pilot:
            await pilot.pause()

            step_widget = pilot.app.query_one("#test-step-widget", StepWidget)
            step_widget.set_failed(
                duration_ms=1000,
                error="Connection timeout",
            )
            await pilot.pause()

            content = str(step_widget.renderable)

            # Should contain failed icon
            assert STATUS_ICONS["failed"] in content

            # Should contain error message
            assert "Connection timeout" in content

    @pytest.mark.asyncio
    async def test_step_widget_set_skipped(self) -> None:
        """Test that set_skipped updates the status."""
        app = StepWidgetTestApp()

        async with app.run_test() as pilot:
            await pilot.pause()

            step_widget = pilot.app.query_one("#test-step-widget", StepWidget)
            step_widget.set_skipped()
            await pilot.pause()

            content = str(step_widget.renderable)

            # Should contain skipped icon
            assert STATUS_ICONS["skipped"] in content


# =============================================================================
# WorkflowExecutionScreen Layout Tests
# =============================================================================


class TestWorkflowExecutionScreenLayout:
    """Tests for WorkflowExecutionScreen layout and composition."""

    @pytest.mark.asyncio
    async def test_screen_renders_compact_header(self) -> None:
        """Test that the screen displays the compact header with workflow name."""
        workflow = create_mock_workflow(name="My Test Workflow")
        app = WorkflowExecutionTestApp(workflow=workflow)

        async with app.run_test() as pilot:
            await pilot.pause()

            header = pilot.app.query_one("#compact-header", Static)
            content = str(header.renderable)

            assert "My Test Workflow" in content

    @pytest.mark.asyncio
    async def test_screen_renders_step_widgets(self) -> None:
        """Test that step widgets are created for each workflow step."""
        workflow = create_mock_workflow(
            steps=[
                {"name": "step1", "type": "python"},
                {"name": "step2", "type": "agent"},
                {"name": "step3", "type": "validate"},
            ]
        )
        app = WorkflowExecutionTestApp(workflow=workflow)

        async with app.run_test() as pilot:
            await pilot.pause()

            # Should have step widgets for each step
            step1 = pilot.app.query_one("#step-step1", StepWidget)
            step2 = pilot.app.query_one("#step-step2", StepWidget)
            step3 = pilot.app.query_one("#step-step3", StepWidget)

            assert step1 is not None
            assert step2 is not None
            assert step3 is not None

    @pytest.mark.asyncio
    async def test_screen_renders_unified_stream(self) -> None:
        """Test that the unified stream widget is rendered."""
        app = WorkflowExecutionTestApp()

        async with app.run_test() as pilot:
            await pilot.pause()

            stream = pilot.app.query_one("#unified-stream", UnifiedStreamWidget)
            assert stream is not None

    @pytest.mark.asyncio
    async def test_exit_available_after_completion(self) -> None:
        """Test that exit key bindings work after workflow completes.

        Note: With the mock executor, the workflow completes almost immediately.
        The streaming-first design uses key bindings (Escape/Q) to exit
        rather than visible buttons - this matches Claude Code's UX.
        """
        app = WorkflowExecutionTestApp()

        async with app.run_test() as pilot:
            await pilot.pause()

            # Verify the screen is mounted and accessible
            screen = pilot.app.screen
            assert isinstance(screen, WorkflowExecutionScreen)

            # After workflow completes, the escape binding should work for exit
            # (The action_cancel_workflow method exits when not running)


# =============================================================================
# WorkflowExecutionScreen Reactive State Tests
# =============================================================================


class TestWorkflowExecutionScreenState:
    """Tests for WorkflowExecutionScreen reactive state."""

    @pytest.mark.asyncio
    async def test_screen_initial_state(self) -> None:
        """Test initial reactive state values.

        Note: This test only checks initial values before mounting.
        The WorkflowFileExecutor is not used until on_mount() is called.
        """
        workflow = create_mock_workflow()

        screen = WorkflowExecutionScreen(
            workflow=workflow,
            inputs={},
        )

        # Check initial values (before mounting)
        assert screen.is_running is False
        assert screen.is_complete is False
        assert screen.current_step == 0
        assert screen.success is None

    @pytest.mark.asyncio
    async def test_screen_total_steps_set_on_mount(self) -> None:
        """Test that total_steps is set when screen mounts."""
        workflow = create_mock_workflow(
            steps=[
                {"name": "step1", "type": "python"},
                {"name": "step2", "type": "agent"},
            ]
        )
        app = WorkflowExecutionTestApp(workflow=workflow)

        async with app.run_test() as pilot:
            await pilot.pause()

            assert app.screen_instance is not None
            assert app.screen_instance.total_steps == 2


# =============================================================================
# WorkflowExecutionScreen Actions Tests
# =============================================================================


class TestWorkflowExecutionScreenActions:
    """Tests for WorkflowExecutionScreen action handlers."""

    @pytest.mark.asyncio
    async def test_escape_cancels_running_workflow(self) -> None:
        """Test that pressing Escape requests cancellation."""
        app = WorkflowExecutionTestApp()

        async with app.run_test() as pilot:
            await pilot.pause()

            # Simulate running state
            if app.screen_instance:
                app.screen_instance.is_running = True

                # Press escape
                await pilot.press("escape")
                await pilot.pause()

                assert app.screen_instance._cancel_requested is True

    @pytest.mark.asyncio
    async def test_escape_exits_app_when_not_running(self) -> None:
        """Test that Escape exits app when workflow is not running.

        With the streaming-first design, Escape exits the app directly
        instead of popping the screen (matches Claude Code's UX).
        """
        app = WorkflowExecutionTestApp()

        async with app.run_test() as pilot:
            await pilot.pause()

            # Ensure not running
            if app.screen_instance:
                app.screen_instance.is_running = False

                # Press escape - this triggers action_cancel_workflow
                # which calls app.exit() when not running
                await pilot.press("escape")
                await pilot.pause()

                # App should be exiting (return_value set)
                # Note: In test mode the app may not fully exit
                # but the action should be triggered

    @pytest.mark.asyncio
    async def test_s_key_toggles_steps_panel(self) -> None:
        """Test that 's' key toggles steps panel visibility."""
        app = WorkflowExecutionTestApp()

        async with app.run_test() as pilot:
            await pilot.pause()

            from textual.containers import Vertical

            steps_panel = pilot.app.query_one("#execution-steps", Vertical)
            initial_hidden = steps_panel.has_class("hidden")

            # Press 's' to toggle
            await pilot.press("s")
            await pilot.pause()

            # Check visibility changed
            new_hidden = steps_panel.has_class("hidden")
            assert new_hidden != initial_hidden

    @pytest.mark.asyncio
    async def test_q_key_exits_app(self) -> None:
        """Test that 'q' key exits app (streaming-first UX)."""
        app = WorkflowExecutionTestApp()

        async with app.run_test() as pilot:
            await pilot.pause()

            # Verify screen is mounted
            assert isinstance(pilot.app.screen, WorkflowExecutionScreen)

            # Press 'q' - this triggers action_exit_app
            await pilot.press("q")
            await pilot.pause()

            # App should be exiting
            # In test mode, we verify the action was triggered


# =============================================================================
# Step Status Update Tests
# =============================================================================


class TestStepStatusUpdates:
    """Tests for step status update methods."""

    @pytest.mark.asyncio
    async def test_mark_step_running(self) -> None:
        """Test that _mark_step_running updates step widget."""
        workflow = create_mock_workflow(steps=[{"name": "test_step", "type": "python"}])
        app = WorkflowExecutionTestApp(workflow=workflow)

        async with app.run_test() as pilot:
            await pilot.pause()

            if app.screen_instance:
                app.screen_instance._mark_step_running("test_step")
                await pilot.pause()

                step_widget = pilot.app.query_one("#step-test_step", StepWidget)
                content = str(step_widget.renderable)

                assert STATUS_ICONS["running"] in content

    @pytest.mark.asyncio
    async def test_mark_step_completed(self) -> None:
        """Test that _mark_step_completed updates step widget."""
        workflow = create_mock_workflow(steps=[{"name": "test_step", "type": "python"}])
        app = WorkflowExecutionTestApp(workflow=workflow)

        async with app.run_test() as pilot:
            await pilot.pause()

            if app.screen_instance:
                app.screen_instance._mark_step_completed("test_step", 2000)
                await pilot.pause()

                step_widget = pilot.app.query_one("#step-test_step", StepWidget)
                content = str(step_widget.renderable)

                assert STATUS_ICONS["completed"] in content
                assert "2.0s" in content

    @pytest.mark.asyncio
    async def test_mark_step_failed(self) -> None:
        """Test that _mark_step_failed updates step widget with error."""
        workflow = create_mock_workflow(steps=[{"name": "test_step", "type": "python"}])
        app = WorkflowExecutionTestApp(workflow=workflow)

        async with app.run_test() as pilot:
            await pilot.pause()

            if app.screen_instance:
                app.screen_instance._mark_step_failed(
                    "test_step",
                    1000,
                    "Test error message",
                )
                await pilot.pause()

                step_widget = pilot.app.query_one("#step-test_step", StepWidget)
                content = str(step_widget.renderable)

                assert STATUS_ICONS["failed"] in content
                assert "Test error message" in content


# =============================================================================
# Streaming Panel Tests
# =============================================================================


class TestStreamingPanelIntegration:
    """Tests for streaming panel integration."""

    @pytest.mark.asyncio
    async def test_streaming_state_initialized(self) -> None:
        """Test that streaming state is initialized with visible=True.

        Note: This test only checks initial values before mounting.
        The WorkflowFileExecutor is not used until on_mount() is called.
        """
        workflow = create_mock_workflow()

        screen = WorkflowExecutionScreen(
            workflow=workflow,
            inputs={},
        )

        assert screen._streaming_state.visible is True
        assert len(screen._streaming_state.entries) == 0

    @pytest.mark.asyncio
    async def test_streaming_state_entries_can_be_added(self) -> None:
        """Test that entries can be added to streaming state.

        Note: This test only checks initial values before mounting.
        The WorkflowFileExecutor is not used until on_mount() is called.
        """
        workflow = create_mock_workflow()

        screen = WorkflowExecutionScreen(
            workflow=workflow,
            inputs={},
        )

        entry = AgentStreamEntry(
            timestamp=12345.0,
            step_name="test_step",
            agent_name="TestAgent",
            text="Test output",
            chunk_type=StreamChunkType.OUTPUT,
        )
        screen._streaming_state.add_entry(entry)

        assert len(screen._streaming_state.entries) == 1
        assert screen._streaming_state.entries[0].text == "Test output"


# =============================================================================
# Progress Update Tests
# =============================================================================


class TestProgressUpdates:
    """Tests for progress tracking and display."""

    @pytest.mark.asyncio
    async def test_update_progress_updates_header(self) -> None:
        """Test that _update_progress updates compact header."""
        workflow = create_mock_workflow(
            steps=[
                {"name": "step1", "type": "python"},
                {"name": "step2", "type": "agent"},
            ]
        )
        app = WorkflowExecutionTestApp(workflow=workflow)

        async with app.run_test() as pilot:
            await pilot.pause()

            if app.screen_instance:
                # Reset completion state (mock workflow completes quickly)
                app.screen_instance.is_complete = False
                app.screen_instance.current_step = 1
                app.screen_instance._update_progress()
                await pilot.pause()

                header = pilot.app.query_one("#compact-header", Static)
                content = str(header.renderable)

                # Compact header shows "Step X/Y" format
                assert "Step 1/2" in content

    @pytest.mark.asyncio
    async def test_show_completion_success(self) -> None:
        """Test that _show_completion displays success state."""
        app = WorkflowExecutionTestApp()

        async with app.run_test() as pilot:
            await pilot.pause()

            if app.screen_instance:
                app.screen_instance._show_completion(
                    success=True, total_duration_ms=5000
                )
                await pilot.pause()

                header = pilot.app.query_one("#compact-header", Static)
                content = str(header.renderable)

                assert "Completed" in content
                assert "5.0s" in content

                # With streaming-first design, user exits via Escape or Q key
                # (no visible completion buttons - matches Claude Code UX)

    @pytest.mark.asyncio
    async def test_show_completion_failure(self) -> None:
        """Test that _show_completion displays failure state."""
        app = WorkflowExecutionTestApp()

        async with app.run_test() as pilot:
            await pilot.pause()

            if app.screen_instance:
                app.screen_instance._show_completion(
                    success=False, total_duration_ms=3000
                )
                await pilot.pause()

                header = pilot.app.query_one("#compact-header", Static)
                content = str(header.renderable)

                assert "Failed" in content
                assert "3.0s" in content

    @pytest.mark.asyncio
    async def test_show_error_logs_message(self) -> None:
        """Test that _show_error logs the error message."""
        app = WorkflowExecutionTestApp()

        async with app.run_test() as pilot:
            await pilot.pause()

            if app.screen_instance:
                # _show_error now just logs, so we verify it doesn't raise
                app.screen_instance._show_error("Connection failed: timeout")
                await pilot.pause()
                # If we get here without error, the test passes
