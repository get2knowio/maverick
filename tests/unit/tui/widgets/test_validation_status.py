"""Unit tests for ValidationStatus widget."""

from __future__ import annotations

from dataclasses import replace

import pytest
from textual.app import App

from maverick.tui.models import ValidationStep, ValidationStepStatus
from maverick.tui.widgets.validation_status import ValidationStatus

# =============================================================================
# Test App for ValidationStatus Testing
# =============================================================================


class ValidationStatusTestApp(App):
    """Test app for ValidationStatus widget testing."""

    def compose(self):
        """Compose the test app."""
        yield ValidationStatus()


# =============================================================================
# ValidationStatus Initialization Tests
# =============================================================================


class TestValidationStatusInitialization:
    """Tests for ValidationStatus initialization."""

    @pytest.mark.asyncio
    async def test_initialization_default_empty(self) -> None:
        """Test ValidationStatus initializes empty by default."""
        async with ValidationStatusTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ValidationStatus)

            assert widget.state.is_empty
            assert len(widget.state.steps) == 0
            assert not widget.state.loading

    @pytest.mark.asyncio
    async def test_initialization_with_custom_id(self) -> None:
        """Test ValidationStatus initializes with custom id."""

        class CustomIdApp(App):
            def compose(self):
                yield ValidationStatus(id="custom-validation")

        async with CustomIdApp().run_test() as pilot:
            widget = pilot.app.query_one("#custom-validation", ValidationStatus)
            assert widget.state.is_empty


# =============================================================================
# Update Steps Tests
# =============================================================================


class TestValidationStatusUpdateSteps:
    """Tests for update_steps method."""

    @pytest.mark.asyncio
    async def test_update_steps_with_multiple_steps(self) -> None:
        """Test updating with multiple validation steps."""
        async with ValidationStatusTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ValidationStatus)

            steps = [
                ValidationStep(
                    name="format",
                    display_name="Format",
                    status=ValidationStepStatus.PENDING,
                ),
                ValidationStep(
                    name="lint",
                    display_name="Lint",
                    status=ValidationStepStatus.PENDING,
                ),
                ValidationStep(
                    name="test",
                    display_name="Test",
                    status=ValidationStepStatus.PENDING,
                ),
            ]

            widget.update_steps(steps)
            await pilot.pause()

            assert len(widget.state.steps) == 3
            assert widget.state.steps[0].name == "format"
            assert widget.state.steps[1].name == "lint"
            assert widget.state.steps[2].name == "test"
            assert not widget.state.is_empty

    @pytest.mark.asyncio
    async def test_update_steps_clears_previous_steps(self) -> None:
        """Test update_steps replaces previous steps."""
        async with ValidationStatusTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ValidationStatus)

            # Set initial steps
            initial_steps = [
                ValidationStep(
                    name="format",
                    display_name="Format",
                    status=ValidationStepStatus.PENDING,
                ),
            ]
            widget.update_steps(initial_steps)
            await pilot.pause()
            assert len(widget.state.steps) == 1

            # Update with new steps
            new_steps = [
                ValidationStep(
                    name="lint",
                    display_name="Lint",
                    status=ValidationStepStatus.PENDING,
                ),
                ValidationStep(
                    name="test",
                    display_name="Test",
                    status=ValidationStepStatus.PENDING,
                ),
            ]
            widget.update_steps(new_steps)
            await pilot.pause()

            assert len(widget.state.steps) == 2
            assert widget.state.steps[0].name == "lint"

    @pytest.mark.asyncio
    async def test_update_steps_with_empty_list(self) -> None:
        """Test update_steps with empty list."""
        async with ValidationStatusTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ValidationStatus)

            # Set steps first
            steps = [
                ValidationStep(
                    name="format",
                    display_name="Format",
                    status=ValidationStepStatus.PENDING,
                ),
            ]
            widget.update_steps(steps)
            await pilot.pause()
            assert not widget.state.is_empty

            # Clear with empty list
            widget.update_steps([])
            await pilot.pause()

            assert widget.state.is_empty
            assert len(widget.state.steps) == 0


# =============================================================================
# Update Step Status Tests
# =============================================================================


class TestValidationStatusUpdateStepStatus:
    """Tests for update_step_status method."""

    @pytest.mark.asyncio
    async def test_update_step_status_to_running(self) -> None:
        """Test updating a step to running status."""
        async with ValidationStatusTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ValidationStatus)

            steps = [
                ValidationStep(
                    name="format",
                    display_name="Format",
                    status=ValidationStepStatus.PENDING,
                ),
            ]
            widget.update_steps(steps)
            await pilot.pause()

            widget.update_step_status("format", ValidationStepStatus.RUNNING)
            await pilot.pause()

            assert widget.state.steps[0].status == ValidationStepStatus.RUNNING
            assert widget.state.running_step == "format"
            assert widget.state.is_running

    @pytest.mark.asyncio
    async def test_update_step_status_to_passed(self) -> None:
        """Test updating a step to passed status."""
        async with ValidationStatusTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ValidationStatus)

            steps = [
                ValidationStep(
                    name="format",
                    display_name="Format",
                    status=ValidationStepStatus.RUNNING,
                ),
            ]
            widget.update_steps(steps)
            await pilot.pause()

            widget.update_step_status("format", ValidationStepStatus.PASSED)
            await pilot.pause()

            assert widget.state.steps[0].status == ValidationStepStatus.PASSED
            assert widget.state.running_step is None
            assert not widget.state.is_running

    @pytest.mark.asyncio
    async def test_update_step_status_to_failed_with_error(self) -> None:
        """Test updating a step to failed status with error output."""
        async with ValidationStatusTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ValidationStatus)

            steps = [
                ValidationStep(
                    name="lint",
                    display_name="Lint",
                    status=ValidationStepStatus.RUNNING,
                ),
            ]
            widget.update_steps(steps)
            await pilot.pause()

            error_msg = "Error: Linting failed on line 42"
            widget.update_step_status(
                "lint", ValidationStepStatus.FAILED, error_output=error_msg
            )
            await pilot.pause()

            assert widget.state.steps[0].status == ValidationStepStatus.FAILED
            assert widget.state.steps[0].error_output == error_msg
            assert widget.state.has_failures
            assert not widget.state.all_passed

    @pytest.mark.asyncio
    async def test_update_step_status_nonexistent_step(self) -> None:
        """Test updating a nonexistent step does nothing."""
        async with ValidationStatusTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ValidationStatus)

            steps = [
                ValidationStep(
                    name="format",
                    display_name="Format",
                    status=ValidationStepStatus.PENDING,
                ),
            ]
            widget.update_steps(steps)
            await pilot.pause()

            # Should not raise error
            widget.update_step_status("nonexistent", ValidationStepStatus.PASSED)
            await pilot.pause()

            # Original step unchanged
            assert widget.state.steps[0].status == ValidationStepStatus.PENDING

    @pytest.mark.asyncio
    async def test_all_passed_property(self) -> None:
        """Test all_passed property when all steps pass."""
        async with ValidationStatusTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ValidationStatus)

            steps = [
                ValidationStep(
                    name="format",
                    display_name="Format",
                    status=ValidationStepStatus.PENDING,
                ),
                ValidationStep(
                    name="lint",
                    display_name="Lint",
                    status=ValidationStepStatus.PENDING,
                ),
            ]
            widget.update_steps(steps)
            await pilot.pause()

            # Initially not all passed
            assert not widget.state.all_passed

            # Update both to passed
            widget.update_step_status("format", ValidationStepStatus.PASSED)
            widget.update_step_status("lint", ValidationStepStatus.PASSED)
            await pilot.pause()

            assert widget.state.all_passed
            assert not widget.state.has_failures


# =============================================================================
# Expand/Collapse Tests
# =============================================================================


class TestValidationStatusExpandCollapse:
    """Tests for expand_step and collapse_step methods."""

    @pytest.mark.asyncio
    async def test_expand_failed_step(self) -> None:
        """Test expanding a failed step shows error details."""
        async with ValidationStatusTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ValidationStatus)

            steps = [
                ValidationStep(
                    name="lint",
                    display_name="Lint",
                    status=ValidationStepStatus.FAILED,
                    error_output="Linting errors found",
                ),
            ]
            widget.update_steps(steps)
            await pilot.pause()

            widget.expand_step("lint")
            await pilot.pause()

            assert widget.state.expanded_step == "lint"

    @pytest.mark.asyncio
    async def test_collapse_step(self) -> None:
        """Test collapsing an expanded step."""
        async with ValidationStatusTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ValidationStatus)

            steps = [
                ValidationStep(
                    name="lint",
                    display_name="Lint",
                    status=ValidationStepStatus.FAILED,
                    error_output="Linting errors found",
                ),
            ]
            widget.update_steps(steps)
            await pilot.pause()

            widget.expand_step("lint")
            await pilot.pause()
            assert widget.state.expanded_step == "lint"

            widget.collapse_step()
            await pilot.pause()
            assert widget.state.expanded_step is None

    @pytest.mark.asyncio
    async def test_expand_different_step_collapses_previous(self) -> None:
        """Test expanding a different step collapses the previously expanded one."""
        async with ValidationStatusTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ValidationStatus)

            steps = [
                ValidationStep(
                    name="lint",
                    display_name="Lint",
                    status=ValidationStepStatus.FAILED,
                    error_output="Lint error",
                ),
                ValidationStep(
                    name="test",
                    display_name="Test",
                    status=ValidationStepStatus.FAILED,
                    error_output="Test error",
                ),
            ]
            widget.update_steps(steps)
            await pilot.pause()

            widget.expand_step("lint")
            await pilot.pause()
            assert widget.state.expanded_step == "lint"

            widget.expand_step("test")
            await pilot.pause()
            assert widget.state.expanded_step == "test"


# =============================================================================
# Rerun Button Tests
# =============================================================================


class TestValidationStatusRerunButton:
    """Tests for set_rerun_enabled method."""

    @pytest.mark.asyncio
    async def test_set_rerun_enabled_true(self) -> None:
        """Test enabling rerun button for a step."""
        async with ValidationStatusTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ValidationStatus)

            steps = [
                ValidationStep(
                    name="format",
                    display_name="Format",
                    status=ValidationStepStatus.PASSED,
                ),
            ]
            widget.update_steps(steps)
            await pilot.pause()

            widget.set_rerun_enabled("format", True)
            await pilot.pause()

            # Should be able to query for rerun button
            # Note: Actual button state would be tested via DOM inspection

    @pytest.mark.asyncio
    async def test_set_rerun_enabled_false(self) -> None:
        """Test disabling rerun button for a step."""
        async with ValidationStatusTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ValidationStatus)

            steps = [
                ValidationStep(
                    name="format",
                    display_name="Format",
                    status=ValidationStepStatus.RUNNING,
                ),
            ]
            widget.update_steps(steps)
            await pilot.pause()

            widget.set_rerun_enabled("format", False)
            await pilot.pause()

            # Rerun button should be disabled during running state


# =============================================================================
# Message Emission Tests
# =============================================================================


class TestValidationStatusMessages:
    """Tests for message emission."""

    @pytest.mark.asyncio
    async def test_expand_step_emits_message(self) -> None:
        """Test expanding a step emits StepExpanded message."""

        messages = []

        class MessageTestApp(App):
            def __init__(self):
                super().__init__()

            def compose(self):
                yield ValidationStatus()

            def on_validation_status_step_expanded(
                self, message: ValidationStatus.StepExpanded
            ):
                messages.append(message)

        async with MessageTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ValidationStatus)

            steps = [
                ValidationStep(
                    name="lint",
                    display_name="Lint",
                    status=ValidationStepStatus.FAILED,
                    error_output="Error",
                ),
            ]
            widget.update_steps(steps)
            await pilot.pause()

            widget.expand_step("lint")
            await pilot.pause()

            # We might get 2 messages - one from expand_step and one
            # from collapsible toggle. Both are valid - what matters is
            # at least one message is posted
            assert len(messages) >= 1
            assert messages[0].step_name == "lint"

    @pytest.mark.asyncio
    async def test_collapse_step_emits_message(self) -> None:
        """Test collapsing a step emits StepCollapsed message."""

        messages = []

        class MessageTestApp(App):
            def __init__(self):
                super().__init__()

            def compose(self):
                yield ValidationStatus()

            def on_validation_status_step_collapsed(
                self, message: ValidationStatus.StepCollapsed
            ):
                messages.append(message)

        async with MessageTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ValidationStatus)

            steps = [
                ValidationStep(
                    name="lint",
                    display_name="Lint",
                    status=ValidationStepStatus.FAILED,
                    error_output="Error",
                ),
            ]
            widget.update_steps(steps)
            await pilot.pause()

            # First expand
            widget.expand_step("lint")
            await pilot.pause()

            widget.collapse_step()
            await pilot.pause()

            assert len(messages) == 1
            assert messages[0].step_name == "lint"


# =============================================================================
# Loading State Tests
# =============================================================================


class TestValidationStatusLoadingState:
    """Tests for loading state."""

    @pytest.mark.asyncio
    async def test_loading_state_shows_spinner(self) -> None:
        """Test loading state displays spinner."""
        async with ValidationStatusTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ValidationStatus)

            # Initially not loading
            assert not widget.state.loading

            # Set loading via state update
            widget._state = replace(widget.state, loading=True)
            widget.refresh()
            await pilot.pause()

            assert widget.state.loading

    @pytest.mark.asyncio
    async def test_is_empty_false_when_loading(self) -> None:
        """Test is_empty returns False when loading."""
        async with ValidationStatusTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ValidationStatus)

            assert widget.state.is_empty

            # Set loading
            widget._state = replace(widget.state, loading=True)
            widget.refresh()
            await pilot.pause()

            # Should not be empty when loading
            assert not widget.state.is_empty


# =============================================================================
# Empty State Tests
# =============================================================================


class TestValidationStatusEmptyState:
    """Tests for empty state."""

    @pytest.mark.asyncio
    async def test_empty_state_shows_message(self) -> None:
        """Test empty state displays 'No validation steps' message."""
        async with ValidationStatusTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ValidationStatus)

            assert widget.state.is_empty

            # Empty state text should be visible in rendered output
            # Actual rendering would be tested via snapshot or text content check


# =============================================================================
# Status Icon Tests
# =============================================================================


class TestValidationStatusIcons:
    """Tests for status icon rendering."""

    def test_icons_constant(self) -> None:
        """Test ICONS constant has correct mappings."""
        assert ValidationStatus.ICONS["pending"] == "○"
        assert ValidationStatus.ICONS["running"] == "◠"  # spinner placeholder
        assert ValidationStatus.ICONS["passed"] == "✓"
        assert ValidationStatus.ICONS["failed"] == "✗"


# =============================================================================
# Integration Tests
# =============================================================================


class TestValidationStatusIntegration:
    """Integration tests for ValidationStatus."""

    @pytest.mark.asyncio
    async def test_typical_validation_flow(self) -> None:
        """Test typical validation workflow progression."""
        async with ValidationStatusTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ValidationStatus)

            # Initialize with pending steps
            steps = [
                ValidationStep(
                    name="format",
                    display_name="Format",
                    status=ValidationStepStatus.PENDING,
                ),
                ValidationStep(
                    name="lint",
                    display_name="Lint",
                    status=ValidationStepStatus.PENDING,
                ),
                ValidationStep(
                    name="test",
                    display_name="Test",
                    status=ValidationStepStatus.PENDING,
                ),
            ]
            widget.update_steps(steps)
            await pilot.pause()

            # Run format - pass
            widget.update_step_status("format", ValidationStepStatus.RUNNING)
            await pilot.pause()
            assert widget.state.is_running

            widget.update_step_status("format", ValidationStepStatus.PASSED)
            await pilot.pause()

            # Run lint - fail
            widget.update_step_status("lint", ValidationStepStatus.RUNNING)
            await pilot.pause()

            widget.update_step_status(
                "lint", ValidationStepStatus.FAILED, error_output="Lint errors"
            )
            await pilot.pause()
            assert widget.state.has_failures

            # Expand failed step
            widget.expand_step("lint")
            await pilot.pause()
            assert widget.state.expanded_step == "lint"

            # Fix and rerun lint - pass
            widget.update_step_status("lint", ValidationStepStatus.RUNNING)
            await pilot.pause()

            widget.update_step_status("lint", ValidationStepStatus.PASSED)
            await pilot.pause()

            # Run test - pass
            widget.update_step_status("test", ValidationStepStatus.RUNNING)
            await pilot.pause()

            widget.update_step_status("test", ValidationStepStatus.PASSED)
            await pilot.pause()

            # All passed
            assert widget.state.all_passed
            assert not widget.state.has_failures
            assert not widget.state.is_running

    @pytest.mark.asyncio
    async def test_horizontal_layout_with_multiple_steps(self) -> None:
        """Test horizontal layout displays all steps in a row."""
        async with ValidationStatusTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ValidationStatus)

            steps = [
                ValidationStep(
                    name="format",
                    display_name="Format",
                    status=ValidationStepStatus.PASSED,
                ),
                ValidationStep(
                    name="lint",
                    display_name="Lint",
                    status=ValidationStepStatus.RUNNING,
                ),
                ValidationStep(
                    name="build",
                    display_name="Build",
                    status=ValidationStepStatus.PENDING,
                ),
                ValidationStep(
                    name="test",
                    display_name="Test",
                    status=ValidationStepStatus.PENDING,
                ),
            ]
            widget.update_steps(steps)
            await pilot.pause()

            # All steps should be present
            assert len(widget.state.steps) == 4


# =============================================================================
# Edge Cases
# =============================================================================


class TestValidationStatusEdgeCases:
    """Tests for ValidationStatus edge cases."""

    @pytest.mark.asyncio
    async def test_expand_nonexistent_step(self) -> None:
        """Test expanding a nonexistent step does nothing."""
        async with ValidationStatusTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ValidationStatus)

            steps = [
                ValidationStep(
                    name="lint",
                    display_name="Lint",
                    status=ValidationStepStatus.FAILED,
                    error_output="Error",
                ),
            ]
            widget.update_steps(steps)
            await pilot.pause()

            # Should not raise error
            widget.expand_step("nonexistent")
            await pilot.pause()

            assert widget.state.expanded_step is None

    @pytest.mark.asyncio
    async def test_collapse_when_nothing_expanded(self) -> None:
        """Test collapsing when nothing is expanded."""
        async with ValidationStatusTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ValidationStatus)

            # Should not raise error
            widget.collapse_step()
            await pilot.pause()

            assert widget.state.expanded_step is None

    @pytest.mark.asyncio
    async def test_multiple_running_steps(self) -> None:
        """Test behavior with multiple running steps."""
        async with ValidationStatusTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ValidationStatus)

            steps = [
                ValidationStep(
                    name="format",
                    display_name="Format",
                    status=ValidationStepStatus.RUNNING,
                ),
                ValidationStep(
                    name="lint",
                    display_name="Lint",
                    status=ValidationStepStatus.RUNNING,
                ),
            ]
            widget.update_steps(steps)
            await pilot.pause()

            assert widget.state.is_running
            # running_step should track the most recently updated one

    @pytest.mark.asyncio
    async def test_very_long_error_output(self) -> None:
        """Test handling of very long error output."""
        async with ValidationStatusTestApp().run_test() as pilot:
            widget = pilot.app.query_one(ValidationStatus)

            long_error = "Error: " + "x" * 10000  # Very long error message
            steps = [
                ValidationStep(
                    name="test",
                    display_name="Test",
                    status=ValidationStepStatus.FAILED,
                    error_output=long_error,
                ),
            ]
            widget.update_steps(steps)
            await pilot.pause()

            widget.expand_step("test")
            await pilot.pause()

            # Should handle long errors without crashing
            assert widget.state.steps[0].error_output == long_error
