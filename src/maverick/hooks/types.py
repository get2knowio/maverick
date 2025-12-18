from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Result of a safety validation.

    Attributes:
        allowed: Whether the operation is permitted.
        reason: Human-readable explanation of the decision.
        tool_name: Name of the tool that was validated.
        blocked_pattern: Pattern that triggered the block (for debugging).
    """

    allowed: bool
    reason: str | None = None
    tool_name: str | None = None
    blocked_pattern: str | None = None


@dataclass(frozen=True, slots=True)
class ToolExecutionLog:
    """Structured log entry for tool execution.

    Attributes:
        tool_name: Name of the tool executed.
        tool_use_id: SDK tool use identifier.
        timestamp: When execution started.
        duration_ms: Execution time in milliseconds.
        success: Whether execution succeeded.
        sanitized_inputs: Inputs with secrets redacted.
        output_summary: Truncated output.
        error_summary: Error message if failed.
    """

    tool_name: str
    tool_use_id: str | None
    timestamp: datetime
    duration_ms: float
    success: bool
    sanitized_inputs: dict[str, Any]
    output_summary: str | None
    error_summary: str | None = None


@dataclass(frozen=True, slots=True)
class ToolMetricEntry:
    """Single metric entry for rolling window.

    Attributes:
        tool_name: Name of the tool executed.
        timestamp: Unix timestamp of execution.
        duration_ms: Execution time in milliseconds.
        success: Whether execution succeeded.
    """

    tool_name: str
    timestamp: float
    duration_ms: float
    success: bool


@dataclass(frozen=True, slots=True)
class ToolMetrics:
    """Aggregated metrics for a tool type.

    Attributes:
        tool_name: Tool name or None for all tools.
        call_count: Total number of executions.
        success_count: Number of successful executions.
        failure_count: Number of failed executions.
        avg_duration_ms: Average execution time.
        p50_duration_ms: Median execution time.
        p95_duration_ms: 95th percentile execution time.
        p99_duration_ms: 99th percentile execution time.
    """

    tool_name: str | None
    call_count: int
    success_count: int
    failure_count: int
    avg_duration_ms: float
    p50_duration_ms: float
    p95_duration_ms: float
    p99_duration_ms: float

    @property
    def success_rate(self) -> float:
        """Success rate as fraction 0.0-1.0."""
        return self.success_count / self.call_count if self.call_count > 0 else 0.0

    @property
    def failure_rate(self) -> float:
        """Failure rate as fraction 0.0-1.0."""
        return self.failure_count / self.call_count if self.call_count > 0 else 0.0
