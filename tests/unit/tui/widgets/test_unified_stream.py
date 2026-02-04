"""Unit tests for UnifiedStreamWidget filtering by step_name.

Tests the step-scoped stream filtering feature where clicking a step
in the sidebar filters the unified stream to show only that step's entries.
"""

from __future__ import annotations

import time

from maverick.tui.models.enums import StreamEntryType
from maverick.tui.models.widget_state import UnifiedStreamEntry, UnifiedStreamState
from maverick.tui.widgets.unified_stream import UnifiedStreamWidget


def _make_entry(
    source: str = "test",
    content: str = "test content",
    entry_type: StreamEntryType = StreamEntryType.AGENT_OUTPUT,
    step_name: str | None = None,
    level: str = "info",
) -> UnifiedStreamEntry:
    """Create a test UnifiedStreamEntry."""
    return UnifiedStreamEntry(
        timestamp=time.time(),
        entry_type=entry_type,
        source=source,
        content=content,
        level=level,
        step_name=step_name,
    )


class TestUnifiedStreamWidgetFilterStep:
    """Tests for filter_step property on UnifiedStreamWidget."""

    def test_filter_step_initially_none(self) -> None:
        """Filter is None by default (show all entries)."""
        state = UnifiedStreamState()
        widget = UnifiedStreamWidget(state)
        assert widget.filter_step is None

    def test_matches_filter_all_when_none(self) -> None:
        """All entries match when filter is None."""
        state = UnifiedStreamState()
        widget = UnifiedStreamWidget(state)

        entry_with_step = _make_entry(step_name="review")
        entry_without_step = _make_entry(step_name=None)

        assert widget._matches_filter(entry_with_step) is True
        assert widget._matches_filter(entry_without_step) is True

    def test_matches_filter_by_step_name(self) -> None:
        """Only entries with matching step_name pass filter."""
        state = UnifiedStreamState()
        widget = UnifiedStreamWidget(state)
        widget._filter_path = "review"

        matching = _make_entry(step_name="review")
        non_matching = _make_entry(step_name="implement")
        global_entry = _make_entry(step_name=None)

        assert widget._matches_filter(matching) is True
        assert widget._matches_filter(non_matching) is False
        # Global entries (step_name=None) always pass
        assert widget._matches_filter(global_entry) is True

    def test_matches_filter_global_entries_always_pass(self) -> None:
        """Entries without step_name (global info/errors) always pass any filter."""
        state = UnifiedStreamState()
        widget = UnifiedStreamWidget(state)
        widget._filter_path = "some_step"

        global_info = _make_entry(
            step_name=None,
            entry_type=StreamEntryType.INFO,
            content="Global info message",
        )
        global_error = _make_entry(
            step_name=None,
            entry_type=StreamEntryType.ERROR,
            content="Global error",
            level="error",
        )

        assert widget._matches_filter(global_info) is True
        assert widget._matches_filter(global_error) is True


class TestUnifiedStreamWidgetFilterProperty:
    """Tests for setting filter_step property."""

    def test_setting_filter_step(self) -> None:
        """Setting filter_step updates the internal state."""
        state = UnifiedStreamState()
        widget = UnifiedStreamWidget(state)

        widget._filter_path = "implement_task"
        assert widget.filter_path == "implement_task"

    def test_clearing_filter_step(self) -> None:
        """Setting filter_step to None clears the filter."""
        state = UnifiedStreamState()
        widget = UnifiedStreamWidget(state)

        widget._filter_path = "implement_task"
        widget._filter_path = None
        assert widget.filter_path is None
