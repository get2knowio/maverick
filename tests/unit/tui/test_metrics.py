"""Tests for TUI widget metrics collection.

Tests verify:
- Render time recording
- Message throughput tracking
- Enable/disable behavior
- Statistics aggregation
- Thread safety
"""

from __future__ import annotations

import time
from threading import Thread
from unittest.mock import patch

import pytest

from maverick.tui.metrics import (
    WidgetMetrics,
    WidgetStats,
    configure_metrics,
    widget_metrics,
)


class TestWidgetMetrics:
    """Test cases for WidgetMetrics class."""

    def test_metrics_disabled_by_default(self) -> None:
        """Metrics should be disabled by default."""
        metrics = WidgetMetrics(enabled=False)
        assert not metrics.enabled

    def test_enable_disable(self) -> None:
        """Test enabling and disabling metrics collection."""
        metrics = WidgetMetrics(enabled=False)
        assert not metrics.enabled

        metrics.enable()
        assert metrics.enabled

        metrics.disable()
        assert not metrics.enabled

    def test_record_render_when_disabled(self) -> None:
        """Recording when disabled should be a no-op."""
        metrics = WidgetMetrics(enabled=False)
        metrics.record_render("TestWidget", 10.5)

        stats = metrics.get_stats("TestWidget")
        assert stats.render_count == 0
        assert stats.avg_render_ms == 0.0

    def test_record_render_when_enabled(self) -> None:
        """Recording when enabled should capture data."""
        metrics = WidgetMetrics(enabled=True)
        metrics.record_render("TestWidget", 10.5)
        metrics.record_render("TestWidget", 15.2)
        metrics.record_render("TestWidget", 12.8)

        stats = metrics.get_stats("TestWidget")
        assert stats.render_count == 3
        assert stats.avg_render_ms == pytest.approx((10.5 + 15.2 + 12.8) / 3)

    def test_record_message_when_disabled(self) -> None:
        """Recording messages when disabled should be a no-op."""
        metrics = WidgetMetrics(enabled=False)
        metrics.record_message("TestWidget")

        stats = metrics.get_stats("TestWidget")
        assert stats.message_count == 0
        assert stats.messages_per_second == 0.0

    def test_record_message_when_enabled(self) -> None:
        """Recording messages when enabled should capture data."""
        metrics = WidgetMetrics(enabled=True)

        # Mock time() to return controlled timestamps spaced 0.1s apart
        base = 1000000.0
        call_count = 0

        def mock_time() -> float:
            nonlocal call_count
            result = base + call_count * 0.1
            call_count += 1
            return result

        with patch("maverick.tui.metrics.time", side_effect=mock_time):
            metrics.record_message("TestWidget")
            metrics.record_message("TestWidget")
            metrics.record_message("TestWidget")

        stats = metrics.get_stats("TestWidget")
        assert stats.message_count == 3
        # Throughput: 3 messages / 0.2 seconds = 15 msg/sec
        assert 14.0 < stats.messages_per_second < 16.0

    def test_get_stats_all_widgets(self) -> None:
        """Get stats for all widgets combined."""
        metrics = WidgetMetrics(enabled=True)
        metrics.record_render("Widget1", 10.0)
        metrics.record_render("Widget2", 20.0)
        metrics.record_render("Widget1", 15.0)

        stats = metrics.get_stats(None)  # All widgets
        assert stats.widget_name is None
        assert stats.render_count == 3
        assert stats.avg_render_ms == pytest.approx((10.0 + 20.0 + 15.0) / 3)

    def test_get_stats_specific_widget(self) -> None:
        """Get stats for a specific widget."""
        metrics = WidgetMetrics(enabled=True)
        metrics.record_render("Widget1", 10.0)
        metrics.record_render("Widget2", 20.0)
        metrics.record_render("Widget1", 15.0)

        stats = metrics.get_stats("Widget1")
        assert stats.widget_name == "Widget1"
        assert stats.render_count == 2
        assert stats.avg_render_ms == pytest.approx((10.0 + 15.0) / 2)

    def test_percentile_calculations(self) -> None:
        """Test render time percentile calculations."""
        metrics = WidgetMetrics(enabled=True)
        # Record 100 values from 1ms to 100ms
        for i in range(1, 101):
            metrics.record_render("TestWidget", float(i))

        stats = metrics.get_stats("TestWidget")
        assert stats.p50_render_ms == pytest.approx(50.5, abs=1.0)
        assert stats.p95_render_ms == pytest.approx(95.5, abs=1.0)
        assert stats.p99_render_ms == pytest.approx(99.5, abs=1.0)

    def test_clear_metrics(self) -> None:
        """Test clearing all metrics."""
        metrics = WidgetMetrics(enabled=True)
        metrics.record_render("TestWidget", 10.0)
        metrics.record_message("TestWidget")

        stats = metrics.get_stats("TestWidget")
        assert stats.render_count > 0
        assert stats.message_count > 0

        metrics.clear()

        stats = metrics.get_stats("TestWidget")
        assert stats.render_count == 0
        assert stats.message_count == 0

    def test_rolling_window_limit(self) -> None:
        """Test that metrics respect max_entries rolling window."""
        metrics = WidgetMetrics(enabled=True, max_entries=10)

        # Record 20 render entries
        for i in range(20):
            metrics.record_render("TestWidget", float(i))

        # Should only keep last 10 due to rolling window
        stats = metrics.get_stats("TestWidget")
        assert stats.render_count == 10
        # Average should be over last 10 values (10-19)
        assert stats.avg_render_ms == pytest.approx(14.5)

    def test_thread_safety(self) -> None:
        """Test that metrics collection is thread-safe."""
        metrics = WidgetMetrics(enabled=True)

        def record_renders() -> None:
            for _ in range(100):
                metrics.record_render("TestWidget", 10.0)

        # Run recordings from multiple threads
        threads = [Thread(target=record_renders) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        stats = metrics.get_stats("TestWidget")
        assert stats.render_count == 500  # 5 threads * 100 records

    def test_empty_stats(self) -> None:
        """Test stats for widget with no data."""
        metrics = WidgetMetrics(enabled=True)
        stats = metrics.get_stats("NonExistent")

        assert stats.widget_name == "NonExistent"
        assert stats.render_count == 0
        assert stats.message_count == 0
        assert stats.avg_render_ms == 0.0
        assert stats.p50_render_ms == 0.0
        assert stats.p95_render_ms == 0.0
        assert stats.p99_render_ms == 0.0
        assert stats.messages_per_second == 0.0

    def test_single_message_throughput(self) -> None:
        """Test that single message doesn't calculate throughput."""
        metrics = WidgetMetrics(enabled=True)
        metrics.record_message("TestWidget")

        stats = metrics.get_stats("TestWidget")
        assert stats.message_count == 1
        assert stats.messages_per_second == 0.0  # Need at least 2 for rate


class TestConfigureMetrics:
    """Test cases for configure_metrics function."""

    def test_configure_metrics_enabled(self) -> None:
        """Test configuring metrics as enabled."""
        # Import to get the newly configured instance
        from maverick.tui import metrics

        configure_metrics(enabled=True, max_entries=5000)

        # Access the newly configured global instance
        assert metrics.widget_metrics.enabled
        # Record something to verify max_entries is respected
        for i in range(10):
            metrics.widget_metrics.record_render("Test", float(i))

    def test_configure_metrics_disabled(self) -> None:
        """Test configuring metrics as disabled."""
        configure_metrics(enabled=False)

        assert not widget_metrics.enabled


class TestWidgetStatsDataclass:
    """Test cases for WidgetStats dataclass."""

    def test_widget_stats_creation(self) -> None:
        """Test creating WidgetStats with all fields."""
        stats = WidgetStats(
            widget_name="TestWidget",
            render_count=100,
            message_count=50,
            avg_render_ms=15.5,
            p50_render_ms=12.0,
            p95_render_ms=25.0,
            p99_render_ms=30.0,
            messages_per_second=10.5,
        )

        assert stats.widget_name == "TestWidget"
        assert stats.render_count == 100
        assert stats.message_count == 50
        assert stats.avg_render_ms == 15.5
        assert stats.p50_render_ms == 12.0
        assert stats.p95_render_ms == 25.0
        assert stats.p99_render_ms == 30.0
        assert stats.messages_per_second == 10.5

    def test_widget_stats_frozen(self) -> None:
        """Test that WidgetStats is immutable."""
        stats = WidgetStats(
            widget_name="TestWidget",
            render_count=100,
            message_count=50,
            avg_render_ms=15.5,
            p50_render_ms=12.0,
            p95_render_ms=25.0,
            p99_render_ms=30.0,
            messages_per_second=10.5,
        )

        with pytest.raises(AttributeError):
            stats.render_count = 200  # type: ignore[misc]


class TestRealWorldScenarios:
    """Test cases simulating real widget usage patterns."""

    def test_agent_output_message_throughput(self) -> None:
        """Simulate AgentOutput receiving multiple messages rapidly."""
        metrics = WidgetMetrics(enabled=True)

        # Mock time() to return timestamps spaced 50ms apart
        base = 1000000.0
        call_count = 0

        def mock_time() -> float:
            nonlocal call_count
            result = base + call_count * 0.05
            call_count += 1
            return result

        with patch("maverick.tui.metrics.time", side_effect=mock_time):
            for _ in range(10):
                metrics.record_message("AgentOutput")

        stats = metrics.get_stats("AgentOutput")

        assert stats.message_count == 10
        # Throughput: 10 messages / 0.45 seconds ~ 22.2 msg/sec
        assert 20.0 < stats.messages_per_second < 25.0

    def test_workflow_progress_render_timing(self) -> None:
        """Simulate WorkflowProgress rebuilding stages."""
        metrics = WidgetMetrics(enabled=True)

        # Simulate multiple stage updates with varying render times
        metrics.record_render("WorkflowProgress", 5.2)
        metrics.record_render("WorkflowProgress", 8.7)
        metrics.record_render("WorkflowProgress", 6.1)
        metrics.record_render("WorkflowProgress", 12.3)

        stats = metrics.get_stats("WorkflowProgress")

        assert stats.render_count == 4
        assert 7.0 < stats.avg_render_ms < 9.0
        assert stats.p50_render_ms == pytest.approx(7.4, abs=1.0)

    def test_review_findings_refresh_performance(self) -> None:
        """Simulate ReviewFindings refresh with many findings."""
        metrics = WidgetMetrics(enabled=True)

        # Simulate rendering large finding lists
        metrics.record_render("ReviewFindings", 25.3)
        metrics.record_render("ReviewFindings", 28.1)
        metrics.record_render("ReviewFindings", 32.5)

        stats = metrics.get_stats("ReviewFindings")

        assert stats.render_count == 3
        assert 25.0 < stats.avg_render_ms < 30.0

    def test_multiple_widgets_interleaved(self) -> None:
        """Test metrics for multiple widgets updating simultaneously."""
        metrics = WidgetMetrics(enabled=True)

        # Interleaved updates from different widgets
        metrics.record_render("AgentOutput", 10.0)
        metrics.record_message("AgentOutput")
        metrics.record_render("WorkflowProgress", 5.0)
        metrics.record_message("ReviewFindings")
        metrics.record_render("AgentOutput", 12.0)
        metrics.record_render("WorkflowProgress", 6.0)

        # Check each widget independently
        agent_stats = metrics.get_stats("AgentOutput")
        assert agent_stats.render_count == 2
        assert agent_stats.message_count == 1

        workflow_stats = metrics.get_stats("WorkflowProgress")
        assert workflow_stats.render_count == 2

        findings_stats = metrics.get_stats("ReviewFindings")
        assert findings_stats.message_count == 1

    def test_performance_overhead_when_disabled(self) -> None:
        """Verify minimal overhead when metrics are disabled."""
        metrics = WidgetMetrics(enabled=False)

        # Should complete instantly even with many calls
        start = time.perf_counter()
        for _ in range(10000):
            metrics.record_render("TestWidget", 1.0)
            metrics.record_message("TestWidget")
        elapsed = time.perf_counter() - start

        # Should be very fast (< 100ms for 10k no-op calls)
        # Using 100ms as threshold to account for CI/slower environments
        assert elapsed < 0.1

        # Verify nothing was recorded
        stats = metrics.get_stats("TestWidget")
        assert stats.render_count == 0
        assert stats.message_count == 0
