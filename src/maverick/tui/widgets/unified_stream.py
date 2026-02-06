"""UnifiedStreamWidget for displaying workflow events as a single stream.

This widget displays all workflow events (step starts, agent outputs, tool calls,
errors) in a chronological, scrollable stream with type-specific styling.

Feature: TUI Redesign - Streaming-First Layout
Date: 2026-01-17
"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.css.query import NoMatches
from textual.widget import Widget
from textual.widgets import RichLog, Static

from maverick.tui.models.enums import StreamEntryType
from maverick.tui.models.widget_state import UnifiedStreamEntry, UnifiedStreamState

# Rich colour names for badge text per entry type.
_BADGE_COLORS: dict[StreamEntryType, str] = {
    StreamEntryType.STEP_START: "dodger_blue1",
    StreamEntryType.STEP_COMPLETE: "green3",
    StreamEntryType.STEP_FAILED: "red1",
    StreamEntryType.STEP_OUTPUT: "grey62",
    StreamEntryType.AGENT_OUTPUT: "medium_purple2",
    StreamEntryType.AGENT_THINKING: "grey62 italic",
    StreamEntryType.TOOL_CALL: "grey42",
    StreamEntryType.TOOL_RESULT: "grey50",
    StreamEntryType.LOOP_START: "gold1",
    StreamEntryType.LOOP_COMPLETE: "gold1",
    StreamEntryType.ERROR: "red1",
    StreamEntryType.INFO: "cyan",
}

# Override badge colour when StepOutput has a non-info level.
_LEVEL_COLORS: dict[str, str] = {
    "success": "green3",
    "warning": "gold1",
    "error": "red1",
}

# Rich style applied to content text (not badge) per entry type.
# Entry types not listed here receive no inline content styling.
_CONTENT_STYLES: dict[StreamEntryType, str] = {
    StreamEntryType.STEP_START: "bold",
    StreamEntryType.STEP_COMPLETE: "green3",
    StreamEntryType.STEP_FAILED: "red1 bold",
    StreamEntryType.AGENT_THINKING: "dim italic",
    StreamEntryType.TOOL_CALL: "grey42",
    StreamEntryType.TOOL_RESULT: "dim",
    StreamEntryType.LOOP_START: "bold",
    StreamEntryType.LOOP_COMPLETE: "bold",
    StreamEntryType.ERROR: "red1",
}

# Entry types that are part of a tool call group.
_TOOL_GROUP_TYPES = frozenset({StreamEntryType.TOOL_CALL, StreamEntryType.TOOL_RESULT})


class UnifiedStreamWidget(Widget):
    """Widget for displaying unified workflow event stream.

    This widget provides:
    - Single scrollable stream for all workflow events
    - Type-specific styling with badges and colors
    - Auto-scroll with pause indicator
    - Compact header with workflow status
    - Blank line spacing between tool call groups and agent output
    - FIFO buffer management for memory efficiency

    Attributes:
        _state: The UnifiedStreamState managing entries and status.

    Example:
        state = UnifiedStreamState(workflow_name="fly-workflow", total_steps=5)
        widget = UnifiedStreamWidget(state)

        # Add stream entries
        entry = UnifiedStreamEntry(
            timestamp=time.time(),
            entry_type=StreamEntryType.STEP_START,
            source="implement_task",
            content="implement_task started",
        )
        widget.add_entry(entry)
    """

    DEFAULT_CSS = """
    UnifiedStreamWidget {
        height: 100%;
        width: 100%;
    }

    /* Compact header - single line */
    UnifiedStreamWidget .compact-header {
        height: 1;
        background: $surface;
        padding: 0 1;
    }

    UnifiedStreamWidget .compact-header .workflow-name {
        color: $primary;
        text-style: bold;
    }

    UnifiedStreamWidget .compact-header .step-indicator {
        color: $text-muted;
    }

    UnifiedStreamWidget .compact-header .elapsed {
        color: $text-disabled;
    }

    /* Stream content area (now a RichLog) */
    UnifiedStreamWidget #stream-content {
        height: 1fr;
        padding: 0 1;
        scrollbar-background: $surface;
        scrollbar-color: $text-disabled;
    }

    /* Auto-scroll paused indicator */
    UnifiedStreamWidget .scroll-indicator {
        dock: bottom;
        height: 1;
        background: $warning 30%;
        color: $warning;
        text-align: center;
        display: none;
    }

    UnifiedStreamWidget .scroll-indicator.paused {
        display: block;
    }
    """

    def __init__(
        self,
        state: UnifiedStreamState,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
        disabled: bool = False,
    ) -> None:
        """Initialize the UnifiedStreamWidget.

        Args:
            state: The UnifiedStreamState managing entries and status.
            name: The name of the widget.
            id: The ID of the widget in the DOM.
            classes: The CSS classes for the widget.
            disabled: Whether the widget is disabled.
        """
        super().__init__(name=name, id=id, classes=classes, disabled=disabled)
        self._state = state
        self._last_displayed_index: int = 0
        self._filter_step: str | None = None
        self._filter_path: str | None = None
        self._last_written_entry_type: StreamEntryType | None = None

    @property
    def filter_step(self) -> str | None:
        """Get the current step filter (legacy, use filter_path)."""
        return self._filter_step

    @filter_step.setter
    def filter_step(self, value: str | None) -> None:
        """Set the step filter (legacy compat, delegates to filter_path)."""
        self.filter_path = value

    @property
    def filter_path(self) -> str | None:
        """Get the current path filter.

        Returns:
            Step path to filter by, or None to show all entries.
        """
        return self._filter_path

    @filter_path.setter
    def filter_path(self, value: str | None) -> None:
        """Set the path filter and re-render entries.

        Filtering uses prefix matching: selecting "a/b" shows all
        entries whose step_path starts with "a/b/" or equals "a/b".

        Args:
            value: Step path to filter by, or None to show all.
        """
        if value == self._filter_path:
            return
        self._filter_path = value
        # Keep legacy filter_step in sync
        self._filter_step = value
        self._rerender_with_filter()

    def _matches_filter(self, entry: UnifiedStreamEntry) -> bool:
        """Check if an entry matches the current path filter.

        Uses prefix matching: filter "a/b" matches entries with
        step_path "a/b", "a/b/c", "a/b/c/d", etc. but not "a/bc".

        Entries with no step_path and no step_name (global events)
        always pass through.

        Args:
            entry: The entry to check.

        Returns:
            True if the entry should be displayed.
        """
        if self._filter_path is None:
            return True
        # Global events (no path or step_name) always shown
        if entry.step_path is None and entry.step_name is None:
            return True
        path = entry.step_path or entry.step_name or ""
        return path == self._filter_path or path.startswith(self._filter_path + "/")

    def _needs_blank_separator(self, entry: UnifiedStreamEntry) -> bool:
        """Check if a blank separator line should be inserted before this entry.

        Inserts a blank line when leaving a tool call group — i.e. the
        previous entry was TOOL_CALL/TOOL_RESULT and the new entry is not.

        Args:
            entry: The entry about to be written.

        Returns:
            True if a blank line should be inserted before this entry.
        """
        return (
            self._last_written_entry_type in _TOOL_GROUP_TYPES
            and entry.entry_type not in _TOOL_GROUP_TYPES
        )

    def _needs_step_separator(self, entry: UnifiedStreamEntry) -> bool:
        """Check if a visual step separator should be inserted before this entry.

        Inserts a horizontal rule when a new root-level step starts and
        there was already prior content in the stream. This creates clear
        visual breaks between workflow phases.

        Args:
            entry: The entry about to be written.

        Returns:
            True if a step separator should be inserted before this entry.
        """
        return (
            entry.entry_type == StreamEntryType.STEP_START
            and self._last_written_entry_type is not None
        )

    def _write_entry_to_richlog(
        self, richlog: RichLog, entry: UnifiedStreamEntry
    ) -> None:
        """Write a single entry to the RichLog, with optional separators.

        Args:
            richlog: The RichLog widget to write to.
            entry: The entry to render and write.
        """
        if self._needs_step_separator(entry):
            richlog.write(Text(""))
            richlog.write(Text("\u2500" * 60, style="dim"))
            richlog.write(Text(""))
        elif self._needs_blank_separator(entry):
            richlog.write(Text(""))

        richlog.write(self._render_entry(entry))
        self._last_written_entry_type = entry.entry_type

    def _rerender_with_filter(self) -> None:
        """Clear displayed entries and re-render with current filter applied."""
        if not self.is_mounted:
            return

        try:
            richlog = self.query_one("#stream-content", RichLog)
            richlog.clear()
            self._last_written_entry_type = None

            # Re-render matching entries from state
            for entry in self._state.entries:
                if self._matches_filter(entry):
                    self._write_entry_to_richlog(richlog, entry)

            # Reset tracking index to current total (so refresh_entries
            # won't re-add already-rendered entries)
            self._last_displayed_index = len(self._state.entries)

            # Scroll to bottom
            if self._state.auto_scroll:
                richlog.scroll_end(animate=False)
        except NoMatches:
            pass

    def compose(self) -> ComposeResult:
        """Compose the widget layout.

        Returns:
            ComposeResult containing header, stream content, and scroll indicator.
        """
        # Compact header
        yield Static(
            self._format_header(),
            classes="compact-header",
            id="unified-header",
        )

        # RichLog for streaming content
        richlog = RichLog(
            id="stream-content",
            markup=False,
            wrap=True,
            auto_scroll=self._state.auto_scroll,
            max_lines=5000,
        )
        yield richlog

        # Scroll paused indicator
        yield Static(
            "\u23f8 Auto-scroll paused - press 'f' to follow",
            classes="scroll-indicator",
            id="scroll-indicator",
        )

    def on_mount(self) -> None:
        """Write existing entries when the widget is mounted."""
        try:
            richlog = self.query_one("#stream-content", RichLog)
            for entry in self._state.entries:
                if self._matches_filter(entry):
                    self._write_entry_to_richlog(richlog, entry)
            self._last_displayed_index = len(self._state.entries)
        except NoMatches:
            pass

    def _format_header(self) -> str:
        """Format the compact header text.

        Returns:
            Formatted header string with workflow name, step, and elapsed time.
        """
        name = self._state.workflow_name or "Workflow"
        step_info = ""
        if self._state.current_step:
            step_info = (
                f"Step {self._state.current_step_number}/{self._state.total_steps}: "
                f"{self._state.current_step}"
            )
        else:
            step_info = f"Step 0/{self._state.total_steps}"

        elapsed = f"\\[{self._state.elapsed_formatted}]"

        return f"[bold]{name}[/bold]  {step_info}  [dim]{elapsed}[/dim]"

    def _render_entry(self, entry: UnifiedStreamEntry) -> Text:
        """Render a stream entry as a Rich Text object.

        Uses Text.append() with style arguments instead of Rich markup
        strings, so brackets in user content are never interpreted.

        Args:
            entry: The stream entry to render.

        Returns:
            A rich.text.Text object representing the entry.
        """
        # Format content with duration if present
        content = entry.content
        if entry.duration_ms is not None:
            duration_sec = entry.duration_ms / 1000
            if duration_sec >= 60:
                minutes = int(duration_sec) // 60
                seconds = int(duration_sec) % 60
                content = f"{content} ({minutes}m {seconds}s)"
            else:
                content = f"{content} ({duration_sec:.1f}s)"

        # Determine badge colour
        badge_color = _BADGE_COLORS.get(entry.entry_type)
        if entry.entry_type == StreamEntryType.STEP_OUTPUT and entry.level != "info":
            badge_color = _LEVEL_COLORS.get(entry.level, badge_color)

        # Determine content style
        content_style = _CONTENT_STYLES.get(entry.entry_type)
        if entry.entry_type == StreamEntryType.STEP_OUTPUT and entry.level != "info":
            content_style = _LEVEL_COLORS.get(entry.level, content_style)

        # Build Text object with styled spans
        text = Text()
        text.append(entry.badge, style=badge_color or "")
        text.append(" ")
        text.append(content, style=content_style or "")

        return text

    def add_entry(self, entry: UnifiedStreamEntry) -> None:
        """Add a new entry to the stream.

        Args:
            entry: The stream entry to add.
        """
        self._state.add_entry(entry)

        # Update current step tracking for step events
        if entry.entry_type == StreamEntryType.STEP_START:
            self._state.current_step = entry.source
            self._state.current_step_number += 1
            self._update_header()
        elif entry.entry_type in (
            StreamEntryType.STEP_COMPLETE,
            StreamEntryType.STEP_FAILED,
        ):
            self._update_header()

        # Mount the widget if we're mounted
        if self.is_mounted:
            self._mount_entry(entry)

    def _mount_entry(self, entry: UnifiedStreamEntry) -> None:
        """Write a new entry to the RichLog.

        Only writes the entry if it passes the current filter.

        Args:
            entry: The entry to write.
        """
        if not self._matches_filter(entry):
            return

        try:
            richlog = self.query_one("#stream-content", RichLog)
            self._write_entry_to_richlog(richlog, entry)

            # Auto-scroll if enabled
            if self._state.auto_scroll:
                richlog.scroll_end(animate=False)
        except NoMatches:
            pass

    def refresh_entries(self) -> None:
        """Refresh the display with all new entries since last refresh.

        This is called by the workflow execution screen after debouncing.
        Only displays entries matching the current step filter.
        """
        if not self.is_mounted:
            return

        try:
            richlog = self.query_one("#stream-content", RichLog)
            entries = self._state.entries
            total = len(entries)

            while self._last_displayed_index < total:
                entry = entries[self._last_displayed_index]
                self._last_displayed_index += 1
                if self._matches_filter(entry):
                    self._write_entry_to_richlog(richlog, entry)

            # Auto-scroll if enabled
            if self._state.auto_scroll:
                richlog.scroll_end(animate=False)
        except NoMatches:
            pass

    def _update_header(self) -> None:
        """Update the header with current status."""
        if not self.is_mounted:
            return

        try:
            header = self.query_one("#unified-header", Static)
            header.update(self._format_header())
        except NoMatches:
            pass

    def update_elapsed(self) -> None:
        """Update the elapsed time display.

        Called periodically by the execution screen.
        """
        self._update_header()

    def set_auto_scroll(self, enabled: bool) -> None:
        """Enable or disable auto-scrolling.

        Args:
            enabled: Whether to auto-scroll on new entries.
        """
        self._state.auto_scroll = enabled
        if self.is_mounted:
            try:
                richlog = self.query_one("#stream-content", RichLog)
                richlog.auto_scroll = enabled
            except NoMatches:
                pass
        self._update_scroll_indicator()

    def toggle_auto_scroll(self) -> None:
        """Toggle auto-scroll mode."""
        self.set_auto_scroll(not self._state.auto_scroll)

    def _update_scroll_indicator(self) -> None:
        """Update the scroll paused indicator visibility."""
        if not self.is_mounted:
            return

        try:
            indicator = self.query_one("#scroll-indicator", Static)
            if self._state.auto_scroll:
                indicator.remove_class("paused")
            else:
                indicator.add_class("paused")
        except NoMatches:
            pass

    def scroll_to_top(self) -> None:
        """Scroll to the top of the stream."""
        if not self.is_mounted:
            return

        try:
            richlog = self.query_one("#stream-content", RichLog)
            richlog.scroll_home(animate=False)
            # Pause auto-scroll when manually scrolling
            self.set_auto_scroll(False)
        except NoMatches:
            pass

    def scroll_to_bottom(self) -> None:
        """Scroll to the bottom of the stream."""
        if not self.is_mounted:
            return

        try:
            richlog = self.query_one("#stream-content", RichLog)
            richlog.scroll_end(animate=False)
        except NoMatches:
            pass

    def clear(self) -> None:
        """Clear all entries from the stream."""
        self._state.clear()
        self._last_displayed_index = 0
        self._last_written_entry_type = None

        if not self.is_mounted:
            return

        try:
            richlog = self.query_one("#stream-content", RichLog)
            richlog.clear()
            self._update_header()
        except NoMatches:
            pass

    def set_workflow_info(
        self,
        workflow_name: str,
        total_steps: int,
        start_time: float,
    ) -> None:
        """Set workflow information for the header.

        Args:
            workflow_name: Name of the workflow.
            total_steps: Total number of steps.
            start_time: Unix timestamp when workflow started.
        """
        self._state.workflow_name = workflow_name
        self._state.total_steps = total_steps
        self._state.start_time = start_time
        self._update_header()


class CompactHeader(Horizontal):
    """Compact single-line header for workflow status.

    Shows: workflow_name    Step N/M: step_name    [MM:SS]
    """

    DEFAULT_CSS = """
    CompactHeader {
        height: 1;
        background: $surface;
        padding: 0 1;
    }

    CompactHeader .workflow-name {
        color: $primary;
        text-style: bold;
        width: auto;
    }

    CompactHeader .spacer {
        width: 1fr;
    }

    CompactHeader .step-indicator {
        color: $text-muted;
        width: auto;
    }

    CompactHeader .elapsed {
        color: $text-disabled;
        width: auto;
        margin-left: 2;
    }
    """

    def __init__(
        self,
        workflow_name: str = "",
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Initialize the compact header.

        Args:
            workflow_name: Name of the workflow.
            name: Widget name.
            id: Widget ID.
            classes: CSS classes.
        """
        super().__init__(name=name, id=id, classes=classes)
        self._workflow_name = workflow_name
        self._current_step = ""
        self._step_number = 0
        self._total_steps = 0
        self._elapsed_seconds = 0

    def compose(self) -> ComposeResult:
        """Compose the header layout."""
        yield Static(
            f"[bold]{self._workflow_name}[/bold]",
            classes="workflow-name",
            id="header-name",
        )
        yield Static("", classes="spacer")
        yield Static(
            self._format_step_indicator(),
            classes="step-indicator",
            id="header-step",
        )
        yield Static(
            self._format_elapsed(),
            classes="elapsed",
            id="header-elapsed",
        )

    def _format_step_indicator(self) -> str:
        """Format the step indicator text."""
        if self._current_step:
            return f"Step {self._step_number}/{self._total_steps}: {self._current_step}"
        return f"Step {self._step_number}/{self._total_steps}"

    def _format_elapsed(self) -> str:
        """Format the elapsed time."""
        minutes = self._elapsed_seconds // 60
        seconds = self._elapsed_seconds % 60
        return f"[{minutes:02d}:{seconds:02d}]"

    def update_step(self, step_name: str, step_number: int, total_steps: int) -> None:
        """Update the current step display.

        Args:
            step_name: Name of the current step.
            step_number: 1-based step number.
            total_steps: Total number of steps.
        """
        self._current_step = step_name
        self._step_number = step_number
        self._total_steps = total_steps

        if self.is_mounted:
            try:
                step_widget = self.query_one("#header-step", Static)
                step_widget.update(self._format_step_indicator())
            except NoMatches:
                pass

    def update_elapsed(self, elapsed_seconds: int) -> None:
        """Update the elapsed time display.

        Args:
            elapsed_seconds: Total elapsed seconds.
        """
        self._elapsed_seconds = elapsed_seconds

        if self.is_mounted:
            try:
                elapsed_widget = self.query_one("#header-elapsed", Static)
                elapsed_widget.update(self._format_elapsed())
            except NoMatches:
                pass
