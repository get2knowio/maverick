"""Tests for StreamingContext text→tool transitions.

Verifies that StreamingContext.emit_tool() inserts a newline before
tool calls that follow text output, preventing same-line rendering.
"""

from __future__ import annotations

import pytest

from maverick.dsl.events import AgentStreamChunk, StepOutput
from maverick.dsl.streaming import StreamingContext


class TestStreamingContextTextToToolTransition:
    """Test text→tool newline insertion in StreamingContext.emit_tool()."""

    @pytest.mark.asyncio
    async def test_emit_tool_after_text_inserts_newline(self) -> None:
        """Tool call emitted after text gets a leading newline."""
        emitted: list[str] = []

        async def capture(event: AgentStreamChunk | StepOutput) -> None:
            if isinstance(event, AgentStreamChunk):
                emitted.append(event.text)

        async with StreamingContext(capture, "test-step") as stream:
            await stream.emit_text("Starting analysis...")
            await stream.emit_tool("Read", {"file_path": "foo.py"})

        # Tool output should start with \n
        assert len(emitted) == 2
        assert emitted[1].startswith("\n"), (
            f"Expected tool call to start with newline after text, got: {emitted[1]!r}"
        )
        assert "\u2514 Read:" in emitted[1]

    @pytest.mark.asyncio
    async def test_emit_tool_without_preceding_text_no_newline(self) -> None:
        """First tool call without preceding text should NOT get extra newline."""
        emitted: list[str] = []

        async def capture(event: AgentStreamChunk | StepOutput) -> None:
            if isinstance(event, AgentStreamChunk):
                emitted.append(event.text)

        async with StreamingContext(capture, "test-step") as stream:
            await stream.emit_tool("Read", {"file_path": "foo.py"})

        assert len(emitted) == 1
        assert not emitted[0].startswith("\n"), (
            f"First tool call should not get extra newline, got: {emitted[0]!r}"
        )

    @pytest.mark.asyncio
    async def test_emit_tool_after_tool_no_extra_newline(self) -> None:
        """Consecutive tool calls should NOT get extra newlines between them."""
        emitted: list[str] = []

        async def capture(event: AgentStreamChunk | StepOutput) -> None:
            if isinstance(event, AgentStreamChunk):
                emitted.append(event.text)

        async with StreamingContext(capture, "test-step") as stream:
            await stream.emit_tool("Read", {"file_path": "foo.py"})
            await stream.emit_tool("Write", {"file_path": "bar.py"})

        assert len(emitted) == 2
        # Second tool should NOT get extra newline (tool→tool transition)
        assert not emitted[1].startswith("\n"), (
            f"Consecutive tool calls should not get extra newlines, got: {emitted[1]!r}"
        )

    @pytest.mark.asyncio
    async def test_emit_text_after_tool_adds_blank_line(self) -> None:
        """Text emitted after tool call gets single newline for spacing."""
        emitted: list[str] = []

        async def capture(event: AgentStreamChunk | StepOutput) -> None:
            if isinstance(event, AgentStreamChunk):
                emitted.append(event.text)

        async with StreamingContext(capture, "test-step") as stream:
            await stream.emit_tool("Read", {"file_path": "foo.py"})
            await stream.emit_text("Analysis complete.")

        assert len(emitted) == 2
        assert emitted[1].startswith("\n"), (
            f"Text after tool should get newline, got: {emitted[1]!r}"
        )
        assert not emitted[1].startswith("\n\n"), (
            "Text after tool should get single newline, "
            f"not double, got: {emitted[1]!r}"
        )

    @pytest.mark.asyncio
    async def test_full_text_tool_text_sequence(self) -> None:
        """Full sequence: text → tool → text transitions work correctly."""
        emitted: list[str] = []

        async def capture(event: AgentStreamChunk | StepOutput) -> None:
            if isinstance(event, AgentStreamChunk):
                emitted.append(event.text)

        async with StreamingContext(capture, "test-step") as stream:
            await stream.emit_text("Let me check the file.")
            await stream.emit_tool("Read", {"file_path": "foo.py"})
            await stream.emit_text("Found the issue.")

        assert len(emitted) == 3
        # Text: no prefix
        assert not emitted[0].startswith("\n")
        # Tool after text: single newline
        assert emitted[1].startswith("\n")
        assert not emitted[1].startswith("\n\n")
        # Text after tool: single newline
        assert emitted[2].startswith("\n")
        assert not emitted[2].startswith("\n\n")

    @pytest.mark.asyncio
    async def test_no_callback_is_noop(self) -> None:
        """When callback is None, emit methods are no-ops."""
        async with StreamingContext(None, "test-step") as stream:
            # Should not raise
            await stream.emit_text("text")
            await stream.emit_tool("Read", {"file_path": "foo.py"})
