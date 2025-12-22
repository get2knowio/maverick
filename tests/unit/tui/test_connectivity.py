"""Unit tests for connectivity monitoring utilities."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.tui.utils.connectivity import ConnectivityMonitor, ConnectivityStatus


class TestConnectivityMonitor:
    """Tests for ConnectivityMonitor class."""

    def test_initialization_defaults(self) -> None:
        """Test monitor initializes with correct defaults."""
        monitor = ConnectivityMonitor()
        assert monitor.status == ConnectivityStatus.CONNECTED
        assert monitor.last_check == 0.0

    def test_is_connected_returns_true_when_connected(self) -> None:
        """Test is_connected returns True when status is CONNECTED."""
        monitor = ConnectivityMonitor()
        monitor.status = ConnectivityStatus.CONNECTED
        assert monitor.is_connected() is True

    def test_is_connected_returns_false_when_disconnected(self) -> None:
        """Test is_connected returns False when status is DISCONNECTED."""
        monitor = ConnectivityMonitor()
        monitor.status = ConnectivityStatus.DISCONNECTED
        assert monitor.is_connected() is False

    def test_is_connected_returns_false_when_checking(self) -> None:
        """Test is_connected returns False when status is CHECKING."""
        monitor = ConnectivityMonitor()
        monitor.status = ConnectivityStatus.CHECKING
        assert monitor.is_connected() is False

    def test_time_since_last_check_returns_infinity_when_never_checked(self) -> None:
        """Test time_since_last_check returns infinity when last_check is 0.0."""
        monitor = ConnectivityMonitor()
        assert monitor.time_since_last_check() == float("inf")

    def test_time_since_last_check_returns_elapsed_time(self) -> None:
        """Test time_since_last_check returns elapsed time since last check."""
        monitor = ConnectivityMonitor()
        monitor.last_check = 100.0

        with patch("time.time", return_value=150.0):
            assert monitor.time_since_last_check() == 50.0

    @pytest.mark.asyncio
    async def test_check_connectivity_sets_checking_status(self) -> None:
        """Test check_connectivity sets status to CHECKING during check."""
        monitor = ConnectivityMonitor()

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=AsyncMock(returncode=0, wait=AsyncMock()),
        ):
            # Status should be CHECKING during the check
            task = monitor.check_connectivity()
            # Give it a moment to start
            await asyncio.sleep(0.01)

            # Complete the check
            result = await task
            assert result is True

    @pytest.mark.asyncio
    async def test_check_connectivity_returns_true_when_gh_succeeds(self) -> None:
        """Test check_connectivity returns True when gh auth status succeeds."""
        monitor = ConnectivityMonitor()

        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.wait = AsyncMock()

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await monitor.check_connectivity()

        assert result is True
        assert monitor.status == ConnectivityStatus.CONNECTED
        assert monitor.last_check > 0.0

    @pytest.mark.asyncio
    async def test_check_connectivity_returns_false_when_gh_fails(self) -> None:
        """Test check_connectivity returns False when gh auth status fails."""
        monitor = ConnectivityMonitor()

        mock_proc = AsyncMock()
        mock_proc.returncode = 1
        mock_proc.wait = AsyncMock()

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await monitor.check_connectivity()

        assert result is False
        assert monitor.status == ConnectivityStatus.DISCONNECTED

    @pytest.mark.asyncio
    async def test_check_connectivity_handles_file_not_found(self) -> None:
        """Test check_connectivity handles gh CLI not being installed."""
        monitor = ConnectivityMonitor()

        with patch(
            "asyncio.create_subprocess_exec", side_effect=FileNotFoundError("gh not found")
        ):
            result = await monitor.check_connectivity()

        assert result is False
        assert monitor.status == ConnectivityStatus.DISCONNECTED

    @pytest.mark.asyncio
    async def test_check_connectivity_handles_generic_exception(self) -> None:
        """Test check_connectivity handles unexpected exceptions gracefully."""
        monitor = ConnectivityMonitor()

        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=RuntimeError("Unexpected error"),
        ):
            result = await monitor.check_connectivity()

        assert result is False
        assert monitor.status == ConnectivityStatus.DISCONNECTED

    @pytest.mark.asyncio
    async def test_check_connectivity_updates_last_check_only_on_success(self) -> None:
        """Test check_connectivity updates last_check timestamp only on success."""
        monitor = ConnectivityMonitor()
        initial_last_check = monitor.last_check

        # First check fails
        mock_proc = AsyncMock()
        mock_proc.returncode = 1
        mock_proc.wait = AsyncMock()

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            await monitor.check_connectivity()

        # last_check should not be updated on failure
        assert monitor.last_check == initial_last_check

        # Second check succeeds
        mock_proc.returncode = 0
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            await monitor.check_connectivity()

        # last_check should now be updated
        assert monitor.last_check > initial_last_check
