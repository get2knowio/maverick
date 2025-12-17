"""Unit tests for Sidebar widget."""

from __future__ import annotations

import pytest
from textual.app import App
from textual.widgets import Static

from maverick.tui.widgets.sidebar import Sidebar
from maverick.tui.widgets.stage_indicator import StageIndicator

# =============================================================================
# Test App for Sidebar Testing
# =============================================================================


class SidebarTestApp(App):
    """Test app for Sidebar widget testing."""

    def compose(self):
        """Compose the test app."""
        yield Sidebar()


# =============================================================================
# Sidebar Initialization Tests
# =============================================================================


class TestSidebarInitialization:
    """Tests for Sidebar initialization."""

    @pytest.mark.asyncio
    async def test_initialization_defaults(self) -> None:
        """Test Sidebar initializes with default navigation mode."""
        async with SidebarTestApp().run_test() as pilot:
            sidebar = pilot.app.query_one(Sidebar)

            assert sidebar.mode == "navigation"
            assert sidebar._stages == []

    @pytest.mark.asyncio
    async def test_compose_creates_navigation_items(self) -> None:
        """Test compose creates navigation items in default mode."""
        async with SidebarTestApp().run_test() as pilot:
            sidebar = pilot.app.query_one(Sidebar)

            # Check sidebar title
            title = sidebar.query_one(".sidebar-title", Static)
            assert "Navigation" in str(title.render())

            # Check navigation items
            nav_items = sidebar.query(".nav-items .nav-item")
            assert len(nav_items) == 3

            # Verify each navigation item exists
            assert sidebar.query_one("#nav-home", Static) is not None
            assert sidebar.query_one("#nav-workflows", Static) is not None
            assert sidebar.query_one("#nav-settings", Static) is not None


# =============================================================================
# Navigation Mode Tests
# =============================================================================


class TestSidebarNavigationMode:
    """Tests for Sidebar navigation mode."""

    @pytest.mark.asyncio
    async def test_set_navigation_mode_updates_mode(self) -> None:
        """Test set_navigation_mode updates mode property."""
        async with SidebarTestApp().run_test() as pilot:
            sidebar = pilot.app.query_one(Sidebar)

            # First set to workflow mode
            stages = [
                {"name": "setup", "status": "pending"},
                {"name": "build", "status": "pending"},
            ]
            sidebar.set_workflow_mode(stages)
            assert sidebar.mode == "workflow"

            # Then switch back to navigation
            sidebar.set_navigation_mode()
            assert sidebar.mode == "navigation"

    @pytest.mark.asyncio
    async def test_set_navigation_mode_rebuilds_content(self) -> None:
        """Test set_navigation_mode rebuilds content to show navigation."""
        async with SidebarTestApp().run_test() as pilot:
            sidebar = pilot.app.query_one(Sidebar)

            # Set workflow mode first
            stages = [
                {"name": "setup", "status": "pending"},
                {"name": "build", "status": "pending"},
            ]
            sidebar.set_workflow_mode(stages)

            # Switch to navigation mode
            sidebar.set_navigation_mode()
            await pilot.pause()

            # Verify navigation items are present
            title = sidebar.query_one(".sidebar-title", Static)
            assert "Navigation" in str(title.render())

            nav_items = sidebar.query(".nav-items .nav-item")
            assert len(nav_items) == 3

    @pytest.mark.asyncio
    async def test_set_navigation_mode_clears_stages(self) -> None:
        """Test set_navigation_mode clears workflow stages."""
        async with SidebarTestApp().run_test() as pilot:
            sidebar = pilot.app.query_one(Sidebar)

            # Set workflow mode with stages
            stages = [
                {"name": "setup", "status": "pending"},
                {"name": "build", "status": "pending"},
            ]
            sidebar.set_workflow_mode(stages)

            # Switch to navigation mode
            sidebar.set_navigation_mode()
            await pilot.pause()

            # Verify no stage indicators exist
            stage_indicators = sidebar.query(StageIndicator)
            assert len(stage_indicators) == 0


# =============================================================================
# Workflow Mode Tests
# =============================================================================


class TestSidebarWorkflowMode:
    """Tests for Sidebar workflow mode."""

    @pytest.mark.asyncio
    async def test_set_workflow_mode_updates_mode(self) -> None:
        """Test set_workflow_mode updates mode property."""
        async with SidebarTestApp().run_test() as pilot:
            sidebar = pilot.app.query_one(Sidebar)

            stages = [
                {"name": "setup", "status": "pending"},
                {"name": "build", "status": "pending"},
            ]
            sidebar.set_workflow_mode(stages)

            assert sidebar.mode == "workflow"
            assert sidebar._stages == stages

    @pytest.mark.asyncio
    async def test_set_workflow_mode_creates_stage_indicators(self) -> None:
        """Test set_workflow_mode creates StageIndicator widgets."""
        async with SidebarTestApp().run_test() as pilot:
            sidebar = pilot.app.query_one(Sidebar)

            stages = [
                {"name": "setup", "status": "pending"},
                {"name": "build", "status": "active"},
                {"name": "test", "status": "completed"},
            ]
            sidebar.set_workflow_mode(stages)
            await pilot.pause()

            # Verify title
            title = sidebar.query_one(".sidebar-title", Static)
            assert "Workflow Stages" in str(title.render())

            # Verify stage indicators
            stage_indicators = sidebar.query(StageIndicator)
            assert len(stage_indicators) == 3

            # Check each stage
            setup_stage = sidebar.query_one("#stage-setup", StageIndicator)
            assert setup_stage.name == "setup"
            assert setup_stage.status == "pending"

            build_stage = sidebar.query_one("#stage-build", StageIndicator)
            assert build_stage.name == "build"
            assert build_stage.status == "active"

            test_stage = sidebar.query_one("#stage-test", StageIndicator)
            assert test_stage.name == "test"
            assert test_stage.status == "completed"

    @pytest.mark.asyncio
    async def test_set_workflow_mode_with_display_names(self) -> None:
        """Test set_workflow_mode uses display_name when provided."""
        async with SidebarTestApp().run_test() as pilot:
            sidebar = pilot.app.query_one(Sidebar)

            stages = [
                {"name": "setup", "display_name": "Setup Phase", "status": "pending"},
                {"name": "build", "display_name": "Build Phase", "status": "pending"},
            ]
            sidebar.set_workflow_mode(stages)

            # Check that display names are used
            setup_stage = sidebar.query_one("#stage-setup", StageIndicator)
            assert setup_stage.name == "Setup Phase"

            build_stage = sidebar.query_one("#stage-build", StageIndicator)
            assert build_stage.name == "Build Phase"

    @pytest.mark.asyncio
    async def test_set_workflow_mode_with_empty_stages(self) -> None:
        """Test set_workflow_mode with empty stages list."""
        async with SidebarTestApp().run_test() as pilot:
            sidebar = pilot.app.query_one(Sidebar)

            sidebar.set_workflow_mode([])
            await pilot.pause()

            assert sidebar.mode == "workflow"
            assert sidebar._stages == []

            # Verify title but no stages
            title = sidebar.query_one(".sidebar-title", Static)
            assert "Workflow Stages" in str(title.render())

            stage_indicators = sidebar.query(StageIndicator)
            assert len(stage_indicators) == 0


# =============================================================================
# Stage Status Update Tests
# =============================================================================


class TestSidebarStageStatusUpdate:
    """Tests for updating stage status."""

    @pytest.mark.asyncio
    async def test_update_stage_status_updates_indicator(self) -> None:
        """Test update_stage_status updates the StageIndicator status."""
        async with SidebarTestApp().run_test() as pilot:
            sidebar = pilot.app.query_one(Sidebar)

            stages = [
                {"name": "setup", "status": "pending"},
                {"name": "build", "status": "pending"},
            ]
            sidebar.set_workflow_mode(stages)

            # Update stage status
            sidebar.update_stage_status("setup", "active")

            # Verify the indicator was updated
            setup_stage = sidebar.query_one("#stage-setup", StageIndicator)
            assert setup_stage.status == "active"

    @pytest.mark.asyncio
    async def test_update_stage_status_persists_in_stages_list(self) -> None:
        """Test update_stage_status persists status in _stages."""
        async with SidebarTestApp().run_test() as pilot:
            sidebar = pilot.app.query_one(Sidebar)

            stages = [
                {"name": "setup", "status": "pending"},
                {"name": "build", "status": "pending"},
            ]
            sidebar.set_workflow_mode(stages)

            # Update stage status
            sidebar.update_stage_status("setup", "completed")

            # Verify it was persisted in _stages
            assert sidebar._stages[0]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_update_stage_status_with_nonexistent_stage(self) -> None:
        """Test update_stage_status with non-existent stage fails gracefully."""
        async with SidebarTestApp().run_test() as pilot:
            sidebar = pilot.app.query_one(Sidebar)

            stages = [
                {"name": "setup", "status": "pending"},
            ]
            sidebar.set_workflow_mode(stages)

            # Should not raise exception
            sidebar.update_stage_status("nonexistent", "active")

            # Original stage unchanged
            setup_stage = sidebar.query_one("#stage-setup", StageIndicator)
            assert setup_stage.status == "pending"

    @pytest.mark.asyncio
    async def test_update_stage_status_in_navigation_mode(self) -> None:
        """Test update_stage_status in navigation mode fails gracefully."""
        async with SidebarTestApp().run_test() as pilot:
            sidebar = pilot.app.query_one(Sidebar)

            # In navigation mode by default
            assert sidebar.mode == "navigation"

            # Should not raise exception
            sidebar.update_stage_status("setup", "active")

    @pytest.mark.asyncio
    async def test_update_stage_status_multiple_stages(self) -> None:
        """Test update_stage_status updates only the specified stage."""
        async with SidebarTestApp().run_test() as pilot:
            sidebar = pilot.app.query_one(Sidebar)

            stages = [
                {"name": "setup", "status": "pending"},
                {"name": "build", "status": "pending"},
                {"name": "test", "status": "pending"},
            ]
            sidebar.set_workflow_mode(stages)

            # Update middle stage
            sidebar.update_stage_status("build", "active")

            # Verify only build was updated
            setup_stage = sidebar.query_one("#stage-setup", StageIndicator)
            assert setup_stage.status == "pending"

            build_stage = sidebar.query_one("#stage-build", StageIndicator)
            assert build_stage.status == "active"

            test_stage = sidebar.query_one("#stage-test", StageIndicator)
            assert test_stage.status == "pending"

    @pytest.mark.asyncio
    async def test_update_stage_status_with_display_name(self) -> None:
        """Test update_stage_status works with stages that have display names."""
        async with SidebarTestApp().run_test() as pilot:
            sidebar = pilot.app.query_one(Sidebar)

            stages = [
                {"name": "setup", "display_name": "Setup Phase", "status": "pending"},
            ]
            sidebar.set_workflow_mode(stages)

            # Update using internal name, not display name
            sidebar.update_stage_status("setup", "active")

            # Verify the indicator was updated
            setup_stage = sidebar.query_one("#stage-setup", StageIndicator)
            assert setup_stage.status == "active"
            assert setup_stage.name == "Setup Phase"


# =============================================================================
# Mode Switching Tests
# =============================================================================


class TestSidebarModeSwitching:
    """Tests for switching between modes."""

    @pytest.mark.asyncio
    async def test_switching_from_workflow_to_navigation_and_back(self) -> None:
        """Test switching between workflow and navigation modes."""
        async with SidebarTestApp().run_test() as pilot:
            sidebar = pilot.app.query_one(Sidebar)

            # Start in navigation
            assert sidebar.mode == "navigation"

            # Switch to workflow
            stages = [
                {"name": "setup", "status": "pending"},
                {"name": "build", "status": "active"},
            ]
            sidebar.set_workflow_mode(stages)
            await pilot.pause()
            assert sidebar.mode == "workflow"

            # Verify workflow content
            stage_indicators = sidebar.query(StageIndicator)
            assert len(stage_indicators) == 2

            # Switch back to navigation
            sidebar.set_navigation_mode()
            await pilot.pause()
            assert sidebar.mode == "navigation"

            # Verify navigation content
            nav_items = sidebar.query(".nav-items .nav-item")
            assert len(nav_items) == 3

            # Switch to workflow again
            sidebar.set_workflow_mode(stages)
            await pilot.pause()
            assert sidebar.mode == "workflow"

            # Verify workflow content again
            stage_indicators = sidebar.query(StageIndicator)
            assert len(stage_indicators) == 2

    @pytest.mark.asyncio
    async def test_updating_stages_persists_after_mode_switch(self) -> None:
        """Test that updating stages and switching modes works correctly."""
        async with SidebarTestApp().run_test() as pilot:
            sidebar = pilot.app.query_one(Sidebar)

            # Set workflow mode
            stages = [
                {"name": "setup", "status": "pending"},
                {"name": "build", "status": "pending"},
            ]
            sidebar.set_workflow_mode(stages)

            # Update a stage
            sidebar.update_stage_status("setup", "completed")

            # Switch to navigation and back
            sidebar.set_navigation_mode()
            await pilot.pause()
            sidebar.set_workflow_mode(stages)
            await pilot.pause()

            # Since we modified the same stages list reference via update_stage_status,
            # the updated status should persist
            setup_stage = sidebar.query_one("#stage-setup", StageIndicator)
            assert setup_stage.status == "completed"
