"""Unit tests for IterationProgress widget and related dataclasses.

This test module covers:

T008 (TDD): LoopIterationItem and LoopIterationState dataclasses
  - Tests should FAIL until implementation is added to:
    src/maverick/tui/models/widget_state.py

T009 (TDD): IterationProgress widget rendering
  - Tests should FAIL until implementation is added to:
    src/maverick/tui/widgets/iteration_progress.py

Test coverage includes:
- LoopIterationItem creation with required/optional fields
- LoopIterationItem display_text property
- LoopIterationState creation and iteration tracking methods
- LoopIterationState current_iteration and progress_fraction properties
- IterationProgress widget creation with state
- Widget rendering with mixed statuses (completed, running, pending, etc.)
- Status icon display for all 6 IterationStatus values
- Nested loop indentation (2 spaces per nesting level)
- Empty state display ("No iterations" indicator)
- Duration display in completed/failed iterations
- Widget update_state method
"""

from __future__ import annotations

import time

import pytest

from maverick.tui.models.enums import IterationStatus
from maverick.tui.models.widget_state import LoopIterationItem, LoopIterationState


class TestLoopIterationItem:
    """Tests for LoopIterationItem dataclass."""

    def test_creation_with_required_fields(self) -> None:
        """Test creating LoopIterationItem with required fields only."""
        item = LoopIterationItem(
            index=0,
            total=3,
            label="Phase 1: Setup",
            status=IterationStatus.PENDING,
        )

        assert item.index == 0
        assert item.total == 3
        assert item.label == "Phase 1: Setup"
        assert item.status == IterationStatus.PENDING
        assert item.duration_ms is None
        assert item.error is None
        assert item.started_at is None
        assert item.completed_at is None

    def test_creation_with_all_fields(self) -> None:
        """Test creating LoopIterationItem with all fields."""
        now = time.time()
        item = LoopIterationItem(
            index=1,
            total=5,
            label="Phase 2: Core Implementation",
            status=IterationStatus.COMPLETED,
            duration_ms=1500,
            error=None,
            started_at=now - 1.5,
            completed_at=now,
        )

        assert item.index == 1
        assert item.total == 5
        assert item.label == "Phase 2: Core Implementation"
        assert item.status == IterationStatus.COMPLETED
        assert item.duration_ms == 1500
        assert item.error is None
        assert item.started_at == pytest.approx(now - 1.5, rel=1e-3)
        assert item.completed_at == pytest.approx(now, rel=1e-3)

    def test_creation_with_error(self) -> None:
        """Test creating LoopIterationItem with error state."""
        item = LoopIterationItem(
            index=2,
            total=3,
            label="Phase 3: Integration",
            status=IterationStatus.FAILED,
            duration_ms=500,
            error="Validation failed: missing required field",
        )

        assert item.status == IterationStatus.FAILED
        assert item.error == "Validation failed: missing required field"
        assert item.duration_ms == 500

    def test_display_text_property_first_iteration(self) -> None:
        """Test display_text property for first iteration (index 0)."""
        item = LoopIterationItem(
            index=0,
            total=3,
            label="Phase 1: Setup",
            status=IterationStatus.RUNNING,
        )

        # Expected format: "{index+1}/{total}: {label}"
        assert item.display_text == "1/3: Phase 1: Setup"

    def test_display_text_property_middle_iteration(self) -> None:
        """Test display_text property for middle iteration."""
        item = LoopIterationItem(
            index=1,
            total=5,
            label="Core Data Structures",
            status=IterationStatus.PENDING,
        )

        assert item.display_text == "2/5: Core Data Structures"

    def test_display_text_property_last_iteration(self) -> None:
        """Test display_text property for last iteration."""
        item = LoopIterationItem(
            index=4,
            total=5,
            label="Cleanup and Finalization",
            status=IterationStatus.COMPLETED,
        )

        assert item.display_text == "5/5: Cleanup and Finalization"

    def test_all_iteration_statuses(self) -> None:
        """Test LoopIterationItem accepts all IterationStatus values."""
        statuses = [
            IterationStatus.PENDING,
            IterationStatus.RUNNING,
            IterationStatus.COMPLETED,
            IterationStatus.FAILED,
            IterationStatus.SKIPPED,
            IterationStatus.CANCELLED,
        ]

        for status in statuses:
            item = LoopIterationItem(
                index=0,
                total=1,
                label="Test",
                status=status,
            )
            assert item.status == status

    def test_item_is_mutable(self) -> None:
        """Test LoopIterationItem is mutable (not frozen)."""
        item = LoopIterationItem(
            index=0,
            total=3,
            label="Phase 1",
            status=IterationStatus.PENDING,
        )

        # Should allow modification
        item.status = IterationStatus.RUNNING
        assert item.status == IterationStatus.RUNNING

        item.started_at = time.time()
        assert item.started_at is not None

        item.duration_ms = 100
        assert item.duration_ms == 100


class TestLoopIterationState:
    """Tests for LoopIterationState dataclass."""

    def test_creation_with_required_fields(self) -> None:
        """Test creating LoopIterationState with required fields."""
        state = LoopIterationState(
            step_name="implement_by_phase",
            iterations=[],
        )

        assert state.step_name == "implement_by_phase"
        assert state.iterations == []
        assert state.nesting_level == 0
        assert state.expanded is True

    def test_creation_with_all_fields(self) -> None:
        """Test creating LoopIterationState with all fields."""
        iterations = [
            LoopIterationItem(
                index=0,
                total=2,
                label="Phase 1",
                status=IterationStatus.COMPLETED,
            ),
            LoopIterationItem(
                index=1,
                total=2,
                label="Phase 2",
                status=IterationStatus.PENDING,
            ),
        ]

        state = LoopIterationState(
            step_name="review_loop",
            iterations=iterations,
            nesting_level=1,
            expanded=False,
        )

        assert state.step_name == "review_loop"
        assert len(state.iterations) == 2
        assert state.nesting_level == 1
        assert state.expanded is False

    def test_get_iteration_valid_index(self) -> None:
        """Test get_iteration returns iteration for valid index."""
        iterations = [
            LoopIterationItem(
                index=0, total=3, label="Phase 1", status=IterationStatus.COMPLETED
            ),
            LoopIterationItem(
                index=1, total=3, label="Phase 2", status=IterationStatus.RUNNING
            ),
            LoopIterationItem(
                index=2, total=3, label="Phase 3", status=IterationStatus.PENDING
            ),
        ]

        state = LoopIterationState(step_name="test_loop", iterations=iterations)

        result = state.get_iteration(1)
        assert result is not None
        assert result.label == "Phase 2"
        assert result.status == IterationStatus.RUNNING

    def test_get_iteration_first_index(self) -> None:
        """Test get_iteration returns first iteration."""
        iterations = [
            LoopIterationItem(
                index=0, total=2, label="First", status=IterationStatus.COMPLETED
            ),
            LoopIterationItem(
                index=1, total=2, label="Second", status=IterationStatus.PENDING
            ),
        ]

        state = LoopIterationState(step_name="test_loop", iterations=iterations)

        result = state.get_iteration(0)
        assert result is not None
        assert result.label == "First"

    def test_get_iteration_last_index(self) -> None:
        """Test get_iteration returns last iteration."""
        iterations = [
            LoopIterationItem(
                index=0, total=2, label="First", status=IterationStatus.COMPLETED
            ),
            LoopIterationItem(
                index=1, total=2, label="Last", status=IterationStatus.PENDING
            ),
        ]

        state = LoopIterationState(step_name="test_loop", iterations=iterations)

        result = state.get_iteration(1)
        assert result is not None
        assert result.label == "Last"

    def test_get_iteration_invalid_index_negative(self) -> None:
        """Test get_iteration returns None for negative index."""
        iterations = [
            LoopIterationItem(
                index=0, total=1, label="Only", status=IterationStatus.PENDING
            ),
        ]

        state = LoopIterationState(step_name="test_loop", iterations=iterations)

        result = state.get_iteration(-1)
        assert result is None

    def test_get_iteration_invalid_index_too_high(self) -> None:
        """Test get_iteration returns None for index >= len(iterations)."""
        iterations = [
            LoopIterationItem(
                index=0, total=2, label="First", status=IterationStatus.COMPLETED
            ),
            LoopIterationItem(
                index=1, total=2, label="Second", status=IterationStatus.PENDING
            ),
        ]

        state = LoopIterationState(step_name="test_loop", iterations=iterations)

        result = state.get_iteration(2)
        assert result is None

        result = state.get_iteration(100)
        assert result is None

    def test_get_iteration_empty_list(self) -> None:
        """Test get_iteration returns None for empty iterations list."""
        state = LoopIterationState(step_name="empty_loop", iterations=[])

        result = state.get_iteration(0)
        assert result is None

    def test_current_iteration_property_with_running(self) -> None:
        """Test current_iteration returns the running iteration."""
        iterations = [
            LoopIterationItem(
                index=0, total=3, label="Phase 1", status=IterationStatus.COMPLETED
            ),
            LoopIterationItem(
                index=1, total=3, label="Phase 2", status=IterationStatus.RUNNING
            ),
            LoopIterationItem(
                index=2, total=3, label="Phase 3", status=IterationStatus.PENDING
            ),
        ]

        state = LoopIterationState(step_name="test_loop", iterations=iterations)

        current = state.current_iteration
        assert current is not None
        assert current.index == 1
        assert current.label == "Phase 2"
        assert current.status == IterationStatus.RUNNING

    def test_current_iteration_property_no_running(self) -> None:
        """Test current_iteration returns None when no iteration is running."""
        iterations = [
            LoopIterationItem(
                index=0, total=2, label="Phase 1", status=IterationStatus.COMPLETED
            ),
            LoopIterationItem(
                index=1, total=2, label="Phase 2", status=IterationStatus.PENDING
            ),
        ]

        state = LoopIterationState(step_name="test_loop", iterations=iterations)

        assert state.current_iteration is None

    def test_current_iteration_property_all_completed(self) -> None:
        """Test current_iteration returns None when all iterations completed."""
        iterations = [
            LoopIterationItem(
                index=0, total=2, label="Phase 1", status=IterationStatus.COMPLETED
            ),
            LoopIterationItem(
                index=1, total=2, label="Phase 2", status=IterationStatus.COMPLETED
            ),
        ]

        state = LoopIterationState(step_name="test_loop", iterations=iterations)

        assert state.current_iteration is None

    def test_current_iteration_property_empty_list(self) -> None:
        """Test current_iteration returns None for empty iterations."""
        state = LoopIterationState(step_name="empty_loop", iterations=[])

        assert state.current_iteration is None

    def test_progress_fraction_property_zero_completed(self) -> None:
        """Test progress_fraction returns 0.0 when no iterations completed."""
        iterations = [
            LoopIterationItem(
                index=0, total=3, label="Phase 1", status=IterationStatus.PENDING
            ),
            LoopIterationItem(
                index=1, total=3, label="Phase 2", status=IterationStatus.PENDING
            ),
            LoopIterationItem(
                index=2, total=3, label="Phase 3", status=IterationStatus.PENDING
            ),
        ]

        state = LoopIterationState(step_name="test_loop", iterations=iterations)

        assert state.progress_fraction == 0.0

    def test_progress_fraction_property_partial_completed(self) -> None:
        """Test progress_fraction returns correct fraction for partial completion."""
        iterations = [
            LoopIterationItem(
                index=0, total=4, label="Phase 1", status=IterationStatus.COMPLETED
            ),
            LoopIterationItem(
                index=1, total=4, label="Phase 2", status=IterationStatus.COMPLETED
            ),
            LoopIterationItem(
                index=2, total=4, label="Phase 3", status=IterationStatus.RUNNING
            ),
            LoopIterationItem(
                index=3, total=4, label="Phase 4", status=IterationStatus.PENDING
            ),
        ]

        state = LoopIterationState(step_name="test_loop", iterations=iterations)

        # 2 completed out of 4
        assert state.progress_fraction == 0.5

    def test_progress_fraction_property_all_completed(self) -> None:
        """Test progress_fraction returns 1.0 when all iterations completed."""
        iterations = [
            LoopIterationItem(
                index=0, total=3, label="Phase 1", status=IterationStatus.COMPLETED
            ),
            LoopIterationItem(
                index=1, total=3, label="Phase 2", status=IterationStatus.COMPLETED
            ),
            LoopIterationItem(
                index=2, total=3, label="Phase 3", status=IterationStatus.COMPLETED
            ),
        ]

        state = LoopIterationState(step_name="test_loop", iterations=iterations)

        assert state.progress_fraction == 1.0

    def test_progress_fraction_property_includes_failed(self) -> None:
        """Test progress_fraction counts failed iterations as completed."""
        iterations = [
            LoopIterationItem(
                index=0, total=3, label="Phase 1", status=IterationStatus.COMPLETED
            ),
            LoopIterationItem(
                index=1, total=3, label="Phase 2", status=IterationStatus.FAILED
            ),
            LoopIterationItem(
                index=2, total=3, label="Phase 3", status=IterationStatus.PENDING
            ),
        ]

        state = LoopIterationState(step_name="test_loop", iterations=iterations)

        # 2 (completed + failed) out of 3
        assert state.progress_fraction == pytest.approx(2 / 3)

    def test_progress_fraction_property_includes_skipped(self) -> None:
        """Test progress_fraction counts skipped iterations as completed."""
        iterations = [
            LoopIterationItem(
                index=0, total=4, label="Phase 1", status=IterationStatus.SKIPPED
            ),
            LoopIterationItem(
                index=1, total=4, label="Phase 2", status=IterationStatus.COMPLETED
            ),
            LoopIterationItem(
                index=2, total=4, label="Phase 3", status=IterationStatus.RUNNING
            ),
            LoopIterationItem(
                index=3, total=4, label="Phase 4", status=IterationStatus.PENDING
            ),
        ]

        state = LoopIterationState(step_name="test_loop", iterations=iterations)

        # 2 (skipped + completed) out of 4
        assert state.progress_fraction == 0.5

    def test_progress_fraction_property_mixed_terminal_states(self) -> None:
        """Test progress_fraction counts all terminal states."""
        iterations = [
            LoopIterationItem(
                index=0, total=5, label="Phase 1", status=IterationStatus.COMPLETED
            ),
            LoopIterationItem(
                index=1, total=5, label="Phase 2", status=IterationStatus.FAILED
            ),
            LoopIterationItem(
                index=2, total=5, label="Phase 3", status=IterationStatus.SKIPPED
            ),
            LoopIterationItem(
                index=3, total=5, label="Phase 4", status=IterationStatus.RUNNING
            ),
            LoopIterationItem(
                index=4, total=5, label="Phase 5", status=IterationStatus.PENDING
            ),
        ]

        state = LoopIterationState(step_name="test_loop", iterations=iterations)

        # 3 (completed + failed + skipped) out of 5
        assert state.progress_fraction == 0.6

    def test_progress_fraction_property_empty_list(self) -> None:
        """Test progress_fraction returns 0.0 for empty iterations."""
        state = LoopIterationState(step_name="empty_loop", iterations=[])

        assert state.progress_fraction == 0.0

    def test_progress_fraction_property_single_iteration(self) -> None:
        """Test progress_fraction with single iteration."""
        state_pending = LoopIterationState(
            step_name="single_loop",
            iterations=[
                LoopIterationItem(
                    index=0, total=1, label="Only", status=IterationStatus.PENDING
                )
            ],
        )
        assert state_pending.progress_fraction == 0.0

        state_completed = LoopIterationState(
            step_name="single_loop",
            iterations=[
                LoopIterationItem(
                    index=0, total=1, label="Only", status=IterationStatus.COMPLETED
                )
            ],
        )
        assert state_completed.progress_fraction == 1.0

    def test_state_is_mutable(self) -> None:
        """Test LoopIterationState is mutable (not frozen)."""
        state = LoopIterationState(
            step_name="test_loop",
            iterations=[],
        )

        # Should allow modification
        state.expanded = False
        assert state.expanded is False

        state.nesting_level = 2
        assert state.nesting_level == 2

        # Should allow adding iterations
        state.iterations.append(
            LoopIterationItem(
                index=0, total=1, label="New", status=IterationStatus.PENDING
            )
        )
        assert len(state.iterations) == 1

    def test_nested_loop_nesting_level(self) -> None:
        """Test nesting_level for nested loops."""
        # Top-level loop
        outer_state = LoopIterationState(
            step_name="outer_loop",
            iterations=[],
            nesting_level=0,
        )

        # Nested loop
        inner_state = LoopIterationState(
            step_name="inner_loop",
            iterations=[],
            nesting_level=1,
        )

        # Deeply nested loop
        deep_state = LoopIterationState(
            step_name="deep_loop",
            iterations=[],
            nesting_level=2,
        )

        assert outer_state.nesting_level == 0
        assert inner_state.nesting_level == 1
        assert deep_state.nesting_level == 2


# =============================================================================
# T009: Unit Tests for IterationProgress Widget Rendering
# =============================================================================


def _create_test_app(state):
    """Create a test app for IterationProgress widget testing.

    Factory function to avoid import issues when the widget module doesn't exist
    yet (TDD pattern).
    """
    from textual.app import App

    from maverick.tui.widgets.iteration_progress import IterationProgress

    class IterationProgressTestApp(App):
        """Test app for IterationProgress widget testing."""

        def __init__(self, test_state=None):
            super().__init__()
            self._test_state = test_state

        def compose(self):
            """Compose the test app with IterationProgress widget."""
            if self._test_state is not None:
                yield IterationProgress(self._test_state)

    return IterationProgressTestApp(state)


class TestIterationProgressWidgetCreation:
    """Tests for IterationProgress widget creation."""

    @pytest.mark.asyncio
    async def test_widget_creation_with_state(self) -> None:
        """Test IterationProgress widget can be created with state."""
        from maverick.tui.widgets.iteration_progress import IterationProgress

        state = LoopIterationState(
            step_name="test_loop",
            iterations=[
                LoopIterationItem(0, 3, "Item 1", IterationStatus.PENDING),
            ],
        )

        widget = IterationProgress(state)
        assert widget._state == state

    @pytest.mark.asyncio
    async def test_widget_mounts_in_app(self) -> None:
        """Test IterationProgress widget can be mounted in an app."""
        from maverick.tui.widgets.iteration_progress import IterationProgress

        state = LoopIterationState(
            step_name="test_loop",
            iterations=[
                LoopIterationItem(0, 2, "Task 1", IterationStatus.PENDING),
                LoopIterationItem(1, 2, "Task 2", IterationStatus.PENDING),
            ],
        )

        async with _create_test_app(state).run_test() as pilot:
            widget = pilot.app.query_one(IterationProgress)
            assert widget is not None
            assert widget._state == state


class TestIterationProgressRendering:
    """Tests for IterationProgress widget rendering with mixed statuses."""

    @pytest.mark.asyncio
    async def test_render_iterations_with_mixed_statuses(self) -> None:
        """Test rendering iterations with completed, running, and pending statuses."""
        from maverick.tui.widgets.iteration_progress import IterationProgress

        state = LoopIterationState(
            step_name="test_loop",
            iterations=[
                LoopIterationItem(0, 3, "Item 1", IterationStatus.COMPLETED),
                LoopIterationItem(1, 3, "Item 2", IterationStatus.RUNNING),
                LoopIterationItem(2, 3, "Item 3", IterationStatus.PENDING),
            ],
        )

        async with _create_test_app(state).run_test() as pilot:
            widget = pilot.app.query_one(IterationProgress)
            await pilot.pause()

            # Verify all iterations are rendered
            assert len(widget._state.iterations) == 3

            # Check that appropriate CSS classes are applied
            completed_items = widget.query(".iteration-completed")
            running_items = widget.query(".iteration-running")
            pending_items = widget.query(".iteration-pending")

            assert len(completed_items) >= 1
            assert len(running_items) >= 1
            assert len(pending_items) >= 1

    @pytest.mark.asyncio
    async def test_render_all_status_types(self) -> None:
        """Test rendering with all iteration status types."""
        from maverick.tui.widgets.iteration_progress import IterationProgress

        state = LoopIterationState(
            step_name="test_loop",
            iterations=[
                LoopIterationItem(0, 6, "Task 1", IterationStatus.COMPLETED),
                LoopIterationItem(1, 6, "Task 2", IterationStatus.RUNNING),
                LoopIterationItem(2, 6, "Task 3", IterationStatus.PENDING),
                LoopIterationItem(3, 6, "Task 4", IterationStatus.FAILED),
                LoopIterationItem(4, 6, "Task 5", IterationStatus.SKIPPED),
                LoopIterationItem(5, 6, "Task 6", IterationStatus.CANCELLED),
            ],
        )

        async with _create_test_app(state).run_test() as pilot:
            widget = pilot.app.query_one(IterationProgress)
            await pilot.pause()

            # Verify each status type has corresponding CSS class
            assert len(widget.query(".iteration-completed")) >= 1
            assert len(widget.query(".iteration-running")) >= 1
            assert len(widget.query(".iteration-pending")) >= 1
            assert len(widget.query(".iteration-failed")) >= 1
            assert len(widget.query(".iteration-skipped")) >= 1
            assert len(widget.query(".iteration-cancelled")) >= 1


class TestIterationProgressStatusIcons:
    """Tests for status icon rendering in IterationProgress widget."""

    def test_status_icons_constant_exists(self) -> None:
        """Test STATUS_ICONS constant is defined with correct mappings."""
        from maverick.tui.widgets.iteration_progress import STATUS_ICONS

        # Verify all status types have icons
        assert IterationStatus.PENDING in STATUS_ICONS
        assert IterationStatus.RUNNING in STATUS_ICONS
        assert IterationStatus.COMPLETED in STATUS_ICONS
        assert IterationStatus.FAILED in STATUS_ICONS
        assert IterationStatus.SKIPPED in STATUS_ICONS
        assert IterationStatus.CANCELLED in STATUS_ICONS

    def test_status_icons_values(self) -> None:
        """Test STATUS_ICONS has correct icon values per quickstart.md."""
        from maverick.tui.widgets.iteration_progress import STATUS_ICONS

        # Based on quickstart.md specification
        assert STATUS_ICONS[IterationStatus.PENDING] == "\u25cb"  # Open circle
        assert STATUS_ICONS[IterationStatus.RUNNING] == "\u25cf"  # Filled circle
        assert STATUS_ICONS[IterationStatus.COMPLETED] == "\u2713"  # Checkmark
        assert STATUS_ICONS[IterationStatus.FAILED] == "\u2717"  # X mark
        assert STATUS_ICONS[IterationStatus.SKIPPED] == "\u2298"  # Circle with slash
        assert STATUS_ICONS[IterationStatus.CANCELLED] == "\u2297"  # Circle with X

    @pytest.mark.asyncio
    async def test_icons_rendered_in_widget(self) -> None:
        """Test status icons are rendered in widget output."""
        from textual.widgets import Static

        from maverick.tui.widgets.iteration_progress import STATUS_ICONS

        state = LoopIterationState(
            step_name="test_loop",
            iterations=[
                LoopIterationItem(0, 3, "Completed Task", IterationStatus.COMPLETED),
                LoopIterationItem(1, 3, "Running Task", IterationStatus.RUNNING),
                LoopIterationItem(2, 3, "Pending Task", IterationStatus.PENDING),
            ],
        )

        async with _create_test_app(state).run_test() as pilot:
            await pilot.pause()

            # Get all Static widgets that represent iterations
            statics = pilot.app.query(Static)

            # Check that at least one static contains each expected icon
            texts = [str(s.renderable) for s in statics]
            all_text = " ".join(texts)

            assert STATUS_ICONS[IterationStatus.COMPLETED] in all_text
            assert STATUS_ICONS[IterationStatus.RUNNING] in all_text
            assert STATUS_ICONS[IterationStatus.PENDING] in all_text


class TestIterationProgressNesting:
    """Tests for nested loop indentation in IterationProgress widget.

    Nesting uses 2 spaces per level.
    """

    @pytest.mark.asyncio
    async def test_nesting_level_zero_no_indent(self) -> None:
        """Test nesting level 0 has no indentation."""
        from textual.widgets import Static

        state = LoopIterationState(
            step_name="outer_loop",
            iterations=[
                LoopIterationItem(0, 1, "Outer Task", IterationStatus.RUNNING),
            ],
            nesting_level=0,
        )

        async with _create_test_app(state).run_test() as pilot:
            await pilot.pause()

            statics = pilot.app.query(Static)

            # With nesting_level=0, text should start with icon (no leading spaces)
            for static in statics:
                text = str(static.renderable)
                if "Outer Task" in text:
                    # Should NOT start with spaces (no indentation)
                    assert not text.startswith("  ")

    @pytest.mark.asyncio
    async def test_nesting_level_one_two_spaces(self) -> None:
        """Test nesting level 1 has 2 spaces indentation."""
        from textual.widgets import Static

        state = LoopIterationState(
            step_name="nested_loop",
            iterations=[
                LoopIterationItem(0, 1, "Nested Task", IterationStatus.RUNNING),
            ],
            nesting_level=1,
        )

        async with _create_test_app(state).run_test() as pilot:
            await pilot.pause()

            statics = pilot.app.query(Static)

            for static in statics:
                text = str(static.renderable)
                if "Nested Task" in text:
                    # Should start with 2 spaces (1 level * 2 spaces)
                    assert text.startswith("  ")
                    # But not 4 spaces
                    assert not text.startswith("    ")

    @pytest.mark.asyncio
    async def test_nesting_level_two_four_spaces(self) -> None:
        """Test nesting level 2 has 4 spaces indentation."""
        from textual.widgets import Static

        state = LoopIterationState(
            step_name="deeply_nested_loop",
            iterations=[
                LoopIterationItem(0, 1, "Deep Task", IterationStatus.RUNNING),
            ],
            nesting_level=2,
        )

        async with _create_test_app(state).run_test() as pilot:
            await pilot.pause()

            statics = pilot.app.query(Static)

            for static in statics:
                text = str(static.renderable)
                if "Deep Task" in text:
                    # Should start with 4 spaces (2 levels * 2 spaces)
                    assert text.startswith("    ")

    @pytest.mark.asyncio
    async def test_nesting_level_three_six_spaces(self) -> None:
        """Test nesting level 3 has 6 spaces indentation."""
        from textual.widgets import Static

        state = LoopIterationState(
            step_name="very_nested_loop",
            iterations=[
                LoopIterationItem(0, 1, "Very Deep Task", IterationStatus.RUNNING),
            ],
            nesting_level=3,
        )

        async with _create_test_app(state).run_test() as pilot:
            await pilot.pause()

            statics = pilot.app.query(Static)

            for static in statics:
                text = str(static.renderable)
                if "Very Deep Task" in text:
                    # Should start with 6 spaces (3 levels * 2 spaces)
                    assert text.startswith("      ")


class TestIterationProgressEmptyState:
    """Tests for empty state display in IterationProgress widget."""

    @pytest.mark.asyncio
    async def test_empty_iterations_shows_indicator(self) -> None:
        """Test empty iterations list displays 'No iterations' indicator."""
        from textual.widgets import Static

        state = LoopIterationState(
            step_name="empty_loop",
            iterations=[],
        )

        async with _create_test_app(state).run_test() as pilot:
            await pilot.pause()

            statics = pilot.app.query(Static)
            texts = [str(s.renderable) for s in statics]
            all_text = " ".join(texts)

            # Should display some indication that there are no iterations
            assert "No iterations" in all_text or "Empty" in all_text.lower()


class TestIterationProgressDuration:
    """Tests for duration display in completed iterations."""

    @pytest.mark.asyncio
    async def test_completed_iteration_shows_duration(self) -> None:
        """Test completed iteration displays duration in milliseconds."""
        from textual.widgets import Static

        state = LoopIterationState(
            step_name="test_loop",
            iterations=[
                LoopIterationItem(
                    index=0,
                    total=1,
                    label="Completed Task",
                    status=IterationStatus.COMPLETED,
                    duration_ms=1500,
                ),
            ],
        )

        async with _create_test_app(state).run_test() as pilot:
            await pilot.pause()

            statics = pilot.app.query(Static)
            texts = [str(s.renderable) for s in statics]
            all_text = " ".join(texts)

            # Duration should be displayed (format: "1500ms" or "(1500ms)")
            assert "1500" in all_text and "ms" in all_text

    @pytest.mark.asyncio
    async def test_pending_iteration_no_duration(self) -> None:
        """Test pending iteration does not display duration."""
        from textual.widgets import Static

        state = LoopIterationState(
            step_name="test_loop",
            iterations=[
                LoopIterationItem(
                    index=0,
                    total=1,
                    label="Pending Task",
                    status=IterationStatus.PENDING,
                    duration_ms=None,  # No duration for pending
                ),
            ],
        )

        async with _create_test_app(state).run_test() as pilot:
            await pilot.pause()

            statics = pilot.app.query(Static)
            texts = [str(s.renderable) for s in statics]
            all_text = " ".join(texts)

            # Should display the task but no "ms" duration marker
            assert "Pending Task" in all_text
            # Duration should not appear when not set
            # "(None" should not appear if duration_ms is None
            assert "Nonems" not in all_text

    @pytest.mark.asyncio
    async def test_running_iteration_no_duration(self) -> None:
        """Test running iteration does not display duration (still in progress)."""
        from textual.widgets import Static

        state = LoopIterationState(
            step_name="test_loop",
            iterations=[
                LoopIterationItem(
                    index=0,
                    total=1,
                    label="Running Task",
                    status=IterationStatus.RUNNING,
                    duration_ms=None,
                ),
            ],
        )

        async with _create_test_app(state).run_test() as pilot:
            await pilot.pause()

            statics = pilot.app.query(Static)
            texts = [str(s.renderable) for s in statics]
            all_text = " ".join(texts)

            assert "Running Task" in all_text

    @pytest.mark.asyncio
    async def test_failed_iteration_shows_duration(self) -> None:
        """Test failed iteration displays duration if available."""
        from textual.widgets import Static

        state = LoopIterationState(
            step_name="test_loop",
            iterations=[
                LoopIterationItem(
                    index=0,
                    total=1,
                    label="Failed Task",
                    status=IterationStatus.FAILED,
                    duration_ms=3000,
                    error="Build failed",
                ),
            ],
        )

        async with _create_test_app(state).run_test() as pilot:
            await pilot.pause()

            statics = pilot.app.query(Static)
            texts = [str(s.renderable) for s in statics]
            all_text = " ".join(texts)

            # Duration should be displayed even for failed iterations
            assert "3000" in all_text and "ms" in all_text


class TestIterationProgressUpdateState:
    """Tests for update_state method in IterationProgress widget."""

    @pytest.mark.asyncio
    async def test_update_state_replaces_state(self) -> None:
        """Test update_state replaces the internal state."""
        from maverick.tui.widgets.iteration_progress import IterationProgress

        initial_state = LoopIterationState(
            step_name="test_loop",
            iterations=[
                LoopIterationItem(0, 3, "Item 1", IterationStatus.PENDING),
            ],
        )

        async with _create_test_app(initial_state).run_test() as pilot:
            widget = pilot.app.query_one(IterationProgress)
            await pilot.pause()

            # Verify initial state
            assert len(widget._state.iterations) == 1
            assert widget._state.iterations[0].status == IterationStatus.PENDING

            # Create new state with updated iteration
            new_state = LoopIterationState(
                step_name="test_loop",
                iterations=[
                    LoopIterationItem(
                        0, 3, "Item 1", IterationStatus.COMPLETED, duration_ms=500
                    ),
                    LoopIterationItem(1, 3, "Item 2", IterationStatus.RUNNING),
                    LoopIterationItem(2, 3, "Item 3", IterationStatus.PENDING),
                ],
            )

            # Update state
            widget.update_state(new_state)
            await pilot.pause()

            # Verify state was updated
            assert len(widget._state.iterations) == 3
            assert widget._state.iterations[0].status == IterationStatus.COMPLETED
            assert widget._state.iterations[1].status == IterationStatus.RUNNING


# =============================================================================
# T020: Unit Tests for Nested Loop Support (Level 4+ Collapsed)
# =============================================================================


class TestIterationProgressConstants:
    """Tests for IterationProgress widget constants."""

    def test_max_visible_nesting_constant_exists(self) -> None:
        """Test MAX_VISIBLE_NESTING constant is defined."""
        from maverick.tui.widgets.iteration_progress import IterationProgress

        assert hasattr(IterationProgress, "MAX_VISIBLE_NESTING")
        assert IterationProgress.MAX_VISIBLE_NESTING == 3

    def test_expand_collapse_icons_exist(self) -> None:
        """Test expand/collapse icons are defined."""
        from maverick.tui.widgets.iteration_progress import (
            COLLAPSE_ICON,
            EXPAND_ICON,
        )

        assert EXPAND_ICON is not None
        assert COLLAPSE_ICON is not None
        # Both should be single unicode characters
        assert len(EXPAND_ICON) == 1
        assert len(COLLAPSE_ICON) == 1


class TestIterationProgressCollapsedState:
    """Tests for collapsed state indicator at nesting level 4+."""

    @pytest.mark.asyncio
    async def test_nesting_level_four_shows_collapsed(self) -> None:
        """Test nesting level 4 shows collapsed indicator instead of iterations."""
        from textual.widgets import Static

        state = LoopIterationState(
            step_name="deeply_nested_loop",
            iterations=[
                LoopIterationItem(0, 3, "Task 1", IterationStatus.COMPLETED),
                LoopIterationItem(1, 3, "Task 2", IterationStatus.RUNNING),
                LoopIterationItem(2, 3, "Task 3", IterationStatus.PENDING),
            ],
            nesting_level=4,
        )

        async with _create_test_app(state).run_test() as pilot:
            await pilot.pause()

            statics = pilot.app.query(Static)
            texts = [str(s.renderable) for s in statics]
            all_text = " ".join(texts)

            # Should show collapsed indicator with step name and iteration count
            assert "..." in all_text
            assert "deeply_nested_loop" in all_text
            assert "3" in all_text  # iteration count

            # Should NOT show individual iteration labels
            assert "Task 1" not in all_text
            assert "Task 2" not in all_text
            assert "Task 3" not in all_text

    @pytest.mark.asyncio
    async def test_nesting_level_five_shows_collapsed(self) -> None:
        """Test nesting level 5+ also shows collapsed indicator."""
        from textual.widgets import Static

        state = LoopIterationState(
            step_name="very_deeply_nested",
            iterations=[
                LoopIterationItem(0, 2, "Deep Task 1", IterationStatus.PENDING),
                LoopIterationItem(1, 2, "Deep Task 2", IterationStatus.PENDING),
            ],
            nesting_level=5,
        )

        async with _create_test_app(state).run_test() as pilot:
            await pilot.pause()

            statics = pilot.app.query(Static)
            texts = [str(s.renderable) for s in statics]
            all_text = " ".join(texts)

            # Should show collapsed indicator
            assert "..." in all_text
            assert "very_deeply_nested" in all_text

    @pytest.mark.asyncio
    async def test_collapsed_indicator_has_css_class(self) -> None:
        """Test collapsed indicator has iteration-collapsed CSS class."""
        from maverick.tui.widgets.iteration_progress import IterationProgress

        state = LoopIterationState(
            step_name="nested_loop",
            iterations=[
                LoopIterationItem(0, 2, "Task 1", IterationStatus.PENDING),
                LoopIterationItem(1, 2, "Task 2", IterationStatus.PENDING),
            ],
            nesting_level=4,
        )

        async with _create_test_app(state).run_test() as pilot:
            widget = pilot.app.query_one(IterationProgress)
            await pilot.pause()

            # Should have collapsed class
            collapsed_items = widget.query(".iteration-collapsed")
            assert len(collapsed_items) == 1

    @pytest.mark.asyncio
    async def test_collapsed_singular_iteration_text(self) -> None:
        """Test collapsed indicator uses singular 'iteration' for count of 1."""
        from textual.widgets import Static

        state = LoopIterationState(
            step_name="single_iteration_loop",
            iterations=[
                LoopIterationItem(0, 1, "Only Task", IterationStatus.PENDING),
            ],
            nesting_level=4,
        )

        async with _create_test_app(state).run_test() as pilot:
            await pilot.pause()

            statics = pilot.app.query(Static)
            texts = [str(s.renderable) for s in statics]
            all_text = " ".join(texts)

            # Should use "1 iteration" not "1 iterations"
            assert "1 iteration" in all_text
            assert "1 iterations" not in all_text

    @pytest.mark.asyncio
    async def test_collapsed_multiple_iterations_text(self) -> None:
        """Test collapsed indicator uses plural 'iterations' for count > 1."""
        from textual.widgets import Static

        state = LoopIterationState(
            step_name="multi_iteration_loop",
            iterations=[
                LoopIterationItem(0, 5, "Task 1", IterationStatus.PENDING),
                LoopIterationItem(1, 5, "Task 2", IterationStatus.PENDING),
                LoopIterationItem(2, 5, "Task 3", IterationStatus.PENDING),
                LoopIterationItem(3, 5, "Task 4", IterationStatus.PENDING),
                LoopIterationItem(4, 5, "Task 5", IterationStatus.PENDING),
            ],
            nesting_level=4,
        )

        async with _create_test_app(state).run_test() as pilot:
            await pilot.pause()

            statics = pilot.app.query(Static)
            texts = [str(s.renderable) for s in statics]
            all_text = " ".join(texts)

            # Should use "5 iterations" (plural)
            assert "5 iterations" in all_text


class TestIterationProgressExpandCollapse:
    """Tests for expand/collapse toggle functionality."""

    @pytest.mark.asyncio
    async def test_is_collapsed_property_at_level_four(self) -> None:
        """Test is_collapsed returns True for nesting level 4."""
        from maverick.tui.widgets.iteration_progress import IterationProgress

        state = LoopIterationState(
            step_name="nested_loop",
            iterations=[
                LoopIterationItem(0, 2, "Task 1", IterationStatus.PENDING),
            ],
            nesting_level=4,
        )

        async with _create_test_app(state).run_test() as pilot:
            widget = pilot.app.query_one(IterationProgress)
            await pilot.pause()

            assert widget.is_collapsed is True

    @pytest.mark.asyncio
    async def test_is_collapsed_property_at_level_three(self) -> None:
        """Test is_collapsed returns False for nesting level 3 (max visible)."""
        from maverick.tui.widgets.iteration_progress import IterationProgress

        state = LoopIterationState(
            step_name="nested_loop",
            iterations=[
                LoopIterationItem(0, 2, "Task 1", IterationStatus.PENDING),
            ],
            nesting_level=3,
            expanded=True,
        )

        async with _create_test_app(state).run_test() as pilot:
            widget = pilot.app.query_one(IterationProgress)
            await pilot.pause()

            assert widget.is_collapsed is False

    @pytest.mark.asyncio
    async def test_explicitly_collapsed_state(self) -> None:
        """Test widget respects expanded=False for manual collapse."""
        from textual.widgets import Static

        from maverick.tui.widgets.iteration_progress import IterationProgress

        state = LoopIterationState(
            step_name="collapsible_loop",
            iterations=[
                LoopIterationItem(0, 2, "Task 1", IterationStatus.PENDING),
                LoopIterationItem(1, 2, "Task 2", IterationStatus.PENDING),
            ],
            nesting_level=1,  # Within visible range
            expanded=False,  # Explicitly collapsed
        )

        async with _create_test_app(state).run_test() as pilot:
            widget = pilot.app.query_one(IterationProgress)
            await pilot.pause()

            # Widget should be collapsed
            assert widget.is_collapsed is True

            # Should show collapsed indicator
            statics = pilot.app.query(Static)
            texts = [str(s.renderable) for s in statics]
            all_text = " ".join(texts)

            assert "..." in all_text
            assert "collapsible_loop" in all_text

    @pytest.mark.asyncio
    async def test_toggle_expanded_changes_state(self) -> None:
        """Test toggle_expanded method changes internal state."""
        from maverick.tui.widgets.iteration_progress import IterationProgress

        state = LoopIterationState(
            step_name="toggleable_loop",
            iterations=[
                LoopIterationItem(0, 2, "Task 1", IterationStatus.PENDING),
            ],
            nesting_level=1,
            expanded=True,
        )

        async with _create_test_app(state).run_test() as pilot:
            widget = pilot.app.query_one(IterationProgress)
            await pilot.pause()

            # Initially expanded
            assert widget._state.expanded is True

            # Toggle
            widget.toggle_expanded()
            await pilot.pause()

            # Now collapsed
            assert widget._state.expanded is False

            # Toggle again
            widget.toggle_expanded()
            await pilot.pause()

            # Back to expanded
            assert widget._state.expanded is True

    @pytest.mark.asyncio
    async def test_toggle_expanded_message_class_exists(self) -> None:
        """Test ToggleExpanded message class is defined."""
        from maverick.tui.widgets.iteration_progress import IterationProgress

        # Message class should exist as nested class
        assert hasattr(IterationProgress, "ToggleExpanded")

        # Should have correct attributes
        msg = IterationProgress.ToggleExpanded("test_loop", True)
        assert msg.step_name == "test_loop"
        assert msg.expanded is True


class TestIterationProgressIndentationCapping:
    """Tests for indentation capping at MAX_VISIBLE_NESTING."""

    @pytest.mark.asyncio
    async def test_indentation_capped_when_expanded_beyond_max(self) -> None:
        """Test indentation is capped at MAX_VISIBLE_NESTING when displaying."""
        from textual.widgets import Static

        # Even if we force expand a deeply nested loop, indentation should cap
        state = LoopIterationState(
            step_name="deep_but_expanded",
            iterations=[
                LoopIterationItem(0, 1, "Deep Task", IterationStatus.RUNNING),
            ],
            nesting_level=10,  # Very deep
            expanded=True,  # But we want to see it
        )

        # The widget should still show collapsed at level 4+
        # because nesting_level > MAX_VISIBLE_NESTING takes precedence
        async with _create_test_app(state).run_test() as pilot:
            await pilot.pause()

            statics = pilot.app.query(Static)
            texts = [str(s.renderable) for s in statics]
            all_text = " ".join(texts)

            # Should show collapsed indicator (level 10 > 3)
            assert "..." in all_text
            assert "deep_but_expanded" in all_text
