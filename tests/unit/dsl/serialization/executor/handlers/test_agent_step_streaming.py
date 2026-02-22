"""Tests for agent step stream_text_callback text→tool transitions.

Verifies that the stream_text_callback in execute_agent_step inserts
a newline before the first tool call after streamed text, preventing
garbled same-line rendering.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from maverick.dsl.context import WorkflowContext
from maverick.dsl.events import AgentStreamChunk
from maverick.dsl.serialization.executor.handlers.agent_step import (
    execute_agent_step,
)
from maverick.dsl.serialization.registry import ComponentRegistry
from maverick.dsl.serialization.schema import AgentStepRecord

# Module-level list to control which chunks the mock agent streams.
# Set this before each test via _set_chunks().
_CHUNKS: list[str] = []


def _set_chunks(chunks: list[str]) -> None:
    global _CHUNKS  # noqa: PLW0603
    _CHUNKS = list(chunks)


class _StreamingMockAgent:
    """Mock agent that streams pre-configured chunks via stream_callback."""

    name = "test-agent"
    stream_callback: Any = None

    def __init__(self, **kwargs: Any) -> None:
        pass

    async def execute(self, context: Any) -> dict[str, str]:
        if self.stream_callback:
            for chunk in _CHUNKS:
                await self.stream_callback(chunk)
        return {"status": "done"}


def _make_step() -> AgentStepRecord:
    return AgentStepRecord(
        name="test-step",
        type="agent",
        agent="test-agent",
    )


async def _run_with_chunks(chunks: list[str]) -> list[str]:
    """Run agent step with given chunks, return emitted output texts."""
    _set_chunks(chunks)
    emitted: list[str] = []

    async def capture_event(event: AgentStreamChunk) -> None:
        if isinstance(event, AgentStreamChunk) and event.chunk_type == "output":
            emitted.append(event.text)

    registry = ComponentRegistry()
    registry.agents.register("test-agent", _StreamingMockAgent, validate=False)
    context = WorkflowContext(inputs={}, results={})

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "maverick.dsl.serialization.executor.handlers.agent_step"
            ".resolve_context_builder",
            AsyncMock(return_value={}),
        )
        await execute_agent_step(
            step=_make_step(),
            resolved_inputs={},
            context=context,
            registry=registry,
            event_callback=capture_event,
        )

    return emitted


class TestStreamTextCallbackTextToToolTransition:
    """Test text→tool newline insertion in stream_text_callback."""

    @pytest.mark.asyncio
    async def test_inserts_newline_before_tool_after_text(self) -> None:
        """Tool call after streamed text gets a leading newline."""
        emitted = await _run_with_chunks(
            [
                "Now let me create tests:",
                "\u2514 TodoWrite\n",
            ]
        )

        tool_outputs = [t for t in emitted if "\u2514" in t]
        assert len(tool_outputs) >= 1
        assert tool_outputs[0].startswith("\n"), (
            f"Expected tool call to start with newline after text, "
            f"got: {tool_outputs[0]!r}"
        )

    @pytest.mark.asyncio
    async def test_no_extra_newline_when_tool_is_first_output(self) -> None:
        """Tool call as first output should NOT get extra newline."""
        emitted = await _run_with_chunks(
            [
                "\u2514 Read: foo.py\n",
            ]
        )

        tool_outputs = [t for t in emitted if "\u2514" in t]
        assert len(tool_outputs) >= 1
        assert not tool_outputs[0].startswith("\n"), (
            f"Tool call as first output should not get extra newline, "
            f"got: {tool_outputs[0]!r}"
        )

    @pytest.mark.asyncio
    async def test_tool_to_text_transition_adds_blank_line(self) -> None:
        """Text after tool call gets single newline prefix for spacing."""
        emitted = await _run_with_chunks(
            [
                "\u2514 Read: foo.py\n",
                "Analysis complete.",
            ]
        )

        text_outputs = [t for t in emitted if "\u2514" not in t]
        assert any(t.startswith("\n") for t in text_outputs), (
            f"Text after tool call should get newline, got: {text_outputs!r}"
        )
        assert not any(t.startswith("\n\n") for t in text_outputs), (
            "Text after tool call should get single newline, "
            f"not double, got: {text_outputs!r}"
        )

    @pytest.mark.asyncio
    async def test_consecutive_tools_no_extra_newline(self) -> None:
        """Consecutive tool calls should NOT get extra newlines between them."""
        emitted = await _run_with_chunks(
            [
                "\u2514 Read: foo.py\n",
                "\u2514 Write: bar.py\n",
            ]
        )

        tool_outputs = [t for t in emitted if "\u2514" in t]
        assert len(tool_outputs) == 2
        assert not tool_outputs[1].startswith("\n"), (
            f"Consecutive tools should not get extra newlines, got: {tool_outputs[1]!r}"
        )

    @pytest.mark.asyncio
    async def test_whitespace_only_text_does_not_trigger_transition(self) -> None:
        """Whitespace-only text should not set has_emitted_text flag."""
        emitted = await _run_with_chunks(
            [
                "   ",  # whitespace-only
                "\u2514 Read: foo.py\n",
            ]
        )

        tool_outputs = [t for t in emitted if "\u2514" in t]
        assert len(tool_outputs) >= 1
        # Whitespace-only text should not trigger the text→tool transition
        assert not tool_outputs[0].startswith("\n"), (
            f"Whitespace-only text should not trigger text→tool newline, "
            f"got: {tool_outputs[0]!r}"
        )
