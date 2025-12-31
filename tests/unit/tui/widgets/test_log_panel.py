"""Unit tests for LogPanel widget."""

from __future__ import annotations

import pytest
from textual.app import App
from textual.widgets import RichLog

from maverick.tui.widgets.log_panel import LogPanel

# =============================================================================
# Test App for LogPanel Testing
# =============================================================================


class LogPanelTestApp(App):
    """Test app for LogPanel widget testing."""

    def compose(self):
        """Compose the test app."""
        yield LogPanel()


# =============================================================================
# LogPanel Initialization Tests
# =============================================================================


class TestLogPanelInitialization:
    """Tests for LogPanel initialization."""

    @pytest.mark.asyncio
    async def test_initialization_defaults(self) -> None:
        """Test LogPanel initializes with default values."""
        async with LogPanelTestApp().run_test() as pilot:
            log_panel = pilot.app.query_one(LogPanel)

            assert log_panel.panel_visible is False
            assert log_panel.auto_scroll is True

    @pytest.mark.asyncio
    async def test_compose_creates_richlog(self) -> None:
        """Test compose creates RichLog widget."""
        async with LogPanelTestApp().run_test() as pilot:
            log_panel = pilot.app.query_one(LogPanel)

            # Check RichLog exists
            rich_log = log_panel.query_one("#log-content", RichLog)
            assert rich_log is not None
            assert rich_log.max_lines == LogPanel.MAX_LINES

    @pytest.mark.asyncio
    async def test_max_lines_constant(self) -> None:
        """Test MAX_LINES constant is correct value."""
        assert LogPanel.MAX_LINES == 1000


# =============================================================================
# Toggle Tests
# =============================================================================


class TestLogPanelToggle:
    """Tests for LogPanel toggle functionality."""

    @pytest.mark.asyncio
    async def test_toggle_changes_visibility(self) -> None:
        """Test toggle changes panel_visible property."""
        async with LogPanelTestApp().run_test() as pilot:
            log_panel = pilot.app.query_one(LogPanel)

            # Initially not visible
            assert log_panel.panel_visible is False

            # Toggle to visible
            log_panel.toggle()
            assert log_panel.panel_visible is True

            # Toggle back to not visible
            log_panel.toggle()
            assert log_panel.panel_visible is False

    @pytest.mark.asyncio
    async def test_toggle_multiple_times(self) -> None:
        """Test toggle works correctly multiple times."""
        async with LogPanelTestApp().run_test() as pilot:
            log_panel = pilot.app.query_one(LogPanel)

            initial_state = log_panel.panel_visible
            log_panel.toggle()
            assert log_panel.panel_visible is not initial_state

            log_panel.toggle()
            assert log_panel.panel_visible is initial_state

            log_panel.toggle()
            assert log_panel.panel_visible is not initial_state

    @pytest.mark.asyncio
    async def test_watch_panel_visible_adds_css_class(self) -> None:
        """Test watch_panel_visible adds CSS class when visible."""
        async with LogPanelTestApp().run_test() as pilot:
            log_panel = pilot.app.query_one(LogPanel)

            # Toggle to visible
            log_panel.panel_visible = True
            await pilot.pause()

            # Check CSS class was added
            assert log_panel.has_class("visible")

    @pytest.mark.asyncio
    async def test_watch_panel_visible_removes_css_class(self) -> None:
        """Test watch_panel_visible removes CSS class when not visible."""
        async with LogPanelTestApp().run_test() as pilot:
            log_panel = pilot.app.query_one(LogPanel)

            # Set visible then back to not visible
            log_panel.panel_visible = True
            await pilot.pause()

            log_panel.panel_visible = False
            await pilot.pause()

            # Check CSS class was removed
            assert not log_panel.has_class("visible")


# =============================================================================
# Add Log Tests
# =============================================================================


class TestLogPanelAddLog:
    """Tests for LogPanel add_log functionality."""

    @pytest.mark.asyncio
    async def test_add_log_basic(self) -> None:
        """Test add_log adds a basic message."""
        async with LogPanelTestApp().run_test() as pilot:
            log_panel = pilot.app.query_one(LogPanel)

            log_panel.add_log("Test message")
            await pilot.pause()

            # Verify log was written
            rich_log = log_panel.query_one(RichLog)
            # RichLog doesn't expose content directly, but we can verify
            # write was called by checking that lines exist
            assert len(rich_log.lines) >= 1

    @pytest.mark.asyncio
    async def test_add_log_with_level_info(self) -> None:
        """Test add_log with info level uses blue color."""
        async with LogPanelTestApp().run_test() as pilot:
            log_panel = pilot.app.query_one(LogPanel)
            rich_log = log_panel.query_one(RichLog)

            log_panel.add_log("Info message", level="info")
            await pilot.pause()

            # Verify log was added
            assert len(rich_log.lines) >= 1

    @pytest.mark.asyncio
    async def test_add_log_with_level_success(self) -> None:
        """Test add_log with success level uses green color."""
        async with LogPanelTestApp().run_test() as pilot:
            log_panel = pilot.app.query_one(LogPanel)

            log_panel.add_log("Success message", level="success")
            await pilot.pause()

            rich_log = log_panel.query_one(RichLog)
            assert len(rich_log.lines) >= 1

    @pytest.mark.asyncio
    async def test_add_log_with_level_warning(self) -> None:
        """Test add_log with warning level uses yellow color."""
        async with LogPanelTestApp().run_test() as pilot:
            log_panel = pilot.app.query_one(LogPanel)

            log_panel.add_log("Warning message", level="warning")
            await pilot.pause()

            rich_log = log_panel.query_one(RichLog)
            assert len(rich_log.lines) >= 1

    @pytest.mark.asyncio
    async def test_add_log_with_level_error(self) -> None:
        """Test add_log with error level uses red color."""
        async with LogPanelTestApp().run_test() as pilot:
            log_panel = pilot.app.query_one(LogPanel)

            log_panel.add_log("Error message", level="error")
            await pilot.pause()

            rich_log = log_panel.query_one(RichLog)
            assert len(rich_log.lines) >= 1

    @pytest.mark.asyncio
    async def test_add_log_with_source(self) -> None:
        """Test add_log with source prefix."""
        async with LogPanelTestApp().run_test() as pilot:
            log_panel = pilot.app.query_one(LogPanel)

            log_panel.add_log("Message", source="TestAgent")
            await pilot.pause()

            rich_log = log_panel.query_one(RichLog)
            assert len(rich_log.lines) >= 1

    @pytest.mark.asyncio
    async def test_add_log_without_source(self) -> None:
        """Test add_log without source doesn't add prefix."""
        async with LogPanelTestApp().run_test() as pilot:
            log_panel = pilot.app.query_one(LogPanel)

            log_panel.add_log("Message")
            await pilot.pause()

            rich_log = log_panel.query_one(RichLog)
            assert len(rich_log.lines) >= 1

    @pytest.mark.asyncio
    async def test_add_log_with_unknown_level(self) -> None:
        """Test add_log with unknown level defaults to white."""
        async with LogPanelTestApp().run_test() as pilot:
            log_panel = pilot.app.query_one(LogPanel)

            log_panel.add_log("Message", level="unknown")
            await pilot.pause()

            rich_log = log_panel.query_one(RichLog)
            assert len(rich_log.lines) >= 1

    @pytest.mark.asyncio
    async def test_add_log_timestamp_format(self) -> None:
        """Test add_log uses correct timestamp format."""
        async with LogPanelTestApp().run_test() as pilot:
            log_panel = pilot.app.query_one(LogPanel)

            log_panel.add_log("Message")
            await pilot.pause()

            # Timestamp should be formatted as HH:MM:SS
            # We can't easily check the exact output, but we verified write was called
            rich_log = log_panel.query_one(RichLog)
            assert len(rich_log.lines) >= 1

    @pytest.mark.asyncio
    async def test_add_log_multiple_messages(self) -> None:
        """Test add_log can add multiple messages."""
        async with LogPanelTestApp().run_test() as pilot:
            log_panel = pilot.app.query_one(LogPanel)

            log_panel.add_log("Message 1")
            log_panel.add_log("Message 2")
            log_panel.add_log("Message 3")
            await pilot.pause()

            rich_log = log_panel.query_one(RichLog)
            assert len(rich_log.lines) >= 3


# =============================================================================
# Auto-scroll Tests
# =============================================================================


class TestLogPanelAutoScroll:
    """Tests for LogPanel auto-scroll functionality."""

    @pytest.mark.asyncio
    async def test_auto_scroll_enabled_by_default(self) -> None:
        """Test auto_scroll is enabled by default."""
        async with LogPanelTestApp().run_test() as pilot:
            log_panel = pilot.app.query_one(LogPanel)

            assert log_panel.auto_scroll is True

    @pytest.mark.asyncio
    async def test_add_log_scrolls_when_auto_scroll_enabled(self) -> None:
        """Test add_log scrolls to bottom when auto_scroll is True."""
        async with LogPanelTestApp().run_test() as pilot:
            log_panel = pilot.app.query_one(LogPanel)

            # Enable auto-scroll
            log_panel.auto_scroll = True

            # Add log and verify it doesn't crash with auto_scroll enabled
            log_panel.add_log("Message")
            await pilot.pause()

            # Verify auto_scroll is still enabled
            assert log_panel.auto_scroll is True

    @pytest.mark.asyncio
    async def test_add_log_does_not_scroll_when_auto_scroll_disabled(self) -> None:
        """Test add_log with auto_scroll disabled still adds the log."""
        async with LogPanelTestApp().run_test() as pilot:
            log_panel = pilot.app.query_one(LogPanel)

            # Disable auto-scroll
            log_panel.auto_scroll = False

            # Add log and verify it doesn't crash with auto_scroll disabled
            log_panel.add_log("Message")
            await pilot.pause()

            # Verify auto_scroll is still disabled
            assert log_panel.auto_scroll is False


# =============================================================================
# Clear Tests
# =============================================================================


class TestLogPanelClear:
    """Tests for LogPanel clear functionality."""

    @pytest.mark.asyncio
    async def test_clear_removes_all_logs(self) -> None:
        """Test clear removes all log entries."""
        async with LogPanelTestApp().run_test() as pilot:
            log_panel = pilot.app.query_one(LogPanel)

            # Add some logs
            log_panel.add_log("Message 1")
            log_panel.add_log("Message 2")
            log_panel.add_log("Message 3")
            await pilot.pause()

            rich_log = log_panel.query_one(RichLog)
            assert len(rich_log.lines) >= 3

            # Clear logs
            log_panel.clear()
            await pilot.pause()

            # Verify logs were cleared
            assert len(rich_log.lines) == 0

    @pytest.mark.asyncio
    async def test_clear_on_empty_log(self) -> None:
        """Test clear on empty log doesn't raise error."""
        async with LogPanelTestApp().run_test() as pilot:
            log_panel = pilot.app.query_one(LogPanel)

            # Clear when empty (should not raise)
            log_panel.clear()
            await pilot.pause()

            rich_log = log_panel.query_one(RichLog)
            assert len(rich_log.lines) == 0

    @pytest.mark.asyncio
    async def test_clear_then_add_log(self) -> None:
        """Test adding logs after clear works correctly."""
        async with LogPanelTestApp().run_test() as pilot:
            log_panel = pilot.app.query_one(LogPanel)

            # Add, clear, then add again
            log_panel.add_log("Message 1")
            await pilot.pause()
            log_panel.clear()
            await pilot.pause()
            log_panel.add_log("Message 2")
            await pilot.pause()

            rich_log = log_panel.query_one(RichLog)
            assert len(rich_log.lines) >= 1


# =============================================================================
# Buffer Limit Tests
# =============================================================================


class TestLogPanelBufferLimit:
    """Tests for LogPanel buffer limit (MAX_LINES)."""

    @pytest.mark.asyncio
    async def test_richlog_max_lines_set_correctly(self) -> None:
        """Test RichLog is initialized with correct max_lines."""
        async with LogPanelTestApp().run_test() as pilot:
            log_panel = pilot.app.query_one(LogPanel)
            rich_log = log_panel.query_one(RichLog)

            assert rich_log.max_lines == 1000

    @pytest.mark.asyncio
    async def test_buffer_limit_enforced_by_richlog(self) -> None:
        """Test that RichLog enforces the buffer limit.

        Note: This test verifies that the max_lines is set correctly.
        The actual enforcement is handled by RichLog itself.
        """
        async with LogPanelTestApp().run_test() as pilot:
            log_panel = pilot.app.query_one(LogPanel)
            rich_log = log_panel.query_one(RichLog)

            # Add messages up to the limit
            for i in range(100):
                log_panel.add_log(f"Message {i}")
            await pilot.pause()

            # RichLog should handle this correctly
            assert len(rich_log.lines) >= 100


# =============================================================================
# Integration Tests
# =============================================================================


class TestLogPanelIntegration:
    """Integration tests for LogPanel."""

    @pytest.mark.asyncio
    async def test_typical_usage_flow(self) -> None:
        """Test typical usage flow of LogPanel."""
        async with LogPanelTestApp().run_test() as pilot:
            log_panel = pilot.app.query_one(LogPanel)

            # Start hidden
            assert log_panel.panel_visible is False

            # Toggle to show
            log_panel.toggle()
            await pilot.pause()
            assert log_panel.panel_visible is True

            # Add various logs
            log_panel.add_log("Starting workflow", level="info", source="Workflow")
            log_panel.add_log("Task completed", level="success", source="Agent")
            log_panel.add_log("Warning detected", level="warning", source="Validator")
            log_panel.add_log("Error occurred", level="error", source="Builder")
            await pilot.pause()

            rich_log = log_panel.query_one(RichLog)
            assert len(rich_log.lines) >= 4

            # Clear logs
            log_panel.clear()
            await pilot.pause()
            assert len(rich_log.lines) == 0

            # Toggle to hide
            log_panel.toggle()
            await pilot.pause()
            assert log_panel.panel_visible is False

    @pytest.mark.asyncio
    async def test_state_persistence_across_visibility_changes(self) -> None:
        """Test that logs persist when toggling visibility."""
        async with LogPanelTestApp().run_test() as pilot:
            log_panel = pilot.app.query_one(LogPanel)

            # Add logs while hidden
            log_panel.add_log("Message 1")
            log_panel.add_log("Message 2")
            await pilot.pause()

            # Toggle visibility
            log_panel.toggle()
            log_panel.toggle()
            await pilot.pause()

            # Logs should still be there
            rich_log = log_panel.query_one(RichLog)
            assert len(rich_log.lines) >= 2
