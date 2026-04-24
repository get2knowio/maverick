"""Unit tests for MaverickAcpClient."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
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
from maverick.executor.acp_client import MAX_SAME_TOOL_CALLS, MaverickAcpClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_text_block(text: str) -> TextContentBlock:
    """Create a TextContentBlock with the given text."""
    return TextContentBlock(text=text, type="text")


def _make_message_chunk(text: str) -> AgentMessageChunk:
    """Create an AgentMessageChunk with the given text."""
    return AgentMessageChunk(
        content=_make_text_block(text),
        session_update="agent_message_chunk",
    )


def _make_thought_chunk(text: str) -> AgentThoughtChunk:
    """Create an AgentThoughtChunk with the given text."""
    return AgentThoughtChunk(
        content=_make_text_block(text),
        session_update="agent_thought_chunk",
    )


def _make_tool_call_start(title: str, tool_call_id: str = "tc1") -> ToolCallStart:
    """Create a ToolCallStart event."""
    return ToolCallStart(
        title=title,
        tool_call_id=tool_call_id,
        session_update="tool_call",
    )


def _make_tool_call_progress(text: str, tool_call_id: str = "tc1") -> ToolCallProgress:
    """Create a ToolCallProgress event with text content."""
    # ToolCallProgress content is a list of tool content types; use None to skip
    prog = ToolCallProgress(
        tool_call_id=tool_call_id,
        session_update="tool_call_update",
    )
    return prog


def _make_permission_options(
    kind: str = "allow_once",
) -> list[PermissionOption]:
    """Create a list of PermissionOption with the given kind."""
    return [
        PermissionOption(
            kind=kind,  # type: ignore[arg-type]
            name="Allow once",
            option_id="opt-1",
        )
    ]


def _make_tool_call_update(title: str = "Read") -> ToolCallUpdate:
    """Create a ToolCallUpdate for use in request_permission."""
    return ToolCallUpdate(tool_call_id="tc1", title=title)


def _make_client(
    permission_mode: PermissionMode = PermissionMode.AUTO_APPROVE,
) -> MaverickAcpClient:
    """Create a MaverickAcpClient with a fresh reset state."""
    client = MaverickAcpClient(permission_mode=permission_mode)
    client.reset(
        step_name="test_step",
        agent_name="test_agent",
        event_callback=None,
        allowed_tools=None,
    )
    return client


# ---------------------------------------------------------------------------
# T030-1: session_update with AgentMessageChunk
# ---------------------------------------------------------------------------


class TestSessionUpdateAgentMessageChunk:
    """AgentMessageChunk → accumulates text and fires output chunk."""

    def test_accumulates_text(self) -> None:
        """Text content is added to internal text_chunks."""
        client = _make_client()
        asyncio.run(client.session_update("s1", _make_message_chunk("hello ")))
        asyncio.run(client.session_update("s1", _make_message_chunk("world")))
        assert client.get_accumulated_text() == "hello world"

    def test_fires_output_chunk_via_callback(self) -> None:
        """Fires AgentStreamChunk(chunk_type='output') via callback."""
        received: list[AgentStreamChunk] = []

        async def callback(chunk: Any) -> None:
            received.append(chunk)

        client = MaverickAcpClient(permission_mode=PermissionMode.AUTO_APPROVE)
        client.reset(
            step_name="my_step",
            agent_name="my_agent",
            event_callback=callback,
            allowed_tools=None,
        )

        async def _run() -> None:
            await client.session_update("s1", _make_message_chunk("hi"))
            # Allow the event loop to process the created tasks
            await asyncio.sleep(0)

        asyncio.run(_run())

        assert len(received) == 1
        assert received[0].chunk_type == "output"
        assert received[0].text == "hi"
        assert received[0].step_name == "my_step"
        assert received[0].agent_name == "my_agent"

    def test_empty_text_not_accumulated(self) -> None:
        """AgentMessageChunk with empty text is silently ignored."""
        client = _make_client()
        asyncio.run(client.session_update("s1", _make_message_chunk("")))
        assert client.get_accumulated_text() == ""


# ---------------------------------------------------------------------------
# T030-2: session_update with AgentThoughtChunk
# ---------------------------------------------------------------------------


class TestSessionUpdateAgentThoughtChunk:
    """AgentThoughtChunk → fires thinking chunk but does NOT accumulate text."""

    def test_fires_thinking_chunk_via_callback(self) -> None:
        """Fires AgentStreamChunk(chunk_type='thinking') via callback."""
        received: list[AgentStreamChunk] = []

        async def callback(chunk: Any) -> None:
            received.append(chunk)

        client = MaverickAcpClient(permission_mode=PermissionMode.AUTO_APPROVE)
        client.reset(
            step_name="step",
            agent_name="agent",
            event_callback=callback,
            allowed_tools=None,
        )

        async def _run() -> None:
            await client.session_update("s1", _make_thought_chunk("pondering..."))
            await asyncio.sleep(0)

        asyncio.run(_run())

        assert len(received) == 1
        assert received[0].chunk_type == "thinking"
        assert received[0].text == "pondering..."

    def test_thought_chunk_does_not_accumulate_text(self) -> None:
        """AgentThoughtChunk text is NOT added to accumulated text."""
        client = _make_client()
        asyncio.run(client.session_update("s1", _make_thought_chunk("internal thought")))
        assert client.get_accumulated_text() == ""


# ---------------------------------------------------------------------------
# T030-3: session_update with ToolCallStart
# ---------------------------------------------------------------------------


class TestSessionUpdateToolCallStart:
    """ToolCallStart → fires [TOOL] chunk and tracks count."""

    def test_fires_tool_chunk_with_prefix(self) -> None:
        """Fires AgentStreamChunk with '[TOOL] ToolName\\n' prefix."""
        received: list[AgentStreamChunk] = []

        async def callback(chunk: Any) -> None:
            received.append(chunk)

        client = MaverickAcpClient(permission_mode=PermissionMode.AUTO_APPROVE)
        client.reset(
            step_name="s",
            agent_name="a",
            event_callback=callback,
            allowed_tools=None,
        )

        async def _run() -> None:
            await client.session_update("s1", _make_tool_call_start("Read"))
            await asyncio.sleep(0)

        asyncio.run(_run())

        assert len(received) == 1
        assert received[0].chunk_type == "output"
        assert received[0].text == "[TOOL] Read\n"

    def test_tracks_tool_call_count(self) -> None:
        """Tool call counts are incremented with each ToolCallStart."""
        client = _make_client()
        asyncio.run(client.session_update("s1", _make_tool_call_start("Bash", "tc1")))
        asyncio.run(client.session_update("s1", _make_tool_call_start("Bash", "tc2")))
        assert client._state.tool_call_counts["Bash"] == 2


# ---------------------------------------------------------------------------
# T030-4: session_update with ToolCallProgress
# ---------------------------------------------------------------------------


class TestSessionUpdateToolCallProgress:
    """ToolCallProgress with text → fires AgentStreamChunk(chunk_type='output')."""

    def test_fires_output_chunk_with_text_content(self) -> None:
        """ToolCallProgress with TextContentBlock content fires output chunk."""

        received: list[AgentStreamChunk] = []

        async def callback(chunk: Any) -> None:
            received.append(chunk)

        client = MaverickAcpClient(permission_mode=PermissionMode.AUTO_APPROVE)
        client.reset(
            step_name="s",
            agent_name="a",
            event_callback=callback,
            allowed_tools=None,
        )

        # ToolCallProgress with TextContentBlock-style content via direct object
        # The _extract_text_content uses TextContentBlock instance check
        # Simulate progress with a TextContentBlock as content (non-list)
        class _FakeProgress:
            pass

        # Create a real ToolCallProgress but with a TextContentBlock as .content
        progress = ToolCallProgress(
            tool_call_id="tc1",
            session_update="tool_call_update",
        )
        # Monkey-patch content to be a TextContentBlock for the test
        object.__setattr__(progress, "content", _make_text_block("output text"))

        async def _run() -> None:
            await client.session_update("s1", progress)
            await asyncio.sleep(0)

        asyncio.run(_run())

        assert len(received) == 1
        assert received[0].chunk_type == "output"
        assert received[0].text == "output text"

    def test_empty_content_does_not_fire(self) -> None:
        """ToolCallProgress with None content fires no callback."""
        received: list[Any] = []

        async def callback(chunk: Any) -> None:
            received.append(chunk)

        client = MaverickAcpClient(permission_mode=PermissionMode.AUTO_APPROVE)
        client.reset(
            step_name="s",
            agent_name="a",
            event_callback=callback,
            allowed_tools=None,
        )

        async def _run() -> None:
            progress = ToolCallProgress(
                tool_call_id="tc1",
                session_update="tool_call_update",
            )
            await client.session_update("s1", progress)
            await asyncio.sleep(0)

        asyncio.run(_run())

        assert len(received) == 0


# ---------------------------------------------------------------------------
# T030-5: get_accumulated_text
# ---------------------------------------------------------------------------


class TestGetAccumulatedText:
    """get_accumulated_text returns joined text from AgentMessageChunk events."""

    def test_multiple_chunks_joined(self) -> None:
        """Multiple chunks are concatenated in order."""
        client = _make_client()
        asyncio.run(client.session_update("s1", _make_message_chunk("foo")))
        asyncio.run(client.session_update("s1", _make_message_chunk(" bar")))
        asyncio.run(client.session_update("s1", _make_message_chunk(" baz")))
        assert client.get_accumulated_text() == "foo bar baz"

    def test_empty_when_no_chunks(self) -> None:
        """Returns empty string when no message chunks received."""
        client = _make_client()
        assert client.get_accumulated_text() == ""


# ---------------------------------------------------------------------------
# T030-6: reset
# ---------------------------------------------------------------------------


class TestReset:
    """reset() clears accumulated text and resets state."""

    def test_clears_accumulated_text(self) -> None:
        """Accumulated text is cleared after reset."""
        client = _make_client()
        asyncio.run(client.session_update("s1", _make_message_chunk("old text")))
        assert client.get_accumulated_text() == "old text"

        client.reset(
            step_name="new_step",
            agent_name="new_agent",
            event_callback=None,
            allowed_tools=None,
        )
        assert client.get_accumulated_text() == ""

    def test_clears_tool_call_counts(self) -> None:
        """Tool call counts are cleared after reset."""
        client = _make_client()
        asyncio.run(client.session_update("s1", _make_tool_call_start("Bash")))
        assert client._state.tool_call_counts["Bash"] == 1

        client.reset(
            step_name="next",
            agent_name="agent",
            event_callback=None,
            allowed_tools=None,
        )
        assert client._state.tool_call_counts == {}

    def test_clears_abort_flag(self) -> None:
        """abort flag is reset after reset()."""
        client = _make_client()
        client._state.abort = True
        assert client.aborted is True

        client.reset(
            step_name="next",
            agent_name="agent",
            event_callback=None,
            allowed_tools=None,
        )
        assert client.aborted is False

    def test_updates_step_and_agent_names(self) -> None:
        """reset() updates _step_name and _agent_name."""
        client = _make_client()
        client.reset(
            step_name="new_step",
            agent_name="new_agent",
            event_callback=None,
            allowed_tools=None,
        )
        assert client._step_name == "new_step"
        assert client._agent_name == "new_agent"


# ---------------------------------------------------------------------------
# T030-7: Circuit breaker
# ---------------------------------------------------------------------------


class TestCircuitBreaker:
    """Circuit breaker triggers when tool call count reaches MAX_SAME_TOOL_CALLS."""

    def test_sets_aborted_at_threshold(self) -> None:
        """aborted=True when single tool reaches MAX_SAME_TOOL_CALLS."""
        client = _make_client()
        for i in range(MAX_SAME_TOOL_CALLS):
            asyncio.run(client.session_update("s1", _make_tool_call_start("Bash", f"tc{i}")))

        assert client.aborted is True

    def test_not_aborted_below_threshold(self) -> None:
        """aborted=False when tool call count is below MAX_SAME_TOOL_CALLS."""
        client = _make_client()
        for i in range(MAX_SAME_TOOL_CALLS - 1):
            asyncio.run(client.session_update("s1", _make_tool_call_start("Bash", f"tc{i}")))

        assert client.aborted is False

    def test_different_tools_do_not_trigger_circuit_breaker(self) -> None:
        """Circuit breaker counts per tool, not globally."""
        client = _make_client()
        tools = ["Bash", "Read", "Write", "Edit", "Grep"]
        for i in range(MAX_SAME_TOOL_CALLS - 1):
            tool = tools[i % len(tools)]
            asyncio.run(client.session_update("s1", _make_tool_call_start(tool, f"tc{i}")))

        assert client.aborted is False

    def test_cancels_session_when_conn_present(self) -> None:
        """When _conn is set, circuit breaker calls conn.cancel() asynchronously."""
        mock_conn = MagicMock()
        mock_conn.cancel = AsyncMock(return_value=None)

        client = _make_client()
        client._conn = mock_conn

        async def _run() -> None:
            for i in range(MAX_SAME_TOOL_CALLS):
                await client.session_update("s1", _make_tool_call_start("Bash", f"tc{i}"))
            await asyncio.sleep(0)

        asyncio.run(_run())

        assert client.aborted is True
        mock_conn.cancel.assert_called_once_with("s1")


# ---------------------------------------------------------------------------
# T030-8: request_permission with AUTO_APPROVE
# ---------------------------------------------------------------------------


class TestRequestPermissionAutoApprove:
    """AUTO_APPROVE → returns allow_once response."""

    def test_returns_allowed_outcome(self) -> None:
        """Returns RequestPermissionResponse with AllowedOutcome."""
        client = _make_client(PermissionMode.AUTO_APPROVE)
        options = _make_permission_options("allow_once")
        tool_call = _make_tool_call_update("Bash")

        response = asyncio.run(
            client.request_permission(
                options=options,
                session_id="s1",
                tool_call=tool_call,
            )
        )

        assert isinstance(response, RequestPermissionResponse)
        assert isinstance(response.outcome, AllowedOutcome)
        assert response.outcome.option_id == "opt-1"

    def test_denies_tool_not_in_allowed_tools(self) -> None:
        """AUTO_APPROVE still enforces an explicit tool allowlist."""
        client = MaverickAcpClient(permission_mode=PermissionMode.AUTO_APPROVE)
        client.reset(
            step_name="s",
            agent_name="a",
            event_callback=None,
            allowed_tools=frozenset({"Read", "submit_outline"}),
        )
        options = _make_permission_options("allow_once")
        tool_call = _make_tool_call_update("Write")

        response = asyncio.run(
            client.request_permission(
                options=options,
                session_id="s1",
                tool_call=tool_call,
            )
        )

        assert isinstance(response.outcome, DeniedOutcome)

    def test_allows_tool_in_allowed_tools(self) -> None:
        """AUTO_APPROVE allows tools that are explicitly allowlisted."""
        client = MaverickAcpClient(permission_mode=PermissionMode.AUTO_APPROVE)
        client.reset(
            step_name="s",
            agent_name="a",
            event_callback=None,
            allowed_tools=frozenset({"Read", "submit_outline"}),
        )
        options = _make_permission_options("allow_once")
        tool_call = _make_tool_call_update("submit_outline")

        response = asyncio.run(
            client.request_permission(
                options=options,
                session_id="s1",
                tool_call=tool_call,
            )
        )

        assert isinstance(response.outcome, AllowedOutcome)

    def test_falls_back_to_first_option_when_no_allow_once(self) -> None:
        """Falls back to first option when no allow_once option available."""
        client = _make_client(PermissionMode.AUTO_APPROVE)
        options = _make_permission_options("allow_always")
        tool_call = _make_tool_call_update("Read")

        response = asyncio.run(
            client.request_permission(
                options=options,
                session_id="s1",
                tool_call=tool_call,
            )
        )

        assert isinstance(response, RequestPermissionResponse)
        assert isinstance(response.outcome, AllowedOutcome)
        assert response.outcome.option_id == "opt-1"


# ---------------------------------------------------------------------------
# T030-9: request_permission with DENY_DANGEROUS
# ---------------------------------------------------------------------------


class TestRequestPermissionDenyDangerous:
    """DENY_DANGEROUS → denies Bash/Write/Edit, allows Read/Grep/Glob."""

    def test_denies_bash(self) -> None:
        """Bash tool is denied in deny_dangerous mode."""
        client = _make_client(PermissionMode.DENY_DANGEROUS)
        options = _make_permission_options("allow_once")
        tool_call = _make_tool_call_update("Bash")

        response = asyncio.run(
            client.request_permission(
                options=options,
                session_id="s1",
                tool_call=tool_call,
            )
        )

        assert isinstance(response.outcome, DeniedOutcome)

    def test_denies_write(self) -> None:
        """Write tool is denied in deny_dangerous mode."""
        client = _make_client(PermissionMode.DENY_DANGEROUS)
        options = _make_permission_options("allow_once")
        tool_call = _make_tool_call_update("Write")

        response = asyncio.run(
            client.request_permission(
                options=options,
                session_id="s1",
                tool_call=tool_call,
            )
        )

        assert isinstance(response.outcome, DeniedOutcome)

    def test_denies_edit(self) -> None:
        """Edit tool is denied in deny_dangerous mode."""
        client = _make_client(PermissionMode.DENY_DANGEROUS)
        options = _make_permission_options("allow_once")
        tool_call = _make_tool_call_update("Edit")

        response = asyncio.run(
            client.request_permission(
                options=options,
                session_id="s1",
                tool_call=tool_call,
            )
        )

        assert isinstance(response.outcome, DeniedOutcome)

    def test_allows_read(self) -> None:
        """Read tool is allowed in deny_dangerous mode when in allowed_tools."""
        client = MaverickAcpClient(permission_mode=PermissionMode.DENY_DANGEROUS)
        client.reset(
            step_name="s",
            agent_name="a",
            event_callback=None,
            allowed_tools=frozenset({"Read", "Grep", "Glob"}),
        )
        options = _make_permission_options("allow_once")
        tool_call = _make_tool_call_update("Read")

        response = asyncio.run(
            client.request_permission(
                options=options,
                session_id="s1",
                tool_call=tool_call,
            )
        )

        assert isinstance(response.outcome, AllowedOutcome)

    def test_allows_grep(self) -> None:
        """Grep tool is allowed in deny_dangerous mode when in allowed_tools."""
        client = MaverickAcpClient(permission_mode=PermissionMode.DENY_DANGEROUS)
        client.reset(
            step_name="s",
            agent_name="a",
            event_callback=None,
            allowed_tools=frozenset({"Grep"}),
        )
        options = _make_permission_options("allow_once")
        tool_call = _make_tool_call_update("Grep")

        response = asyncio.run(
            client.request_permission(
                options=options,
                session_id="s1",
                tool_call=tool_call,
            )
        )

        assert isinstance(response.outcome, AllowedOutcome)

    def test_denies_unknown_tool_not_in_allowed(self) -> None:
        """Unknown tool not in allowed_tools is denied in deny_dangerous mode."""
        client = MaverickAcpClient(permission_mode=PermissionMode.DENY_DANGEROUS)
        client.reset(
            step_name="s",
            agent_name="a",
            event_callback=None,
            allowed_tools=frozenset({"Read"}),
        )
        options = _make_permission_options("allow_once")
        tool_call = _make_tool_call_update("SomeFancyTool")

        response = asyncio.run(
            client.request_permission(
                options=options,
                session_id="s1",
                tool_call=tool_call,
            )
        )

        assert isinstance(response.outcome, DeniedOutcome)

    def test_safe_tool_denied_when_not_in_allowed_tools(self) -> None:
        """Explicit allowlists are enforced before safe-tool shortcuts."""
        client = MaverickAcpClient(permission_mode=PermissionMode.DENY_DANGEROUS)
        client.reset(
            step_name="s",
            agent_name="a",
            event_callback=None,
            allowed_tools=frozenset({"Read"}),
        )
        options = _make_permission_options("allow_once")
        tool_call = _make_tool_call_update("WebSearch")

        response = asyncio.run(
            client.request_permission(
                options=options,
                session_id="s1",
                tool_call=tool_call,
            )
        )

        assert isinstance(response.outcome, DeniedOutcome)

    def test_safe_tool_allowed_with_no_allowed_tools_set(self) -> None:
        """Safe tools are allowed in deny_dangerous mode even with no allowed_tools."""
        client = MaverickAcpClient(permission_mode=PermissionMode.DENY_DANGEROUS)
        client.reset(
            step_name="s",
            agent_name="a",
            event_callback=None,
            allowed_tools=None,
        )
        options = _make_permission_options("allow_once")
        tool_call = _make_tool_call_update("Glob")

        response = asyncio.run(
            client.request_permission(
                options=options,
                session_id="s1",
                tool_call=tool_call,
            )
        )

        assert isinstance(response.outcome, AllowedOutcome)


# ---------------------------------------------------------------------------
# T030-10: request_permission with INTERACTIVE
# ---------------------------------------------------------------------------


class TestRequestPermissionInteractive:
    """INTERACTIVE permission mode raises NotImplementedError."""

    def test_raises_not_implemented(self) -> None:
        """INTERACTIVE mode raises NotImplementedError."""
        client = _make_client(PermissionMode.INTERACTIVE)
        options = _make_permission_options("allow_once")
        tool_call = _make_tool_call_update("Read")

        with pytest.raises(NotImplementedError, match="INTERACTIVE"):
            asyncio.run(
                client.request_permission(
                    options=options,
                    session_id="s1",
                    tool_call=tool_call,
                )
            )


# ---------------------------------------------------------------------------
# one_shot_tools: cancel fires on ToolCallProgress(completed), not on Start
# ---------------------------------------------------------------------------


class TestOneShotTools:
    """one_shot_tools cancels the session after the tool actually completes.

    The initial implementation cancelled on ToolCallStart, which aborted
    the MCP round-trip before our own on_tool_call handler had a chance
    to forward the payload to the supervisor. The cancel must wait for
    ToolCallProgress with status='completed'.
    """

    def _make_client_with_one_shot(
        self,
        one_shot: list[str],
    ) -> MaverickAcpClient:
        client = MaverickAcpClient(permission_mode=PermissionMode.AUTO_APPROVE)
        # Give it a fake conn so the cancel path can fire its create_task.
        client._conn = MagicMock()
        client._conn.cancel = AsyncMock(return_value=None)
        client.reset(
            step_name="t",
            agent_name="a",
            event_callback=None,
            allowed_tools=None,
            one_shot_tools=frozenset(one_shot),
        )
        return client

    def test_start_alone_does_not_cancel(self) -> None:
        """ToolCallStart for a one-shot tool does NOT fire cancel yet —
        the MCP tool round-trip must finish before we cancel."""
        client = self._make_client_with_one_shot(["submit_navigator_brief"])
        asyncio.run(
            client.session_update(
                "s1",
                _make_tool_call_start("mcp__agent-inbox__submit_navigator_brief", "tc1"),
            )
        )
        client._conn.cancel.assert_not_called()
        assert client._state.one_shot_fired is False

    def test_completed_progress_cancels(self) -> None:
        """ToolCallProgress with status=completed for a one-shot tool
        fires cancel. Title matched via tool_call_id mapping captured
        at Start time — ToolCallProgress may omit the title."""
        client = self._make_client_with_one_shot(["submit_navigator_brief"])

        async def _run() -> None:
            # Start records the title for tc1.
            await client.session_update(
                "s1",
                _make_tool_call_start("mcp__agent-inbox__submit_navigator_brief", "tc1"),
            )
            # Completed progress WITHOUT title must still match via id.
            prog = ToolCallProgress(
                tool_call_id="tc1",
                status="completed",
                session_update="tool_call_update",
            )
            await client.session_update("s1", prog)
            await asyncio.sleep(0)  # let the cancel task run

        asyncio.run(_run())
        assert client._state.one_shot_fired is True
        client._conn.cancel.assert_awaited_once_with("s1")

    def test_in_progress_status_does_not_cancel(self) -> None:
        """Only status=completed triggers cancel; in_progress does not."""
        client = self._make_client_with_one_shot(["submit_navigator_brief"])

        async def _run() -> None:
            await client.session_update(
                "s1",
                _make_tool_call_start("mcp__agent-inbox__submit_navigator_brief", "tc1"),
            )
            prog = ToolCallProgress(
                tool_call_id="tc1",
                status="in_progress",
                session_update="tool_call_update",
            )
            await client.session_update("s1", prog)
            await asyncio.sleep(0)

        asyncio.run(_run())
        assert client._state.one_shot_fired is False
        client._conn.cancel.assert_not_called()

    def test_non_one_shot_tool_never_cancels(self) -> None:
        """Tools not in one_shot_tools complete without cancel."""
        client = self._make_client_with_one_shot(["submit_navigator_brief"])

        async def _run() -> None:
            await client.session_update(
                "s1",
                _make_tool_call_start("Read File", "tc1"),
            )
            prog = ToolCallProgress(
                tool_call_id="tc1",
                status="completed",
                session_update="tool_call_update",
            )
            await client.session_update("s1", prog)
            await asyncio.sleep(0)

        asyncio.run(_run())
        assert client._state.one_shot_fired is False
        client._conn.cancel.assert_not_called()
