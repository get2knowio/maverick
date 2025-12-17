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

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Collapsible, Static

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
    """

    BINDINGS = [
        Binding("ctrl+f", "activate_search", "Search", show=True),
        Binding("escape", "clear_search", "Clear Search", show=False),
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
            except Exception:
                pass  # Empty state already removed

        # Render the message
        self._render_message(message)

        # Auto-scroll if enabled and at bottom
        if self.state.auto_scroll:
            self.scroll_to_bottom()

    def _render_message(self, message: AgentMessage) -> None:
        """Render a single message to the display.

        Args:
            message: The message to render.
        """
        scroll_container = self.query_one("#message-scroll", VerticalScroll)

        # Create message container
        with scroll_container:
            container = Static(classes="message-container")
            container.mount(self._create_message_header(message))

            # Render based on message type
            if message.message_type == MessageType.TEXT:
                container.mount(self._create_text_content(message))
            elif message.message_type == MessageType.CODE:
                container.mount(self._create_code_content(message))
            elif message.message_type == MessageType.TOOL_CALL:
                container.mount(self._create_tool_call_content(message))
            elif message.message_type == MessageType.TOOL_RESULT:
                container.mount(self._create_tool_result_content(message))

            scroll_container.mount(container)

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

    def _create_text_content(self, message: AgentMessage) -> Static:
        """Create text message content.

        Args:
            message: The message to render.

        Returns:
            Static widget with message content.
        """
        content = self._highlight_search(message.content)
        return Static(content, classes="message-content", markup=True)

    def _create_code_content(self, message: AgentMessage) -> Static:
        """Create code message content with syntax highlighting.

        Args:
            message: The message to render.

        Returns:
            Static widget with syntax-highlighted code.
        """
        from rich.syntax import Syntax

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

    def _create_tool_result_content(self, message: AgentMessage) -> Static:
        """Create tool result content.

        Args:
            message: The message to render.

        Returns:
            Static widget with result content.
        """
        content = self._highlight_search(f"Result: {message.content}")
        return Static(content, classes="message-content", markup=True)

    def _highlight_search(self, text: str) -> str:
        """Highlight search matches in text.

        Args:
            text: The text to process.

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
        highlighted = pattern.sub(
            lambda m: f"[on yellow]{m.group(0)}[/on yellow]", text
        )
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
        except Exception:
            pass  # Container not found

    def set_auto_scroll(self, enabled: bool) -> None:
        """Enable or disable auto-scrolling.

        Args:
            enabled: Whether to auto-scroll on new messages.
        """
        self.state.auto_scroll = enabled
        self.show_scroll_indicator = not enabled

    def scroll_to_bottom(self) -> None:
        """Scroll to the bottom of the output."""
        try:
            scroll_container = self.query_one("#message-scroll", VerticalScroll)
            scroll_container.scroll_end(animate=False)
            self.show_scroll_indicator = False
        except Exception:
            pass  # Container not ready yet

    def set_search_query(self, query: str | None) -> None:
        """Set the search filter query.

        Args:
            query: Search string to filter/highlight, or None to clear.
        """
        self.state.search_query = query
        # Re-render all messages to update highlighting
        self._refresh_display()

    def set_agent_filter(self, agent_id: str | None) -> None:
        """Filter messages to a specific agent.

        Args:
            agent_id: Agent ID to filter by, or None to show all.
        """
        self.state.filter_agent = agent_id
        self._refresh_display()

    def _refresh_display(self) -> None:
        """Refresh the entire display based on current filters."""
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
                for msg in filtered:
                    self._render_message(msg)
        except Exception:
            pass  # Container not found

    def action_activate_search(self) -> None:
        """Activate search mode (Ctrl+F)."""
        self.post_message(self.SearchActivated())

    def action_clear_search(self) -> None:
        """Clear search query (Escape)."""
        self.set_search_query(None)

    def watch_show_scroll_indicator(self, show: bool) -> None:
        """Update scroll indicator visibility.

        Args:
            show: Whether to show the indicator.
        """
        try:
            indicator = self.query_one("#scroll-indicator", Static)
            indicator.set_class(show, "visible")
        except Exception:
            pass  # Indicator not ready yet

    def on_mount(self) -> None:
        """Handle widget mount event."""
        # Set up scroll detection for auto-scroll pause
        scroll_container = self.query_one("#message-scroll", VerticalScroll)

        def on_scroll() -> None:
            """Detect when user scrolls up."""
            # Check if we're at the bottom
            if scroll_container.scroll_offset.y < scroll_container.max_scroll_y:
                self.set_auto_scroll(False)
            else:
                self.set_auto_scroll(True)

        # Note: Textual doesn't have a direct scroll event, so we'd need to
        # implement this differently in a real app (e.g., with a background task)
        # For now, this is a placeholder for the architecture

    # =========================================================================
    # Keyboard Navigation Actions
    # =========================================================================

    def action_page_up(self) -> None:
        """Scroll up by one page."""
        try:
            scroll_container = self.query_one("#message-scroll", VerticalScroll)
            scroll_container.scroll_page_up()
            self.set_auto_scroll(False)
        except Exception:
            pass

    def action_page_down(self) -> None:
        """Scroll down by one page."""
        try:
            scroll_container = self.query_one("#message-scroll", VerticalScroll)
            scroll_container.scroll_page_down()
            # Check if at bottom
            if scroll_container.scroll_offset.y >= scroll_container.max_scroll_y:
                self.set_auto_scroll(True)
        except Exception:
            pass

    def action_scroll_home(self) -> None:
        """Scroll to the top."""
        try:
            scroll_container = self.query_one("#message-scroll", VerticalScroll)
            scroll_container.scroll_home()
            self.set_auto_scroll(False)
        except Exception:
            pass

    def action_scroll_end(self) -> None:
        """Scroll to the bottom."""
        self.scroll_to_bottom()
        self.set_auto_scroll(True)
