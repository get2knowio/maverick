"""Unit tests for AgentUsage and AgentResult dataclasses."""

from __future__ import annotations

import pytest

from maverick.agents.result import AgentResult, AgentUsage
from maverick.exceptions import AgentError


class TestAgentUsage:
    """Test suite for AgentUsage dataclass."""

    def test_creation_with_valid_values(self) -> None:
        """Test creating AgentUsage with valid values."""
        usage = AgentUsage(
            input_tokens=100,
            output_tokens=200,
            total_cost_usd=0.003,
            duration_ms=1500,
        )

        assert usage.input_tokens == 100
        assert usage.output_tokens == 200
        assert usage.total_cost_usd == 0.003
        assert usage.duration_ms == 1500

    def test_creation_with_none_cost(self) -> None:
        """Test creating AgentUsage with None cost."""
        usage = AgentUsage(
            input_tokens=100,
            output_tokens=200,
            total_cost_usd=None,
            duration_ms=1500,
        )

        assert usage.input_tokens == 100
        assert usage.output_tokens == 200
        assert usage.total_cost_usd is None
        assert usage.duration_ms == 1500

    def test_frozen_immutable(self) -> None:
        """Test that AgentUsage is frozen (immutable)."""
        usage = AgentUsage(
            input_tokens=100,
            output_tokens=200,
            total_cost_usd=0.003,
            duration_ms=1500,
        )

        with pytest.raises(AttributeError, match="cannot assign to field"):
            usage.input_tokens = 999  # type: ignore[misc]

        with pytest.raises(AttributeError, match="cannot assign to field"):
            usage.output_tokens = 999  # type: ignore[misc]

        with pytest.raises(AttributeError, match="cannot assign to field"):
            usage.total_cost_usd = 0.999  # type: ignore[misc]

        with pytest.raises(AttributeError, match="cannot assign to field"):
            usage.duration_ms = 999  # type: ignore[misc]

    def test_slots_no_dict(self) -> None:
        """Test that AgentUsage uses slots (no __dict__)."""
        usage = AgentUsage(
            input_tokens=100,
            output_tokens=200,
            total_cost_usd=0.003,
            duration_ms=1500,
        )

        assert not hasattr(usage, "__dict__")

    def test_total_tokens_computed_property(self) -> None:
        """Test total_tokens computed property."""
        usage = AgentUsage(
            input_tokens=100,
            output_tokens=200,
            total_cost_usd=0.003,
            duration_ms=1500,
        )

        assert usage.total_tokens == 300

    def test_total_tokens_with_zero_values(self) -> None:
        """Test total_tokens with zero values."""
        usage = AgentUsage(
            input_tokens=0,
            output_tokens=0,
            total_cost_usd=0.0,
            duration_ms=0,
        )

        assert usage.total_tokens == 0

    def test_validation_input_tokens_negative(self) -> None:
        """Test validation fails when input_tokens is negative."""
        with pytest.raises(ValueError, match="input_tokens must be non-negative"):
            AgentUsage(
                input_tokens=-1,
                output_tokens=200,
                total_cost_usd=0.003,
                duration_ms=1500,
            )

    def test_validation_output_tokens_negative(self) -> None:
        """Test validation fails when output_tokens is negative."""
        with pytest.raises(ValueError, match="output_tokens must be non-negative"):
            AgentUsage(
                input_tokens=100,
                output_tokens=-1,
                total_cost_usd=0.003,
                duration_ms=1500,
            )

    def test_validation_duration_ms_negative(self) -> None:
        """Test validation fails when duration_ms is negative."""
        with pytest.raises(ValueError, match="duration_ms must be non-negative"):
            AgentUsage(
                input_tokens=100,
                output_tokens=200,
                total_cost_usd=0.003,
                duration_ms=-1,
            )

    def test_validation_total_cost_usd_negative(self) -> None:
        """Test validation fails when total_cost_usd is negative."""
        with pytest.raises(ValueError, match="total_cost_usd must be non-negative"):
            AgentUsage(
                input_tokens=100,
                output_tokens=200,
                total_cost_usd=-0.001,
                duration_ms=1500,
            )

    def test_validation_total_cost_usd_none_is_valid(self) -> None:
        """Test that None total_cost_usd is valid."""
        usage = AgentUsage(
            input_tokens=100,
            output_tokens=200,
            total_cost_usd=None,
            duration_ms=1500,
        )

        assert usage.total_cost_usd is None

    def test_validation_zero_values_are_valid(self) -> None:
        """Test that zero values are valid."""
        usage = AgentUsage(
            input_tokens=0,
            output_tokens=0,
            total_cost_usd=0.0,
            duration_ms=0,
        )

        assert usage.input_tokens == 0
        assert usage.output_tokens == 0
        assert usage.total_cost_usd == 0.0
        assert usage.duration_ms == 0


class TestAgentResult:
    """Test suite for AgentResult dataclass."""

    def test_creation_with_valid_values(self) -> None:
        """Test creating AgentResult with valid values."""
        usage = AgentUsage(
            input_tokens=100,
            output_tokens=200,
            total_cost_usd=0.003,
            duration_ms=1500,
        )
        error = AgentError("Test error", agent_name="test_agent")

        result = AgentResult(
            success=False,
            output="Test output",
            usage=usage,
            metadata={"session_id": "abc123"},
            errors=[error],
        )

        assert result.success is False
        assert result.output == "Test output"
        assert result.usage == usage
        assert result.metadata == {"session_id": "abc123"}
        assert len(result.errors) == 1
        assert result.errors[0] == error

    def test_frozen_immutable(self) -> None:
        """Test that AgentResult is frozen (immutable)."""
        usage = AgentUsage(
            input_tokens=100,
            output_tokens=200,
            total_cost_usd=0.003,
            duration_ms=1500,
        )
        error = AgentError("Test error")

        result = AgentResult(
            success=False,
            output="Test output",
            usage=usage,
            metadata={"key": "value"},
            errors=[error],
        )

        with pytest.raises(AttributeError, match="cannot assign to field"):
            result.success = True  # type: ignore[misc]

        with pytest.raises(AttributeError, match="cannot assign to field"):
            result.output = "New output"  # type: ignore[misc]

        with pytest.raises(AttributeError, match="cannot assign to field"):
            result.usage = usage  # type: ignore[misc]

    def test_slots_no_dict(self) -> None:
        """Test that AgentResult uses slots (no __dict__)."""
        usage = AgentUsage(
            input_tokens=100,
            output_tokens=200,
            total_cost_usd=0.003,
            duration_ms=1500,
        )
        error = AgentError("Test error")

        result = AgentResult(
            success=False,
            output="Test output",
            usage=usage,
            errors=[error],
        )

        assert not hasattr(result, "__dict__")

    def test_success_result_factory_method(self) -> None:
        """Test success_result factory method."""
        usage = AgentUsage(
            input_tokens=100,
            output_tokens=200,
            total_cost_usd=0.003,
            duration_ms=1500,
        )

        result = AgentResult.success_result(
            output="Analysis complete",
            usage=usage,
            metadata={"session_id": "xyz789"},
        )

        assert result.success is True
        assert result.output == "Analysis complete"
        assert result.usage == usage
        assert result.metadata == {"session_id": "xyz789"}
        assert result.errors == []

    def test_success_result_factory_method_without_metadata(self) -> None:
        """Test success_result factory method without metadata."""
        usage = AgentUsage(
            input_tokens=100,
            output_tokens=200,
            total_cost_usd=0.003,
            duration_ms=1500,
        )

        result = AgentResult.success_result(
            output="Analysis complete",
            usage=usage,
        )

        assert result.success is True
        assert result.output == "Analysis complete"
        assert result.usage == usage
        assert result.metadata == {}
        assert result.errors == []

    def test_failure_result_factory_method(self) -> None:
        """Test failure_result factory method."""
        usage = AgentUsage(
            input_tokens=100,
            output_tokens=200,
            total_cost_usd=0.003,
            duration_ms=1500,
        )
        error = AgentError("Something went wrong", agent_name="test_agent")

        result = AgentResult.failure_result(
            errors=[error],
            usage=usage,
            output="Partial output",
            metadata={"attempt": 1},
        )

        assert result.success is False
        assert result.output == "Partial output"
        assert result.usage == usage
        assert result.metadata == {"attempt": 1}
        assert len(result.errors) == 1
        assert result.errors[0] == error

    def test_failure_result_factory_method_minimal(self) -> None:
        """Test failure_result factory method with minimal arguments."""
        usage = AgentUsage(
            input_tokens=100,
            output_tokens=200,
            total_cost_usd=0.003,
            duration_ms=1500,
        )
        error = AgentError("Something went wrong")

        result = AgentResult.failure_result(
            errors=[error],
            usage=usage,
        )

        assert result.success is False
        assert result.output == ""
        assert result.usage == usage
        assert result.metadata == {}
        assert len(result.errors) == 1
        assert result.errors[0] == error

    def test_failure_result_requires_at_least_one_error(self) -> None:
        """Test failure_result raises ValueError when errors list is empty."""
        usage = AgentUsage(
            input_tokens=100,
            output_tokens=200,
            total_cost_usd=0.003,
            duration_ms=1500,
        )

        error_msg = "Failed results must have at least one error"
        with pytest.raises(ValueError, match=error_msg):
            AgentResult.failure_result(
                errors=[],
                usage=usage,
            )

    def test_post_init_validation_failure_without_errors(self) -> None:
        """Test __post_init__ validation fails when success=False with no errors."""
        usage = AgentUsage(
            input_tokens=100,
            output_tokens=200,
            total_cost_usd=0.003,
            duration_ms=1500,
        )

        error_msg = "Failed results must have at least one error"
        with pytest.raises(ValueError, match=error_msg):
            AgentResult(
                success=False,
                output="Failed output",
                usage=usage,
                metadata={},
                errors=[],
            )

    def test_post_init_validation_success_with_errors_is_allowed(self) -> None:
        """Test that success=True with errors is allowed (warnings case)."""
        usage = AgentUsage(
            input_tokens=100,
            output_tokens=200,
            total_cost_usd=0.003,
            duration_ms=1500,
        )
        error = AgentError("Warning: something minor")

        result = AgentResult(
            success=True,
            output="Success with warnings",
            usage=usage,
            metadata={},
            errors=[error],
        )

        assert result.success is True
        assert len(result.errors) == 1

    def test_default_metadata_and_errors(self) -> None:
        """Test that metadata and errors default to empty dict and list."""
        usage = AgentUsage(
            input_tokens=100,
            output_tokens=200,
            total_cost_usd=0.003,
            duration_ms=1500,
        )

        result = AgentResult(
            success=True,
            output="Test output",
            usage=usage,
        )

        assert result.metadata == {}
        assert result.errors == []

    def test_multiple_errors(self) -> None:
        """Test AgentResult with multiple errors."""
        usage = AgentUsage(
            input_tokens=100,
            output_tokens=200,
            total_cost_usd=0.003,
            duration_ms=1500,
        )
        error1 = AgentError("First error")
        error2 = AgentError("Second error")
        error3 = AgentError("Third error")

        result = AgentResult.failure_result(
            errors=[error1, error2, error3],
            usage=usage,
        )

        assert len(result.errors) == 3
        assert result.errors[0] == error1
        assert result.errors[1] == error2
        assert result.errors[2] == error3
