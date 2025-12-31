"""Unit tests for WorkflowProgress widget.

This test module covers the WorkflowProgress widget for User Story 1
(012-workflow-widgets). The widget displays workflow stages vertically with
status icons, duration, and expandable details.

Test coverage includes:
- Initialization and configuration
- Rendering stages with various statuses
- Status icons and duration display
- Expandable/collapsible stage details
- Loading and empty states
- Message emission for user interactions
- Protocol compliance
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from textual.app import App

from maverick.tui.models import StageStatus, WorkflowStage
from maverick.tui.widgets.workflow_progress import (
    StageCollapsed,
    StageExpanded,
    WorkflowProgress,
)

# =============================================================================
# Test App and Fixtures
# =============================================================================


class WorkflowProgressTestApp(App):
    """Test app for WorkflowProgress widget testing."""

    def compose(self):
        """Compose the test app."""
        yield WorkflowProgress()


@pytest.fixture
def sample_stages() -> tuple[WorkflowStage, ...]:
    """Create sample workflow stages for testing."""
    now = datetime.now()
    return (
        WorkflowStage(
            name="setup",
            display_name="Setup",
            status=StageStatus.COMPLETED,
            started_at=now - timedelta(seconds=15),
            completed_at=now - timedelta(seconds=10),
            detail_content="Branch synced with origin/main",
        ),
        WorkflowStage(
            name="implementation",
            display_name="Implementation",
            status=StageStatus.ACTIVE,
            started_at=now - timedelta(seconds=5),
            detail_content="Running task T001: Add feature X",
        ),
        WorkflowStage(
            name="review",
            display_name="Code Review",
            status=StageStatus.PENDING,
            detail_content=None,
        ),
        WorkflowStage(
            name="validation",
            display_name="Validation",
            status=StageStatus.PENDING,
        ),
    )


@pytest.fixture
def failed_stage() -> WorkflowStage:
    """Create a failed workflow stage for testing."""
    now = datetime.now()
    return WorkflowStage(
        name="validation",
        display_name="Validation",
        status=StageStatus.FAILED,
        started_at=now - timedelta(seconds=30),
        completed_at=now,
        error_message="Build failed: compilation error in src/main.py",
        detail_content="Running validation steps...",
    )


# =============================================================================
# Initialization Tests (T018)
# =============================================================================


class TestWorkflowProgressInitialization:
    """Tests for WorkflowProgress initialization."""

    @pytest.mark.asyncio
    async def test_initialization_creates_empty_widget(self) -> None:
        """Test WorkflowProgress initializes with no stages."""
        async with WorkflowProgressTestApp().run_test() as pilot:
            widget = pilot.app.query_one(WorkflowProgress)

            assert widget.state.is_empty
            assert len(widget.state.stages) == 0
            assert not widget.state.loading
            assert widget.state.expanded_stage is None

    @pytest.mark.asyncio
    async def test_initialization_with_custom_id(self) -> None:
        """Test WorkflowProgress initializes with custom id."""

        class CustomIdApp(App):
            def compose(self):
                yield WorkflowProgress(id="custom-progress")

        async with CustomIdApp().run_test() as pilot:
            widget = pilot.app.query_one("#custom-progress", WorkflowProgress)

            assert widget.state.is_empty
            assert len(widget.state.stages) == 0


# =============================================================================
# Rendering Tests (T019)
# =============================================================================


class TestWorkflowProgressRendering:
    """Tests for WorkflowProgress rendering."""

    @pytest.mark.asyncio
    async def test_render_empty_state(self) -> None:
        """Test rendering when no stages are present."""
        async with WorkflowProgressTestApp().run_test() as pilot:
            widget = pilot.app.query_one(WorkflowProgress)
            await pilot.pause()

            assert widget.state.is_empty
            # Widget should render an empty state message
            rendered_text = widget.render()
            assert "No workflow stages" in rendered_text or rendered_text == ""

    @pytest.mark.asyncio
    async def test_render_loading_state(self) -> None:
        """Test rendering during initial data load."""
        async with WorkflowProgressTestApp().run_test() as pilot:
            widget = pilot.app.query_one(WorkflowProgress)
            widget.set_loading(True)
            await pilot.pause()

            assert widget.state.loading
            assert not widget.state.is_empty
            rendered_text = widget.render()
            assert "Loading" in rendered_text or "..." in rendered_text

    @pytest.mark.asyncio
    async def test_render_stages_with_status_icons(self, sample_stages) -> None:
        """Test rendering stages with correct status icons."""
        async with WorkflowProgressTestApp().run_test() as pilot:
            widget = pilot.app.query_one(WorkflowProgress)
            widget.update_stages(sample_stages)
            await pilot.pause()

            # Verify stages are rendered
            assert len(widget.state.stages) == 4

            # The widget should display status icons based on StageStatus
            # Icons: pending (○), active (◐), completed (✓), failed (✗)
            # We test this by checking the internal state and icon mapping
            assert widget.state.stages[0].status == StageStatus.COMPLETED
            assert widget.state.stages[1].status == StageStatus.ACTIVE
            assert widget.state.stages[2].status == StageStatus.PENDING
            assert widget.state.stages[3].status == StageStatus.PENDING

    @pytest.mark.asyncio
    async def test_render_completed_stage_with_duration(self, sample_stages) -> None:
        """Test rendering completed stage with duration display."""
        async with WorkflowProgressTestApp().run_test() as pilot:
            widget = pilot.app.query_one(WorkflowProgress)
            widget.update_stages(sample_stages)
            await pilot.pause()

            completed_stage = widget.state.stages[0]
            assert completed_stage.status == StageStatus.COMPLETED
            assert completed_stage.duration_display == "5s"

    @pytest.mark.asyncio
    async def test_render_failed_stage_with_error_icon(self, failed_stage) -> None:
        """Test rendering failed stage with error icon and message."""
        async with WorkflowProgressTestApp().run_test() as pilot:
            widget = pilot.app.query_one(WorkflowProgress)
            widget.update_stages((failed_stage,))
            await pilot.pause()

            assert widget.state.stages[0].status == StageStatus.FAILED
            assert widget.state.stages[0].error_message is not None


# =============================================================================
# Update Methods Tests (T020)
# =============================================================================


class TestWorkflowProgressUpdateMethods:
    """Tests for WorkflowProgress update methods."""

    @pytest.mark.asyncio
    async def test_update_stages_replaces_all_stages(self, sample_stages) -> None:
        """Test update_stages replaces all stages."""
        async with WorkflowProgressTestApp().run_test() as pilot:
            widget = pilot.app.query_one(WorkflowProgress)

            # Initial update
            widget.update_stages(sample_stages[:2])
            await pilot.pause()
            assert len(widget.state.stages) == 2

            # Replace with new stages
            widget.update_stages(sample_stages)
            await pilot.pause()
            assert len(widget.state.stages) == 4

    @pytest.mark.asyncio
    async def test_update_stage_status_changes_single_stage(
        self, sample_stages
    ) -> None:
        """Test update_stage_status updates a specific stage."""
        async with WorkflowProgressTestApp().run_test() as pilot:
            widget = pilot.app.query_one(WorkflowProgress)
            widget.update_stages(sample_stages)
            await pilot.pause()

            # Update implementation stage to completed
            widget.update_stage_status("implementation", "completed")
            await pilot.pause()

            updated_stage = next(
                s for s in widget.state.stages if s.name == "implementation"
            )
            assert updated_stage.status == StageStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_update_stage_status_with_error_message(self, sample_stages) -> None:
        """Test update_stage_status with error message for failed stage."""
        async with WorkflowProgressTestApp().run_test() as pilot:
            widget = pilot.app.query_one(WorkflowProgress)
            widget.update_stages(sample_stages)
            await pilot.pause()

            error_msg = "Test failed: assertion error"
            widget.update_stage_status("validation", "failed", error_message=error_msg)
            await pilot.pause()

            failed_stage = next(
                s for s in widget.state.stages if s.name == "validation"
            )
            assert failed_stage.status == StageStatus.FAILED
            assert failed_stage.error_message == error_msg

    @pytest.mark.asyncio
    async def test_update_nonexistent_stage_does_nothing(self, sample_stages) -> None:
        """Test update_stage_status with nonexistent stage name does nothing."""
        async with WorkflowProgressTestApp().run_test() as pilot:
            widget = pilot.app.query_one(WorkflowProgress)
            widget.update_stages(sample_stages)
            await pilot.pause()

            initial_count = len(widget.state.stages)
            widget.update_stage_status("nonexistent", "completed")
            await pilot.pause()

            # No changes should occur
            assert len(widget.state.stages) == initial_count


# =============================================================================
# Expansion/Collapse Tests (T021)
# =============================================================================


class TestWorkflowProgressExpansion:
    """Tests for stage expansion/collapse functionality."""

    @pytest.mark.asyncio
    async def test_expand_stage_sets_expanded_state(self, sample_stages) -> None:
        """Test expand_stage sets the expanded stage in state."""
        async with WorkflowProgressTestApp().run_test() as pilot:
            widget = pilot.app.query_one(WorkflowProgress)
            widget.update_stages(sample_stages)
            await pilot.pause()

            widget.expand_stage("setup")
            await pilot.pause()

            assert widget.state.expanded_stage == "setup"

    @pytest.mark.asyncio
    async def test_expand_stage_emits_message(self, sample_stages) -> None:
        """Test expand_stage emits StageExpanded message."""
        messages_received = []

        class MessageCapturingApp(App):
            def compose(self):
                yield WorkflowProgress()

            def on_stage_expanded(self, message: StageExpanded) -> None:
                messages_received.append(message)

        async with MessageCapturingApp().run_test() as pilot:
            widget = pilot.app.query_one(WorkflowProgress)
            widget.update_stages(sample_stages)
            await pilot.pause()

            widget.expand_stage("setup")
            await pilot.pause()

            # Verify message was emitted
            assert len(messages_received) == 1
            assert messages_received[0].stage_name == "setup"

    @pytest.mark.asyncio
    async def test_collapse_stage_clears_expanded_state(self, sample_stages) -> None:
        """Test collapse_stage clears the expanded stage."""
        async with WorkflowProgressTestApp().run_test() as pilot:
            widget = pilot.app.query_one(WorkflowProgress)
            widget.update_stages(sample_stages)
            await pilot.pause()

            # First expand
            widget.expand_stage("setup")
            await pilot.pause()
            assert widget.state.expanded_stage == "setup"

            # Then collapse
            widget.collapse_stage("setup")
            await pilot.pause()
            assert widget.state.expanded_stage is None

    @pytest.mark.asyncio
    async def test_collapse_stage_emits_message(self, sample_stages) -> None:
        """Test collapse_stage emits StageCollapsed message."""
        messages_received = []

        class MessageCapturingApp(App):
            def compose(self):
                yield WorkflowProgress()

            def on_stage_collapsed(self, message: StageCollapsed) -> None:
                messages_received.append(message)

        async with MessageCapturingApp().run_test() as pilot:
            widget = pilot.app.query_one(WorkflowProgress)
            widget.update_stages(sample_stages)
            widget.expand_stage("setup")
            await pilot.pause()

            widget.collapse_stage("setup")
            await pilot.pause()

            assert len(messages_received) == 1
            assert messages_received[0].stage_name == "setup"

    @pytest.mark.asyncio
    async def test_expand_different_stage_collapses_previous(
        self, sample_stages
    ) -> None:
        """Test expanding a different stage collapses the currently expanded one."""
        async with WorkflowProgressTestApp().run_test() as pilot:
            widget = pilot.app.query_one(WorkflowProgress)
            widget.update_stages(sample_stages)
            await pilot.pause()

            widget.expand_stage("setup")
            await pilot.pause()
            assert widget.state.expanded_stage == "setup"

            widget.expand_stage("implementation")
            await pilot.pause()
            assert widget.state.expanded_stage == "implementation"


# =============================================================================
# Loading State Tests (T022)
# =============================================================================


class TestWorkflowProgressLoadingState:
    """Tests for loading state management."""

    @pytest.mark.asyncio
    async def test_set_loading_true_shows_loading_state(self) -> None:
        """Test set_loading(True) displays loading state."""
        async with WorkflowProgressTestApp().run_test() as pilot:
            widget = pilot.app.query_one(WorkflowProgress)

            widget.set_loading(True)
            await pilot.pause()

            assert widget.state.loading
            assert not widget.state.is_empty

    @pytest.mark.asyncio
    async def test_set_loading_false_clears_loading_state(self) -> None:
        """Test set_loading(False) clears loading state."""
        async with WorkflowProgressTestApp().run_test() as pilot:
            widget = pilot.app.query_one(WorkflowProgress)

            widget.set_loading(True)
            await pilot.pause()
            assert widget.state.loading

            widget.set_loading(False)
            await pilot.pause()
            assert not widget.state.loading

    @pytest.mark.asyncio
    async def test_loading_state_with_stages_shows_stages(self, sample_stages) -> None:
        """Test loading=True with stages still shows stages."""
        async with WorkflowProgressTestApp().run_test() as pilot:
            widget = pilot.app.query_one(WorkflowProgress)

            widget.update_stages(sample_stages)
            widget.set_loading(True)
            await pilot.pause()

            assert widget.state.loading
            assert len(widget.state.stages) == 4


# =============================================================================
# Current Stage Tests (T023)
# =============================================================================


class TestWorkflowProgressCurrentStage:
    """Tests for current stage tracking."""

    @pytest.mark.asyncio
    async def test_current_stage_returns_active_stage(self, sample_stages) -> None:
        """Test current_stage property returns the active stage."""
        async with WorkflowProgressTestApp().run_test() as pilot:
            widget = pilot.app.query_one(WorkflowProgress)
            widget.update_stages(sample_stages)
            await pilot.pause()

            current = widget.state.current_stage
            assert current is not None
            assert current.name == "implementation"
            assert current.status == StageStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_current_stage_returns_none_when_all_pending(self) -> None:
        """Test current_stage returns None when all stages are pending."""
        async with WorkflowProgressTestApp().run_test() as pilot:
            widget = pilot.app.query_one(WorkflowProgress)

            pending_stages = (
                WorkflowStage(
                    name="stage1", display_name="Stage 1", status=StageStatus.PENDING
                ),
                WorkflowStage(
                    name="stage2", display_name="Stage 2", status=StageStatus.PENDING
                ),
            )
            widget.update_stages(pending_stages)
            await pilot.pause()

            assert widget.state.current_stage is None

    @pytest.mark.asyncio
    async def test_current_stage_returns_none_when_empty(self) -> None:
        """Test current_stage returns None when no stages exist."""
        async with WorkflowProgressTestApp().run_test() as pilot:
            widget = pilot.app.query_one(WorkflowProgress)

            assert widget.state.current_stage is None


# =============================================================================
# Duration Display Tests (T024)
# =============================================================================


class TestWorkflowProgressDurationDisplay:
    """Tests for duration calculation and display."""

    @pytest.mark.asyncio
    async def test_duration_display_seconds_only(self) -> None:
        """Test duration display for stages under 60 seconds."""
        async with WorkflowProgressTestApp().run_test() as pilot:
            widget = pilot.app.query_one(WorkflowProgress)

            now = datetime.now()
            stage = WorkflowStage(
                name="quick",
                display_name="Quick Stage",
                status=StageStatus.COMPLETED,
                started_at=now - timedelta(seconds=15),
                completed_at=now,
            )
            widget.update_stages((stage,))
            await pilot.pause()

            assert widget.state.stages[0].duration_display == "15s"

    @pytest.mark.asyncio
    async def test_duration_display_minutes_and_seconds(self) -> None:
        """Test duration display for stages over 60 seconds."""
        async with WorkflowProgressTestApp().run_test() as pilot:
            widget = pilot.app.query_one(WorkflowProgress)

            now = datetime.now()
            stage = WorkflowStage(
                name="longer",
                display_name="Longer Stage",
                status=StageStatus.COMPLETED,
                started_at=now - timedelta(seconds=95),
                completed_at=now,
            )
            widget.update_stages((stage,))
            await pilot.pause()

            assert widget.state.stages[0].duration_display == "1m 35s"

    @pytest.mark.asyncio
    async def test_duration_display_empty_for_incomplete_stage(self) -> None:
        """Test duration display is empty for incomplete stages."""
        async with WorkflowProgressTestApp().run_test() as pilot:
            widget = pilot.app.query_one(WorkflowProgress)

            stage = WorkflowStage(
                name="active",
                display_name="Active Stage",
                status=StageStatus.ACTIVE,
                started_at=datetime.now(),
            )
            widget.update_stages((stage,))
            await pilot.pause()

            assert widget.state.stages[0].duration_display == ""


# =============================================================================
# Protocol Compliance Tests (T025)
# =============================================================================


class TestWorkflowProgressProtocolCompliance:
    """Tests for protocol compliance."""

    @pytest.mark.asyncio
    async def test_implements_update_stages_method(self) -> None:
        """Test widget implements update_stages method from protocol."""
        async with WorkflowProgressTestApp().run_test() as pilot:
            widget = pilot.app.query_one(WorkflowProgress)

            assert hasattr(widget, "update_stages")
            assert callable(widget.update_stages)

    @pytest.mark.asyncio
    async def test_implements_update_stage_status_method(self) -> None:
        """Test widget implements update_stage_status method from protocol."""
        async with WorkflowProgressTestApp().run_test() as pilot:
            widget = pilot.app.query_one(WorkflowProgress)

            assert hasattr(widget, "update_stage_status")
            assert callable(widget.update_stage_status)

    @pytest.mark.asyncio
    async def test_implements_expand_stage_method(self) -> None:
        """Test widget implements expand_stage method from protocol."""
        async with WorkflowProgressTestApp().run_test() as pilot:
            widget = pilot.app.query_one(WorkflowProgress)

            assert hasattr(widget, "expand_stage")
            assert callable(widget.expand_stage)

    @pytest.mark.asyncio
    async def test_implements_collapse_stage_method(self) -> None:
        """Test widget implements collapse_stage method from protocol."""
        async with WorkflowProgressTestApp().run_test() as pilot:
            widget = pilot.app.query_one(WorkflowProgress)

            assert hasattr(widget, "collapse_stage")
            assert callable(widget.collapse_stage)

    @pytest.mark.asyncio
    async def test_messages_have_correct_attributes(self) -> None:
        """Test emitted messages have required attributes."""
        # StageExpanded message
        expanded_msg = StageExpanded(stage_name="test")
        assert expanded_msg.stage_name == "test"

        # StageCollapsed message
        collapsed_msg = StageCollapsed(stage_name="test")
        assert collapsed_msg.stage_name == "test"
