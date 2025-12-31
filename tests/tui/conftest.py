"""TUI test fixtures and utilities.

This module provides pytest fixtures and utilities specific to testing
Textual TUI components, including base test app classes and pilot fixtures.

Test Pattern:
    1. Create a minimal test app that composes the widget/screen under test
    2. Use async with app.run_test() as pilot to get a pilot instance
    3. Query for widgets and assert on their state/behavior

Example:
    ```python
    class MyWidgetTestApp(App):
        def compose(self):
            yield MyWidget()

    @pytest.mark.asyncio
    async def test_widget_behavior():
        async with MyWidgetTestApp().run_test() as pilot:
            widget = pilot.app.query_one(MyWidget)
            assert widget.some_property == expected_value
    ```
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import pytest
from textual.app import App

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from textual.pilot import Pilot


# =============================================================================
# Base Test App Classes
# =============================================================================


class TUITestApp(App[None]):
    """Base class for TUI test applications.

    Provides a minimal Textual app for testing individual widgets and screens.
    Subclass this and override compose() to test specific components.

    Features:
        - Minimal configuration for fast test execution
        - No CSS loading by default (override CSS_PATH if needed)
        - Synchronous compose for simpler test setup

    Example:
        ```python
        class MySidebarTestApp(TUITestApp):
            def compose(self):
                yield Sidebar(id="test-sidebar")

        async def test_sidebar():
            async with MySidebarTestApp().run_test() as pilot:
                sidebar = pilot.app.query_one(Sidebar)
                assert sidebar.id == "test-sidebar"
        ```
    """

    # Override in subclass if CSS is needed for testing
    CSS_PATH = None


class ScreenTestApp(App[None]):
    """Base class for testing Textual screens.

    Use this when you need to test screen-specific behavior like navigation,
    screen lifecycle methods, or screen-level actions.

    Features:
        - Supports push_screen/pop_screen testing
        - Tracks screen stack for navigation tests
        - Minimal configuration for fast execution

    Example:
        ```python
        class MyScreenTestApp(ScreenTestApp):
            def on_mount(self):
                self.push_screen(HomeScreen())

        async def test_screen_navigation():
            async with MyScreenTestApp().run_test() as pilot:
                assert len(pilot.app.screen_stack) == 1
                assert isinstance(pilot.app.screen, HomeScreen)
        ```
    """

    CSS_PATH = None


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
async def tui_pilot() -> AsyncGenerator[Pilot[None], None]:
    """Provide a basic TUI pilot for simple widget testing.

    Returns a pilot instance running a minimal TUITestApp. Use this for
    testing individual widgets without needing to create a custom app class.

    Yields:
        Pilot instance for the test app.

    Example:
        ```python
        @pytest.mark.asyncio
        async def test_basic_widget(tui_pilot):
            # Access app via pilot.app
            assert tui_pilot.app is not None
        ```

    Note:
        For most tests, you should create a custom test app that composes
        the specific widget/screen under test. This fixture is mainly for
        simple utility tests.
    """
    app = TUITestApp()
    async with app.run_test() as pilot:
        yield pilot


# =============================================================================
# Test Utilities
# =============================================================================


def assert_has_class(widget: object, class_name: str) -> None:
    """Assert that a widget has a specific CSS class.

    Args:
        widget: Textual widget to check.
        class_name: CSS class name to check for.

    Raises:
        AssertionError: If widget does not have the class.

    Example:
        ```python
        async with TestApp().run_test() as pilot:
            widget = pilot.app.query_one(MyWidget)
            assert_has_class(widget, "active")
        ```
    """
    # Type checking: widget should have has_class method
    if not hasattr(widget, "has_class"):
        raise TypeError(f"Widget {widget!r} does not have has_class method")
    if not hasattr(widget, "classes"):
        raise TypeError(f"Widget {widget!r} does not have classes attribute")

    # The hasattr checks above ensure these attributes exist at runtime
    widget_any = cast(Any, widget)
    assert widget_any.has_class(class_name), (
        f"Widget {widget!r} does not have class '{class_name}'. "
        f"Classes: {widget_any.classes}"
    )


def assert_not_has_class(widget: object, class_name: str) -> None:
    """Assert that a widget does not have a specific CSS class.

    Args:
        widget: Textual widget to check.
        class_name: CSS class name to check for absence.

    Raises:
        AssertionError: If widget has the class.

    Example:
        ```python
        async with TestApp().run_test() as pilot:
            widget = pilot.app.query_one(MyWidget)
            assert_not_has_class(widget, "hidden")
        ```
    """
    # Type checking: widget should have has_class method
    if not hasattr(widget, "has_class"):
        raise TypeError(f"Widget {widget!r} does not have has_class method")
    if not hasattr(widget, "classes"):
        raise TypeError(f"Widget {widget!r} does not have classes attribute")

    # The hasattr checks above ensure these attributes exist at runtime
    widget_any = cast(Any, widget)
    assert not widget_any.has_class(class_name), (
        f"Widget {widget!r} has class '{class_name}' but should not. "
        f"Classes: {widget_any.classes}"
    )


def assert_widget_count(app: object, selector: str, expected_count: int) -> None:
    """Assert the number of widgets matching a selector.

    Args:
        app: Textual app instance.
        selector: CSS selector to query.
        expected_count: Expected number of matching widgets.

    Raises:
        AssertionError: If count doesn't match.

    Example:
        ```python
        async with TestApp().run_test() as pilot:
            assert_widget_count(pilot.app, ".task-item", 5)
        ```
    """
    # Type checking: app should have query method
    if not hasattr(app, "query"):
        raise TypeError(f"App {app!r} does not have query method")

    # The hasattr check above ensures query method exists at runtime
    app_any = cast(Any, app)
    widgets = app_any.query(selector)
    actual_count = len(widgets)
    assert actual_count == expected_count, (
        f"Expected {expected_count} widgets matching '{selector}', "
        f"but found {actual_count}"
    )


__all__ = [
    "TUITestApp",
    "ScreenTestApp",
    "tui_pilot",
    "assert_has_class",
    "assert_not_has_class",
    "assert_widget_count",
]

# Apply TUI marker to all tests in this directory
pytestmark = pytest.mark.tui
