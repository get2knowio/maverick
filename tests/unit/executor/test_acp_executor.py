"""Unit tests for AcpStepExecutor."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from acp import RequestError as AcpRequestError
from pydantic import BaseModel

from maverick.config import AgentProviderConfig, PermissionMode
from maverick.exceptions.agent import (
    AgentError,
    CLINotFoundError,
    MalformedResponseError,
    MaverickTimeoutError,
    NetworkError,
    ProcessError,
)
from maverick.exceptions.config import ConfigError
from maverick.exceptions.workflow import ReferenceResolutionError
from maverick.executor.acp import AcpStepExecutor, _get_available_model_ids
from maverick.executor.acp_client import MaverickAcpClient
from maverick.executor.config import StepConfig
from maverick.executor.errors import OutputSchemaValidationError
from maverick.executor.provider_registry import AgentProviderRegistry
from maverick.executor.result import ExecutorResult
from maverick.registry import ComponentRegistry

# ---------------------------------------------------------------------------
# Schema for structured output tests
# ---------------------------------------------------------------------------


class _SampleOutput(BaseModel):
    """Sample output schema for structured output tests."""

    message: str
    count: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_provider_config(
    command: list[str] | None = None,
    permission_mode: PermissionMode = PermissionMode.AUTO_APPROVE,
    default: bool = True,
) -> AgentProviderConfig:
    """Create an AgentProviderConfig for tests."""
    return AgentProviderConfig(
        command=command or ["fake-agent", "--acp"],
        permission_mode=permission_mode,
        default=default,
    )


def _make_provider_registry(
    provider_name: str = "claude",
    config: AgentProviderConfig | None = None,
) -> AgentProviderRegistry:
    """Create an AgentProviderRegistry with a single provider."""
    if config is None:
        config = _make_provider_config(default=True)
    return AgentProviderRegistry({provider_name: config})


def _make_agent_registry(
    agent_name: str = "test_agent",
    build_prompt_return: str = "default prompt",
) -> ComponentRegistry:
    """Create a ComponentRegistry with a mock agent registered."""
    reg = ComponentRegistry()

    class _MockAgent:
        name = agent_name

        def build_prompt(self, context: Any) -> str:
            return build_prompt_return

        async def execute(self, context: Any) -> str:
            return "agent result"

    reg.agents.register(agent_name, _MockAgent, validate=False)
    return reg


def _make_executor(
    agent_name: str = "test_agent",
    build_prompt_return: str = "the prompt",
    provider_name: str = "claude",
    provider_config: AgentProviderConfig | None = None,
) -> AcpStepExecutor:
    """Create an AcpStepExecutor with a stubbed out registry."""
    provider_registry = _make_provider_registry(
        provider_name=provider_name,
        config=provider_config,
    )
    agent_registry = _make_agent_registry(
        agent_name=agent_name,
        build_prompt_return=build_prompt_return,
    )
    return AcpStepExecutor(
        provider_registry=provider_registry,
        agent_registry=agent_registry,
    )


def _mock_spawn_context(
    accumulated_text: str = "agent output",
    aborted: bool = False,
) -> tuple[MagicMock, MagicMock]:
    """Return (mock_conn, mock_proc) for use in spawn_agent_process mocks.

    The mock_conn is configured to support new_session(), prompt(), close(),
    and initialize(). The MaverickAcpClient.get_accumulated_text() is
    configured to return accumulated_text.
    """
    mock_conn = MagicMock()
    mock_conn.initialize = AsyncMock(return_value=None)
    mock_conn.close = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.session_id = "sess-123"
    mock_conn.new_session = AsyncMock(return_value=mock_session)
    mock_conn.prompt = AsyncMock(return_value=None)

    mock_proc = MagicMock()
    mock_proc.terminate = MagicMock()

    return mock_conn, mock_proc


class _FakeAsyncContextManager:
    """Async context manager that yields (conn, proc)."""

    def __init__(self, conn: Any, proc: Any) -> None:
        self._conn = conn
        self._proc = proc
        self.exited = False

    async def __aenter__(self) -> tuple[Any, Any]:
        return self._conn, self._proc

    async def __aexit__(self, *args: Any) -> None:
        self.exited = True
        pass


# ---------------------------------------------------------------------------
# T031-1: Basic execute flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestAcpStepExecutorBasicExecute:
    """Basic execute flow tests."""

    async def test_returns_executor_result(self) -> None:
        """execute() returns an ExecutorResult with success=True."""
        executor = _make_executor()
        mock_conn, mock_proc = _mock_spawn_context(accumulated_text="agent output")

        with patch("maverick.executor.acp.spawn_agent_process") as mock_spawn:
            mock_spawn.return_value = _FakeAsyncContextManager(mock_conn, mock_proc)

            # Patch get_accumulated_text on the client created by the executor
            with patch.object(
                MaverickAcpClient, "get_accumulated_text", return_value="agent output"
            ):
                result = await executor.execute(
                    step_name="my_step",
                    agent_name="test_agent",
                    prompt={"key": "value"},
                )

        assert isinstance(result, ExecutorResult)
        assert result.success is True
        assert result.output == "agent output"
        assert result.usage is None
        assert result.events == ()

    async def test_calls_build_prompt(self) -> None:
        """execute() calls agent.build_prompt() with the prompt context."""
        called_with: list[Any] = []

        reg = ComponentRegistry()

        class _TrackingAgent:
            name = "tracking"

            def build_prompt(self, context: Any) -> str:
                called_with.append(context)
                return "built prompt"

            async def execute(self, context: Any) -> str:
                return ""

        reg.agents.register("tracking", _TrackingAgent, validate=False)

        provider_registry = _make_provider_registry()
        executor = AcpStepExecutor(
            provider_registry=provider_registry,
            agent_registry=reg,
        )
        mock_conn, mock_proc = _mock_spawn_context()

        with patch("maverick.executor.acp.spawn_agent_process") as mock_spawn:
            mock_spawn.return_value = _FakeAsyncContextManager(mock_conn, mock_proc)
            with patch.object(
                MaverickAcpClient, "get_accumulated_text", return_value=""
            ):
                await executor.execute(
                    step_name="s",
                    agent_name="tracking",
                    prompt={"my_key": "my_val"},
                )

        assert called_with == [{"my_key": "my_val"}]

    async def test_calls_new_session_and_prompt(self) -> None:
        """execute() calls conn.new_session() and conn.prompt()."""
        executor = _make_executor()
        mock_conn, mock_proc = _mock_spawn_context()

        with patch("maverick.executor.acp.spawn_agent_process") as mock_spawn:
            mock_spawn.return_value = _FakeAsyncContextManager(mock_conn, mock_proc)
            with patch.object(
                MaverickAcpClient, "get_accumulated_text", return_value="output"
            ):
                await executor.execute(
                    step_name="s",
                    agent_name="test_agent",
                    prompt={},
                )

        mock_conn.new_session.assert_awaited_once()
        mock_conn.prompt.assert_awaited_once()

    async def test_raises_for_unknown_agent(self) -> None:
        """execute() raises ReferenceResolutionError for unknown agent."""
        executor = _make_executor()

        with pytest.raises(ReferenceResolutionError):
            await executor.execute(
                step_name="s",
                agent_name="nonexistent_agent",
                prompt={},
            )


# ---------------------------------------------------------------------------
# T031-2: Prompt building with instructions prepended
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestInstructionsPrepended:
    """Instructions are prepended to the prompt in [SYSTEM INSTRUCTIONS] format."""

    async def test_instructions_prepended_to_prompt(self) -> None:
        """Instructions are prepended with system header."""
        captured_prompts: list[str] = []

        mock_conn, mock_proc = _mock_spawn_context()

        # Capture the prompt text sent to conn.prompt()
        async def _capture_prompt(*args: Any, **kwargs: Any) -> None:
            # The prompt is a list of text_block objects; extract text
            if "prompt" in kwargs:
                blocks = kwargs["prompt"]
                for block in blocks:
                    if hasattr(block, "text"):
                        captured_prompts.append(block.text)

        mock_conn.prompt = AsyncMock(side_effect=_capture_prompt)

        executor = _make_executor(build_prompt_return="the raw prompt")

        with patch("maverick.executor.acp.spawn_agent_process") as mock_spawn:
            mock_spawn.return_value = _FakeAsyncContextManager(mock_conn, mock_proc)
            with patch.object(
                MaverickAcpClient, "get_accumulated_text", return_value=""
            ):
                await executor.execute(
                    step_name="s",
                    agent_name="test_agent",
                    prompt={},
                    instructions="Be careful.",
                )

        # At least one prompt call should have happened
        assert len(captured_prompts) >= 1
        combined = " ".join(captured_prompts)
        assert "[SYSTEM INSTRUCTIONS]" in combined
        assert "Be careful." in combined
        assert "the raw prompt" in combined

    async def test_no_instructions_uses_raw_prompt(self) -> None:
        """Without instructions, the raw prompt is used directly."""
        captured_prompts: list[str] = []

        mock_conn, mock_proc = _mock_spawn_context()

        async def _capture_prompt(*args: Any, **kwargs: Any) -> None:
            if "prompt" in kwargs:
                blocks = kwargs["prompt"]
                for block in blocks:
                    if hasattr(block, "text"):
                        captured_prompts.append(block.text)

        mock_conn.prompt = AsyncMock(side_effect=_capture_prompt)

        executor = _make_executor(build_prompt_return="raw prompt only")

        with patch("maverick.executor.acp.spawn_agent_process") as mock_spawn:
            mock_spawn.return_value = _FakeAsyncContextManager(mock_conn, mock_proc)
            with patch.object(
                MaverickAcpClient, "get_accumulated_text", return_value=""
            ):
                await executor.execute(
                    step_name="s",
                    agent_name="test_agent",
                    prompt={},
                    instructions=None,
                )

        combined = " ".join(captured_prompts)
        assert "[SYSTEM INSTRUCTIONS]" not in combined
        assert "raw prompt only" in combined


# ---------------------------------------------------------------------------
# T031-3: Structured output extraction — fenced ```json ... ``` block
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestStructuredOutputFenced:
    """Structured output extracted from fenced JSON code blocks."""

    async def test_extracts_fenced_json_block(self) -> None:
        """Extracts and validates JSON from fenced ```json ... ``` block."""
        json_text = '```json\n{"message": "hello", "count": 42}\n```'
        executor = _make_executor(build_prompt_return="x")
        mock_conn, mock_proc = _mock_spawn_context()

        with patch("maverick.executor.acp.spawn_agent_process") as mock_spawn:
            mock_spawn.return_value = _FakeAsyncContextManager(mock_conn, mock_proc)
            with patch.object(
                MaverickAcpClient,
                "get_accumulated_text",
                return_value=json_text,
            ):
                result = await executor.execute(
                    step_name="s",
                    agent_name="test_agent",
                    prompt={},
                    output_schema=_SampleOutput,
                )

        assert isinstance(result.output, _SampleOutput)
        assert result.output.message == "hello"
        assert result.output.count == 42

    async def test_extracts_last_fenced_block_when_multiple(self) -> None:
        """When multiple fenced blocks, extracts the last one."""
        json_text = (
            "```json\n"
            '{"message": "first", "count": 1}\n'
            "```\n"
            "Some text\n"
            "```json\n"
            '{"message": "last", "count": 99}\n'
            "```"
        )
        executor = _make_executor()
        mock_conn, mock_proc = _mock_spawn_context()

        with patch("maverick.executor.acp.spawn_agent_process") as mock_spawn:
            mock_spawn.return_value = _FakeAsyncContextManager(mock_conn, mock_proc)
            with patch.object(
                MaverickAcpClient,
                "get_accumulated_text",
                return_value=json_text,
            ):
                result = await executor.execute(
                    step_name="s",
                    agent_name="test_agent",
                    prompt={},
                    output_schema=_SampleOutput,
                )

        assert result.output.message == "last"
        assert result.output.count == 99


# ---------------------------------------------------------------------------
# T031-4: Structured output extraction — raw {…} brace-matched JSON
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestStructuredOutputBraceMatched:
    """Structured output extracted from raw brace-matched JSON."""

    async def test_extracts_raw_json_object(self) -> None:
        """Extracts JSON from raw brace-matched block when no fenced block."""
        json_text = 'Here is my answer: {"message": "world", "count": 7}'
        executor = _make_executor()
        mock_conn, mock_proc = _mock_spawn_context()

        with patch("maverick.executor.acp.spawn_agent_process") as mock_spawn:
            mock_spawn.return_value = _FakeAsyncContextManager(mock_conn, mock_proc)
            with patch.object(
                MaverickAcpClient,
                "get_accumulated_text",
                return_value=json_text,
            ):
                result = await executor.execute(
                    step_name="s",
                    agent_name="test_agent",
                    prompt={},
                    output_schema=_SampleOutput,
                )

        assert isinstance(result.output, _SampleOutput)
        assert result.output.message == "world"
        assert result.output.count == 7


# ---------------------------------------------------------------------------
# T031-5: Structured output validation error → OutputSchemaValidationError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestStructuredOutputValidationError:
    """OutputSchemaValidationError raised when JSON fails schema validation."""

    async def test_raises_on_invalid_schema(self) -> None:
        """Raises OutputSchemaValidationError when JSON is structurally valid
        but fails Pydantic schema validation."""
        # count should be int, not string
        json_text = '```json\n{"message": "hi", "count": "not_an_int"}\n```'
        executor = _make_executor()
        mock_conn, mock_proc = _mock_spawn_context()

        with patch("maverick.executor.acp.spawn_agent_process") as mock_spawn:
            mock_spawn.return_value = _FakeAsyncContextManager(mock_conn, mock_proc)
            with patch.object(
                MaverickAcpClient,
                "get_accumulated_text",
                return_value=json_text,
            ):
                with pytest.raises(OutputSchemaValidationError) as exc_info:
                    await executor.execute(
                        step_name="my_step",
                        agent_name="test_agent",
                        prompt={},
                        output_schema=_SampleOutput,
                    )

        assert exc_info.value.step_name == "my_step"
        assert exc_info.value.schema_type is _SampleOutput


# ---------------------------------------------------------------------------
# T056: Structured output extraction edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestStructuredOutputEdgeCases:
    """T056: Edge cases in _extract_json_output / no-schema path."""

    async def test_no_json_block_returns_plain_text(self) -> None:
        """When output_schema is None, plain text is returned as-is."""
        executor = _make_executor()
        mock_conn, mock_proc = _mock_spawn_context()

        with patch("maverick.executor.acp.spawn_agent_process") as mock_spawn:
            mock_spawn.return_value = _FakeAsyncContextManager(mock_conn, mock_proc)
            with patch.object(
                MaverickAcpClient,
                "get_accumulated_text",
                return_value="Just plain text output, no JSON here.",
            ):
                result = await executor.execute(
                    step_name="plain_step",
                    agent_name="test_agent",
                    prompt={},
                    output_schema=None,
                )

        assert isinstance(result, ExecutorResult)
        assert result.output == "Just plain text output, no JSON here."

    async def test_malformed_json_raises_output_schema_validation_error(self) -> None:
        """When JSON fails schema validation, OutputSchemaValidationError is raised."""
        executor = _make_executor()
        mock_conn, mock_proc = _mock_spawn_context()

        # Valid JSON syntax but wrong types for the schema
        with patch("maverick.executor.acp.spawn_agent_process") as mock_spawn:
            mock_spawn.return_value = _FakeAsyncContextManager(mock_conn, mock_proc)
            with patch.object(
                MaverickAcpClient,
                "get_accumulated_text",
                return_value='```json\n{"message": 123, "count": "wrong"}\n```',
            ):
                with pytest.raises(OutputSchemaValidationError) as exc_info:
                    await executor.execute(
                        step_name="malformed_step",
                        agent_name="test_agent",
                        prompt={},
                        output_schema=_SampleOutput,
                    )

        assert exc_info.value.step_name == "malformed_step"

    async def test_nested_json_blocks_extracts_last(self) -> None:
        """When multiple JSON blocks exist, the last one is extracted."""
        executor = _make_executor()
        mock_conn, mock_proc = _mock_spawn_context()

        # First block has invalid schema, last block is valid
        output_text = (
            '```json\n{"message": "first block", "count": "wrong_type"}\n```\n'
            "Some intermediate text\n"
            '```json\n{"message": "last block", "count": 42}\n```'
        )

        with patch("maverick.executor.acp.spawn_agent_process") as mock_spawn:
            mock_spawn.return_value = _FakeAsyncContextManager(mock_conn, mock_proc)
            with patch.object(
                MaverickAcpClient,
                "get_accumulated_text",
                return_value=output_text,
            ):
                result = await executor.execute(
                    step_name="nested_step",
                    agent_name="test_agent",
                    prompt={},
                    output_schema=_SampleOutput,
                )

        assert isinstance(result, ExecutorResult)
        assert isinstance(result.output, _SampleOutput)
        assert result.output.message == "last block"
        assert result.output.count == 42

    async def test_no_json_block_with_schema_raises_malformed(self) -> None:
        """When no JSON found with output_schema, MalformedResponseError raised."""
        executor = _make_executor()
        mock_conn, mock_proc = _mock_spawn_context()

        with patch("maverick.executor.acp.spawn_agent_process") as mock_spawn:
            mock_spawn.return_value = _FakeAsyncContextManager(mock_conn, mock_proc)
            with patch.object(
                MaverickAcpClient,
                "get_accumulated_text",
                return_value="No JSON in this output at all.",
            ):
                with pytest.raises(MalformedResponseError) as exc_info:
                    await executor.execute(
                        step_name="no_json_step",
                        agent_name="test_agent",
                        prompt={},
                        output_schema=_SampleOutput,
                    )

        assert "no_json_step" in str(exc_info.value)


# ---------------------------------------------------------------------------
# _parse_json_lenient: escaped single quote handling
# ---------------------------------------------------------------------------


class TestParseJsonLenient:
    """Tests for _parse_json_lenient edge cases."""

    def test_escaped_single_quotes_sanitized(self) -> None:
        """LLM-produced \\' in JSON strings should be stripped to bare '."""
        from maverick.executor.acp import _parse_json_lenient

        json_str = (
            '{"summary": "The agent\\\'s output was correct", "count": 1}'
        )
        result = _parse_json_lenient(json_str, "test_step")
        assert result["summary"] == "The agent's output was correct"
        assert result["count"] == 1

    def test_valid_json_unchanged(self) -> None:
        """Valid JSON passes through without modification."""
        from maverick.executor.acp import _parse_json_lenient

        json_str = '{"message": "hello", "count": 42}'
        result = _parse_json_lenient(json_str, "test_step")
        assert result["message"] == "hello"

    def test_truncated_json_repaired(self) -> None:
        """Truncated JSON is repaired by closing open structures."""
        from maverick.executor.acp import _parse_json_lenient

        json_str = '{"message": "hello"'
        result = _parse_json_lenient(json_str, "test_step")
        assert result["message"] == "hello"


# ---------------------------------------------------------------------------
# T031-6: Connection caching — same provider reuses connection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestConnectionCaching:
    """Connection caching: same provider reuses connection on second call."""

    async def test_same_provider_reuses_connection(self) -> None:
        """spawn_agent_process called only once for the same provider."""
        executor = _make_executor()
        mock_conn, mock_proc = _mock_spawn_context()

        spawn_count = 0

        class _CountingContextManager:
            async def __aenter__(self) -> tuple[Any, Any]:
                nonlocal spawn_count
                spawn_count += 1
                return mock_conn, mock_proc

            async def __aexit__(self, *args: Any) -> None:
                pass

        with patch("maverick.executor.acp.spawn_agent_process") as mock_spawn:
            mock_spawn.return_value = _CountingContextManager()
            with patch.object(
                MaverickAcpClient, "get_accumulated_text", return_value="out"
            ):
                await executor.execute(
                    step_name="s1",
                    agent_name="test_agent",
                    prompt={},
                )
                await executor.execute(
                    step_name="s2",
                    agent_name="test_agent",
                    prompt={},
                )

        assert spawn_count == 1

    async def test_different_providers_spawn_separate_connections(self) -> None:
        """Different providers each get their own subprocess."""
        provider_registry = AgentProviderRegistry(
            {
                "p1": AgentProviderConfig(command=["fake-p1"], default=True),
                "p2": AgentProviderConfig(command=["fake-p2"]),
            }
        )
        agent_registry = _make_agent_registry()
        executor = AcpStepExecutor(
            provider_registry=provider_registry,
            agent_registry=agent_registry,
        )

        mock_conn1, mock_proc1 = _mock_spawn_context(accumulated_text="out1")
        mock_conn2, mock_proc2 = _mock_spawn_context(accumulated_text="out2")

        calls: list[str] = []

        def _make_ctx(conn: Any, proc: Any, name: str) -> Any:
            class _Ctx:
                async def __aenter__(self) -> tuple[Any, Any]:
                    calls.append(name)
                    return conn, proc

                async def __aexit__(self, *args: Any) -> None:
                    pass

            return _Ctx()

        side_effects = [
            _make_ctx(mock_conn1, mock_proc1, "p1"),
            _make_ctx(mock_conn2, mock_proc2, "p2"),
        ]

        with patch("maverick.executor.acp.spawn_agent_process") as mock_spawn:
            mock_spawn.side_effect = side_effects
            with patch.object(
                MaverickAcpClient, "get_accumulated_text", return_value="out"
            ):
                await executor.execute(
                    step_name="s1",
                    agent_name="test_agent",
                    prompt={},
                    config=StepConfig(provider="p1"),
                )
                await executor.execute(
                    step_name="s2",
                    agent_name="test_agent",
                    prompt={},
                    config=StepConfig(provider="p2"),
                )

        assert len(calls) == 2
        assert "p1" in calls
        assert "p2" in calls


# ---------------------------------------------------------------------------
# T031-7: cleanup() terminates all cached subprocesses
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCleanup:
    """cleanup() terminates all cached subprocesses."""

    async def test_cleanup_exits_context_manager(self) -> None:
        """cleanup() exits the spawn context manager."""
        executor = _make_executor()
        mock_conn, mock_proc = _mock_spawn_context()
        fake_ctx = _FakeAsyncContextManager(mock_conn, mock_proc)

        with patch("maverick.executor.acp.spawn_agent_process") as mock_spawn:
            mock_spawn.return_value = fake_ctx
            with patch.object(
                MaverickAcpClient, "get_accumulated_text", return_value="out"
            ):
                await executor.execute(
                    step_name="s",
                    agent_name="test_agent",
                    prompt={},
                )

        assert not fake_ctx.exited
        await executor.cleanup()
        assert fake_ctx.exited

    async def test_cleanup_clears_connection_cache(self) -> None:
        """cleanup() empties _connections cache."""
        executor = _make_executor()
        mock_conn, mock_proc = _mock_spawn_context()

        with patch("maverick.executor.acp.spawn_agent_process") as mock_spawn:
            mock_spawn.return_value = _FakeAsyncContextManager(mock_conn, mock_proc)
            with patch.object(
                MaverickAcpClient, "get_accumulated_text", return_value="out"
            ):
                await executor.execute(
                    step_name="s",
                    agent_name="test_agent",
                    prompt={},
                )

        assert len(executor._connections) == 1
        await executor.cleanup()
        assert len(executor._connections) == 0

    async def test_cleanup_safe_when_no_connections(self) -> None:
        """cleanup() is safe to call with no cached connections."""
        executor = _make_executor()
        # Should not raise
        await executor.cleanup()

    async def test_cleanup_safe_when_called_twice(self) -> None:
        """cleanup() is idempotent."""
        executor = _make_executor()
        mock_conn, mock_proc = _mock_spawn_context()

        with patch("maverick.executor.acp.spawn_agent_process") as mock_spawn:
            mock_spawn.return_value = _FakeAsyncContextManager(mock_conn, mock_proc)
            with patch.object(
                MaverickAcpClient, "get_accumulated_text", return_value="out"
            ):
                await executor.execute(
                    step_name="s",
                    agent_name="test_agent",
                    prompt={},
                )

        await executor.cleanup()
        await executor.cleanup()  # Should not raise


# ---------------------------------------------------------------------------
# T031-8: Lifecycle logging at correct levels
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestLifecycleLogging:
    """Lifecycle events logged at INFO (spawn/cleanup) and DEBUG (session/prompt)."""

    async def test_info_logged_on_spawn(self) -> None:
        """subprocess_spawn event logged at INFO level."""
        executor = _make_executor()
        mock_conn, mock_proc = _mock_spawn_context()

        info_events: list[str] = []

        original_info = executor._logger.info

        def _capture_info(event: str, **kwargs: Any) -> None:
            info_events.append(event)

        executor._logger.info = _capture_info  # type: ignore[assignment]

        with patch("maverick.executor.acp.spawn_agent_process") as mock_spawn:
            mock_spawn.return_value = _FakeAsyncContextManager(mock_conn, mock_proc)
            with patch.object(
                MaverickAcpClient, "get_accumulated_text", return_value="out"
            ):
                await executor.execute(
                    step_name="s",
                    agent_name="test_agent",
                    prompt={},
                )

        assert any("subprocess_spawn" in e for e in info_events)
        assert any("step_start" in e for e in info_events)
        assert any("step_complete" in e for e in info_events)

        executor._logger.info = original_info  # type: ignore[assignment]

    async def test_info_logged_on_cleanup(self) -> None:
        """cleanup event logged at INFO level per connection."""
        executor = _make_executor()
        mock_conn, mock_proc = _mock_spawn_context()

        with patch("maverick.executor.acp.spawn_agent_process") as mock_spawn:
            mock_spawn.return_value = _FakeAsyncContextManager(mock_conn, mock_proc)
            with patch.object(
                MaverickAcpClient, "get_accumulated_text", return_value="out"
            ):
                await executor.execute(
                    step_name="s",
                    agent_name="test_agent",
                    prompt={},
                )

        info_events: list[str] = []

        def _capture_info(event: str, **kwargs: Any) -> None:
            info_events.append(event)

        executor._logger.info = _capture_info  # type: ignore[assignment]
        await executor.cleanup()

        assert any("cleanup" in e for e in info_events)

    async def test_debug_logged_for_session_create(self) -> None:
        """session_create event logged at DEBUG level."""
        executor = _make_executor()
        mock_conn, mock_proc = _mock_spawn_context()

        debug_events: list[str] = []

        def _capture_debug(event: str, **kwargs: Any) -> None:
            debug_events.append(event)

        executor._logger.debug = _capture_debug  # type: ignore[assignment]

        with patch("maverick.executor.acp.spawn_agent_process") as mock_spawn:
            mock_spawn.return_value = _FakeAsyncContextManager(mock_conn, mock_proc)
            with patch.object(
                MaverickAcpClient, "get_accumulated_text", return_value="out"
            ):
                await executor.execute(
                    step_name="s",
                    agent_name="test_agent",
                    prompt={},
                )

        assert any("session_create" in e for e in debug_events)
        assert any("prompt_send" in e for e in debug_events)


# ---------------------------------------------------------------------------
# T034: Multi-provider scenarios
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestMultiProviderScenarios:
    """Multi-provider selection logic in AcpStepExecutor.execute()."""

    async def test_explicit_provider_selects_correct_config(self) -> None:
        """config.provider='claude' selects that provider's config."""
        provider_registry = AgentProviderRegistry(
            {
                "claude": AgentProviderConfig(command=["claude-agent"], default=True),
                "gemini": AgentProviderConfig(command=["gemini-agent"]),
            }
        )
        agent_registry = _make_agent_registry()
        executor = AcpStepExecutor(
            provider_registry=provider_registry,
            agent_registry=agent_registry,
        )

        mock_conn, mock_proc = _mock_spawn_context()
        captured_commands: list[str] = []

        def _spawn_side_effect(
            client: Any, command: str, *args: Any, **kwargs: Any
        ) -> Any:
            captured_commands.append(command)
            return _FakeAsyncContextManager(mock_conn, mock_proc)

        with patch(
            "maverick.executor.acp.spawn_agent_process", side_effect=_spawn_side_effect
        ):
            with patch.object(
                MaverickAcpClient, "get_accumulated_text", return_value="out"
            ):
                await executor.execute(
                    step_name="s",
                    agent_name="test_agent",
                    prompt={},
                    config=StepConfig(provider="claude"),
                )

        assert captured_commands == ["claude-agent"]

    async def test_none_provider_uses_default(self) -> None:
        """Step with config.provider=None uses the default provider."""
        provider_registry = AgentProviderRegistry(
            {
                "claude": AgentProviderConfig(command=["claude-agent"], default=True),
                "gemini": AgentProviderConfig(command=["gemini-agent"]),
            }
        )
        agent_registry = _make_agent_registry()
        executor = AcpStepExecutor(
            provider_registry=provider_registry,
            agent_registry=agent_registry,
        )

        mock_conn, mock_proc = _mock_spawn_context()
        captured_commands: list[str] = []

        def _spawn_side_effect(
            client: Any, command: str, *args: Any, **kwargs: Any
        ) -> Any:
            captured_commands.append(command)
            return _FakeAsyncContextManager(mock_conn, mock_proc)

        with patch(
            "maverick.executor.acp.spawn_agent_process", side_effect=_spawn_side_effect
        ):
            with patch.object(
                MaverickAcpClient, "get_accumulated_text", return_value="out"
            ):
                # No explicit provider — should use the default ("claude")
                await executor.execute(
                    step_name="s",
                    agent_name="test_agent",
                    prompt={},
                    config=StepConfig(provider=None),
                )

        assert captured_commands == ["claude-agent"]

    async def test_unknown_provider_raises_config_error(self) -> None:
        """Step with config.provider='nonexistent' raises ConfigError."""
        provider_registry = AgentProviderRegistry(
            {
                "claude": AgentProviderConfig(command=["claude-agent"], default=True),
            }
        )
        agent_registry = _make_agent_registry()
        executor = AcpStepExecutor(
            provider_registry=provider_registry,
            agent_registry=agent_registry,
        )

        with pytest.raises(ConfigError):
            await executor.execute(
                step_name="s",
                agent_name="test_agent",
                prompt={},
                config=StepConfig(provider="nonexistent"),
            )


# ---------------------------------------------------------------------------
# T042: Error resilience scenarios
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestErrorResilience:
    """Error resilience: timeout, retry, subprocess errors, ACP request errors."""

    async def test_timeout_raises_maverick_timeout_error(self) -> None:
        """When conn.prompt() times out, MaverickTimeoutError is raised."""
        executor = _make_executor()
        mock_conn, mock_proc = _mock_spawn_context()

        # Make conn.prompt raise asyncio.TimeoutError (simulates wait_for timeout)
        mock_conn.prompt = AsyncMock(side_effect=TimeoutError())

        with patch("maverick.executor.acp.spawn_agent_process") as mock_spawn:
            mock_spawn.return_value = _FakeAsyncContextManager(mock_conn, mock_proc)
            with pytest.raises(MaverickTimeoutError):
                await executor.execute(
                    step_name="s",
                    agent_name="test_agent",
                    prompt={},
                    config=StepConfig(timeout=5),
                )

    async def test_retry_creates_fresh_sessions(self) -> None:
        """When prompt() fails twice then succeeds, new_session() is called 3 times."""
        executor = _make_executor()
        mock_conn, mock_proc = _mock_spawn_context()

        # Fail twice, succeed third time
        call_count = 0

        async def _prompt_side_effect(*args: Any, **kwargs: Any) -> None:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("transient failure")

        mock_conn.prompt = AsyncMock(side_effect=_prompt_side_effect)

        with patch("maverick.executor.acp.spawn_agent_process") as mock_spawn:
            mock_spawn.return_value = _FakeAsyncContextManager(mock_conn, mock_proc)
            with patch.object(
                MaverickAcpClient, "get_accumulated_text", return_value="success"
            ):
                with patch("maverick.executor.acp.wait_exponential"):
                    result = await executor.execute(
                        step_name="s",
                        agent_name="test_agent",
                        prompt={},
                        config=StepConfig(max_retries=2),
                    )

        assert result.success is True
        # new_session should be called once per attempt: 3 total
        assert mock_conn.new_session.call_count == 3

    async def test_command_not_found_raises_cli_not_found_error(self) -> None:
        """FileNotFoundError from spawn_agent_process raises CLINotFoundError."""
        executor = _make_executor()

        with patch(
            "maverick.executor.acp.spawn_agent_process",
            side_effect=FileNotFoundError("fake-agent: not found"),
        ):
            with pytest.raises(CLINotFoundError):
                await executor.execute(
                    step_name="s",
                    agent_name="test_agent",
                    prompt={},
                )

    async def test_subprocess_oserror_raises_process_error(self) -> None:
        """When spawn_agent_process raises OSError, ProcessError is raised."""
        executor = _make_executor()

        with patch(
            "maverick.executor.acp.spawn_agent_process",
            side_effect=OSError("failed to spawn"),
        ):
            with pytest.raises(ProcessError):
                await executor.execute(
                    step_name="s",
                    agent_name="test_agent",
                    prompt={},
                )

    async def test_acp_request_error_during_prompt_raises_network_error_after_reconnect(
        self,
    ) -> None:
        """When conn.prompt() raises AcpRequestError, reconnect is attempted.

        If the retry after reconnect also fails with AcpRequestError, a
        NetworkError is raised (transparent reconnect exhausted, FR-021).
        """
        executor = _make_executor()
        mock_conn, mock_proc = _mock_spawn_context()

        # Both the original prompt AND the retry-after-reconnect fail
        mock_conn.prompt = AsyncMock(
            side_effect=AcpRequestError(code=500, message="ACP request failed")
        )

        with patch("maverick.executor.acp.spawn_agent_process") as mock_spawn:
            mock_spawn.return_value = _FakeAsyncContextManager(mock_conn, mock_proc)
            with pytest.raises(NetworkError):
                await executor.execute(
                    step_name="s",
                    agent_name="test_agent",
                    prompt={},
                )


# ---------------------------------------------------------------------------
# T040: Transparent reconnect on connection drop (FR-021)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTransparentReconnect:
    """Transparent reconnect on AcpRequestError from new_session() or prompt()."""

    async def test_reconnect_on_new_session_failure_then_success(self) -> None:
        """When new_session() raises AcpRequestError, reconnect is attempted.

        If the second new_session() succeeds, the step completes normally.
        """
        executor = _make_executor()

        # First connection: new_session fails once
        mock_conn1, mock_proc1 = _mock_spawn_context()
        mock_conn1.new_session = AsyncMock(
            side_effect=[
                AcpRequestError(code=503, message="dropped"),
                MagicMock(session_id="sess-new"),
            ]
        )

        # Second connection (after reconnect): new_session and prompt succeed
        mock_conn2, mock_proc2 = _mock_spawn_context()
        mock_conn2.new_session = AsyncMock(
            return_value=MagicMock(session_id="sess-reconnect")
        )

        spawn_call_count = 0

        def _spawn_side_effect(
            client: Any, command: str, *args: Any, **kwargs: Any
        ) -> Any:
            nonlocal spawn_call_count
            spawn_call_count += 1
            if spawn_call_count == 1:
                return _FakeAsyncContextManager(mock_conn1, mock_proc1)
            return _FakeAsyncContextManager(mock_conn2, mock_proc2)

        with patch(
            "maverick.executor.acp.spawn_agent_process",
            side_effect=_spawn_side_effect,
        ):
            with patch.object(
                MaverickAcpClient, "get_accumulated_text", return_value="reconnected"
            ):
                result = await executor.execute(
                    step_name="s",
                    agent_name="test_agent",
                    prompt={},
                )

        assert result.success is True
        assert result.output == "reconnected"

    async def test_reconnect_on_new_session_failure_also_fails_raises_network_error(
        self,
    ) -> None:
        """new_session() failing after reconnect raises NetworkError."""
        executor = _make_executor()
        mock_conn, mock_proc = _mock_spawn_context()

        # new_session always raises AcpRequestError
        mock_conn.new_session = AsyncMock(
            side_effect=AcpRequestError(code=503, message="connection lost")
        )

        with patch("maverick.executor.acp.spawn_agent_process") as mock_spawn:
            mock_spawn.return_value = _FakeAsyncContextManager(mock_conn, mock_proc)
            with pytest.raises(NetworkError):
                await executor.execute(
                    step_name="s",
                    agent_name="test_agent",
                    prompt={},
                )

    async def test_reconnect_on_prompt_failure_then_success(self) -> None:
        """When conn.prompt() raises AcpRequestError, reconnect is attempted.

        If the retry prompt on the new connection succeeds, the step completes.
        """
        executor = _make_executor()

        # First connection: prompt fails
        mock_conn1, mock_proc1 = _mock_spawn_context()
        mock_conn1.prompt = AsyncMock(
            side_effect=AcpRequestError(code=503, message="transport error")
        )

        # Second connection (after reconnect): prompt succeeds
        mock_conn2, mock_proc2 = _mock_spawn_context()
        mock_conn2.prompt = AsyncMock(return_value=None)

        spawn_call_count = 0

        def _spawn_side_effect(
            client: Any, command: str, *args: Any, **kwargs: Any
        ) -> Any:
            nonlocal spawn_call_count
            spawn_call_count += 1
            if spawn_call_count == 1:
                return _FakeAsyncContextManager(mock_conn1, mock_proc1)
            return _FakeAsyncContextManager(mock_conn2, mock_proc2)

        with patch(
            "maverick.executor.acp.spawn_agent_process",
            side_effect=_spawn_side_effect,
        ):
            with patch.object(
                MaverickAcpClient,
                "get_accumulated_text",
                return_value="after reconnect",
            ):
                result = await executor.execute(
                    step_name="s",
                    agent_name="test_agent",
                    prompt={},
                )

        assert result.success is True
        assert result.output == "after reconnect"

    async def test_reconnect_removes_stale_connection_from_cache(self) -> None:
        """After reconnect, the stale connection is replaced in _connections."""
        executor = _make_executor()
        mock_conn1, mock_proc1 = _mock_spawn_context()
        mock_conn1.new_session = AsyncMock(
            side_effect=AcpRequestError(code=503, message="dropped")
        )

        mock_conn2, mock_proc2 = _mock_spawn_context()
        spawn_call_count = 0

        def _spawn_side_effect(
            client: Any, command: str, *args: Any, **kwargs: Any
        ) -> Any:
            nonlocal spawn_call_count
            spawn_call_count += 1
            if spawn_call_count == 1:
                return _FakeAsyncContextManager(mock_conn1, mock_proc1)
            return _FakeAsyncContextManager(mock_conn2, mock_proc2)

        with patch(
            "maverick.executor.acp.spawn_agent_process",
            side_effect=_spawn_side_effect,
        ):
            with patch.object(
                MaverickAcpClient, "get_accumulated_text", return_value="ok"
            ):
                await executor.execute(
                    step_name="s",
                    agent_name="test_agent",
                    prompt={},
                )

        # After reconnect, the cached connection should be the new one (conn2)
        assert "claude" in executor._connections
        assert executor._connections["claude"].conn is mock_conn2

    async def test_reconnect_logs_attempt_and_success_at_info(self) -> None:
        """_reconnect() logs reconnect_attempt and reconnect_success at INFO level."""
        executor = _make_executor()

        mock_conn1, mock_proc1 = _mock_spawn_context()
        mock_conn1.new_session = AsyncMock(
            side_effect=AcpRequestError(code=503, message="dropped")
        )

        mock_conn2, mock_proc2 = _mock_spawn_context()
        spawn_call_count = 0

        def _spawn_side_effect(
            client: Any, command: str, *args: Any, **kwargs: Any
        ) -> Any:
            nonlocal spawn_call_count
            spawn_call_count += 1
            if spawn_call_count == 1:
                return _FakeAsyncContextManager(mock_conn1, mock_proc1)
            return _FakeAsyncContextManager(mock_conn2, mock_proc2)

        info_events: list[str] = []

        def _capture_info(event: str, **kwargs: Any) -> None:
            info_events.append(event)

        executor._logger.info = _capture_info  # type: ignore[assignment]

        with patch(
            "maverick.executor.acp.spawn_agent_process",
            side_effect=_spawn_side_effect,
        ):
            with patch.object(
                MaverickAcpClient, "get_accumulated_text", return_value="ok"
            ):
                await executor.execute(
                    step_name="s",
                    agent_name="test_agent",
                    prompt={},
                )

        assert any("reconnect_attempt" in e for e in info_events)
        assert any("reconnect_success" in e for e in info_events)


# ---------------------------------------------------------------------------
# Model validation: _get_available_model_ids
# ---------------------------------------------------------------------------


class TestGetAvailableModelIds:
    """Tests for _get_available_model_ids helper."""

    def test_extracts_from_models_attribute(self) -> None:
        """Extracts model IDs from session.models.available_models."""
        model_a = MagicMock()
        model_a.model_id = "sonnet"
        model_b = MagicMock()
        model_b.model_id = "opus"
        models = MagicMock()
        models.available_models = [model_a, model_b]

        session = MagicMock()
        session.models = models
        session.config_options = None

        assert _get_available_model_ids(session) == {"sonnet", "opus"}

    def test_extracts_from_config_options(self) -> None:
        """Extracts model IDs from config_options with id='model'."""
        opt_a = MagicMock()
        opt_a.value = "default"
        opt_b = MagicMock()
        opt_b.value = "haiku"
        config_opt = MagicMock()
        config_opt.root = config_opt  # root == self
        config_opt.id = "model"
        config_opt.options = [opt_a, opt_b]

        session = MagicMock()
        session.models = None
        session.config_options = [config_opt]

        assert _get_available_model_ids(session) == {"default", "haiku"}

    def test_merges_both_sources(self) -> None:
        """Merges models from both session.models and config_options."""
        model = MagicMock()
        model.model_id = "sonnet"
        models = MagicMock()
        models.available_models = [model]

        opt_val = MagicMock()
        opt_val.value = "haiku"
        config_opt = MagicMock()
        config_opt.root = config_opt
        config_opt.id = "model"
        config_opt.options = [opt_val]

        session = MagicMock()
        session.models = models
        session.config_options = [config_opt]

        assert _get_available_model_ids(session) == {"sonnet", "haiku"}

    def test_empty_when_no_models_info(self) -> None:
        """Returns empty set when session has no models info."""
        session = MagicMock()
        session.models = None
        session.config_options = None

        assert _get_available_model_ids(session) == set()

    def test_skips_non_model_config_options(self) -> None:
        """Ignores config_options that are not id='model'."""
        config_opt = MagicMock()
        config_opt.root = config_opt
        config_opt.id = "mode"
        config_opt.options = [MagicMock(value="agent")]

        session = MagicMock()
        session.models = None
        session.config_options = [config_opt]

        assert _get_available_model_ids(session) == set()

    def test_skips_none_values(self) -> None:
        """Skips options with None value."""
        opt = MagicMock()
        opt.value = None
        config_opt = MagicMock()
        config_opt.root = config_opt
        config_opt.id = "model"
        config_opt.options = [opt]

        session = MagicMock()
        session.models = None
        session.config_options = [config_opt]

        assert _get_available_model_ids(session) == set()


# ---------------------------------------------------------------------------
# Model validation: executor rejects unavailable models
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestModelValidation:
    """Tests for model validation in execute()."""

    async def test_raises_on_unavailable_model(self) -> None:
        """Executor raises AgentError when model is not in available list."""
        executor = _make_executor()
        mock_conn, mock_proc = _mock_spawn_context()

        # Add available models to the session mock
        mock_session = mock_conn.new_session.return_value
        model_obj = MagicMock()
        model_obj.model_id = "sonnet"
        mock_session.models = MagicMock(available_models=[model_obj])
        mock_session.config_options = None

        with patch("maverick.executor.acp.spawn_agent_process") as mock_spawn:
            mock_spawn.return_value = _FakeAsyncContextManager(mock_conn, mock_proc)
            with pytest.raises(AgentError, match="not available"):
                await executor.execute(
                    step_name="s",
                    agent_name="test_agent",
                    prompt={},
                    config=StepConfig(model_id="nonexistent-model"),
                )

    async def test_error_lists_available_models(self) -> None:
        """AgentError message includes the list of available models."""
        executor = _make_executor()
        mock_conn, mock_proc = _mock_spawn_context()

        mock_session = mock_conn.new_session.return_value
        m1 = MagicMock(model_id="haiku")
        m2 = MagicMock(model_id="sonnet")
        mock_session.models = MagicMock(available_models=[m1, m2])
        mock_session.config_options = None

        with patch("maverick.executor.acp.spawn_agent_process") as mock_spawn:
            mock_spawn.return_value = _FakeAsyncContextManager(mock_conn, mock_proc)
            with pytest.raises(AgentError, match="haiku.*sonnet"):
                await executor.execute(
                    step_name="s",
                    agent_name="test_agent",
                    prompt={},
                    config=StepConfig(model_id="gpt-5"),
                )

    async def test_proceeds_when_model_available(self) -> None:
        """Executor proceeds normally when model matches available list."""
        executor = _make_executor()
        mock_conn, mock_proc = _mock_spawn_context(accumulated_text="done")

        mock_session = mock_conn.new_session.return_value
        model_obj = MagicMock(model_id="sonnet")
        mock_session.models = MagicMock(available_models=[model_obj])
        mock_session.config_options = None

        with patch("maverick.executor.acp.spawn_agent_process") as mock_spawn:
            mock_spawn.return_value = _FakeAsyncContextManager(mock_conn, mock_proc)
            with patch.object(
                MaverickAcpClient, "get_accumulated_text", return_value="done"
            ):
                result = await executor.execute(
                    step_name="s",
                    agent_name="test_agent",
                    prompt={},
                    config=StepConfig(model_id="sonnet"),
                )

        assert result.success is True

    async def test_skips_validation_when_no_models_advertised(self) -> None:
        """Executor skips validation when provider advertises no models."""
        executor = _make_executor()
        mock_conn, mock_proc = _mock_spawn_context(accumulated_text="ok")

        mock_session = mock_conn.new_session.return_value
        mock_session.models = None
        mock_session.config_options = None

        with patch("maverick.executor.acp.spawn_agent_process") as mock_spawn:
            mock_spawn.return_value = _FakeAsyncContextManager(mock_conn, mock_proc)
            with patch.object(
                MaverickAcpClient, "get_accumulated_text", return_value="ok"
            ):
                result = await executor.execute(
                    step_name="s",
                    agent_name="test_agent",
                    prompt={},
                    config=StepConfig(model_id="any-model"),
                )

        assert result.success is True
