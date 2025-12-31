"""Widget-level performance metrics for TUI components.

This module provides opt-in performance tracking for Textual widgets:
- Render time tracking for widget updates
- Message throughput tracking (messages/second)
- Rolling window statistics similar to hooks/metrics.py
- Zero overhead when disabled

Example:
    # In widget code
    from maverick.tui.metrics import widget_metrics

    if widget_metrics.enabled:
        start = time.perf_counter()
    # ... render logic ...
    if widget_metrics.enabled:
        elapsed = (time.perf_counter() - start) * 1000
        widget_metrics.record_render("AgentOutput", elapsed)

    # Get stats
    stats = widget_metrics.get_stats("AgentOutput")
    print(f"Avg render: {stats.avg_render_ms:.2f}ms")
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass
from time import time


@dataclass(frozen=True, slots=True)
class RenderMetricEntry:
    """Single render metric entry for rolling window.

    Attributes:
        widget_name: Name of the widget that rendered.
        timestamp: Unix timestamp of render.
        duration_ms: Render time in milliseconds.
    """

    widget_name: str
    timestamp: float
    duration_ms: float


@dataclass(frozen=True, slots=True)
class MessageMetricEntry:
    """Single message metric entry for rolling window.

    Attributes:
        widget_name: Name of the widget that received a message.
        timestamp: Unix timestamp of message.
    """

    widget_name: str
    timestamp: float


@dataclass(frozen=True, slots=True)
class WidgetStats:
    """Aggregated statistics for a widget.

    Attributes:
        widget_name: Widget name or None for all widgets.
        render_count: Total number of renders tracked.
        message_count: Total number of messages tracked.
        avg_render_ms: Average render time.
        p50_render_ms: Median render time.
        p95_render_ms: 95th percentile render time.
        p99_render_ms: 99th percentile render time.
        messages_per_second: Message throughput rate.
    """

    widget_name: str | None
    render_count: int
    message_count: int
    avg_render_ms: float
    p50_render_ms: float
    p95_render_ms: float
    p99_render_ms: float
    messages_per_second: float


class WidgetMetrics:
    """Thread-safe widget performance metrics collector.

    Tracks render times and message throughput for TUI widgets using a
    rolling window. Can be enabled/disabled without code changes.

    The singleton instance `widget_metrics` should be used globally.

    Attributes:
        enabled: Whether metrics collection is active.
        max_entries: Maximum entries in rolling window (per metric type).
    """

    def __init__(self, enabled: bool = False, max_entries: int = 10000) -> None:
        """Initialize the metrics collector.

        Args:
            enabled: Whether to collect metrics.
            max_entries: Maximum entries in rolling window.
        """
        self._enabled = enabled
        self._max_entries = max_entries
        self._lock = threading.Lock()
        self._render_entries: deque[RenderMetricEntry] = deque(maxlen=max_entries)
        self._message_entries: deque[MessageMetricEntry] = deque(maxlen=max_entries)

    @property
    def enabled(self) -> bool:
        """Check if metrics collection is enabled."""
        return self._enabled

    def enable(self) -> None:
        """Enable metrics collection."""
        self._enabled = True

    def disable(self) -> None:
        """Disable metrics collection."""
        self._enabled = False

    def record_render(self, widget_name: str, duration_ms: float) -> None:
        """Record a widget render event.

        Args:
            widget_name: Name of the widget (e.g., "AgentOutput", "WorkflowProgress").
            duration_ms: Render duration in milliseconds.
        """
        if not self._enabled:
            return

        entry = RenderMetricEntry(
            widget_name=widget_name,
            timestamp=time(),
            duration_ms=duration_ms,
        )

        with self._lock:
            self._render_entries.append(entry)

    def record_message(self, widget_name: str) -> None:
        """Record a message received by a widget.

        Used to track message throughput (messages/second).

        Args:
            widget_name: Name of the widget receiving the message.
        """
        if not self._enabled:
            return

        entry = MessageMetricEntry(
            widget_name=widget_name,
            timestamp=time(),
        )

        with self._lock:
            self._message_entries.append(entry)

    def get_stats(self, widget_name: str | None = None) -> WidgetStats:
        """Get aggregated statistics for a widget.

        Args:
            widget_name: Filter by widget name. None for all widgets.

        Returns:
            Aggregated statistics with render times and message throughput.
        """
        with self._lock:
            # Filter render entries
            if widget_name is None:
                render_entries = list(self._render_entries)
                message_entries = list(self._message_entries)
            else:
                render_entries = [
                    e for e in self._render_entries if e.widget_name == widget_name
                ]
                message_entries = [
                    e for e in self._message_entries if e.widget_name == widget_name
                ]

            return self._aggregate(widget_name, render_entries, message_entries)

    def clear(self) -> None:
        """Clear all collected metrics."""
        with self._lock:
            self._render_entries.clear()
            self._message_entries.clear()

    def _aggregate(
        self,
        widget_name: str | None,
        render_entries: list[RenderMetricEntry],
        message_entries: list[MessageMetricEntry],
    ) -> WidgetStats:
        """Aggregate metric entries into summary statistics.

        Args:
            widget_name: Widget name for the stats.
            render_entries: List of render entries to aggregate.
            message_entries: List of message entries to aggregate.

        Returns:
            Aggregated statistics.
        """
        # Render time statistics
        render_count = len(render_entries)
        if render_count > 0:
            durations = sorted(e.duration_ms for e in render_entries)
            avg_render = sum(durations) / len(durations)
            p50_render = self._percentile(durations, 50)
            p95_render = self._percentile(durations, 95)
            p99_render = self._percentile(durations, 99)
        else:
            avg_render = 0.0
            p50_render = 0.0
            p95_render = 0.0
            p99_render = 0.0

        # Message throughput
        message_count = len(message_entries)
        messages_per_second = 0.0
        if message_count > 1:
            # Calculate messages/second from time range
            timestamps = [e.timestamp for e in message_entries]
            time_span = max(timestamps) - min(timestamps)
            if time_span > 0:
                messages_per_second = message_count / time_span

        return WidgetStats(
            widget_name=widget_name,
            render_count=render_count,
            message_count=message_count,
            avg_render_ms=avg_render,
            p50_render_ms=p50_render,
            p95_render_ms=p95_render,
            p99_render_ms=p99_render,
            messages_per_second=messages_per_second,
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


# Global singleton instance
widget_metrics = WidgetMetrics(enabled=False)


def configure_metrics(enabled: bool, max_entries: int = 10000) -> None:
    """Configure the global widget metrics collector.

    Args:
        enabled: Whether to enable metrics collection.
        max_entries: Maximum entries in rolling window.
    """
    global widget_metrics
    widget_metrics = WidgetMetrics(enabled=enabled, max_entries=max_entries)
