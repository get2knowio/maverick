from __future__ import annotations

from datetime import datetime

import pytest

from maverick.hooks.types import (
    ToolExecutionLog,
    ToolMetricEntry,
    ToolMetrics,
    ValidationResult,
)


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_creation_allowed(self) -> None:
        """Test creating an allowed result."""
        result = ValidationResult(allowed=True)
        assert result.allowed is True
        assert result.reason is None
        assert result.tool_name is None
        assert result.blocked_pattern is None

    def test_creation_blocked(self) -> None:
        """Test creating a blocked result with all fields."""
        result = ValidationResult(
            allowed=False,
            reason="Dangerous command detected",
            tool_name="Bash",
            blocked_pattern="rm -rf",
        )
        assert result.allowed is False
        assert result.reason == "Dangerous command detected"
        assert result.tool_name == "Bash"
        assert result.blocked_pattern == "rm -rf"

    def test_immutability(self) -> None:
        """Test that ValidationResult is immutable (frozen)."""
        result = ValidationResult(allowed=True)
        with pytest.raises(AttributeError):
            result.allowed = False  # type: ignore[misc]


class TestToolExecutionLog:
    """Tests for ToolExecutionLog dataclass."""

    def test_creation(self) -> None:
        """Test creating a log entry."""
        now = datetime.now()
        log = ToolExecutionLog(
            tool_name="Bash",
            tool_use_id="123",
            timestamp=now,
            duration_ms=45.5,
            success=True,
            sanitized_inputs={"command": "ls -la"},
            output_summary="total 16...",
        )
        assert log.tool_name == "Bash"
        assert log.tool_use_id == "123"
        assert log.timestamp == now
        assert log.duration_ms == 45.5
        assert log.success is True
        assert log.sanitized_inputs == {"command": "ls -la"}
        assert log.output_summary == "total 16..."
        assert log.error_summary is None

    def test_with_error(self) -> None:
        """Test creating a log entry with error."""
        log = ToolExecutionLog(
            tool_name="Bash",
            tool_use_id=None,
            timestamp=datetime.now(),
            duration_ms=10.0,
            success=False,
            sanitized_inputs={},
            output_summary=None,
            error_summary="Command failed",
        )
        assert log.success is False
        assert log.error_summary == "Command failed"


class TestToolMetricEntry:
    """Tests for ToolMetricEntry dataclass."""

    def test_creation(self) -> None:
        """Test creating a metric entry."""
        entry = ToolMetricEntry(
            tool_name="Bash",
            timestamp=1234567890.0,
            duration_ms=50.0,
            success=True,
        )
        assert entry.tool_name == "Bash"
        assert entry.timestamp == 1234567890.0
        assert entry.duration_ms == 50.0
        assert entry.success is True


class TestToolMetrics:
    """Tests for ToolMetrics dataclass."""

    def test_creation(self) -> None:
        """Test creating aggregated metrics."""
        metrics = ToolMetrics(
            tool_name="Bash",
            call_count=100,
            success_count=95,
            failure_count=5,
            avg_duration_ms=50.0,
            p50_duration_ms=45.0,
            p95_duration_ms=80.0,
            p99_duration_ms=120.0,
        )
        assert metrics.tool_name == "Bash"
        assert metrics.call_count == 100
        assert metrics.success_count == 95
        assert metrics.failure_count == 5

    def test_success_rate(self) -> None:
        """Test success rate calculation."""
        metrics = ToolMetrics(
            tool_name="Bash",
            call_count=100,
            success_count=95,
            failure_count=5,
            avg_duration_ms=50.0,
            p50_duration_ms=45.0,
            p95_duration_ms=80.0,
            p99_duration_ms=120.0,
        )
        assert metrics.success_rate == 0.95

    def test_failure_rate(self) -> None:
        """Test failure rate calculation."""
        metrics = ToolMetrics(
            tool_name="Bash",
            call_count=100,
            success_count=95,
            failure_count=5,
            avg_duration_ms=50.0,
            p50_duration_ms=45.0,
            p95_duration_ms=80.0,
            p99_duration_ms=120.0,
        )
        assert metrics.failure_rate == 0.05

    def test_zero_calls_rates(self) -> None:
        """Test rate calculations with zero calls."""
        metrics = ToolMetrics(
            tool_name=None,
            call_count=0,
            success_count=0,
            failure_count=0,
            avg_duration_ms=0.0,
            p50_duration_ms=0.0,
            p95_duration_ms=0.0,
            p99_duration_ms=0.0,
        )
        assert metrics.success_rate == 0.0
        assert metrics.failure_rate == 0.0
