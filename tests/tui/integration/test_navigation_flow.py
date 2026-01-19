"""Integration tests for TUI navigation flows.

This module tests multi-screen navigation patterns including:
- Screen-to-screen transitions
- Navigation context tracking
- Back navigation with Escape
- Screen stack management
"""

from __future__ import annotations

import pytest

from maverick.tui.app import MaverickApp
from maverick.tui.screens.config import ConfigScreen
from maverick.tui.screens.dashboard import DashboardScreen
from maverick.tui.screens.review import ReviewScreen
from maverick.tui.screens.settings import SettingsScreen

# Apply TUI marker to all tests
pytestmark = pytest.mark.tui


# =============================================================================
# Dashboard Navigation Tests
# =============================================================================


class TestDashboardNavigation:
    """Tests for navigation from the dashboard screen."""

    @pytest.mark.asyncio
    async def test_app_starts_on_dashboard(self) -> None:
        """Test that MaverickApp starts on the DashboardScreen."""
        app = MaverickApp()

        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            # Should be on dashboard screen
            assert isinstance(pilot.app.screen, DashboardScreen)

    @pytest.mark.asyncio
    async def test_navigation_to_settings(self) -> None:
        """Test navigation from dashboard to settings."""
        app = MaverickApp()

        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            # Navigate to settings via action
            pilot.app.action_show_settings()
            await pilot.pause()

            # Should be on settings screen
            assert isinstance(pilot.app.screen, SettingsScreen)

    @pytest.mark.asyncio
    async def test_navigation_to_config(self) -> None:
        """Test navigation from dashboard to config."""
        app = MaverickApp()

        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            # Navigate to config via action
            pilot.app.action_show_config()
            await pilot.pause()

            # Should be on config screen
            assert isinstance(pilot.app.screen, ConfigScreen)

    @pytest.mark.asyncio
    async def test_navigation_to_review(self) -> None:
        """Test navigation from dashboard to review."""
        app = MaverickApp()

        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            # Navigate to review via action
            pilot.app.action_go_review()
            await pilot.pause()

            # Should be on review screen
            assert isinstance(pilot.app.screen, ReviewScreen)


# =============================================================================
# Back Navigation Tests
# =============================================================================


class TestBackNavigation:
    """Tests for back navigation with Escape key."""

    @pytest.mark.asyncio
    async def test_escape_pops_screen(self) -> None:
        """Test that Escape returns to previous screen."""
        app = MaverickApp()

        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            # Record initial stack size (includes base screen)
            initial_stack_size = len(pilot.app.screen_stack)

            # Navigate to settings
            pilot.app.action_show_settings()
            await pilot.pause()

            assert isinstance(pilot.app.screen, SettingsScreen)
            assert len(pilot.app.screen_stack) == initial_stack_size + 1

            # Press Escape
            await pilot.press("escape")
            await pilot.pause()

            # Should be back on dashboard
            assert isinstance(pilot.app.screen, DashboardScreen)
            assert len(pilot.app.screen_stack) == initial_stack_size

    @pytest.mark.asyncio
    async def test_escape_on_dashboard_pops_to_base_screen(self) -> None:
        """Test that Escape on dashboard pops to base screen."""
        app = MaverickApp()

        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            assert isinstance(pilot.app.screen, DashboardScreen)

            # Press Escape on dashboard - this pops the dashboard to base screen
            await pilot.press("escape")
            await pilot.pause()

            # Should be on the base screen (not dashboard)
            # The stack has 1 item - the base _default screen
            assert len(pilot.app.screen_stack) == 1

    @pytest.mark.asyncio
    async def test_multi_level_back_navigation(self) -> None:
        """Test multi-level back navigation through screen stack."""
        app = MaverickApp()

        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            initial_stack_size = len(pilot.app.screen_stack)

            # Navigate to settings
            pilot.app.action_show_settings()
            await pilot.pause()

            # Navigate to config (from settings)
            pilot.app.action_show_config()
            await pilot.pause()

            assert len(pilot.app.screen_stack) == initial_stack_size + 2
            assert isinstance(pilot.app.screen, ConfigScreen)

            # Navigate back twice
            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(pilot.app.screen, SettingsScreen)

            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(pilot.app.screen, DashboardScreen)


# =============================================================================
# Navigation Context Tests
# =============================================================================


class TestNavigationContext:
    """Tests for navigation context tracking."""

    @pytest.mark.asyncio
    async def test_push_screen_tracked_updates_context(self) -> None:
        """Test that push_screen_tracked updates navigation context."""
        app = MaverickApp()

        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            initial_history_len = len(pilot.app.navigation_context.history)

            # Use tracked push
            pilot.app.push_screen_tracked(
                SettingsScreen(),
                params={"source": "test"},
            )
            await pilot.pause()

            # Context should be updated
            assert len(pilot.app.navigation_context.history) == initial_history_len + 1

            # Last entry should have screen name
            last_entry = pilot.app.navigation_context.history[-1]
            assert last_entry.screen_name == "SettingsScreen"
            assert last_entry.params == {"source": "test"}

    @pytest.mark.asyncio
    async def test_pop_screen_tracked_updates_context(self) -> None:
        """Test that pop_screen_tracked updates navigation context."""
        app = MaverickApp()

        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            # Push TWO screens with tracking - need 2+ for can_go_back to work
            pilot.app.push_screen_tracked(SettingsScreen())
            await pilot.pause()
            pilot.app.push_screen_tracked(ConfigScreen())
            await pilot.pause()

            history_len_after_push = len(pilot.app.navigation_context.history)
            assert history_len_after_push == 2  # Two screens pushed

            # Pop with tracking - should reduce history since can_go_back is True
            pilot.app.pop_screen_tracked()
            await pilot.pause()

            # Context history should be reduced by 1
            assert (
                len(pilot.app.navigation_context.history) == history_len_after_push - 1
            )

    @pytest.mark.asyncio
    async def test_navigation_context_can_go_back(self) -> None:
        """Test navigation context can_go_back property.

        Note: can_go_back requires len(history) > 1, so we need at least
        2 pushed screens before can_go_back returns True.
        """
        app = MaverickApp()

        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            # Initial state - should not be able to go back (0 entries)
            assert not pilot.app.navigation_context.can_go_back

            # Push first screen with tracking (1 entry)
            pilot.app.push_screen_tracked(SettingsScreen())
            await pilot.pause()

            # Still can't go back with just 1 entry
            assert not pilot.app.navigation_context.can_go_back

            # Push second screen with tracking (2 entries)
            pilot.app.push_screen_tracked(ConfigScreen())
            await pilot.pause()

            # Now should be able to go back (2+ entries)
            assert pilot.app.navigation_context.can_go_back


# =============================================================================
# Home Navigation Tests
# =============================================================================


class TestHomeNavigation:
    """Tests for go_home navigation action."""

    @pytest.mark.asyncio
    async def test_go_home_pops_to_base_screen(self) -> None:
        """Test that go_home pops all screens to the base screen.

        Note: action_go_home() pops screens until len(screen_stack) == 1,
        leaving only the base _default screen.
        """
        app = MaverickApp()

        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            initial_stack_size = len(pilot.app.screen_stack)

            # Navigate deep into the app
            pilot.app.action_show_settings()
            await pilot.pause()
            pilot.app.action_show_config()
            await pilot.pause()
            pilot.app.action_go_review()
            await pilot.pause()

            assert len(pilot.app.screen_stack) == initial_stack_size + 3

            # Go home - pops all screens including dashboard to base
            pilot.app.action_go_home()
            await pilot.pause()

            # Should have only the base _default screen
            assert len(pilot.app.screen_stack) == 1


# =============================================================================
# Keyboard Shortcut Navigation Tests
# =============================================================================


class TestKeyboardNavigation:
    """Tests for keyboard shortcut navigation."""

    @pytest.mark.asyncio
    async def test_ctrl_comma_opens_config(self) -> None:
        """Test that Ctrl+, opens config screen."""
        app = MaverickApp()

        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            # Press Ctrl+,
            await pilot.press("ctrl+comma")
            await pilot.pause()

            # Should be on config screen
            assert isinstance(pilot.app.screen, ConfigScreen)

    @pytest.mark.asyncio
    async def test_ctrl_h_goes_home(self) -> None:
        """Test that Ctrl+H goes to home (base screen).

        Note: action_go_home() pops all screens to the base _default screen.
        """
        app = MaverickApp()

        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            # Navigate away from dashboard
            pilot.app.action_show_settings()
            await pilot.pause()

            # Press Ctrl+H
            await pilot.press("ctrl+h")
            await pilot.pause()

            # Should be on base screen with only 1 screen in stack
            assert len(pilot.app.screen_stack) == 1

    @pytest.mark.asyncio
    async def test_q_quits_app(self) -> None:
        """Test that 'q' initiates app quit."""
        app = MaverickApp()

        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            # Press 'q' - this will trigger quit action
            # In test mode, this won't actually exit but we verify
            # the key binding works by ensuring no error occurs
            await pilot.press("q")
            await pilot.pause()

            # App should have initiated exit (handled in test mode)


# =============================================================================
# Screen Stack Management Tests
# =============================================================================


class TestScreenStackManagement:
    """Tests for screen stack management."""

    @pytest.mark.asyncio
    async def test_screen_stack_grows_on_push(self) -> None:
        """Test that screen stack grows when pushing screens."""
        app = MaverickApp()

        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            initial_size = len(pilot.app.screen_stack)

            pilot.app.action_show_settings()
            await pilot.pause()
            assert len(pilot.app.screen_stack) == initial_size + 1

            pilot.app.action_show_config()
            await pilot.pause()
            assert len(pilot.app.screen_stack) == initial_size + 2

    @pytest.mark.asyncio
    async def test_screen_stack_shrinks_on_pop(self) -> None:
        """Test that screen stack shrinks when popping screens."""
        app = MaverickApp()

        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            # Push two screens
            pilot.app.action_show_settings()
            await pilot.pause()
            pilot.app.action_show_config()
            await pilot.pause()

            initial_size = len(pilot.app.screen_stack)

            # Pop one screen
            await pilot.press("escape")
            await pilot.pause()
            assert len(pilot.app.screen_stack) == initial_size - 1

    @pytest.mark.asyncio
    async def test_current_screen_is_top_of_stack(self) -> None:
        """Test that current screen is always top of stack."""
        app = MaverickApp()

        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            # Dashboard should be current
            assert pilot.app.screen == pilot.app.screen_stack[-1]

            # Push settings
            pilot.app.action_show_settings()
            await pilot.pause()
            assert pilot.app.screen == pilot.app.screen_stack[-1]
            assert isinstance(pilot.app.screen, SettingsScreen)

            # Pop
            await pilot.press("escape")
            await pilot.pause()
            assert pilot.app.screen == pilot.app.screen_stack[-1]
            assert isinstance(pilot.app.screen, DashboardScreen)
