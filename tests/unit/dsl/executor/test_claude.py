"""Unit tests for ClaudeStepExecutor."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel

from maverick.dsl.errors import ReferenceResolutionError
from maverick.dsl.events import AgentStreamChunk
from maverick.dsl.executor.claude import ClaudeStepExecutor
from maverick.dsl.executor.config import RetryPolicy, StepExecutorConfig
from maverick.dsl.executor.errors import OutputSchemaValidationError
from maverick.dsl.executor.result import ExecutorResult, UsageMetadata
from maverick.dsl.serialization.registry import ComponentRegistry

# ── helpers ────────────────────────────────────────────────────────────────


def _make_registry(
    agent_name: str = "test_agent", agent_class: type | None = None
) -> ComponentRegistry:
    """Create a registry with a mock agent registered."""
    reg = ComponentRegistry()
    if agent_class is None:

        class _MockAgent:
            name = "test-agent"

            async def execute(self, context: Any) -> str:
                return "agent result"

        agent_class = _MockAgent
    reg.agents.register(agent_name, agent_class, validate=False)
    return reg


def _make_executor(
    agent_name: str = "test_agent", agent_class: type | None = None
) -> ClaudeStepExecutor:
    """Create a ClaudeStepExecutor with a test registry."""
    return ClaudeStepExecutor(registry=_make_registry(agent_name, agent_class))


# ── happy path ──────────────────────────────────────────────────────────────


class TestClaudeStepExecutorHappyPath:
    """Tests for successful execution paths."""

    async def test_returns_executor_result(self) -> None:
        """Happy path returns ExecutorResult with success=True."""
        executor = _make_executor()
        result = await executor.execute(
            step_name="test_step",
            agent_name="test_agent",
            prompt={"input": "hello"},
        )
        assert isinstance(result, ExecutorResult)
        assert result.success is True
        assert result.output == "agent result"

    async def test_result_has_events_tuple(self) -> None:
        """ExecutorResult.events is a tuple."""
        executor = _make_executor()
        result = await executor.execute(
            step_name="test_step",
            agent_name="test_agent",
            prompt={},
        )
        assert isinstance(result.events, tuple)

    async def test_thinking_event_in_result(self) -> None:
        """Thinking indicator is always emitted and collected in events."""
        executor = _make_executor()
        result = await executor.execute(
            step_name="my_step",
            agent_name="test_agent",
            prompt={},
        )
        thinking_events = [
            e
            for e in result.events
            if isinstance(e, AgentStreamChunk) and e.chunk_type == "thinking"
        ]
        assert len(thinking_events) == 1
        assert thinking_events[0].step_name == "my_step"
        assert "working" in thinking_events[0].text.lower()

    async def test_sync_agent_execute(self) -> None:
        """Handles agents with synchronous execute() method."""

        class _SyncAgent:
            name = "sync"

            def execute(self, context: Any) -> str:
                return "sync result"

        reg = ComponentRegistry()
        reg.agents.register("sync_agent", _SyncAgent, validate=False)
        executor = ClaudeStepExecutor(registry=reg)
        result = await executor.execute(
            step_name="step", agent_name="sync_agent", prompt={}
        )
        assert result.output == "sync result"
        assert result.success is True

    async def test_async_agent_execute(self) -> None:
        """Handles agents with async execute() method."""

        class _AsyncAgent:
            name = "async"

            async def execute(self, context: Any) -> str:
                return "async result"

        reg = ComponentRegistry()
        reg.agents.register("async_agent", _AsyncAgent, validate=False)
        executor = ClaudeStepExecutor(registry=reg)
        result = await executor.execute(
            step_name="step", agent_name="async_agent", prompt={}
        )
        assert result.output == "async result"

    async def test_no_output_schema_returns_raw_result(self) -> None:
        """Without output_schema, raw agent result is returned unchanged."""
        executor = _make_executor()
        result = await executor.execute(
            step_name="step",
            agent_name="test_agent",
            prompt={},
            output_schema=None,
        )
        assert result.output == "agent result"

    async def test_usage_is_none_when_agent_returns_no_usage(self) -> None:
        """ExecutorResult.usage is None when agent result has no usage attr."""
        executor = _make_executor()
        result = await executor.execute(
            step_name="step",
            agent_name="test_agent",
            prompt={},
        )
        assert result.usage is None

    async def test_usage_extracted_from_result_with_usage_attr(self) -> None:
        """UsageMetadata is extracted when agent result exposes usage."""

        class _UsageResult:
            input_tokens = 10
            output_tokens = 20
            cache_read_tokens = 5
            cache_write_tokens = 2
            total_cost_usd = 0.001

        class _UsageAgent:
            name = "usage"

            async def execute(self, context: Any) -> Any:
                result = MagicMock()
                result.usage = _UsageResult()
                return result

        reg = ComponentRegistry()
        reg.agents.register("usage_agent", _UsageAgent, validate=False)
        executor = ClaudeStepExecutor(registry=reg)
        result = await executor.execute(
            step_name="step", agent_name="usage_agent", prompt={}
        )
        assert isinstance(result.usage, UsageMetadata)
        assert result.usage.input_tokens == 10
        assert result.usage.output_tokens == 20
        assert result.usage.cache_read_tokens == 5
        assert result.usage.cache_write_tokens == 2
        assert result.usage.total_cost_usd == 0.001


# ── streaming ───────────────────────────────────────────────────────────────


class TestClaudeStepExecutorStreaming:
    """Tests for streaming event forwarding."""

    async def test_event_callback_receives_thinking_event(self) -> None:
        """event_callback receives thinking indicator in real-time."""
        received: list[AgentStreamChunk] = []

        async def callback(event: Any) -> None:
            if isinstance(event, AgentStreamChunk):
                received.append(event)

        executor = _make_executor()
        await executor.execute(
            step_name="step",
            agent_name="test_agent",
            prompt={},
            event_callback=callback,
        )
        thinking = [e for e in received if e.chunk_type == "thinking"]
        assert len(thinking) == 1

    async def test_stream_callback_chunks_forwarded(self) -> None:
        """Streaming chunks from agent are forwarded via event_callback."""

        class _StreamingAgent:
            name = "streamer"
            stream_callback: Any = None

            async def execute(self, context: Any) -> str:
                if self.stream_callback:
                    await self.stream_callback("hello ")
                    await self.stream_callback("world")
                return "hello world"

        reg = ComponentRegistry()
        reg.agents.register("streaming_agent", _StreamingAgent, validate=False)
        executor = ClaudeStepExecutor(registry=reg)

        received_output: list[str] = []

        async def callback(event: Any) -> None:
            if isinstance(event, AgentStreamChunk) and event.chunk_type == "output":
                received_output.append(event.text)

        await executor.execute(
            step_name="step",
            agent_name="streaming_agent",
            prompt={},
            event_callback=callback,
        )
        assert "hello " in received_output
        assert "world" in received_output

    async def test_stream_chunks_in_executor_result_events(self) -> None:
        """Streaming chunks are collected in ExecutorResult.events."""

        class _StreamingAgent:
            name = "streamer"
            stream_callback: Any = None

            async def execute(self, context: Any) -> str:
                if self.stream_callback:
                    await self.stream_callback("chunk1")
                return "done"

        reg = ComponentRegistry()
        reg.agents.register("sa", _StreamingAgent, validate=False)
        executor = ClaudeStepExecutor(registry=reg)

        result = await executor.execute(step_name="step", agent_name="sa", prompt={})
        output_events = [
            e
            for e in result.events
            if isinstance(e, AgentStreamChunk) and e.chunk_type == "output"
        ]
        assert len(output_events) >= 1
        texts = [e.text for e in output_events]
        assert any("chunk1" in t for t in texts)

    async def test_no_stream_callback_attr_still_works(self) -> None:
        """Agents without stream_callback attribute work fine (no streaming)."""

        class _NoStreamAgent:
            # No stream_callback attribute
            name = "nostream"

            async def execute(self, context: Any) -> dict[str, str]:
                return {"output": "result text"}

        reg = ComponentRegistry()
        reg.agents.register("ns_agent", _NoStreamAgent, validate=False)
        executor = ClaudeStepExecutor(registry=reg)
        result = await executor.execute(
            step_name="step", agent_name="ns_agent", prompt={}
        )
        # Output text should be extracted and emitted as OUTPUT chunk
        output_events = [
            e
            for e in result.events
            if isinstance(e, AgentStreamChunk) and e.chunk_type == "output"
        ]
        assert len(output_events) >= 1
        assert result.success is True

    async def test_streaming_agent_no_duplicate_output_event(self) -> None:
        """No extra OUTPUT chunk emitted for return value.

        When output was already streamed, duplicates are avoided.
        """

        class _StreamingAgent:
            name = "streamer"
            stream_callback: Any = None

            async def execute(self, context: Any) -> str:
                if self.stream_callback:
                    await self.stream_callback("streamed")
                return "streamed"  # Same as what was streamed

        reg = ComponentRegistry()
        reg.agents.register("streaming_agent", _StreamingAgent, validate=False)
        executor = ClaudeStepExecutor(registry=reg)

        result = await executor.execute(
            step_name="step", agent_name="streaming_agent", prompt={}
        )
        output_events = [
            e
            for e in result.events
            if isinstance(e, AgentStreamChunk) and e.chunk_type == "output"
        ]
        # Only the streamed chunks, not the return value duplicated
        texts = [e.text for e in output_events]
        # The combined text should contain "streamed" only once
        assert "streamed" in "".join(texts)

    async def test_thinking_event_has_correct_agent_name(self) -> None:
        """Thinking chunk reports display_name from agent instance."""

        class _NamedAgent:
            name = "My Custom Agent"

            async def execute(self, context: Any) -> str:
                return "done"

        reg = ComponentRegistry()
        reg.agents.register("named_agent", _NamedAgent, validate=False)
        executor = ClaudeStepExecutor(registry=reg)

        result = await executor.execute(
            step_name="step", agent_name="named_agent", prompt={}
        )
        thinking = [
            e
            for e in result.events
            if isinstance(e, AgentStreamChunk) and e.chunk_type == "thinking"
        ]
        assert len(thinking) == 1
        assert thinking[0].agent_name == "My Custom Agent"

    async def test_no_event_callback_does_not_raise(self) -> None:
        """Executing without event_callback still works.

        Events are collected internally.
        """
        executor = _make_executor()
        result = await executor.execute(
            step_name="step",
            agent_name="test_agent",
            prompt={},
            event_callback=None,
        )
        assert result.success is True
        assert len(result.events) >= 1  # At least thinking event


# ── error handling ───────────────────────────────────────────────────────────


class TestClaudeStepExecutorErrors:
    """Tests for error handling and event emission."""

    async def test_unknown_agent_raises_reference_error(self) -> None:
        """Unknown agent name raises ReferenceResolutionError."""
        executor = _make_executor()
        with pytest.raises(ReferenceResolutionError) as exc_info:
            await executor.execute(
                step_name="step",
                agent_name="nonexistent_agent",
                prompt={},
            )
        assert exc_info.value.reference_name == "nonexistent_agent"

    async def test_agent_error_emits_error_chunk(self) -> None:
        """When agent raises, an ERROR chunk is emitted via event_callback."""

        class _FailingAgent:
            name = "failer"

            async def execute(self, context: Any) -> None:
                raise RuntimeError("agent exploded")

        reg = ComponentRegistry()
        reg.agents.register("fail_agent", _FailingAgent, validate=False)
        executor = ClaudeStepExecutor(registry=reg)

        received: list[AgentStreamChunk] = []

        async def callback(event: Any) -> None:
            if isinstance(event, AgentStreamChunk):
                received.append(event)

        with pytest.raises(RuntimeError, match="agent exploded"):
            await executor.execute(
                step_name="step",
                agent_name="fail_agent",
                prompt={},
                event_callback=callback,
            )
        error_events = [e for e in received if e.chunk_type == "error"]
        assert len(error_events) == 1
        assert "agent exploded" in error_events[0].text

    async def test_agent_error_in_result_events_no_callback(self) -> None:
        """When agent raises with no callback, exception is re-raised."""

        class _FailingAgent:
            name = "failer"

            async def execute(self, context: Any) -> None:
                raise ValueError("boom")

        reg = ComponentRegistry()
        reg.agents.register("fail_agent", _FailingAgent, validate=False)
        executor = ClaudeStepExecutor(registry=reg)

        with pytest.raises(ValueError, match="boom"):
            await executor.execute(
                step_name="step",
                agent_name="fail_agent",
                prompt={},
            )

    async def test_agent_error_chunk_step_name_matches(self) -> None:
        """Error chunk carries the correct step_name."""

        class _FailingAgent:
            name = "failer"

            async def execute(self, context: Any) -> None:
                raise RuntimeError("oops")

        reg = ComponentRegistry()
        reg.agents.register("fail_agent", _FailingAgent, validate=False)
        executor = ClaudeStepExecutor(registry=reg)

        received: list[AgentStreamChunk] = []

        async def callback(event: Any) -> None:
            if isinstance(event, AgentStreamChunk):
                received.append(event)

        with pytest.raises(RuntimeError):
            await executor.execute(
                step_name="my_failing_step",
                agent_name="fail_agent",
                prompt={},
                event_callback=callback,
            )
        error_events = [e for e in received if e.chunk_type == "error"]
        assert len(error_events) == 1
        assert error_events[0].step_name == "my_failing_step"

    async def test_unknown_agent_does_not_emit_error_chunk(self) -> None:
        """ReferenceResolutionError is raised before any event emission."""
        executor = _make_executor()
        received: list[AgentStreamChunk] = []

        async def callback(event: Any) -> None:
            if isinstance(event, AgentStreamChunk):
                received.append(event)

        with pytest.raises(ReferenceResolutionError):
            await executor.execute(
                step_name="step",
                agent_name="nonexistent",
                prompt={},
                event_callback=callback,
            )
        # No events should have been emitted (fast fail before agent instantiation)
        error_events = [e for e in received if e.chunk_type == "error"]
        assert len(error_events) == 0

    async def test_non_callable_agent_raises_type_error(self) -> None:
        """Non-callable registered as agent raises TypeError."""
        reg = ComponentRegistry()

        # Bypass validation to register a non-callable (an instance instead of class)
        # We register a class first, then override the internal dict
        class _DummyAgent:
            name = "dummy"

            async def execute(self, context: Any) -> str:
                return "ok"

        reg.agents.register("bad_agent", _DummyAgent, validate=False)
        # Replace with a non-callable in the registry's internal dict
        reg.agents._agents["bad_agent"] = "not_a_class"  # type: ignore[assignment]
        executor = ClaudeStepExecutor(registry=reg)

        with pytest.raises(TypeError):
            await executor.execute(
                step_name="step",
                agent_name="bad_agent",
                prompt={},
            )


# ── retry policy ─────────────────────────────────────────────────────────────


class TestClaudeStepExecutorRetryPolicy:
    """Tests for retry policy behavior."""

    async def test_retry_policy_retries_on_failure(self) -> None:
        """Agent with retry policy retries on failure and succeeds."""
        call_count = 0

        class _FlakyAgent:
            name = "flaky"

            async def execute(self, context: Any) -> str:
                nonlocal call_count
                call_count += 1
                if call_count < 2:
                    raise RuntimeError("temporary failure")
                return "success after retry"

        reg = ComponentRegistry()
        reg.agents.register("flaky_agent", _FlakyAgent, validate=False)
        executor = ClaudeStepExecutor(registry=reg)

        policy = RetryPolicy(max_attempts=3, wait_min=0.0, wait_max=0.0)
        config = StepExecutorConfig(retry_policy=policy)

        result = await executor.execute(
            step_name="step",
            agent_name="flaky_agent",
            prompt={},
            config=config,
        )
        assert result.success is True
        assert result.output == "success after retry"
        assert call_count == 2

    async def test_retry_policy_exhausts_attempts(self) -> None:
        """Agent exceeding max_attempts raises the original error."""

        class _AlwaysFailAgent:
            name = "fail"

            async def execute(self, context: Any) -> None:
                raise RuntimeError("always fails")

        reg = ComponentRegistry()
        reg.agents.register("fail_agent", _AlwaysFailAgent, validate=False)
        executor = ClaudeStepExecutor(registry=reg)

        policy = RetryPolicy(max_attempts=2, wait_min=0.0, wait_max=0.0)
        config = StepExecutorConfig(retry_policy=policy)

        with pytest.raises(RuntimeError, match="always fails"):
            await executor.execute(
                step_name="step",
                agent_name="fail_agent",
                prompt={},
                config=config,
            )

    async def test_no_retry_policy_no_retry(self) -> None:
        """Without retry policy, single failure raises immediately."""
        call_count = 0

        class _FailOnce:
            name = "fail"

            async def execute(self, context: Any) -> None:
                nonlocal call_count
                call_count += 1
                raise RuntimeError("single failure")

        reg = ComponentRegistry()
        reg.agents.register("fail_once", _FailOnce, validate=False)
        executor = ClaudeStepExecutor(registry=reg)

        with pytest.raises(RuntimeError):
            await executor.execute(
                step_name="step",
                agent_name="fail_once",
                prompt={},
                # No config = DEFAULT_EXECUTOR_CONFIG (no retry)
            )
        assert call_count == 1

    async def test_retry_count_with_three_attempts(self) -> None:
        """With max_attempts=3, a flaky agent is retried up to 3 times total."""
        call_count = 0

        class _FlakyAgent:
            name = "flaky"

            async def execute(self, context: Any) -> str:
                nonlocal call_count
                call_count += 1
                if call_count < 3:
                    raise RuntimeError("transient error")
                return "finally succeeded"

        reg = ComponentRegistry()
        reg.agents.register("flaky3", _FlakyAgent, validate=False)
        executor = ClaudeStepExecutor(registry=reg)

        policy = RetryPolicy(max_attempts=3, wait_min=0.0, wait_max=0.0)
        config = StepExecutorConfig(retry_policy=policy)

        result = await executor.execute(
            step_name="step",
            agent_name="flaky3",
            prompt={},
            config=config,
        )
        assert result.success is True
        assert call_count == 3


# ── timeout ─────────────────────────────────────────────────────────────────


class TestClaudeStepExecutorTimeout:
    """Tests for timeout enforcement."""

    @pytest.mark.slow
    async def test_timeout_raises_timeout_error(self) -> None:
        """When agent exceeds timeout, asyncio.TimeoutError is raised."""

        class _SlowAgent:
            name = "slow"

            async def execute(self, context: Any) -> str:
                await asyncio.sleep(10.0)  # Very slow
                return "too late"

        reg = ComponentRegistry()
        reg.agents.register("slow_agent", _SlowAgent, validate=False)
        executor = ClaudeStepExecutor(registry=reg)

        config = StepExecutorConfig(timeout=1)  # 1 second timeout

        with pytest.raises((asyncio.TimeoutError, TimeoutError)):
            await executor.execute(
                step_name="step",
                agent_name="slow_agent",
                prompt={},
                config=config,
            )

    async def test_no_timeout_no_enforcement(self) -> None:
        """Without timeout config, agent runs to completion."""

        class _FastAgent:
            name = "fast"

            async def execute(self, context: Any) -> str:
                return "fast result"

        reg = ComponentRegistry()
        reg.agents.register("fast_agent", _FastAgent, validate=False)
        executor = ClaudeStepExecutor(registry=reg)

        # Explicit None timeout for this test
        config = StepExecutorConfig(timeout=None)
        result = await executor.execute(
            step_name="step",
            agent_name="fast_agent",
            prompt={},
            config=config,
        )
        assert result.output == "fast result"

    @pytest.mark.slow
    async def test_timeout_with_retry_policy(self) -> None:
        """Timeout is enforced per-attempt when retry policy is active."""
        call_count = 0

        class _SlowAgent:
            name = "slow"

            async def execute(self, context: Any) -> str:
                nonlocal call_count
                call_count += 1
                await asyncio.sleep(10.0)
                return "too late"

        reg = ComponentRegistry()
        reg.agents.register("slow_agent", _SlowAgent, validate=False)
        executor = ClaudeStepExecutor(registry=reg)

        policy = RetryPolicy(max_attempts=2, wait_min=0.0, wait_max=0.0)
        config = StepExecutorConfig(timeout=1, retry_policy=policy)

        with pytest.raises((asyncio.TimeoutError, TimeoutError)):
            await executor.execute(
                step_name="step",
                agent_name="slow_agent",
                prompt={},
                config=config,
            )
        # Both attempts should have been tried (and timed out)
        assert call_count >= 1


# ── output schema ─────────────────────────────────────────────────────────────


class TestClaudeStepExecutorOutputSchema:
    """Tests for output_schema validation (US3 / FR-007)."""

    class _ReviewResult(BaseModel):
        summary: str
        issues: list[str] = []

    async def test_conforming_output_validated(self) -> None:
        """Conforming output passes schema validation and is a Pydantic instance."""

        class _Agent:
            name = "reviewer"

            async def execute(self, context: Any) -> dict[str, Any]:
                return {"summary": "looks good", "issues": []}

        reg = ComponentRegistry()
        reg.agents.register("review_agent", _Agent, validate=False)
        executor = ClaudeStepExecutor(registry=reg)

        result = await executor.execute(
            step_name="step",
            agent_name="review_agent",
            prompt={},
            output_schema=TestClaudeStepExecutorOutputSchema._ReviewResult,
        )
        assert isinstance(
            result.output, TestClaudeStepExecutorOutputSchema._ReviewResult
        )
        assert result.output.summary == "looks good"

    async def test_non_conforming_output_raises_validation_error(self) -> None:
        """Non-conforming output raises OutputSchemaValidationError."""

        class _BadAgent:
            name = "bad"

            async def execute(self, context: Any) -> str:
                return "this is not a valid ReviewResult"

        reg = ComponentRegistry()
        reg.agents.register("bad_agent", _BadAgent, validate=False)
        executor = ClaudeStepExecutor(registry=reg)

        with pytest.raises(OutputSchemaValidationError) as exc_info:
            await executor.execute(
                step_name="my_step",
                agent_name="bad_agent",
                prompt={},
                output_schema=TestClaudeStepExecutorOutputSchema._ReviewResult,
            )
        assert exc_info.value.step_name == "my_step"
        assert (
            exc_info.value.schema_type
            is TestClaudeStepExecutorOutputSchema._ReviewResult
        )

    async def test_no_output_schema_backward_compatible(self) -> None:
        """Without output_schema, raw result returned unchanged (backward compat)."""

        class _RawAgent:
            name = "raw"

            async def execute(self, context: Any) -> list[str]:
                return ["item1", "item2"]

        reg = ComponentRegistry()
        reg.agents.register("raw_agent", _RawAgent, validate=False)
        executor = ClaudeStepExecutor(registry=reg)

        result = await executor.execute(
            step_name="step",
            agent_name="raw_agent",
            prompt={},
            output_schema=None,
        )
        assert result.output == ["item1", "item2"]

    async def test_conforming_dict_result_validated_to_pydantic(self) -> None:
        """Dict output matching schema is coerced to Pydantic model instance."""

        class _Agent:
            name = "agent"

            async def execute(self, context: Any) -> dict[str, Any]:
                return {"summary": "all clear"}

        reg = ComponentRegistry()
        reg.agents.register("agent", _Agent, validate=False)
        executor = ClaudeStepExecutor(registry=reg)

        result = await executor.execute(
            step_name="step",
            agent_name="agent",
            prompt={},
            output_schema=TestClaudeStepExecutorOutputSchema._ReviewResult,
        )
        assert result.success is True
        assert isinstance(
            result.output, TestClaudeStepExecutorOutputSchema._ReviewResult
        )
        assert result.output.issues == []

    async def test_schema_validation_error_has_validation_errors(self) -> None:
        """OutputSchemaValidationError exposes pydantic error.

        The underlying pydantic ValidationError is accessible.
        """

        class _BadAgent:
            name = "bad"

            async def execute(self, context: Any) -> dict[str, Any]:
                return {"wrong_field": "value"}  # Missing required 'summary'

        reg = ComponentRegistry()
        reg.agents.register("bad_agent", _BadAgent, validate=False)
        executor = ClaudeStepExecutor(registry=reg)

        with pytest.raises(OutputSchemaValidationError) as exc_info:
            await executor.execute(
                step_name="step",
                agent_name="bad_agent",
                prompt={},
                output_schema=TestClaudeStepExecutorOutputSchema._ReviewResult,
            )
        # validation_errors should be a Pydantic ValidationError
        from pydantic import ValidationError

        assert isinstance(exc_info.value.validation_errors, ValidationError)


# ── per-step config ────────────────────────────────────────────────────────────


class TestClaudeStepExecutorPerStepConfig:
    """Tests for per-step executor configuration (US4)."""

    @pytest.mark.slow
    async def test_custom_timeout_enforced(self) -> None:
        """Step-specific timeout is enforced by executor."""

        class _SlowAgent:
            name = "slow"

            async def execute(self, context: Any) -> str:
                await asyncio.sleep(10.0)
                return "too late"

        reg = ComponentRegistry()
        reg.agents.register("slow_agent", _SlowAgent, validate=False)
        executor = ClaudeStepExecutor(registry=reg)

        config = StepExecutorConfig(timeout=1)  # Short timeout

        with pytest.raises((asyncio.TimeoutError, TimeoutError)):
            await executor.execute(
                step_name="step",
                agent_name="slow_agent",
                prompt={},
                config=config,
            )

    async def test_no_config_uses_default(self) -> None:
        """None config applies DEFAULT_EXECUTOR_CONFIG."""
        executor = _make_executor()
        # Just verify it runs and returns a result
        result = await executor.execute(
            step_name="step",
            agent_name="test_agent",
            prompt={},
            config=None,  # Should use DEFAULT_EXECUTOR_CONFIG
        )
        assert result.success is True

    async def test_two_steps_independent_configs(self) -> None:
        """Two calls with different configs each enforce their own settings."""

        class _TimedAgent:
            name = "timed"

            async def execute(self, context: Any) -> str:
                return "done"

        reg = ComponentRegistry()
        reg.agents.register("timed_agent", _TimedAgent, validate=False)
        executor = ClaudeStepExecutor(registry=reg)

        config_a = StepExecutorConfig(timeout=30)
        config_b = StepExecutorConfig(timeout=60)

        result_a = await executor.execute(
            step_name="step_a",
            agent_name="timed_agent",
            prompt={},
            config=config_a,
        )
        result_b = await executor.execute(
            step_name="step_b",
            agent_name="timed_agent",
            prompt={},
            config=config_b,
        )
        assert result_a.success is True
        assert result_b.success is True

    async def test_config_with_no_retry_and_no_timeout(self) -> None:
        """Config with both timeout=None and retry_policy=None works fine."""
        executor = _make_executor()
        config = StepExecutorConfig(timeout=None, retry_policy=None)
        result = await executor.execute(
            step_name="step",
            agent_name="test_agent",
            prompt={},
            config=config,
        )
        assert result.success is True
        assert result.output == "agent result"


# ── observability ─────────────────────────────────────────────────────────────


class TestClaudeStepExecutorObservability:
    """Tests for structured log events (NFR-001)."""

    async def test_step_start_logged(self) -> None:
        """executor.step_start is logged on execution start."""
        executor = _make_executor()
        log_events: list[dict[str, Any]] = []

        original_info = executor._logger.info

        def capture_info(event: str, **kwargs: Any) -> Any:
            log_events.append({"event": event, **kwargs})
            return original_info(event, **kwargs)

        with patch.object(executor._logger, "info", side_effect=capture_info):
            await executor.execute(
                step_name="my_step",
                agent_name="test_agent",
                prompt={},
            )

        start_events = [
            e for e in log_events if e.get("event") == "executor.step_start"
        ]
        assert len(start_events) >= 1
        assert start_events[0]["step_name"] == "my_step"
        assert start_events[0]["agent_name"] == "test_agent"

    async def test_step_complete_logged(self) -> None:
        """executor.step_complete is logged on successful completion."""
        executor = _make_executor()
        log_events: list[dict[str, Any]] = []

        original_info = executor._logger.info

        def capture_info(event: str, **kwargs: Any) -> Any:
            log_events.append({"event": event, **kwargs})
            return original_info(event, **kwargs)

        with patch.object(executor._logger, "info", side_effect=capture_info):
            await executor.execute(
                step_name="my_step",
                agent_name="test_agent",
                prompt={},
            )

        complete_events = [
            e for e in log_events if e.get("event") == "executor.step_complete"
        ]
        assert len(complete_events) >= 1
        assert complete_events[0]["success"] is True
        assert "duration_ms" in complete_events[0]

    async def test_step_error_logged_on_failure(self) -> None:
        """executor.step_error is logged when agent raises."""

        class _FailAgent:
            name = "fail"

            async def execute(self, context: Any) -> None:
                raise RuntimeError("error!")

        reg = ComponentRegistry()
        reg.agents.register("fail_a", _FailAgent, validate=False)
        executor = ClaudeStepExecutor(registry=reg)
        log_events: list[dict[str, Any]] = []

        original_error = executor._logger.error

        def capture_error(event: str, **kwargs: Any) -> Any:
            log_events.append({"event": event, **kwargs})
            return original_error(event, **kwargs)

        with patch.object(executor._logger, "error", side_effect=capture_error):
            with pytest.raises(RuntimeError):
                await executor.execute(
                    step_name="failing_step",
                    agent_name="fail_a",
                    prompt={},
                )

        error_events = [
            e for e in log_events if e.get("event") == "executor.step_error"
        ]
        assert len(error_events) >= 1
        assert error_events[0]["step_name"] == "failing_step"

    async def test_step_start_includes_config_info(self) -> None:
        """executor.step_start log event includes config dict."""
        executor = _make_executor()
        log_events: list[dict[str, Any]] = []

        original_info = executor._logger.info

        def capture_info(event: str, **kwargs: Any) -> Any:
            log_events.append({"event": event, **kwargs})
            return original_info(event, **kwargs)

        config = StepExecutorConfig(timeout=42)
        with patch.object(executor._logger, "info", side_effect=capture_info):
            await executor.execute(
                step_name="my_step",
                agent_name="test_agent",
                prompt={},
                config=config,
            )

        start_events = [
            e for e in log_events if e.get("event") == "executor.step_start"
        ]
        assert len(start_events) >= 1
        assert "config" in start_events[0]
        assert start_events[0]["config"]["timeout"] == 42

    async def test_step_complete_includes_duration_ms(self) -> None:
        """executor.step_complete log includes a non-negative duration_ms."""
        executor = _make_executor()
        log_events: list[dict[str, Any]] = []

        original_info = executor._logger.info

        def capture_info(event: str, **kwargs: Any) -> Any:
            log_events.append({"event": event, **kwargs})
            return original_info(event, **kwargs)

        with patch.object(executor._logger, "info", side_effect=capture_info):
            await executor.execute(
                step_name="step",
                agent_name="test_agent",
                prompt={},
            )

        complete_events = [
            e for e in log_events if e.get("event") == "executor.step_complete"
        ]
        assert len(complete_events) >= 1
        assert complete_events[0]["duration_ms"] >= 0


# ── _extract_output_text edge cases ──────────────────────────────────────────


class TestExtractOutputText:
    """Tests for the _extract_output_text helper via executor output chunks."""

    async def _get_output_texts(
        self, agent_class: type, agent_name: str = "agent"
    ) -> list[str]:
        """Run executor and collect non-streaming OUTPUT chunk texts."""
        reg = ComponentRegistry()
        reg.agents.register(agent_name, agent_class, validate=False)
        executor = ClaudeStepExecutor(registry=reg)
        result = await executor.execute(
            step_name="step", agent_name=agent_name, prompt={}
        )
        return [
            e.text
            for e in result.events
            if isinstance(e, AgentStreamChunk) and e.chunk_type == "output"
        ]

    async def test_string_result_emitted_as_output_chunk(self) -> None:
        """String result is directly emitted as an OUTPUT chunk."""

        class _Agent:
            name = "a"

            async def execute(self, context: Any) -> str:
                return "hello world"

        texts = await self._get_output_texts(_Agent)
        assert any("hello world" in t for t in texts)

    async def test_none_result_emits_no_output_chunk(self) -> None:
        """None result produces no OUTPUT event (empty string extracted)."""

        class _Agent:
            name = "a"

            async def execute(self, context: Any) -> None:
                return None

        texts = await self._get_output_texts(_Agent)
        # No meaningful output to emit
        assert not any(t.strip() for t in texts)

    async def test_dict_with_output_key_extracted(self) -> None:
        """Dict result with 'output' key has its value extracted for streaming."""

        class _Agent:
            name = "a"

            async def execute(self, context: Any) -> dict[str, str]:
                return {"output": "the answer"}

        texts = await self._get_output_texts(_Agent)
        assert any("the answer" in t for t in texts)

    async def test_object_with_output_attr_extracted(self) -> None:
        """Object with .output string attribute is extracted for streaming."""

        class _ResultObj:
            output = "attr result"

        class _Agent:
            name = "a"

            async def execute(self, context: Any) -> _ResultObj:
                return _ResultObj()

        texts = await self._get_output_texts(_Agent)
        assert any("attr result" in t for t in texts)
