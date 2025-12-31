from __future__ import annotations

import asyncio
from collections import deque
from time import time
from typing import Any

from maverick.hooks.config import MetricsConfig
from maverick.hooks.types import ToolMetricEntry, ToolMetrics
from maverick.logging import get_logger

logger = get_logger(__name__)


class MetricsCollector:
    """Async-safe metrics collector with rolling window.

    Uses asyncio.Lock for coroutine-safe access to metrics data.

    Attributes:
        config: Metrics configuration.
    """

    def __init__(self, config: MetricsConfig | None = None) -> None:
        """Initialize the metrics collector.

        Args:
            config: Optional metrics configuration.
        """
        self._config = config or MetricsConfig()
        self._lock = asyncio.Lock()
        self._entries: deque[ToolMetricEntry] = deque(maxlen=self._config.max_entries)

    @property
    def entry_count(self) -> int:
        """Current number of entries in rolling window."""
        return len(self._entries)

    async def record(self, entry: ToolMetricEntry) -> None:
        """Record a metric entry (async-safe).

        Args:
            entry: Metric data point to record.
        """
        async with self._lock:
            self._entries.append(entry)

    async def get_metrics(self, tool_name: str | None = None) -> ToolMetrics:
        """Get aggregated metrics (async-safe).

        Args:
            tool_name: Filter by tool name. None for all tools.

        Returns:
            Aggregated metrics with counts, rates, and timing statistics.
        """
        async with self._lock:
            # Filter entries
            if tool_name is None:
                filtered = list(self._entries)
            else:
                filtered = [e for e in self._entries if e.tool_name == tool_name]

            return self._aggregate(filtered, tool_name)

    async def clear(self) -> None:
        """Clear all collected metrics."""
        async with self._lock:
            self._entries.clear()

    def _aggregate(
        self, entries: list[ToolMetricEntry], tool_name: str | None
    ) -> ToolMetrics:
        """Aggregate metric entries into summary.

        Args:
            entries: List of entries to aggregate.
            tool_name: Tool name for the metrics.

        Returns:
            Aggregated metrics.
        """
        if not entries:
            return ToolMetrics(
                tool_name=tool_name,
                call_count=0,
                success_count=0,
                failure_count=0,
                avg_duration_ms=0.0,
                p50_duration_ms=0.0,
                p95_duration_ms=0.0,
                p99_duration_ms=0.0,
            )

        call_count = len(entries)
        success_count = sum(1 for e in entries if e.success)
        failure_count = call_count - success_count

        durations = sorted(e.duration_ms for e in entries)
        avg_duration = sum(durations) / len(durations)

        return ToolMetrics(
            tool_name=tool_name,
            call_count=call_count,
            success_count=success_count,
            failure_count=failure_count,
            avg_duration_ms=avg_duration,
            p50_duration_ms=self._percentile(durations, 50),
            p95_duration_ms=self._percentile(durations, 95),
            p99_duration_ms=self._percentile(durations, 99),
        )

    @staticmethod
    def _percentile(sorted_values: list[float], percentile: int) -> float:
        """Calculate percentile from sorted values.

        Args:
            sorted_values: Pre-sorted list of values.
            percentile: Percentile to calculate (0-100).

        Returns:
            Percentile value.
        """
        if not sorted_values:
            return 0.0

        n = len(sorted_values)
        k = (n - 1) * percentile / 100
        f = int(k)
        c = k - f

        if f + 1 < n:
            return sorted_values[f] * (1 - c) + sorted_values[f + 1] * c
        return sorted_values[f]


async def collect_metrics(
    input_data: dict[str, Any],
    tool_use_id: str | None,
    context: Any,
    *,
    collector: MetricsCollector,
    start_time: float | None = None,
) -> dict[str, Any]:
    """Collect execution metrics.

    Args:
        input_data: Contains tool_name, status, duration info.
        tool_use_id: SDK tool use identifier.
        context: Hook context from SDK.
        collector: MetricsCollector instance (required).
        start_time: Unix timestamp when execution started.

    Returns:
        Empty dict (no modification to flow).
    """
    try:
        tool_name = input_data.get("tool_name", "unknown")
        status = input_data.get("status", "unknown")
        success = status == "success"

        # Calculate duration
        now = time()
        duration_ms = 0.0
        if start_time:
            duration_ms = (now - start_time) * 1000

        # Create and record entry
        entry = ToolMetricEntry(
            tool_name=tool_name,
            timestamp=now,
            duration_ms=duration_ms,
            success=success,
        )

        await collector.record(entry)

        return {}

    except Exception as e:
        logger.error(f"Error collecting metrics: {e}")
        return {}  # Don't fail the hook
