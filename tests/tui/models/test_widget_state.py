"""Unit tests for TUI widget state models.

Tests for UnifiedStreamState, particularly the new detail panel tracking methods.
"""

from __future__ import annotations

import time

from maverick.tui.models.enums import StreamEntryType
from maverick.tui.models.widget_state import UnifiedStreamEntry, UnifiedStreamState


class TestUnifiedStreamStateBasic:
    """Test suite for basic UnifiedStreamState functionality."""

    def test_creation_with_defaults(self) -> None:
        """Test creating UnifiedStreamState with default values."""
        state = UnifiedStreamState()
        assert state.entries == []
        assert state.auto_scroll is True
        assert state.max_size_bytes == 100 * 1024
        assert state.current_step is None
        assert state.current_step_number == 0
        assert state.total_steps == 0
        assert state.workflow_name == ""
        assert state.start_time is None

    def test_creation_with_workflow_info(self) -> None:
        """Test creating UnifiedStreamState with workflow info."""
        state = UnifiedStreamState(
            workflow_name="fly-workflow",
            total_steps=5,
            start_time=time.time(),
        )
        assert state.workflow_name == "fly-workflow"
        assert state.total_steps == 5
        assert state.start_time is not None


class TestUnifiedStreamStateDetailTracking:
    """Test suite for UnifiedStreamState detail panel tracking methods."""

    def test_detail_fields_default_values(self) -> None:
        """Test that new detail tracking fields have correct defaults."""
        state = UnifiedStreamState()
        assert state.current_step_type is None
        assert state.current_step_started_at is None
        assert state.current_step_tokens == 0
        assert state.current_step_cost == 0.0
        assert state.total_tokens == 0
        assert state.total_cost == 0.0
        assert state.completed_steps == 0
        assert state.failed_steps == 0

    def test_start_step(self) -> None:
        """Test start_step method initializes detail fields."""
        state = UnifiedStreamState(total_steps=3)

        state.start_step("implement_task", "agent")

        assert state.current_step == "implement_task"
        assert state.current_step_type == "agent"
        assert state.current_step_started_at is not None
        assert state.current_step_started_at > 0
        assert state.current_step_tokens == 0
        assert state.current_step_cost == 0.0
        assert state.current_step_number == 1

    def test_start_step_increments_step_number(self) -> None:
        """Test that start_step increments step number correctly."""
        state = UnifiedStreamState(total_steps=3)

        state.start_step("step1", "python")
        assert state.current_step_number == 1

        state.start_step("step2", "agent")
        assert state.current_step_number == 2

        state.start_step("step3", "python")
        assert state.current_step_number == 3

    def test_complete_step_success(self) -> None:
        """Test complete_step with successful completion."""
        state = UnifiedStreamState(total_steps=2)
        state.start_step("step1", "python")

        state.complete_step(success=True)

        assert state.completed_steps == 1
        assert state.failed_steps == 0

    def test_complete_step_failure(self) -> None:
        """Test complete_step with failed completion."""
        state = UnifiedStreamState(total_steps=2)
        state.start_step("step1", "agent")

        state.complete_step(success=False)

        assert state.completed_steps == 0
        assert state.failed_steps == 1

    def test_complete_step_with_usage(self) -> None:
        """Test complete_step with token/cost usage data."""
        state = UnifiedStreamState(total_steps=1)
        state.start_step("agent_step", "agent")

        state.complete_step(
            success=True,
            input_tokens=1000,
            output_tokens=500,
            cost_usd=0.0045,
        )

        # Current step should have tokens and cost
        assert state.current_step_tokens == 1500  # input + output
        assert state.current_step_cost == 0.0045
        # Totals should be updated
        assert state.total_tokens == 1500
        assert state.total_cost == 0.0045

    def test_complete_step_accumulates_totals(self) -> None:
        """Test that complete_step accumulates totals across steps."""
        state = UnifiedStreamState(total_steps=3)

        # First agent step
        state.start_step("step1", "agent")
        state.complete_step(
            success=True,
            input_tokens=1000,
            output_tokens=500,
            cost_usd=0.005,
        )
        assert state.total_tokens == 1500
        assert state.total_cost == 0.005

        # Second agent step
        state.start_step("step2", "agent")
        state.complete_step(
            success=True,
            input_tokens=2000,
            output_tokens=800,
            cost_usd=0.010,
        )
        assert state.total_tokens == 4300  # 1500 + 2800
        assert state.total_cost == 0.015  # 0.005 + 0.010

        # Non-agent step (no usage)
        state.start_step("step3", "python")
        state.complete_step(success=True)
        assert state.total_tokens == 4300  # No change
        assert state.total_cost == 0.015  # No change

    def test_complete_step_with_none_usage(self) -> None:
        """Test complete_step with None usage values (non-agent steps)."""
        state = UnifiedStreamState(total_steps=1)
        state.start_step("python_step", "python")

        state.complete_step(
            success=True,
            input_tokens=None,
            output_tokens=None,
            cost_usd=None,
        )

        assert state.current_step_tokens == 0
        assert state.current_step_cost == 0.0
        assert state.total_tokens == 0
        assert state.total_cost == 0.0

    def test_complete_step_with_partial_usage(self) -> None:
        """Test complete_step with partial usage data."""
        state = UnifiedStreamState(total_steps=1)
        state.start_step("agent_step", "agent")

        state.complete_step(
            success=True,
            input_tokens=500,
            output_tokens=None,  # Output tokens unavailable
            cost_usd=0.002,
        )

        assert state.current_step_tokens == 500  # Only input tokens
        assert state.total_tokens == 500
        assert state.total_cost == 0.002

    def test_current_step_elapsed_formatted(self) -> None:
        """Test current_step_elapsed_formatted property."""
        state = UnifiedStreamState()

        # No step started
        assert state.current_step_elapsed_formatted == "--:--"

        # Step started
        state.current_step_started_at = time.time() - 75  # 75 seconds ago
        elapsed = state.current_step_elapsed_formatted
        # Should be "01:15" or close to it (timing may vary slightly)
        assert elapsed.startswith("01:")

    def test_current_step_elapsed_formatted_minutes(self) -> None:
        """Test current_step_elapsed_formatted with multiple minutes."""
        state = UnifiedStreamState()
        state.current_step_started_at = time.time() - 125  # 2:05 ago

        elapsed = state.current_step_elapsed_formatted
        assert elapsed.startswith("02:")


class TestUnifiedStreamStateAddEntry:
    """Test suite for UnifiedStreamState add_entry method."""

    def test_add_entry_basic(self) -> None:
        """Test adding a basic entry."""
        state = UnifiedStreamState()
        entry = UnifiedStreamEntry(
            timestamp=time.time(),
            entry_type=StreamEntryType.STEP_START,
            source="test_step",
            content="test_step started",
        )

        state.add_entry(entry)

        assert len(state.entries) == 1
        assert state.entries[0] == entry

    def test_add_entry_respects_size_limit(self) -> None:
        """Test that add_entry enforces FIFO eviction at size limit."""
        state = UnifiedStreamState(max_size_bytes=100)  # Small limit

        # Add entries until we exceed the limit
        for i in range(20):
            entry = UnifiedStreamEntry(
                timestamp=time.time(),
                entry_type=StreamEntryType.INFO,
                source="test",
                content=f"Entry {i} with some content",
            )
            state.add_entry(entry)

        # Total size should be under limit
        total_size = sum(e.size_bytes for e in state.entries)
        assert total_size <= state.max_size_bytes + 50  # Allow some margin

    def test_clear(self) -> None:
        """Test clear method removes all entries."""
        state = UnifiedStreamState()
        for i in range(5):
            entry = UnifiedStreamEntry(
                timestamp=time.time(),
                entry_type=StreamEntryType.INFO,
                source="test",
                content=f"Entry {i}",
            )
            state.add_entry(entry)

        assert len(state.entries) == 5

        state.clear()

        assert len(state.entries) == 0
        assert state._current_size_bytes == 0


class TestUnifiedStreamStateElapsedTime:
    """Test suite for UnifiedStreamState elapsed time tracking."""

    def test_elapsed_seconds_no_start_time(self) -> None:
        """Test elapsed_seconds returns 0 when no start time."""
        state = UnifiedStreamState()
        assert state.elapsed_seconds == 0

    def test_elapsed_seconds_with_start_time(self) -> None:
        """Test elapsed_seconds calculates correctly."""
        state = UnifiedStreamState()
        state.start_time = time.time() - 60  # 60 seconds ago

        # Should be approximately 60 (allow some margin for test execution)
        assert 59 <= state.elapsed_seconds <= 62

    def test_elapsed_formatted(self) -> None:
        """Test elapsed_formatted returns MM:SS format."""
        state = UnifiedStreamState()
        state.start_time = time.time() - 125  # 2:05 ago

        elapsed = state.elapsed_formatted
        assert elapsed == "02:05" or elapsed == "02:06"  # Allow slight timing variance
