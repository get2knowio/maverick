"""ValidationStatus widget for displaying validation step results.

This widget displays validation steps (format, lint, build, test) in a compact
horizontal layout with status icons and expandable error details for failed steps.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Button, Collapsible, Static

from maverick.tui.models import (
    ValidationStatusState,
    ValidationStep,
    ValidationStepStatus,
)


class ValidationStatus(Widget):
    """Displays validation steps with status icons and error expansion.

    The widget shows all steps in a horizontal row with status icons:
    - Pending: gray circle (○)
    - Running: spinner (◠)
    - Passed: green checkmark (✓)
    - Failed: red X (✗)

    Failed steps can be expanded to show error output. Each step has a
    re-run button that can be enabled/disabled.

    Messages:
        StepExpanded: Emitted when a failed step is expanded
        StepCollapsed: Emitted when a step is collapsed
        RerunRequested: Emitted when a re-run button is clicked
    """

    DEFAULT_CSS = """
    ValidationStatus {
        height: auto;
        width: 100%;
    }

    ValidationStatus .validation-steps-row {
        height: auto;
        width: 100%;
    }

    ValidationStatus .step-container {
        width: auto;
        height: auto;
        margin: 0 1;
    }

    ValidationStatus .step-header {
        width: auto;
        height: 1;
    }

    ValidationStatus .step-status {
        width: auto;
    }

    ValidationStatus .step-name {
        width: auto;
    }

    ValidationStatus .rerun-button {
        width: auto;
        min-width: 8;
        height: 1;
    }

    ValidationStatus .error-output {
        padding: 1;
        background: $error 20%;
        border: solid $error;
        margin: 1 0;
    }

    ValidationStatus .empty-state {
        height: 3;
        content-align: center middle;
        color: $text-muted;
    }

    ValidationStatus .loading-state {
        height: 3;
        content-align: center middle;
        color: $text-muted;
    }

    /* Status-specific colors */
    ValidationStatus .status-pending {
        color: $text-muted;
    }

    ValidationStatus .status-running {
        color: $accent;
    }

    ValidationStatus .status-passed {
        color: $success;
    }

    ValidationStatus .status-failed {
        color: $error;
    }
    """

    BINDINGS = [
        Binding("left", "move_left", "Previous step", show=False),
        Binding("right", "move_right", "Next step", show=False),
        Binding("enter", "toggle_expand", "Expand/collapse", show=False),
        Binding("r", "rerun_focused", "Re-run step", show=False),
    ]

    # Status icons
    ICONS = {
        "pending": "○",
        "running": "◠",  # Simple spinner representation
        "passed": "✓",
        "failed": "✗",
    }

    # Messages
    class StepExpanded(Message):
        """Emitted when a step is expanded."""

        def __init__(self, step_name: str) -> None:
            super().__init__()
            self.step_name = step_name

    class StepCollapsed(Message):
        """Emitted when a step is collapsed."""

        def __init__(self, step_name: str) -> None:
            super().__init__()
            self.step_name = step_name

    class RerunRequested(Message):
        """Emitted when re-run is requested for a step."""

        def __init__(self, step_name: str) -> None:
            super().__init__()
            self.step_name = step_name

    # Reactive state - don't use init=False to avoid watcher issues
    _state: reactive[ValidationStatusState] = reactive(ValidationStatusState())

    def __init__(
        self,
        *,
        id: str | None = None,
    ) -> None:
        """Initialize the ValidationStatus widget.

        Args:
            id: Optional widget ID.
        """
        super().__init__(id=id)
        # Track rerun button enabled state for each step
        self._rerun_enabled: dict[str, bool] = {}

    @property
    def state(self) -> ValidationStatusState:
        """Get the current state."""
        return self._state

    def compose(self) -> ComposeResult:
        """Compose the widget."""
        # Create a container that we'll update reactively
        yield Horizontal(id="steps-container", classes="validation-steps-row")

    def on_mount(self) -> None:
        """Update display after mount."""
        self._update_display()

    def watch__state(
        self, old_state: ValidationStatusState, new_state: ValidationStatusState
    ) -> None:
        """React to state changes by re-rendering."""
        if self.is_mounted:
            self._update_display()

    def _update_display(self) -> None:
        """Update the display based on current state."""
        try:
            container = self.query_one("#steps-container", Horizontal)
        except Exception:
            # Container not yet available
            return

        container.remove_children()

        if self.state.loading:
            container.mount(
                Static("Loading validation steps...", classes="loading-state")
            )
        elif self.state.is_empty:
            container.mount(Static("No validation steps", classes="empty-state"))
        else:
            self._render_steps(container)

    def _render_steps(self, container: Horizontal) -> None:
        """Render all validation steps in the given container.

        Args:
            container: The container to mount steps into.
        """
        for step in self.state.steps:
            # Build the step container with all its children
            step_container = self._build_step_container(step)
            container.mount(step_container)

    def _build_step_container(self, step: ValidationStep) -> Vertical:
        """Build a complete step container with all children.

        Args:
            step: The validation step to render.

        Returns:
            A Vertical container with the step's UI elements.
        """
        # Status icon
        icon = self.ICONS.get(step.status.value, "○")
        status_class = f"status-{step.status.value}"

        # Re-run button
        rerun_enabled = self._rerun_enabled.get(step.name, True)
        disabled = not rerun_enabled or step.status == ValidationStepStatus.RUNNING

        # Build the container using compose-style approach
        # Create container first
        step_container = Vertical(classes="step-container")

        # Create and compose header
        step_header = Horizontal(classes="step-header")
        step_header.compose_add_child(
            Static(icon, classes=f"step-status {status_class}")
        )
        step_header.compose_add_child(Static(step.display_name, classes="step-name"))

        # Add header to container
        step_container.compose_add_child(step_header)

        # Add re-run button (only for failed steps per FR-028)
        if step.status == ValidationStepStatus.FAILED:
            step_container.compose_add_child(
                Button(
                    "⟳ Rerun",
                    id=f"rerun-{step.name}",
                    classes="rerun-button",
                    disabled=disabled,
                )
            )

        # Error output for failed steps (collapsible)
        if step.status == ValidationStepStatus.FAILED and step.error_output:
            is_expanded = self.state.expanded_step == step.name
            error_collapsible = Collapsible(
                title="Error Details",
                collapsed=not is_expanded,
                id=f"error-{step.name}",
            )
            error_collapsible.compose_add_child(
                Static(step.error_output, classes="error-output")
            )
            step_container.compose_add_child(error_collapsible)

        return step_container

    def update_steps(self, steps: Sequence[ValidationStep]) -> None:
        """Update all validation steps.

        Args:
            steps: Sequence of validation step data.
        """
        self._state = replace(self._state, steps=tuple(steps))

    def update_step_status(
        self,
        step_name: str,
        status: ValidationStepStatus,
        *,
        error_output: str | None = None,
    ) -> None:
        """Update a single step's status.

        Args:
            step_name: The step identifier.
            status: New status value.
            error_output: Error details if status is FAILED.
        """
        updated_steps = []
        running_step = None

        for step in self.state.steps:
            if step.name == step_name:
                # Update this step
                updated_step = replace(
                    step,
                    status=status,
                    error_output=error_output
                    if error_output is not None
                    else step.error_output,
                )
                updated_steps.append(updated_step)

                if status == ValidationStepStatus.RUNNING:
                    running_step = step_name
            else:
                updated_steps.append(step)

                # Track if any other step is running
                if step.status == ValidationStepStatus.RUNNING:
                    running_step = step.name

        self._state = replace(
            self._state,
            steps=tuple(updated_steps),
            running_step=running_step,
        )

    def expand_step(self, step_name: str) -> None:
        """Expand a failed step to show error details.

        Args:
            step_name: The step to expand.
        """
        # Check if step exists
        step_exists = any(step.name == step_name for step in self.state.steps)
        if not step_exists:
            return

        self._state = replace(self._state, expanded_step=step_name)
        self.post_message(self.StepExpanded(step_name))

    def collapse_step(self) -> None:
        """Collapse the currently expanded step."""
        if self.state.expanded_step:
            step_name = self.state.expanded_step
            self._state = replace(self._state, expanded_step=None)
            self.post_message(self.StepCollapsed(step_name))

    def set_rerun_enabled(self, step_name: str, enabled: bool) -> None:
        """Enable or disable the re-run button for a step.

        Args:
            step_name: The step identifier.
            enabled: Whether re-run should be enabled.
        """
        self._rerun_enabled[step_name] = enabled
        self.refresh(recompose=True)

    @on(Button.Pressed)
    def on_rerun_button_pressed(self, event: Button.Pressed) -> None:
        """Handle re-run button press."""
        if event.button.id and event.button.id.startswith("rerun-"):
            step_name = event.button.id.replace("rerun-", "")
            self.post_message(self.RerunRequested(step_name))
            event.stop()

    @on(Collapsible.Toggled)
    def on_collapsible_toggled(self, event: Collapsible.Toggled) -> None:
        """Handle collapsible toggle."""
        if event.collapsible.id and event.collapsible.id.startswith("error-"):
            step_name = event.collapsible.id.replace("error-", "")

            if event.collapsible.collapsed:
                # Collapsed
                if self.state.expanded_step == step_name:
                    self._state = replace(self._state, expanded_step=None)
                    self.post_message(self.StepCollapsed(step_name))
            else:
                # Expanded
                self._state = replace(self._state, expanded_step=step_name)
                self.post_message(self.StepExpanded(step_name))

            event.stop()

    # =========================================================================
    # Keyboard Navigation Actions
    # =========================================================================

    def action_move_left(self) -> None:
        """Move focus to previous step."""
        if self.state.is_empty:
            return

        steps = self.state.steps
        if not steps:
            return

        # Find current focused step
        current_name = self.state.expanded_step
        current_index = -1
        for i, step in enumerate(steps):
            if step.name == current_name:
                current_index = i
                break

        # Move left (with wrap-around)
        new_index = len(steps) - 1 if current_index <= 0 else current_index - 1

        # Focus the step (expand if failed)
        new_step = steps[new_index]
        if new_step.status == ValidationStepStatus.FAILED:
            self.expand_step(new_step.name)

    def action_move_right(self) -> None:
        """Move focus to next step."""
        if self.state.is_empty:
            return

        steps = self.state.steps
        if not steps:
            return

        # Find current focused step
        current_name = self.state.expanded_step
        current_index = -1
        for i, step in enumerate(steps):
            if step.name == current_name:
                current_index = i
                break

        # Move right (with wrap-around)
        if current_index < 0 or current_index >= len(steps) - 1:
            new_index = 0
        else:
            new_index = current_index + 1

        # Focus the step (expand if failed)
        new_step = steps[new_index]
        if new_step.status == ValidationStepStatus.FAILED:
            self.expand_step(new_step.name)

    def action_toggle_expand(self) -> None:
        """Toggle expansion of the currently expanded step."""
        if self.state.expanded_step:
            self.collapse_step()
        elif self.state.steps:
            # Expand first failed step
            for step in self.state.steps:
                if step.status == ValidationStepStatus.FAILED:
                    self.expand_step(step.name)
                    break

    def action_rerun_focused(self) -> None:
        """Re-run the currently focused step."""
        if self.state.expanded_step:
            self.post_message(self.RerunRequested(self.state.expanded_step))
