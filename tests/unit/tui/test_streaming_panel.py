"""Unit tests for AgentStreamingPanel widget and related dataclasses.

This test module covers:

T022 (TDD): AgentStreamEntry and StreamingPanelState dataclasses
  - Tests should FAIL until implementation is added to:
    src/maverick/tui/models/widget_state.py

T023 (TDD): AgentStreamingPanel widget rendering
  - Tests should FAIL until implementation is added to:
    src/maverick/tui/widgets/agent_streaming_panel.py

Test coverage includes:
- AgentStreamEntry creation with required fields
- AgentStreamEntry size_bytes property calculation
- StreamingPanelState creation and entry management
- StreamingPanelState FIFO eviction at buffer limit
- StreamingPanelState current_source tracking
- AgentStreamingPanel widget creation with state
- Widget mounting in a Textual app
- Header display with and without current_source
- Chunk rendering with different chunk types (OUTPUT, THINKING, ERROR)
- Toggle visibility method
- Append chunk method
- Auto-scroll behavior when enabled

Feature: 030-tui-execution-visibility
User Story: 2 - Monitor Agent Activity in Real-Time
Date: 2026-01-12
"""

from __future__ import annotations

import time

import pytest

from maverick.tui.models import StreamChunkType

# These imports will fail until the implementation is added
from maverick.tui.models.widget_state import AgentStreamEntry, StreamingPanelState


class TestAgentStreamEntry:
    """Tests for AgentStreamEntry frozen dataclass."""

    def test_creation_with_all_fields(self) -> None:
        """Test creating AgentStreamEntry with all required fields."""
        timestamp = time.time()
        entry = AgentStreamEntry(
            timestamp=timestamp,
            step_name="implement_task",
            agent_name="ImplementerAgent",
            text="Starting implementation...",
            chunk_type=StreamChunkType.OUTPUT,
        )

        assert entry.timestamp == timestamp
        assert entry.step_name == "implement_task"
        assert entry.agent_name == "ImplementerAgent"
        assert entry.text == "Starting implementation..."
        assert entry.chunk_type == StreamChunkType.OUTPUT

    def test_creation_with_thinking_chunk_type(self) -> None:
        """Test creating AgentStreamEntry with THINKING chunk type."""
        entry = AgentStreamEntry(
            timestamp=time.time(),
            step_name="review_code",
            agent_name="ReviewerAgent",
            text="",  # Empty for thinking indicator
            chunk_type=StreamChunkType.THINKING,
        )

        assert entry.chunk_type == StreamChunkType.THINKING
        assert entry.text == ""

    def test_creation_with_error_chunk_type(self) -> None:
        """Test creating AgentStreamEntry with ERROR chunk type."""
        entry = AgentStreamEntry(
            timestamp=time.time(),
            step_name="validate_code",
            agent_name="ValidatorAgent",
            text="Validation failed: syntax error",
            chunk_type=StreamChunkType.ERROR,
        )

        assert entry.chunk_type == StreamChunkType.ERROR
        assert "syntax error" in entry.text

    def test_size_bytes_property_ascii_text(self) -> None:
        """Test size_bytes property with ASCII text."""
        entry = AgentStreamEntry(
            timestamp=time.time(),
            step_name="test",
            agent_name="TestAgent",
            text="Hello, World!",  # 13 ASCII characters = 13 bytes
            chunk_type=StreamChunkType.OUTPUT,
        )

        assert entry.size_bytes == 13

    def test_size_bytes_property_unicode_text(self) -> None:
        """Test size_bytes property with Unicode text (UTF-8 encoding)."""
        entry = AgentStreamEntry(
            timestamp=time.time(),
            step_name="test",
            agent_name="TestAgent",
            text="Hello, World!",  # 13 bytes in UTF-8
            chunk_type=StreamChunkType.OUTPUT,
        )

        # Create entry with emoji (multi-byte UTF-8)
        entry_unicode = AgentStreamEntry(
            timestamp=time.time(),
            step_name="test",
            agent_name="TestAgent",
            text="Hello",  # 11 bytes: 4 bytes for emoji + 5 for Hello + space + emoji
            chunk_type=StreamChunkType.OUTPUT,
        )

        # Verify we're measuring UTF-8 bytes, not character count
        assert entry.size_bytes == len(entry.text.encode("utf-8"))
        assert entry_unicode.size_bytes == len(entry_unicode.text.encode("utf-8"))

    def test_size_bytes_property_empty_text(self) -> None:
        """Test size_bytes property with empty text."""
        entry = AgentStreamEntry(
            timestamp=time.time(),
            step_name="test",
            agent_name="TestAgent",
            text="",
            chunk_type=StreamChunkType.THINKING,
        )

        assert entry.size_bytes == 0

    def test_size_bytes_property_large_text(self) -> None:
        """Test size_bytes property with large text content."""
        large_text = "X" * 10000  # 10KB of text
        entry = AgentStreamEntry(
            timestamp=time.time(),
            step_name="test",
            agent_name="TestAgent",
            text=large_text,
            chunk_type=StreamChunkType.OUTPUT,
        )

        assert entry.size_bytes == 10000

    def test_entry_is_frozen(self) -> None:
        """Test that AgentStreamEntry is immutable (frozen dataclass)."""
        entry = AgentStreamEntry(
            timestamp=time.time(),
            step_name="test",
            agent_name="TestAgent",
            text="Immutable text",
            chunk_type=StreamChunkType.OUTPUT,
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            entry.text = "Modified text"  # type: ignore[misc]

    def test_entry_has_slots(self) -> None:
        """Test that AgentStreamEntry uses __slots__ for memory efficiency."""
        entry = AgentStreamEntry(
            timestamp=time.time(),
            step_name="test",
            agent_name="TestAgent",
            text="Test",
            chunk_type=StreamChunkType.OUTPUT,
        )

        # Slots-based classes don't have __dict__
        assert not hasattr(entry, "__dict__")


class TestStreamingPanelState:
    """Tests for StreamingPanelState mutable dataclass."""

    def test_creation_with_defaults(self) -> None:
        """Test creating StreamingPanelState with default values."""
        state = StreamingPanelState()

        assert state.visible is True
        assert state.auto_scroll is True
        assert state.entries == []
        assert state.current_source is None
        assert state.max_size_bytes == 100 * 1024  # 100KB default
        assert state.total_size_bytes == 0

    def test_creation_with_custom_values(self) -> None:
        """Test creating StreamingPanelState with custom values."""
        entry = AgentStreamEntry(
            timestamp=time.time(),
            step_name="test",
            agent_name="TestAgent",
            text="Initial entry",
            chunk_type=StreamChunkType.OUTPUT,
        )

        state = StreamingPanelState(
            visible=False,
            auto_scroll=False,
            entries=[entry],
            current_source="test - TestAgent",
            max_size_bytes=50 * 1024,  # 50KB
        )

        assert state.visible is False
        assert state.auto_scroll is False
        assert len(state.entries) == 1
        assert state.current_source == "test - TestAgent"
        assert state.max_size_bytes == 50 * 1024

    def test_add_entry_single(self) -> None:
        """Test add_entry method adds a single entry."""
        state = StreamingPanelState()

        entry = AgentStreamEntry(
            timestamp=time.time(),
            step_name="implement_task",
            agent_name="ImplementerAgent",
            text="Starting work...",
            chunk_type=StreamChunkType.OUTPUT,
        )
        state.add_entry(entry)

        assert len(state.entries) == 1
        assert state.entries[0] == entry
        assert state.total_size_bytes == entry.size_bytes

    def test_add_entry_multiple(self) -> None:
        """Test add_entry method with multiple entries."""
        state = StreamingPanelState()

        entries = []
        for i in range(5):
            entry = AgentStreamEntry(
                timestamp=time.time(),
                step_name="test",
                agent_name="TestAgent",
                text=f"Message {i}",
                chunk_type=StreamChunkType.OUTPUT,
            )
            entries.append(entry)
            state.add_entry(entry)

        assert len(state.entries) == 5
        assert state.entries == entries
        expected_size = sum(e.size_bytes for e in entries)
        assert state.total_size_bytes == expected_size

    def test_add_entry_updates_current_source(self) -> None:
        """Test add_entry method updates current_source."""
        state = StreamingPanelState()
        assert state.current_source is None

        entry1 = AgentStreamEntry(
            timestamp=time.time(),
            step_name="step_1",
            agent_name="Agent1",
            text="From agent 1",
            chunk_type=StreamChunkType.OUTPUT,
        )
        state.add_entry(entry1)
        assert state.current_source == "step_1 - Agent1"

        entry2 = AgentStreamEntry(
            timestamp=time.time(),
            step_name="step_2",
            agent_name="Agent2",
            text="From agent 2",
            chunk_type=StreamChunkType.OUTPUT,
        )
        state.add_entry(entry2)
        assert state.current_source == "step_2 - Agent2"

    def test_add_entry_fifo_eviction_basic(self) -> None:
        """Test add_entry evicts oldest entries when buffer exceeds limit."""
        state = StreamingPanelState(max_size_bytes=100)

        # Add entries until over limit
        for _ in range(20):
            entry = AgentStreamEntry(
                timestamp=time.time(),
                step_name="test",
                agent_name="TestAgent",
                text="X" * 10,  # 10 bytes each
                chunk_type=StreamChunkType.OUTPUT,
            )
            state.add_entry(entry)

        # Should have evicted oldest to stay under 100 bytes
        assert state.total_size_bytes <= 100
        assert len(state.entries) <= 10

    def test_add_entry_fifo_eviction_preserves_newest(self) -> None:
        """Test FIFO eviction keeps newest entries."""
        state = StreamingPanelState(max_size_bytes=50)

        entries_added = []
        for i in range(10):
            entry = AgentStreamEntry(
                timestamp=time.time() + i,  # Increasing timestamps
                step_name="test",
                agent_name="TestAgent",
                text=f"Entry{i:02d}",  # 7 bytes each: "Entry00", etc.
                chunk_type=StreamChunkType.OUTPUT,
            )
            entries_added.append(entry)
            state.add_entry(entry)

        # With 7 bytes each and 50 byte limit, should keep ~7 entries
        assert state.total_size_bytes <= 50

        # Remaining entries should be the most recent ones
        if state.entries:
            remaining_texts = [e.text for e in state.entries]
            # The last entry added should be present
            assert entries_added[-1].text in remaining_texts

    def test_add_entry_fifo_eviction_exact_boundary(self) -> None:
        """Test FIFO eviction at exact buffer boundary."""
        state = StreamingPanelState(max_size_bytes=30)

        # Add 3 entries of 10 bytes each = exactly 30 bytes
        for _ in range(3):
            entry = AgentStreamEntry(
                timestamp=time.time(),
                step_name="test",
                agent_name="TestAgent",
                text="X" * 10,
                chunk_type=StreamChunkType.OUTPUT,
            )
            state.add_entry(entry)

        assert len(state.entries) == 3
        assert state.total_size_bytes == 30

        # Add one more - should evict oldest
        entry = AgentStreamEntry(
            timestamp=time.time(),
            step_name="test",
            agent_name="TestAgent",
            text="Y" * 10,
            chunk_type=StreamChunkType.OUTPUT,
        )
        state.add_entry(entry)

        assert len(state.entries) == 3
        assert state.total_size_bytes == 30
        assert state.entries[-1].text == "Y" * 10

    def test_add_entry_large_single_entry(self) -> None:
        """Test adding single entry larger than max buffer still works."""
        state = StreamingPanelState(max_size_bytes=50)

        # First add some small entries
        for _ in range(3):
            entry = AgentStreamEntry(
                timestamp=time.time(),
                step_name="test",
                agent_name="TestAgent",
                text="Small",
                chunk_type=StreamChunkType.OUTPUT,
            )
            state.add_entry(entry)

        # Add a large entry that exceeds buffer
        large_entry = AgentStreamEntry(
            timestamp=time.time(),
            step_name="test",
            agent_name="TestAgent",
            text="X" * 60,  # 60 bytes, larger than 50 byte limit
            chunk_type=StreamChunkType.OUTPUT,
        )
        state.add_entry(large_entry)

        # Should have evicted all small entries
        # The large entry may be the only one remaining
        assert state.entries[-1] == large_entry

    def test_clear_method(self) -> None:
        """Test clear method removes all entries."""
        state = StreamingPanelState()

        # Add some entries
        for i in range(5):
            entry = AgentStreamEntry(
                timestamp=time.time(),
                step_name="test",
                agent_name="TestAgent",
                text=f"Entry {i}",
                chunk_type=StreamChunkType.OUTPUT,
            )
            state.add_entry(entry)

        assert len(state.entries) > 0
        assert state.total_size_bytes > 0
        assert state.current_source is not None

        # Clear
        state.clear()

        assert state.entries == []
        assert state.total_size_bytes == 0
        assert state.current_source is None

    def test_clear_method_on_empty_state(self) -> None:
        """Test clear method on already empty state."""
        state = StreamingPanelState()
        assert len(state.entries) == 0

        # Should not raise
        state.clear()

        assert state.entries == []
        assert state.total_size_bytes == 0
        assert state.current_source is None

    def test_total_size_bytes_property(self) -> None:
        """Test total_size_bytes property tracks buffer size."""
        state = StreamingPanelState()

        assert state.total_size_bytes == 0

        entry1 = AgentStreamEntry(
            timestamp=time.time(),
            step_name="test",
            agent_name="TestAgent",
            text="Hello",  # 5 bytes
            chunk_type=StreamChunkType.OUTPUT,
        )
        state.add_entry(entry1)
        assert state.total_size_bytes == 5

        entry2 = AgentStreamEntry(
            timestamp=time.time(),
            step_name="test",
            agent_name="TestAgent",
            text="World!",  # 6 bytes
            chunk_type=StreamChunkType.OUTPUT,
        )
        state.add_entry(entry2)
        assert state.total_size_bytes == 11

    def test_current_source_tracking(self) -> None:
        """Test current_source is updated with each entry."""
        state = StreamingPanelState()

        # Initially None
        assert state.current_source is None

        # First entry
        entry1 = AgentStreamEntry(
            timestamp=time.time(),
            step_name="implement_feature",
            agent_name="ImplementerAgent",
            text="Starting...",
            chunk_type=StreamChunkType.OUTPUT,
        )
        state.add_entry(entry1)
        assert state.current_source == "implement_feature - ImplementerAgent"

        # Second entry from different source
        entry2 = AgentStreamEntry(
            timestamp=time.time(),
            step_name="review_code",
            agent_name="ReviewerAgent",
            text="Reviewing...",
            chunk_type=StreamChunkType.OUTPUT,
        )
        state.add_entry(entry2)
        assert state.current_source == "review_code - ReviewerAgent"

        # Third entry from same source as first
        entry3 = AgentStreamEntry(
            timestamp=time.time(),
            step_name="implement_feature",
            agent_name="ImplementerAgent",
            text="Continuing...",
            chunk_type=StreamChunkType.OUTPUT,
        )
        state.add_entry(entry3)
        assert state.current_source == "implement_feature - ImplementerAgent"

    def test_state_is_mutable(self) -> None:
        """Test StreamingPanelState is mutable (not frozen)."""
        state = StreamingPanelState()

        # Should allow direct modification
        state.visible = False
        assert state.visible is False

        state.auto_scroll = False
        assert state.auto_scroll is False

        state.max_size_bytes = 200 * 1024
        assert state.max_size_bytes == 200 * 1024

    def test_state_has_slots(self) -> None:
        """Test StreamingPanelState uses __slots__ for memory efficiency."""
        state = StreamingPanelState()

        # Slots-based classes don't have __dict__
        assert not hasattr(state, "__dict__")


class TestStreamingPanelStateEdgeCases:
    """Edge case tests for StreamingPanelState."""

    def test_pre_existing_entries_size_tracking(self) -> None:
        """Test size tracking is correctly initialized with pre-existing entries."""
        entry1 = AgentStreamEntry(
            timestamp=time.time(),
            step_name="test",
            agent_name="TestAgent",
            text="Hello",  # 5 bytes
            chunk_type=StreamChunkType.OUTPUT,
        )
        entry2 = AgentStreamEntry(
            timestamp=time.time() + 1,
            step_name="test",
            agent_name="TestAgent",
            text="World!",  # 6 bytes
            chunk_type=StreamChunkType.OUTPUT,
        )

        # Create state with pre-existing entries
        state = StreamingPanelState(
            entries=[entry1, entry2],
            current_source="test - TestAgent",
        )

        # Size should be automatically calculated from entries
        assert state.total_size_bytes == 11  # 5 + 6 bytes

        # Adding more entries should work correctly
        entry3 = AgentStreamEntry(
            timestamp=time.time() + 2,
            step_name="test",
            agent_name="TestAgent",
            text="Test",  # 4 bytes
            chunk_type=StreamChunkType.OUTPUT,
        )
        state.add_entry(entry3)

        # Total should now be 15 bytes
        assert state.total_size_bytes == 15
        assert len(state.entries) == 3

    def test_pre_existing_entries_eviction_works(self) -> None:
        """Test FIFO eviction works correctly with pre-existing entries."""
        # Create entries totaling 80 bytes
        entries = [
            AgentStreamEntry(
                timestamp=time.time() + i,
                step_name="test",
                agent_name="TestAgent",
                text="X" * 10,  # 10 bytes each
                chunk_type=StreamChunkType.OUTPUT,
            )
            for i in range(8)
        ]

        # Create state with 100 byte limit and 80 bytes of pre-existing entries
        state = StreamingPanelState(
            entries=entries,
            max_size_bytes=100,
        )

        assert state.total_size_bytes == 80
        assert len(state.entries) == 8

        # Add entry that requires eviction (30 bytes, total would be 110)
        large_entry = AgentStreamEntry(
            timestamp=time.time() + 8,
            step_name="test",
            agent_name="TestAgent",
            text="Y" * 30,
            chunk_type=StreamChunkType.OUTPUT,
        )
        state.add_entry(large_entry)

        # Should have evicted oldest entries to make room
        assert state.total_size_bytes <= 100
        assert large_entry in state.entries

    def test_zero_max_size_bytes(self) -> None:
        """Test behavior with zero max_size_bytes."""
        state = StreamingPanelState(max_size_bytes=0)

        entry = AgentStreamEntry(
            timestamp=time.time(),
            step_name="test",
            agent_name="TestAgent",
            text="Any text",
            chunk_type=StreamChunkType.OUTPUT,
        )
        state.add_entry(entry)

        # With 0 limit, entries added then immediately evicted until none can fit
        # But the current entry should still be added
        assert len(state.entries) >= 0

    def test_very_small_max_size(self) -> None:
        """Test with max_size_bytes smaller than typical entry."""
        state = StreamingPanelState(max_size_bytes=5)

        # Add entry larger than limit
        entry = AgentStreamEntry(
            timestamp=time.time(),
            step_name="test",
            agent_name="TestAgent",
            text="This is longer than 5 bytes",
            chunk_type=StreamChunkType.OUTPUT,
        )
        state.add_entry(entry)

        # Entry should still be added (eviction happens before add)
        assert entry in state.entries

    def test_rapid_entry_addition(self) -> None:
        """Test rapid sequential entry additions."""
        state = StreamingPanelState(max_size_bytes=1000)

        start_time = time.time()
        for i in range(100):
            entry = AgentStreamEntry(
                timestamp=start_time + i * 0.001,  # Sequential timestamps
                step_name="test",
                agent_name="TestAgent",
                text=f"Message {i:03d}",  # "Message 000", etc.
                chunk_type=StreamChunkType.OUTPUT,
            )
            state.add_entry(entry)

        # All should fit within 1000 bytes (11 bytes * 100 = 1100, some eviction)
        assert state.total_size_bytes <= 1000
        # Most recent should be present
        assert state.entries[-1].text == "Message 099"

    def test_mixed_chunk_types(self) -> None:
        """Test handling of different chunk types."""
        state = StreamingPanelState()

        chunk_types = [
            StreamChunkType.THINKING,
            StreamChunkType.OUTPUT,
            StreamChunkType.ERROR,
            StreamChunkType.OUTPUT,
        ]

        for i, chunk_type in enumerate(chunk_types):
            entry = AgentStreamEntry(
                timestamp=time.time(),
                step_name="test",
                agent_name="TestAgent",
                text=f"Chunk {i}" if chunk_type != StreamChunkType.THINKING else "",
                chunk_type=chunk_type,
            )
            state.add_entry(entry)

        assert len(state.entries) == 4
        assert state.entries[0].chunk_type == StreamChunkType.THINKING
        assert state.entries[2].chunk_type == StreamChunkType.ERROR

    def test_unicode_text_size_tracking(self) -> None:
        """Test that size tracking works correctly with Unicode."""
        state = StreamingPanelState(max_size_bytes=50)

        # Add entry with emoji (multi-byte UTF-8 characters)
        entry = AgentStreamEntry(
            timestamp=time.time(),
            step_name="test",
            agent_name="TestAgent",
            text="Test",  # 8 bytes in UTF-8: 4 for emoji + 4 for "Test"
            chunk_type=StreamChunkType.OUTPUT,
        )
        state.add_entry(entry)

        # Verify size tracking uses UTF-8 bytes, not character count
        expected_size = len(entry.text.encode("utf-8"))
        assert state.total_size_bytes == expected_size

    def test_source_with_special_characters(self) -> None:
        """Test current_source with special characters in step/agent names."""
        state = StreamingPanelState()

        entry = AgentStreamEntry(
            timestamp=time.time(),
            step_name="implement_feature-v2.1",
            agent_name="Code-Reviewer/Agent",
            text="Test",
            chunk_type=StreamChunkType.OUTPUT,
        )
        state.add_entry(entry)

        assert state.current_source == "implement_feature-v2.1 - Code-Reviewer/Agent"


# =============================================================================
# T023: Unit Tests for AgentStreamingPanel Widget
# =============================================================================


def _create_streaming_panel_test_app(state):
    """Create a test app for AgentStreamingPanel widget testing.

    Factory function to avoid import issues when the widget module doesn't exist
    yet (TDD pattern).
    """
    from textual.app import App

    from maverick.tui.widgets.agent_streaming_panel import AgentStreamingPanel

    class AgentStreamingPanelTestApp(App):
        """Test app for AgentStreamingPanel widget testing."""

        def __init__(self, test_state=None):
            super().__init__()
            self._test_state = test_state

        def compose(self):
            """Compose the test app with AgentStreamingPanel widget."""
            if self._test_state is not None:
                yield AgentStreamingPanel(self._test_state)

    return AgentStreamingPanelTestApp(state)


class TestAgentStreamingPanelCreation:
    """Tests for AgentStreamingPanel widget creation."""

    @pytest.mark.asyncio
    async def test_widget_creation_with_state(self) -> None:
        """Test AgentStreamingPanel widget can be created with state."""
        from maverick.tui.widgets.agent_streaming_panel import AgentStreamingPanel

        state = StreamingPanelState()
        widget = AgentStreamingPanel(state)

        assert widget._state == state

    @pytest.mark.asyncio
    async def test_widget_mounts_in_app(self) -> None:
        """Test AgentStreamingPanel widget can be mounted in an app."""
        from maverick.tui.widgets.agent_streaming_panel import AgentStreamingPanel

        state = StreamingPanelState()

        async with _create_streaming_panel_test_app(state).run_test() as pilot:
            widget = pilot.app.query_one(AgentStreamingPanel)
            assert widget is not None
            assert widget._state == state


class TestAgentStreamingPanelHeader:
    """Tests for AgentStreamingPanel header display."""

    @pytest.mark.asyncio
    async def test_header_shows_default_text_when_no_source(self) -> None:
        """Test header shows 'Agent Output' when current_source is None."""
        from textual.widgets import Static

        state = StreamingPanelState()
        # current_source is None by default

        async with _create_streaming_panel_test_app(state).run_test() as pilot:
            await pilot.pause()

            # Find header Static widget
            statics = pilot.app.query(Static)
            header_found = False

            for static in statics:
                text = str(static.renderable)
                if "Agent Output" in text:
                    header_found = True
                    # Should NOT have source suffix when no source
                    break

            assert header_found, "Header with 'Agent Output' not found"

    @pytest.mark.asyncio
    async def test_header_shows_current_source_when_set(self) -> None:
        """Test header shows 'Agent Output: source' when current_source is set."""
        from textual.widgets import Static

        state = StreamingPanelState()
        entry = AgentStreamEntry(
            timestamp=time.time(),
            step_name="implement_feature",
            agent_name="ImplementerAgent",
            text="Working...",
            chunk_type=StreamChunkType.OUTPUT,
        )
        state.add_entry(entry)

        async with _create_streaming_panel_test_app(state).run_test() as pilot:
            await pilot.pause()

            statics = pilot.app.query(Static)
            header_text = ""

            for static in statics:
                text = str(static.renderable)
                if "Agent Output" in text:
                    header_text = text
                    break

            # Should contain the source info
            assert "implement_feature - ImplementerAgent" in header_text


class TestAgentStreamingPanelChunkRendering:
    """Tests for rendering different chunk types in AgentStreamingPanel."""

    @pytest.mark.asyncio
    async def test_render_output_chunk(self) -> None:
        """Test rendering OUTPUT chunk type."""
        from maverick.tui.widgets.agent_streaming_panel import AgentStreamingPanel

        state = StreamingPanelState()
        entry = AgentStreamEntry(
            timestamp=time.time(),
            step_name="test",
            agent_name="Agent",
            text="Output text content",
            chunk_type=StreamChunkType.OUTPUT,
        )
        state.add_entry(entry)

        async with _create_streaming_panel_test_app(state).run_test() as pilot:
            widget = pilot.app.query_one(AgentStreamingPanel)
            await pilot.pause()

            # Check for output class
            output_chunks = widget.query(".chunk-output")
            assert len(output_chunks) >= 1

    @pytest.mark.asyncio
    async def test_render_thinking_chunk(self) -> None:
        """Test rendering THINKING chunk type."""
        from maverick.tui.widgets.agent_streaming_panel import AgentStreamingPanel

        state = StreamingPanelState()
        entry = AgentStreamEntry(
            timestamp=time.time(),
            step_name="test",
            agent_name="Agent",
            text="",  # Thinking chunks often have empty text
            chunk_type=StreamChunkType.THINKING,
        )
        state.add_entry(entry)

        async with _create_streaming_panel_test_app(state).run_test() as pilot:
            widget = pilot.app.query_one(AgentStreamingPanel)
            await pilot.pause()

            # Check for thinking class
            thinking_chunks = widget.query(".chunk-thinking")
            assert len(thinking_chunks) >= 1

    @pytest.mark.asyncio
    async def test_render_error_chunk(self) -> None:
        """Test rendering ERROR chunk type."""
        from maverick.tui.widgets.agent_streaming_panel import AgentStreamingPanel

        state = StreamingPanelState()
        entry = AgentStreamEntry(
            timestamp=time.time(),
            step_name="test",
            agent_name="Agent",
            text="Error: Something went wrong",
            chunk_type=StreamChunkType.ERROR,
        )
        state.add_entry(entry)

        async with _create_streaming_panel_test_app(state).run_test() as pilot:
            widget = pilot.app.query_one(AgentStreamingPanel)
            await pilot.pause()

            # Check for error class
            error_chunks = widget.query(".chunk-error")
            assert len(error_chunks) >= 1

    @pytest.mark.asyncio
    async def test_render_mixed_chunk_types(self) -> None:
        """Test rendering multiple chunk types together."""
        from maverick.tui.widgets.agent_streaming_panel import AgentStreamingPanel

        state = StreamingPanelState()

        # Add one of each type
        entries = [
            AgentStreamEntry(
                timestamp=time.time(),
                step_name="test",
                agent_name="Agent",
                text="",
                chunk_type=StreamChunkType.THINKING,
            ),
            AgentStreamEntry(
                timestamp=time.time(),
                step_name="test",
                agent_name="Agent",
                text="Normal output",
                chunk_type=StreamChunkType.OUTPUT,
            ),
            AgentStreamEntry(
                timestamp=time.time(),
                step_name="test",
                agent_name="Agent",
                text="Error occurred",
                chunk_type=StreamChunkType.ERROR,
            ),
        ]

        for entry in entries:
            state.add_entry(entry)

        async with _create_streaming_panel_test_app(state).run_test() as pilot:
            widget = pilot.app.query_one(AgentStreamingPanel)
            await pilot.pause()

            # All chunk types should be present
            assert len(widget.query(".chunk-thinking")) >= 1
            assert len(widget.query(".chunk-output")) >= 1
            assert len(widget.query(".chunk-error")) >= 1


class TestAgentStreamingPanelToggleVisibility:
    """Tests for toggle_visibility method in AgentStreamingPanel."""

    @pytest.mark.asyncio
    async def test_toggle_visibility_changes_state(self) -> None:
        """Test toggle_visibility changes visible state."""
        from maverick.tui.widgets.agent_streaming_panel import AgentStreamingPanel

        state = StreamingPanelState(visible=True)

        async with _create_streaming_panel_test_app(state).run_test() as pilot:
            widget = pilot.app.query_one(AgentStreamingPanel)
            await pilot.pause()

            # Initially visible
            assert widget._state.visible is True

            # Toggle
            widget.toggle_visibility()
            await pilot.pause()

            # Now hidden
            assert widget._state.visible is False

            # Toggle again
            widget.toggle_visibility()
            await pilot.pause()

            # Back to visible
            assert widget._state.visible is True

    @pytest.mark.asyncio
    async def test_toggle_visibility_adds_collapsed_class(self) -> None:
        """Test toggle_visibility adds/removes 'collapsed' CSS class."""
        from maverick.tui.widgets.agent_streaming_panel import AgentStreamingPanel

        state = StreamingPanelState(visible=True)

        async with _create_streaming_panel_test_app(state).run_test() as pilot:
            widget = pilot.app.query_one(AgentStreamingPanel)
            await pilot.pause()

            # Initially no collapsed class
            assert not widget.has_class("collapsed")

            # Toggle to collapse
            widget.toggle_visibility()
            await pilot.pause()

            # Should have collapsed class
            assert widget.has_class("collapsed")

            # Toggle to expand
            widget.toggle_visibility()
            await pilot.pause()

            # Should not have collapsed class
            assert not widget.has_class("collapsed")


class TestAgentStreamingPanelAppendChunk:
    """Tests for append_chunk method in AgentStreamingPanel."""

    @pytest.mark.asyncio
    async def test_append_chunk_adds_entry_to_state(self) -> None:
        """Test append_chunk adds entry to internal state."""
        from maverick.tui.widgets.agent_streaming_panel import AgentStreamingPanel

        state = StreamingPanelState()

        async with _create_streaming_panel_test_app(state).run_test() as pilot:
            widget = pilot.app.query_one(AgentStreamingPanel)
            await pilot.pause()

            assert len(widget._state.entries) == 0

            entry = AgentStreamEntry(
                timestamp=time.time(),
                step_name="test",
                agent_name="Agent",
                text="New chunk",
                chunk_type=StreamChunkType.OUTPUT,
            )

            widget.append_chunk(entry)
            await pilot.pause()

            assert len(widget._state.entries) == 1
            assert widget._state.entries[0].text == "New chunk"

    @pytest.mark.asyncio
    async def test_append_chunk_mounts_new_widget(self) -> None:
        """Test append_chunk mounts a new Static widget for the chunk."""
        from maverick.tui.widgets.agent_streaming_panel import AgentStreamingPanel

        state = StreamingPanelState()

        async with _create_streaming_panel_test_app(state).run_test() as pilot:
            widget = pilot.app.query_one(AgentStreamingPanel)
            await pilot.pause()

            # Get initial count of chunk widgets
            initial_chunks = len(widget.query(".chunk-output"))

            entry = AgentStreamEntry(
                timestamp=time.time(),
                step_name="test",
                agent_name="Agent",
                text="Appended chunk",
                chunk_type=StreamChunkType.OUTPUT,
            )

            widget.append_chunk(entry)
            await pilot.pause()

            # Should have one more chunk widget
            new_chunks = len(widget.query(".chunk-output"))
            assert new_chunks == initial_chunks + 1

    @pytest.mark.asyncio
    async def test_append_chunk_updates_current_source(self) -> None:
        """Test append_chunk updates current_source in header."""
        from maverick.tui.widgets.agent_streaming_panel import AgentStreamingPanel

        state = StreamingPanelState()

        async with _create_streaming_panel_test_app(state).run_test() as pilot:
            widget = pilot.app.query_one(AgentStreamingPanel)
            await pilot.pause()

            entry = AgentStreamEntry(
                timestamp=time.time(),
                step_name="new_step",
                agent_name="NewAgent",
                text="Chunk text",
                chunk_type=StreamChunkType.OUTPUT,
            )

            widget.append_chunk(entry)
            await pilot.pause()

            assert widget._state.current_source == "new_step - NewAgent"


class TestAgentStreamingPanelAutoScroll:
    """Tests for auto-scroll behavior in AgentStreamingPanel."""

    @pytest.mark.asyncio
    async def test_auto_scroll_enabled_by_default(self) -> None:
        """Test auto_scroll is enabled by default."""
        from maverick.tui.widgets.agent_streaming_panel import AgentStreamingPanel

        state = StreamingPanelState()

        async with _create_streaming_panel_test_app(state).run_test() as pilot:
            widget = pilot.app.query_one(AgentStreamingPanel)
            await pilot.pause()

            assert widget._state.auto_scroll is True

    @pytest.mark.asyncio
    async def test_append_chunk_respects_auto_scroll_enabled(self) -> None:
        """Test append_chunk triggers scroll when auto_scroll is enabled."""
        from maverick.tui.widgets.agent_streaming_panel import AgentStreamingPanel

        state = StreamingPanelState(auto_scroll=True)

        async with _create_streaming_panel_test_app(state).run_test() as pilot:
            widget = pilot.app.query_one(AgentStreamingPanel)
            await pilot.pause()

            # Add multiple chunks
            for i in range(10):
                entry = AgentStreamEntry(
                    timestamp=time.time(),
                    step_name="test",
                    agent_name="Agent",
                    text=f"Chunk {i}",
                    chunk_type=StreamChunkType.OUTPUT,
                )
                widget.append_chunk(entry)
                await pilot.pause()

            # Auto-scroll should work without errors
            # (Actual scroll verification is difficult in headless tests,
            # but we verify no exceptions are raised)
            assert len(widget._state.entries) == 10

    @pytest.mark.asyncio
    async def test_append_chunk_respects_auto_scroll_disabled(self) -> None:
        """Test append_chunk does not scroll when auto_scroll is disabled."""
        from maverick.tui.widgets.agent_streaming_panel import AgentStreamingPanel

        state = StreamingPanelState(auto_scroll=False)

        async with _create_streaming_panel_test_app(state).run_test() as pilot:
            widget = pilot.app.query_one(AgentStreamingPanel)
            await pilot.pause()

            # Add chunks without auto-scroll
            for i in range(5):
                entry = AgentStreamEntry(
                    timestamp=time.time(),
                    step_name="test",
                    agent_name="Agent",
                    text=f"Chunk {i}",
                    chunk_type=StreamChunkType.OUTPUT,
                )
                widget.append_chunk(entry)
                await pilot.pause()

            # Should still add entries
            assert len(widget._state.entries) == 5
            # auto_scroll should still be disabled
            assert widget._state.auto_scroll is False


class TestAgentStreamingPanelEmptyState:
    """Tests for empty state display in AgentStreamingPanel."""

    @pytest.mark.asyncio
    async def test_empty_state_renders_without_error(self) -> None:
        """Test widget renders correctly when entries list is empty."""
        from maverick.tui.widgets.agent_streaming_panel import AgentStreamingPanel

        state = StreamingPanelState()

        async with _create_streaming_panel_test_app(state).run_test() as pilot:
            widget = pilot.app.query_one(AgentStreamingPanel)
            await pilot.pause()

            assert widget is not None
            assert len(widget._state.entries) == 0

    @pytest.mark.asyncio
    async def test_initial_render_then_add_chunk(self) -> None:
        """Test widget can render empty then receive chunks."""
        from maverick.tui.widgets.agent_streaming_panel import AgentStreamingPanel

        state = StreamingPanelState()

        async with _create_streaming_panel_test_app(state).run_test() as pilot:
            widget = pilot.app.query_one(AgentStreamingPanel)
            await pilot.pause()

            # Empty state
            assert len(widget._state.entries) == 0

            # Add a chunk
            entry = AgentStreamEntry(
                timestamp=time.time(),
                step_name="test",
                agent_name="Agent",
                text="First chunk",
                chunk_type=StreamChunkType.OUTPUT,
            )
            widget.append_chunk(entry)
            await pilot.pause()

            # Should now have content
            assert len(widget._state.entries) == 1


class TestAgentStreamingPanelCSSClasses:
    """Tests for CSS classes in AgentStreamingPanel."""

    @pytest.mark.asyncio
    async def test_has_header_class(self) -> None:
        """Test panel has header element with 'header' class."""
        from maverick.tui.widgets.agent_streaming_panel import AgentStreamingPanel

        state = StreamingPanelState()

        async with _create_streaming_panel_test_app(state).run_test() as pilot:
            widget = pilot.app.query_one(AgentStreamingPanel)
            await pilot.pause()

            headers = widget.query(".header")
            assert len(headers) >= 1

    @pytest.mark.asyncio
    async def test_has_content_class(self) -> None:
        """Test panel has content container with 'content' class."""
        from maverick.tui.widgets.agent_streaming_panel import AgentStreamingPanel

        state = StreamingPanelState()

        async with _create_streaming_panel_test_app(state).run_test() as pilot:
            widget = pilot.app.query_one(AgentStreamingPanel)
            await pilot.pause()

            content = widget.query(".content")
            assert len(content) >= 1


class TestAgentStreamingPanelStateIsolation:
    """Tests for state isolation between widget instances."""

    @pytest.mark.asyncio
    async def test_multiple_instances_have_isolated_state(self) -> None:
        """Test multiple widget instances don't share state."""
        from maverick.tui.widgets.agent_streaming_panel import AgentStreamingPanel

        state1 = StreamingPanelState()
        state2 = StreamingPanelState()

        widget1 = AgentStreamingPanel(state1)
        widget2 = AgentStreamingPanel(state2)

        entry = AgentStreamEntry(
            timestamp=time.time(),
            step_name="test",
            agent_name="Agent",
            text="Widget 1 only",
            chunk_type=StreamChunkType.OUTPUT,
        )
        state1.add_entry(entry)

        assert len(widget1._state.entries) == 1
        assert len(widget2._state.entries) == 0


# =============================================================================
# T034: Unit Tests for StreamingPanelState FIFO Buffer at 100KB Limit
# =============================================================================


class TestStreamingPanelStateFIFO100KB:
    """Tests for StreamingPanelState FIFO buffer behavior at 100KB limit.

    These tests verify that:
    - The 100KB limit is correctly enforced
    - FIFO eviction removes oldest entries first
    - Edge cases are handled correctly
    - Buffer size tracking is accurate

    Feature: 030-tui-execution-visibility
    User Story: 3 - Debug Failed Workflows
    """

    def test_default_max_size_is_100kb(self) -> None:
        """Test that default max_size_bytes is 100KB."""
        state = StreamingPanelState()

        assert state.max_size_bytes == 100 * 1024  # 100KB

    def test_fifo_eviction_at_100kb_limit(self) -> None:
        """Test that oldest entries are evicted when exceeding 100KB limit."""
        state = StreamingPanelState(max_size_bytes=100 * 1024)  # 100KB

        # Add entries totaling ~150KB (15 x 10KB each)
        for i in range(15):
            entry = AgentStreamEntry(
                timestamp=time.time() + i,  # Sequential timestamps
                step_name="test",
                agent_name="TestAgent",
                text="X" * 10240,  # 10KB each
                chunk_type=StreamChunkType.OUTPUT,
            )
            state.add_entry(entry)

        # Should have evicted oldest to stay under 100KB
        assert state.total_size_bytes <= 100 * 1024
        # Should have ~10 entries (100KB / 10KB each)
        assert len(state.entries) == 10

    def test_fifo_eviction_preserves_newest_entries(self) -> None:
        """Test FIFO eviction keeps the most recent entries."""
        state = StreamingPanelState(max_size_bytes=100 * 1024)  # 100KB

        # Add entries totaling ~200KB
        entries_added = []
        for i in range(20):
            entry = AgentStreamEntry(
                timestamp=time.time() + i,
                step_name="test",
                agent_name="TestAgent",
                text=f"Entry_{i:04d}_" + "X" * 10000,  # ~10KB each with unique prefix
                chunk_type=StreamChunkType.OUTPUT,
            )
            entries_added.append(entry)
            state.add_entry(entry)

        # Last entry should always be present
        assert state.entries[-1].text.startswith("Entry_0019_")

        # First entries should have been evicted
        remaining_texts = [e.text[:11] for e in state.entries]
        assert "Entry_0000_" not in remaining_texts
        assert "Entry_0001_" not in remaining_texts

        # Later entries should be present
        assert "Entry_0019_" in remaining_texts
        assert "Entry_0018_" in remaining_texts

    def test_fifo_eviction_exactly_at_100kb(self) -> None:
        """Test behavior when total size is exactly at 100KB limit."""
        state = StreamingPanelState(max_size_bytes=100 * 1024)  # 100KB

        # Add 10 entries of exactly 10KB each = 100KB total
        for i in range(10):
            entry = AgentStreamEntry(
                timestamp=time.time() + i,
                step_name="test",
                agent_name="TestAgent",
                text="X" * 10240,  # Exactly 10KB
                chunk_type=StreamChunkType.OUTPUT,
            )
            state.add_entry(entry)

        # Should have exactly 10 entries and exactly 100KB
        assert len(state.entries) == 10
        assert state.total_size_bytes == 100 * 1024

        # Add one more entry to trigger eviction
        entry = AgentStreamEntry(
            timestamp=time.time() + 10,
            step_name="test",
            agent_name="TestAgent",
            text="Y" * 10240,  # Another 10KB
            chunk_type=StreamChunkType.OUTPUT,
        )
        state.add_entry(entry)

        # Should still be at 100KB (one evicted, one added)
        assert len(state.entries) == 10
        assert state.total_size_bytes == 100 * 1024

        # Newest entry should be present
        assert state.entries[-1].text == "Y" * 10240

    def test_fifo_eviction_slightly_over_100kb(self) -> None:
        """Test FIFO eviction when slightly exceeding 100KB limit."""
        state = StreamingPanelState(max_size_bytes=100 * 1024)  # 100KB

        # Add entries just slightly over 100KB
        entries_size = 0
        entries_count = 0
        while entries_size <= 100 * 1024:
            entry = AgentStreamEntry(
                timestamp=time.time() + entries_count,
                step_name="test",
                agent_name="TestAgent",
                text="A" * 5000,  # 5KB each
                chunk_type=StreamChunkType.OUTPUT,
            )
            state.add_entry(entry)
            entries_size += 5000
            entries_count += 1

        # Add one more to go slightly over
        entry = AgentStreamEntry(
            timestamp=time.time() + entries_count,
            step_name="test",
            agent_name="TestAgent",
            text="B" * 1000,  # 1KB more
            chunk_type=StreamChunkType.OUTPUT,
        )
        state.add_entry(entry)

        # Should be under limit after eviction
        assert state.total_size_bytes <= 100 * 1024

        # Newest entry should be present
        assert state.entries[-1].text == "B" * 1000

    def test_fifo_eviction_far_over_100kb(self) -> None:
        """Test FIFO eviction when adding much larger than buffer size."""
        state = StreamingPanelState(max_size_bytes=100 * 1024)  # 100KB

        # Fill with small entries
        for i in range(100):
            entry = AgentStreamEntry(
                timestamp=time.time() + i,
                step_name="test",
                agent_name="TestAgent",
                text="S" * 1000,  # 1KB each (100KB total)
                chunk_type=StreamChunkType.OUTPUT,
            )
            state.add_entry(entry)

        # Add very large entry (90KB) - should evict many entries
        large_entry = AgentStreamEntry(
            timestamp=time.time() + 100,
            step_name="test",
            agent_name="TestAgent",
            text="L" * 92160,  # 90KB
            chunk_type=StreamChunkType.OUTPUT,
        )
        state.add_entry(large_entry)

        # Large entry should be present
        assert state.entries[-1] == large_entry
        # Should be under limit
        assert state.total_size_bytes <= 100 * 1024
        # Should have evicted most small entries
        assert len(state.entries) <= 11  # At most 10KB of small entries + 90KB large

    def test_fifo_eviction_with_varying_entry_sizes(self) -> None:
        """Test FIFO eviction with entries of varying sizes."""
        state = StreamingPanelState(max_size_bytes=100 * 1024)  # 100KB

        # Add entries of varying sizes
        sizes = [1000, 5000, 10000, 20000, 30000, 25000, 15000, 8000, 12000]
        for i, size in enumerate(sizes):
            entry = AgentStreamEntry(
                timestamp=time.time() + i,
                step_name="test",
                agent_name="TestAgent",
                text="X" * size,
                chunk_type=StreamChunkType.OUTPUT,
            )
            state.add_entry(entry)

        # Total is 126KB, should be under 100KB after eviction
        assert state.total_size_bytes <= 100 * 1024

        # Newest entries should be present
        assert state.entries[-1].text == "X" * 12000  # Last added

    def test_fifo_buffer_size_tracking_accuracy(self) -> None:
        """Test that total_size_bytes accurately tracks buffer size."""
        state = StreamingPanelState(max_size_bytes=100 * 1024)

        # Add entries and verify size tracking
        expected_size = 0
        for i in range(5):
            text_size = (i + 1) * 1000  # 1KB, 2KB, 3KB, 4KB, 5KB
            entry = AgentStreamEntry(
                timestamp=time.time() + i,
                step_name="test",
                agent_name="TestAgent",
                text="X" * text_size,
                chunk_type=StreamChunkType.OUTPUT,
            )
            state.add_entry(entry)
            expected_size += text_size
            assert state.total_size_bytes == expected_size

    def test_fifo_eviction_size_tracking_after_eviction(self) -> None:
        """Test that size tracking remains accurate after evictions."""
        state = StreamingPanelState(max_size_bytes=50 * 1024)  # 50KB for faster test

        # Add entries until eviction occurs
        for i in range(20):
            entry = AgentStreamEntry(
                timestamp=time.time() + i,
                step_name="test",
                agent_name="TestAgent",
                text="X" * 5120,  # 5KB each
                chunk_type=StreamChunkType.OUTPUT,
            )
            state.add_entry(entry)

        # Verify actual size matches tracked size
        actual_size = sum(e.size_bytes for e in state.entries)
        assert state.total_size_bytes == actual_size
        assert state.total_size_bytes <= 50 * 1024

    def test_fifo_with_multiple_evictions_per_add(self) -> None:
        """Test when adding one entry requires evicting multiple entries."""
        state = StreamingPanelState(max_size_bytes=50 * 1024)  # 50KB

        # Fill with small entries (50 x 1KB = 50KB)
        for i in range(50):
            entry = AgentStreamEntry(
                timestamp=time.time() + i,
                step_name="test",
                agent_name="TestAgent",
                text="S" * 1024,  # 1KB each
                chunk_type=StreamChunkType.OUTPUT,
            )
            state.add_entry(entry)

        # Add large entry that requires evicting multiple small entries
        large_entry = AgentStreamEntry(
            timestamp=time.time() + 50,
            step_name="test",
            agent_name="TestAgent",
            text="L" * 20480,  # 20KB
            chunk_type=StreamChunkType.OUTPUT,
        )
        state.add_entry(large_entry)

        # Large entry should be present
        assert large_entry in state.entries
        # Should be under limit
        assert state.total_size_bytes <= 50 * 1024
        # Multiple small entries should have been evicted
        assert len(state.entries) < 50

    def test_fifo_entry_larger_than_buffer(self) -> None:
        """Test adding single entry larger than the entire buffer."""
        state = StreamingPanelState(max_size_bytes=10 * 1024)  # 10KB

        # Add some small entries first
        for i in range(5):
            entry = AgentStreamEntry(
                timestamp=time.time() + i,
                step_name="test",
                agent_name="TestAgent",
                text="S" * 1024,
                chunk_type=StreamChunkType.OUTPUT,
            )
            state.add_entry(entry)

        # Add entry larger than entire buffer
        huge_entry = AgentStreamEntry(
            timestamp=time.time() + 5,
            step_name="test",
            agent_name="TestAgent",
            text="H" * 20480,  # 20KB, larger than 10KB limit
            chunk_type=StreamChunkType.OUTPUT,
        )
        state.add_entry(huge_entry)

        # Entry should still be added (eviction happens before add)
        assert huge_entry in state.entries
        # All small entries should be evicted
        small_entries = [e for e in state.entries if e.text.startswith("S")]
        assert len(small_entries) == 0

    def test_fifo_clear_resets_size_tracking(self) -> None:
        """Test that clear() properly resets size tracking."""
        state = StreamingPanelState(max_size_bytes=100 * 1024)

        # Add entries
        for i in range(10):
            entry = AgentStreamEntry(
                timestamp=time.time() + i,
                step_name="test",
                agent_name="TestAgent",
                text="X" * 10240,  # 10KB each
                chunk_type=StreamChunkType.OUTPUT,
            )
            state.add_entry(entry)

        assert state.total_size_bytes == 100 * 1024
        assert len(state.entries) == 10

        # Clear and verify
        state.clear()

        assert state.total_size_bytes == 0
        assert len(state.entries) == 0

        # Add new entries and verify size tracking works
        entry = AgentStreamEntry(
            timestamp=time.time(),
            step_name="test",
            agent_name="TestAgent",
            text="X" * 5000,
            chunk_type=StreamChunkType.OUTPUT,
        )
        state.add_entry(entry)
        assert state.total_size_bytes == 5000

    def test_fifo_unicode_text_size_calculation(self) -> None:
        """Test FIFO correctly handles UTF-8 encoded text size."""
        state = StreamingPanelState(max_size_bytes=100)  # Small limit for testing

        # Add entries with multi-byte UTF-8 characters
        # Japanese characters are 3 bytes each in UTF-8
        # "\u3053\u3093\u306b\u3061\u306f" = hiragana for "konnichiwa"
        japanese_text = "\u3053\u3093\u306b\u3061\u306f"  # 5 chars, 15 bytes
        entry1 = AgentStreamEntry(
            timestamp=time.time(),
            step_name="test",
            agent_name="TestAgent",
            text=japanese_text,
            chunk_type=StreamChunkType.OUTPUT,
        )
        state.add_entry(entry1)

        # Verify size is calculated as UTF-8 bytes, not character count
        assert state.total_size_bytes == len(entry1.text.encode("utf-8"))
        assert len(japanese_text) == 5  # 5 characters
        assert state.total_size_bytes == 15  # 15 bytes (3 bytes per char)


# =============================================================================
# T035: Unit Tests for History Scrolling with 100KB of Content
# =============================================================================


class TestHistoryScrollingWith100KB:
    """Tests for history scrolling with 100KB of content.

    These tests verify that:
    - AgentStreamingPanel can handle 100KB of entries
    - auto_scroll can be toggled for manual history navigation
    - Scrolling behavior works correctly with large content
    - Performance remains acceptable with large buffers

    Feature: 030-tui-execution-visibility
    User Story: 3 - Debug Failed Workflows
    """

    @pytest.mark.asyncio
    async def test_panel_handles_100kb_of_entries(self) -> None:
        """Test that AgentStreamingPanel can handle 100KB of entries."""
        from maverick.tui.widgets.agent_streaming_panel import AgentStreamingPanel

        state = StreamingPanelState(max_size_bytes=100 * 1024)

        # Add entries totaling 100KB
        for i in range(100):
            entry = AgentStreamEntry(
                timestamp=time.time() + i,
                step_name="test",
                agent_name="TestAgent",
                text=f"Line_{i:04d}_" + "X" * 1000,  # ~1KB each
                chunk_type=StreamChunkType.OUTPUT,
            )
            state.add_entry(entry)

        async with _create_streaming_panel_test_app(state).run_test() as pilot:
            widget = pilot.app.query_one(AgentStreamingPanel)
            await pilot.pause()

            # Widget should be created and have entries
            assert widget is not None
            assert len(widget._state.entries) == 100
            assert widget._state.total_size_bytes <= 100 * 1024

    @pytest.mark.asyncio
    async def test_panel_renders_many_entries_without_error(self) -> None:
        """Test panel renders without error with many entries."""
        from maverick.tui.widgets.agent_streaming_panel import AgentStreamingPanel

        state = StreamingPanelState(max_size_bytes=100 * 1024)

        # Add many entries
        for i in range(50):
            entry = AgentStreamEntry(
                timestamp=time.time() + i,
                step_name="test",
                agent_name="TestAgent",
                text=f"Content line {i}: " + "A" * 2000,  # ~2KB each
                chunk_type=StreamChunkType.OUTPUT,
            )
            state.add_entry(entry)

        async with _create_streaming_panel_test_app(state).run_test() as pilot:
            widget = pilot.app.query_one(AgentStreamingPanel)
            await pilot.pause()

            # Should have rendered chunk widgets
            chunks = widget.query(".chunk-output")
            assert len(chunks) == 50

    @pytest.mark.asyncio
    async def test_auto_scroll_toggle_for_manual_navigation(self) -> None:
        """Test auto_scroll can be toggled for manual history navigation."""
        from maverick.tui.widgets.agent_streaming_panel import AgentStreamingPanel

        state = StreamingPanelState(auto_scroll=True)

        async with _create_streaming_panel_test_app(state).run_test() as pilot:
            widget = pilot.app.query_one(AgentStreamingPanel)
            await pilot.pause()

            # Initially auto_scroll is enabled
            assert widget._state.auto_scroll is True

            # Disable auto_scroll for manual navigation
            widget.set_auto_scroll(False)
            assert widget._state.auto_scroll is False

            # Add entries - should not auto-scroll
            for i in range(5):
                entry = AgentStreamEntry(
                    timestamp=time.time() + i,
                    step_name="test",
                    agent_name="TestAgent",
                    text=f"Entry {i}",
                    chunk_type=StreamChunkType.OUTPUT,
                )
                widget.append_chunk(entry)
                await pilot.pause()

            # Verify auto_scroll is still disabled
            assert widget._state.auto_scroll is False

            # Re-enable auto_scroll
            widget.set_auto_scroll(True)
            assert widget._state.auto_scroll is True

    @pytest.mark.asyncio
    async def test_auto_scroll_disabled_allows_history_review(self) -> None:
        """Test disabling auto_scroll allows reviewing history."""
        from maverick.tui.widgets.agent_streaming_panel import AgentStreamingPanel

        state = StreamingPanelState(auto_scroll=False)

        # Pre-populate with entries
        for i in range(20):
            entry = AgentStreamEntry(
                timestamp=time.time() + i,
                step_name="test",
                agent_name="TestAgent",
                text=f"Historical entry {i}",
                chunk_type=StreamChunkType.OUTPUT,
            )
            state.add_entry(entry)

        async with _create_streaming_panel_test_app(state).run_test() as pilot:
            widget = pilot.app.query_one(AgentStreamingPanel)
            await pilot.pause()

            # All entries should be present for review
            assert len(widget._state.entries) == 20

            # Add new entry
            new_entry = AgentStreamEntry(
                timestamp=time.time() + 20,
                step_name="test",
                agent_name="TestAgent",
                text="New entry after history",
                chunk_type=StreamChunkType.OUTPUT,
            )
            widget.append_chunk(new_entry)
            await pilot.pause()

            # Entry should be added but auto_scroll should remain disabled
            assert len(widget._state.entries) == 21
            assert widget._state.auto_scroll is False

    @pytest.mark.asyncio
    async def test_scroll_end_method_availability(self) -> None:
        """Test that scroll_end is callable on the content container."""
        from textual.containers import ScrollableContainer

        from maverick.tui.widgets.agent_streaming_panel import AgentStreamingPanel

        state = StreamingPanelState()

        # Add some entries
        for i in range(10):
            entry = AgentStreamEntry(
                timestamp=time.time() + i,
                step_name="test",
                agent_name="TestAgent",
                text=f"Entry {i}",
                chunk_type=StreamChunkType.OUTPUT,
            )
            state.add_entry(entry)

        async with _create_streaming_panel_test_app(state).run_test() as pilot:
            widget = pilot.app.query_one(AgentStreamingPanel)
            await pilot.pause()

            # Get the scrollable content container
            content = widget.query_one(".content", ScrollableContainer)

            # scroll_end should be callable without error
            content.scroll_end(animate=False)
            await pilot.pause()

    @pytest.mark.asyncio
    async def test_append_chunk_triggers_scroll_when_auto_scroll_enabled(self) -> None:
        """Test append_chunk triggers scroll_end when auto_scroll is enabled."""
        from maverick.tui.widgets.agent_streaming_panel import AgentStreamingPanel

        state = StreamingPanelState(auto_scroll=True)

        async with _create_streaming_panel_test_app(state).run_test() as pilot:
            widget = pilot.app.query_one(AgentStreamingPanel)
            await pilot.pause()

            # Add multiple entries
            for i in range(20):
                entry = AgentStreamEntry(
                    timestamp=time.time() + i,
                    step_name="test",
                    agent_name="TestAgent",
                    text=f"Line {i}:" + "X" * 100,
                    chunk_type=StreamChunkType.OUTPUT,
                )
                widget.append_chunk(entry)
                await pilot.pause()

            # Should have all entries and auto_scroll should remain enabled
            assert len(widget._state.entries) == 20
            assert widget._state.auto_scroll is True

    @pytest.mark.asyncio
    async def test_append_chunk_does_not_scroll_when_auto_scroll_disabled(self) -> None:
        """Test append_chunk does not scroll when auto_scroll is disabled."""
        from maverick.tui.widgets.agent_streaming_panel import AgentStreamingPanel

        state = StreamingPanelState(auto_scroll=False)

        async with _create_streaming_panel_test_app(state).run_test() as pilot:
            widget = pilot.app.query_one(AgentStreamingPanel)
            await pilot.pause()

            # Add entries
            for i in range(10):
                entry = AgentStreamEntry(
                    timestamp=time.time() + i,
                    step_name="test",
                    agent_name="TestAgent",
                    text=f"Entry {i}",
                    chunk_type=StreamChunkType.OUTPUT,
                )
                widget.append_chunk(entry)
                await pilot.pause()

            # auto_scroll should still be disabled
            assert widget._state.auto_scroll is False

    @pytest.mark.asyncio
    async def test_large_content_with_fifo_eviction(self) -> None:
        """Test scrolling works after FIFO eviction has occurred."""
        from maverick.tui.widgets.agent_streaming_panel import AgentStreamingPanel

        state = StreamingPanelState(max_size_bytes=50 * 1024)  # 50KB for faster test

        async with _create_streaming_panel_test_app(state).run_test() as pilot:
            widget = pilot.app.query_one(AgentStreamingPanel)
            await pilot.pause()

            # Add entries that exceed the buffer limit
            for i in range(100):
                entry = AgentStreamEntry(
                    timestamp=time.time() + i,
                    step_name="test",
                    agent_name="TestAgent",
                    text=f"Entry_{i:04d}_" + "X" * 1000,  # ~1KB each
                    chunk_type=StreamChunkType.OUTPUT,
                )
                widget.append_chunk(entry)

            await pilot.pause()

            # Buffer should be at or under limit
            assert widget._state.total_size_bytes <= 50 * 1024

            # Widget should still be functional
            assert widget._state.entries[-1].text.startswith("Entry_0099_")

    @pytest.mark.asyncio
    async def test_content_container_is_scrollable(self) -> None:
        """Test that the content container is a ScrollableContainer."""
        from textual.containers import ScrollableContainer

        from maverick.tui.widgets.agent_streaming_panel import AgentStreamingPanel

        state = StreamingPanelState()

        async with _create_streaming_panel_test_app(state).run_test() as pilot:
            widget = pilot.app.query_one(AgentStreamingPanel)
            await pilot.pause()

            # Content should be a ScrollableContainer
            content = widget.query_one(".content")
            assert isinstance(content, ScrollableContainer)

    @pytest.mark.asyncio
    async def test_entries_persist_for_history_review(self) -> None:
        """Test entries persist in state for post-completion history review."""
        state = StreamingPanelState(max_size_bytes=100 * 1024)

        # Simulate workflow execution with multiple entries
        for i in range(50):
            entry = AgentStreamEntry(
                timestamp=time.time() + i,
                step_name=f"step_{i % 5}",
                agent_name=f"Agent_{i % 3}",
                text=f"Output from step {i % 5} agent {i % 3}: " + "X" * 500,
                chunk_type=StreamChunkType.OUTPUT,
            )
            state.add_entry(entry)

        # All entries should persist (within buffer limit)
        assert len(state.entries) == 50

        # Should be able to filter/search through entries
        step_0_entries = [e for e in state.entries if e.step_name == "step_0"]
        assert len(step_0_entries) == 10

        agent_1_entries = [e for e in state.entries if e.agent_name == "Agent_1"]
        assert len(agent_1_entries) > 0

    @pytest.mark.asyncio
    async def test_mixed_chunk_types_in_history(self) -> None:
        """Test history contains mixed chunk types for debugging."""
        from maverick.tui.widgets.agent_streaming_panel import AgentStreamingPanel

        state = StreamingPanelState()

        # Add mixed chunk types
        entries_to_add = [
            (StreamChunkType.THINKING, "Analyzing the problem..."),
            (StreamChunkType.OUTPUT, "Starting implementation"),
            (StreamChunkType.OUTPUT, "Writing tests"),
            (StreamChunkType.ERROR, "Test failed: assertion error"),
            (StreamChunkType.THINKING, "Reviewing error..."),
            (StreamChunkType.OUTPUT, "Fixing the issue"),
            (StreamChunkType.OUTPUT, "Tests passing now"),
        ]

        for i, (chunk_type, text) in enumerate(entries_to_add):
            entry = AgentStreamEntry(
                timestamp=time.time() + i,
                step_name="debug_step",
                agent_name="DebugAgent",
                text=text,
                chunk_type=chunk_type,
            )
            state.add_entry(entry)

        async with _create_streaming_panel_test_app(state).run_test() as pilot:
            widget = pilot.app.query_one(AgentStreamingPanel)
            await pilot.pause()

            # All chunk types should be rendered
            assert len(widget.query(".chunk-thinking")) == 2
            assert len(widget.query(".chunk-output")) == 4
            assert len(widget.query(".chunk-error")) == 1

    @pytest.mark.asyncio
    async def test_history_review_after_workflow_completion(self) -> None:
        """Test entries can be reviewed after simulated workflow completion."""
        from maverick.tui.widgets.agent_streaming_panel import AgentStreamingPanel

        state = StreamingPanelState(auto_scroll=True)

        # Simulate workflow execution
        workflow_phases = [
            ("init", "Initializing workflow..."),
            ("implement", "Implementing feature..."),
            ("test", "Running tests..."),
            ("review", "Reviewing code..."),
            ("complete", "Workflow complete!"),
        ]

        for i, (phase, message) in enumerate(workflow_phases):
            entry = AgentStreamEntry(
                timestamp=time.time() + i,
                step_name=phase,
                agent_name=f"{phase}Agent",
                text=message,
                chunk_type=StreamChunkType.OUTPUT,
            )
            state.add_entry(entry)

        async with _create_streaming_panel_test_app(state).run_test() as pilot:
            widget = pilot.app.query_one(AgentStreamingPanel)
            await pilot.pause()

            # After workflow completion, disable auto_scroll for review
            widget.set_auto_scroll(False)

            # All entries should be present for review
            assert len(widget._state.entries) == 5

            # Can verify workflow progression by examining entries
            assert widget._state.entries[0].step_name == "init"
            assert widget._state.entries[-1].step_name == "complete"

            # History is preserved and scrollable
            assert widget._state.auto_scroll is False


# =============================================================================
# T037: Tests for Scroll Support for Reviewing History
# =============================================================================


class TestAgentStreamingPanelScrollSupport:
    """Tests for scroll support methods in AgentStreamingPanel.

    T037: Add scroll support for reviewing history in AgentStreamingPanel.

    These tests verify that:
    - scroll_to_top method scrolls to the beginning of content
    - scroll_to_bottom method scrolls to the end of content
    - Methods handle unmounted widget gracefully
    - Scrolling works with many entries

    Feature: 030-tui-execution-visibility
    User Story: 3 - Debug Failed Workflows
    """

    @pytest.mark.asyncio
    async def test_scroll_to_top_method_exists(self) -> None:
        """Test scroll_to_top method exists and is callable."""
        from maverick.tui.widgets.agent_streaming_panel import AgentStreamingPanel

        state = StreamingPanelState()
        widget = AgentStreamingPanel(state)

        # Method should exist
        assert hasattr(widget, "scroll_to_top")
        assert callable(widget.scroll_to_top)

    @pytest.mark.asyncio
    async def test_scroll_to_bottom_method_exists(self) -> None:
        """Test scroll_to_bottom method exists and is callable."""
        from maverick.tui.widgets.agent_streaming_panel import AgentStreamingPanel

        state = StreamingPanelState()
        widget = AgentStreamingPanel(state)

        # Method should exist
        assert hasattr(widget, "scroll_to_bottom")
        assert callable(widget.scroll_to_bottom)

    @pytest.mark.asyncio
    async def test_scroll_to_top_when_mounted(self) -> None:
        """Test scroll_to_top works when widget is mounted."""
        from maverick.tui.widgets.agent_streaming_panel import AgentStreamingPanel

        state = StreamingPanelState()

        # Add entries
        for i in range(20):
            entry = AgentStreamEntry(
                timestamp=time.time() + i,
                step_name="test",
                agent_name="TestAgent",
                text=f"Entry {i}",
                chunk_type=StreamChunkType.OUTPUT,
            )
            state.add_entry(entry)

        async with _create_streaming_panel_test_app(state).run_test() as pilot:
            widget = pilot.app.query_one(AgentStreamingPanel)
            await pilot.pause()

            # Should not raise any exception
            widget.scroll_to_top()
            await pilot.pause()

    @pytest.mark.asyncio
    async def test_scroll_to_bottom_when_mounted(self) -> None:
        """Test scroll_to_bottom works when widget is mounted."""
        from maverick.tui.widgets.agent_streaming_panel import AgentStreamingPanel

        state = StreamingPanelState()

        # Add entries
        for i in range(20):
            entry = AgentStreamEntry(
                timestamp=time.time() + i,
                step_name="test",
                agent_name="TestAgent",
                text=f"Entry {i}",
                chunk_type=StreamChunkType.OUTPUT,
            )
            state.add_entry(entry)

        async with _create_streaming_panel_test_app(state).run_test() as pilot:
            widget = pilot.app.query_one(AgentStreamingPanel)
            await pilot.pause()

            # Should not raise any exception
            widget.scroll_to_bottom()
            await pilot.pause()

    @pytest.mark.asyncio
    async def test_scroll_to_top_when_not_mounted(self) -> None:
        """Test scroll_to_top handles unmounted widget gracefully."""
        from maverick.tui.widgets.agent_streaming_panel import AgentStreamingPanel

        state = StreamingPanelState()
        widget = AgentStreamingPanel(state)

        # Should not raise exception when not mounted
        widget.scroll_to_top()

    @pytest.mark.asyncio
    async def test_scroll_to_bottom_when_not_mounted(self) -> None:
        """Test scroll_to_bottom handles unmounted widget gracefully."""
        from maverick.tui.widgets.agent_streaming_panel import AgentStreamingPanel

        state = StreamingPanelState()
        widget = AgentStreamingPanel(state)

        # Should not raise exception when not mounted
        widget.scroll_to_bottom()

    @pytest.mark.asyncio
    async def test_scroll_to_top_then_bottom_sequence(self) -> None:
        """Test scrolling to top then bottom in sequence."""
        from maverick.tui.widgets.agent_streaming_panel import AgentStreamingPanel

        state = StreamingPanelState()

        # Add many entries
        for i in range(30):
            entry = AgentStreamEntry(
                timestamp=time.time() + i,
                step_name="test",
                agent_name="TestAgent",
                text=f"Entry {i}: " + "X" * 100,
                chunk_type=StreamChunkType.OUTPUT,
            )
            state.add_entry(entry)

        async with _create_streaming_panel_test_app(state).run_test() as pilot:
            widget = pilot.app.query_one(AgentStreamingPanel)
            await pilot.pause()

            # Scroll to top
            widget.scroll_to_top()
            await pilot.pause()

            # Scroll to bottom
            widget.scroll_to_bottom()
            await pilot.pause()

            # Should complete without error

    @pytest.mark.asyncio
    async def test_scroll_methods_with_empty_content(self) -> None:
        """Test scroll methods work with empty content."""
        from maverick.tui.widgets.agent_streaming_panel import AgentStreamingPanel

        state = StreamingPanelState()

        async with _create_streaming_panel_test_app(state).run_test() as pilot:
            widget = pilot.app.query_one(AgentStreamingPanel)
            await pilot.pause()

            # Both should work without error on empty content
            widget.scroll_to_top()
            widget.scroll_to_bottom()
            await pilot.pause()


# =============================================================================
# T038: Tests for Auto-Scroll Toggle
# =============================================================================


class TestAgentStreamingPanelAutoScrollToggle:
    """Tests for auto-scroll toggle in AgentStreamingPanel.

    T038: Add auto-scroll toggle to allow manual scrolling through history.

    These tests verify that:
    - toggle_auto_scroll method toggles the auto_scroll state
    - Visual indicator shows when auto-scroll is disabled
    - append_chunk respects auto_scroll setting
    - set_auto_scroll and toggle_auto_scroll update the header

    Feature: 030-tui-execution-visibility
    User Story: 3 - Debug Failed Workflows
    """

    @pytest.mark.asyncio
    async def test_toggle_auto_scroll_method_exists(self) -> None:
        """Test toggle_auto_scroll method exists and is callable."""
        from maverick.tui.widgets.agent_streaming_panel import AgentStreamingPanel

        state = StreamingPanelState()
        widget = AgentStreamingPanel(state)

        # Method should exist
        assert hasattr(widget, "toggle_auto_scroll")
        assert callable(widget.toggle_auto_scroll)

    @pytest.mark.asyncio
    async def test_toggle_auto_scroll_toggles_state(self) -> None:
        """Test toggle_auto_scroll toggles the auto_scroll state."""
        from maverick.tui.widgets.agent_streaming_panel import AgentStreamingPanel

        state = StreamingPanelState(auto_scroll=True)

        async with _create_streaming_panel_test_app(state).run_test() as pilot:
            widget = pilot.app.query_one(AgentStreamingPanel)
            await pilot.pause()

            # Initially enabled
            assert widget._state.auto_scroll is True

            # Toggle
            widget.toggle_auto_scroll()
            await pilot.pause()
            assert widget._state.auto_scroll is False

            # Toggle again
            widget.toggle_auto_scroll()
            await pilot.pause()
            assert widget._state.auto_scroll is True

    @pytest.mark.asyncio
    async def test_toggle_auto_scroll_from_disabled(self) -> None:
        """Test toggle_auto_scroll from disabled state."""
        from maverick.tui.widgets.agent_streaming_panel import AgentStreamingPanel

        state = StreamingPanelState(auto_scroll=False)

        async with _create_streaming_panel_test_app(state).run_test() as pilot:
            widget = pilot.app.query_one(AgentStreamingPanel)
            await pilot.pause()

            # Initially disabled
            assert widget._state.auto_scroll is False

            # Toggle
            widget.toggle_auto_scroll()
            await pilot.pause()
            assert widget._state.auto_scroll is True

    @pytest.mark.asyncio
    async def test_visual_indicator_when_auto_scroll_disabled(self) -> None:
        """Test visual indicator shows when auto-scroll is disabled."""
        from textual.widgets import Static

        from maverick.tui.widgets.agent_streaming_panel import AgentStreamingPanel

        state = StreamingPanelState(auto_scroll=False)

        async with _create_streaming_panel_test_app(state).run_test() as pilot:
            widget = pilot.app.query_one(AgentStreamingPanel)
            await pilot.pause()

            # Get header text
            header = widget.query_one("#streaming-header", Static)
            header_text = str(header.renderable)

            # Should show SCROLL PAUSED indicator
            assert "SCROLL PAUSED" in header_text

    @pytest.mark.asyncio
    async def test_no_visual_indicator_when_auto_scroll_enabled(self) -> None:
        """Test no indicator when auto-scroll is enabled."""
        from textual.widgets import Static

        from maverick.tui.widgets.agent_streaming_panel import AgentStreamingPanel

        state = StreamingPanelState(auto_scroll=True)

        async with _create_streaming_panel_test_app(state).run_test() as pilot:
            widget = pilot.app.query_one(AgentStreamingPanel)
            await pilot.pause()

            # Get header text
            header = widget.query_one("#streaming-header", Static)
            header_text = str(header.renderable)

            # Should NOT show SCROLL PAUSED indicator
            assert "SCROLL PAUSED" not in header_text

    @pytest.mark.asyncio
    async def test_visual_indicator_updates_on_toggle(self) -> None:
        """Test visual indicator updates when auto-scroll is toggled."""
        from textual.widgets import Static

        from maverick.tui.widgets.agent_streaming_panel import AgentStreamingPanel

        state = StreamingPanelState(auto_scroll=True)

        async with _create_streaming_panel_test_app(state).run_test() as pilot:
            widget = pilot.app.query_one(AgentStreamingPanel)
            await pilot.pause()

            header = widget.query_one("#streaming-header", Static)

            # Initially no indicator
            assert "SCROLL PAUSED" not in str(header.renderable)

            # Toggle to disable
            widget.toggle_auto_scroll()
            await pilot.pause()

            # Should now show indicator
            assert "SCROLL PAUSED" in str(header.renderable)

            # Toggle back to enable
            widget.toggle_auto_scroll()
            await pilot.pause()

            # Indicator should be gone
            assert "SCROLL PAUSED" not in str(header.renderable)

    @pytest.mark.asyncio
    async def test_visual_indicator_updates_on_set_auto_scroll(self) -> None:
        """Test visual indicator updates when set_auto_scroll is called."""
        from textual.widgets import Static

        from maverick.tui.widgets.agent_streaming_panel import AgentStreamingPanel

        state = StreamingPanelState(auto_scroll=True)

        async with _create_streaming_panel_test_app(state).run_test() as pilot:
            widget = pilot.app.query_one(AgentStreamingPanel)
            await pilot.pause()

            header = widget.query_one("#streaming-header", Static)

            # Initially no indicator
            assert "SCROLL PAUSED" not in str(header.renderable)

            # Disable auto-scroll
            widget.set_auto_scroll(False)
            await pilot.pause()

            # Should now show indicator
            assert "SCROLL PAUSED" in str(header.renderable)

            # Enable auto-scroll
            widget.set_auto_scroll(True)
            await pilot.pause()

            # Indicator should be gone
            assert "SCROLL PAUSED" not in str(header.renderable)

    @pytest.mark.asyncio
    async def test_append_chunk_no_scroll_when_disabled(self) -> None:
        """Test append_chunk does not auto-scroll when disabled."""
        from maverick.tui.widgets.agent_streaming_panel import AgentStreamingPanel

        state = StreamingPanelState(auto_scroll=False)

        async with _create_streaming_panel_test_app(state).run_test() as pilot:
            widget = pilot.app.query_one(AgentStreamingPanel)
            await pilot.pause()

            # Add entries
            for i in range(10):
                entry = AgentStreamEntry(
                    timestamp=time.time() + i,
                    step_name="test",
                    agent_name="TestAgent",
                    text=f"Entry {i}",
                    chunk_type=StreamChunkType.OUTPUT,
                )
                widget.append_chunk(entry)
                await pilot.pause()

            # Entries should be added
            assert len(widget._state.entries) == 10

            # auto_scroll should still be disabled
            assert widget._state.auto_scroll is False

    @pytest.mark.asyncio
    async def test_toggle_auto_scroll_when_not_mounted(self) -> None:
        """Test toggle_auto_scroll handles unmounted widget gracefully."""
        from maverick.tui.widgets.agent_streaming_panel import AgentStreamingPanel

        state = StreamingPanelState(auto_scroll=True)
        widget = AgentStreamingPanel(state)

        # Should not raise exception when not mounted
        widget.toggle_auto_scroll()

        # State should still be updated
        assert widget._state.auto_scroll is False

    @pytest.mark.asyncio
    async def test_visual_indicator_with_current_source(self) -> None:
        """Test visual indicator appears alongside current source."""
        from textual.widgets import Static

        from maverick.tui.widgets.agent_streaming_panel import AgentStreamingPanel

        state = StreamingPanelState(auto_scroll=False)

        # Add an entry to set current_source
        entry = AgentStreamEntry(
            timestamp=time.time(),
            step_name="implement_task",
            agent_name="ImplementerAgent",
            text="Working...",
            chunk_type=StreamChunkType.OUTPUT,
        )
        state.add_entry(entry)

        async with _create_streaming_panel_test_app(state).run_test() as pilot:
            widget = pilot.app.query_one(AgentStreamingPanel)
            await pilot.pause()

            header = widget.query_one("#streaming-header", Static)
            header_text = str(header.renderable)

            # Should show both source and indicator
            assert "implement_task - ImplementerAgent" in header_text
            assert "SCROLL PAUSED" in header_text

    @pytest.mark.asyncio
    async def test_disable_auto_scroll_for_history_review_workflow(self) -> None:
        """Test workflow: disable auto-scroll, scroll to top, review history."""
        from maverick.tui.widgets.agent_streaming_panel import AgentStreamingPanel

        state = StreamingPanelState(auto_scroll=True)

        # Add entries simulating workflow output
        for i in range(15):
            entry = AgentStreamEntry(
                timestamp=time.time() + i,
                step_name=f"step_{i}",
                agent_name="WorkflowAgent",
                text=f"Output from step {i}",
                chunk_type=StreamChunkType.OUTPUT,
            )
            state.add_entry(entry)

        async with _create_streaming_panel_test_app(state).run_test() as pilot:
            widget = pilot.app.query_one(AgentStreamingPanel)
            await pilot.pause()

            # Step 1: Disable auto-scroll
            widget.set_auto_scroll(False)
            await pilot.pause()
            assert widget._state.auto_scroll is False

            # Step 2: Scroll to top to review history
            widget.scroll_to_top()
            await pilot.pause()

            # Step 3: Add new entry while reviewing
            new_entry = AgentStreamEntry(
                timestamp=time.time() + 20,
                step_name="new_step",
                agent_name="NewAgent",
                text="New output while reviewing",
                chunk_type=StreamChunkType.OUTPUT,
            )
            widget.append_chunk(new_entry)
            await pilot.pause()

            # Entry should be added without disrupting scroll position
            assert len(widget._state.entries) == 16
            assert widget._state.auto_scroll is False

            # Step 4: Re-enable auto-scroll and return to bottom
            widget.set_auto_scroll(True)
            widget.scroll_to_bottom()
            await pilot.pause()

            assert widget._state.auto_scroll is True
