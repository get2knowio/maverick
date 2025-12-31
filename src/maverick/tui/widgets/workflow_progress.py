"""WorkflowProgress widget for displaying workflow stages.

This widget displays workflow stages vertically with status icons, duration,
and expandable details. Part of User Story 1 for feature 012-workflow-widgets.

Features:
- Status icons: pending (○), active (animated spinner), completed (✓), failed (✗ in red)
- Duration display for completed stages (e.g., "12s", "1m 30s")
- Expandable details via Collapsible
- Loading and empty states
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import replace

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Collapsible, Label, LoadingIndicator, Static

from maverick.tui.metrics import widget_metrics
from maverick.tui.models import StageStatus, WorkflowProgressState, WorkflowStage

# =============================================================================
# Messages
# =============================================================================


class StageExpanded(Message):
    """Message emitted when a workflow stage is expanded."""

    def __init__(self, stage_name: str) -> None:
        """Initialize message.

        Args:
            stage_name: Name of the expanded stage.
        """
        super().__init__()
        self.stage_name = stage_name


class StageCollapsed(Message):
    """Message emitted when a workflow stage is collapsed."""

    def __init__(self, stage_name: str) -> None:
        """Initialize message.

        Args:
            stage_name: Name of the collapsed stage.
        """
        super().__init__()
        self.stage_name = stage_name


class WorkflowProgress(Widget):
    """WorkflowProgress widget displays workflow stages vertically.

    The widget shows a list of workflow stages with:
    - Status icons indicating stage state (pending, active, completed, failed)
    - Duration for completed stages
    - Expandable details for stages with additional content
    - Loading state indicator
    - Empty state when no stages are present

    Attributes:
        state: Reactive WorkflowProgressState tracking all widget data.
    """

    BINDINGS = [
        Binding("up", "move_up", "Previous stage", show=False),
        Binding("down", "move_down", "Next stage", show=False),
        Binding("enter", "toggle_expand", "Expand/collapse", show=False),
    ]

    ICONS = {
        StageStatus.PENDING: "○",
        StageStatus.COMPLETED: "✓",
        StageStatus.FAILED: "✗",
    }

    state: reactive[WorkflowProgressState] = reactive(
        WorkflowProgressState, always_update=True
    )

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Initialize WorkflowProgress widget.

        Args:
            name: Widget name.
            id: Widget ID.
            classes: CSS classes.
        """
        super().__init__(name=name, id=id, classes=classes)
        self.state = WorkflowProgressState()

    def render(self) -> str:
        """Render the widget content.

        Returns:
            Rendered text for the widget.
        """
        if self.state.is_empty:
            return "No workflow stages"
        if self.state.loading:
            return "Loading workflow stages..."
        return ""

    def compose(self) -> ComposeResult:
        """Compose the widget's child widgets."""
        with VerticalScroll(id="workflow-progress-container"):
            yield Static("No workflow stages", classes="empty-state")

    def update_stages(self, stages: Sequence[WorkflowStage]) -> None:
        """Update all stages with new data.

        Args:
            stages: Sequence of WorkflowStage objects in display order.
        """
        # Track message throughput (stage updates)
        widget_metrics.record_message("WorkflowProgress")

        self.state = replace(self.state, stages=tuple(stages))
        self._rebuild_stages()

    def update_stage_status(
        self,
        stage_name: str,
        status: str,
        *,
        error_message: str | None = None,
    ) -> None:
        """Update a single stage's status.

        Args:
            stage_name: The stage identifier.
            status: New status value ("pending", "active", "completed", "failed").
            error_message: Error details if status is "failed".
        """
        # Find and update the stage
        updated_stages = []
        found = False

        for stage in self.state.stages:
            if stage.name == stage_name:
                found = True
                # Convert string status to StageStatus enum
                try:
                    new_status = StageStatus(status)
                except ValueError:
                    # Invalid status, skip update
                    updated_stages.append(stage)
                    continue

                # Update stage with new status and error message
                updated_stage = replace(
                    stage,
                    status=new_status,
                    error_message=error_message
                    if error_message
                    else stage.error_message,
                )
                updated_stages.append(updated_stage)
            else:
                updated_stages.append(stage)

        if found:
            self.state = replace(self.state, stages=tuple(updated_stages))
            self._rebuild_stages()

    def expand_stage(self, stage_name: str) -> None:
        """Expand a stage to show details.

        Args:
            stage_name: The stage to expand.
        """
        self.state = replace(self.state, expanded_stage=stage_name)
        self._rebuild_stages()
        self.post_message(StageExpanded(stage_name))

    def collapse_stage(self, stage_name: str) -> None:
        """Collapse an expanded stage.

        Args:
            stage_name: The stage to collapse.
        """
        if self.state.expanded_stage == stage_name:
            self.state = replace(self.state, expanded_stage=None)
            self._rebuild_stages()
            self.post_message(StageCollapsed(stage_name))

    def set_loading(self, loading: bool) -> None:
        """Set the loading state.

        Args:
            loading: Whether to show loading state.
        """
        self.state = replace(self.state, loading=loading)
        self._rebuild_stages()

    def _rebuild_stages(self) -> None:
        """Rebuild the stages display."""
        # Track render time
        start_time = time.perf_counter() if widget_metrics.enabled else 0.0

        try:
            container = self.query_one("#workflow-progress-container", VerticalScroll)
        except Exception:
            # Widget not yet mounted
            return

        # Remove all children
        for child in list(container.children):
            child.remove()

        # Show loading state
        if self.state.loading:
            container.mount(
                Static("Loading workflow stages...", classes="loading-state")
            )
            return

        # Show empty state
        if self.state.is_empty:
            container.mount(Static("No workflow stages", classes="empty-state"))
            return

        # Build stage widgets
        for stage in self.state.stages:
            container.mount(self._create_stage_widget(stage))

        # Record render time
        if widget_metrics.enabled:
            duration_ms = (time.perf_counter() - start_time) * 1000
            widget_metrics.record_render("WorkflowProgress", duration_ms)

    def _create_stage_widget(self, stage: WorkflowStage) -> Widget:
        """Create a widget for a single stage.

        Args:
            stage: The workflow stage to render.

        Returns:
            Widget representing the stage.
        """
        status_class = f"status-{stage.status.value}"

        # For active stages, create a container with LoadingIndicator
        if stage.status == StageStatus.ACTIVE:
            # Build header text without icon (indicator will be shown separately)
            header_text = stage.display_name
            if stage.duration_display:
                header_text += f" ({stage.duration_display})"

            # If stage has details or error, make it expandable
            if stage.detail_content or stage.error_message:
                is_expanded = self.state.expanded_stage == stage.name

                # Determine detail content
                if stage.error_message:
                    detail_text = stage.error_message
                    detail_classes = "stage-detail error-detail"
                elif stage.detail_content:
                    detail_text = stage.detail_content
                    detail_classes = "stage-detail"
                else:
                    detail_text = ""
                    detail_classes = "stage-detail"

                # Create expandable container with spinner
                class ActiveStageItemContainer(Vertical):
                    """Container for active stage with collapsible details."""

                    def compose(self) -> ComposeResult:
                        """Compose the stage item with spinner and collapsible."""
                        # Header with spinner
                        with Horizontal(classes="stage-header-active"):
                            yield LoadingIndicator(classes="stage-spinner")
                            yield Label(
                                header_text, classes=f"stage-label {status_class}"
                            )

                        # Inner collapsible class for details
                        class StageCollapsibleWidget(Collapsible):
                            """Custom collapsible for stage details."""

                            def compose(self) -> ComposeResult:
                                yield Static(detail_text, classes=detail_classes)

                        yield StageCollapsibleWidget(
                            title="Details",
                            collapsed=not is_expanded,
                            classes=f"stage-collapsible {status_class}",
                        )

                return ActiveStageItemContainer(classes="stage-item active-stage-item")
            else:
                # Simple active stage without expansion
                class ActiveStageContainer(Horizontal):
                    """Container for active stage with animated spinner."""

                    def compose(self) -> ComposeResult:
                        yield LoadingIndicator(classes="stage-spinner")
                        yield Label(header_text, classes=f"stage-label {status_class}")

                return ActiveStageContainer(
                    classes=f"stage-header {status_class} active-stage"
                )

        # For non-active stages, use static icons
        icon = self.ICONS.get(stage.status, "○")

        # Build header text
        header_text = f"{icon} {stage.display_name}"
        if stage.duration_display:
            header_text += f" ({stage.duration_display})"

        # If stage has details or error, make it expandable
        if stage.detail_content or stage.error_message:
            is_expanded = self.state.expanded_stage == stage.name

            # Determine detail content
            if stage.error_message:
                detail_text = stage.error_message
                detail_classes = "stage-detail error-detail"
            elif stage.detail_content:
                detail_text = stage.detail_content
                detail_classes = "stage-detail"
            else:
                detail_text = ""
                detail_classes = "stage-detail"

            # Create custom container class that composes children
            class StageItemContainer(Vertical):
                """Container for a stage with collapsible details."""

                def compose(self) -> ComposeResult:
                    """Compose the stage item with collapsible."""

                    # Inner collapsible class
                    class StageCollapsibleWidget(Collapsible):
                        """Custom collapsible for stage details."""

                        def compose(self) -> ComposeResult:
                            yield Static(detail_text, classes=detail_classes)

                    yield StageCollapsibleWidget(
                        title=header_text,
                        collapsed=not is_expanded,
                        classes=f"stage-header {status_class}",
                    )

            return StageItemContainer(classes="stage-item")
        else:
            # Simple label without expansion
            return Label(header_text, classes=f"stage-header {status_class}")

    def watch_state(
        self, old_state: WorkflowProgressState, new_state: WorkflowProgressState
    ) -> None:
        """React to state changes.

        Args:
            old_state: Previous state.
            new_state: New state.
        """
        # The _rebuild_stages in update methods handles re-rendering
        pass

    # =========================================================================
    # Keyboard Navigation Actions
    # =========================================================================

    def action_move_up(self) -> None:
        """Move focus to previous stage."""
        if self.state.is_empty:
            return

        stages = self.state.stages
        if not stages:
            return

        # Find current focused index
        focused_name = self.state.expanded_stage
        current_index = -1
        for i, stage in enumerate(stages):
            if stage.name == focused_name:
                current_index = i
                break

        # Move up (with wrap-around)
        new_index = len(stages) - 1 if current_index <= 0 else current_index - 1

        # Update expanded stage to show focus
        new_stage = stages[new_index]
        if new_stage.detail_content or new_stage.error_message:
            self.expand_stage(new_stage.name)

    def action_move_down(self) -> None:
        """Move focus to next stage."""
        if self.state.is_empty:
            return

        stages = self.state.stages
        if not stages:
            return

        # Find current focused index
        focused_name = self.state.expanded_stage
        current_index = -1
        for i, stage in enumerate(stages):
            if stage.name == focused_name:
                current_index = i
                break

        # Move down (with wrap-around)
        if current_index < 0 or current_index >= len(stages) - 1:
            new_index = 0
        else:
            new_index = current_index + 1

        # Update expanded stage to show focus
        new_stage = stages[new_index]
        if new_stage.detail_content or new_stage.error_message:
            self.expand_stage(new_stage.name)

    def action_toggle_expand(self) -> None:
        """Toggle expansion of the currently focused stage."""
        if self.state.expanded_stage:
            self.collapse_stage(self.state.expanded_stage)
        elif self.state.stages:
            # Expand the first stage with content
            for stage in self.state.stages:
                if stage.detail_content or stage.error_message:
                    self.expand_stage(stage.name)
                    break
