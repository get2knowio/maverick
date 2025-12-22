"""Unit tests for FlyScreen and RefuelScreen connectivity handling."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from maverick.tui.screens.fly import FlyScreen
from maverick.tui.screens.refuel import RefuelScreen


class TestFlyScreenConnectivity:
    """Tests for FlyScreen connectivity handling."""

    def test_fly_screen_initializes_with_workflow_paused_false(self) -> None:
        """Test FlyScreen initializes with workflow_paused as False."""
        screen = FlyScreen()
        assert screen.workflow_paused is False

    def test_handle_connectivity_change_when_workflow_not_running(self) -> None:
        """Test connectivity handler does nothing when workflow is not running."""
        screen = FlyScreen()
        mock_app = MagicMock()
        screen.is_workflow_running = False

        initial_paused = screen.workflow_paused

        with patch.object(
            type(screen), "app", new_callable=PropertyMock, return_value=mock_app
        ):
            # Simulate disconnection
            screen._handle_connectivity_change(False)

        # workflow_paused should not change when workflow is not running
        assert screen.workflow_paused == initial_paused

        # Parent notification should still be called
        mock_app.notify.assert_called()

    def test_handle_connectivity_change_pauses_workflow_on_disconnect(self) -> None:
        """Test that workflow is paused when connectivity is lost."""
        screen = FlyScreen()
        mock_app = MagicMock()
        screen.is_workflow_running = True
        screen.workflow_paused = False

        with patch.object(
            type(screen), "app", new_callable=PropertyMock, return_value=mock_app
        ):
            # Simulate disconnection
            screen._handle_connectivity_change(False)

        assert screen.workflow_paused is True
        mock_app.notify.assert_called()

    def test_handle_connectivity_change_resumes_workflow_on_reconnect(self) -> None:
        """Test that workflow is resumed when connectivity is restored."""
        screen = FlyScreen()
        mock_app = MagicMock()
        screen.is_workflow_running = True
        screen.workflow_paused = True  # Workflow was paused

        with patch.object(
            type(screen), "app", new_callable=PropertyMock, return_value=mock_app
        ):
            # Simulate reconnection
            screen._handle_connectivity_change(True)

        assert screen.workflow_paused is False
        mock_app.notify.assert_called()

    def test_handle_connectivity_change_no_resume_if_not_paused(self) -> None:
        """Test that workflow_paused stays False if it wasn't paused before."""
        screen = FlyScreen()
        mock_app = MagicMock()
        screen.is_workflow_running = True
        screen.workflow_paused = False  # Workflow wasn't paused

        with patch.object(
            type(screen), "app", new_callable=PropertyMock, return_value=mock_app
        ):
            # Simulate reconnection
            screen._handle_connectivity_change(True)

        # Should remain False
        assert screen.workflow_paused is False

    @pytest.mark.asyncio
    async def test_connectivity_integration_with_check(self) -> None:
        """Test full connectivity check integration with FlyScreen."""
        screen = FlyScreen()
        mock_app = MagicMock()
        screen.is_workflow_running = True

        with patch.object(
            type(screen), "app", new_callable=PropertyMock, return_value=mock_app
        ):
            # Mock the connectivity monitor
            screen._connectivity_monitor.is_connected = MagicMock(return_value=True)
            screen._connectivity_monitor.check_connectivity = AsyncMock(
                return_value=False
            )

            # Perform connectivity check
            await screen._check_connectivity()

        # Workflow should be paused
        assert screen.workflow_paused is True
        mock_app.notify.assert_called()


class TestRefuelScreenConnectivity:
    """Tests for RefuelScreen connectivity handling."""

    def test_refuel_screen_initializes_with_workflow_paused_false(self) -> None:
        """Test RefuelScreen initializes with workflow_paused as False."""
        screen = RefuelScreen()
        assert screen.workflow_paused is False

    def test_handle_connectivity_change_when_workflow_not_running(self) -> None:
        """Test connectivity handler does nothing when workflow is not running."""
        screen = RefuelScreen()
        mock_app = MagicMock()
        screen.is_workflow_running = False

        initial_paused = screen.workflow_paused

        with patch.object(
            type(screen), "app", new_callable=PropertyMock, return_value=mock_app
        ):
            # Simulate disconnection
            screen._handle_connectivity_change(False)

        # workflow_paused should not change when workflow is not running
        assert screen.workflow_paused == initial_paused

        # Parent notification should still be called
        mock_app.notify.assert_called()

    def test_handle_connectivity_change_pauses_workflow_on_disconnect(self) -> None:
        """Test that workflow is paused when connectivity is lost."""
        screen = RefuelScreen()
        mock_app = MagicMock()
        screen.is_workflow_running = True
        screen.workflow_paused = False

        with patch.object(
            type(screen), "app", new_callable=PropertyMock, return_value=mock_app
        ):
            # Simulate disconnection
            screen._handle_connectivity_change(False)

        assert screen.workflow_paused is True
        mock_app.notify.assert_called()

    def test_handle_connectivity_change_resumes_workflow_on_reconnect(self) -> None:
        """Test that workflow is resumed when connectivity is restored."""
        screen = RefuelScreen()
        mock_app = MagicMock()
        screen.is_workflow_running = True
        screen.workflow_paused = True  # Workflow was paused

        with patch.object(
            type(screen), "app", new_callable=PropertyMock, return_value=mock_app
        ):
            # Simulate reconnection
            screen._handle_connectivity_change(True)

        assert screen.workflow_paused is False
        mock_app.notify.assert_called()

    def test_handle_connectivity_change_no_resume_if_not_paused(self) -> None:
        """Test that workflow_paused stays False if it wasn't paused before."""
        screen = RefuelScreen()
        mock_app = MagicMock()
        screen.is_workflow_running = True
        screen.workflow_paused = False  # Workflow wasn't paused

        with patch.object(
            type(screen), "app", new_callable=PropertyMock, return_value=mock_app
        ):
            # Simulate reconnection
            screen._handle_connectivity_change(True)

        # Should remain False
        assert screen.workflow_paused is False

    @pytest.mark.asyncio
    async def test_connectivity_integration_with_check(self) -> None:
        """Test full connectivity check integration with RefuelScreen."""
        screen = RefuelScreen()
        mock_app = MagicMock()
        screen.is_workflow_running = True

        with patch.object(
            type(screen), "app", new_callable=PropertyMock, return_value=mock_app
        ):
            # Mock the connectivity monitor
            screen._connectivity_monitor.is_connected = MagicMock(return_value=True)
            screen._connectivity_monitor.check_connectivity = AsyncMock(
                return_value=False
            )

            # Perform connectivity check
            await screen._check_connectivity()

        # Workflow should be paused
        assert screen.workflow_paused is True
        mock_app.notify.assert_called()
