"""Demo of the AgentOutput widget.

This example demonstrates the AgentOutput widget with various message types.
Run with: python examples/agent_output_demo.py

Feature: 012-workflow-widgets
User Story: 2 - AgentOutput Widget
Date: 2025-12-17
"""

from __future__ import annotations

from datetime import datetime

from textual.app import App, ComposeResult
from textual.widgets import Footer, Header

from maverick.tui.models import AgentMessage, MessageType, ToolCallInfo
from maverick.tui.widgets import AgentOutput


class AgentOutputDemo(App[None]):
    """Demo app for AgentOutput widget."""

    CSS = """
    Screen {
        background: #1a1a1a;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("a", "add_message", "Add Message"),
        ("c", "clear", "Clear"),
        ("s", "toggle_scroll", "Toggle Auto-Scroll"),
    ]

    def compose(self) -> ComposeResult:
        """Compose the demo app."""
        yield Header()
        yield AgentOutput(id="agent-output")
        yield Footer()

    def on_mount(self) -> None:
        """Add some demo messages on mount."""
        output = self.query_one("#agent-output", AgentOutput)

        # Add various message types
        messages = [
            AgentMessage(
                id="1",
                timestamp=datetime.now(),
                agent_id="implementer",
                agent_name="Implementer",
                message_type=MessageType.TEXT,
                content="Starting implementation of feature X",
            ),
            AgentMessage(
                id="2",
                timestamp=datetime.now(),
                agent_id="implementer",
                agent_name="Implementer",
                message_type=MessageType.CODE,
                content=(
                    "def hello_world():\n"
                    '    """Print a greeting."""\n'
                    '    print("Hello, World!")'
                ),
                language="python",
            ),
            AgentMessage(
                id="3",
                timestamp=datetime.now(),
                agent_id="implementer",
                agent_name="Implementer",
                message_type=MessageType.TOOL_CALL,
                content="Creating pull request",
                tool_call=ToolCallInfo(
                    tool_name="create_pull_request",
                    arguments=(
                        '{"title": "feat: add hello world", '
                        '"body": "Adds greeting function"}'
                    ),
                    result='{"number": 123, "url": "https://github.com/repo/pull/123"}',
                ),
            ),
            AgentMessage(
                id="4",
                timestamp=datetime.now(),
                agent_id="reviewer",
                agent_name="Code Reviewer",
                message_type=MessageType.TEXT,
                content="Reviewing pull request #123",
            ),
            AgentMessage(
                id="5",
                timestamp=datetime.now(),
                agent_id="reviewer",
                agent_name="Code Reviewer",
                message_type=MessageType.TOOL_RESULT,
                content="Review complete: 2 suggestions, 0 errors",
            ),
        ]

        for msg in messages:
            output.add_message(msg)

    def action_add_message(self) -> None:
        """Add a new demo message."""
        output = self.query_one("#agent-output", AgentOutput)
        msg = AgentMessage(
            id=str(len(output.state.messages) + 1),
            timestamp=datetime.now(),
            agent_id="demo",
            agent_name="Demo Agent",
            message_type=MessageType.TEXT,
            content=f"Demo message #{len(output.state.messages) + 1}",
        )
        output.add_message(msg)

    def action_clear(self) -> None:
        """Clear all messages."""
        output = self.query_one("#agent-output", AgentOutput)
        output.clear_messages()

    def action_toggle_scroll(self) -> None:
        """Toggle auto-scroll."""
        output = self.query_one("#agent-output", AgentOutput)
        output.set_auto_scroll(not output.state.auto_scroll)
        status = "enabled" if output.state.auto_scroll else "disabled"
        self.notify(f"Auto-scroll {status}")


if __name__ == "__main__":
    app = AgentOutputDemo()
    app.run()
