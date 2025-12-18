"""Tests for TUI test fixtures and utilities.

Verifies that the TUI conftest fixtures and utilities work correctly.
"""

from __future__ import annotations

from collections.abc import Iterable

import pytest
from textual.app import App
from textual.widget import Widget
from textual.widgets import Static

from tests.tui.conftest import (
    ScreenTestApp,
    TUITestApp,
    assert_has_class,
    assert_not_has_class,
    assert_widget_count,
)

# =============================================================================
# TUITestApp Tests
# =============================================================================


class SimpleTUITestApp(TUITestApp):
    """Test app with a simple widget."""

    def compose(self) -> Iterable[Widget]:
        """Compose test app with a Static widget."""
        yield Static("Test content", id="test-static")


class TestTUITestApp:
    """Tests for TUITestApp base class."""

    @pytest.mark.asyncio
    async def test_tui_test_app_basic_usage(self) -> None:
        """Test TUITestApp can be instantiated and run."""
        async with SimpleTUITestApp().run_test() as pilot:
            assert pilot.app is not None
            assert isinstance(pilot.app, App)

    @pytest.mark.asyncio
    async def test_tui_test_app_compose(self) -> None:
        """Test TUITestApp compose method works."""
        async with SimpleTUITestApp().run_test() as pilot:
            static = pilot.app.query_one("#test-static", Static)
            assert static is not None
            assert static.id == "test-static"

    @pytest.mark.asyncio
    async def test_tui_test_app_no_css_by_default(self) -> None:
        """Test TUITestApp has no CSS path by default."""
        app = TUITestApp()
        assert app.CSS_PATH is None


# =============================================================================
# ScreenTestApp Tests
# =============================================================================


class SimpleScreenTestApp(ScreenTestApp):
    """Test app for screen testing."""

    def compose(self) -> Iterable[Widget]:
        """Compose test app."""
        yield Static("Screen test", id="screen-content")


class TestScreenTestApp:
    """Tests for ScreenTestApp base class."""

    @pytest.mark.asyncio
    async def test_screen_test_app_basic_usage(self) -> None:
        """Test ScreenTestApp can be instantiated and run."""
        async with SimpleScreenTestApp().run_test() as pilot:
            assert pilot.app is not None
            assert isinstance(pilot.app, App)

    @pytest.mark.asyncio
    async def test_screen_test_app_no_css_by_default(self) -> None:
        """Test ScreenTestApp has no CSS path by default."""
        app = ScreenTestApp()
        assert app.CSS_PATH is None


# =============================================================================
# tui_pilot Fixture Tests
# =============================================================================


class TestTUIPilotFixture:
    """Tests for tui_pilot fixture."""

    @pytest.mark.asyncio
    async def test_tui_pilot_fixture_provides_pilot(self, tui_pilot: object) -> None:
        """Test tui_pilot fixture provides a pilot instance."""
        assert tui_pilot is not None
        assert tui_pilot.app is not None  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_tui_pilot_fixture_app_is_tui_test_app(
        self, tui_pilot: object
    ) -> None:
        """Test tui_pilot fixture uses TUITestApp."""
        assert isinstance(tui_pilot.app, TUITestApp)  # type: ignore[attr-defined]


# =============================================================================
# Utility Function Tests
# =============================================================================


class WidgetWithClassesApp(TUITestApp):
    """Test app with a widget that has CSS classes."""

    def compose(self) -> Iterable[Widget]:
        """Compose app with widget that has classes."""
        widget = Static("Test", id="test-widget")
        widget.add_class("active")
        widget.add_class("highlight")
        yield widget


class TestAssertHasClass:
    """Tests for assert_has_class utility."""

    @pytest.mark.asyncio
    async def test_assert_has_class_passes_when_class_exists(self) -> None:
        """Test assert_has_class passes when widget has the class."""
        async with WidgetWithClassesApp().run_test() as pilot:
            widget = pilot.app.query_one("#test-widget")
            # Should not raise
            assert_has_class(widget, "active")

    @pytest.mark.asyncio
    async def test_assert_has_class_fails_when_class_missing(self) -> None:
        """Test assert_has_class fails when widget doesn't have the class."""
        async with WidgetWithClassesApp().run_test() as pilot:
            widget = pilot.app.query_one("#test-widget")
            with pytest.raises(AssertionError, match="does not have class"):
                assert_has_class(widget, "missing-class")


class TestAssertNotHasClass:
    """Tests for assert_not_has_class utility."""

    @pytest.mark.asyncio
    async def test_assert_not_has_class_passes_when_class_missing(self) -> None:
        """Test assert_not_has_class passes when widget doesn't have the class."""
        async with WidgetWithClassesApp().run_test() as pilot:
            widget = pilot.app.query_one("#test-widget")
            # Should not raise
            assert_not_has_class(widget, "missing-class")

    @pytest.mark.asyncio
    async def test_assert_not_has_class_fails_when_class_exists(self) -> None:
        """Test assert_not_has_class fails when widget has the class."""
        async with WidgetWithClassesApp().run_test() as pilot:
            widget = pilot.app.query_one("#test-widget")
            with pytest.raises(AssertionError, match="has class"):
                assert_not_has_class(widget, "active")


class MultipleWidgetsApp(TUITestApp):
    """Test app with multiple widgets."""

    def compose(self) -> Iterable[Widget]:
        """Compose app with multiple widgets."""
        yield Static("Widget 1", classes="task-item")
        yield Static("Widget 2", classes="task-item")
        yield Static("Widget 3", classes="task-item")
        yield Static("Other widget", classes="other")


class TestAssertWidgetCount:
    """Tests for assert_widget_count utility."""

    @pytest.mark.asyncio
    async def test_assert_widget_count_passes_when_count_matches(self) -> None:
        """Test assert_widget_count passes when count matches."""
        async with MultipleWidgetsApp().run_test() as pilot:
            # Should not raise
            assert_widget_count(pilot.app, ".task-item", 3)

    @pytest.mark.asyncio
    async def test_assert_widget_count_fails_when_count_differs(self) -> None:
        """Test assert_widget_count fails when count doesn't match."""
        async with MultipleWidgetsApp().run_test() as pilot:
            with pytest.raises(AssertionError, match="Expected 5 widgets"):
                assert_widget_count(pilot.app, ".task-item", 5)

    @pytest.mark.asyncio
    async def test_assert_widget_count_with_id_selector(self) -> None:
        """Test assert_widget_count works with ID selector."""
        async with SimpleTUITestApp().run_test() as pilot:
            assert_widget_count(pilot.app, "#test-static", 1)

    @pytest.mark.asyncio
    async def test_assert_widget_count_with_zero_count(self) -> None:
        """Test assert_widget_count works with zero count."""
        async with SimpleTUITestApp().run_test() as pilot:
            assert_widget_count(pilot.app, ".nonexistent", 0)
