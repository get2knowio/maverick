"""Tests for UsageMetadata and ExecutorResult frozen dataclasses."""

from __future__ import annotations

import pytest

from maverick.executor.result import ExecutorResult, UsageMetadata


class TestUsageMetadata:
    """Tests for UsageMetadata frozen dataclass."""

    def test_default_values(self) -> None:
        """UsageMetadata defaults to zero tokens and no cost."""
        usage = UsageMetadata()
        assert usage.input_tokens == 0
        assert usage.output_tokens == 0
        assert usage.cache_read_tokens == 0
        assert usage.cache_write_tokens == 0
        assert usage.total_cost_usd is None

    def test_custom_values(self) -> None:
        """UsageMetadata accepts custom token counts."""
        usage = UsageMetadata(
            input_tokens=100,
            output_tokens=200,
            cache_read_tokens=50,
            cache_write_tokens=25,
            total_cost_usd=0.003,
        )
        assert usage.input_tokens == 100
        assert usage.output_tokens == 200
        assert usage.cache_read_tokens == 50
        assert usage.cache_write_tokens == 25
        assert usage.total_cost_usd == pytest.approx(0.003)

    def test_to_dict_roundtrip(self) -> None:
        """UsageMetadata.to_dict() produces JSON-compatible dict."""
        usage = UsageMetadata(input_tokens=100, output_tokens=50)
        d = usage.to_dict()
        assert d["input_tokens"] == 100
        assert d["output_tokens"] == 50
        assert d["cache_read_tokens"] == 0
        assert d["cache_write_tokens"] == 0
        assert d["total_cost_usd"] is None

    def test_to_dict_with_cost(self) -> None:
        """UsageMetadata.to_dict() includes cost when set."""
        usage = UsageMetadata(total_cost_usd=0.01)
        d = usage.to_dict()
        assert d["total_cost_usd"] == pytest.approx(0.01)

    def test_frozen_immutable(self) -> None:
        """UsageMetadata is frozen (cannot be mutated)."""
        usage = UsageMetadata()
        with pytest.raises((AttributeError, TypeError)):
            usage.input_tokens = 100  # type: ignore[misc]


class TestExecutorResult:
    """Tests for ExecutorResult frozen dataclass."""

    def test_construction_with_all_fields(self) -> None:
        """ExecutorResult can be constructed with all fields."""
        usage = UsageMetadata(input_tokens=10)
        result = ExecutorResult(
            output="some output",
            success=True,
            usage=usage,
            events=(),
        )
        assert result.output == "some output"
        assert result.success is True
        assert result.usage == usage
        assert result.events == ()

    def test_construction_no_usage(self) -> None:
        """ExecutorResult supports None usage."""
        result = ExecutorResult(
            output={"key": "value"},
            success=True,
            usage=None,
            events=(),
        )
        assert result.usage is None
        assert result.output == {"key": "value"}

    def test_success_false(self) -> None:
        """ExecutorResult supports success=False."""
        result = ExecutorResult(
            output=None,
            success=False,
            usage=None,
            events=(),
        )
        assert result.success is False

    def test_events_is_tuple(self) -> None:
        """ExecutorResult.events is a tuple (frozen-dataclass safe)."""
        from maverick.events import AgentStreamChunk

        chunk = AgentStreamChunk(
            step_name="test", agent_name="agent", text="hi", chunk_type="output"
        )
        result = ExecutorResult(
            output="done",
            success=True,
            usage=None,
            events=(chunk,),
        )
        assert isinstance(result.events, tuple)
        assert len(result.events) == 1
        assert result.events[0] is chunk

    def test_to_dict_basic(self) -> None:
        """ExecutorResult.to_dict() produces JSON-compatible dict."""
        result = ExecutorResult(
            output="hello",
            success=True,
            usage=None,
            events=(),
        )
        d = result.to_dict()
        assert d["output"] == "hello"
        assert d["success"] is True
        assert d["usage"] is None
        assert d["events"] == []

    def test_to_dict_with_usage(self) -> None:
        """ExecutorResult.to_dict() serializes nested UsageMetadata."""
        usage = UsageMetadata(input_tokens=5, output_tokens=10)
        result = ExecutorResult(output="x", success=True, usage=usage, events=())
        d = result.to_dict()
        assert d["usage"]["input_tokens"] == 5
        assert d["usage"]["output_tokens"] == 10

    def test_frozen_immutable(self) -> None:
        """ExecutorResult is frozen (cannot be mutated)."""
        result = ExecutorResult(output="x", success=True, usage=None, events=())
        with pytest.raises((AttributeError, TypeError)):
            result.output = "y"  # type: ignore[misc]
