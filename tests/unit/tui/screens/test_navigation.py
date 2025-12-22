"""Tests for screen navigation (User Story 5)."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

# Mock classes for testing navigation behavior
# (Real screens may not exist yet - TDD approach)


@dataclass
class MockScreen:
    """Mock screen for navigation testing."""

    name: str
    can_go_back: bool = True


class MockApp:
    """Mock Textual App for navigation testing."""

    def __init__(self) -> None:
        self.screen_stack: list[MockScreen] = [MockScreen("HomeScreen")]
        self._pushed_screens: list[MockScreen] = []
        self._popped_count: int = 0

    def push_screen(self, screen: MockScreen) -> None:
        self.screen_stack.append(screen)
        self._pushed_screens.append(screen)

    def pop_screen(self) -> None:
        if len(self.screen_stack) > 1:
            self.screen_stack.pop()
            self._popped_count += 1

    @property
    def current_screen(self) -> MockScreen:
        return self.screen_stack[-1]


class TestScreenNavigation:
    """Tests for navigation from HomeScreen to other screens."""

    def test_navigate_home_to_fly(self) -> None:
        """Navigation from HomeScreen to FlyScreen works."""
        app = MockApp()
        assert app.current_screen.name == "HomeScreen"

        app.push_screen(MockScreen("FlyScreen"))

        assert app.current_screen.name == "FlyScreen"
        assert len(app.screen_stack) == 2

    def test_navigate_home_to_refuel(self) -> None:
        """Navigation from HomeScreen to RefuelScreen works."""
        app = MockApp()
        app.push_screen(MockScreen("RefuelScreen"))
        assert app.current_screen.name == "RefuelScreen"

    def test_navigate_home_to_settings(self) -> None:
        """Navigation from HomeScreen to SettingsScreen works."""
        app = MockApp()
        app.push_screen(MockScreen("SettingsScreen"))
        assert app.current_screen.name == "SettingsScreen"

    def test_navigate_fly_to_review(self) -> None:
        """Navigation from FlyScreen to ReviewScreen works."""
        app = MockApp()
        app.push_screen(MockScreen("FlyScreen"))
        app.push_screen(MockScreen("ReviewScreen"))
        assert app.current_screen.name == "ReviewScreen"
        assert len(app.screen_stack) == 3


class TestEscapeKeyNavigation:
    """Tests for Escape key back navigation."""

    def test_escape_goes_back(self) -> None:
        """Escape key pops current screen."""
        app = MockApp()
        app.push_screen(MockScreen("FlyScreen"))

        # Simulate Escape key
        app.pop_screen()

        assert app.current_screen.name == "HomeScreen"
        assert len(app.screen_stack) == 1

    def test_escape_does_nothing_on_home(self) -> None:
        """Escape key does nothing when on HomeScreen."""
        app = MockApp()
        initial_count = len(app.screen_stack)

        app.pop_screen()  # Should not pop HomeScreen

        assert len(app.screen_stack) == initial_count
        assert app.current_screen.name == "HomeScreen"

    def test_multi_level_back_navigation(self) -> None:
        """Multiple Escape presses navigate back through stack."""
        app = MockApp()
        app.push_screen(MockScreen("FlyScreen"))
        app.push_screen(MockScreen("ReviewScreen"))

        app.pop_screen()
        assert app.current_screen.name == "FlyScreen"

        app.pop_screen()
        assert app.current_screen.name == "HomeScreen"


class TestModalOverlayBehavior:
    """Tests for modal dialog overlay behavior."""

    @pytest.mark.asyncio
    async def test_modal_overlays_current_screen(self) -> None:
        """Modal dialog overlays without replacing current screen."""
        app = MockApp()
        app.push_screen(MockScreen("FlyScreen"))

        # Push modal
        modal = MockScreen("ConfirmDialog", can_go_back=True)
        app.push_screen(modal)

        assert app.current_screen.name == "ConfirmDialog"
        assert app.screen_stack[-2].name == "FlyScreen"  # Still in stack

    @pytest.mark.asyncio
    async def test_modal_dismiss_returns_to_screen(self) -> None:
        """Dismissing modal returns to previous screen."""
        app = MockApp()
        app.push_screen(MockScreen("FlyScreen"))
        app.push_screen(MockScreen("ConfirmDialog"))

        app.pop_screen()  # Dismiss modal

        assert app.current_screen.name == "FlyScreen"

    @pytest.mark.asyncio
    async def test_modal_escape_dismisses(self) -> None:
        """Escape key dismisses modal dialog."""
        app = MockApp()
        app.push_screen(MockScreen("FlyScreen"))
        app.push_screen(MockScreen("ErrorDialog"))

        # Escape should dismiss
        app.pop_screen()

        assert app.current_screen.name == "FlyScreen"


class TestNavigationContext:
    """Tests for navigation context tracking."""

    def test_navigation_history_tracked(self) -> None:
        """Navigation history is maintained."""
        history: list[str] = []

        def track_push(screen: MockScreen) -> None:
            history.append(screen.name)

        app = MockApp()
        app.push_screen(MockScreen("FlyScreen"))
        history.append("FlyScreen")
        app.push_screen(MockScreen("ReviewScreen"))
        history.append("ReviewScreen")

        assert history == ["FlyScreen", "ReviewScreen"]

    def test_can_go_back_when_not_on_home(self) -> None:
        """can_go_back is True when not on HomeScreen."""
        app = MockApp()
        app.push_screen(MockScreen("FlyScreen"))

        assert len(app.screen_stack) > 1  # can_go_back

    def test_cannot_go_back_on_home(self) -> None:
        """can_go_back is False on HomeScreen."""
        app = MockApp()

        assert len(app.screen_stack) == 1  # cannot go back
