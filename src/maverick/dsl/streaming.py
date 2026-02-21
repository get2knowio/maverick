"""Shared streaming utilities for DSL step handlers.

This module provides step-type-agnostic streaming infrastructure so all
handlers can emit formatted progress events consistently.

Usage:
    async def execute_my_step(..., event_callback: EventCallback | None = None):
        async with StreamingContext(event_callback, step_name) as stream:
            await stream.emit_progress("Starting work...")
            await stream.emit_tool("Read", {"file_path": "/foo/bar.py"})
            await stream.emit_text("Analysis complete.")
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from maverick.dsl.events import AgentStreamChunk, StepOutput

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    # Event callback type used by executor
    EventCallback = Callable[["AgentStreamChunk | StepOutput"], Awaitable[None]]


# Prefix character for tool call display (Unicode L-bracket └)
_TOOL_PREFIX = "\u2514"


def _shorten_path(path: str, max_length: int = 50) -> str:
    """Shorten a file path for display."""
    if len(path) <= max_length:
        return path

    parts = path.split("/")
    if len(parts) <= 2:
        return path

    filename = parts[-1]
    if len(filename) >= max_length - 4:
        return "..." + filename[-(max_length - 3) :]

    result_parts = [filename]
    remaining = max_length - len(filename) - 4

    for part in reversed(parts[:-1]):
        if len(part) + 1 <= remaining:
            result_parts.insert(0, part)
            remaining -= len(part) + 1
        else:
            break

    return ".../" + "/".join(result_parts)


def format_tool_call(tool_name: str, tool_input: dict[str, Any]) -> str:
    """Format a tool call for streaming display with └ prefix.

    Uses └ prefix for visually distinct but unobtrusive tool activity display.
    Format: "└ ToolName: key_parameter\\n"

    Note: This output must be plain text (no Rich markup tags) because it flows
    through sentence-boundary text buffering that can split content mid-string.
    Rich markup like [dim]...[/dim] would be broken across buffer flushes,
    causing MarkupError. Styling is applied at the widget level via CSS classes.

    The trailing newline is critical: the sentence-boundary buffer splits at
    ": " (colon+space), which would break "└ Bash: make test" into two entries.
    The trailing newline ensures it is the last boundary in the buffer, so the
    entire tool call line is flushed as one piece. The newline is stripped by
    .rstrip() before display.

    Args:
        tool_name: Name of the tool being called
        tool_input: Input parameters for the tool

    Returns:
        Formatted tool call string with trailing newline, or empty string
        if no meaningful display.
    """
    if tool_name == "Read":
        file_path = tool_input.get("file_path", "")
        if file_path:
            short_path = _shorten_path(file_path)
            return f"{_TOOL_PREFIX} Read: {short_path}\n"
        return ""

    if tool_name == "Write":
        file_path = tool_input.get("file_path", "")
        if file_path:
            short_path = _shorten_path(file_path)
            return f"{_TOOL_PREFIX} Write: {short_path}\n"
        return ""

    if tool_name == "Edit":
        file_path = tool_input.get("file_path", "")
        if file_path:
            short_path = _shorten_path(file_path)
            return f"{_TOOL_PREFIX} Edit: {short_path}\n"
        return ""

    if tool_name == "Glob":
        pattern = tool_input.get("pattern", "")
        return f"{_TOOL_PREFIX} Glob: {pattern}\n"

    if tool_name == "Grep":
        pattern = tool_input.get("pattern", "")
        return f"{_TOOL_PREFIX} Grep: {pattern}\n"

    if tool_name == "Bash":
        command = tool_input.get("command", "")
        if len(command) > 80:
            command = command[:77] + "..."
        return f"{_TOOL_PREFIX} Bash: {command}\n"

    if tool_name == "Task":
        description = tool_input.get("description", "")
        return f"{_TOOL_PREFIX} Task: {description}\n"

    if tool_name in ("WebFetch", "WebSearch"):
        url = tool_input.get("url", "")
        query = tool_input.get("query", "")
        param = url or query
        if len(param) > 60:
            param = param[:57] + "..."
        return f"{_TOOL_PREFIX} {tool_name}: {param}\n"

    # Generic fallback for other tools
    return f"{_TOOL_PREFIX} {tool_name}\n"


@runtime_checkable
class SupportsStreaming(Protocol):
    """Protocol for handlers that support streaming output.

    This is optional - handlers can just accept event_callback as a parameter.
    The protocol is useful for type checking and documentation.
    """

    async def __call__(
        self,
        step: Any,
        resolved_inputs: dict[str, Any],
        context: Any,
        registry: Any,
        config: Any | None = None,
        event_callback: EventCallback | None = None,
    ) -> Any: ...


class StreamingContext:
    """Context manager for streaming output with automatic mode transitions.

    Tracks whether last output was a tool call to add proper spacing when
    switching between tool output and text output.

    Usage:
        async with StreamingContext(event_callback, "my_step") as stream:
            await stream.emit_text("Starting analysis...")
            await stream.emit_tool("Read", {"file_path": "foo.py"})
            await stream.emit_text("Found 3 issues.")
            await stream.emit_progress("Validation complete", level="success")
    """

    def __init__(
        self,
        event_callback: EventCallback | None,
        step_name: str,
        source_name: str | None = None,
    ) -> None:
        """Initialize streaming context.

        Args:
            event_callback: Callback to emit events (can be None for no-op)
            step_name: Name of the current step
            source_name: Optional source identifier (e.g., agent name)
        """
        self._callback = event_callback
        self._step_name = step_name
        self._source_name = source_name or step_name
        self._last_was_tool = False
        self._has_output = False

    async def __aenter__(self) -> StreamingContext:
        """Enter the streaming context."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit the streaming context."""
        pass

    async def emit_text(self, text: str) -> None:
        """Emit text output with proper mode transition spacing.

        Adds extra newlines when switching from tool output to text.
        """
        if not self._callback or not text.strip():
            return

        output_text = text
        if self._last_was_tool and self._has_output:
            output_text = "\n\n" + text

        self._last_was_tool = False
        self._has_output = True

        await self._callback(
            AgentStreamChunk(
                step_name=self._step_name,
                agent_name=self._source_name,
                text=output_text,
                chunk_type="output",
            )
        )

    async def emit_tool(self, tool_name: str, tool_input: dict[str, Any]) -> None:
        """Emit a formatted tool call with emoji prefix."""
        if not self._callback:
            return

        formatted = format_tool_call(tool_name, tool_input)
        if not formatted:
            return

        # Ensure tool call starts on a new line after text output
        if self._has_output and not self._last_was_tool:
            formatted = "\n" + formatted

        self._last_was_tool = True
        self._has_output = True

        await self._callback(
            AgentStreamChunk(
                step_name=self._step_name,
                agent_name=self._source_name,
                text=formatted,
                chunk_type="output",
            )
        )

    async def emit_progress(
        self,
        message: str,
        level: str = "info",
        source: str | None = None,
    ) -> None:
        """Emit a step progress message.

        Args:
            message: Progress message text
            level: One of "info", "success", "warning", "error"
            source: Optional source identifier
        """
        if not self._callback:
            return

        # Add spacing if coming from tool output
        if self._last_was_tool and self._has_output:
            message = "\n\n" + message

        self._last_was_tool = False
        self._has_output = True

        await self._callback(
            StepOutput(
                step_name=self._step_name,
                message=message,
                level=level,  # type: ignore[arg-type]
                source=source or self._source_name,
            )
        )

    async def emit_stage(
        self,
        stage_name: str,
        status: str = "running",
        details: str | None = None,
    ) -> None:
        """Emit a validation/processing stage indicator.

        Args:
            stage_name: Name of the stage (e.g., "format", "lint", "test")
            status: One of "running", "passed", "failed", "skipped"
            details: Optional additional details
        """
        if not self._callback:
            return

        if status == "running":
            indicator = "..."
            level = "info"
        elif status == "passed":
            indicator = "\u2713"  # ✓
            level = "success"
        elif status == "failed":
            indicator = "\u2717"  # ✗
            level = "error"
        else:  # skipped
            indicator = "-"
            level = "warning"

        message = f"{_TOOL_PREFIX} {stage_name} {indicator}"
        if details:
            message += f" {details}"

        self._last_was_tool = True  # Treat stages like tool calls for spacing
        self._has_output = True

        await self._callback(
            StepOutput(
                step_name=self._step_name,
                message=message,
                level=level,  # type: ignore[arg-type]
                source=stage_name,
            )
        )

    async def emit_thinking(self, message: str = "Working...") -> None:
        """Emit a thinking/processing indicator."""
        if not self._callback:
            return

        await self._callback(
            AgentStreamChunk(
                step_name=self._step_name,
                agent_name=self._source_name,
                text=message,
                chunk_type="thinking",
            )
        )
