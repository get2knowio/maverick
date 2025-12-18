"""Unit tests for StageIndicator widget."""

from __future__ import annotations

import pytest
from textual.app import App

from maverick.tui.widgets.stage_indicator import StageIndicator

# =============================================================================
# Test App for StageIndicator Testing
# =============================================================================


class StageIndicatorTestApp(App):
    """Test app for StageIndicator widget testing."""

    def compose(self):
        """Compose the test app."""
        yield StageIndicator(name="test-stage", status="pending")


# =============================================================================
# StageIndicator Initialization Tests
# =============================================================================


class TestStageIndicatorInitialization:
    """Tests for StageIndicator initialization."""

    @pytest.mark.asyncio
    async def test_initialization_with_required_parameters(self) -> None:
        """Test StageIndicator initializes with required parameters."""
        async with StageIndicatorTestApp().run_test() as pilot:
            indicator = pilot.app.query_one(StageIndicator)

            assert indicator.name == "test-stage"
            assert indicator.status == "pending"

    @pytest.mark.asyncio
    async def test_initialization_with_custom_id(self) -> None:
        """Test StageIndicator initializes with custom id."""

        class CustomIdApp(App):
            def compose(self):
                yield StageIndicator(name="test", status="pending", id="custom-id")

        async with CustomIdApp().run_test() as pilot:
            indicator = pilot.app.query_one("#custom-id", StageIndicator)

            assert indicator.name == "test"
            assert indicator.status == "pending"

    @pytest.mark.asyncio
    async def test_initialization_default_status(self) -> None:
        """Test StageIndicator uses default status if not provided."""

        class DefaultStatusApp(App):
            def compose(self):
                yield StageIndicator(name="test")

        async with DefaultStatusApp().run_test() as pilot:
            indicator = pilot.app.query_one(StageIndicator)

            assert indicator.name == "test"
            assert indicator.status == "pending"

    def test_icons_constant(self) -> None:
        """Test ICONS constant has correct mappings."""
        assert StageIndicator.ICONS["pending"] == "○"
        assert StageIndicator.ICONS["active"] == "◉"
        assert StageIndicator.ICONS["completed"] == "✓"
        assert StageIndicator.ICONS["failed"] == "✗"


# =============================================================================
# Render Tests
# =============================================================================


class TestStageIndicatorRender:
    """Tests for StageIndicator rendering."""

    @pytest.mark.asyncio
    async def test_render_pending_status(self) -> None:
        """Test render with pending status."""

        class PendingApp(App):
            def compose(self):
                yield StageIndicator(name="Setup", status="pending")

        async with PendingApp().run_test() as pilot:
            indicator = pilot.app.query_one(StageIndicator)

            assert indicator.render() == "○ Setup"

    @pytest.mark.asyncio
    async def test_render_active_status(self) -> None:
        """Test render with active status."""

        class ActiveApp(App):
            def compose(self):
                yield StageIndicator(name="Build", status="active")

        async with ActiveApp().run_test() as pilot:
            indicator = pilot.app.query_one(StageIndicator)

            assert indicator.render() == "◉ Build"

    @pytest.mark.asyncio
    async def test_render_completed_status(self) -> None:
        """Test render with completed status."""

        class CompletedApp(App):
            def compose(self):
                yield StageIndicator(name="Test", status="completed")

        async with CompletedApp().run_test() as pilot:
            indicator = pilot.app.query_one(StageIndicator)

            assert indicator.render() == "✓ Test"

    @pytest.mark.asyncio
    async def test_render_failed_status(self) -> None:
        """Test render with failed status."""

        class FailedApp(App):
            def compose(self):
                yield StageIndicator(name="Deploy", status="failed")

        async with FailedApp().run_test() as pilot:
            indicator = pilot.app.query_one(StageIndicator)

            assert indicator.render() == "✗ Deploy"

    @pytest.mark.asyncio
    async def test_render_unknown_status(self) -> None:
        """Test render with unknown status defaults to pending icon."""

        class UnknownApp(App):
            def compose(self):
                yield StageIndicator(name="Unknown", status="unknown")

        async with UnknownApp().run_test() as pilot:
            indicator = pilot.app.query_one(StageIndicator)

            # Unknown status should default to "○" (pending icon)
            assert indicator.render() == "○ Unknown"


# =============================================================================
# Status Reactive Tests
# =============================================================================


class TestStageIndicatorStatusReactive:
    """Tests for StageIndicator status reactive property."""

    @pytest.mark.asyncio
    async def test_status_change_updates_render(self) -> None:
        """Test changing status updates the rendered output."""
        async with StageIndicatorTestApp().run_test() as pilot:
            indicator = pilot.app.query_one(StageIndicator)

            # Initial state
            assert indicator.status == "pending"
            assert indicator.render() == "○ test-stage"

            # Change to active
            indicator.status = "active"
            await pilot.pause()

            assert indicator.render() == "◉ test-stage"

    @pytest.mark.asyncio
    async def test_status_change_updates_css_classes(self) -> None:
        """Test changing status updates CSS classes."""
        async with StageIndicatorTestApp().run_test() as pilot:
            indicator = pilot.app.query_one(StageIndicator)

            # Initial state - should have pending class
            assert indicator.has_class("pending")

            # Change to active
            indicator.status = "active"
            await pilot.pause()

            # Should remove pending and add active
            assert not indicator.has_class("pending")
            assert indicator.has_class("active")

    @pytest.mark.asyncio
    async def test_watch_status_removes_old_class(self) -> None:
        """Test watch_status removes old status class."""
        async with StageIndicatorTestApp().run_test() as pilot:
            indicator = pilot.app.query_one(StageIndicator)

            # Set to active
            indicator.status = "active"
            await pilot.pause()
            assert indicator.has_class("active")

            # Change to completed
            indicator.status = "completed"
            await pilot.pause()

            # Old class should be removed
            assert not indicator.has_class("active")
            assert indicator.has_class("completed")

    @pytest.mark.asyncio
    async def test_watch_status_adds_new_class(self) -> None:
        """Test watch_status adds new status class."""
        async with StageIndicatorTestApp().run_test() as pilot:
            indicator = pilot.app.query_one(StageIndicator)

            # Change to failed
            indicator.status = "failed"
            await pilot.pause()

            # New class should be added
            assert indicator.has_class("failed")

    @pytest.mark.asyncio
    async def test_status_changes_through_all_states(self) -> None:
        """Test status changes through all valid states."""
        async with StageIndicatorTestApp().run_test() as pilot:
            indicator = pilot.app.query_one(StageIndicator)

            # Pending -> Active
            indicator.status = "active"
            await pilot.pause()
            assert indicator.render() == "◉ test-stage"
            assert indicator.has_class("active")

            # Active -> Completed
            indicator.status = "completed"
            await pilot.pause()
            assert indicator.render() == "✓ test-stage"
            assert indicator.has_class("completed")
            assert not indicator.has_class("active")

            # Completed -> Failed (unusual but should work)
            indicator.status = "failed"
            await pilot.pause()
            assert indicator.render() == "✗ test-stage"
            assert indicator.has_class("failed")
            assert not indicator.has_class("completed")

            # Failed -> Pending (reset)
            indicator.status = "pending"
            await pilot.pause()
            assert indicator.render() == "○ test-stage"
            assert indicator.has_class("pending")
            assert not indicator.has_class("failed")


# =============================================================================
# Name Reactive Tests
# =============================================================================


class TestStageIndicatorNameReactive:
    """Tests for StageIndicator name reactive property."""

    @pytest.mark.asyncio
    async def test_name_change_updates_render(self) -> None:
        """Test changing name updates the rendered output."""
        async with StageIndicatorTestApp().run_test() as pilot:
            indicator = pilot.app.query_one(StageIndicator)

            # Initial state
            assert indicator.name == "test-stage"
            assert indicator.render() == "○ test-stage"

            # Change name
            indicator.name = "new-name"
            await pilot.pause()

            assert indicator.render() == "○ new-name"

    @pytest.mark.asyncio
    async def test_name_and_status_change_together(self) -> None:
        """Test changing both name and status updates correctly."""
        async with StageIndicatorTestApp().run_test() as pilot:
            indicator = pilot.app.query_one(StageIndicator)

            # Change both
            indicator.name = "Deploy"
            indicator.status = "completed"
            await pilot.pause()

            assert indicator.render() == "✓ Deploy"


# =============================================================================
# Integration Tests
# =============================================================================


class TestStageIndicatorIntegration:
    """Integration tests for StageIndicator."""

    @pytest.mark.asyncio
    async def test_typical_workflow_progression(self) -> None:
        """Test typical workflow stage progression."""

        class WorkflowApp(App):
            def compose(self):
                yield StageIndicator(name="Setup", status="pending", id="setup")
                yield StageIndicator(name="Build", status="pending", id="build")
                yield StageIndicator(name="Test", status="pending", id="test")

        async with WorkflowApp().run_test() as pilot:
            setup = pilot.app.query_one("#setup", StageIndicator)
            build = pilot.app.query_one("#build", StageIndicator)
            test = pilot.app.query_one("#test", StageIndicator)

            # All start pending
            assert setup.render() == "○ Setup"
            assert build.render() == "○ Build"
            assert test.render() == "○ Test"

            # Setup becomes active
            setup.status = "active"
            await pilot.pause()
            assert setup.render() == "◉ Setup"

            # Setup completes, build becomes active
            setup.status = "completed"
            build.status = "active"
            await pilot.pause()
            assert setup.render() == "✓ Setup"
            assert build.render() == "◉ Build"

            # Build completes, test becomes active
            build.status = "completed"
            test.status = "active"
            await pilot.pause()
            assert build.render() == "✓ Build"
            assert test.render() == "◉ Test"

            # Test completes
            test.status = "completed"
            await pilot.pause()
            assert test.render() == "✓ Test"

    @pytest.mark.asyncio
    async def test_stage_with_display_name(self) -> None:
        """Test stage with custom display name."""

        class DisplayNameApp(App):
            def compose(self):
                yield StageIndicator(
                    name="Setup Environment",
                    status="pending",
                )

        async with DisplayNameApp().run_test() as pilot:
            indicator = pilot.app.query_one(StageIndicator)

            assert indicator.render() == "○ Setup Environment"

            indicator.status = "active"
            await pilot.pause()

            assert indicator.render() == "◉ Setup Environment"

    @pytest.mark.asyncio
    async def test_multiple_status_updates(self) -> None:
        """Test multiple rapid status updates."""
        async with StageIndicatorTestApp().run_test() as pilot:
            indicator = pilot.app.query_one(StageIndicator)

            # Rapidly change status multiple times
            for _ in range(3):
                indicator.status = "active"
                await pilot.pause()
                assert indicator.has_class("active")

                indicator.status = "pending"
                await pilot.pause()
                assert indicator.has_class("pending")

            # Final state should be correct
            indicator.status = "completed"
            await pilot.pause()
            assert indicator.render() == "✓ test-stage"
            assert indicator.has_class("completed")


# =============================================================================
# Edge Cases
# =============================================================================


class TestStageIndicatorEdgeCases:
    """Tests for StageIndicator edge cases."""

    @pytest.mark.asyncio
    async def test_empty_name(self) -> None:
        """Test StageIndicator with empty name."""

        class EmptyNameApp(App):
            def compose(self):
                yield StageIndicator(name="", status="pending")

        async with EmptyNameApp().run_test() as pilot:
            indicator = pilot.app.query_one(StageIndicator)

            assert indicator.render() == "○ "

    @pytest.mark.asyncio
    async def test_long_name(self) -> None:
        """Test StageIndicator with very long name."""

        class LongNameApp(App):
            def compose(self):
                yield StageIndicator(
                    name="This is a very long stage name that should still work",
                    status="pending",
                )

        async with LongNameApp().run_test() as pilot:
            indicator = pilot.app.query_one(StageIndicator)

            assert (
                indicator.render()
                == "○ This is a very long stage name that should still work"
            )

    @pytest.mark.asyncio
    async def test_special_characters_in_name(self) -> None:
        """Test StageIndicator with special characters in name."""

        class SpecialCharsApp(App):
            def compose(self):
                yield StageIndicator(
                    name="Build & Test (Production)",
                    status="pending",
                )

        async with SpecialCharsApp().run_test() as pilot:
            indicator = pilot.app.query_one(StageIndicator)

            assert indicator.render() == "○ Build & Test (Production)"

    @pytest.mark.asyncio
    async def test_same_status_assignment(self) -> None:
        """Test assigning the same status multiple times."""
        async with StageIndicatorTestApp().run_test() as pilot:
            indicator = pilot.app.query_one(StageIndicator)

            # Assign same status multiple times
            indicator.status = "pending"
            await pilot.pause()
            indicator.status = "pending"
            await pilot.pause()
            indicator.status = "pending"
            await pilot.pause()

            # Should still work correctly
            assert indicator.render() == "○ test-stage"
            assert indicator.has_class("pending")
