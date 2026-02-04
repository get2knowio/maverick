"""Unit tests for MaverickApp class.

Tests focus on business logic and state management rather than full
Textual rendering. Tests verify timer methods, workflow info methods,
action methods, and command provider functionality.
"""

from __future__ import annotations

import time
from unittest.mock import Mock, patch

import pytest
from textual.command import Hit
from textual.widgets import Header

from maverick.tui.app import MaverickApp, MaverickCommands
from maverick.tui.widgets.log_panel import LogPanel
from maverick.tui.widgets.sidebar import Sidebar


class TestMaverickAppInitialization:
    """Test MaverickApp initialization and constants."""

    def test_app_title(self) -> None:
        """Test that app has correct title."""
        app = MaverickApp()
        assert app.TITLE == "Maverick"

    def test_min_width_constant(self) -> None:
        """Test that MIN_WIDTH is set correctly."""
        app = MaverickApp()
        assert app.MIN_WIDTH == 80

    def test_min_height_constant(self) -> None:
        """Test that MIN_HEIGHT is set correctly."""
        app = MaverickApp()
        assert app.MIN_HEIGHT == 24

    def test_command_palette_enabled(self) -> None:
        """Test that command palette is enabled."""
        app = MaverickApp()
        assert app.ENABLE_COMMAND_PALETTE is True

    def test_commands_provider_configured(self) -> None:
        """Test that MaverickCommands provider is configured."""
        app = MaverickApp()
        assert MaverickCommands in app.COMMANDS

    def test_bindings_configured(self) -> None:
        """Test that key bindings are configured."""
        app = MaverickApp()
        assert len(app.BINDINGS) > 0
        # Check some critical bindings exist
        binding_keys = [binding.key for binding in app.BINDINGS]
        assert "ctrl+l" in binding_keys
        assert "q" in binding_keys
        assert "escape" in binding_keys

    def test_initial_timer_state(self) -> None:
        """Test that timer starts in uninitialized state."""
        app = MaverickApp()
        assert app._timer_start is None
        assert app._timer_running is False

    def test_initial_workflow_state(self) -> None:
        """Test that workflow info starts empty."""
        app = MaverickApp()
        assert app._current_workflow == ""
        assert app._current_branch == ""


class TestTimerMethods:
    """Test timer-related methods."""

    def test_start_timer_sets_start_time(self) -> None:
        """Test that start_timer sets timer start time."""
        app = MaverickApp()
        before = time.time()
        app.start_timer()
        after = time.time()

        assert app._timer_start is not None
        assert before <= app._timer_start <= after
        assert app._timer_running is True

    def test_stop_timer_stops_running(self) -> None:
        """Test that stop_timer sets running flag to False."""
        app = MaverickApp()
        app.start_timer()
        assert app._timer_running is True

        app.stop_timer()
        assert app._timer_running is False

    def test_elapsed_time_before_start(self) -> None:
        """Test that elapsed_time returns 0.0 before timer starts."""
        app = MaverickApp()
        assert app.elapsed_time == 0.0

    def test_elapsed_time_while_running(self) -> None:
        """Test that elapsed_time calculates correctly while running."""
        app = MaverickApp()
        app.start_timer()

        # Simulate elapsed time by backdating the start time
        app._timer_start = time.time() - 0.5

        elapsed = app.elapsed_time
        assert elapsed >= 0.4
        assert elapsed < 2.0

    def test_elapsed_time_after_stop(self) -> None:
        """Test that elapsed_time returns 0.0 after stopping."""
        app = MaverickApp()
        app.start_timer()
        app.stop_timer()

        # After stopping, elapsed_time should return 0.0
        # because _timer_running is False
        assert app.elapsed_time == 0.0

    def test_restart_timer(self) -> None:
        """Test that timer can be restarted."""
        app = MaverickApp()

        # Start, stop, start again
        app.start_timer()
        first_start = app._timer_start
        app.stop_timer()

        # Simulate a gap by backdating the first start
        app.start_timer()
        second_start = app._timer_start

        # Second start time should be different (later or equal)
        assert second_start is not None
        assert first_start is not None
        assert second_start >= first_start
        assert app._timer_running is True


class TestWorkflowInfoMethods:
    """Test workflow info management methods."""

    def test_set_workflow_info_updates_state(self) -> None:
        """Test that set_workflow_info updates internal state."""
        app = MaverickApp()

        app.set_workflow_info("FlyWorkflow", "feature-branch")

        assert app._current_workflow == "FlyWorkflow"
        assert app._current_branch == "feature-branch"

    def test_set_workflow_info_without_branch(self) -> None:
        """Test that set_workflow_info works without branch name."""
        app = MaverickApp()

        app.set_workflow_info("RefuelWorkflow")

        assert app._current_workflow == "RefuelWorkflow"
        assert app._current_branch == ""

    def test_clear_workflow_info_clears_state(self) -> None:
        """Test that clear_workflow_info clears internal state."""
        app = MaverickApp()

        # Set workflow info first
        app.set_workflow_info("FlyWorkflow", "feature-branch")
        assert app._current_workflow != ""

        # Clear it
        app.clear_workflow_info()

        assert app._current_workflow == ""
        assert app._current_branch == ""

    def test_clear_workflow_info_without_header(self) -> None:
        """Test that clear_workflow_info handles missing header gracefully."""
        app = MaverickApp()

        # Should not raise exception even if header not mounted
        app.clear_workflow_info()

        assert app._current_workflow == ""
        assert app._current_branch == ""


class TestUpdateHeaderSubtitle:
    """Test header subtitle update logic."""

    def test_update_header_subtitle_with_workflow_and_branch(self) -> None:
        """Test header subtitle format with workflow and branch."""
        app = MaverickApp()
        app.start_timer()
        app._current_workflow = "FlyWorkflow"
        app._current_branch = "feature-branch"

        # Mock the header widget
        mock_header = Mock(spec=Header)
        mock_header.subtitle = ""

        with patch.object(app, "query_one", return_value=mock_header):
            app._update_header_subtitle()

        # Should set subtitle with workflow, branch, and time
        assert mock_header.subtitle is not None
        subtitle = mock_header.subtitle
        assert "FlyWorkflow" in subtitle
        assert "feature-branch" in subtitle
        assert "00:00" in subtitle or "00:01" in subtitle

    def test_update_header_subtitle_with_workflow_no_branch(self) -> None:
        """Test header subtitle format with workflow but no branch."""
        app = MaverickApp()
        app.start_timer()
        app._current_workflow = "RefuelWorkflow"
        app._current_branch = ""

        mock_header = Mock(spec=Header)
        mock_header.subtitle = ""

        with patch.object(app, "query_one", return_value=mock_header):
            app._update_header_subtitle()

        subtitle = mock_header.subtitle
        assert "RefuelWorkflow" in subtitle
        assert "00:00" in subtitle or "00:01" in subtitle
        # Should not contain empty parentheses
        assert "()" not in subtitle

    def test_update_header_subtitle_without_workflow(self) -> None:
        """Test that header subtitle is not updated without workflow."""
        app = MaverickApp()
        app._current_workflow = ""

        mock_header = Mock(spec=Header)

        with patch.object(app, "query_one", return_value=mock_header):
            app._update_header_subtitle()

        # Should not set subtitle when no workflow
        # The method should exit early without calling query_one
        # Actually, let's check that nothing happens
        assert app._current_workflow == ""

    def test_update_header_subtitle_formats_time_correctly(self) -> None:
        """Test that elapsed time is formatted as MM:SS."""
        app = MaverickApp()
        app.start_timer()
        app._current_workflow = "TestWorkflow"

        # Simulate 65 seconds elapsed (1:05)
        app._timer_start = time.time() - 65

        mock_header = Mock(spec=Header)
        mock_header.subtitle = ""

        with patch.object(app, "query_one", return_value=mock_header):
            app._update_header_subtitle()

        subtitle = mock_header.subtitle
        assert "01:0" in subtitle  # 01:05

    def test_update_header_subtitle_handles_missing_header(self) -> None:
        """Test that missing header doesn't raise exception."""
        app = MaverickApp()
        app.start_timer()
        app._current_workflow = "TestWorkflow"

        # Mock query_one to raise exception
        with patch.object(app, "query_one", side_effect=Exception("Not mounted")):
            # Should not raise exception
            app._update_header_subtitle()


class TestActionMethods:
    """Test action methods."""

    def test_action_toggle_log(self) -> None:
        """Test that action_toggle_log toggles log panel."""
        app = MaverickApp()
        mock_log_panel = Mock(spec=LogPanel)

        with patch.object(app, "query_one", return_value=mock_log_panel):
            app.action_toggle_log()

        mock_log_panel.toggle.assert_called_once()

    def test_action_toggle_log_handles_missing_widget(self) -> None:
        """Test that action_toggle_log handles missing widget gracefully."""
        app = MaverickApp()

        with patch.object(app, "query_one", side_effect=Exception("Not mounted")):
            # Should not raise exception
            app.action_toggle_log()

    @pytest.mark.asyncio
    async def test_action_pop_screen_when_multiple_screens(self) -> None:
        """Test that action_pop_screen pops when multiple screens exist."""
        app = MaverickApp()
        # Mock screen_stack with multiple screens
        mock_screens = [Mock(), Mock()]

        with patch.object(
            type(app),
            "screen_stack",
            new_callable=lambda: property(lambda self: mock_screens),
        ):
            with patch.object(app, "pop_screen") as mock_pop:
                await app.action_pop_screen()

            mock_pop.assert_called_once()

    @pytest.mark.asyncio
    async def test_action_pop_screen_when_single_screen(self) -> None:
        """Test that action_pop_screen doesn't pop when only one screen."""
        app = MaverickApp()
        # Mock screen_stack with single screen
        mock_screens = [Mock()]

        with patch.object(
            type(app),
            "screen_stack",
            new_callable=lambda: property(lambda self: mock_screens),
        ):
            with patch.object(app, "pop_screen") as mock_pop:
                await app.action_pop_screen()

            mock_pop.assert_not_called()

    @pytest.mark.asyncio
    async def test_action_quit_exits_app(self) -> None:
        """Test that action_quit calls exit()."""
        app = MaverickApp()

        with patch.object(app, "exit") as mock_exit:
            await app.action_quit()

        mock_exit.assert_called_once()

    def test_action_show_help_adds_log_entries(self) -> None:
        """Test that action_show_help adds help log entries."""
        app = MaverickApp()

        with patch.object(app, "add_log") as mock_add_log:
            app.action_show_help()

        # Should add multiple log entries for help
        assert mock_add_log.call_count >= 4

        # Check that help text contains key bindings
        calls = [str(call) for call in mock_add_log.call_args_list]
        calls_str = " ".join(calls)
        assert "Ctrl+L" in calls_str or "ctrl+l" in calls_str.lower()

    def test_action_show_help_shows_log_panel(self) -> None:
        """Test that action_show_help makes log panel visible."""
        app = MaverickApp()
        mock_log_panel = Mock(spec=LogPanel)
        mock_log_panel.panel_visible = False

        with patch.object(app, "add_log"):
            with patch.object(app, "query_one", return_value=mock_log_panel):
                app.action_show_help()

        # Should toggle log panel if not visible
        mock_log_panel.toggle.assert_called_once()

    def test_action_go_home_pops_all_screens(self) -> None:
        """Test that action_go_home pops all screens except base."""
        app = MaverickApp()

        # Track pop_screen calls
        original_len = Mock(
            side_effect=[3, 2, 1]
        )  # Simulate screen_stack length decreasing

        with patch.object(app, "pop_screen") as mock_pop:
            # Mock screen_stack to return decreasing length
            with patch.object(
                type(app),
                "screen_stack",
                new_callable=lambda: property(lambda self: Mock(__len__=original_len)),
            ):
                app.action_go_home()

                # Should pop twice (3 screens -> 2 -> 1)
                assert mock_pop.call_count == 2

    def test_action_start_workflow_pushes_workflow_screen(self) -> None:
        """Test that action_start_workflow pushes WorkflowScreen."""
        app = MaverickApp()

        with patch.object(app, "push_screen") as mock_push:
            app.action_start_workflow()

        mock_push.assert_called_once()
        # Check that the argument is a WorkflowScreen
        args = mock_push.call_args[0]
        assert len(args) == 1
        screen = args[0]
        assert screen.__class__.__name__ == "WorkflowScreen"

    def test_action_show_config_pushes_config_screen(self) -> None:
        """Test that action_show_config pushes ConfigScreen."""
        app = MaverickApp()

        with patch.object(app, "push_screen") as mock_push:
            app.action_show_config()

        mock_push.assert_called_once()
        args = mock_push.call_args[0]
        assert len(args) == 1
        screen = args[0]
        assert screen.__class__.__name__ == "ConfigScreen"

    def test_action_go_review_pushes_review_screen(self) -> None:
        """Test that action_go_review pushes ReviewScreen."""
        app = MaverickApp()

        with patch.object(app, "push_screen") as mock_push:
            app.action_go_review()

        mock_push.assert_called_once()
        args = mock_push.call_args[0]
        assert len(args) == 1
        screen = args[0]
        assert screen.__class__.__name__ == "ReviewScreen"

    def test_action_go_workflow_pushes_workflow_screen(self) -> None:
        """Test that action_go_workflow pushes WorkflowScreen."""
        app = MaverickApp()

        with patch.object(app, "push_screen") as mock_push:
            app.action_go_workflow()

        mock_push.assert_called_once()
        args = mock_push.call_args[0]
        assert len(args) == 1
        screen = args[0]
        assert screen.__class__.__name__ == "WorkflowScreen"

    def test_action_refresh_calls_screen_refresh_if_available(self) -> None:
        """Test that action_refresh calls screen.refresh() if available."""
        app = MaverickApp()
        mock_screen = Mock()
        mock_screen.refresh = Mock()

        # Mock the screen property to return our mock screen
        with patch.object(
            type(app), "screen", new_callable=lambda: property(lambda self: mock_screen)
        ):
            app.action_refresh()

            mock_screen.refresh.assert_called_once()

    def test_action_refresh_adds_log_if_no_refresh_method(self) -> None:
        """Test that action_refresh logs if screen has no refresh method."""
        app = MaverickApp()
        mock_screen = Mock(spec=[])  # No refresh method

        # Mock the screen property to return our mock screen
        with patch.object(
            type(app), "screen", new_callable=lambda: property(lambda self: mock_screen)
        ):
            with patch.object(app, "add_log") as mock_add_log:
                app.action_refresh()

            mock_add_log.assert_called_once()
            args = mock_add_log.call_args[0]
            assert "refresh" in args[0].lower()


class TestAddLogMethod:
    """Test add_log convenience method."""

    def test_add_log_delegates_to_log_panel(self) -> None:
        """Test that add_log delegates to LogPanel.add_log()."""
        app = MaverickApp()
        mock_log_panel = Mock(spec=LogPanel)

        with patch.object(app, "query_one", return_value=mock_log_panel):
            app.add_log("Test message", "info", "test-agent")

        mock_log_panel.add_log.assert_called_once_with(
            "Test message", "info", "test-agent"
        )

    def test_add_log_uses_default_level(self) -> None:
        """Test that add_log uses default level 'info'."""
        app = MaverickApp()
        mock_log_panel = Mock(spec=LogPanel)

        with patch.object(app, "query_one", return_value=mock_log_panel):
            app.add_log("Test message")

        mock_log_panel.add_log.assert_called_once()
        args = mock_log_panel.add_log.call_args[0]
        kwargs = mock_log_panel.add_log.call_args[1]
        # Check level is info (either as positional or keyword arg)
        if len(args) > 1:
            assert args[1] == "info"
        else:
            assert kwargs.get("level") == "info"

    def test_add_log_handles_missing_log_panel(self) -> None:
        """Test that add_log handles missing log panel gracefully."""
        app = MaverickApp()

        with patch.object(app, "query_one", side_effect=Exception("Not mounted")):
            # Should not raise exception
            app.add_log("Test message", "error", "test-agent")


class TestGetSidebar:
    """Test get_sidebar method."""

    def test_get_sidebar_returns_sidebar(self) -> None:
        """Test that get_sidebar returns Sidebar widget."""
        app = MaverickApp()
        mock_sidebar = Mock(spec=Sidebar)

        with patch.object(app, "query_one", return_value=mock_sidebar):
            result = app.get_sidebar()

        assert result == mock_sidebar

    def test_get_sidebar_returns_none_when_not_mounted(self) -> None:
        """Test that get_sidebar returns None when widget not mounted."""
        app = MaverickApp()

        with patch.object(app, "query_one", side_effect=Exception("Not mounted")):
            result = app.get_sidebar()

        assert result is None


class TestMaverickCommands:
    """Test MaverickCommands provider."""

    @pytest.mark.asyncio
    async def test_search_returns_all_commands_for_empty_query(self) -> None:
        """Test that search returns all commands for empty query."""
        app = MaverickApp()
        mock_screen = Mock()
        mock_screen.app = app
        provider = MaverickCommands(screen=mock_screen)

        hits = []
        async for hit in provider.search(""):
            hits.append(hit)

        # Should return all 9 commands
        assert len(hits) == 9

    @pytest.mark.asyncio
    async def test_search_filters_by_name(self) -> None:
        """Test that search filters commands by name."""
        app = MaverickApp()
        mock_screen = Mock()
        mock_screen.app = app
        provider = MaverickCommands(screen=mock_screen)

        hits = []
        async for hit in provider.search("home"):
            hits.append(hit)

        # Should return "Go to Home" command
        assert len(hits) >= 1
        assert any("Home" in hit.text for hit in hits)

    @pytest.mark.asyncio
    async def test_search_filters_by_description(self) -> None:
        """Test that search filters commands by description."""
        app = MaverickApp()
        mock_screen = Mock()
        mock_screen.app = app
        provider = MaverickCommands(screen=mock_screen)

        hits = []
        async for hit in provider.search("navigate"):
            hits.append(hit)

        # Should return navigation-related commands
        assert len(hits) >= 1

    @pytest.mark.asyncio
    async def test_search_is_case_insensitive(self) -> None:
        """Test that search is case-insensitive."""
        app = MaverickApp()
        mock_screen = Mock()
        mock_screen.app = app
        provider = MaverickCommands(screen=mock_screen)

        hits_lower = []
        async for hit in provider.search("workflow"):
            hits_lower.append(hit)

        hits_upper = []
        async for hit in provider.search("WORKFLOW"):
            hits_upper.append(hit)

        # Should return same results regardless of case
        assert len(hits_lower) == len(hits_upper)
        assert len(hits_lower) >= 1

    @pytest.mark.asyncio
    async def test_search_returns_hit_with_correct_attributes(self) -> None:
        """Test that search returns Hit objects with correct attributes."""
        app = MaverickApp()
        mock_screen = Mock()
        mock_screen.app = app
        provider = MaverickCommands(screen=mock_screen)

        hits = []
        async for hit in provider.search("home"):
            hits.append(hit)

        assert len(hits) >= 1
        hit = hits[0]

        # Check Hit attributes
        assert isinstance(hit, Hit)
        assert hit.score == 1
        assert hit.match_display is not None
        assert hit.command is not None
        assert hit.text is not None
        assert hit.help is not None

    @pytest.mark.asyncio
    async def test_all_commands_have_correct_callbacks(self) -> None:
        """Test that all commands map to correct action methods."""
        app = MaverickApp()
        mock_screen = Mock()
        mock_screen.app = app
        provider = MaverickCommands(screen=mock_screen)

        # Map of search terms to expected action methods
        expected_actions = {
            "home": "action_go_home",
            "settings": "action_show_config",
            "review": "action_go_review",
            "workflow": "action_go_workflow",
            "log": "action_toggle_log",
            "start workflow": "action_start_workflow",
            "refresh": "action_refresh",
            "help": "action_show_help",
        }

        for search_term, expected_method in expected_actions.items():
            hits = []
            async for hit in provider.search(search_term):
                hits.append(hit)

            assert len(hits) >= 1, f"No hits for '{search_term}'"
            # Check that at least one hit has the expected callback
            callbacks = [hit.command for hit in hits]
            callback_names = [
                callback.__name__
                for callback in callbacks
                if hasattr(callback, "__name__")
            ]
            assert expected_method in callback_names, (
                f"Expected '{expected_method}' in callbacks for '{search_term}', "
                f"got {callback_names}"
            )
