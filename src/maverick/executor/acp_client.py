"""MaverickAcpClient — ACP Client subclass for streaming and permission handling."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from acp import Client
from acp.schema import (
    AgentMessageChunk,
    AgentThoughtChunk,
    AllowedOutcome,
    DeniedOutcome,
    PermissionOption,
    RequestPermissionResponse,
    TextContentBlock,
    ToolCallProgress,
    ToolCallStart,
    ToolCallUpdate,
)

from maverick.config import PermissionMode
from maverick.events import AgentStreamChunk
from maverick.executor.protocol import EventCallback
from maverick.logging import get_logger

__all__ = ["MaverickAcpClient"]

logger = get_logger(__name__)

#: Circuit breaker: max calls to the same tool before triggering.
#: Set high enough for agents that thoroughly explore codebases
#: (e.g., 50+ Grep calls across a Rust workspace is normal).
MAX_SAME_TOOL_CALLS: int = 100

#: Tools that are always denied in deny_dangerous mode
_DANGEROUS_TOOL_PATTERNS: frozenset[str] = frozenset({"Bash", "Write", "Edit", "NotebookEdit"})

#: Tools that are always allowed in deny_dangerous mode
_SAFE_TOOL_PATTERNS: frozenset[str] = frozenset({"Read", "Glob", "Grep", "WebSearch", "WebFetch"})


@dataclass
class _SessionState:
    """Mutable state for a single ACP session within MaverickAcpClient."""

    text_chunks: list[str] = field(default_factory=list)
    tool_call_counts: dict[str, int] = field(default_factory=dict)
    abort: bool = False


class MaverickAcpClient(Client):
    """ACP Client that handles streaming events and permission requests.

    Created per-connection. Supports reset() between sessions on the same
    connection.

    The client handles:
    - Streaming AgentMessageChunk -> AgentStreamChunk(chunk_type="output")
    - Streaming AgentThoughtChunk -> AgentStreamChunk(chunk_type="thinking")
    - Streaming ToolCallStart -> AgentStreamChunk(chunk_type="output", text="[TOOL]")
    - Streaming ToolCallProgress -> AgentStreamChunk(chunk_type="output")
    - Circuit breaker on excessive tool calls
    - Permission mode enforcement (auto_approve, deny_dangerous)
    """

    def __init__(
        self,
        permission_mode: PermissionMode = PermissionMode.AUTO_APPROVE,
    ) -> None:
        """Initialize MaverickAcpClient.

        Args:
            permission_mode: How to handle agent permission requests.
        """
        super().__init__()
        self._permission_mode = permission_mode
        self._state = _SessionState()
        self._step_name: str = ""
        self._agent_name: str = ""
        self._event_callback: EventCallback | None = None
        self._allowed_tools: frozenset[str] | None = None
        self._conn: Any = None  # Set by executor after connection creation

    def reset(
        self,
        step_name: str,
        agent_name: str,
        event_callback: EventCallback | None,
        allowed_tools: frozenset[str] | None,
    ) -> None:
        """Reset state for a new session.

        Args:
            step_name: Current step name for event tagging.
            agent_name: Current agent name for event tagging.
            event_callback: Where to forward AgentStreamChunk events.
            allowed_tools: Tools the agent is allowed to use.
        """
        self._state = _SessionState()
        self._step_name = step_name
        self._agent_name = agent_name
        self._event_callback = event_callback
        self._allowed_tools = allowed_tools

    def reset_for_turn(self) -> None:
        """Clear per-turn accumulators without destroying session state.

        Used for multi-turn sessions where the same session receives
        multiple prompts.  Clears accumulated text and tool counts
        so the next turn starts with fresh accumulators, but preserves
        the overall session identity (step_name, agent_name, callbacks).

        The abort flag is NOT cleared — if a circuit breaker fired on a
        previous turn, subsequent turns should not proceed.
        """
        abort = self._state.abort
        self._state = _SessionState(abort=abort)

    def get_accumulated_text(self) -> str:
        """Return all accumulated agent text from the current session.

        Returns:
            Concatenated text from all AgentMessageChunk events.
        """
        return "".join(self._state.text_chunks)

    @property
    def aborted(self) -> bool:
        """Whether the circuit breaker triggered for the current session."""
        return self._state.abort

    async def session_update(
        self,
        session_id: str,
        update: Any,
        **kwargs: Any,
    ) -> None:
        """Handle ACP streaming events (FR-008).

        Maps ACP events to AgentStreamChunk events and forwards to callback.
        Tracks tool call counts for circuit breaker (FR-013).

        Args:
            session_id: ACP session identifier.
            update: The streaming update event.
        """
        if isinstance(update, AgentMessageChunk):
            text = _extract_text_content(update.content)
            if text:
                self._state.text_chunks.append(text)
                chunk = AgentStreamChunk(
                    step_name=self._step_name,
                    agent_name=self._agent_name,
                    text=text,
                    chunk_type="output",
                )
                await _fire_callback(self._event_callback, chunk)

        elif isinstance(update, AgentThoughtChunk):
            text = _extract_text_content(update.content)
            if text:
                chunk = AgentStreamChunk(
                    step_name=self._step_name,
                    agent_name=self._agent_name,
                    text=text,
                    chunk_type="thinking",
                )
                await _fire_callback(self._event_callback, chunk)

        elif isinstance(update, ToolCallStart):
            # Track circuit breaker
            title = update.title or "unknown_tool"
            self._state.tool_call_counts[title] = self._state.tool_call_counts.get(title, 0) + 1
            logger.debug(
                "acp_client.tool_call_start",
                tool=title,
                count=self._state.tool_call_counts[title],
            )

            # Check circuit breaker
            if self._state.tool_call_counts[title] >= MAX_SAME_TOOL_CALLS:
                logger.info(
                    "acp_client.circuit_breaker_triggered",
                    tool=title,
                    count=self._state.tool_call_counts[title],
                    session_id=session_id,
                )
                self._state.abort = True
                if self._conn is not None:
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(self._conn.cancel(session_id))
                    except RuntimeError:
                        pass  # No running event loop

            chunk = AgentStreamChunk(
                step_name=self._step_name,
                agent_name=self._agent_name,
                text=f"[TOOL] {title}\n",
                chunk_type="output",
            )
            await _fire_callback(self._event_callback, chunk)

        elif isinstance(update, ToolCallProgress):
            text = _extract_text_content(update.content)
            if text:
                chunk = AgentStreamChunk(
                    step_name=self._step_name,
                    agent_name=self._agent_name,
                    text=text,
                    chunk_type="output",
                )
                await _fire_callback(self._event_callback, chunk)

    async def request_permission(
        self,
        options: list[PermissionOption],
        session_id: str,
        tool_call: ToolCallUpdate,
        **kwargs: Any,
    ) -> RequestPermissionResponse:
        """Handle ACP permission requests (FR-008).

        Args:
            options: Available permission options from the agent.
            session_id: ACP session identifier.
            tool_call: The tool call requesting permission.

        Returns:
            RequestPermissionResponse with allow or deny outcome.

        Raises:
            NotImplementedError: If permission_mode is INTERACTIVE.
        """
        tool_name = (tool_call.title if hasattr(tool_call, "title") else "") or ""

        if not self._is_allowlisted_tool(tool_name):
            logger.info(
                "acp_client.permission_denied",
                tool=tool_name,
                mode=self._permission_mode.value,
                reason="not_allowlisted",
            )
            return _make_deny_response()

        if self._permission_mode == PermissionMode.AUTO_APPROVE:
            return _make_allow_response(options)

        elif self._permission_mode == PermissionMode.DENY_DANGEROUS:
            if self._is_dangerous_tool(tool_name):
                logger.info(
                    "acp_client.permission_denied",
                    tool=tool_name,
                    mode="deny_dangerous",
                )
                return _make_deny_response()
            return _make_allow_response(options)

        else:
            raise NotImplementedError(
                "PermissionMode.INTERACTIVE is not yet supported. "
                "Use AUTO_APPROVE or DENY_DANGEROUS."
            )

    def _is_allowlisted_tool(self, tool_name: str) -> bool:
        """Check whether a tool is permitted by the explicit allowlist.

        ACP surfaces MCP tools as ``mcp__<server>__<tool>``; callers
        typically configure their allowlist with the bare tool name.
        Match both forms so ``allowed_tools=["submit_outline"]`` accepts
        a call whose title is ``mcp__agent-inbox__submit_outline``.
        """
        if self._allowed_tools is None:
            return True
        if tool_name in self._allowed_tools:
            return True
        if tool_name.startswith("mcp__"):
            bare = tool_name.rsplit("__", 1)[-1]
            if bare in self._allowed_tools:
                return True
        return False

    def _is_dangerous_tool(self, tool_name: str) -> bool:
        """Check if a tool should be denied in deny_dangerous mode.

        Evaluation order:
        1. If the tool is in _SAFE_TOOL_PATTERNS, it is always allowed.
        2. If the tool is in _DANGEROUS_TOOL_PATTERNS, it is always denied.

        Args:
            tool_name: Tool name to check.

        Returns:
            True if the tool should be denied.
        """
        if tool_name in _SAFE_TOOL_PATTERNS:
            return False  # Always safe
        return tool_name in _DANGEROUS_TOOL_PATTERNS


def _extract_text_content(content: Any) -> str:
    """Extract text from an ACP content block.

    Args:
        content: TextContentBlock or other content block.

    Returns:
        Text string, or empty string if not a text block.
    """
    if isinstance(content, TextContentBlock):
        return content.text
    return ""


async def _fire_callback(callback: EventCallback | None, chunk: AgentStreamChunk) -> None:
    """Await async event callback.

    Exceptions are logged at warning level but not propagated — a broken
    progress indicator should not crash the agent execution.

    Args:
        callback: Async event callback, or None.
        chunk: Event to deliver.
    """
    if callback is None:
        return
    try:
        await callback(chunk)
    except Exception:
        get_logger(__name__).warning("event_callback_failed")


def _make_allow_response(options: list[PermissionOption]) -> RequestPermissionResponse:
    """Build an allow_once permission response.

    Args:
        options: Available permission options.

    Returns:
        RequestPermissionResponse selecting the allow_once option.
    """
    for opt in options:
        if opt.kind == "allow_once":
            return RequestPermissionResponse(
                outcome=AllowedOutcome(option_id=opt.option_id, outcome="selected")
            )
    # Fall back to first option if allow_once not found
    if options:
        return RequestPermissionResponse(
            outcome=AllowedOutcome(option_id=options[0].option_id, outcome="selected")
        )
    return RequestPermissionResponse(outcome=AllowedOutcome(option_id="", outcome="selected"))


def _make_deny_response() -> RequestPermissionResponse:
    """Build a reject_once permission response.

    Returns:
        RequestPermissionResponse with deny outcome.
    """
    return RequestPermissionResponse(outcome=DeniedOutcome(outcome="cancelled"))
