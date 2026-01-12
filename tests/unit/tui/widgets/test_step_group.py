"""Unit tests for StepGroup widget and related dataclasses.

This test module covers:
- StepGroupStatus enum
- StepSummary dataclass and properties
- StepGroup widget creation and methods
- Auto-collapse behavior
- Duration formatting

Feature: 030-tui-execution-visibility
Date: 2026-01-12
"""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult

from maverick.tui.widgets.step_group import StepGroup, StepGroupStatus, StepSummary


class TestStepGroupStatus:
    """Tests for StepGroupStatus enum."""

    def test_all_status_values(self) -> None:
        """Test all status values are defined."""
        assert StepGroupStatus.PENDING == "pending"
        assert StepGroupStatus.RUNNING == "running"
        assert StepGroupStatus.COMPLETED == "completed"
        assert StepGroupStatus.FAILED == "failed"
        assert StepGroupStatus.MIXED == "mixed"

    def test_status_is_string(self) -> None:
        """Test StepGroupStatus is a string enum."""
        assert isinstance(StepGroupStatus.PENDING, str)
        assert StepGroupStatus.COMPLETED.value == "completed"


class TestStepSummary:
    """Tests for StepSummary dataclass."""

    def test_creation_with_all_fields(self) -> None:
        """Test creating StepSummary with all fields."""
        summary = StepSummary(total=10, completed=5, failed=2, running=1, pending=2)

        assert summary.total == 10
        assert summary.completed == 5
        assert summary.failed == 2
        assert summary.running == 1
        assert summary.pending == 2

    def test_status_all_pending(self) -> None:
        """Test status property when all steps pending."""
        summary = StepSummary(total=5, completed=0, failed=0, running=0, pending=5)
        assert summary.status == StepGroupStatus.PENDING

    def test_status_running(self) -> None:
        """Test status property when step is running."""
        summary = StepSummary(total=5, completed=2, failed=0, running=1, pending=2)
        assert summary.status == StepGroupStatus.RUNNING

    def test_status_all_completed(self) -> None:
        """Test status property when all steps completed."""
        summary = StepSummary(total=5, completed=5, failed=0, running=0, pending=0)
        assert summary.status == StepGroupStatus.COMPLETED

    def test_status_all_failed(self) -> None:
        """Test status property when all steps failed."""
        summary = StepSummary(total=5, completed=0, failed=5, running=0, pending=0)
        assert summary.status == StepGroupStatus.FAILED

    def test_status_mixed(self) -> None:
        """Test status property with mixed completed and failed."""
        summary = StepSummary(total=5, completed=3, failed=2, running=0, pending=0)
        assert summary.status == StepGroupStatus.MIXED

    def test_status_running_takes_precedence(self) -> None:
        """Test running status takes precedence over others."""
        summary = StepSummary(total=5, completed=2, failed=1, running=1, pending=1)
        assert summary.status == StepGroupStatus.RUNNING

    def test_display_text_all_pending(self) -> None:
        """Test display_text when all pending."""
        summary = StepSummary(total=3, completed=0, failed=0, running=0, pending=3)
        assert "3 pending" in summary.display_text
        assert "dim" in summary.display_text

    def test_display_text_mixed(self) -> None:
        """Test display_text with mixed statuses."""
        summary = StepSummary(total=4, completed=2, failed=1, running=1, pending=0)
        text = summary.display_text

        assert "2 completed" in text
        assert "green" in text
        assert "1 failed" in text
        assert "red" in text
        assert "1 running" in text
        assert "yellow" in text

    def test_display_text_empty(self) -> None:
        """Test display_text with no steps."""
        summary = StepSummary(total=0, completed=0, failed=0, running=0, pending=0)
        assert "No steps" in summary.display_text

    def test_summary_is_frozen(self) -> None:
        """Test that StepSummary is immutable (frozen dataclass)."""
        summary = StepSummary(total=5, completed=2, failed=1, running=1, pending=1)

        with pytest.raises(Exception):  # FrozenInstanceError
            summary.total = 10  # type: ignore[misc]


class TestStepGroupFormatDuration:
    """Tests for StepGroup._format_duration method."""

    def test_format_none(self) -> None:
        """Test formatting None duration."""
        group = StepGroup("Test")
        assert group._format_duration(None) == ""

    def test_format_milliseconds(self) -> None:
        """Test formatting sub-second durations."""
        group = StepGroup("Test")
        assert group._format_duration(0.5) == "500ms"
        assert group._format_duration(0.1) == "100ms"

    def test_format_seconds(self) -> None:
        """Test formatting second durations."""
        group = StepGroup("Test")
        assert group._format_duration(1.0) == "1.0s"
        assert group._format_duration(30.5) == "30.5s"

    def test_format_minutes(self) -> None:
        """Test formatting minute durations."""
        group = StepGroup("Test")
        assert group._format_duration(60.0) == "1m0s"
        assert group._format_duration(90.0) == "1m30s"


class TestStepGroupCreation:
    """Tests for StepGroup widget creation."""

    def test_creation_with_name_only(self) -> None:
        """Test creating StepGroup with name only."""
        group = StepGroup("Implementation")

        assert group._group_name == "Implementation"
        assert group._auto_collapse is True
        assert group.collapsed is False
        assert group._steps == {}

    def test_creation_with_options(self) -> None:
        """Test creating StepGroup with custom options."""
        group = StepGroup(
            "Validation",
            auto_collapse=False,
            initially_collapsed=True,
            id="val-group",
        )

        assert group._group_name == "Validation"
        assert group._auto_collapse is False
        assert group.collapsed is True
        assert group.id == "val-group"

    def test_add_step_creates_entry(self) -> None:
        """Test add_step creates step entry."""
        group = StepGroup("Test")
        group.add_step("validate", "pending")

        assert "validate" in group._steps
        assert group._steps["validate"] == "pending"

    def test_add_step_default_status(self) -> None:
        """Test add_step default status is pending."""
        group = StepGroup("Test")
        group.add_step("implement")

        assert group._steps["implement"] == "pending"

    def test_update_step_changes_status(self) -> None:
        """Test update_step changes step status."""
        group = StepGroup("Test")
        group.add_step("validate", "pending")
        group.update_step("validate", "completed")

        assert group._steps["validate"] == "completed"

    def test_update_step_with_duration(self) -> None:
        """Test update_step can set duration."""
        group = StepGroup("Test")
        group.add_step("validate", "pending")
        group.update_step("validate", "completed", duration=5.5)

        assert group._steps["validate"] == "completed"
        assert group._step_durations["validate"] == 5.5

    def test_update_step_nonexistent_adds_step(self) -> None:
        """Test update_step on nonexistent step adds it."""
        group = StepGroup("Test")
        group.update_step("new_step", "running")

        assert "new_step" in group._steps
        assert group._steps["new_step"] == "running"

    def test_remove_step(self) -> None:
        """Test remove_step removes step."""
        group = StepGroup("Test")
        group.add_step("validate", "completed")
        group.add_step("implement", "pending")

        group.remove_step("validate")

        assert "validate" not in group._steps
        assert "implement" in group._steps

    def test_remove_step_nonexistent(self) -> None:
        """Test remove_step handles nonexistent step gracefully."""
        group = StepGroup("Test")
        # Should not raise
        group.remove_step("nonexistent")

    def test_summary_property(self) -> None:
        """Test summary property returns StepSummary."""
        group = StepGroup("Test")
        group.add_step("step1", "completed")
        group.add_step("step2", "running")
        group.add_step("step3", "pending")

        summary = group.summary

        assert summary.total == 3
        assert summary.completed == 1
        assert summary.running == 1
        assert summary.pending == 1

    def test_total_duration_property(self) -> None:
        """Test total_duration property sums durations."""
        group = StepGroup("Test")
        group.add_step("step1", "completed")
        group._step_durations["step1"] = 10.0
        group.add_step("step2", "completed")
        group._step_durations["step2"] = 20.0

        assert group.total_duration == 30.0

    def test_total_duration_empty(self) -> None:
        """Test total_duration with no durations."""
        group = StepGroup("Test")
        assert group.total_duration == 0.0


class TestStepGroupMessages:
    """Tests for StepGroup message classes."""

    def test_step_status_changed_message(self) -> None:
        """Test StepStatusChanged message attributes."""
        msg = StepGroup.StepStatusChanged("Implementation", "validate", "completed")

        assert msg.group_name == "Implementation"
        assert msg.step_name == "validate"
        assert msg.status == "completed"

    def test_group_expanded_message(self) -> None:
        """Test GroupExpanded message attributes."""
        msg = StepGroup.GroupExpanded("Implementation")

        assert msg.group_name == "Implementation"

    def test_group_collapsed_message(self) -> None:
        """Test GroupCollapsed message attributes."""
        msg = StepGroup.GroupCollapsed("Implementation")

        assert msg.group_name == "Implementation"


class _StepGroupTestApp(App):
    """Test app for StepGroup widget testing."""

    def __init__(
        self,
        group_name: str = "Test Group",
        auto_collapse: bool = True,
        initially_collapsed: bool = False,
    ):
        super().__init__()
        self._group_name = group_name
        self._auto_collapse = auto_collapse
        self._initially_collapsed = initially_collapsed

    def compose(self) -> ComposeResult:
        yield StepGroup(
            self._group_name,
            auto_collapse=self._auto_collapse,
            initially_collapsed=self._initially_collapsed,
            id="test-group",
        )


class TestStepGroupMounted:
    """Tests for StepGroup when mounted in an app."""

    @pytest.mark.asyncio
    async def test_widget_mounts_successfully(self) -> None:
        """Test StepGroup can be mounted in an app."""
        async with _StepGroupTestApp().run_test() as pilot:
            group = pilot.app.query_one(StepGroup)
            assert group is not None

    @pytest.mark.asyncio
    async def test_add_step_when_mounted(self) -> None:
        """Test add_step works when widget is mounted."""
        async with _StepGroupTestApp().run_test() as pilot:
            group = pilot.app.query_one(StepGroup)

            group.add_step("validate", "pending")
            group.add_step("implement", "pending")
            await pilot.pause()

            assert len(group._steps) == 2

    @pytest.mark.asyncio
    async def test_update_step_when_mounted(self) -> None:
        """Test update_step works when widget is mounted."""
        async with _StepGroupTestApp().run_test() as pilot:
            group = pilot.app.query_one(StepGroup)

            group.add_step("validate", "pending")
            await pilot.pause()

            group.update_step("validate", "completed", duration=1.5)
            await pilot.pause()

            assert group._steps["validate"] == "completed"
            assert group._step_durations["validate"] == 1.5

    @pytest.mark.asyncio
    async def test_expand_group(self) -> None:
        """Test expand_group method."""
        async with _StepGroupTestApp(initially_collapsed=True).run_test() as pilot:
            group = pilot.app.query_one(StepGroup)

            assert group.collapsed is True

            group.expand_group()
            await pilot.pause()

            assert group.collapsed is False

    @pytest.mark.asyncio
    async def test_collapse_group(self) -> None:
        """Test collapse_group method."""
        async with _StepGroupTestApp(initially_collapsed=False).run_test() as pilot:
            group = pilot.app.query_one(StepGroup)

            assert group.collapsed is False

            group.collapse_group()
            await pilot.pause()

            assert group.collapsed is True

    @pytest.mark.asyncio
    async def test_auto_collapse_on_all_completed(self) -> None:
        """Test auto-collapse when all steps complete."""
        async with _StepGroupTestApp(auto_collapse=True).run_test() as pilot:
            group = pilot.app.query_one(StepGroup)

            group.add_step("step1", "completed")
            group.add_step("step2", "running")
            await pilot.pause()

            assert group.collapsed is False

            # Complete the running step
            group.update_step("step2", "completed")
            await pilot.pause()

            assert group.collapsed is True

    @pytest.mark.asyncio
    async def test_auto_expand_on_failure(self) -> None:
        """Test auto-expand when a step fails."""
        async with _StepGroupTestApp(
            auto_collapse=True, initially_collapsed=True
        ).run_test() as pilot:
            group = pilot.app.query_one(StepGroup)

            # Start collapsed
            assert group.collapsed is True

            # Add a step and mark it failed - should auto-expand
            group.add_step("step1", "pending")
            group.update_step("step1", "failed")
            await pilot.pause()

            # Should expand on failure
            assert group.collapsed is False

    @pytest.mark.asyncio
    async def test_auto_expand_on_running(self) -> None:
        """Test auto-expand when a step starts running."""
        async with _StepGroupTestApp(
            auto_collapse=True, initially_collapsed=True
        ).run_test() as pilot:
            group = pilot.app.query_one(StepGroup)
            assert group.collapsed is True

            group.add_step("step1", "pending")
            group.update_step("step1", "running")
            await pilot.pause()

            # Should expand when step starts running
            assert group.collapsed is False

    @pytest.mark.asyncio
    async def test_no_auto_collapse_when_disabled(self) -> None:
        """Test no auto-collapse when auto_collapse=False."""
        async with _StepGroupTestApp(auto_collapse=False).run_test() as pilot:
            group = pilot.app.query_one(StepGroup)

            group.add_step("step1", "pending")
            group.update_step("step1", "completed")
            await pilot.pause()

            # Should not auto-collapse
            assert group.collapsed is False

    @pytest.mark.asyncio
    async def test_status_class_applied(self) -> None:
        """Test status CSS class is applied."""
        async with _StepGroupTestApp().run_test() as pilot:
            group = pilot.app.query_one(StepGroup)

            # Initially pending
            group.add_step("step1", "pending")
            await pilot.pause()
            assert group.has_class("status-pending")

            # Update to running
            group.update_step("step1", "running")
            await pilot.pause()
            assert group.has_class("status-running")

            # Update to completed
            group.update_step("step1", "completed")
            await pilot.pause()
            assert group.has_class("status-completed")
