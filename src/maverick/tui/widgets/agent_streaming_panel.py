"""AgentStreamingPanel widget for real-time agent output streaming.

This widget provides a collapsible panel for displaying real-time agent
streaming output with:
- Collapsible header with current source display
- Scrollable content area with auto-scroll support
- Different styling for output, thinking, and error chunks
- FIFO buffer management for memory efficiency

Feature: 030-tui-execution-visibility
User Story: 2 - Monitor Agent Activity in Real-Time
Date: 2026-01-12
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import ScrollableContainer
from textual.css.query import NoMatches
from textual.widget import Widget
from textual.widgets import Static

from maverick.tui.models.widget_state import AgentStreamEntry, StreamingPanelState


class AgentStreamingPanel(Widget):
    """Collapsible panel for real-time agent output.

    This widget displays streaming agent output with support for:
    - Header showing current source (step and agent name)
    - Collapsible content area
    - Different styling for OUTPUT, THINKING, and ERROR chunks
    - Auto-scroll behavior when enabled
    - FIFO buffer eviction when size limit is reached

    Attributes:
        _state: The StreamingPanelState managing entries and visibility.

    Example:
        state = StreamingPanelState()
        panel = AgentStreamingPanel(state)

        # Add streaming chunks
        entry = AgentStreamEntry(
            timestamp=time.time(),
            step_name="implement_task",
            agent_name="ImplementerAgent",
            text="Starting implementation...",
            chunk_type=StreamChunkType.OUTPUT,
        )
        panel.append_chunk(entry)

        # Toggle visibility
        panel.toggle_visibility()
    """

    DEFAULT_CSS = """
    AgentStreamingPanel {
        height: auto;
        max-height: 50%;
        border: solid #00aaff;
    }

    AgentStreamingPanel .header {
        background: #242424;
        padding: 0 1;
    }

    AgentStreamingPanel .content {
        padding: 1;
    }

    AgentStreamingPanel.collapsed .content {
        display: none;
    }

    /* Chunk type styling */
    AgentStreamingPanel .chunk {
        width: 100%;
    }

    AgentStreamingPanel .chunk-output {
        color: #e0e0e0;
    }

    AgentStreamingPanel .chunk-thinking {
        color: #808080;
        text-style: italic;
    }

    AgentStreamingPanel .chunk-error {
        color: #f44336;
    }
    """

    def __init__(
        self,
        state: StreamingPanelState,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
        disabled: bool = False,
    ) -> None:
        """Initialize the AgentStreamingPanel widget.

        Args:
            state: The StreamingPanelState managing entries and visibility.
            name: The name of the widget.
            id: The ID of the widget in the DOM.
            classes: The CSS classes for the widget.
            disabled: Whether the widget is disabled.
        """
        super().__init__(name=name, id=id, classes=classes, disabled=disabled)
        self._state = state

    def compose(self) -> ComposeResult:
        """Compose the widget's child widgets.

        Returns:
            ComposeResult containing the header and scrollable content.
        """
        header_text = "Agent Output"
        if self._state.current_source:
            header_text = f"Agent Output: {self._state.current_source}"

        # Add auto-scroll indicator when disabled
        if not self._state.auto_scroll:
            header_text = f"{header_text} [SCROLL PAUSED]"

        yield Static(header_text, classes="header", id="streaming-header")
        with ScrollableContainer(classes="content", id="streaming-content"):
            for entry in self._state.entries:
                yield Static(
                    entry.text,
                    classes=f"chunk chunk-{entry.chunk_type.value}",
                )

    def append_chunk(self, entry: AgentStreamEntry) -> None:
        """Add new chunk and scroll if auto-scroll enabled.

        This method adds the entry to the internal state and mounts
        a new Static widget for the chunk. If auto_scroll is enabled,
        it scrolls the content to the end.

        Args:
            entry: The streaming entry to add.
        """
        self._state.add_entry(entry)

        # Only modify DOM if mounted
        if not self.is_mounted:
            return

        try:
            # Add to content container
            content = self.query_one(".content", ScrollableContainer)
            content.mount(
                Static(
                    entry.text,
                    classes=f"chunk chunk-{entry.chunk_type.value}",
                )
            )

            # Auto-scroll if enabled
            if self._state.auto_scroll:
                content.scroll_end(animate=False)

            # Update header with new source
            self._update_header()
        except NoMatches:
            # Content container not found (widget not mounted yet)
            pass

    def toggle_visibility(self) -> None:
        """Toggle panel expand/collapse.

        This method toggles the visible state and adds/removes
        the 'collapsed' CSS class to hide/show the content.
        """
        self._state.visible = not self._state.visible
        self.toggle_class("collapsed")

    def _update_header(self) -> None:
        """Update the header text with current source and auto-scroll status."""
        if not self.is_mounted:
            return

        try:
            header = self.query_one("#streaming-header", Static)
            header_text = "Agent Output"
            if self._state.current_source:
                header_text = f"Agent Output: {self._state.current_source}"

            # Add auto-scroll indicator when disabled
            if not self._state.auto_scroll:
                header_text = f"{header_text} [SCROLL PAUSED]"

            header.update(header_text)
        except NoMatches:
            # Header not found (widget not mounted yet)
            pass

    def clear(self) -> None:
        """Clear all entries from the panel.

        This method clears the internal state and removes all
        chunk widgets from the content container.
        """
        self._state.clear()

        # Only modify DOM if mounted
        if not self.is_mounted:
            return

        try:
            content = self.query_one(".content", ScrollableContainer)
            for child in list(content.children):
                child.remove()
            self._update_header()
        except NoMatches:
            # Content container not found (widget not mounted yet)
            pass

    def set_auto_scroll(self, enabled: bool) -> None:
        """Enable or disable auto-scrolling.

        Args:
            enabled: Whether to auto-scroll on new chunks.
        """
        self._state.auto_scroll = enabled
        self._update_header()

    def toggle_auto_scroll(self) -> None:
        """Toggle auto-scroll on/off.

        Convenience method that inverts the current auto_scroll state.
        Useful for keyboard shortcuts or toggle buttons.
        """
        self.set_auto_scroll(not self._state.auto_scroll)

    def scroll_to_top(self) -> None:
        """Scroll content to top for history review.

        This method scrolls the content container to the beginning,
        allowing users to review earlier entries in the streaming history.
        """
        if not self.is_mounted:
            return

        try:
            content = self.query_one(".content", ScrollableContainer)
            content.scroll_home(animate=False)
        except NoMatches:
            pass

    def scroll_to_bottom(self) -> None:
        """Scroll content to bottom.

        This method scrolls the content container to the end,
        showing the most recent entries. Useful after manually
        reviewing history to return to the latest output.
        """
        if not self.is_mounted:
            return

        try:
            content = self.query_one(".content", ScrollableContainer)
            content.scroll_end(animate=False)
        except NoMatches:
            pass
