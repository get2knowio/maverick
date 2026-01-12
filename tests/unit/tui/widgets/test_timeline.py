"""Unit tests for ProgressTimeline widget and TimelineStep dataclass.

This test module covers:
- TimelineStep dataclass creation and attributes
- ProgressTimeline widget creation and methods
- Duration formatting
- Property calculations

Feature: 030-tui-execution-visibility
Date: 2026-01-12
"""

from __future__ import annotations

import pytest

from maverick.tui.widgets.timeline import ProgressTimeline, TimelineStep


class TestTimelineStep:
    """Tests for TimelineStep dataclass."""

    def test_creation_with_required_fields(self) -> None:
        """Test creating TimelineStep with required fields only."""
        step = TimelineStep(name="validate", status="pending")

        assert step.name == "validate"
        assert step.status == "pending"
        assert step.duration_seconds is None
        assert step.estimated_seconds is None

    def test_creation_with_all_fields(self) -> None:
        """Test creating TimelineStep with all fields."""
        step = TimelineStep(
            name="implement",
            status="completed",
            duration_seconds=30.5,
            estimated_seconds=45.0,
        )

        assert step.name == "implement"
        assert step.status == "completed"
        assert step.duration_seconds == 30.5
        assert step.estimated_seconds == 45.0

    def test_step_is_frozen(self) -> None:
        """Test that TimelineStep is immutable (frozen dataclass)."""
        step = TimelineStep(name="test", status="pending")

        with pytest.raises(Exception):  # FrozenInstanceError
            step.name = "modified"  # type: ignore[misc]

    def test_step_has_slots(self) -> None:
        """Test that TimelineStep uses __slots__ for memory efficiency."""
        step = TimelineStep(name="test", status="pending")

        # Slots-based classes don't have __dict__
        assert not hasattr(step, "__dict__")

    def test_all_status_values(self) -> None:
        """Test TimelineStep accepts all valid status values."""
        statuses = ["pending", "running", "completed", "failed", "skipped"]

        for status in statuses:
            step = TimelineStep(name="test", status=status)
            assert step.status == status


class TestProgressTimelineFormatDuration:
    """Tests for ProgressTimeline._format_duration method."""

    def test_format_zero_seconds(self) -> None:
        """Test formatting zero seconds."""
        timeline = ProgressTimeline()
        assert timeline._format_duration(0) == "0s"

    def test_format_none_seconds(self) -> None:
        """Test formatting None seconds."""
        timeline = ProgressTimeline()
        assert timeline._format_duration(None) == "0s"

    def test_format_milliseconds(self) -> None:
        """Test formatting sub-second durations."""
        timeline = ProgressTimeline()
        assert timeline._format_duration(0.5) == "500ms"
        assert timeline._format_duration(0.1) == "100ms"
        assert timeline._format_duration(0.05) == "50ms"

    def test_format_seconds(self) -> None:
        """Test formatting second durations."""
        timeline = ProgressTimeline()
        assert timeline._format_duration(1.0) == "1.0s"
        assert timeline._format_duration(5.5) == "5.5s"
        assert timeline._format_duration(30.0) == "30.0s"

    def test_format_minutes(self) -> None:
        """Test formatting minute durations."""
        timeline = ProgressTimeline()
        assert timeline._format_duration(60.0) == "1m0s"
        assert timeline._format_duration(90.0) == "1m30s"
        assert timeline._format_duration(125.0) == "2m5s"


class TestProgressTimelineStepTime:
    """Tests for ProgressTimeline._get_step_time method."""

    def test_get_step_time_with_duration(self) -> None:
        """Test getting step time with actual duration."""
        timeline = ProgressTimeline()
        step = TimelineStep(
            name="test",
            status="completed",
            duration_seconds=30.0,
            estimated_seconds=45.0,
        )

        # Actual duration takes precedence
        assert timeline._get_step_time(step) == 30.0

    def test_get_step_time_with_estimate_only(self) -> None:
        """Test getting step time with estimate only."""
        timeline = ProgressTimeline()
        step = TimelineStep(name="test", status="pending", estimated_seconds=45.0)

        assert timeline._get_step_time(step) == 45.0

    def test_get_step_time_with_no_times(self) -> None:
        """Test getting step time with no duration or estimate."""
        timeline = ProgressTimeline()
        step = TimelineStep(name="test", status="pending")

        # Default to 1.0 second
        assert timeline._get_step_time(step) == 1.0


class TestProgressTimelineTotalTime:
    """Tests for ProgressTimeline._get_total_time method."""

    def test_total_time_empty_steps(self) -> None:
        """Test total time with no steps."""
        timeline = ProgressTimeline()
        timeline._steps = []

        assert timeline._get_total_time() == 0.0

    def test_total_time_with_durations(self) -> None:
        """Test total time with actual durations."""
        timeline = ProgressTimeline()
        timeline._steps = [
            TimelineStep("step1", "completed", duration_seconds=10.0),
            TimelineStep("step2", "completed", duration_seconds=20.0),
            TimelineStep("step3", "completed", duration_seconds=30.0),
        ]

        assert timeline._get_total_time() == 60.0

    def test_total_time_with_estimates(self) -> None:
        """Test total time with estimates."""
        timeline = ProgressTimeline()
        timeline._steps = [
            TimelineStep("step1", "pending", estimated_seconds=15.0),
            TimelineStep("step2", "pending", estimated_seconds=25.0),
        ]

        assert timeline._get_total_time() == 40.0

    def test_total_time_mixed(self) -> None:
        """Test total time with mixed durations and estimates."""
        timeline = ProgressTimeline()
        timeline._steps = [
            TimelineStep("step1", "completed", duration_seconds=10.0),
            TimelineStep("step2", "pending", estimated_seconds=20.0),
            TimelineStep("step3", "pending"),  # Default 1.0
        ]

        assert timeline._get_total_time() == 31.0


class TestProgressTimelineProperties:
    """Tests for ProgressTimeline property methods."""

    def test_total_duration_empty(self) -> None:
        """Test total_duration with no steps."""
        timeline = ProgressTimeline()
        timeline._steps = []

        assert timeline.total_duration == 0.0

    def test_total_duration_with_completed_steps(self) -> None:
        """Test total_duration sums completed step durations."""
        timeline = ProgressTimeline()
        timeline._steps = [
            TimelineStep("step1", "completed", duration_seconds=10.0),
            TimelineStep("step2", "completed", duration_seconds=20.0),
            TimelineStep("step3", "pending", estimated_seconds=30.0),
        ]

        # Only completed steps with durations
        assert timeline.total_duration == 30.0

    def test_total_duration_no_durations(self) -> None:
        """Test total_duration when no steps have durations."""
        timeline = ProgressTimeline()
        timeline._steps = [
            TimelineStep("step1", "completed"),
            TimelineStep("step2", "pending"),
        ]

        assert timeline.total_duration == 0.0

    def test_estimated_remaining_empty(self) -> None:
        """Test estimated_remaining with no steps."""
        timeline = ProgressTimeline()
        timeline._steps = []

        assert timeline.estimated_remaining == 0.0

    def test_estimated_remaining_with_pending_steps(self) -> None:
        """Test estimated_remaining sums pending and running estimates."""
        timeline = ProgressTimeline()
        timeline._steps = [
            TimelineStep("step1", "completed", duration_seconds=10.0),
            TimelineStep("step2", "running", estimated_seconds=20.0),
            TimelineStep("step3", "pending", estimated_seconds=30.0),
        ]

        assert timeline.estimated_remaining == 50.0

    def test_estimated_remaining_default_estimate(self) -> None:
        """Test estimated_remaining uses default for missing estimates."""
        timeline = ProgressTimeline()
        timeline._steps = [
            TimelineStep("step1", "completed"),
            TimelineStep("step2", "running"),  # Default 1.0
            TimelineStep("step3", "pending"),  # Default 1.0
        ]

        assert timeline.estimated_remaining == 2.0


class TestProgressTimelineCreation:
    """Tests for ProgressTimeline widget creation."""

    def test_creation_with_defaults(self) -> None:
        """Test creating ProgressTimeline with default options."""
        timeline = ProgressTimeline()

        assert timeline._steps == []
        assert timeline._show_labels is True
        assert timeline._show_durations is True

    def test_creation_with_custom_options(self) -> None:
        """Test creating ProgressTimeline with custom options."""
        timeline = ProgressTimeline(
            show_labels=False, show_durations=False, id="my-timeline"
        )

        assert timeline._show_labels is False
        assert timeline._show_durations is False
        assert timeline.id == "my-timeline"

    def test_set_steps_updates_internal_list(self) -> None:
        """Test set_steps updates the internal steps list."""
        timeline = ProgressTimeline()
        steps = [
            TimelineStep("step1", "pending"),
            TimelineStep("step2", "pending"),
        ]

        timeline.set_steps(steps)

        assert len(timeline._steps) == 2
        assert timeline._steps[0].name == "step1"
        assert timeline._steps[1].name == "step2"


class TestProgressTimelineSetAndUpdate:
    """Tests for set_steps and update_step without mounting."""

    def test_set_steps_updates_internal_list(self) -> None:
        """Test set_steps stores steps internally."""
        timeline = ProgressTimeline()
        steps = [
            TimelineStep("validate", "completed", duration_seconds=1.5),
            TimelineStep("implement", "running", estimated_seconds=30),
            TimelineStep("review", "pending", estimated_seconds=10),
        ]
        timeline.set_steps(steps)

        assert len(timeline._steps) == 3
        assert timeline._steps[0].name == "validate"

    def test_update_step_changes_status(self) -> None:
        """Test update_step can change a step's status."""
        timeline = ProgressTimeline()
        steps = [
            TimelineStep("validate", "pending"),
            TimelineStep("implement", "pending"),
        ]
        timeline.set_steps(steps)

        # Update status (won't trigger display update since not mounted)
        timeline.update_step("validate", status="completed")

        assert timeline._steps[0].status == "completed"
        assert timeline._steps[1].status == "pending"

    def test_update_step_changes_duration(self) -> None:
        """Test update_step can set duration."""
        timeline = ProgressTimeline()
        steps = [TimelineStep("validate", "running")]
        timeline.set_steps(steps)

        # Update duration
        timeline.update_step("validate", duration_seconds=5.5)

        assert timeline._steps[0].duration_seconds == 5.5

    def test_update_step_nonexistent_step(self) -> None:
        """Test update_step handles nonexistent step gracefully."""
        timeline = ProgressTimeline()
        steps = [TimelineStep("validate", "pending")]
        timeline.set_steps(steps)

        # Should not raise
        timeline.update_step("nonexistent", status="completed")

        # Original step unchanged
        assert timeline._steps[0].status == "pending"
