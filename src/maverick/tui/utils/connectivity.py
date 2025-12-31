"""Network connectivity utilities for Maverick TUI.

This module provides utilities for monitoring network connectivity and GitHub API
reachability. It enables the TUI to gracefully handle network interruptions by
detecting connectivity loss and allowing workflows to pause/resume accordingly.

Features:
    - Async connectivity checking via GitHub CLI
    - Status tracking (connected/disconnected/checking)
    - Timestamp of last successful check
    - Silent failure handling

Example:
    ```python
    monitor = ConnectivityMonitor()

    # Check connectivity
    is_connected = await monitor.check_connectivity()

    if is_connected:
        logger.info(f"Status: {monitor.status}")
    else:
        logger.warning("GitHub API is unreachable")
    ```
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum

from maverick.tui.services import check_github_connection

__all__ = ["ConnectivityStatus", "ConnectivityMonitor"]


class ConnectivityStatus(str, Enum):
    """Network connectivity status enumeration.

    Attributes:
        CONNECTED: GitHub API is reachable and authenticated.
        DISCONNECTED: GitHub API is unreachable or authentication failed.
        CHECKING: Connectivity check is in progress.
    """

    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    CHECKING = "checking"


@dataclass
class ConnectivityMonitor:
    """Monitors network connectivity for GitHub API.

    Tracks the current connectivity status and provides async methods for
    checking GitHub API reachability via the GitHub CLI (`gh auth status`).

    The monitor maintains the last check timestamp to enable polling strategies
    and rate limiting.

    Attributes:
        status: Current connectivity status.
        last_check: Timestamp (seconds since epoch) of last successful check.
            Defaults to 0.0 (never checked).

    Example:
        ```python
        # Create monitor
        monitor = ConnectivityMonitor()

        # Check connectivity
        if await monitor.check_connectivity():
            print("Connected to GitHub")
        else:
            print(f"Not connected: {monitor.status}")

        # Check time since last check
        time_since_check = time.time() - monitor.last_check
        if time_since_check > 60:
            # Re-check after 60 seconds
            await monitor.check_connectivity()
        ```
    """

    status: ConnectivityStatus = field(default=ConnectivityStatus.CONNECTED)
    last_check: float = field(default=0.0)

    async def check_connectivity(self) -> bool:
        """Check if GitHub API is reachable.

        Executes `gh auth status` to verify GitHub CLI authentication and API
        reachability. Updates the monitor's status and last_check timestamp.

        The check runs asynchronously and does not block the TUI event loop.
        Errors are caught silently to prevent connectivity checks from crashing
        the application.

        Returns:
            True if connected (gh auth status exits with 0), False otherwise.

        Side Effects:
            Updates `status` to CONNECTED or DISCONNECTED.
            Updates `last_check` to current timestamp on success.

        Example:
            ```python
            monitor = ConnectivityMonitor()

            # Check before starting workflow
            if not await monitor.check_connectivity():
                self.show_error("Cannot start workflow: GitHub is unreachable")
                return

            # Status is now CONNECTED or DISCONNECTED
            print(f"Current status: {monitor.status}")
            ```
        """
        # Set status to checking
        self.status = ConnectivityStatus.CHECKING

        try:
            # Use the service function for connectivity checking
            result = await check_github_connection()

            # Update status based on result
            if result.connected:
                self.status = ConnectivityStatus.CONNECTED
                self.last_check = time.time()
                return True
            else:
                self.status = ConnectivityStatus.DISCONNECTED
                return False

        except Exception:
            # Any error (permission denied, timeout, etc.)
            self.status = ConnectivityStatus.DISCONNECTED
            return False

    def is_connected(self) -> bool:
        """Check if currently connected.

        Returns:
            True if status is CONNECTED, False otherwise.

        Note:
            This returns the cached status without performing a network check.
            Call `check_connectivity()` to perform an actual check.

        Example:
            ```python
            monitor = ConnectivityMonitor()
            await monitor.check_connectivity()

            # Use cached status
            if monitor.is_connected():
                start_workflow()
            ```
        """
        return self.status == ConnectivityStatus.CONNECTED

    def time_since_last_check(self) -> float:
        """Get time elapsed since last successful check.

        Returns:
            Seconds since last check, or infinity if never checked.

        Example:
            ```python
            monitor = ConnectivityMonitor()
            await monitor.check_connectivity()

            # Later...
            if monitor.time_since_last_check() > 60:
                # Re-check after 60 seconds
                await monitor.check_connectivity()
            ```
        """
        if self.last_check == 0.0:
            return float("inf")
        return time.time() - self.last_check
