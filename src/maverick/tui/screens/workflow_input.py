"""Workflow input screen for configuring workflow parameters.

This screen dynamically generates a form based on the workflow's input schema,
allowing users to configure required and optional parameters before execution.

Supports input history for quick re-runs with previous values.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Button, Input, Static, Switch, TextArea

from maverick.dsl.serialization.schema import InputDefinition, InputType
from maverick.tui.input_history import InputHistoryEntry, get_input_history_store
from maverick.tui.screens.base import MaverickScreen

if TYPE_CHECKING:
    from maverick.dsl.discovery.models import DiscoveredWorkflow


class WorkflowInputScreen(MaverickScreen):
    """Configure workflow inputs before execution.

    This screen generates a dynamic form based on the workflow's input
    definitions, supporting various input types including strings, integers,
    booleans, floats, arrays, and objects.
    """

    TITLE = "Configure Workflow"

    BINDINGS = [
        Binding("ctrl+enter", "run_workflow", "Run", show=True),
        Binding("ctrl+l", "load_last_inputs", "Load Last", show=True),
        Binding("escape", "go_back", "Back", show=True),
    ]

    # Reactive state
    can_run: reactive[bool] = reactive(False)
    has_history: reactive[bool] = reactive(False)

    def __init__(
        self,
        workflow: DiscoveredWorkflow,
        *,
        prefill_inputs: dict[str, Any] | None = None,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Initialize the workflow input screen.

        Args:
            workflow: The discovered workflow to configure.
            prefill_inputs: Optional inputs to pre-fill the form with.
            name: Widget name.
            id: Widget ID.
            classes: CSS classes.
        """
        super().__init__(name=name, id=id, classes=classes)
        self._workflow = workflow
        self._prefill_inputs = prefill_inputs
        self._input_values: dict[str, Any] = {}
        self._validation_errors: dict[str, str] = {}
        self._field_widgets: dict[str, Input | Switch | TextArea] = {}
        self._history_store = get_input_history_store()
        self._last_history_entry: InputHistoryEntry | None = None

    def compose(self) -> ComposeResult:
        """Create the input form layout."""
        workflow = self._workflow.workflow

        yield Static(
            f"[bold]{workflow.name}[/bold]",
            id="input-title",
        )
        yield Static(
            workflow.description or "[dim]No description[/dim]",
            id="input-description",
        )

        with Vertical(id="form-container"):
            # Generate form fields for each input
            for input_name, input_def in workflow.inputs.items():
                # Initialize with default value
                if input_def.default is not None:
                    self._input_values[input_name] = input_def.default

                yield from self._create_field(input_name, input_def)

        # History banner (shown if previous inputs exist)
        yield Static(
            "",
            id="history-banner",
            classes="history-banner hidden",
        )

        with Horizontal(id="button-bar"):
            yield Button(
                "Run Workflow",
                id="run-btn",
                variant="primary",
                disabled=True,
            )
            yield Button(
                "Load Previous",
                id="load-history-btn",
                variant="default",
                classes="hidden",
            )
            yield Button(
                "Back",
                id="back-btn",
                variant="default",
            )

    def _create_field(
        self,
        input_name: str,
        input_def: InputDefinition,
    ) -> ComposeResult:
        """Create form field widgets for an input definition.

        Args:
            input_name: Name of the input parameter.
            input_def: Input definition with type and constraints.

        Yields:
            Widgets for the form field.
        """
        # Field container
        with Vertical(classes="input-field", id=f"field-{input_name}"):
            # Label with required marker
            required_marker = "[red]*[/red] " if input_def.required else ""
            yield Static(
                f"{required_marker}[bold]{input_name}[/bold]",
                classes="field-label",
            )

            # Description
            if input_def.description:
                yield Static(
                    f"[dim]{input_def.description}[/dim]",
                    classes="field-description",
                )

            # Create appropriate widget based on type
            widget = self._create_widget(input_name, input_def)
            self._field_widgets[input_name] = widget
            yield widget

            # Error display
            yield Static(
                "",
                classes="field-error",
                id=f"error-{input_name}",
            )

    def _create_widget(
        self,
        input_name: str,
        input_def: InputDefinition,
    ) -> Input | Switch | TextArea:
        """Create the appropriate widget for an input type.

        Args:
            input_name: Name of the input parameter.
            input_def: Input definition with type and constraints.

        Returns:
            Widget appropriate for the input type.
        """
        input_type = input_def.type
        default = input_def.default

        if input_type == InputType.BOOLEAN:
            return Switch(
                value=bool(default) if default is not None else False,
                id=f"input-{input_name}",
            )

        if input_type == InputType.INTEGER:
            return Input(
                value=str(default) if default is not None else "",
                placeholder="Enter integer value",
                id=f"input-{input_name}",
                type="integer",
            )

        if input_type == InputType.FLOAT:
            return Input(
                value=str(default) if default is not None else "",
                placeholder="Enter decimal value",
                id=f"input-{input_name}",
                type="number",
            )

        if input_type in (InputType.ARRAY, InputType.OBJECT):
            # Use TextArea for JSON input
            default_json = ""
            if default is not None:
                try:
                    default_json = json.dumps(default, indent=2)
                except (TypeError, ValueError):
                    default_json = str(default)

            return TextArea(
                text=default_json,
                id=f"input-{input_name}",
            )

        # Default: STRING type
        return Input(
            value=str(default) if default is not None else "",
            placeholder=f"Enter {input_name}",
            id=f"input-{input_name}",
        )

    def on_mount(self) -> None:
        """Initialize the screen and validate initial state."""
        super().on_mount()

        # Check for input history
        workflow_name = self._workflow.workflow.name
        self._last_history_entry = self._history_store.get_last_inputs(workflow_name)
        self.has_history = self._last_history_entry is not None

        # Apply prefill inputs if provided
        if self._prefill_inputs:
            self._apply_inputs(self._prefill_inputs)
        elif self._last_history_entry:
            # Show history banner
            self._show_history_banner()

        self._validate_all()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input value changes."""
        input_id = event.input.id
        if input_id and input_id.startswith("input-"):
            input_name = input_id[6:]  # Remove "input-" prefix
            self._input_values[input_name] = event.value
            self._validate_field(input_name)
            self._update_can_run()

    def on_switch_changed(self, event: Switch.Changed) -> None:
        """Handle switch (boolean) value changes."""
        switch_id = event.switch.id
        if switch_id and switch_id.startswith("input-"):
            input_name = switch_id[6:]  # Remove "input-" prefix
            self._input_values[input_name] = event.value
            self._validate_field(input_name)
            self._update_can_run()

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        """Handle text area (JSON) value changes."""
        text_area_id = event.text_area.id
        if text_area_id and text_area_id.startswith("input-"):
            input_name = text_area_id[6:]  # Remove "input-" prefix
            self._input_values[input_name] = event.text_area.text
            self._validate_field(input_name)
            self._update_can_run()

    def _validate_all(self) -> None:
        """Validate all input fields."""
        for input_name in self._workflow.workflow.inputs:
            self._validate_field(input_name)
        self._update_can_run()

    def _validate_field(self, input_name: str) -> None:
        """Validate a single input field.

        Args:
            input_name: Name of the input to validate.
        """
        input_def = self._workflow.workflow.inputs.get(input_name)
        if not input_def:
            return

        value = self._input_values.get(input_name)
        error = None

        # Check required
        if input_def.required and (
            value is None or (isinstance(value, str) and not value.strip())
        ):
            error = "This field is required"

        # Type-specific validation
        if error is None and value is not None:
            input_type = input_def.type

            if input_type == InputType.INTEGER:
                if isinstance(value, str) and value.strip():
                    try:
                        int(value)
                    except ValueError:
                        error = "Must be a valid integer"

            elif input_type == InputType.FLOAT:
                if isinstance(value, str) and value.strip():
                    try:
                        float(value)
                    except ValueError:
                        error = "Must be a valid number"

            elif input_type == InputType.ARRAY:
                if isinstance(value, str) and value.strip():
                    try:
                        parsed = json.loads(value)
                        if not isinstance(parsed, list):
                            error = "Must be a valid JSON array"
                    except json.JSONDecodeError as e:
                        error = f"Invalid JSON: {e}"

            elif input_type == InputType.OBJECT:
                is_non_empty_str = isinstance(value, str) and value.strip()
                if is_non_empty_str:
                    try:
                        parsed = json.loads(value)
                        if not isinstance(parsed, dict):
                            error = "Must be a valid JSON object"
                    except json.JSONDecodeError as e:
                        error = f"Invalid JSON: {e}"

        # Update error state
        if error:
            self._validation_errors[input_name] = error
        elif input_name in self._validation_errors:
            del self._validation_errors[input_name]

        # Update error display
        error_widget = self.query_one(f"#error-{input_name}", Static)
        error_widget.update(f"[red]{error}[/red]" if error else "")

    def _update_can_run(self) -> None:
        """Update the can_run state based on validation."""
        self.can_run = len(self._validation_errors) == 0

    def watch_can_run(self, can_run: bool) -> None:
        """React to can_run state changes."""
        run_btn = self.query_one("#run-btn", Button)
        run_btn.disabled = not can_run

    def watch_has_history(self, has_history: bool) -> None:
        """React to has_history state changes."""
        try:
            load_btn = self.query_one("#load-history-btn", Button)
            if has_history:
                load_btn.remove_class("hidden")
            else:
                load_btn.add_class("hidden")
        except Exception:
            pass

    def _show_history_banner(self) -> None:
        """Show the history availability banner."""
        if not self._last_history_entry:
            return

        try:
            banner = self.query_one("#history-banner", Static)
            banner.update(
                f"[dim]Previous inputs available from "
                f"{self._last_history_entry.display_timestamp}. "
                f"Press [cyan]Ctrl+L[/cyan] or click 'Load Previous' to use them.[/dim]"
            )
            banner.remove_class("hidden")
        except Exception:
            pass

    def _apply_inputs(self, inputs: dict[str, Any]) -> None:
        """Apply a set of inputs to the form fields.

        Args:
            inputs: Dictionary of input name to value.
        """
        for input_name, value in inputs.items():
            if input_name not in self._field_widgets:
                continue

            widget = self._field_widgets[input_name]
            input_def = self._workflow.workflow.inputs.get(input_name)
            if not input_def:
                continue

            # Update the widget based on its type
            if isinstance(widget, Switch):
                widget.value = bool(value)
                self._input_values[input_name] = bool(value)

            elif isinstance(widget, TextArea):
                # JSON input (array/object)
                if isinstance(value, (list, dict)):
                    text = json.dumps(value, indent=2)
                else:
                    text = str(value) if value is not None else ""
                widget.text = text
                self._input_values[input_name] = text

            elif isinstance(widget, Input):
                str_value = str(value) if value is not None else ""
                widget.value = str_value
                self._input_values[input_name] = str_value

        # Revalidate after applying inputs
        self._validate_all()

    def action_load_last_inputs(self) -> None:
        """Load the most recent inputs from history."""
        if not self._last_history_entry:
            return

        self._apply_inputs(self._last_history_entry.inputs)

        # Hide the banner after loading
        try:
            banner = self.query_one("#history-banner", Static)
            banner.add_class("hidden")
        except Exception:
            pass

        # Show confirmation
        self.notify("Previous inputs loaded", severity="information")

    def _get_typed_inputs(self) -> dict[str, Any]:
        """Convert input values to their proper types.

        Returns:
            Dictionary of input values with proper types.
        """
        typed_inputs: dict[str, Any] = {}

        for input_name, input_def in self._workflow.workflow.inputs.items():
            value = self._input_values.get(input_name)
            input_type = input_def.type

            if value is None or (isinstance(value, str) and not value.strip()):
                # Use default or None
                typed_inputs[input_name] = input_def.default
                continue

            # Convert to proper type
            if input_type == InputType.BOOLEAN:
                typed_inputs[input_name] = bool(value)

            elif input_type == InputType.INTEGER:
                typed_inputs[input_name] = int(value)

            elif input_type == InputType.FLOAT:
                typed_inputs[input_name] = float(value)

            elif input_type in (InputType.ARRAY, InputType.OBJECT):
                if isinstance(value, str):
                    typed_inputs[input_name] = json.loads(value)
                else:
                    typed_inputs[input_name] = value

            else:  # STRING
                typed_inputs[input_name] = str(value)

        return typed_inputs

    def action_run_workflow(self) -> None:
        """Run the workflow with configured inputs."""
        if not self.can_run:
            return

        try:
            typed_inputs = self._get_typed_inputs()
        except (ValueError, json.JSONDecodeError) as e:
            self.show_error("Invalid input values", details=str(e))
            return

        # Save inputs to history for future quick runs
        workflow_name = self._workflow.workflow.name
        self._history_store.save_inputs(workflow_name, typed_inputs)

        # Navigate to execution screen
        from maverick.tui.screens.workflow_execution import WorkflowExecutionScreen

        self.app.push_screen(
            WorkflowExecutionScreen(
                workflow=self._workflow.workflow,
                inputs=typed_inputs,
            )
        )

    def action_go_back(self) -> None:
        """Go back to the browser screen."""
        self.app.pop_screen()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "run-btn":
            self.action_run_workflow()
        elif event.button.id == "load-history-btn":
            self.action_load_last_inputs()
        elif event.button.id == "back-btn":
            self.action_go_back()
