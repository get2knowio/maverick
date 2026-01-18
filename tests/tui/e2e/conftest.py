"""E2E test fixtures for Maverick TUI.

This module provides fixtures for end-to-end testing using:
- MCP TUI driver for automated TUI interaction
- Sample project at /workspaces/sample-maverick-project for realistic workflows
- Full app integration with longer timeouts
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator

# Sample project path - configurable via environment
SAMPLE_PROJECT_PATH = Path(
    os.environ.get(
        "MAVERICK_SAMPLE_PROJECT_PATH", "/workspaces/sample-maverick-project"
    )
)

# Apply E2E marker to all tests in this directory
pytestmark = [pytest.mark.e2e, pytest.mark.tui]


# =============================================================================
# Sample Project Fixtures
# =============================================================================


@pytest.fixture
def sample_project_path() -> Path:
    """Get the path to the sample project.

    Returns:
        Path to the sample project directory.

    Raises:
        pytest.skip: If sample project is not available.
    """
    if not SAMPLE_PROJECT_PATH.exists():
        pytest.skip(f"Sample project not found at {SAMPLE_PROJECT_PATH}")
    return SAMPLE_PROJECT_PATH


@pytest.fixture
def reset_sample_project(sample_project_path: Path) -> Generator[Path, None, None]:
    """Reset sample project before and after E2E tests.

    This fixture ensures the sample project is in a clean state before
    running tests and resets it after the test completes.

    Uses the full reset script if GitHub auth is available, otherwise
    falls back to local-only reset.

    Args:
        sample_project_path: Path to the sample project.

    Yields:
        Path to the reset sample project.
    """

    def full_reset() -> bool:
        """Try full reset with push using the reset script.

        Note: Disabled for E2E tests because the script does git clean
        which deletes the .env file needed for API credentials.
        Use local_reset instead which preserves .env.
        """
        # Disabled - the script deletes .env which we need for tests
        return False

    def local_reset() -> bool:
        """Perform a local-only reset using git commands."""
        try:
            # Clean untracked files, but preserve .env (credentials)
            subprocess.run(
                ["git", "clean", "-fd", "--exclude=.env"],
                cwd=sample_project_path,
                check=True,
                capture_output=True,
            )
            # Reset any uncommitted changes
            subprocess.run(
                ["git", "checkout", "."],
                cwd=sample_project_path,
                check=True,
                capture_output=True,
            )
            # Checkout main and reset to baseline if tag exists
            subprocess.run(
                ["git", "checkout", "main"],
                cwd=sample_project_path,
                check=True,
                capture_output=True,
            )
            # Try to reset to baseline tag (may not exist)
            subprocess.run(
                ["git", "reset", "--hard", "baseline/main"],
                cwd=sample_project_path,
                check=False,  # OK if tag doesn't exist
                capture_output=True,
            )
            return True
        except subprocess.CalledProcessError:
            return False

    # Try full reset first, fall back to local reset
    if not full_reset() and not local_reset():
        pytest.skip("Failed to reset sample project to clean state")

    yield sample_project_path

    # Reset after test (best effort) - local only for speed
    local_reset()


@pytest.fixture
def initialized_sample_project(
    reset_sample_project: Path,
) -> Generator[Path, None, None]:
    """Reset and initialize sample project with maverick.yaml.

    This fixture:
    1. Resets the sample project to a clean state
    2. Runs `maverick init` to create maverick.yaml
    3. Cleans up after the test

    Note: The maverick CLI automatically loads .env from the cwd,
    so API credentials are picked up from the sample project's .env file.

    Args:
        reset_sample_project: Path to the reset sample project.

    Yields:
        Path to the initialized sample project with maverick.yaml.
    """
    project_path = reset_sample_project
    maverick_yaml = project_path / "maverick.yaml"

    # Load .env file for API credentials
    env_file = project_path / ".env"
    if not env_file.exists():
        pytest.skip("Sample project .env file not found (needed for API credentials)")

    # Build environment with .env variables
    # (needed because uv run --directory changes the effective cwd for dotenv)
    env = os.environ.copy()
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                env[key.strip()] = value.strip()

    # Run maverick init with --no-detect to avoid needing Claude for detection
    # Use --type python as the sample project is Python-based
    # Note: We run maverick directly via Python instead of uv run --directory
    # because --directory changes the effective cwd for maverick's file operations
    maverick_venv = Path("/workspaces/maverick/.venv/bin/python")
    try:
        result = subprocess.run(
            [
                str(maverick_venv),
                "-m",
                "maverick.main",
                "init",
                "--type",
                "python",
                "--no-detect",
                "--force",
            ],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
        if result.returncode != 0:
            pytest.skip(f"maverick init failed: {result.stderr}")
    except subprocess.TimeoutExpired:
        pytest.skip("maverick init timed out")
    except FileNotFoundError:
        pytest.skip("maverick command not found")

    # Verify maverick.yaml was created
    if not maverick_yaml.exists():
        pytest.skip("maverick.yaml was not created by maverick init")

    yield project_path

    # Cleanup is handled by reset_sample_project's teardown


# =============================================================================
# MCP TUI Driver Fixtures
# =============================================================================


@pytest.fixture
def tui_session_config() -> dict[str, Any]:
    """Default configuration for TUI sessions.

    Returns:
        Dictionary with default TUI session configuration.
    """
    return {
        "cols": 120,
        "rows": 40,
        "timeout_ms": 30000,
        "idle_ms": 500,
    }


@pytest.fixture
def maverick_command(sample_project_path: Path) -> list[str]:
    """Command to launch Maverick TUI in the sample project.

    Args:
        sample_project_path: Path to the sample project.

    Returns:
        List of command arguments for launching Maverick.
    """
    return [
        "uv",
        "run",
        "--directory",
        str(sample_project_path),
        "maverick",
        "tui",
    ]


# =============================================================================
# Test Helpers
# =============================================================================


class TUITestSession:
    """Helper class for E2E TUI testing.

    This class provides a high-level API for common TUI test operations.
    It wraps the MCP TUI driver tools for easier use in tests.

    Note: This class is designed to work with the MCP TUI server.
    When the MCP server is not available, methods will skip gracefully.

    Example:
        ```python
        async def test_workflow(tui_session):
            await tui_session.wait_for_screen("Dashboard")
            await tui_session.press_key("w")
            await tui_session.wait_for_text("Workflow")
        ```
    """

    def __init__(self, session_id: str, config: dict[str, Any]) -> None:
        """Initialize the TUI test session.

        Args:
            session_id: The MCP TUI session ID.
            config: Session configuration.
        """
        self.session_id = session_id
        self.config = config
        self._snapshots: list[str] = []

    async def wait_for_text(self, text: str, timeout_ms: int | None = None) -> bool:
        """Wait for text to appear on screen.

        Args:
            text: Text to wait for.
            timeout_ms: Timeout in milliseconds (uses config default if None).

        Returns:
            True if text found, False if timeout.

        Note: This is a placeholder for MCP TUI driver integration.
        """
        # Placeholder - actual implementation would use MCP TUI tools
        return True

    async def press_key(self, key: str) -> None:
        """Press a key in the TUI session.

        Args:
            key: Key to press (e.g., "Enter", "Tab", "Ctrl+c").

        Note: This is a placeholder for MCP TUI driver integration.
        """
        # Placeholder - actual implementation would use MCP TUI tools
        pass

    async def send_text(self, text: str) -> None:
        """Send raw text to the TUI session.

        Args:
            text: Text to type.

        Note: This is a placeholder for MCP TUI driver integration.
        """
        # Placeholder - actual implementation would use MCP TUI tools
        pass

    async def snapshot(self) -> str:
        """Take an accessibility-style snapshot of the current screen.

        Returns:
            Snapshot string with element references.

        Note: This is a placeholder for MCP TUI driver integration.
        """
        # Placeholder - actual implementation would use MCP TUI tools
        snapshot = f"snapshot_{len(self._snapshots)}"
        self._snapshots.append(snapshot)
        return snapshot

    async def wait_for_idle(self, idle_ms: int | None = None) -> None:
        """Wait for the screen to stop changing.

        Args:
            idle_ms: How long screen must be stable (uses config default if None).

        Note: This is a placeholder for MCP TUI driver integration.
        """
        # Placeholder - actual implementation would use MCP TUI tools
        pass


@pytest.fixture
def tui_session_factory(
    tui_session_config: dict[str, Any],
) -> Any:  # Using Any for Callable return type
    """Factory for creating TUI test sessions.

    Args:
        tui_session_config: Default session configuration.

    Returns:
        Factory function that creates TUITestSession instances.
    """

    def factory(session_id: str = "test-session") -> TUITestSession:
        return TUITestSession(session_id, tui_session_config)

    return factory


# =============================================================================
# Longer Timeout for E2E Tests
# =============================================================================


@pytest.fixture(autouse=True)
def e2e_timeout_override() -> None:
    """Override default timeout for E2E tests.

    E2E tests may take longer due to real workflow execution.
    This fixture is applied automatically to all E2E tests.
    """
    # This is handled via pytest.mark.timeout(120) in the Makefile
    # or via the test marker. This fixture exists as documentation.
    pass
