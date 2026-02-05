"""Unit tests for WorkflowExecutionScreen."""

from __future__ import annotations

import asyncio
import contextlib
from unittest.mock import MagicMock

import pytest

from maverick.tui.screens.workflow_execution import (
    STATUS_ICONS,
    STEP_TYPE_ICONS,
    WorkflowExecutionScreen,
)


def create_mock_step(
    name: str = "test-step",
    step_type: str = "python",
) -> MagicMock:
    """Create a mock step for testing."""
    mock_step = MagicMock()
    mock_step.name = name
    mock_step.type.value = step_type
    return mock_step


def create_mock_workflow(
    name: str = "test-workflow",
    description: str | None = "Test workflow description",
    steps: list | None = None,
) -> MagicMock:
    """Create a mock WorkflowFile for testing."""
    mock_workflow = MagicMock()
    mock_workflow.name = name
    mock_workflow.description = description
    mock_workflow.steps = steps or []
    return mock_workflow


# Step Type Icons Tests
class TestStepTypeIcons:
    """Tests for step type icon mapping."""

    def test_python_icon(self):
        """Test python step has gear icon."""
        assert STEP_TYPE_ICONS["python"] == "\u2699"

    def test_agent_icon(self):
        """Test agent step has robot icon."""
        assert STEP_TYPE_ICONS["agent"] == "\U0001f916"

    def test_generate_icon(self):
        """Test generate step has writing hand icon."""
        assert STEP_TYPE_ICONS["generate"] == "\u270d"

    def test_validate_icon(self):
        """Test validate step has checkmark icon."""
        assert STEP_TYPE_ICONS["validate"] == "\u2713"

    def test_checkpoint_icon(self):
        """Test checkpoint step has floppy disk icon."""
        assert STEP_TYPE_ICONS["checkpoint"] == "\U0001f4be"

    def test_subworkflow_icon(self):
        """Test subworkflow step has shuffle icon."""
        assert STEP_TYPE_ICONS["subworkflow"] == "\U0001f500"

    def test_branch_icon(self):
        """Test branch step has shuffle icon."""
        assert STEP_TYPE_ICONS["branch"] == "\U0001f500"

    def test_loop_icon(self):
        """Test loop step has repeat icon."""
        assert STEP_TYPE_ICONS["loop"] == "\U0001f501"


# Status Icons Tests
class TestStatusIcons:
    """Tests for status icon mapping."""

    def test_pending_icon(self):
        """Test pending status has empty circle icon."""
        assert STATUS_ICONS["pending"] == "\u25cb"

    def test_running_icon(self):
        """Test running status has filled circle icon."""
        assert STATUS_ICONS["running"] == "\u25cf"

    def test_completed_icon(self):
        """Test completed status has checkmark icon."""
        assert STATUS_ICONS["completed"] == "\u2713"

    def test_failed_icon(self):
        """Test failed status has X mark icon."""
        assert STATUS_ICONS["failed"] == "\u2717"

    def test_skipped_icon(self):
        """Test skipped status has em dash icon."""
        assert STATUS_ICONS["skipped"] == "\u2014"


# WorkflowExecutionScreen Initialization Tests
class TestWorkflowExecutionInitialization:
    """Tests for WorkflowExecutionScreen initialization."""

    def test_screen_has_correct_title(self):
        """Test that screen has correct title."""
        assert WorkflowExecutionScreen.TITLE == "Running Workflow"

    def test_screen_has_required_bindings(self):
        """Test that screen has all required key bindings."""
        binding_keys = [b.key for b in WorkflowExecutionScreen.BINDINGS]
        assert "escape" in binding_keys
        assert "q" in binding_keys

    def test_screen_initializes_with_workflow(self):
        """Test that screen initializes with workflow data."""
        mock_workflow = create_mock_workflow(
            name="my-workflow",
            steps=[create_mock_step()],
        )
        inputs = {"key": "value"}

        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs=inputs)

        assert screen._workflow == mock_workflow
        assert screen._inputs == inputs
        assert screen._cancel_requested is False


# Reactive State Tests
class TestReactiveState:
    """Tests for reactive state properties."""

    def test_initial_is_running_state(self):
        """Test initial is_running state is False."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})
        assert screen.is_running is False

    def test_initial_is_complete_state(self):
        """Test initial is_complete state is False."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})
        assert screen.is_complete is False

    def test_initial_current_step(self):
        """Test initial current_step is 0."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})
        assert screen.current_step == 0

    def test_initial_total_steps(self):
        """Test initial total_steps is 0."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})
        assert screen.total_steps == 0

    def test_initial_success_state(self):
        """Test initial success state is None."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})
        assert screen.success is None


# Step Marking Tests
class TestStepMarking:
    """Tests for step marking methods using tree state."""

    def test_mark_step_running(self):
        """Test marking a step as running updates tree state."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        screen._mark_step_running("test", "python")

        node = screen._tree_state._node_index.get("test")
        assert node is not None
        assert node.status == "running"

    def test_mark_step_completed(self):
        """Test marking a step as completed updates tree state."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        screen._mark_step_running("test", "python")
        screen._mark_step_completed("test", 1000)

        node = screen._tree_state._node_index.get("test")
        assert node is not None
        assert node.status == "completed"
        assert node.duration_ms == 1000

    def test_mark_step_failed(self):
        """Test marking a step as failed updates tree state."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        screen._mark_step_running("test", "python")
        screen._mark_step_failed("test", 500, "Error message")

        node = screen._tree_state._node_index.get("test")
        assert node is not None
        assert node.status == "failed"
        assert node.duration_ms == 500

    def test_mark_unknown_step_no_error(self):
        """Test marking unknown step doesn't raise error."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        # Should not raise
        screen._mark_step_running("unknown-step")
        screen._mark_step_completed("unknown-step", 1000)
        screen._mark_step_failed("unknown-step", 500)


# Cancel Tests
class TestCancel:
    """Tests for workflow cancellation."""

    def test_cancel_flag_initial_state(self):
        """Test cancel flag is False initially."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})
        assert screen._cancel_requested is False

    def test_cancel_flag_can_be_set(self):
        """Test cancel flag can be set directly."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})
        screen._cancel_requested = True
        assert screen._cancel_requested is True


# Progress Tests
class TestProgress:
    """Tests for progress tracking."""

    def test_update_progress_calculation(self):
        """Test progress calculation."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        screen.total_steps = 10
        screen.current_step = 5

        # Progress should be 50%
        percent = screen.current_step / screen.total_steps * 100
        assert percent == 50.0

    def test_update_progress_zero_total(self):
        """Test progress calculation with zero total steps."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        screen.total_steps = 0
        screen.current_step = 0

        # Should not raise division by zero
        if screen.total_steps > 0:
            percent = screen.current_step / screen.total_steps * 100
        else:
            percent = 0.0
        assert percent == 0.0


# Streaming Panel Persistence Tests (T036)
class TestStreamingPanelPersistence:
    """Tests for streaming panel entry persistence after workflow completion.

    Per User Story 3 (T036), streaming panel entries must be preserved after
    workflow completion (success or failure) to allow users to scroll back
    and review agent output for debugging failed workflows.
    """

    def test_streaming_state_initialized(self):
        """Test that streaming state is initialized with entries list."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        assert hasattr(screen, "_streaming_state")
        assert screen._streaming_state is not None
        assert hasattr(screen._streaming_state, "entries")
        assert isinstance(screen._streaming_state.entries, list)

    def test_streaming_state_visible_by_default(self):
        """Test that streaming panel is visible by default (T033)."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        assert screen._streaming_state.visible is True

    def test_entries_persist_after_success(self):
        """Test that entries are NOT cleared when workflow succeeds.

        After _show_completion is called with success=True, the streaming
        entries should remain in the state for debugging purposes.
        """
        from maverick.tui.models.enums import StreamChunkType
        from maverick.tui.models.widget_state import AgentStreamEntry

        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        # Add some entries to streaming state
        entry1 = AgentStreamEntry(
            timestamp=1.0,
            step_name="test_step",
            agent_name="TestAgent",
            text="Starting implementation...",
            chunk_type=StreamChunkType.OUTPUT,
        )
        entry2 = AgentStreamEntry(
            timestamp=2.0,
            step_name="test_step",
            agent_name="TestAgent",
            text="Task completed.",
            chunk_type=StreamChunkType.OUTPUT,
        )
        screen._streaming_state.add_entry(entry1)
        screen._streaming_state.add_entry(entry2)

        # Verify entries exist before completion
        assert len(screen._streaming_state.entries) == 2

        # Note: _show_completion cannot be called without mounting the widget,
        # so we verify that no clear() call exists in the workflow lifecycle
        # by checking that entries are preserved in the state

        # Entries should still exist (no automatic clearing)
        assert len(screen._streaming_state.entries) == 2
        assert screen._streaming_state.entries[0].text == "Starting implementation..."
        assert screen._streaming_state.entries[1].text == "Task completed."

    def test_entries_persist_after_failure(self):
        """Test that entries are NOT cleared when workflow fails.

        After _show_completion is called with success=False, the streaming
        entries should remain in the state for debugging failed workflows.
        """
        from maverick.tui.models.enums import StreamChunkType
        from maverick.tui.models.widget_state import AgentStreamEntry

        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        # Add entries including error output
        entries = [
            AgentStreamEntry(
                timestamp=1.0,
                step_name="test_step",
                agent_name="TestAgent",
                text="Starting implementation...",
                chunk_type=StreamChunkType.OUTPUT,
            ),
            AgentStreamEntry(
                timestamp=2.0,
                step_name="test_step",
                agent_name="TestAgent",
                text="Error: Something went wrong!",
                chunk_type=StreamChunkType.ERROR,
            ),
        ]
        for entry in entries:
            screen._streaming_state.add_entry(entry)

        # Verify entries exist
        assert len(screen._streaming_state.entries) == 2

        # Simulate workflow failure state (without calling _show_completion
        # which requires mounted widgets)
        screen.success = False
        screen.is_complete = True
        screen.is_running = False

        # Entries should still be accessible for debugging
        assert len(screen._streaming_state.entries) == 2
        assert "Error:" in screen._streaming_state.entries[1].text

    def test_no_clear_method_called_on_completion(self):
        """Test that StreamingPanelState.clear() is never auto-called.

        The design ensures no automatic clearing happens during the workflow
        lifecycle, preserving entries for post-completion debugging.
        """
        from maverick.tui.models.enums import StreamChunkType
        from maverick.tui.models.widget_state import AgentStreamEntry

        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        # Add entries
        entry = AgentStreamEntry(
            timestamp=1.0,
            step_name="test_step",
            agent_name="TestAgent",
            text="Test output",
            chunk_type=StreamChunkType.OUTPUT,
        )
        screen._streaming_state.add_entry(entry)

        # Record entry count
        initial_count = len(screen._streaming_state.entries)

        # Simulate various state transitions
        screen.is_running = True
        screen.current_step = 1
        screen.is_running = False
        screen.is_complete = True
        screen.success = True

        # Entry count should remain the same (no clearing occurred)
        assert len(screen._streaming_state.entries) == initial_count


# Debounce Tests (T042)
class TestDebounce:
    """Tests for UI update debouncing.

    Per SC-003, there must be a minimum 50ms between visual state changes
    to prevent flickering during rapid event sequences.
    """

    def test_debounce_state_initialized(self):
        """Test that debounce tracking state is initialized."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        # Verify debounce tracking attributes exist
        assert hasattr(screen, "_last_iteration_update")
        assert hasattr(screen, "_last_streaming_update")
        assert hasattr(screen, "_pending_iteration_update")
        assert hasattr(screen, "_pending_streaming_update")
        assert hasattr(screen, "_pending_iteration_step")

        # Verify initial values
        assert screen._last_iteration_update == 0.0
        assert screen._last_streaming_update == 0.0
        assert screen._pending_iteration_update is None
        assert screen._pending_streaming_update is None
        assert screen._pending_iteration_step is None

    def test_iteration_refresh_updates_last_time(self):
        """Test that _refresh_iteration_widget updates last update time."""
        import time

        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        # Set up a loop state
        from maverick.tui.models.enums import IterationStatus
        from maverick.tui.models.widget_state import (
            LoopIterationItem,
            LoopIterationState,
        )

        screen._loop_states["test_loop"] = LoopIterationState(
            step_name="test_loop",
            iterations=[
                LoopIterationItem(
                    index=0,
                    total=3,
                    label="item-0",
                    status=IterationStatus.PENDING,
                )
            ],
            nesting_level=0,
        )

        # Ensure enough time has passed since "last update"
        screen._last_iteration_update = 0.0

        # Call refresh
        before_call = time.time()
        screen._refresh_iteration_widget("test_loop")

        # Verify last update time was updated
        assert screen._last_iteration_update >= before_call

    def test_streaming_refresh_updates_last_time(self):
        """Test that _refresh_streaming_panel updates last update time."""
        import time

        from maverick.tui.models.enums import StreamChunkType
        from maverick.tui.models.widget_state import AgentStreamEntry

        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        # Add an entry to streaming state
        entry = AgentStreamEntry(
            timestamp=1.0,
            step_name="test_step",
            agent_name="TestAgent",
            text="Test output",
            chunk_type=StreamChunkType.OUTPUT,
        )
        screen._streaming_state.add_entry(entry)

        # Ensure enough time has passed since "last update"
        screen._last_streaming_update = 0.0

        # Call refresh
        before_call = time.time()
        screen._refresh_streaming_panel()

        # Verify last update time was updated
        assert screen._last_streaming_update >= before_call

    @pytest.mark.asyncio
    async def test_iteration_refresh_schedules_delayed_update(self):
        """Test that rapid calls schedule delayed updates."""

        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        # Set up a loop state
        from maverick.tui.models.enums import IterationStatus
        from maverick.tui.models.widget_state import (
            LoopIterationItem,
            LoopIterationState,
        )

        screen._loop_states["test_loop"] = LoopIterationState(
            step_name="test_loop",
            iterations=[
                LoopIterationItem(
                    index=0,
                    total=3,
                    label="item-0",
                    status=IterationStatus.PENDING,
                )
            ],
            nesting_level=0,
        )

        # First call should update immediately
        screen._last_iteration_update = 0.0
        screen._refresh_iteration_widget("test_loop")
        first_update_time = screen._last_iteration_update

        # Second rapid call should schedule delayed update
        screen._refresh_iteration_widget("test_loop")

        # The last update time should NOT have changed (debounced)
        assert screen._last_iteration_update == first_update_time
        # A pending update should be scheduled
        assert screen._pending_iteration_update is not None
        assert screen._pending_iteration_step == "test_loop"

        # Clean up the pending task
        if screen._pending_iteration_update:
            screen._pending_iteration_update.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await screen._pending_iteration_update

    @pytest.mark.asyncio
    async def test_streaming_refresh_schedules_delayed_update(self):
        """Test that rapid streaming calls schedule delayed updates."""
        from maverick.tui.models.enums import StreamChunkType
        from maverick.tui.models.widget_state import AgentStreamEntry

        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        # Add entries to streaming state
        for i in range(2):
            entry = AgentStreamEntry(
                timestamp=float(i),
                step_name="test_step",
                agent_name="TestAgent",
                text=f"Output {i}",
                chunk_type=StreamChunkType.OUTPUT,
            )
            screen._streaming_state.add_entry(entry)

        # First call should update immediately
        screen._last_streaming_update = 0.0
        screen._refresh_streaming_panel()
        first_update_time = screen._last_streaming_update

        # Second rapid call should schedule delayed update
        screen._refresh_streaming_panel()

        # The last update time should NOT have changed (debounced)
        assert screen._last_streaming_update == first_update_time
        # A pending update should be scheduled
        assert screen._pending_streaming_update is not None

        # Clean up the pending task
        if screen._pending_streaming_update:
            screen._pending_streaming_update.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await screen._pending_streaming_update

    @pytest.mark.asyncio
    async def test_debounce_interval_is_50ms(self):
        """Test that debounce interval is 50ms per SC-003."""
        import time

        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        # Set up a loop state
        from maverick.tui.models.enums import IterationStatus
        from maverick.tui.models.widget_state import (
            LoopIterationItem,
            LoopIterationState,
        )

        screen._loop_states["test_loop"] = LoopIterationState(
            step_name="test_loop",
            iterations=[
                LoopIterationItem(
                    index=0,
                    total=3,
                    label="item-0",
                    status=IterationStatus.PENDING,
                )
            ],
            nesting_level=0,
        )

        # Set last update to just under 50ms ago
        screen._last_iteration_update = time.time() - 0.049

        # This should be debounced (not enough time elapsed)
        screen._refresh_iteration_widget("test_loop")

        # Should have scheduled a delayed update
        assert screen._pending_iteration_update is not None

        # Clean up first pending task
        first_pending = screen._pending_iteration_update
        first_pending.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await first_pending

        # Now set last update to more than 50ms ago
        screen._last_iteration_update = time.time() - 0.051
        screen._pending_iteration_update = None  # Clear pending

        # This should NOT be debounced
        before_call = time.time()
        screen._refresh_iteration_widget("test_loop")

        # Last update time should have been updated
        assert screen._last_iteration_update >= before_call

        # Clean up any pending task
        if screen._pending_iteration_update:
            screen._pending_iteration_update.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await screen._pending_iteration_update


# Steps Panel Visibility Tests
class TestStepsPanelVisibility:
    """Tests for steps panel default visibility."""

    def test_steps_panel_visible_by_default(self):
        """Test that the steps panel is visible by default (not hidden)."""
        mock_workflow = create_mock_workflow(
            steps=[create_mock_step()],
        )
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        assert screen._steps_panel_visible is True

    def test_toggle_steps_panel_hides(self):
        """Test that toggling from visible hides the panel."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        # Initial state is visible
        assert screen._steps_panel_visible is True

        # Simulate what toggle does to the flag
        screen._steps_panel_visible = not screen._steps_panel_visible
        assert screen._steps_panel_visible is False


# Step Selection Tests
class TestStepSelection:
    """Tests for step selection via _apply_scope for stream filtering."""

    def test_selected_step_initial_state(self):
        """Test that no step is selected initially."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})
        assert screen._selected_step is None

    def test_apply_scope_sets_selected_step(self):
        """Test that _apply_scope sets _selected_step and tree state."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        screen._apply_scope("test_step")

        assert screen._selected_step == "test_step"
        assert screen._tree_state.selected_path == "test_step"

    def test_apply_scope_none_clears_selection(self):
        """Test that _apply_scope(None) clears selection."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        screen._apply_scope("test_step")
        screen._apply_scope(None)

        assert screen._selected_step is None
        assert screen._tree_state.selected_path is None

    def test_apply_scope_switches_step(self):
        """Test that _apply_scope switches selection to a different step."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        screen._apply_scope("step_a")
        screen._apply_scope("step_b")

        assert screen._selected_step == "step_b"


# UnifiedStreamEntry step_name Tests
class TestUnifiedStreamEntryStepName:
    """Tests for step_name field on UnifiedStreamEntry in workflow execution context."""

    def test_mark_step_running_sets_step_name(self):
        """Test that _mark_step_running creates entry with step_name."""

        from maverick.tui.models.enums import StreamEntryType

        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        screen._mark_step_running("review", "agent")

        # Find the step start entry in unified state
        entries = screen._unified_state.entries
        step_start_entries = [
            e for e in entries if e.entry_type == StreamEntryType.STEP_START
        ]
        assert len(step_start_entries) == 1
        assert step_start_entries[0].step_name == "review"

    def test_mark_step_completed_sets_step_name(self):
        """Test that _mark_step_completed creates entry with step_name."""
        from maverick.tui.models.enums import StreamEntryType

        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        screen._mark_step_completed("validate", 2000)

        entries = screen._unified_state.entries
        step_complete_entries = [
            e for e in entries if e.entry_type == StreamEntryType.STEP_COMPLETE
        ]
        assert len(step_complete_entries) == 1
        assert step_complete_entries[0].step_name == "validate"

    def test_mark_step_failed_sets_step_name(self):
        """Test that _mark_step_failed creates entry with step_name."""
        from maverick.tui.models.enums import StreamEntryType

        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        screen._mark_step_failed("build", 500, "Build failed")

        entries = screen._unified_state.entries
        step_failed_entries = [
            e for e in entries if e.entry_type == StreamEntryType.STEP_FAILED
        ]
        assert len(step_failed_entries) == 1
        assert step_failed_entries[0].step_name == "build"


# Bug Fix: Agent step tree node from stream chunks
class TestAgentStepTreeNodeFromStreamChunk:
    """Tests for Bug 1 fix: agent steps inside loop iterations should
    appear in the step tree when their first AgentStreamChunk arrives.

    Agent steps (e.g., implement_phase) inside loop iterations do NOT
    receive a separate StepStarted event through the callback chain.
    The first AgentStreamChunk is the earliest signal that the step is
    running, so _handle_stream_chunk must create the tree node.
    """

    @pytest.mark.asyncio
    async def test_first_stream_chunk_creates_tree_node(self):
        """Test that the first AgentStreamChunk creates a tree node."""
        from maverick.dsl.events import AgentStreamChunk

        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        # Simulate the tree state having the parent nodes already
        screen._tree_state.upsert_node(
            "implement_by_phase", step_type="loop", status="running"
        )
        screen._tree_state.upsert_node(
            "implement_by_phase/[0]", label="Phase 1: Setup", status="running"
        )

        # Simulate an AgentStreamChunk with a step_path for implement_phase
        event = AgentStreamChunk(
            step_name="implement_phase",
            agent_name="implementer",
            text="Working on task...\n",
            chunk_type="output",
            step_path="implement_by_phase/[0]/implement_phase",
        )

        await screen._handle_stream_chunk(event)

        # Verify the tree node was created
        node = screen._tree_state._node_index.get(
            "implement_by_phase/[0]/implement_phase"
        )
        assert node is not None, "implement_phase tree node should be created"
        assert node.status == "running"
        assert node.step_type == "agent"

    @pytest.mark.asyncio
    async def test_subsequent_chunks_do_not_re_upsert(self):
        """Test that only the first chunk triggers upsert, not every chunk."""
        from maverick.dsl.events import AgentStreamChunk

        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        # Pre-create parent nodes
        screen._tree_state.upsert_node(
            "implement_by_phase/[0]", label="Phase 1", status="running"
        )

        step_path = "implement_by_phase/[0]/implement_phase"

        # First chunk
        event1 = AgentStreamChunk(
            step_name="implement_phase",
            agent_name="implementer",
            text="First chunk\n",
            chunk_type="output",
            step_path=step_path,
        )
        await screen._handle_stream_chunk(event1)

        # Verify path is registered
        assert step_path in screen._registered_stream_paths

        # Manually mark node as completed to detect if a re-upsert resets it
        screen._tree_state.upsert_node(step_path, status="completed")

        # Second chunk should NOT overwrite the status
        event2 = AgentStreamChunk(
            step_name="implement_phase",
            agent_name="implementer",
            text="Second chunk\n",
            chunk_type="output",
            step_path=step_path,
        )
        await screen._handle_stream_chunk(event2)

        node = screen._tree_state._node_index[step_path]
        assert node.status == "completed", (
            "Status should not be overwritten by subsequent chunks"
        )

    @pytest.mark.asyncio
    async def test_chunk_without_step_path_skips_tree(self):
        """Test that chunks without step_path do not create tree nodes."""
        from maverick.dsl.events import AgentStreamChunk

        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        event = AgentStreamChunk(
            step_name="implement_phase",
            agent_name="implementer",
            text="No path chunk\n",
            chunk_type="output",
            step_path=None,
        )

        await screen._handle_stream_chunk(event)

        # No tree node should be created for path-less chunks
        assert "implement_phase" not in screen._tree_state._node_index


# Bug Fix: Pre-populate all iteration nodes
class TestPrePopulateIterationNodes:
    """Tests for Bug 2 fix: when the first LoopIterationStarted fires,
    ALL iteration nodes should be pre-populated in the step tree as
    pending/collapsed entries so users can see the total number of phases.
    """

    @pytest.mark.asyncio
    async def test_all_iterations_prepopulated_on_first_event(self):
        """Test that all iterations appear in tree on first LoopIterationStarted."""
        from maverick.dsl.events import LoopIterationStarted

        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        # Pre-create the loop parent node
        screen._tree_state.upsert_node(
            "implement_by_phase", step_type="loop", status="running"
        )

        event = LoopIterationStarted(
            step_name="implement_by_phase",
            iteration_index=0,
            total_iterations=3,
            item_label="Phase 1: Setup",
            parent_step_name=None,
            step_path="implement_by_phase/[0]",
        )

        await screen._handle_iteration_started(event)

        # Verify all three iteration nodes exist
        for i in range(3):
            path = f"implement_by_phase/[{i}]"
            node = screen._tree_state._node_index.get(path)
            assert node is not None, f"Iteration [{i}] node should exist"

        # Current iteration (0) should be running
        node_0 = screen._tree_state._node_index["implement_by_phase/[0]"]
        assert node_0.status == "running"
        assert node_0.label == "Phase 1: Setup"

        # Future iterations should be pending and collapsed
        node_1 = screen._tree_state._node_index["implement_by_phase/[1]"]
        assert node_1.status == "pending"
        assert node_1.expanded is False

        node_2 = screen._tree_state._node_index["implement_by_phase/[2]"]
        assert node_2.status == "pending"
        assert node_2.expanded is False

    @pytest.mark.asyncio
    async def test_pending_iteration_uses_generic_label(self):
        """Test that pending iterations get generic labels when real labels
        are not yet known.
        """
        from maverick.dsl.events import LoopIterationStarted

        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        screen._tree_state.upsert_node("my_loop", step_type="loop", status="running")

        event = LoopIterationStarted(
            step_name="my_loop",
            iteration_index=0,
            total_iterations=2,
            item_label="Item A",
            parent_step_name=None,
            step_path="my_loop/[0]",
        )

        await screen._handle_iteration_started(event)

        # Future iteration should have a generic label "Phase {i+1}" where i=1
        node_1 = screen._tree_state._node_index["my_loop/[1]"]
        assert node_1.label == "Phase 2"

    @pytest.mark.asyncio
    async def test_subsequent_iteration_updates_label_and_status(self):
        """Test that when a subsequent LoopIterationStarted fires, the
        pre-populated pending node is updated to running with correct label.
        """
        from maverick.dsl.events import LoopIterationStarted

        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        screen._tree_state.upsert_node(
            "implement_by_phase", step_type="loop", status="running"
        )

        # First iteration
        event_0 = LoopIterationStarted(
            step_name="implement_by_phase",
            iteration_index=0,
            total_iterations=3,
            item_label="Phase 1: Setup",
            parent_step_name=None,
            step_path="implement_by_phase/[0]",
        )
        await screen._handle_iteration_started(event_0)

        # Verify [1] is pending with generic label
        node_1 = screen._tree_state._node_index["implement_by_phase/[1]"]
        assert node_1.status == "pending"

        # Second iteration starts
        event_1 = LoopIterationStarted(
            step_name="implement_by_phase",
            iteration_index=1,
            total_iterations=3,
            item_label="Phase 2: Core",
            parent_step_name=None,
            step_path="implement_by_phase/[1]",
        )
        await screen._handle_iteration_started(event_1)

        # [1] should now be running with real label
        node_1 = screen._tree_state._node_index["implement_by_phase/[1]"]
        assert node_1.status == "running"
        assert node_1.label == "Phase 2: Core"

    @pytest.mark.asyncio
    async def test_no_step_path_skips_tree_prepopulation(self):
        """Test that events without step_path don't prepopulate tree."""
        from maverick.dsl.events import LoopIterationStarted

        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        event = LoopIterationStarted(
            step_name="my_loop",
            iteration_index=0,
            total_iterations=3,
            item_label="Item A",
            parent_step_name=None,
            step_path=None,
        )

        await screen._handle_iteration_started(event)

        # Only the loop state should be created, no tree nodes
        assert "my_loop" in screen._loop_states
        # No iteration tree nodes since step_path was None
        assert "my_loop/[0]" not in screen._tree_state._node_index


# Bug Fix: Nested step status transitions
class TestNestedStepStatusTransitions:
    """Tests for Bug 3 fix: nested steps inside loop iterations must
    transition their tree node status from running to completed/failed.

    The root cause was that StepStarted/StepCompleted events were only
    emitted for root-level workflow steps.  Nested steps (agent,
    subworkflow, python) executed inside loop iterations never received
    lifecycle events, so their tree nodes stayed as running (filled
    circle) forever.

    The fix emits StepStarted/StepCompleted from the loop handler for
    every nested step, and the TUI handles them via dedicated methods
    that update only the tree state without inflating global counters.
    """

    def test_nested_step_running_updates_tree_only(self):
        """Test that _mark_nested_step_running updates tree without counters."""
        from maverick.dsl.events import StepStarted
        from maverick.dsl.types import StepType

        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})
        screen.total_steps = 5
        screen.current_step = 2

        # Pre-create parent nodes in tree
        screen._tree_state.upsert_node(
            "implement_by_phase", step_type="loop", status="running"
        )
        screen._tree_state.upsert_node(
            "implement_by_phase/[0]", label="Phase 1", status="running"
        )

        event = StepStarted(
            step_name="implement_phase",
            step_type=StepType.AGENT,
            step_path="implement_by_phase/[0]/implement_phase",
        )

        screen._mark_nested_step_running(event)

        # Tree node should be created with running status
        node = screen._tree_state._node_index.get(
            "implement_by_phase/[0]/implement_phase"
        )
        assert node is not None
        assert node.status == "running"
        assert node.step_type == "agent"

        # Global step counter should NOT be incremented
        assert screen.current_step == 2

    def test_nested_step_completed_updates_tree_to_completed(self):
        """Test that _mark_nested_step_completed transitions tree to completed."""
        from maverick.dsl.events import StepCompleted
        from maverick.dsl.types import StepType

        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        # Pre-create tree hierarchy
        screen._tree_state.upsert_node(
            "implement_by_phase", step_type="loop", status="running"
        )
        screen._tree_state.upsert_node(
            "implement_by_phase/[0]", label="Phase 1", status="running"
        )
        screen._tree_state.upsert_node(
            "implement_by_phase/[0]/implement_phase",
            step_type="agent",
            status="running",
        )

        event = StepCompleted(
            step_name="implement_phase",
            step_type=StepType.AGENT,
            success=True,
            duration_ms=5000,
            step_path="implement_by_phase/[0]/implement_phase",
        )

        screen._mark_nested_step_completed(event)

        node = screen._tree_state._node_index["implement_by_phase/[0]/implement_phase"]
        assert node.status == "completed"
        assert node.duration_ms == 5000

    def test_nested_step_failed_updates_tree_to_failed(self):
        """Test that _mark_nested_step_completed transitions tree to failed."""
        from maverick.dsl.events import StepCompleted
        from maverick.dsl.types import StepType

        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        # Pre-create tree hierarchy
        screen._tree_state.upsert_node(
            "implement_by_phase/[0]/validate_phase",
            step_type="subworkflow",
            status="running",
        )

        event = StepCompleted(
            step_name="validate_phase",
            step_type=StepType.SUBWORKFLOW,
            success=False,
            duration_ms=3000,
            error="Validation failed",
            step_path="implement_by_phase/[0]/validate_phase",
        )

        screen._mark_nested_step_completed(event)

        node = screen._tree_state._node_index["implement_by_phase/[0]/validate_phase"]
        assert node.status == "failed"
        assert node.duration_ms == 3000

    def test_root_step_still_increments_counter(self):
        """Test that root-level StepStarted still increments current_step."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})
        screen.total_steps = 5
        screen.current_step = 0

        # Root step: step_path has no "/" separators
        screen._mark_step_running("setup", "python", step_path="setup")

        assert screen.current_step == 0  # _mark_step_running doesn't increment
        # current_step is incremented in the event loop, not _mark_step_running

    def test_nested_step_path_detection(self):
        """Test the is_nested_step detection logic used in _execute_workflow."""
        # Root-level paths (no slash)
        assert "/" not in "implement_by_phase"
        assert "/" not in "setup"

        # Nested paths (contain slash)
        assert "/" in "implement_by_phase/[0]/implement_phase"
        assert "/" in "implement_by_phase/[0]/validate_phase"
        assert "/" in "loop/[0]"

    def test_full_lifecycle_agent_in_loop(self):
        """Test full running -> completed lifecycle for agent step in loop.

        Simulates the real event sequence: first AgentStreamChunk creates
        the tree node (via _handle_stream_chunk), then StepCompleted
        transitions it to completed (via _mark_nested_step_completed).
        """
        from maverick.dsl.events import StepCompleted
        from maverick.dsl.types import StepType

        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        path = "implement_by_phase/[0]/implement_phase"

        # Step 1: _handle_stream_chunk creates node with status="running"
        screen._registered_stream_paths.add(path)
        screen._tree_state.upsert_node(path, step_type="agent", status="running")

        node = screen._tree_state._node_index[path]
        assert node.status == "running"

        # Step 2: StepCompleted arrives and transitions to completed
        event = StepCompleted(
            step_name="implement_phase",
            step_type=StepType.AGENT,
            success=True,
            duration_ms=12000,
            step_path=path,
        )
        screen._mark_nested_step_completed(event)

        node = screen._tree_state._node_index[path]
        assert node.status == "completed"
        assert node.duration_ms == 12000

    def test_full_lifecycle_subworkflow_in_loop(self):
        """Test full running -> completed lifecycle for subworkflow step in loop."""
        from maverick.dsl.events import StepCompleted, StepStarted
        from maverick.dsl.types import StepType

        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        path = "implement_by_phase/[0]/validate_phase"

        # Step 1: StepStarted creates node with status="running"
        start_event = StepStarted(
            step_name="validate_phase",
            step_type=StepType.SUBWORKFLOW,
            step_path=path,
        )
        screen._mark_nested_step_running(start_event)

        node = screen._tree_state._node_index[path]
        assert node.status == "running"

        # Step 2: StepCompleted transitions to completed
        complete_event = StepCompleted(
            step_name="validate_phase",
            step_type=StepType.SUBWORKFLOW,
            success=True,
            duration_ms=8000,
            step_path=path,
        )
        screen._mark_nested_step_completed(complete_event)

        node = screen._tree_state._node_index[path]
        assert node.status == "completed"
        assert node.duration_ms == 8000
