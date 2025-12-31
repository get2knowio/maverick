from __future__ import annotations

import asyncio
from time import time

import pytest

from maverick.hooks.config import MetricsConfig
from maverick.hooks.metrics import MetricsCollector, collect_metrics
from maverick.hooks.types import ToolMetricEntry


class TestMetricsCollectorRecordAndQuery:
    """Tests for MetricsCollector record and query operations."""

    @pytest.mark.asyncio
    async def test_record_single_entry(self) -> None:
        """Test recording a single metric entry."""
        collector = MetricsCollector()
        entry = ToolMetricEntry(
            tool_name="Bash",
            timestamp=time(),
            duration_ms=50.0,
            success=True,
        )
        await collector.record(entry)
        assert collector.entry_count == 1

    @pytest.mark.asyncio
    async def test_get_metrics_all_tools(self) -> None:
        """Test getting metrics for all tools."""
        collector = MetricsCollector()
        for i in range(10):
            await collector.record(
                ToolMetricEntry(
                    tool_name="Bash" if i % 2 == 0 else "Write",
                    timestamp=time(),
                    duration_ms=50.0 + i,
                    success=True,
                )
            )

        metrics = await collector.get_metrics()
        assert metrics.call_count == 10
        assert metrics.tool_name is None

    @pytest.mark.asyncio
    async def test_get_metrics_specific_tool(self) -> None:
        """Test getting metrics for a specific tool."""
        collector = MetricsCollector()
        for i in range(10):
            await collector.record(
                ToolMetricEntry(
                    tool_name="Bash" if i % 2 == 0 else "Write",
                    timestamp=time(),
                    duration_ms=50.0,
                    success=True,
                )
            )

        metrics = await collector.get_metrics("Bash")
        assert metrics.call_count == 5
        assert metrics.tool_name == "Bash"

    @pytest.mark.asyncio
    async def test_empty_metrics(self) -> None:
        """Test metrics for empty collector."""
        collector = MetricsCollector()
        metrics = await collector.get_metrics()
        assert metrics.call_count == 0
        assert metrics.avg_duration_ms == 0.0


class TestRollingWindowEviction:
    """Tests for rolling window eviction."""

    @pytest.mark.asyncio
    async def test_max_entries_enforced(self) -> None:
        """Test that max entries is enforced."""
        config = MetricsConfig(max_entries=100)
        collector = MetricsCollector(config)

        # Add more entries than max
        for _ in range(150):
            await collector.record(
                ToolMetricEntry(
                    tool_name="Bash",
                    timestamp=time(),
                    duration_ms=50.0,
                    success=True,
                )
            )

        assert collector.entry_count == 100

    @pytest.mark.asyncio
    async def test_oldest_entries_evicted(self) -> None:
        """Test that oldest entries are evicted first."""
        config = MetricsConfig(max_entries=100)
        collector = MetricsCollector(config)

        # Add entries with increasing duration
        for i in range(150):
            await collector.record(
                ToolMetricEntry(
                    tool_name="Bash",
                    timestamp=time(),
                    duration_ms=float(i * 10),
                    success=True,
                )
            )

        metrics = await collector.get_metrics()
        # Oldest entries (0-49) should be evicted
        # Average should be (500+510+520+...+1490)/100
        # This is sum from 50 to 149 multiplied by 10
        # Sum of 50..149 = (50+149)*100/2 = 9950
        # Average = 9950 * 10 / 100 = 995
        assert metrics.avg_duration_ms == 995.0


class TestThreadSafety:
    """Tests for thread-safety under concurrent access."""

    @pytest.mark.asyncio
    async def test_concurrent_records(self) -> None:
        """Test concurrent record operations."""
        collector = MetricsCollector()

        async def record_many(start: int) -> None:
            for i in range(100):
                await collector.record(
                    ToolMetricEntry(
                        tool_name="Bash",
                        timestamp=time(),
                        duration_ms=float(start + i),
                        success=True,
                    )
                )

        # Run multiple concurrent tasks
        await asyncio.gather(
            record_many(0),
            record_many(100),
            record_many(200),
        )

        assert collector.entry_count == 300

    @pytest.mark.asyncio
    async def test_concurrent_read_write(self) -> None:
        """Test concurrent read and write operations."""
        collector = MetricsCollector()

        async def writer() -> None:
            for _ in range(50):
                await collector.record(
                    ToolMetricEntry(
                        tool_name="Bash",
                        timestamp=time(),
                        duration_ms=50.0,
                        success=True,
                    )
                )

        async def reader() -> None:
            for _ in range(50):
                await collector.get_metrics()

        # Run concurrent readers and writers
        await asyncio.gather(
            writer(),
            reader(),
            writer(),
            reader(),
        )

        # Should have 100 entries from 2 writers
        assert collector.entry_count == 100


class TestPercentileCalculations:
    """Tests for percentile calculations."""

    @pytest.mark.asyncio
    async def test_p50_calculation(self) -> None:
        """Test median (p50) calculation."""
        collector = MetricsCollector()

        # Add entries with known durations: 10, 20, 30, 40, 50
        for duration in [10, 20, 30, 40, 50]:
            await collector.record(
                ToolMetricEntry(
                    tool_name="Bash",
                    timestamp=time(),
                    duration_ms=float(duration),
                    success=True,
                )
            )

        metrics = await collector.get_metrics()
        assert metrics.p50_duration_ms == 30.0

    @pytest.mark.asyncio
    async def test_p95_calculation(self) -> None:
        """Test p95 calculation."""
        collector = MetricsCollector()

        # Add 100 entries with durations 1-100
        for i in range(1, 101):
            await collector.record(
                ToolMetricEntry(
                    tool_name="Bash",
                    timestamp=time(),
                    duration_ms=float(i),
                    success=True,
                )
            )

        metrics = await collector.get_metrics()
        # P95 should be close to 95
        assert 94 <= metrics.p95_duration_ms <= 96

    @pytest.mark.asyncio
    async def test_p99_calculation(self) -> None:
        """Test p99 calculation."""
        collector = MetricsCollector()

        # Add 100 entries with durations 1-100
        for i in range(1, 101):
            await collector.record(
                ToolMetricEntry(
                    tool_name="Bash",
                    timestamp=time(),
                    duration_ms=float(i),
                    success=True,
                )
            )

        metrics = await collector.get_metrics()
        # P99 should be close to 99
        assert 98 <= metrics.p99_duration_ms <= 100

    @pytest.mark.asyncio
    async def test_success_failure_counts(self) -> None:
        """Test success and failure counting."""
        collector = MetricsCollector()

        # Add 7 successes and 3 failures
        for i in range(10):
            await collector.record(
                ToolMetricEntry(
                    tool_name="Bash",
                    timestamp=time(),
                    duration_ms=50.0,
                    success=i < 7,
                )
            )

        metrics = await collector.get_metrics()
        assert metrics.success_count == 7
        assert metrics.failure_count == 3
        assert metrics.success_rate == 0.7
        assert metrics.failure_rate == 0.3


class TestCollectMetrics:
    """Tests for collect_metrics hook function."""

    @pytest.mark.asyncio
    async def test_collects_metric(self) -> None:
        """Test that collect_metrics records a metric."""
        collector = MetricsCollector()
        input_data = {
            "tool_name": "Bash",
            "status": "success",
        }

        await collect_metrics(input_data, None, None, collector=collector)

        assert collector.entry_count == 1

    @pytest.mark.asyncio
    async def test_calculates_duration(self) -> None:
        """Test duration calculation from start_time."""
        collector = MetricsCollector()
        input_data = {
            "tool_name": "Bash",
            "status": "success",
        }

        start = time() - 0.1  # 100ms ago
        await collect_metrics(
            input_data, None, None, collector=collector, start_time=start
        )

        metrics = await collector.get_metrics()
        # Duration should be approximately 100ms
        assert metrics.avg_duration_ms >= 90  # Allow some tolerance

    @pytest.mark.asyncio
    async def test_records_failure(self) -> None:
        """Test recording failure status."""
        collector = MetricsCollector()
        input_data = {
            "tool_name": "Bash",
            "status": "error",
        }

        await collect_metrics(input_data, None, None, collector=collector)

        metrics = await collector.get_metrics()
        assert metrics.failure_count == 1
        assert metrics.success_count == 0


class TestClear:
    """Tests for clear functionality."""

    @pytest.mark.asyncio
    async def test_clear_empties_collector(self) -> None:
        """Test that clear removes all entries."""
        collector = MetricsCollector()

        # Add entries
        for _ in range(10):
            await collector.record(
                ToolMetricEntry(
                    tool_name="Bash",
                    timestamp=time(),
                    duration_ms=50.0,
                    success=True,
                )
            )

        assert collector.entry_count == 10

        await collector.clear()

        assert collector.entry_count == 0
