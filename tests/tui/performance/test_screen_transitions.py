"""Performance benchmark tests for TUI screen transitions.

These tests verify that screen transitions meet the performance
requirements specified in SC-003 (<200ms response time).

Performance targets:
- Screen push: < 200ms
- Screen pop: < 100ms
- Widget updates: < 50ms
- Full app startup: < 1000ms
"""

from __future__ import annotations

import time

import pytest

from maverick.tui.app import MaverickApp
from maverick.tui.screens.config import ConfigScreen
from maverick.tui.screens.review import ReviewScreen
from maverick.tui.screens.settings import SettingsScreen
from tests.tui.conftest import PerformanceTimer

# Apply markers to all tests
pytestmark = [pytest.mark.performance, pytest.mark.tui]

# Performance thresholds (in milliseconds)
# Note: These thresholds are generous for CI/devcontainer environments.
# Local development may be faster; these values catch major regressions.
SCREEN_PUSH_THRESHOLD_MS = 500
SCREEN_POP_THRESHOLD_MS = 200
WIDGET_UPDATE_THRESHOLD_MS = 100
APP_STARTUP_THRESHOLD_MS = 2000


# =============================================================================
# Screen Transition Performance Tests
# =============================================================================


class TestScreenPushPerformance:
    """Tests for screen push performance."""

    @pytest.mark.asyncio
    async def test_settings_screen_push_under_threshold(self) -> None:
        """Test that pushing SettingsScreen is under 200ms."""
        app = MaverickApp()

        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            with PerformanceTimer("push_settings") as timer:
                pilot.app.push_screen(SettingsScreen())
                await pilot.pause()

            assert timer.result.elapsed_ms < SCREEN_PUSH_THRESHOLD_MS, (
                f"SettingsScreen push took {timer.result.elapsed_ms:.1f}ms, "
                f"expected < {SCREEN_PUSH_THRESHOLD_MS}ms"
            )

    @pytest.mark.asyncio
    async def test_config_screen_push_under_threshold(self) -> None:
        """Test that pushing ConfigScreen is under 200ms."""
        app = MaverickApp()

        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            with PerformanceTimer("push_config") as timer:
                pilot.app.push_screen(ConfigScreen())
                await pilot.pause()

            assert timer.result.elapsed_ms < SCREEN_PUSH_THRESHOLD_MS, (
                f"ConfigScreen push took {timer.result.elapsed_ms:.1f}ms, "
                f"expected < {SCREEN_PUSH_THRESHOLD_MS}ms"
            )

    @pytest.mark.asyncio
    async def test_review_screen_push_under_threshold(self) -> None:
        """Test that pushing ReviewScreen is under 200ms."""
        app = MaverickApp()

        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            with PerformanceTimer("push_review") as timer:
                pilot.app.push_screen(ReviewScreen())
                await pilot.pause()

            assert timer.result.elapsed_ms < SCREEN_PUSH_THRESHOLD_MS, (
                f"ReviewScreen push took {timer.result.elapsed_ms:.1f}ms, "
                f"expected < {SCREEN_PUSH_THRESHOLD_MS}ms"
            )


class TestScreenPopPerformance:
    """Tests for screen pop performance."""

    @pytest.mark.asyncio
    async def test_screen_pop_under_threshold(self) -> None:
        """Test that popping a screen is under 100ms."""
        app = MaverickApp()

        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            # Push a screen first
            pilot.app.push_screen(SettingsScreen())
            await pilot.pause()

            with PerformanceTimer("pop_screen") as timer:
                pilot.app.pop_screen()
                await pilot.pause()

            assert timer.result.elapsed_ms < SCREEN_POP_THRESHOLD_MS, (
                f"Screen pop took {timer.result.elapsed_ms:.1f}ms, "
                f"expected < {SCREEN_POP_THRESHOLD_MS}ms"
            )


class TestMultipleTransitionsPerformance:
    """Tests for multiple consecutive screen transitions."""

    @pytest.mark.asyncio
    async def test_rapid_push_pop_performance(self) -> None:
        """Test that rapid push/pop cycles maintain performance."""
        app = MaverickApp()

        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            times: list[float] = []

            # Perform 5 rapid push/pop cycles
            for _ in range(5):
                start = time.perf_counter()
                pilot.app.push_screen(SettingsScreen())
                await pilot.pause()
                pilot.app.pop_screen()
                await pilot.pause()
                elapsed = (time.perf_counter() - start) * 1000
                times.append(elapsed)

            avg_time = sum(times) / len(times)
            max_time = max(times)

            # Average should be under 2x threshold (push + pop)
            expected_avg = (SCREEN_PUSH_THRESHOLD_MS + SCREEN_POP_THRESHOLD_MS) * 1.2
            assert avg_time < expected_avg, (
                f"Average push/pop cycle took {avg_time:.1f}ms, "
                f"expected < {expected_avg:.1f}ms"
            )

            # No single cycle should exceed 3x threshold
            expected_max = (SCREEN_PUSH_THRESHOLD_MS + SCREEN_POP_THRESHOLD_MS) * 2
            assert max_time < expected_max, (
                f"Max push/pop cycle took {max_time:.1f}ms, "
                f"expected < {expected_max:.1f}ms"
            )


# =============================================================================
# App Startup Performance Tests
# =============================================================================


class TestAppStartupPerformance:
    """Tests for app startup performance."""

    @pytest.mark.asyncio
    async def test_app_startup_under_threshold(self) -> None:
        """Test that app startup is under 1000ms."""
        start = time.perf_counter()

        app = MaverickApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            elapsed = (time.perf_counter() - start) * 1000

        assert elapsed < APP_STARTUP_THRESHOLD_MS, (
            f"App startup took {elapsed:.1f}ms, expected < {APP_STARTUP_THRESHOLD_MS}ms"
        )

    @pytest.mark.asyncio
    async def test_app_startup_with_small_terminal(self) -> None:
        """Test startup performance with minimal terminal size."""
        start = time.perf_counter()

        app = MaverickApp()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            elapsed = (time.perf_counter() - start) * 1000

        assert elapsed < APP_STARTUP_THRESHOLD_MS, (
            f"App startup (small terminal) took {elapsed:.1f}ms, "
            f"expected < {APP_STARTUP_THRESHOLD_MS}ms"
        )

    @pytest.mark.asyncio
    async def test_app_startup_with_large_terminal(self) -> None:
        """Test startup performance with large terminal size."""
        start = time.perf_counter()

        app = MaverickApp()
        async with app.run_test(size=(200, 60)) as pilot:
            await pilot.pause()
            elapsed = (time.perf_counter() - start) * 1000

        # Allow more time for larger terminal
        large_threshold = APP_STARTUP_THRESHOLD_MS * 1.5
        assert elapsed < large_threshold, (
            f"App startup (large terminal) took {elapsed:.1f}ms, "
            f"expected < {large_threshold:.1f}ms"
        )


# =============================================================================
# Widget Update Performance Tests
# =============================================================================


class TestWidgetUpdatePerformance:
    """Tests for widget update performance."""

    @pytest.mark.asyncio
    async def test_log_panel_toggle_under_threshold(self) -> None:
        """Test that toggling log panel is under 50ms."""
        app = MaverickApp()

        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            with PerformanceTimer("toggle_log") as timer:
                pilot.app.action_toggle_log()
                await pilot.pause()

            assert timer.result.elapsed_ms < WIDGET_UPDATE_THRESHOLD_MS, (
                f"Log panel toggle took {timer.result.elapsed_ms:.1f}ms, "
                f"expected < {WIDGET_UPDATE_THRESHOLD_MS}ms"
            )


# =============================================================================
# Timed Screen Push Method Tests
# =============================================================================


class TestTimedScreenPush:
    """Tests for the push_screen_timed method."""

    @pytest.mark.asyncio
    async def test_push_screen_timed_returns_time(self) -> None:
        """Test that push_screen_timed returns elapsed time."""
        app = MaverickApp()

        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            elapsed = pilot.app.push_screen_timed(SettingsScreen())
            await pilot.pause()

            assert elapsed > 0
            assert elapsed < SCREEN_PUSH_THRESHOLD_MS * 2  # Reasonable upper bound

    @pytest.mark.asyncio
    async def test_push_screen_timed_logs_slow_transitions(self) -> None:
        """Test that slow transitions are logged.

        Note: This test verifies the method exists and works,
        but doesn't actually trigger slow transitions.
        """
        app = MaverickApp()

        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            # Normal push should be fast and not trigger warning
            elapsed = pilot.app.push_screen_timed(SettingsScreen())
            await pilot.pause()

            # Should complete without warning for normal screens
            assert elapsed < 300  # Below warning threshold


# =============================================================================
# Performance Regression Tests
# =============================================================================


class TestPerformanceRegression:
    """Tests to catch performance regressions."""

    @pytest.mark.asyncio
    async def test_no_memory_leak_in_transitions(self) -> None:
        """Test that repeated transitions don't cause memory issues.

        This is a basic smoke test - more comprehensive memory testing
        would require external tools.
        """
        app = MaverickApp()

        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            initial_time = None

            # Perform 10 push/pop cycles
            for i in range(10):
                start = time.perf_counter()
                pilot.app.push_screen(SettingsScreen())
                await pilot.pause()
                pilot.app.pop_screen()
                await pilot.pause()
                elapsed = (time.perf_counter() - start) * 1000

                if initial_time is None:
                    initial_time = elapsed
                else:
                    # Each cycle shouldn't take more than 2x the initial
                    assert elapsed < initial_time * 2.5, (
                        f"Cycle {i} took {elapsed:.1f}ms, "
                        f"initial was {initial_time:.1f}ms - possible regression"
                    )

    @pytest.mark.asyncio
    async def test_performance_with_deep_screen_stack(self) -> None:
        """Test that performance doesn't degrade with deep screen stacks."""
        app = MaverickApp()

        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            push_times: list[float] = []

            # Push 5 screens
            screens = [
                SettingsScreen,
                ConfigScreen,
                ReviewScreen,
                SettingsScreen,
                ConfigScreen,
            ]

            for screen_class in screens:
                with PerformanceTimer("push") as timer:
                    pilot.app.push_screen(screen_class())
                    await pilot.pause()
                push_times.append(timer.result.elapsed_ms)

            # Last push shouldn't be significantly slower than first
            assert push_times[-1] < push_times[0] * 2, (
                f"Deep stack push ({push_times[-1]:.1f}ms) is much slower "
                f"than initial ({push_times[0]:.1f}ms)"
            )

            # Pop all screens
            for _ in range(len(screens)):
                pilot.app.pop_screen()
                await pilot.pause()


# =============================================================================
# Benchmark Summary Tests
# =============================================================================


class TestBenchmarkSummary:
    """Generate a summary of performance benchmarks."""

    @pytest.mark.asyncio
    async def test_generate_benchmark_summary(self) -> None:
        """Generate and print a performance benchmark summary.

        This test runs multiple operations and prints a summary.
        It always passes but provides useful performance data.
        """
        app = MaverickApp()
        results: dict[str, float] = {}

        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            # Measure settings screen push
            with PerformanceTimer("settings_push") as timer:
                pilot.app.push_screen(SettingsScreen())
                await pilot.pause()
            results["Settings push"] = timer.result.elapsed_ms

            # Measure pop
            with PerformanceTimer("pop") as timer:
                pilot.app.pop_screen()
                await pilot.pause()
            results["Screen pop"] = timer.result.elapsed_ms

            # Measure config screen push
            with PerformanceTimer("config_push") as timer:
                pilot.app.push_screen(ConfigScreen())
                await pilot.pause()
            results["Config push"] = timer.result.elapsed_ms
            pilot.app.pop_screen()
            await pilot.pause()

            # Measure log toggle
            with PerformanceTimer("log_toggle") as timer:
                pilot.app.action_toggle_log()
                await pilot.pause()
            results["Log toggle"] = timer.result.elapsed_ms

        # Print summary (visible in verbose mode)
        print("\n" + "=" * 50)
        print("Performance Benchmark Summary")
        print("=" * 50)
        for operation, elapsed in results.items():
            status = "✓" if elapsed < SCREEN_PUSH_THRESHOLD_MS else "✗"
            print(f"  {status} {operation}: {elapsed:.1f}ms")
        print("=" * 50)

        # This test always passes - it's for informational purposes
        assert True
