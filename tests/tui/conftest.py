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

Extended Fixtures:
    - Widget factories for quick test app creation
    - Sample data fixtures for common TUI states
    - Full app pilot fixture for integration tests
    - Performance timing utilities
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, TypeVar, cast

import pytest
from textual.app import App
from textual.widget import Widget

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable, Iterable

    from textual.pilot import Pilot

    from maverick.tui.app import MaverickApp

# Type variable for widget classes
W = TypeVar("W", bound=Widget)


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


# =============================================================================
# Widget Factory Helpers
# =============================================================================


def create_widget_app(
    widget_class: type[W],
    *args: Any,
    **kwargs: Any,
) -> TUITestApp:
    """Create a minimal test app containing a single widget.

    This is a factory function that creates a TUITestApp subclass
    dynamically with the specified widget composed. Useful for quick
    widget testing without creating a custom test app class.

    Args:
        widget_class: The widget class to instantiate and test.
        *args: Positional arguments to pass to the widget constructor.
        **kwargs: Keyword arguments to pass to the widget constructor.

    Returns:
        A TUITestApp instance that will compose the widget.

    Example:
        ```python
        from maverick.tui.widgets.modal import ConfirmDialog

        async def test_confirm_dialog():
            app = create_widget_app(
                ConfirmDialog,
                title="Test",
                message="Are you sure?"
            )
            async with app.run_test() as pilot:
                dialog = pilot.app.query_one(ConfirmDialog)
                assert dialog.title_text == "Test"
        ```
    """

    class DynamicWidgetTestApp(TUITestApp):
        def compose(self) -> Iterable[Widget]:
            yield widget_class(*args, **kwargs)

    return DynamicWidgetTestApp()


# =============================================================================
# Performance Timing Utilities
# =============================================================================


@dataclass
class TimingResult:
    """Result of a timed operation.

    Attributes:
        elapsed_ms: Elapsed time in milliseconds.
        operation: Name of the timed operation.
        passed: Whether the operation met the target time.
        target_ms: Target time in milliseconds.
    """

    elapsed_ms: float
    operation: str
    target_ms: float = 200.0
    passed: bool = field(init=False)

    def __post_init__(self) -> None:
        self.passed = self.elapsed_ms < self.target_ms


class PerformanceTimer:
    """Context manager for timing TUI operations.

    Example:
        ```python
        async with app.run_test() as pilot:
            with PerformanceTimer("screen_push") as timer:
                await pilot.app.push_screen(SettingsScreen())

            assert timer.result.elapsed_ms < 200
        ```
    """

    def __init__(self, operation: str = "operation", target_ms: float = 200.0) -> None:
        """Initialize the performance timer.

        Args:
            operation: Name of the operation being timed.
            target_ms: Target time threshold in milliseconds.
        """
        self.operation = operation
        self.target_ms = target_ms
        self._start: float = 0.0
        self._result: TimingResult | None = None

    def __enter__(self) -> PerformanceTimer:
        self._start = time.perf_counter()
        return self

    def __exit__(self, *args: object) -> None:
        elapsed = (time.perf_counter() - self._start) * 1000
        self._result = TimingResult(
            elapsed_ms=elapsed,
            operation=self.operation,
            target_ms=self.target_ms,
        )

    @property
    def result(self) -> TimingResult:
        """Get the timing result after exiting the context."""
        if self._result is None:
            raise RuntimeError("Timer has not completed yet")
        return self._result


# =============================================================================
# Sample Data Fixtures
# =============================================================================


@pytest.fixture
def sample_workflows() -> list[dict[str, Any]]:
    """Sample workflow data for testing workflow list widgets.

    Returns:
        List of workflow dictionaries with common workflow properties.
    """
    return [
        {
            "branch_name": "feature/user-auth",
            "workflow_type": "fly",
            "status": "completed",
            "started_at": "2025-12-17T10:00:00",
            "completed_at": "2025-12-17T10:30:00",
            "pr_url": "https://github.com/test/repo/pull/1",
        },
        {
            "branch_name": "fix/validation-bug",
            "workflow_type": "refuel",
            "status": "in_progress",
            "started_at": "2025-12-17T11:00:00",
        },
        {
            "branch_name": "feature/dark-mode",
            "workflow_type": "fly",
            "status": "failed",
            "started_at": "2025-12-17T09:00:00",
            "error": "Build failed: TypeScript errors",
        },
    ]


@pytest.fixture
def streaming_state() -> Any:
    """Create a StreamingPanelState with sample entries for testing.

    Returns:
        StreamingPanelState with pre-populated entries.
    """
    from maverick.tui.models import StreamChunkType, StreamingPanelState

    state = StreamingPanelState()
    # Add sample entries using the public API
    from maverick.tui.models import AgentStreamEntry

    entries = [
        AgentStreamEntry(
            timestamp=time.time(),
            step_name="implement_task",
            agent_name="ImplementerAgent",
            text="Starting implementation...",
            chunk_type=StreamChunkType.OUTPUT,
        ),
        AgentStreamEntry(
            timestamp=time.time() + 1,
            step_name="implement_task",
            agent_name="ImplementerAgent",
            text="Analyzing requirements...",
            chunk_type=StreamChunkType.THINKING,
        ),
        AgentStreamEntry(
            timestamp=time.time() + 2,
            step_name="implement_task",
            agent_name="ImplementerAgent",
            text="Writing code...",
            chunk_type=StreamChunkType.OUTPUT,
        ),
    ]
    for entry in entries:
        state.add_entry(entry)
    return state


@pytest.fixture
def sample_review_findings() -> list[dict[str, Any]]:
    """Sample review findings for testing review widgets.

    Returns:
        List of review finding dictionaries.
    """
    return [
        {
            "id": "finding-1",
            "severity": "error",
            "message": "Potential SQL injection vulnerability",
            "file_path": "src/db/queries.py",
            "line": 42,
            "category": "security",
        },
        {
            "id": "finding-2",
            "severity": "warning",
            "message": "Unused import 'os'",
            "file_path": "src/utils/helpers.py",
            "line": 5,
            "category": "code-quality",
        },
        {
            "id": "finding-3",
            "severity": "info",
            "message": "Consider extracting to a helper function",
            "file_path": "src/main.py",
            "line": 100,
            "category": "refactoring",
        },
    ]


@pytest.fixture
def sample_github_issues() -> list[dict[str, Any]]:
    """Sample GitHub issues for testing issue list widgets.

    Returns:
        List of GitHub issue dictionaries.
    """
    return [
        {
            "number": 101,
            "title": "Fix login button not responding",
            "state": "open",
            "labels": ["bug", "priority-high"],
            "assignee": "developer1",
            "created_at": "2025-12-15T08:00:00Z",
        },
        {
            "number": 102,
            "title": "Add dark mode support",
            "state": "open",
            "labels": ["enhancement", "ui"],
            "assignee": None,
            "created_at": "2025-12-16T10:00:00Z",
        },
        {
            "number": 100,
            "title": "Update documentation for v2.0",
            "state": "closed",
            "labels": ["documentation"],
            "assignee": "developer2",
            "created_at": "2025-12-14T14:00:00Z",
            "closed_at": "2025-12-17T09:00:00Z",
        },
    ]


# =============================================================================
# Full App Fixtures
# =============================================================================


@pytest.fixture
async def maverick_pilot() -> AsyncGenerator[Pilot[None], None]:
    """Provide a full MaverickApp pilot for integration testing.

    This fixture creates and runs a complete MaverickApp instance with
    a larger terminal size suitable for full-app testing.

    Yields:
        Pilot instance for the MaverickApp.

    Example:
        ```python
        @pytest.mark.asyncio
        async def test_app_navigation(maverick_pilot):
            # Navigate to settings
            await maverick_pilot.press("ctrl+comma")
            await maverick_pilot.pause()

            # Verify we're on settings screen
            from maverick.tui.screens.settings import SettingsScreen
            assert isinstance(maverick_pilot.app.screen, SettingsScreen)
        ```
    """
    from maverick.tui.app import MaverickApp

    app = MaverickApp()
    async with app.run_test(size=(120, 40)) as pilot:
        yield pilot


@pytest.fixture
def maverick_app() -> MaverickApp:
    """Create a MaverickApp instance without running it.

    Useful when you need to configure the app before running tests.

    Returns:
        Unconfigured MaverickApp instance.
    """
    from maverick.tui.app import MaverickApp

    return MaverickApp()


# =============================================================================
# Modal Testing Fixtures
# =============================================================================


@pytest.fixture
def confirm_dialog_factory() -> Callable[..., Any]:
    """Factory fixture for creating ConfirmDialog instances.

    Returns:
        Callable that creates ConfirmDialog with provided arguments.
    """
    from maverick.tui.widgets.modal import ConfirmDialog

    def factory(
        title: str = "Confirm",
        message: str = "Are you sure?",
        confirm_label: str = "Yes",
        cancel_label: str = "No",
    ) -> ConfirmDialog:
        return ConfirmDialog(
            title=title,
            message=message,
            confirm_label=confirm_label,
            cancel_label=cancel_label,
        )

    return factory


@pytest.fixture
def error_dialog_factory() -> Callable[..., Any]:
    """Factory fixture for creating ErrorDialog instances.

    Returns:
        Callable that creates ErrorDialog with provided arguments.
    """
    from maverick.tui.widgets.modal import ErrorDialog

    def factory(
        message: str = "An error occurred",
        details: str | None = None,
        title: str = "Error",
    ) -> ErrorDialog:
        return ErrorDialog(message=message, details=details, title=title)

    return factory


@pytest.fixture
def input_dialog_factory() -> Callable[..., Any]:
    """Factory fixture for creating InputDialog instances.

    Returns:
        Callable that creates InputDialog with provided arguments.
    """
    from maverick.tui.widgets.modal import InputDialog

    def factory(
        title: str = "Input",
        prompt: str = "Enter value:",
        placeholder: str = "",
        initial_value: str = "",
        password: bool = False,
    ) -> InputDialog:
        return InputDialog(
            title=title,
            prompt=prompt,
            placeholder=placeholder,
            initial_value=initial_value,
            password=password,
        )

    return factory


__all__ = [
    # Base test app classes
    "TUITestApp",
    "ScreenTestApp",
    # Fixtures
    "tui_pilot",
    "maverick_pilot",
    "maverick_app",
    "sample_workflows",
    "streaming_state",
    "sample_review_findings",
    "sample_github_issues",
    "confirm_dialog_factory",
    "error_dialog_factory",
    "input_dialog_factory",
    # Widget factory
    "create_widget_app",
    # Assertion utilities
    "assert_has_class",
    "assert_not_has_class",
    "assert_widget_count",
    # Performance utilities
    "PerformanceTimer",
    "TimingResult",
]

# Apply TUI marker to all tests in this directory
pytestmark = pytest.mark.tui
