"""Unit tests for WorkflowExecutionScreen event handlers.

This module tests the event handlers for loop iteration and agent streaming
events in the WorkflowExecutionScreen.
"""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import MagicMock

import pytest

from maverick.dsl.events import (
    AgentStreamChunk,
    LoopIterationCompleted,
    LoopIterationStarted,
)
from maverick.tui.models.enums import (
    IterationStatus,
    StreamChunkType,
    StreamEntryType,
)
from maverick.tui.models.widget_state import (
    LoopIterationItem,
    LoopIterationState,
)
from maverick.tui.screens.workflow_execution import WorkflowExecutionScreen


def create_mock_workflow(
    name: str = "test-workflow",
    description: str | None = "Test workflow description",
    steps: list[Any] | None = None,
) -> MagicMock:
    """Create a mock WorkflowFile for testing."""
    mock_workflow = MagicMock()
    mock_workflow.name = name
    mock_workflow.description = description
    mock_workflow.steps = steps or []
    return mock_workflow


# =============================================================================
# LoopIterationStarted Event Handler Tests
# =============================================================================


class TestHandleIterationStarted:
    """Tests for _handle_iteration_started event handler."""

    @pytest.mark.asyncio
    async def test_creates_loop_state_on_first_iteration(self) -> None:
        """Test that handler creates LoopIterationState on first iteration event."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        event = LoopIterationStarted(
            step_name="test_loop",
            iteration_index=0,
            total_iterations=3,
            item_label="Item 1",
        )

        # Patch mount method to avoid Textual widget errors

        await screen._handle_iteration_started(event)

        # Verify loop state was created
        assert "test_loop" in screen._loop_states
        state = screen._loop_states["test_loop"]
        assert isinstance(state, LoopIterationState)
        assert state.step_name == "test_loop"
        assert len(state.iterations) == 3

    @pytest.mark.asyncio
    async def test_creates_correct_number_of_iterations(self) -> None:
        """Test that handler creates correct number of iteration items."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        event = LoopIterationStarted(
            step_name="test_loop",
            iteration_index=0,
            total_iterations=5,
            item_label="Item 1",
        )


        await screen._handle_iteration_started(event)

        state = screen._loop_states["test_loop"]
        assert len(state.iterations) == 5

    @pytest.mark.asyncio
    async def test_sets_iteration_status_to_running(self) -> None:
        """Test that handler updates iteration status to RUNNING."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        event = LoopIterationStarted(
            step_name="test_loop",
            iteration_index=0,
            total_iterations=3,
            item_label="First Item",
        )


        await screen._handle_iteration_started(event)

        state = screen._loop_states["test_loop"]
        assert state.iterations[0].status == IterationStatus.RUNNING

    @pytest.mark.asyncio
    async def test_sets_iteration_label(self) -> None:
        """Test that handler sets the item_label on the iteration."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        event = LoopIterationStarted(
            step_name="test_loop",
            iteration_index=0,
            total_iterations=3,
            item_label="Phase 1: Setup",
        )


        await screen._handle_iteration_started(event)

        state = screen._loop_states["test_loop"]
        assert state.iterations[0].label == "Phase 1: Setup"

    @pytest.mark.asyncio
    async def test_sets_started_at_timestamp(self) -> None:
        """Test that handler sets started_at timestamp from event."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        timestamp = time.time()
        event = LoopIterationStarted(
            step_name="test_loop",
            iteration_index=0,
            total_iterations=3,
            item_label="Item 1",
            timestamp=timestamp,
        )


        await screen._handle_iteration_started(event)

        state = screen._loop_states["test_loop"]
        assert state.iterations[0].started_at == timestamp

    @pytest.mark.asyncio
    async def test_updates_existing_iteration(self) -> None:
        """Test that handler updates existing iteration without creating new state."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        # First iteration
        event1 = LoopIterationStarted(
            step_name="test_loop",
            iteration_index=0,
            total_iterations=3,
            item_label="Item 1",
        )


        await screen._handle_iteration_started(event1)

        # Second iteration (same loop)
        event2 = LoopIterationStarted(
            step_name="test_loop",
            iteration_index=1,
            total_iterations=3,
            item_label="Item 2",
        )

        await screen._handle_iteration_started(event2)

        # Should still have only one loop state
        assert len(screen._loop_states) == 1
        state = screen._loop_states["test_loop"]
        assert state.iterations[0].label == "Item 1"
        assert state.iterations[1].label == "Item 2"
        assert state.iterations[1].status == IterationStatus.RUNNING


# =============================================================================
# LoopIterationCompleted Event Handler Tests
# =============================================================================


class TestHandleIterationCompleted:
    """Tests for _handle_iteration_completed event handler."""

    @pytest.mark.asyncio
    async def test_updates_status_to_completed_on_success(self) -> None:
        """Test that handler sets status to COMPLETED when success=True."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        # First, create the loop state
        start_event = LoopIterationStarted(
            step_name="test_loop",
            iteration_index=0,
            total_iterations=3,
            item_label="Item 1",
        )


        await screen._handle_iteration_started(start_event)

        # Now complete the iteration
        complete_event = LoopIterationCompleted(
            step_name="test_loop",
            iteration_index=0,
            success=True,
            duration_ms=1500,
        )

        await screen._handle_iteration_completed(complete_event)

        state = screen._loop_states["test_loop"]
        assert state.iterations[0].status == IterationStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_updates_status_to_failed_on_failure(self) -> None:
        """Test that handler sets status to FAILED when success=False."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        # First, create the loop state
        start_event = LoopIterationStarted(
            step_name="test_loop",
            iteration_index=0,
            total_iterations=3,
            item_label="Item 1",
        )


        await screen._handle_iteration_started(start_event)

        # Now fail the iteration
        complete_event = LoopIterationCompleted(
            step_name="test_loop",
            iteration_index=0,
            success=False,
            duration_ms=500,
            error="Something went wrong",
        )

        await screen._handle_iteration_completed(complete_event)

        state = screen._loop_states["test_loop"]
        assert state.iterations[0].status == IterationStatus.FAILED

    @pytest.mark.asyncio
    async def test_sets_duration_ms(self) -> None:
        """Test that handler sets duration_ms on iteration."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        start_event = LoopIterationStarted(
            step_name="test_loop",
            iteration_index=0,
            total_iterations=3,
            item_label="Item 1",
        )


        await screen._handle_iteration_started(start_event)

        complete_event = LoopIterationCompleted(
            step_name="test_loop",
            iteration_index=0,
            success=True,
            duration_ms=2500,
        )

        await screen._handle_iteration_completed(complete_event)

        state = screen._loop_states["test_loop"]
        assert state.iterations[0].duration_ms == 2500

    @pytest.mark.asyncio
    async def test_sets_error_message(self) -> None:
        """Test that handler sets error message on failed iteration."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        start_event = LoopIterationStarted(
            step_name="test_loop",
            iteration_index=0,
            total_iterations=3,
            item_label="Item 1",
        )


        await screen._handle_iteration_started(start_event)

        complete_event = LoopIterationCompleted(
            step_name="test_loop",
            iteration_index=0,
            success=False,
            duration_ms=500,
            error="Database connection failed",
        )

        await screen._handle_iteration_completed(complete_event)

        state = screen._loop_states["test_loop"]
        assert state.iterations[0].error == "Database connection failed"

    @pytest.mark.asyncio
    async def test_sets_completed_at_timestamp(self) -> None:
        """Test that handler sets completed_at timestamp from event."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        start_event = LoopIterationStarted(
            step_name="test_loop",
            iteration_index=0,
            total_iterations=3,
            item_label="Item 1",
        )


        await screen._handle_iteration_started(start_event)

        timestamp = time.time()
        complete_event = LoopIterationCompleted(
            step_name="test_loop",
            iteration_index=0,
            success=True,
            duration_ms=1000,
            timestamp=timestamp,
        )

        await screen._handle_iteration_completed(complete_event)

        state = screen._loop_states["test_loop"]
        assert state.iterations[0].completed_at == timestamp

    @pytest.mark.asyncio
    async def test_handles_missing_loop_state_gracefully(self) -> None:
        """Test that handler does nothing when loop state doesn't exist."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        # Try to complete an iteration for a loop that doesn't exist
        complete_event = LoopIterationCompleted(
            step_name="nonexistent_loop",
            iteration_index=0,
            success=True,
            duration_ms=1000,
        )

        # Should not raise
        await screen._handle_iteration_completed(complete_event)

    @pytest.mark.asyncio
    async def test_handles_out_of_bounds_index(self) -> None:
        """Test that handler handles out of bounds iteration index gracefully."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        start_event = LoopIterationStarted(
            step_name="test_loop",
            iteration_index=0,
            total_iterations=3,
            item_label="Item 1",
        )


        await screen._handle_iteration_started(start_event)

        # Try to complete an iteration with out of bounds index
        complete_event = LoopIterationCompleted(
            step_name="test_loop",
            iteration_index=10,  # Out of bounds
            success=True,
            duration_ms=1000,
        )

        # Should not raise
        await screen._handle_iteration_completed(complete_event)

        # Original iteration should be unchanged
        state = screen._loop_states["test_loop"]
        assert state.iterations[0].status == IterationStatus.RUNNING


# =============================================================================
# AgentStreamChunk Event Handler Tests
# =============================================================================


class TestHandleStreamChunk:
    """Tests for _handle_stream_chunk event handler."""

    @pytest.mark.asyncio
    async def test_adds_entry_to_streaming_state(self) -> None:
        """Test that handler adds AgentStreamEntry to streaming state.

        Note: With newline-based buffering, text is buffered until a
        newline character appears. We use text ending with "\\n" to
        trigger immediate flush, or call _flush_all_stream_buffers.
        """
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        # Patch refresh method to avoid Textual widget errors
        screen._refresh_streaming_panel = MagicMock()

        timestamp = time.time()
        # Text ends with newline to trigger flush
        event = AgentStreamChunk(
            step_name="test_step",
            agent_name="TestAgent",
            text="Hello, world!\n",
            chunk_type="output",
            timestamp=timestamp,
        )

        await screen._handle_stream_chunk(event)

        assert len(screen._streaming_state.entries) == 1
        entry = screen._streaming_state.entries[0]
        assert entry.step_name == "test_step"
        assert entry.agent_name == "TestAgent"
        assert "Hello, world!" in entry.text
        assert entry.timestamp == timestamp

    @pytest.mark.asyncio
    async def test_converts_output_chunk_type(self) -> None:
        """Test that handler converts 'output' chunk type to enum."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        screen._refresh_streaming_panel = MagicMock()

        # Use newline to trigger flush
        event = AgentStreamChunk(
            step_name="test_step",
            agent_name="TestAgent",
            text="Output text\n",
            chunk_type="output",
        )

        await screen._handle_stream_chunk(event)

        entry = screen._streaming_state.entries[0]
        assert entry.chunk_type == StreamChunkType.OUTPUT

    @pytest.mark.asyncio
    async def test_converts_thinking_chunk_type(self) -> None:
        """Test that handler converts 'thinking' chunk type to enum."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        screen._refresh_streaming_panel = MagicMock()

        # Use newline to trigger flush
        event = AgentStreamChunk(
            step_name="test_step",
            agent_name="TestAgent",
            text="Thinking about this\n",
            chunk_type="thinking",
        )

        await screen._handle_stream_chunk(event)

        entry = screen._streaming_state.entries[0]
        assert entry.chunk_type == StreamChunkType.THINKING

    @pytest.mark.asyncio
    async def test_converts_error_chunk_type(self) -> None:
        """Test that handler converts 'error' chunk type to enum."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        screen._refresh_streaming_panel = MagicMock()

        # Use newline to trigger flush
        event = AgentStreamChunk(
            step_name="test_step",
            agent_name="TestAgent",
            text="Error occurred!\n",
            chunk_type="error",
        )

        await screen._handle_stream_chunk(event)

        entry = screen._streaming_state.entries[0]
        assert entry.chunk_type == StreamChunkType.ERROR

    @pytest.mark.asyncio
    async def test_defaults_unknown_chunk_type_to_output(self) -> None:
        """Test that handler defaults unknown chunk types to OUTPUT."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        screen._refresh_streaming_panel = MagicMock()

        # Use newline to trigger flush
        event = AgentStreamChunk(
            step_name="test_step",
            agent_name="TestAgent",
            text="Unknown type\n",
            chunk_type="unknown_type",
        )

        await screen._handle_stream_chunk(event)

        entry = screen._streaming_state.entries[0]
        assert entry.chunk_type == StreamChunkType.OUTPUT

    @pytest.mark.asyncio
    async def test_adds_multiple_entries_sequentially(self) -> None:
        """Test that handler adds multiple entries in order.

        With newline-based buffering, each chunk needs a newline to
        flush immediately, or we flush all buffers at the end.
        """
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        screen._refresh_streaming_panel = MagicMock()

        # Use newline to trigger flush for each chunk
        events = [
            AgentStreamChunk(
                step_name="step1",
                agent_name="Agent1",
                text="First chunk\n",
                chunk_type="output",
            ),
            AgentStreamChunk(
                step_name="step1",
                agent_name="Agent1",
                text="Second chunk\n",
                chunk_type="output",
            ),
            AgentStreamChunk(
                step_name="step2",
                agent_name="Agent2",
                text="Third chunk\n",
                chunk_type="thinking",
            ),
        ]

        for event in events:
            await screen._handle_stream_chunk(event)

        assert len(screen._streaming_state.entries) == 3
        assert "First chunk" in screen._streaming_state.entries[0].text
        assert "Second chunk" in screen._streaming_state.entries[1].text
        assert "Third chunk" in screen._streaming_state.entries[2].text

    @pytest.mark.asyncio
    async def test_adds_to_unified_stream(self) -> None:
        """Test that handler adds entry to unified stream."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        screen._add_unified_entry = MagicMock()

        # Use newline to trigger flush
        event = AgentStreamChunk(
            step_name="test_step",
            agent_name="TestAgent",
            text="Some text\n",
            chunk_type="output",
        )

        await screen._handle_stream_chunk(event)

        screen._add_unified_entry.assert_called_once()

    @pytest.mark.asyncio
    async def test_tool_call_text_gets_tool_call_entry_type(self) -> None:
        """Tool calls (└ prefix) are mapped to TOOL_CALL entry type."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})
        screen._add_unified_entry = MagicMock()

        event = AgentStreamChunk(
            step_name="test_step",
            agent_name="TestAgent",
            text="\u2514 Read: src/main.py\n",
            chunk_type="output",
        )

        await screen._handle_stream_chunk(event)

        screen._add_unified_entry.assert_called_once()
        entry = screen._add_unified_entry.call_args[0][0]
        assert entry.entry_type == StreamEntryType.TOOL_CALL

    @pytest.mark.asyncio
    async def test_regular_output_not_mapped_to_tool_call(self) -> None:
        """Regular agent text is still mapped to AGENT_OUTPUT."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})
        screen._add_unified_entry = MagicMock()

        event = AgentStreamChunk(
            step_name="test_step",
            agent_name="TestAgent",
            text="Analyzing the code...\n",
            chunk_type="output",
        )

        await screen._handle_stream_chunk(event)

        screen._add_unified_entry.assert_called_once()
        entry = screen._add_unified_entry.call_args[0][0]
        assert entry.entry_type == StreamEntryType.AGENT_OUTPUT


# =============================================================================
# Nesting Level Computation Tests
# =============================================================================


class TestComputeNesting:
    """Tests for _compute_nesting method."""

    def test_top_level_loop_has_nesting_zero(self) -> None:
        """Test that top-level loops (no parent) have nesting level 0."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        nesting = screen._compute_nesting(None)

        assert nesting == 0

    def test_first_nested_loop_has_nesting_one(self) -> None:
        """Test that first nested loop has nesting level 1."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        # Create parent loop state
        screen._loop_states["parent_loop"] = LoopIterationState(
            step_name="parent_loop",
            iterations=[
                LoopIterationItem(
                    index=0,
                    total=2,
                    label="Parent Item",
                    status=IterationStatus.RUNNING,
                )
            ],
            nesting_level=0,
        )

        nesting = screen._compute_nesting("parent_loop")

        assert nesting == 1

    def test_second_nested_loop_has_nesting_two(self) -> None:
        """Test that second nested loop has nesting level 2."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        # Create parent loop state (level 0)
        screen._loop_states["grandparent_loop"] = LoopIterationState(
            step_name="grandparent_loop",
            iterations=[],
            nesting_level=0,
        )

        # Create intermediate loop state (level 1)
        screen._loop_states["parent_loop"] = LoopIterationState(
            step_name="parent_loop",
            iterations=[],
            nesting_level=1,
        )

        nesting = screen._compute_nesting("parent_loop")

        assert nesting == 2

    def test_missing_parent_returns_zero(self) -> None:
        """Test that referencing missing parent returns nesting level 0."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        # Parent doesn't exist
        nesting = screen._compute_nesting("nonexistent_parent")

        assert nesting == 0

    @pytest.mark.asyncio
    async def test_nesting_level_set_on_loop_creation(self) -> None:
        """Test that nesting level is correctly set when loop state is created."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        # Create parent loop first
        parent_event = LoopIterationStarted(
            step_name="parent_loop",
            iteration_index=0,
            total_iterations=2,
            item_label="Parent 1",
            parent_step_name=None,
        )


        await screen._handle_iteration_started(parent_event)

        # Parent should have nesting level 0
        assert screen._loop_states["parent_loop"].nesting_level == 0

        # Create nested loop
        nested_event = LoopIterationStarted(
            step_name="nested_loop",
            iteration_index=0,
            total_iterations=3,
            item_label="Nested 1",
            parent_step_name="parent_loop",
        )

        await screen._handle_iteration_started(nested_event)

        # Nested should have nesting level 1
        assert screen._loop_states["nested_loop"].nesting_level == 1

    @pytest.mark.asyncio
    async def test_deeply_nested_loops(self) -> None:
        """Test nesting level computation for deeply nested loops."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})


        # Create level 0 loop
        await screen._handle_iteration_started(
            LoopIterationStarted(
                step_name="level_0",
                iteration_index=0,
                total_iterations=1,
                item_label="L0",
                parent_step_name=None,
            )
        )

        # Create level 1 loop
        await screen._handle_iteration_started(
            LoopIterationStarted(
                step_name="level_1",
                iteration_index=0,
                total_iterations=1,
                item_label="L1",
                parent_step_name="level_0",
            )
        )

        # Create level 2 loop
        await screen._handle_iteration_started(
            LoopIterationStarted(
                step_name="level_2",
                iteration_index=0,
                total_iterations=1,
                item_label="L2",
                parent_step_name="level_1",
            )
        )

        # Verify nesting levels
        assert screen._loop_states["level_0"].nesting_level == 0
        assert screen._loop_states["level_1"].nesting_level == 1
        assert screen._loop_states["level_2"].nesting_level == 2


# =============================================================================
# Integration Tests
# =============================================================================


class TestEventHandlerIntegration:
    """Integration tests for event handlers working together."""

    @pytest.mark.asyncio
    async def test_full_loop_lifecycle(self) -> None:
        """Test complete loop iteration lifecycle from start to completion."""
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})


        # Start iteration 0
        await screen._handle_iteration_started(
            LoopIterationStarted(
                step_name="test_loop",
                iteration_index=0,
                total_iterations=2,
                item_label="Item 1",
            )
        )

        state = screen._loop_states["test_loop"]
        assert state.iterations[0].status == IterationStatus.RUNNING
        assert state.iterations[1].status == IterationStatus.PENDING

        # Complete iteration 0
        await screen._handle_iteration_completed(
            LoopIterationCompleted(
                step_name="test_loop",
                iteration_index=0,
                success=True,
                duration_ms=1000,
            )
        )

        assert state.iterations[0].status == IterationStatus.COMPLETED
        assert state.iterations[0].duration_ms == 1000

        # Start iteration 1
        await screen._handle_iteration_started(
            LoopIterationStarted(
                step_name="test_loop",
                iteration_index=1,
                total_iterations=2,
                item_label="Item 2",
            )
        )

        assert state.iterations[1].status == IterationStatus.RUNNING
        assert state.iterations[1].label == "Item 2"

        # Fail iteration 1
        await screen._handle_iteration_completed(
            LoopIterationCompleted(
                step_name="test_loop",
                iteration_index=1,
                success=False,
                duration_ms=500,
                error="Failed!",
            )
        )

        assert state.iterations[1].status == IterationStatus.FAILED
        assert state.iterations[1].error == "Failed!"

    @pytest.mark.asyncio
    async def test_concurrent_loops_with_streaming(self) -> None:
        """Test handling events from multiple loops and streaming concurrently.

        With newline-based buffering, we use text ending with a newline
        to trigger flush, or explicitly flush buffers.
        """
        mock_workflow = create_mock_workflow()
        screen = WorkflowExecutionScreen(workflow=mock_workflow, inputs={})

        screen._refresh_streaming_panel = MagicMock()

        # Start loop 1
        await screen._handle_iteration_started(
            LoopIterationStarted(
                step_name="loop_1",
                iteration_index=0,
                total_iterations=2,
                item_label="L1-I1",
            )
        )

        # Receive streaming from loop 1 (text ends with newline to flush)
        await screen._handle_stream_chunk(
            AgentStreamChunk(
                step_name="loop_1",
                agent_name="Agent1",
                text="Processing loop 1.\n",
                chunk_type="output",
            )
        )

        # Start loop 2
        await screen._handle_iteration_started(
            LoopIterationStarted(
                step_name="loop_2",
                iteration_index=0,
                total_iterations=3,
                item_label="L2-I1",
            )
        )

        # Receive streaming from loop 2 (text ends with newline to flush)
        await screen._handle_stream_chunk(
            AgentStreamChunk(
                step_name="loop_2",
                agent_name="Agent2",
                text="Processing loop 2.\n",
                chunk_type="thinking",
            )
        )

        # Verify both loops exist
        assert "loop_1" in screen._loop_states
        assert "loop_2" in screen._loop_states

        # Verify streaming entries from both
        assert len(screen._streaming_state.entries) == 2
        assert screen._streaming_state.entries[0].step_name == "loop_1"
        assert screen._streaming_state.entries[1].step_name == "loop_2"
