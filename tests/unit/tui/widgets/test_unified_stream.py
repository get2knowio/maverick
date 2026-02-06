"""Unit tests for UnifiedStreamWidget.

Tests cover step-scoped stream filtering, entry-type content styling via
rich.text.Text objects (RichLog-based rendering), and blank line spacing.
"""

from __future__ import annotations

import time

import pytest
from rich.text import Text

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


class TestRenderEntryContentStyling:
    """Tests for inline Rich content styling in _render_entry.

    _render_entry returns a rich.text.Text object. We inspect the plain
    text and the styled spans to verify badge + content styling.
    """

    def _render(self, entry: UnifiedStreamEntry) -> Text:
        """Render an entry via _render_entry and return the Text object."""
        state = UnifiedStreamState()
        widget = UnifiedStreamWidget(state)
        return widget._render_entry(entry)

    # --- styled entry types --------------------------------------------------

    @pytest.mark.parametrize(
        ("entry_type", "expected_style"),
        [
            (StreamEntryType.TOOL_CALL, "grey42"),
            (StreamEntryType.TOOL_RESULT, "dim"),
            (StreamEntryType.AGENT_THINKING, "dim italic"),
            (StreamEntryType.STEP_START, "bold"),
            (StreamEntryType.STEP_COMPLETE, "green3"),
            (StreamEntryType.STEP_FAILED, "red1 bold"),
            (StreamEntryType.ERROR, "red1"),
            (StreamEntryType.LOOP_START, "bold"),
            (StreamEntryType.LOOP_COMPLETE, "bold"),
        ],
    )
    def test_content_styled_for_entry_type(
        self, entry_type: StreamEntryType, expected_style: str
    ) -> None:
        """Content text is rendered with the correct Rich style."""
        entry = _make_entry(
            entry_type=entry_type, content="hello world", source="test"
        )
        rendered = self._render(entry)

        # The plain text should contain the content
        assert "hello world" in rendered.plain

        # Find the span that covers the "hello world" portion
        content_start = rendered.plain.index("hello world")
        content_end = content_start + len("hello world")

        # Check that the content region has the expected style
        # Text._spans contains (start, end, style) tuples
        content_spans = [
            span
            for span in rendered._spans
            if span.start <= content_start and span.end >= content_end
        ]
        assert len(content_spans) >= 1
        assert any(str(s.style) == expected_style for s in content_spans)

    # --- unstyled entry types ------------------------------------------------

    @pytest.mark.parametrize(
        "entry_type",
        [StreamEntryType.AGENT_OUTPUT, StreamEntryType.INFO],
    )
    def test_content_unstyled_for_plain_types(
        self, entry_type: StreamEntryType
    ) -> None:
        """Agent output and info content have no inline style on content."""
        entry = _make_entry(
            entry_type=entry_type, content="plain text", source="agent"
        )
        rendered = self._render(entry)

        # Content should be present
        assert "plain text" in rendered.plain

        # Content region should have no style (empty style string)
        content_start = rendered.plain.index("plain text")
        content_end = content_start + len("plain text")

        content_spans = [
            span
            for span in rendered._spans
            if span.start <= content_start
            and span.end >= content_end
            and str(span.style) != ""
        ]
        assert len(content_spans) == 0

    # --- level-based overrides -----------------------------------------------

    @pytest.mark.parametrize(
        ("level", "expected_style"),
        [
            ("success", "green3"),
            ("warning", "gold1"),
            ("error", "red1"),
        ],
    )
    def test_step_output_level_overrides_content_style(
        self, level: str, expected_style: str
    ) -> None:
        """StepOutput with non-info level applies level colour to content."""
        entry = _make_entry(
            entry_type=StreamEntryType.STEP_OUTPUT,
            content="lint passed",
            level=level,
        )
        rendered = self._render(entry)

        content_start = rendered.plain.index("lint passed")
        content_end = content_start + len("lint passed")

        content_spans = [
            span
            for span in rendered._spans
            if span.start <= content_start and span.end >= content_end
        ]
        assert any(str(s.style) == expected_style for s in content_spans)

    def test_step_output_info_level_no_content_style(self) -> None:
        """StepOutput with default 'info' level has no inline content style."""
        entry = _make_entry(
            entry_type=StreamEntryType.STEP_OUTPUT,
            content="running lint",
            level="info",
        )
        rendered = self._render(entry)

        content_start = rendered.plain.index("running lint")
        content_end = content_start + len("running lint")

        content_spans = [
            span
            for span in rendered._spans
            if span.start <= content_start
            and span.end >= content_end
            and str(span.style) != ""
        ]
        assert len(content_spans) == 0

    # --- escaping safety -----------------------------------------------------

    def test_brackets_in_content_are_safe(self) -> None:
        """User content with Rich-like brackets is not interpreted as markup."""
        entry = _make_entry(
            entry_type=StreamEntryType.TOOL_CALL,
            content="dict[str, Any]",
        )
        rendered = self._render(entry)
        # Using Text.append() with style args means brackets are literal
        assert "dict[str, Any]" in rendered.plain

    def test_duration_included_in_styled_content(self) -> None:
        """Duration suffix is included inside the content style."""
        entry = UnifiedStreamEntry(
            timestamp=time.time(),
            entry_type=StreamEntryType.STEP_COMPLETE,
            source="test",
            content="review done",
            duration_ms=2500,
        )
        rendered = self._render(entry)
        assert "2.5s" in rendered.plain

        # The content+duration should be styled with green3
        content_start = rendered.plain.index("review done")
        content_spans = [
            span
            for span in rendered._spans
            if span.start <= content_start and span.end >= content_start
        ]
        assert any(str(s.style) == "green3" for s in content_spans)


class TestBlankLineSpacing:
    """Tests for blank line spacing between tool call groups and other entries."""

    def test_blank_line_between_tool_call_and_agent_output(self) -> None:
        """Blank separator when transitioning TOOL_CALL -> AGENT_OUTPUT."""
        state = UnifiedStreamState()
        widget = UnifiedStreamWidget(state)

        widget._last_written_entry_type = StreamEntryType.TOOL_CALL
        entry = _make_entry(entry_type=StreamEntryType.AGENT_OUTPUT)
        assert widget._needs_blank_separator(entry) is True

    def test_blank_line_between_tool_result_and_agent_output(self) -> None:
        """Blank separator when transitioning TOOL_RESULT -> AGENT_OUTPUT."""
        state = UnifiedStreamState()
        widget = UnifiedStreamWidget(state)

        widget._last_written_entry_type = StreamEntryType.TOOL_RESULT
        entry = _make_entry(entry_type=StreamEntryType.AGENT_OUTPUT)
        assert widget._needs_blank_separator(entry) is True

    def test_no_blank_line_between_consecutive_tool_calls(self) -> None:
        """No blank separator between consecutive TOOL_CALL entries."""
        state = UnifiedStreamState()
        widget = UnifiedStreamWidget(state)

        widget._last_written_entry_type = StreamEntryType.TOOL_CALL
        entry = _make_entry(entry_type=StreamEntryType.TOOL_CALL)
        assert widget._needs_blank_separator(entry) is False

    def test_no_blank_line_between_tool_call_and_tool_result(self) -> None:
        """No blank separator between TOOL_CALL and TOOL_RESULT."""
        state = UnifiedStreamState()
        widget = UnifiedStreamWidget(state)

        widget._last_written_entry_type = StreamEntryType.TOOL_CALL
        entry = _make_entry(entry_type=StreamEntryType.TOOL_RESULT)
        assert widget._needs_blank_separator(entry) is False

    def test_no_blank_line_between_consecutive_agent_outputs(self) -> None:
        """No blank separator between consecutive AGENT_OUTPUT entries."""
        state = UnifiedStreamState()
        widget = UnifiedStreamWidget(state)

        widget._last_written_entry_type = StreamEntryType.AGENT_OUTPUT
        entry = _make_entry(entry_type=StreamEntryType.AGENT_OUTPUT)
        assert widget._needs_blank_separator(entry) is False

    def test_no_blank_line_when_no_previous_entry(self) -> None:
        """No blank separator when there is no previous entry."""
        state = UnifiedStreamState()
        widget = UnifiedStreamWidget(state)

        assert widget._last_written_entry_type is None
        entry = _make_entry(entry_type=StreamEntryType.AGENT_OUTPUT)
        assert widget._needs_blank_separator(entry) is False

    def test_blank_line_between_tool_call_and_step_start(self) -> None:
        """Blank separator from tool group to step start."""
        state = UnifiedStreamState()
        widget = UnifiedStreamWidget(state)

        widget._last_written_entry_type = StreamEntryType.TOOL_CALL
        entry = _make_entry(entry_type=StreamEntryType.STEP_START)
        assert widget._needs_blank_separator(entry) is True

    def test_no_blank_line_entering_tool_group(self) -> None:
        """No separator when entering a tool group from agent output."""
        state = UnifiedStreamState()
        widget = UnifiedStreamWidget(state)

        widget._last_written_entry_type = StreamEntryType.AGENT_OUTPUT
        entry = _make_entry(entry_type=StreamEntryType.TOOL_CALL)
        assert widget._needs_blank_separator(entry) is False

    def test_clear_resets_last_written_entry_type(self) -> None:
        """Clearing the widget resets _last_written_entry_type."""
        state = UnifiedStreamState()
        widget = UnifiedStreamWidget(state)

        widget._last_written_entry_type = StreamEntryType.TOOL_CALL
        widget.clear()
        assert widget._last_written_entry_type is None
