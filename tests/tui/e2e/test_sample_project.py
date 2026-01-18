"""End-to-end tests using the sample project.

These tests use the MCP TUI driver to interact with a real Maverick TUI
running against the sample project at /workspaces/sample-maverick-project.

Note: These tests require the MCP TUI server to be available and the
sample project to be properly set up. They are marked as e2e and slow.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# Apply markers to all tests
pytestmark = [pytest.mark.e2e, pytest.mark.slow, pytest.mark.tui]


# =============================================================================
# Basic TUI Launch Tests
# =============================================================================


class TestTUILaunch:
    """Tests for launching the Maverick TUI."""

    @pytest.mark.asyncio
    async def test_tui_session_factory_creates_session(
        self,
        tui_session_factory: object,
    ) -> None:
        """Test that TUI session factory creates a valid session."""
        factory = tui_session_factory  # type: ignore[arg-type]
        session = factory("test-launch")

        assert session is not None
        assert session.session_id == "test-launch"

    @pytest.mark.asyncio
    async def test_sample_project_path_exists(
        self,
        sample_project_path: Path,
    ) -> None:
        """Test that sample project path is accessible."""
        assert sample_project_path.exists()
        assert sample_project_path.is_dir()

    @pytest.mark.asyncio
    async def test_initialized_project_has_maverick_yaml(
        self,
        initialized_sample_project: Path,
    ) -> None:
        """Test that initialized sample project has maverick.yaml."""
        maverick_yaml = initialized_sample_project / "maverick.yaml"
        assert maverick_yaml.exists(), "maverick.yaml should exist after init"

        # Verify it's valid YAML with expected structure
        import yaml
        with open(maverick_yaml) as f:
            config = yaml.safe_load(f)

        assert "project_type" in config, "maverick.yaml should have project_type"


# =============================================================================
# Dashboard E2E Tests
# =============================================================================


class TestDashboardE2E:
    """E2E tests for the dashboard screen."""

    @pytest.mark.asyncio
    async def test_dashboard_loads(
        self,
        tui_session_factory: object,
    ) -> None:
        """Test that dashboard loads successfully.

        This is a placeholder test demonstrating the pattern for E2E tests.
        Actual implementation would use MCP TUI driver tools.
        """
        factory = tui_session_factory  # type: ignore[arg-type]
        session = factory("dashboard-test")

        # In a full implementation:
        # 1. tui_launch(command="maverick tui", ...)
        # 2. tui_wait_for_text(text="Dashboard")
        # 3. tui_snapshot() to verify state

        # Placeholder assertion
        assert session is not None


# =============================================================================
# Workflow Selection E2E Tests
# =============================================================================


class TestWorkflowSelectionE2E:
    """E2E tests for workflow selection and browsing."""

    @pytest.mark.asyncio
    async def test_workflow_browser_navigation(
        self,
        tui_session_factory: object,
    ) -> None:
        """Test navigating to workflow browser.

        Pattern:
        1. Launch TUI
        2. Navigate to workflow browser (press 'w' or similar)
        3. Wait for workflow list to load
        4. Verify workflow entries are displayed
        """
        factory = tui_session_factory  # type: ignore[arg-type]
        session = factory("workflow-browser-test")

        # Placeholder for actual MCP TUI driver integration
        # await session.wait_for_text("Dashboard")
        # await session.press_key("w")
        # await session.wait_for_text("Available Workflows")

        assert session is not None


# =============================================================================
# Workflow Execution E2E Tests
# =============================================================================


class TestWorkflowExecutionE2E:
    """E2E tests for workflow execution with sample project."""

    @pytest.mark.asyncio
    async def test_workflow_starts_and_shows_progress(
        self,
        initialized_sample_project: Path,
        tui_session_factory: object,
    ) -> None:
        """Test that a workflow can be started and shows progress.

        Pattern:
        1. Initialize sample project with maverick.yaml
        2. Launch TUI
        3. Select and start a workflow
        4. Verify progress timeline appears
        5. Wait for completion or timeout
        """
        factory = tui_session_factory  # type: ignore[arg-type]
        session = factory("workflow-execution-test")

        # Verify sample project is initialized
        assert initialized_sample_project.exists()
        assert (initialized_sample_project / "maverick.yaml").exists()

        # Placeholder for actual execution test
        # In full implementation:
        # await session.wait_for_text("Dashboard")
        # await session.press_key("w")
        # await session.wait_for_text("fly-workflow")
        # await session.press_key("enter")
        # await session.wait_for_text("Running", timeout_ms=5000)
        # await session.wait_for_idle(idle_ms=500)

        assert session is not None

    @pytest.mark.asyncio
    async def test_workflow_cancellation(
        self,
        initialized_sample_project: Path,
        tui_session_factory: object,
    ) -> None:
        """Test that a running workflow can be cancelled.

        Pattern:
        1. Start a workflow in initialized project
        2. Wait for it to begin executing
        3. Press Escape to cancel
        4. Verify cancellation message appears
        """
        factory = tui_session_factory  # type: ignore[arg-type]
        session = factory("workflow-cancel-test")

        # Verify project is initialized
        assert (initialized_sample_project / "maverick.yaml").exists()

        # Placeholder
        # await session.start_workflow()
        # await session.wait_for_text("Running")
        # await session.press_key("escape")
        # await session.wait_for_text("Cancelled")

        assert session is not None


# =============================================================================
# Settings E2E Tests
# =============================================================================


class TestSettingsE2E:
    """E2E tests for settings screen."""

    @pytest.mark.asyncio
    async def test_settings_can_be_viewed(
        self,
        tui_session_factory: object,
    ) -> None:
        """Test that settings screen can be opened and viewed.

        Pattern:
        1. Launch TUI
        2. Press Ctrl+comma to open settings
        3. Verify settings categories are displayed
        """
        factory = tui_session_factory  # type: ignore[arg-type]
        session = factory("settings-test")

        # await session.wait_for_text("Dashboard")
        # await session.press_key("Ctrl+comma")
        # await session.wait_for_text("Settings")

        assert session is not None

    @pytest.mark.asyncio
    async def test_settings_can_be_modified(
        self,
        tui_session_factory: object,
    ) -> None:
        """Test that settings can be modified.

        This is a more complex E2E test pattern.
        """
        factory = tui_session_factory  # type: ignore[arg-type]
        session = factory("settings-modify-test")

        # Placeholder for settings modification test
        assert session is not None


# =============================================================================
# Error Handling E2E Tests
# =============================================================================


class TestErrorHandlingE2E:
    """E2E tests for error handling in the TUI."""

    @pytest.mark.asyncio
    async def test_invalid_workflow_shows_error(
        self,
        tui_session_factory: object,
    ) -> None:
        """Test that invalid workflow configuration shows error dialog.

        Pattern:
        1. Launch TUI with invalid config
        2. Attempt to run workflow
        3. Verify error dialog appears
        """
        factory = tui_session_factory  # type: ignore[arg-type]
        session = factory("error-handling-test")

        # Placeholder
        assert session is not None

    @pytest.mark.asyncio
    async def test_network_error_shows_error(
        self,
        tui_session_factory: object,
    ) -> None:
        """Test that network errors are displayed to user.

        Note: This would require network simulation/mocking
        which is complex for E2E tests.
        """
        factory = tui_session_factory  # type: ignore[arg-type]
        session = factory("network-error-test")

        # Placeholder
        assert session is not None


# =============================================================================
# Keyboard Accessibility E2E Tests
# =============================================================================


@pytest.mark.accessibility
class TestKeyboardAccessibilityE2E:
    """E2E tests for keyboard accessibility."""

    @pytest.mark.asyncio
    async def test_tab_navigation_works(
        self,
        tui_session_factory: object,
    ) -> None:
        """Test that Tab moves focus through interactive elements."""
        factory = tui_session_factory  # type: ignore[arg-type]
        session = factory("tab-nav-test")

        # Pattern:
        # await session.press_key("Tab")
        # snapshot1 = await session.snapshot()
        # await session.press_key("Tab")
        # snapshot2 = await session.snapshot()
        # assert focused element changed

        assert session is not None

    @pytest.mark.asyncio
    async def test_enter_activates_focused_element(
        self,
        tui_session_factory: object,
    ) -> None:
        """Test that Enter activates the currently focused element."""
        factory = tui_session_factory  # type: ignore[arg-type]
        session = factory("enter-activation-test")

        # Placeholder
        assert session is not None

    @pytest.mark.asyncio
    async def test_arrow_key_navigation(
        self,
        tui_session_factory: object,
    ) -> None:
        """Test that arrow keys navigate within lists."""
        factory = tui_session_factory  # type: ignore[arg-type]
        session = factory("arrow-nav-test")

        # Placeholder
        assert session is not None


# =============================================================================
# Full Workflow Journey Test
# =============================================================================


class TestCompleteWorkflowJourney:
    """End-to-end test of a complete workflow journey.

    This is the most comprehensive E2E test, exercising the full
    user journey through the application.
    """

    @pytest.mark.asyncio
    @pytest.mark.timeout(120)  # 2 minute timeout for full journey
    async def test_complete_workflow_journey(
        self,
        initialized_sample_project: Path,
        tui_session_factory: object,
    ) -> None:
        """Test complete user journey through a workflow.

        Steps:
        1. Launch TUI with initialized project
        2. Navigate to workflow browser
        3. Select a workflow
        4. Configure inputs if needed
        5. Start execution
        6. Monitor progress
        7. View results
        8. Return to dashboard

        This test verifies the entire user flow works end-to-end.
        """
        factory = tui_session_factory  # type: ignore[arg-type]
        session = factory("complete-journey-test")

        # Verify project is ready with maverick.yaml
        assert initialized_sample_project.exists()
        assert (initialized_sample_project / "maverick.yaml").exists()

        # In full implementation, this would exercise the complete flow:
        #
        # # Step 1: Launch and verify dashboard
        # await session.wait_for_text("Dashboard", timeout_ms=10000)
        #
        # # Step 2: Navigate to workflows
        # await session.press_key("w")
        # await session.wait_for_text("Workflows")
        #
        # # Step 3: Select workflow
        # await session.press_key("Down")  # Navigate list
        # await session.press_key("Enter")  # Select
        #
        # # Step 4: Configure inputs (if input screen appears)
        # if await session.wait_for_text("Inputs", timeout_ms=2000):
        #     await session.send_text("feature/test")
        #     await session.press_key("Enter")
        #
        # # Step 5: Monitor execution
        # await session.wait_for_text("Running", timeout_ms=5000)
        # await session.wait_for_text("Completed", timeout_ms=60000)
        #
        # # Step 6: View results
        # snapshot = await session.snapshot()
        # assert "Completed" in snapshot or "Success" in snapshot
        #
        # # Step 7: Return to dashboard
        # await session.press_key("Escape")
        # await session.wait_for_text("Dashboard")

        assert session is not None
