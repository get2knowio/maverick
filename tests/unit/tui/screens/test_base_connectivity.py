"""Unit tests for MaverickScreen connectivity monitoring integration."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from maverick.tui.screens.base import MaverickScreen


class TestMaverickScreenConnectivity:
    """Tests for MaverickScreen connectivity monitoring."""

    def test_screen_initializes_connectivity_monitor(self) -> None:
        """Test that MaverickScreen initializes a ConnectivityMonitor."""
        screen = MaverickScreen()
        assert hasattr(screen, "_connectivity_monitor")
        assert screen._connectivity_monitor is not None

    @pytest.mark.asyncio
    async def test_on_mount_starts_connectivity_polling(self) -> None:
        """Test that on_mount sets up periodic connectivity checks."""
        screen = MaverickScreen()

        # Mock set_interval to capture the callback
        mock_set_interval = MagicMock()
        screen.set_interval = mock_set_interval

        screen.on_mount()

        # Verify set_interval was called with 30 second interval
        mock_set_interval.assert_called_once()
        args = mock_set_interval.call_args[0]
        assert args[0] == 30.0  # 30 second interval
        assert callable(args[1])  # Callback function

    @pytest.mark.asyncio
    async def test_check_connectivity_calls_monitor(self) -> None:
        """Test that _check_connectivity calls the monitor's check method."""
        screen = MaverickScreen()

        # Mock the connectivity monitor
        screen._connectivity_monitor.check_connectivity = AsyncMock(return_value=True)
        screen._connectivity_monitor.is_connected = MagicMock(return_value=True)

        await screen._check_connectivity()

        screen._connectivity_monitor.check_connectivity.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_connectivity_calls_handler_on_change(self) -> None:
        """Test that connectivity changes trigger the handler."""
        screen = MaverickScreen()

        # Mock the handler
        screen._handle_connectivity_change = MagicMock()

        # Set baseline established (handler only called after baseline)
        screen._connectivity_baseline_established = True

        # Simulate state change from connected to disconnected
        screen._connectivity_monitor.is_connected = MagicMock(return_value=True)
        screen._connectivity_monitor.check_connectivity = AsyncMock(return_value=False)

        await screen._check_connectivity()

        # Handler should be called with False (disconnected)
        screen._handle_connectivity_change.assert_called_once_with(False)

    @pytest.mark.asyncio
    async def test_check_connectivity_no_handler_call_when_no_change(self) -> None:
        """Test that handler is not called when connectivity status doesn't change."""
        screen = MaverickScreen()

        # Mock the handler
        screen._handle_connectivity_change = MagicMock()

        # Simulate no state change (stays connected)
        screen._connectivity_monitor.is_connected = MagicMock(return_value=True)
        screen._connectivity_monitor.check_connectivity = AsyncMock(return_value=True)

        await screen._check_connectivity()

        # Handler should not be called
        screen._handle_connectivity_change.assert_not_called()

    @pytest.mark.asyncio
    async def test_check_connectivity_handles_reconnection(self) -> None:
        """Test that reconnection is properly detected and handled."""
        screen = MaverickScreen()

        # Mock the handler
        screen._handle_connectivity_change = MagicMock()

        # Set baseline established (handler only called after baseline)
        screen._connectivity_baseline_established = True

        # Simulate state change from disconnected to connected
        screen._connectivity_monitor.is_connected = MagicMock(return_value=False)
        screen._connectivity_monitor.check_connectivity = AsyncMock(return_value=True)

        await screen._check_connectivity()

        # Handler should be called with True (reconnected)
        screen._handle_connectivity_change.assert_called_once_with(True)

    def test_default_handle_connectivity_change_is_noop(self) -> None:
        """Test that default handler is a no-op (does not show notifications).

        The connectivity notifications were removed because the underlying
        connectivity detection was unreliable and produced false positives.
        Subclasses can override _handle_connectivity_change if they need
        connectivity-aware behavior.
        """
        screen = MaverickScreen()

        # Mock the app's notify method
        mock_app = MagicMock()

        with patch.object(
            type(screen), "app", new_callable=PropertyMock, return_value=mock_app
        ):
            # Test disconnection - no notification should be sent
            screen._handle_connectivity_change(False)
            mock_app.notify.assert_not_called()

            # Test reconnection - no notification should be sent
            screen._handle_connectivity_change(True)
            mock_app.notify.assert_not_called()


class ConcreteScreen(MaverickScreen):
    """Concrete screen for testing connectivity override."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.connectivity_change_calls: list[bool] = []

    def _handle_connectivity_change(self, connected: bool) -> None:
        """Track connectivity changes."""
        self.connectivity_change_calls.append(connected)
        super()._handle_connectivity_change(connected)


class TestMaverickScreenConnectivityOverride:
    """Tests for overriding connectivity handling in subclasses."""

    def test_subclass_can_override_connectivity_handler(self) -> None:
        """Test that subclasses can override _handle_connectivity_change."""
        screen = ConcreteScreen()
        mock_app = MagicMock()

        with patch.object(
            type(screen), "app", new_callable=PropertyMock, return_value=mock_app
        ):
            # Call handler
            screen._handle_connectivity_change(False)

            # Verify our override was called
            assert screen.connectivity_change_calls == [False]

            # Verify parent is a no-op (no notification called)
            mock_app.notify.assert_not_called()

    @pytest.mark.asyncio
    async def test_subclass_receives_connectivity_changes(self) -> None:
        """Test that subclass connectivity handler receives changes."""
        screen = ConcreteScreen()
        mock_app = MagicMock()

        with patch.object(
            type(screen), "app", new_callable=PropertyMock, return_value=mock_app
        ):
            # Set baseline established (handler only called after baseline)
            screen._connectivity_baseline_established = True

            # Mock connectivity monitor
            screen._connectivity_monitor.is_connected = MagicMock(return_value=True)
            screen._connectivity_monitor.check_connectivity = AsyncMock(
                return_value=False
            )

            await screen._check_connectivity()

            # Verify subclass handler was called
            assert screen.connectivity_change_calls == [False]
