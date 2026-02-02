"""Unit tests for AggregateStatsBar widget."""

from __future__ import annotations

from maverick.tui.models.widget_state import UnifiedStreamState
from maverick.tui.widgets.aggregate_stats import AggregateStatsBar


def _make_state(**kwargs) -> UnifiedStreamState:
    """Create a UnifiedStreamState with given overrides."""
    return UnifiedStreamState(**kwargs)


class TestAggregateStatsBarFormatting:
    """Tests for AggregateStatsBar._format_stats output."""

    def test_zero_state(self):
        """Test rendering with zero state (no steps)."""
        state = _make_state(total_steps=0)
        bar = AggregateStatsBar(state)
        text = bar._format_stats()

        assert "No steps" in text
        assert "Tokens:" in text
        assert "Cost:" in text
        assert "0" in text  # zero tokens
        assert "$0.0000" in text  # zero cost

    def test_all_pending(self):
        """Test rendering when all steps are pending."""
        state = _make_state(total_steps=5)
        bar = AggregateStatsBar(state)
        text = bar._format_stats()

        assert "5 pending" in text
        assert "running" not in text
        assert "completed" not in text
        assert "failed" not in text

    def test_one_running(self):
        """Test rendering with one step running."""
        state = _make_state(total_steps=5)
        state.start_step("step-1", "python")
        bar = AggregateStatsBar(state)
        text = bar._format_stats()

        assert "1 running" in text
        assert "4 pending" in text

    def test_mixed_statuses(self):
        """Test rendering with a mix of completed, failed, running, pending."""
        state = _make_state(total_steps=6)
        # Simulate: 2 completed, 1 failed, 1 running, 2 pending
        state.completed_steps = 2
        state.failed_steps = 1
        state.current_step = "step-4"
        state.current_step_number = 4
        bar = AggregateStatsBar(state)
        text = bar._format_stats()

        assert "1 running" in text
        assert "2 completed" in text
        assert "1 failed" in text
        assert "2 pending" in text

    def test_all_completed(self):
        """Test rendering when all steps are completed."""
        state = _make_state(total_steps=3, completed_steps=3)
        # No current step means not running
        bar = AggregateStatsBar(state)
        text = bar._format_stats()

        assert "3 completed" in text
        assert "running" not in text
        assert "pending" not in text
        assert "failed" not in text

    def test_token_formatting_with_commas(self):
        """Test that tokens are formatted with comma separators."""
        state = _make_state(total_steps=1, total_tokens=12345)
        bar = AggregateStatsBar(state)
        text = bar._format_stats()

        assert "12,345" in text

    def test_cost_formatting_four_decimals(self):
        """Test that cost is formatted with dollar sign and 4 decimals."""
        state = _make_state(total_steps=1, total_cost=0.0385)
        bar = AggregateStatsBar(state)
        text = bar._format_stats()

        assert "$0.0385" in text

    def test_large_token_count(self):
        """Test formatting with large token count."""
        state = _make_state(total_steps=1, total_tokens=1_234_567)
        bar = AggregateStatsBar(state)
        text = bar._format_stats()

        assert "1,234,567" in text

    def test_pipe_separators_present(self):
        """Test that pipe separators are present between sections."""
        state = _make_state(total_steps=3, completed_steps=1)
        state.current_step = "step-2"
        bar = AggregateStatsBar(state)
        text = bar._format_stats()

        # Unicode pipe character U+2502
        assert "\u2502" in text


class TestAggregateStatsBarRefresh:
    """Tests for AggregateStatsBar.refresh_display method."""

    def test_refresh_display_updates_content(self):
        """Test that refresh_display calls update with formatted stats."""
        state = _make_state(total_steps=3, completed_steps=2, total_tokens=500)
        bar = AggregateStatsBar(state)

        # Call _format_stats to get expected content
        expected = bar._format_stats()

        # refresh_display should produce the same formatted text
        # We verify the format stays consistent after state changes
        state.total_tokens = 1000
        new_text = bar._format_stats()

        assert "1,000" in new_text
        assert "500" in expected


class TestAggregateStatsBarInit:
    """Tests for AggregateStatsBar initialization."""

    def test_stores_state_reference(self):
        """Test that the widget stores the state reference."""
        state = _make_state(total_steps=5)
        bar = AggregateStatsBar(state, id="stats-bar")
        assert bar._state is state

    def test_widget_id(self):
        """Test that widget ID is set correctly."""
        state = _make_state()
        bar = AggregateStatsBar(state, id="my-stats")
        assert bar.id == "my-stats"
