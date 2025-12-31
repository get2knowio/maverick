"""AgentOutput widget for displaying streaming agent messages.

This widget displays real-time agent output with:
- Timestamped messages with agent identifiers
- Syntax highlighting for code blocks
- Collapsible tool calls (collapsed by default)
- Auto-scroll behavior with manual override
- Search functionality (Ctrl+F)
- Agent filtering
- 1000-message buffer limit

Feature: 012-workflow-widgets
User Story: 2 - AgentOutput Widget
Date: 2025-12-17
"""

from __future__ import annotations

import time

from rich.syntax import Syntax
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.css.query import NoMatches
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Collapsible, Static

from maverick.tui.metrics import widget_metrics
from maverick.tui.models import AgentMessage, AgentOutputState, MessageType


class AgentOutput(Widget):
    """Widget for displaying streaming agent output.

    Features:
    - Timestamps and agent identifiers for each message
    - Syntax highlighting for code blocks using Rich
    - Collapsible tool calls (collapsed by default)
    - Auto-scroll when at bottom, pauses when user scrolls up
    - "Scroll to bottom" indicator when auto-scroll is paused
    - Search with Ctrl+F (highlights matches)
    - Filter by agent name
    - Message buffer limit of 1000 (truncates oldest)
    - Empty state message when no output yet

    Messages Emitted:
        SearchActivated: When Ctrl+F is pressed
        ToolCallExpanded: When a tool call section is expanded
        ToolCallCollapsed: When a tool call section is collapsed

    Example:
        output = AgentOutput()
        output.add_message(message_data)
        output.set_search_query("error")
    """

    DEFAULT_CSS = """
    AgentOutput {
        height: 100%;
        width: 100%;
    }

    AgentOutput VerticalScroll {
        height: 100%;
        width: 100%;
        background: $surface;
        border: solid $border;
        padding: 1;
    }

    AgentOutput .empty-state {
        height: 100%;
        width: 100%;
        content-align: center middle;
        color: $text-muted;
    }

    AgentOutput .message-container {
        width: 100%;
        margin: 0 0 1 0;
    }

    AgentOutput .message-header {
        color: $text-muted;
        text-style: dim;
    }

    AgentOutput .message-content {
        color: $text;
        margin: 0 0 0 2;
    }

    AgentOutput .code-block {
        background: $surface-elevated;
        border: solid $border;
        padding: 1;
        margin: 0 0 0 2;
    }

    AgentOutput .tool-call {
        margin: 0 0 0 2;
    }

    AgentOutput .tool-call-header {
        color: $info;
        text-style: bold;
    }

    AgentOutput .tool-call-content {
        color: $text-muted;
        margin: 0 0 0 2;
    }

    AgentOutput .search-match {
        background: $warning 40%;
        color: $text;
    }

    AgentOutput .scroll-indicator {
        dock: bottom;
        height: 1;
        width: 100%;
        background: $info 30%;
        color: $text;
        text-align: center;
        display: none;
    }

    AgentOutput .scroll-indicator.visible {
        display: block;
    }

    AgentOutput .match-counter {
        dock: top;
        height: 1;
        width: 100%;
        background: $surface-elevated;
        color: $text-muted;
        text-align: right;
        padding: 0 1;
        display: none;
    }

    AgentOutput .match-counter.visible {
        display: block;
    }
    """

    BINDINGS = [
        Binding("ctrl+f", "activate_search", "Search", show=True),
        Binding("escape", "clear_search", "Clear Search", show=False),
        Binding("f3", "next_match", "Next Match", show=True),
        Binding("shift+f3", "prev_match", "Previous Match", show=True),
        Binding("enter", "next_match", "Next Match", show=False),
        Binding("pageup", "page_up", "Page Up", show=False),
        Binding("pagedown", "page_down", "Page Down", show=False),
        Binding("home", "scroll_home", "Go to top", show=False),
        Binding("end", "scroll_end", "Go to bottom", show=False),
    ]

    # Reactive state
    state: reactive[AgentOutputState] = reactive(AgentOutputState)
    show_scroll_indicator: reactive[bool] = reactive(False)

    # Messages
    class SearchActivated(Message):
        """Emitted when Ctrl+F is pressed."""

        pass

    class ToolCallExpanded(Message):
        """Emitted when a tool call is expanded."""

        def __init__(self, message_id: str, tool_name: str) -> None:
            """Initialize the message.

            Args:
                message_id: ID of the message containing the tool call.
                tool_name: Name of the tool being called.
            """
            super().__init__()
            self.message_id = message_id
            self.tool_name = tool_name

    class ToolCallCollapsed(Message):
        """Emitted when a tool call is collapsed."""

        def __init__(self, message_id: str, tool_name: str) -> None:
            """Initialize the message.

            Args:
                message_id: ID of the message containing the tool call.
                tool_name: Name of the tool being called.
            """
            super().__init__()
            self.message_id = message_id
            self.tool_name = tool_name

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
        disabled: bool = False,
    ) -> None:
        """Initialize the AgentOutput widget.

        Args:
            name: The name of the widget.
            id: The ID of the widget in the DOM.
            classes: The CSS classes for the widget.
            disabled: Whether the widget is disabled.
        """
        super().__init__(name=name, id=id, classes=classes, disabled=disabled)
        self.state = AgentOutputState()

    def compose(self) -> ComposeResult:
        """Compose the widget's child widgets.

        Returns:
            ComposeResult containing the vertical scroll container.
        """
        yield Static(
            "",
            classes="match-counter",
            id="match-counter",
        )
        with VerticalScroll(id="message-scroll"):
            if self.state.is_empty:
                yield Static(
                    "No agent output yet. Output will appear when workflow runs.",
                    classes="empty-state",
                    id="empty-state",
                )
        yield Static(
            "Scroll to bottom",
            classes="scroll-indicator",
            id="scroll-indicator",
        )

    def add_message(self, message: AgentMessage) -> None:
        """Add a new agent message to the output.

        Messages are appended to the buffer. If buffer exceeds max_messages,
        oldest messages are discarded.

        Args:
            message: The message data to add.
        """
        # Track message throughput
        widget_metrics.record_message("AgentOutput")

        # Add to state first
        self.state.add_message(message)

        # Only render if widget is mounted
        if not self.is_mounted:
            return

        # Remove empty state if present
        if len(self.state.messages) == 1:  # First message
            try:
                empty_state = self.query_one("#empty-state", Static)
                empty_state.remove()
            except NoMatches:
                # Empty state widget not present (already removed or never created)
                pass

        # Render the message
        self._render_message(message)

        # Auto-scroll if enabled and at bottom
        if self.state.auto_scroll:
            self.scroll_to_bottom()

    def _render_message(self, message: AgentMessage, message_index: int = -1) -> None:
        """Render a single message to the display.

        Args:
            message: The message to render.
            message_index: Index in filtered_messages (for search highlighting).
        """
        # Track render time
        start_time = time.perf_counter() if widget_metrics.enabled else 0.0

        scroll_container = self.query_one("#message-scroll", VerticalScroll)

        # Create message container
        with scroll_container:
            container = Static(classes="message-container")
            container.mount(self._create_message_header(message))

            # Render based on message type
            if message.message_type == MessageType.TEXT:
                container.mount(self._create_text_content(message, message_index))
            elif message.message_type == MessageType.CODE:
                container.mount(self._create_code_content(message))
            elif message.message_type == MessageType.TOOL_CALL:
                container.mount(self._create_tool_call_content(message))
            elif message.message_type == MessageType.TOOL_RESULT:
                container.mount(
                    self._create_tool_result_content(message, message_index)
                )

            scroll_container.mount(container)

        # Record render time
        if widget_metrics.enabled:
            duration_ms = (time.perf_counter() - start_time) * 1000
            widget_metrics.record_render("AgentOutput", duration_ms)

    def _create_message_header(self, message: AgentMessage) -> Static:
        """Create the message header with timestamp and agent name.

        Args:
            message: The message to create header for.

        Returns:
            Static widget with formatted header.
        """
        timestamp_str = message.timestamp.strftime("%H:%M:%S")
        header_text = f"[{timestamp_str}] {message.agent_name}"
        return Static(header_text, classes="message-header")

    def _create_text_content(
        self, message: AgentMessage, message_index: int = -1
    ) -> Static:
        """Create text message content.

        Args:
            message: The message to render.
            message_index: Index in filtered_messages (for search highlighting).

        Returns:
            Static widget with message content.
        """
        content = self._highlight_search(message.content, message_index)
        return Static(content, classes="message-content", markup=True)

    def _create_code_content(self, message: AgentMessage) -> Static:
        """Create code message content with syntax highlighting.

        Args:
            message: The message to render.

        Returns:
            Static widget with syntax-highlighted code.
        """
        # Create syntax-highlighted code
        syntax = Syntax(
            message.content,
            message.language or "text",
            theme="monokai",
            line_numbers=True,
        )
        code_widget = Static(classes="code-block")
        code_widget.update(syntax)
        return code_widget

    def _create_tool_call_content(self, message: AgentMessage) -> Collapsible | Static:
        """Create collapsible tool call content.

        Args:
            message: The message to render.

        Returns:
            Collapsible widget containing tool call details, or Static if no details.
        """
        if message.tool_call is None:
            return Static("Tool call (no details)", classes="tool-call")

        # Create collapsible section
        title = f"Tool Call: {message.tool_call.tool_name}"
        collapsible = Collapsible(
            title=title,
            collapsed=True,  # Collapsed by default
            classes="tool-call",
        )

        # Add tool call details
        with collapsible:
            collapsible.mount(
                Static(
                    f"Arguments: {message.tool_call.arguments}",
                    classes="tool-call-content",
                )
            )
            if message.tool_call.result:
                collapsible.mount(
                    Static(
                        f"Result: {message.tool_call.result}",
                        classes="tool-call-content",
                    )
                )

        return collapsible

    def _create_tool_result_content(
        self, message: AgentMessage, message_index: int = -1
    ) -> Static:
        """Create tool result content.

        Args:
            message: The message to render.
            message_index: Index in filtered_messages (for search highlighting).

        Returns:
            Static widget with result content.
        """
        content = self._highlight_search(f"Result: {message.content}", message_index)
        return Static(content, classes="message-content", markup=True)

    def _highlight_search(self, text: str, message_index: int = -1) -> str:
        """Highlight search matches in text.

        Args:
            text: The text to process.
            message_index: Index in filtered_messages (for tracking current match).

        Returns:
            Text with search matches highlighted using Rich markup.
        """
        if not self.state.search_query:
            return text

        # Simple case-insensitive highlighting
        query = self.state.search_query
        # Use Rich markup to highlight matches
        import re

        pattern = re.compile(re.escape(query), re.IGNORECASE)

        # Track which match in this message is the current match
        current_match_offset = -1
        if self.state.current_match_index >= 0 and self.state.current_match_index < len(
            self.state.match_positions
        ):
            msg_idx, char_offset = self.state.match_positions[
                self.state.current_match_index
            ]
            if msg_idx == message_index:
                current_match_offset = char_offset

        # Highlight matches, with special highlighting for current match
        def replace_match(match: re.Match[str]) -> str:
            # Check if this is the current match
            if match.start() == current_match_offset:
                # Current match: bright highlight
                return (
                    f"[black on bright_yellow]{match.group(0)}[/black on bright_yellow]"
                )
            else:
                # Other matches: dim highlight
                return f"[on yellow]{match.group(0)}[/on yellow]"

        highlighted = pattern.sub(replace_match, text)
        return highlighted

    def clear_messages(self) -> None:
        """Clear all messages from the output."""
        self.state.messages.clear()

        # Only modify DOM if mounted
        if not self.is_mounted:
            return

        # Remove all message containers
        try:
            scroll_container = self.query_one("#message-scroll", VerticalScroll)
            for child in list(scroll_container.children):
                child.remove()

            # Show empty state
            scroll_container.mount(
                Static(
                    "No agent output yet. Output will appear when workflow runs.",
                    classes="empty-state",
                    id="empty-state",
                )
            )
        except NoMatches:
            # Scroll container not found (widget not mounted or already removed)
            pass

    def set_auto_scroll(self, enabled: bool) -> None:
        """Enable or disable auto-scrolling.

        Args:
            enabled: Whether to auto-scroll on new messages.
        """
        self.state.auto_scroll = enabled
        self.show_scroll_indicator = not enabled

    def scroll_to_bottom(self) -> None:
        """Scroll to the bottom of the output and re-enable auto-scroll."""
        try:
            scroll_container = self.query_one("#message-scroll", VerticalScroll)
            scroll_container.scroll_end(animate=False)
            self.set_auto_scroll(True)
        except NoMatches:
            # Scroll container not found (widget not mounted yet)
            pass

    def set_search_query(self, query: str | None) -> None:
        """Set the search filter query.

        Args:
            query: Search string to filter/highlight, or None to clear.
        """
        self.state.search_query = query

        # Compute match positions if query is set
        if query:
            self._compute_match_positions()
            # Start at first match
            self.state.current_match_index = 0 if self.state.total_matches > 0 else -1
        else:
            # Clear match tracking
            self.state.match_positions.clear()
            self.state.current_match_index = -1
            self.state.total_matches = 0

        # Re-render all messages to update highlighting
        self._refresh_display()

        # Update match counter display
        self._update_match_counter()

    def _compute_match_positions(self) -> None:
        """Compute all match positions for the current search query."""
        self.state.match_positions.clear()
        self.state.total_matches = 0

        if not self.state.search_query:
            return

        import re

        pattern = re.compile(re.escape(self.state.search_query), re.IGNORECASE)

        # Search through filtered messages
        filtered_messages = self.state.filtered_messages
        for msg_idx, message in enumerate(filtered_messages):
            # Search in message content
            for match in pattern.finditer(message.content):
                self.state.match_positions.append((msg_idx, match.start()))
                self.state.total_matches += 1

    def set_agent_filter(self, agent_id: str | None) -> None:
        """Filter messages to a specific agent.

        Args:
            agent_id: Agent ID to filter by, or None to show all.
        """
        self.state.filter_agent = agent_id
        self._refresh_display()

    def set_message_type_filter(self, message_type: MessageType | None) -> None:
        """Filter messages to a specific message type.

        FR-016: Support filtering by message type (text, code, tool_call, tool_result).

        Args:
            message_type: Message type to filter by, or None to show all.
        """
        self.state.filter_message_type = message_type
        self._refresh_display()

    def _refresh_display(self) -> None:
        """Refresh the entire display based on current filters."""
        # Track render time for full refresh
        start_time = time.perf_counter() if widget_metrics.enabled else 0.0

        # Only refresh if mounted
        if not self.is_mounted:
            return

        try:
            # Clear current display
            scroll_container = self.query_one("#message-scroll", VerticalScroll)
            for child in list(scroll_container.children):
                child.remove()

            # Re-render filtered messages
            filtered = self.state.filtered_messages
            if not filtered:
                scroll_container.mount(
                    Static(
                        "No messages match the current filters.",
                        classes="empty-state",
                        id="empty-state",
                    )
                )
            else:
                for idx, msg in enumerate(filtered):
                    self._render_message(msg, idx)

            # Record render time for full refresh
            if widget_metrics.enabled:
                duration_ms = (time.perf_counter() - start_time) * 1000
                widget_metrics.record_render(
                    "AgentOutput._refresh_display", duration_ms
                )
        except NoMatches:
            # Scroll container not found (widget not mounted yet)
            pass

    def action_activate_search(self) -> None:
        """Activate search mode (Ctrl+F)."""
        self.post_message(self.SearchActivated())

    def action_clear_search(self) -> None:
        """Clear search query (Escape)."""
        self.set_search_query(None)

    def action_next_match(self) -> None:
        """Navigate to next search match (F3 or Enter).

        Wraps around to the first match when reaching the end.
        """
        if not self.state.search_query or self.state.total_matches == 0:
            return

        # Move to next match
        if self.state.current_match_index < self.state.total_matches - 1:
            self.state.current_match_index += 1
        else:
            # Wrap around to first match
            self.state.current_match_index = 0

        # Scroll to the match
        self._scroll_to_current_match()

        # Update match counter
        self._update_match_counter()

    def action_prev_match(self) -> None:
        """Navigate to previous search match (Shift+F3).

        Wraps around to the last match when reaching the beginning.
        """
        if not self.state.search_query or self.state.total_matches == 0:
            return

        # Move to previous match
        if self.state.current_match_index > 0:
            self.state.current_match_index -= 1
        else:
            # Wrap around to last match
            self.state.current_match_index = self.state.total_matches - 1

        # Scroll to the match
        self._scroll_to_current_match()

        # Update match counter
        self._update_match_counter()

    def _scroll_to_current_match(self) -> None:
        """Scroll to the currently selected match."""
        if self.state.current_match_index < 0 or self.state.current_match_index >= len(
            self.state.match_positions
        ):
            return

        # Get the message index for the current match
        message_index, _ = self.state.match_positions[self.state.current_match_index]

        # Refresh display to update highlighting
        self._refresh_display()

        # Scroll to the message (message containers are scroll children)
        try:
            scroll_container = self.query_one("#message-scroll", VerticalScroll)
            # Get all message containers
            message_containers = list(scroll_container.query(".message-container"))
            if message_index < len(message_containers):
                message_containers[message_index].scroll_visible(animate=False)
        except (NoMatches, IndexError):
            # Container not found or index out of range
            pass

    def _update_match_counter(self) -> None:
        """Update the match counter display."""
        if not self.is_mounted:
            return

        try:
            counter = self.query_one("#match-counter", Static)
            if self.state.search_query and self.state.total_matches > 0:
                # Show counter with current position
                counter_text = (
                    f"Match {self.state.current_match_index + 1} "
                    f"of {self.state.total_matches}"
                )
                counter.update(counter_text)
                counter.set_class(True, "visible")
            else:
                # Hide counter
                counter.set_class(False, "visible")
        except NoMatches:
            # Counter not found (widget not mounted yet)
            pass

    def watch_show_scroll_indicator(self, show: bool) -> None:
        """Update scroll indicator visibility.

        Args:
            show: Whether to show the indicator.
        """
        try:
            indicator = self.query_one("#scroll-indicator", Static)
            indicator.set_class(show, "visible")
        except NoMatches:
            # Scroll indicator not found (widget not mounted yet)
            pass

    def on_mount(self) -> None:
        """Handle widget mount event to set up scroll detection.

        FR-013: Widget MUST pause auto-scroll when user scrolls up manually.
        """
        # Get the scroll container
        scroll_container = self.query_one("#message-scroll", VerticalScroll)

        # Watch the scroll_y reactive to detect user scrolling
        def watch_scroll(old_value: float, new_value: float) -> None:
            """Detect when user scrolls to pause/resume auto-scroll."""
            # Check if at bottom (within 1px threshold for float precision)
            at_bottom = new_value >= scroll_container.max_scroll_y - 1

            if at_bottom and not self.state.auto_scroll:
                # User scrolled back to bottom, re-enable auto-scroll
                self.set_auto_scroll(True)
            elif not at_bottom and self.state.auto_scroll:
                # User scrolled up, pause auto-scroll
                self.set_auto_scroll(False)

        # Use Textual's watch method to monitor scroll_y changes
        scroll_container.watch(scroll_container, "scroll_y", watch_scroll)

    # =========================================================================
    # Keyboard Navigation Actions
    # =========================================================================

    def action_page_up(self) -> None:
        """Scroll up by one page."""
        try:
            scroll_container = self.query_one("#message-scroll", VerticalScroll)
            scroll_container.scroll_page_up()
            self.set_auto_scroll(False)
        except NoMatches:
            # Scroll container not found (widget not mounted yet)
            pass

    def action_page_down(self) -> None:
        """Scroll down by one page."""
        try:
            scroll_container = self.query_one("#message-scroll", VerticalScroll)
            scroll_container.scroll_page_down()
            # Check if at bottom
            if scroll_container.scroll_offset.y >= scroll_container.max_scroll_y:
                self.set_auto_scroll(True)
        except NoMatches:
            # Scroll container not found (widget not mounted yet)
            pass

    def action_scroll_home(self) -> None:
        """Scroll to the top."""
        try:
            scroll_container = self.query_one("#message-scroll", VerticalScroll)
            scroll_container.scroll_home()
            self.set_auto_scroll(False)
        except NoMatches:
            # Scroll container not found (widget not mounted yet)
            pass

    def action_scroll_end(self) -> None:
        """Scroll to the bottom."""
        self.scroll_to_bottom()
        self.set_auto_scroll(True)
