"""Visual regression test fixtures.

This module provides fixtures for visual regression testing using
Textual's snapshot capabilities and custom comparison utilities.

Visual tests verify that:
- Widget rendering matches expected snapshots
- Layout adapts correctly to different terminal sizes
- Themes and colors are applied correctly
- Visual consistency across updates
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

# Apply visual marker to all tests
pytestmark = [pytest.mark.visual, pytest.mark.tui]

# Snapshot directory
SNAPSHOTS_DIR = Path(__file__).parent / "snapshots"


# =============================================================================
# Snapshot Management
# =============================================================================


class SnapshotManager:
    """Manages visual regression snapshots.

    This class handles saving, loading, and comparing snapshots
    for visual regression testing.
    """

    def __init__(self, base_dir: Path = SNAPSHOTS_DIR) -> None:
        """Initialize the snapshot manager.

        Args:
            base_dir: Base directory for storing snapshots.
        """
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _get_snapshot_path(self, test_name: str, suffix: str = "") -> Path:
        """Get the path for a snapshot file.

        Args:
            test_name: Name of the test.
            suffix: Optional suffix for the snapshot file.

        Returns:
            Path to the snapshot file.
        """
        safe_name = test_name.replace("::", "_").replace("/", "_")
        filename = f"{safe_name}{suffix}.snapshot"
        return self.base_dir / filename

    def save_snapshot(self, test_name: str, content: str, suffix: str = "") -> Path:
        """Save a snapshot to disk.

        Args:
            test_name: Name of the test.
            content: Snapshot content (text representation).
            suffix: Optional suffix for the snapshot file.

        Returns:
            Path to the saved snapshot.
        """
        path = self._get_snapshot_path(test_name, suffix)
        path.write_text(content, encoding="utf-8")
        return path

    def load_snapshot(self, test_name: str, suffix: str = "") -> str | None:
        """Load a snapshot from disk.

        Args:
            test_name: Name of the test.
            suffix: Optional suffix for the snapshot file.

        Returns:
            Snapshot content, or None if not found.
        """
        path = self._get_snapshot_path(test_name, suffix)
        if path.exists():
            return path.read_text(encoding="utf-8")
        return None

    def compare_snapshots(
        self,
        expected: str,
        actual: str,
        ignore_whitespace: bool = False,
    ) -> tuple[bool, str]:
        """Compare two snapshots.

        Args:
            expected: Expected snapshot content.
            actual: Actual snapshot content.
            ignore_whitespace: Whether to ignore whitespace differences.

        Returns:
            Tuple of (matches, diff_description).
        """
        if ignore_whitespace:
            expected_normalized = " ".join(expected.split())
            actual_normalized = " ".join(actual.split())
            matches = expected_normalized == actual_normalized
        else:
            matches = expected == actual

        if matches:
            return True, ""

        # Generate diff description
        expected_lines = expected.splitlines()
        actual_lines = actual.splitlines()

        diff_lines = []
        max_lines = max(len(expected_lines), len(actual_lines))

        for i in range(max_lines):
            exp_line = expected_lines[i] if i < len(expected_lines) else "<missing>"
            act_line = actual_lines[i] if i < len(actual_lines) else "<missing>"

            if exp_line != act_line:
                diff_lines.append(f"Line {i + 1}:")
                diff_lines.append(f"  Expected: {exp_line!r}")
                diff_lines.append(f"  Actual:   {act_line!r}")

        return False, "\n".join(diff_lines)

    def get_content_hash(self, content: str) -> str:
        """Get a hash of the content for quick comparison.

        Args:
            content: Content to hash.

        Returns:
            SHA256 hash of the content.
        """
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def snapshot_manager() -> SnapshotManager:
    """Provide a SnapshotManager instance.

    Returns:
        Configured SnapshotManager.
    """
    return SnapshotManager()


@pytest.fixture
def snapshot_dir() -> Path:
    """Provide the snapshot directory path.

    Returns:
        Path to the snapshots directory.
    """
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    return SNAPSHOTS_DIR


@pytest.fixture
def assert_snapshot(
    request: pytest.FixtureRequest,
    snapshot_manager: SnapshotManager,
) -> Callable[[str, str], None]:
    """Fixture for asserting snapshot matches.

    This fixture provides a function that compares actual content
    against a stored snapshot, creating the snapshot if it doesn't exist.

    Usage:
        async def test_widget_visual(assert_snapshot):
            content = get_widget_content()
            assert_snapshot(content, "widget-state")

    Args:
        request: Pytest request fixture.
        snapshot_manager: SnapshotManager instance.

    Returns:
        Assertion function.
    """
    test_name = request.node.name

    def _assert_snapshot(actual: str, name: str = "") -> None:
        suffix = f"_{name}" if name else ""
        expected = snapshot_manager.load_snapshot(test_name, suffix)

        if expected is None:
            # First run - create snapshot
            snapshot_manager.save_snapshot(test_name, actual, suffix)
            pytest.skip(f"Created new snapshot for {test_name}{suffix}")
        else:
            matches, diff = snapshot_manager.compare_snapshots(expected, actual)
            if not matches:
                # Save actual for debugging
                actual_path = snapshot_manager.save_snapshot(
                    f"{test_name}_actual", actual, suffix
                )
                pytest.fail(
                    f"Snapshot mismatch for {test_name}{suffix}:\n{diff}\n"
                    f"Actual saved to: {actual_path}"
                )

    return _assert_snapshot


@pytest.fixture
def update_snapshot(
    request: pytest.FixtureRequest,
    snapshot_manager: SnapshotManager,
) -> Callable[[str, str], Path]:
    """Fixture for updating snapshots.

    Use this when you want to force-update a snapshot.

    Args:
        request: Pytest request fixture.
        snapshot_manager: SnapshotManager instance.

    Returns:
        Function that saves a snapshot.
    """
    test_name = request.node.name

    def _update_snapshot(content: str, name: str = "") -> Path:
        suffix = f"_{name}" if name else ""
        return snapshot_manager.save_snapshot(test_name, content, suffix)

    return _update_snapshot


# =============================================================================
# Terminal Size Fixtures
# =============================================================================


@pytest.fixture(
    params=[
        (80, 24, "minimal"),
        (100, 30, "compact"),
        (120, 40, "normal"),
        (160, 50, "wide"),
    ],
    ids=["minimal", "compact", "normal", "wide"],
)
def terminal_size(request: pytest.FixtureRequest) -> tuple[int, int, str]:
    """Parametrized fixture for different terminal sizes.

    Provides common terminal size configurations for responsive testing.

    Yields:
        Tuple of (width, height, size_name).
    """
    return request.param


@pytest.fixture
def minimal_terminal() -> tuple[int, int]:
    """Minimal terminal size (80x24).

    Returns:
        Tuple of (width, height).
    """
    return (80, 24)


@pytest.fixture
def normal_terminal() -> tuple[int, int]:
    """Normal terminal size (120x40).

    Returns:
        Tuple of (width, height).
    """
    return (120, 40)


@pytest.fixture
def wide_terminal() -> tuple[int, int]:
    """Wide terminal size (160x50).

    Returns:
        Tuple of (width, height).
    """
    return (160, 50)


# =============================================================================
# Theme Fixtures
# =============================================================================


@pytest.fixture(params=["dark", "light"], ids=["dark-theme", "light-theme"])
def theme_mode(request: pytest.FixtureRequest) -> str:
    """Parametrized fixture for theme modes.

    Provides both dark and light themes for visual testing.

    Returns:
        Theme mode ("dark" or "light").
    """
    return request.param


# =============================================================================
# Utility Functions
# =============================================================================


def normalize_snapshot(content: str) -> str:
    """Normalize snapshot content for comparison.

    Removes or normalizes elements that may vary between runs:
    - Timestamps
    - Random IDs
    - Elapsed times

    Args:
        content: Raw snapshot content.

    Returns:
        Normalized content.
    """
    import re

    # Normalize timestamps
    content = re.sub(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", "TIMESTAMP", content)

    # Normalize elapsed times
    content = re.sub(r"\d{2}:\d{2}:\d{2}", "HH:MM:SS", content)
    content = re.sub(r"\d+\.\d+s", "X.Xs", content)
    content = re.sub(r"\d+ms", "Xms", content)

    # Normalize random IDs (common patterns)
    content = re.sub(r"id-[a-f0-9]{8,}", "id-XXXXXXXX", content)

    return content


def capture_widget_text(widget: object) -> str:
    """Capture the text representation of a widget.

    Args:
        widget: Textual widget to capture.

    Returns:
        Text representation of the widget.
    """
    if hasattr(widget, "renderable"):
        return str(widget.renderable)
    if hasattr(widget, "render"):
        return str(widget.render())
    return str(widget)


def capture_screen_state(app: object) -> dict[str, Any]:
    """Capture the state of the current screen for comparison.

    Args:
        app: Textual app instance.

    Returns:
        Dictionary with screen state information.
    """
    from typing import cast

    app_any = cast(Any, app)

    state = {
        "screen_type": type(app_any.screen).__name__,
        "screen_stack_size": len(app_any.screen_stack),
        "focused_widget": None,
    }

    if app_any.focused:
        state["focused_widget"] = type(app_any.focused).__name__

    return state
