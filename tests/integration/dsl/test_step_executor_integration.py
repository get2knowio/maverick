"""Integration tests for StepExecutor protocol + execute_agent_step.

Tests:
- Mock StepExecutor injection via context.step_executor
- ClaudeStepExecutor end-to-end with mock MaverickAgent
- output_schema resolution and validation
- executor_config deserialization
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import BaseModel

from maverick.dsl.context import WorkflowContext
from maverick.dsl.events import AgentStreamChunk
from maverick.dsl.executor.claude import ClaudeStepExecutor
from maverick.dsl.executor.errors import OutputSchemaValidationError
from maverick.dsl.executor.protocol import StepExecutor
from maverick.dsl.executor.result import ExecutorResult
from maverick.dsl.serialization.executor.handlers.agent_step import execute_agent_step
from maverick.dsl.serialization.executor.handlers.models import HandlerOutput
from maverick.dsl.serialization.registry import ComponentRegistry
from maverick.dsl.serialization.schema import AgentStepRecord
from maverick.exceptions import ConfigError

# ── helpers ─────────────────────────────────────────────────────────────────


def _make_step(
    agent: str = "test_agent",
    output_schema: str | None = None,
    executor_config: dict | None = None,
) -> AgentStepRecord:
    """Create a test AgentStepRecord."""
    return AgentStepRecord(
        name="test_step",
        type="agent",
        agent=agent,
        output_schema=output_schema,
        executor_config=executor_config,
    )


def _make_context(executor: StepExecutor | None = None) -> WorkflowContext:
    """Create a WorkflowContext with optional step_executor."""
    ctx = WorkflowContext(inputs={})
    ctx.step_executor = executor
    return ctx


_CONTEXT_BUILDER_PATH = (
    "maverick.dsl.serialization.executor.handlers.agent_step.resolve_context_builder"
)


# ── mock executor injection ──────────────────────────────────────────────────


class TestMockExecutorInjection:
    """Tests for mock StepExecutor injection via context.step_executor."""

    async def test_mock_executor_called_with_correct_params(self) -> None:
        """execute_agent_step calls executor.execute() with correct params."""
        mock_result = ExecutorResult(
            output="mock result",
            success=True,
            usage=None,
            events=(),
        )
        mock_executor = AsyncMock(spec=ClaudeStepExecutor)
        mock_executor.execute = AsyncMock(return_value=mock_result)

        registry = ComponentRegistry()

        class _DummyAgent:
            async def execute(self, ctx: Any) -> str:
                return "dummy"

        registry.agents.register("test_agent", _DummyAgent, validate=False)

        context = _make_context(executor=mock_executor)
        step = _make_step(agent="test_agent")

        with patch(
            _CONTEXT_BUILDER_PATH,
            new=AsyncMock(return_value={"key": "value"}),
        ):
            await execute_agent_step(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
            )

        # Verify mock's execute() was called
        mock_executor.execute.assert_called_once()
        call_kwargs = mock_executor.execute.call_args.kwargs
        assert call_kwargs["step_name"] == "test_step"
        assert call_kwargs["agent_name"] == "test_agent"

    async def test_handler_output_result_equals_executor_result_output(self) -> None:
        """HandlerOutput.result equals ExecutorResult.output."""
        mock_result = ExecutorResult(
            output={"key": "value"},
            success=True,
            usage=None,
            events=(),
        )
        mock_executor = AsyncMock(spec=ClaudeStepExecutor)
        mock_executor.execute = AsyncMock(return_value=mock_result)

        registry = ComponentRegistry()

        class _DummyAgent:
            async def execute(self, ctx: Any) -> dict:
                return {}

        registry.agents.register("test_agent", _DummyAgent, validate=False)

        context = _make_context(executor=mock_executor)
        step = _make_step()

        with patch(
            _CONTEXT_BUILDER_PATH,
            new=AsyncMock(return_value={}),
        ):
            output = await execute_agent_step(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
            )

        assert isinstance(output, HandlerOutput)
        assert output.result == mock_result.output

    async def test_handler_output_events_match_executor_result_events_no_callback(
        self,
    ) -> None:
        """HandlerOutput.events == list(ExecutorResult.events).

        Asserted when no event_callback is provided.
        """
        chunk = AgentStreamChunk(
            step_name="test_step",
            agent_name="test_agent",
            text="streaming chunk",
            chunk_type="output",
        )
        mock_result = ExecutorResult(
            output="result",
            success=True,
            usage=None,
            events=(chunk,),
        )
        mock_executor = AsyncMock(spec=ClaudeStepExecutor)
        mock_executor.execute = AsyncMock(return_value=mock_result)

        registry = ComponentRegistry()

        class _DummyAgent:
            async def execute(self, ctx: Any) -> str:
                return "dummy"

        registry.agents.register("test_agent", _DummyAgent, validate=False)

        context = _make_context(executor=mock_executor)
        step = _make_step()

        with patch(
            _CONTEXT_BUILDER_PATH,
            new=AsyncMock(return_value={}),
        ):
            output = await execute_agent_step(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
                event_callback=None,  # No callback
            )

        assert isinstance(output, HandlerOutput)
        assert output.events == list(mock_result.events)

    async def test_handler_output_events_empty_when_callback_provided(self) -> None:
        """With event_callback, HandlerOutput.events is empty (no double-emission)."""
        chunk = AgentStreamChunk(
            step_name="test_step",
            agent_name="test_agent",
            text="streaming chunk",
            chunk_type="output",
        )
        mock_result = ExecutorResult(
            output="result",
            success=True,
            usage=None,
            events=(chunk,),
        )
        mock_executor = AsyncMock(spec=ClaudeStepExecutor)
        mock_executor.execute = AsyncMock(return_value=mock_result)

        registry = ComponentRegistry()

        class _DummyAgent:
            async def execute(self, ctx: Any) -> str:
                return "dummy"

        registry.agents.register("test_agent", _DummyAgent, validate=False)

        context = _make_context(executor=mock_executor)
        step = _make_step()

        async def event_callback(event: Any) -> None:
            pass

        with patch(
            _CONTEXT_BUILDER_PATH,
            new=AsyncMock(return_value={}),
        ):
            output = await execute_agent_step(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
                event_callback=event_callback,
            )

        # Events should be empty to avoid double-emission
        assert isinstance(output, HandlerOutput)
        assert output.events == []


# ── ClaudeStepExecutor end-to-end ────────────────────────────────────────────


class TestClaudeStepExecutorEndToEnd:
    """End-to-end tests using ClaudeStepExecutor with mock MaverickAgent."""

    async def test_claude_executor_produces_correct_output(self) -> None:
        """ClaudeStepExecutor runs mock agent and produces correct HandlerOutput."""

        class _MockAgent:
            name = "test-agent"

            async def execute(self, context: Any) -> str:
                return "expected output"

        registry = ComponentRegistry()
        registry.agents.register("test_agent", _MockAgent, validate=False)

        executor = ClaudeStepExecutor(registry=registry)
        context = _make_context(executor=executor)
        step = _make_step()

        with patch(
            _CONTEXT_BUILDER_PATH,
            new=AsyncMock(return_value={"data": "context"}),
        ):
            output = await execute_agent_step(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
            )

        assert isinstance(output, HandlerOutput)
        assert output.result == "expected output"

    async def test_claude_executor_streaming_events_forwarded(self) -> None:
        """ClaudeStepExecutor forwards streaming events via event_callback."""

        # Use a list to capture the stream callback set by the executor
        _callbacks: list[Any] = []

        class _StreamingAgent:
            name = "streamer"
            stream_callback: Any = None

            async def execute(self, context: Any) -> str:
                # If stream_callback was set by executor, call it
                if self.stream_callback is not None:
                    await self.stream_callback("chunk data")
                return "done"

        registry = ComponentRegistry()
        registry.agents.register("streaming_agent", _StreamingAgent, validate=False)

        executor = ClaudeStepExecutor(registry=registry)
        context = _make_context(executor=executor)
        step = _make_step(agent="streaming_agent")

        received: list[AgentStreamChunk] = []

        async def callback(event: Any) -> None:
            if isinstance(event, AgentStreamChunk):
                received.append(event)

        with patch(
            _CONTEXT_BUILDER_PATH,
            new=AsyncMock(return_value={}),
        ):
            await execute_agent_step(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
                event_callback=callback,
            )

        # Should have received output chunks from the stream_callback
        output_chunks = [e for e in received if e.chunk_type == "output"]
        assert any("chunk data" in c.text for c in output_chunks)

    async def test_no_step_executor_falls_back_to_new_claude_executor(self) -> None:
        """Handler creates a default ClaudeStepExecutor.

        Triggered when context.step_executor is None.
        """

        class _MockAgent:
            name = "mock"

            async def execute(self, context: Any) -> str:
                return "fallback result"

        registry = ComponentRegistry()
        registry.agents.register("test_agent", _MockAgent, validate=False)

        # No executor in context
        context = _make_context(executor=None)
        step = _make_step()

        with patch(
            _CONTEXT_BUILDER_PATH,
            new=AsyncMock(return_value={}),
        ):
            output = await execute_agent_step(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
            )

        assert isinstance(output, HandlerOutput)
        assert output.result == "fallback result"

    async def test_claude_executor_usage_metadata_extracted(self) -> None:
        """ClaudeStepExecutor extracts usage metadata.

        Verifies extraction from agent result when available.
        """

        class _UsageResult:
            """Simulates an agent result with usage metadata."""

            class Usage:
                input_tokens = 100
                output_tokens = 50
                cache_read_tokens = 10
                cache_write_tokens = 5
                total_cost_usd = 0.001

        class _AgentWithUsage:
            name = "usage-agent"

            async def execute(self, context: Any) -> _UsageResult:
                return _UsageResult()

        registry = ComponentRegistry()
        registry.agents.register("usage_agent", _AgentWithUsage, validate=False)

        executor = ClaudeStepExecutor(registry=registry)

        result = await executor.execute(
            step_name="usage_step",
            agent_name="usage_agent",
            prompt={"context": "test"},
        )

        assert result.success is True
        assert result.usage is not None
        assert result.usage.input_tokens == 100
        assert result.usage.output_tokens == 50


# ── output_schema end-to-end ──────────────────────────────────────────────────


class TestOutputSchemaEndToEnd:
    """End-to-end tests for output_schema YAML field → Pydantic validation."""

    async def test_output_schema_none_returns_raw_result(self) -> None:
        """Without output_schema, agent raw result is returned unchanged."""

        class _Agent:
            name = "reviewer"

            async def execute(self, context: Any) -> dict[str, Any]:
                return {"summary": "good code", "score": 95}

        registry = ComponentRegistry()
        registry.agents.register("review_agent", _Agent, validate=False)

        executor = ClaudeStepExecutor(registry=registry)
        context = _make_context(executor=executor)

        step = AgentStepRecord(
            name="review_step",
            type="agent",
            agent="review_agent",
            output_schema=None,
        )

        with patch(
            _CONTEXT_BUILDER_PATH,
            new=AsyncMock(return_value={}),
        ):
            output = await execute_agent_step(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
            )

        assert isinstance(output, HandlerOutput)
        assert isinstance(output.result, dict)
        assert output.result["summary"] == "good code"

    async def test_invalid_output_schema_path_raises_config_error(self) -> None:
        """Invalid dotted path for output_schema raises ConfigError."""

        class _Agent:
            name = "test"

            async def execute(self, context: Any) -> str:
                return "result"

        registry = ComponentRegistry()
        registry.agents.register("test_agent", _Agent, validate=False)

        executor = ClaudeStepExecutor(registry=registry)
        context = _make_context(executor=executor)

        step = AgentStepRecord(
            name="test_step",
            type="agent",
            agent="test_agent",
            output_schema="nonexistent.module.SomeClass",
        )

        with patch(
            _CONTEXT_BUILDER_PATH,
            new=AsyncMock(return_value={}),
        ):
            with pytest.raises(ConfigError):
                await execute_agent_step(
                    step=step,
                    resolved_inputs={},
                    context=context,
                    registry=registry,
                )

    async def test_output_schema_validates_dict_output(self) -> None:
        """When output_schema is valid, executor validates agent dict output."""

        class _ReviewResult(BaseModel):
            summary: str
            score: int = 0

        class _Agent:
            name = "reviewer"

            async def execute(self, context: Any) -> dict[str, Any]:
                return {"summary": "great", "score": 99}

        registry = ComponentRegistry()
        registry.agents.register("schema_agent", _Agent, validate=False)

        executor = ClaudeStepExecutor(registry=registry)

        # Directly test executor with output_schema
        result = await executor.execute(
            step_name="schema_step",
            agent_name="schema_agent",
            prompt={},
            output_schema=_ReviewResult,
        )

        assert result.success is True
        assert isinstance(result.output, _ReviewResult)
        assert result.output.summary == "great"
        assert result.output.score == 99

    async def test_output_schema_raises_on_invalid_data(self) -> None:
        """OutputSchemaValidationError raised on invalid data.

        Agent output that fails schema validation triggers it.
        """

        class _StrictResult(BaseModel):
            required_field: str  # This field is required

        class _BadAgent:
            name = "bad"

            async def execute(self, context: Any) -> dict[str, Any]:
                return {"unexpected": "data"}  # Missing required_field

        registry = ComponentRegistry()
        registry.agents.register("bad_agent", _BadAgent, validate=False)

        executor = ClaudeStepExecutor(registry=registry)

        with pytest.raises(OutputSchemaValidationError) as exc_info:
            await executor.execute(
                step_name="bad_step",
                agent_name="bad_agent",
                prompt={},
                output_schema=_StrictResult,
            )

        assert exc_info.value.step_name == "bad_step"
        assert exc_info.value.schema_type is _StrictResult


# ── executor_config deserialization ──────────────────────────────────────────


class TestExecutorConfigEndToEnd:
    """Tests for executor_config YAML field deserialization."""

    async def test_executor_config_timeout_applied(self) -> None:
        """executor_config timeout is applied to the step."""

        class _SlowAgent:
            name = "slow"

            async def execute(self, context: Any) -> str:
                await asyncio.sleep(10.0)
                return "too late"

        registry = ComponentRegistry()
        registry.agents.register("slow_agent", _SlowAgent, validate=False)

        executor = ClaudeStepExecutor(registry=registry)
        context = _make_context(executor=executor)

        step = AgentStepRecord(
            name="slow_step",
            type="agent",
            agent="slow_agent",
            executor_config={"timeout": 1},  # 1 second
        )

        with patch(
            _CONTEXT_BUILDER_PATH,
            new=AsyncMock(return_value={}),
        ):
            with pytest.raises((asyncio.TimeoutError, TimeoutError)):
                await execute_agent_step(
                    step=step,
                    resolved_inputs={},
                    context=context,
                    registry=registry,
                )

    async def test_executor_config_unknown_key_raises_config_error(self) -> None:
        """executor_config with unknown key raises ConfigError."""

        class _Agent:
            name = "test"

            async def execute(self, context: Any) -> str:
                return "result"

        registry = ComponentRegistry()
        registry.agents.register("test_agent", _Agent, validate=False)

        executor = ClaudeStepExecutor(registry=registry)
        context = _make_context(executor=executor)

        step = AgentStepRecord(
            name="test_step",
            type="agent",
            agent="test_agent",
            executor_config={"unknown_key": "value"},
        )

        with patch(
            _CONTEXT_BUILDER_PATH,
            new=AsyncMock(return_value={}),
        ):
            with pytest.raises(ConfigError):
                await execute_agent_step(
                    step=step,
                    resolved_inputs={},
                    context=context,
                    registry=registry,
                )

    async def test_no_executor_config_uses_default(self) -> None:
        """Without executor_config, DEFAULT_EXECUTOR_CONFIG is applied."""

        class _Agent:
            name = "test"

            async def execute(self, context: Any) -> str:
                return "result"

        registry = ComponentRegistry()
        registry.agents.register("test_agent", _Agent, validate=False)

        executor = ClaudeStepExecutor(registry=registry)
        context = _make_context(executor=executor)

        step = _make_step()  # No executor_config

        with patch(
            _CONTEXT_BUILDER_PATH,
            new=AsyncMock(return_value={}),
        ):
            output = await execute_agent_step(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
            )

        assert isinstance(output, HandlerOutput)
        assert output.result == "result"

    async def test_executor_config_model_override_passed_to_executor(self) -> None:
        """executor_config model override is deserialized.

        Verified available on StepExecutorConfig.
        """

        class _Agent:
            name = "test"

            async def execute(self, context: Any) -> str:
                return "result"

        registry = ComponentRegistry()
        registry.agents.register("test_agent", _Agent, validate=False)

        captured_config: list[Any] = []

        class _CapturingExecutor:
            async def execute(self, **kwargs: Any) -> ExecutorResult:
                captured_config.append(kwargs.get("config"))
                return ExecutorResult(
                    output="captured",
                    success=True,
                    usage=None,
                    events=(),
                )

        context = _make_context(executor=_CapturingExecutor())  # type: ignore[arg-type]

        step = AgentStepRecord(
            name="test_step",
            type="agent",
            agent="test_agent",
            executor_config={"model": "claude-opus-4-6", "timeout": 120},
        )

        with patch(
            _CONTEXT_BUILDER_PATH,
            new=AsyncMock(return_value={}),
        ):
            output = await execute_agent_step(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
            )

        assert isinstance(output, HandlerOutput)
        assert len(captured_config) == 1
        config = captured_config[0]
        assert config is not None
        assert config.model == "claude-opus-4-6"
        assert config.timeout == 120

    async def test_executor_config_retry_policy_deserialized(self) -> None:
        """executor_config retry_policy dict is deserialized to RetryPolicy."""
        from maverick.dsl.executor.config import RetryPolicy

        captured_config: list[Any] = []

        class _Agent:
            name = "test"

            async def execute(self, context: Any) -> str:
                return "result"

        registry = ComponentRegistry()
        registry.agents.register("test_agent", _Agent, validate=False)

        class _CapturingExecutor:
            async def execute(self, **kwargs: Any) -> ExecutorResult:
                captured_config.append(kwargs.get("config"))
                return ExecutorResult(
                    output="done",
                    success=True,
                    usage=None,
                    events=(),
                )

        context = _make_context(executor=_CapturingExecutor())  # type: ignore[arg-type]

        step = AgentStepRecord(
            name="test_step",
            type="agent",
            agent="test_agent",
            executor_config={
                "retry_policy": {
                    "max_attempts": 5,
                    "wait_min": 2.0,
                    "wait_max": 30.0,
                }
            },
        )

        with patch(
            _CONTEXT_BUILDER_PATH,
            new=AsyncMock(return_value={}),
        ):
            await execute_agent_step(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
            )

        assert len(captured_config) == 1
        config = captured_config[0]
        assert config is not None
        assert isinstance(config.retry_policy, RetryPolicy)
        assert config.retry_policy.max_attempts == 5
        assert config.retry_policy.wait_min == 2.0
        assert config.retry_policy.wait_max == 30.0


# ── StepExecutor protocol conformance ────────────────────────────────────────


class TestStepExecutorProtocolConformance:
    """Tests verifying that ClaudeStepExecutor conforms to StepExecutor protocol."""

    def test_claude_executor_satisfies_step_executor_protocol(self) -> None:
        """ClaudeStepExecutor is a runtime instance of StepExecutor protocol."""
        registry = ComponentRegistry()
        executor = ClaudeStepExecutor(registry=registry)

        # StepExecutor is @runtime_checkable, so isinstance() works
        assert isinstance(executor, StepExecutor)

    def test_step_executor_protocol_is_runtime_checkable(self) -> None:
        """StepExecutor protocol supports isinstance() checks."""

        class _CustomExecutor:
            async def execute(self, **kwargs: Any) -> ExecutorResult:
                return ExecutorResult(output=None, success=True, usage=None, events=())

        executor = _CustomExecutor()
        assert isinstance(executor, StepExecutor)

    async def test_mock_satisfying_protocol_works_as_step_executor(self) -> None:
        """Any async object with execute() can serve as StepExecutor via injection."""

        class _MinimalExecutor:
            async def execute(
                self,
                *,
                step_name: str,
                agent_name: str,
                prompt: Any,
                **kwargs: Any,
            ) -> ExecutorResult:
                return ExecutorResult(
                    output=f"executed_{step_name}",
                    success=True,
                    usage=None,
                    events=(),
                )

        registry = ComponentRegistry()

        class _DummyAgent:
            async def execute(self, ctx: Any) -> str:
                return "dummy"

        registry.agents.register("test_agent", _DummyAgent, validate=False)

        context = _make_context(executor=_MinimalExecutor())  # type: ignore[arg-type]
        step = _make_step()

        with patch(
            _CONTEXT_BUILDER_PATH,
            new=AsyncMock(return_value={}),
        ):
            output = await execute_agent_step(
                step=step,
                resolved_inputs={},
                context=context,
                registry=registry,
            )

        assert isinstance(output, HandlerOutput)
        assert output.result == "executed_test_step"
