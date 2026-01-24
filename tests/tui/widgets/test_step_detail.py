"""Tests for StepDetailPanel widget.

This module tests the StepDetailPanel widget using Textual pilot testing.
"""

from __future__ import annotations

import pytest
from textual.app import App
from textual.widgets import Static

from maverick.tui.models.widget_state import UnifiedStreamState
from maverick.tui.widgets.step_detail import StepDetailPanel


class StepDetailTestApp(App):
    """Test app for StepDetailPanel testing."""

    def __init__(self, state: UnifiedStreamState | None = None) -> None:
        super().__init__()
        self._state = state or UnifiedStreamState()

    def compose(self):
        yield StepDetailPanel(self._state, id="detail-panel")


class TestStepDetailPanelCreation:
    """Test suite for StepDetailPanel creation."""

    def test_creation_with_state(self) -> None:
        """Test creating StepDetailPanel with state."""
        state = UnifiedStreamState(workflow_name="test-workflow", total_steps=5)
        panel = StepDetailPanel(state, id="test-panel")

        assert panel._state is state
        assert panel.border_title == "Detail"

    def test_creation_with_empty_state(self) -> None:
        """Test creating StepDetailPanel with empty state."""
        state = UnifiedStreamState()
        panel = StepDetailPanel(state)

        assert panel._state.current_step is None
        assert panel._state.total_steps == 0


class TestStepDetailPanelFormatting:
    """Test suite for StepDetailPanel formatting methods."""

    def test_format_tokens_with_value(self) -> None:
        """Test _format_tokens with positive value."""
        state = UnifiedStreamState()
        panel = StepDetailPanel(state)

        assert panel._format_tokens(1000) == "1,000"
        assert panel._format_tokens(1234567) == "1,234,567"

    def test_format_tokens_zero(self) -> None:
        """Test _format_tokens with zero returns '--'."""
        state = UnifiedStreamState()
        panel = StepDetailPanel(state)

        assert panel._format_tokens(0) == "--"

    def test_format_tokens_negative(self) -> None:
        """Test _format_tokens with negative value returns '--'."""
        state = UnifiedStreamState()
        panel = StepDetailPanel(state)

        assert panel._format_tokens(-100) == "--"

    def test_format_cost_with_value(self) -> None:
        """Test _format_cost with positive value."""
        state = UnifiedStreamState()
        panel = StepDetailPanel(state)

        result = panel._format_cost(0.0045)
        assert "$0.0045" in result
        assert "[green]" in result  # Should be styled green

    def test_format_cost_zero(self) -> None:
        """Test _format_cost with zero returns '--'."""
        state = UnifiedStreamState()
        panel = StepDetailPanel(state)

        assert panel._format_cost(0.0) == "--"

    def test_format_cost_negative(self) -> None:
        """Test _format_cost with negative value returns '--'."""
        state = UnifiedStreamState()
        panel = StepDetailPanel(state)

        assert panel._format_cost(-1.0) == "--"

    def test_get_step_type_icon_agent(self) -> None:
        """Test _get_step_type_icon for agent step."""
        state = UnifiedStreamState()
        panel = StepDetailPanel(state)

        icon = panel._get_step_type_icon("agent")
        assert icon == "\U0001f916"  # robot emoji

    def test_get_step_type_icon_python(self) -> None:
        """Test _get_step_type_icon for python step."""
        state = UnifiedStreamState()
        panel = StepDetailPanel(state)

        icon = panel._get_step_type_icon("python")
        assert icon == "\u2699"  # gear emoji

    def test_get_step_type_icon_unknown(self) -> None:
        """Test _get_step_type_icon for unknown type returns bullet."""
        state = UnifiedStreamState()
        panel = StepDetailPanel(state)

        icon = panel._get_step_type_icon("unknown_type")
        assert icon == "\u2022"  # bullet


@pytest.mark.asyncio
class TestStepDetailPanelRendering:
    """Test suite for StepDetailPanel rendering with pilot testing."""

    async def test_renders_no_selection_when_no_step(self) -> None:
        """Test that panel shows 'No step selected' when no step is active."""
        state = UnifiedStreamState()
        app = StepDetailTestApp(state)

        async with app.run_test():
            panel = app.query_one("#detail-panel", StepDetailPanel)
            content = panel.query_one("#detail-content", Static)

            # Should show no selection message
            assert "No step selected" in content.renderable

    async def test_renders_step_info_when_step_active(self) -> None:
        """Test that panel shows step info when a step is active."""
        state = UnifiedStreamState(total_steps=3)
        state.start_step("implement_task", "agent")

        app = StepDetailTestApp(state)

        async with app.run_test() as pilot:
            panel = app.query_one("#detail-panel", StepDetailPanel)
            panel.refresh_display()
            await pilot.pause()

            content = panel.query_one("#detail-content", Static)
            rendered = str(content.renderable)

            # Should show step name and type
            assert "implement_task" in rendered
            assert "agent" in rendered

    async def test_refresh_display_updates_content(self) -> None:
        """Test that refresh_display updates the content."""
        state = UnifiedStreamState(total_steps=2)
        app = StepDetailTestApp(state)

        async with app.run_test() as pilot:
            panel = app.query_one("#detail-panel", StepDetailPanel)

            # Initially no step
            content = panel.query_one("#detail-content", Static)
            assert "No step selected" in content.renderable

            # Start a step and refresh
            state.start_step("new_step", "python")
            panel.refresh_display()
            await pilot.pause()

            # Content should now show the step
            assert "new_step" in str(content.renderable)

    async def test_shows_aggregate_metrics(self) -> None:
        """Test that panel shows aggregate workflow metrics."""
        state = UnifiedStreamState(total_steps=3)
        state.start_step("step1", "agent")
        state.complete_step(
            success=True,
            input_tokens=1000,
            output_tokens=500,
            cost_usd=0.005,
        )
        state.start_step("step2", "agent")

        app = StepDetailTestApp(state)

        async with app.run_test() as pilot:
            panel = app.query_one("#detail-panel", StepDetailPanel)
            panel.refresh_display()
            await pilot.pause()

            content = panel.query_one("#detail-content", Static)
            rendered = str(content.renderable)

            # Should show aggregate stats
            assert "1/3" in rendered or "1 /3" in rendered  # steps progress
            assert "1,500" in rendered  # total tokens


@pytest.mark.asyncio
class TestStepDetailPanelIntegration:
    """Integration tests for StepDetailPanel state updates."""

    async def test_state_changes_reflected_after_refresh(self) -> None:
        """Test that state changes are reflected after refresh_display."""
        state = UnifiedStreamState(total_steps=2)
        app = StepDetailTestApp(state)

        async with app.run_test() as pilot:
            panel = app.query_one("#detail-panel", StepDetailPanel)

            # Start step
            state.start_step("step1", "agent")
            panel.refresh_display()
            await pilot.pause()

            content = panel.query_one("#detail-content", Static)
            assert "step1" in str(content.renderable)

            # Complete step and start new one
            state.complete_step(success=True, input_tokens=100, output_tokens=50)
            state.start_step("step2", "python")
            panel.refresh_display()
            await pilot.pause()

            # Should now show step2
            assert "step2" in str(content.renderable)
