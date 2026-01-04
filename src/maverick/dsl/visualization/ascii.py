"""ASCII diagram generator for workflow visualization.

This module implements the ASCIIGenerator class which produces terminal-friendly
workflow diagrams using box-drawing characters.

The generator creates diagrams with:
- Workflow header with name and description
- Input parameters section
- Numbered steps with type annotations
- Box-drawing characters for structure
- Arrows for flow control
- Indentation for nested structures

Example output:
    ┌─────────────────────────────────────┐
    │ Workflow: my-workflow               │
    │ A simple example workflow           │
    ├─────────────────────────────────────┤
    │ Inputs:                             │
    │   target (string, required)         │
    │   verbose (boolean, default: false) │
    ├─────────────────────────────────────┤
    │ 1. [python] process_data            │
    │       ↓                             │
    │ 2. [validate] check_format          │
    │    ├─ on fail → 2a. fix_format      │
    │    │            └─ retry → 2.       │
    │    └─ on pass ↓                     │
    │ 3. [agent] code_review              │
    │    └─ when: inputs.review_enabled   │
    │       ↓                             │
    │ 4. [python] deploy                  │
    └─────────────────────────────────────┘
"""

from __future__ import annotations

from maverick.dsl.config import DEFAULTS
from maverick.dsl.serialization.schema import (
    BranchStepRecord,
    InputDefinition,
    LoopStepRecord,
    StepRecordUnion,
    ValidateStepRecord,
    WorkflowFile,
)

# Module-level constants for ASCII diagram layout
# These are kept for backward compatibility but now reference DEFAULTS
DEFAULT_WIDTH = DEFAULTS.ASCII_DIAGRAM_WIDTH
BORDER_CORNERS_WIDTH = DEFAULTS.ASCII_DIAGRAM_BORDER_WIDTH
BORDER_WITH_SPACE = DEFAULTS.ASCII_DIAGRAM_PADDING
TOTAL_PADDING_WIDTH = BORDER_WITH_SPACE * 2  # Total padding on both sides

__all__ = [
    "ASCIIGenerator",
    "DEFAULT_WIDTH",
    "BORDER_CORNERS_WIDTH",
    "BORDER_WITH_SPACE",
    "TOTAL_PADDING_WIDTH",
]


class ASCIIGenerator:
    """Generator for ASCII diagrams (FR-021).

    Produces terminal-friendly workflow diagrams using box-drawing characters
    and arrows to represent workflow structure and flow.

    Attributes:
        width: Maximum diagram width in characters.

    """

    def __init__(self, width: int = DEFAULT_WIDTH) -> None:
        """Initialize ASCII generator.

        Args:
            width: Maximum diagram width in characters. Default is 60 per FR-021.

        """
        self.width = width

    def generate(self, workflow: WorkflowFile) -> str:
        """Generate ASCII diagram from workflow definition.

        Args:
            workflow: WorkflowFile to visualize.

        Returns:
            ASCII diagram string using box-drawing characters.

        Example:
            >>> generator = ASCIIGenerator(width=60)
            >>> diagram = generator.generate(workflow)
            >>> print(diagram)

        """
        lines: list[str] = []

        # Draw header
        lines.extend(self._draw_header(workflow))

        # Draw inputs if present
        if workflow.inputs:
            lines.extend(self._draw_inputs(workflow.inputs))

        # Draw steps
        lines.extend(self._draw_steps(workflow.steps))

        # Close box
        lines.append(self._draw_bottom_border())

        return "\n".join(lines)

    def _draw_header(self, workflow: WorkflowFile) -> list[str]:
        """Draw workflow name and description.

        Args:
            workflow: Workflow with metadata.

        Returns:
            List of header lines.

        """
        lines: list[str] = []

        # Top border
        lines.append(self._draw_top_border())

        # Workflow name
        name_line = f"Workflow: {workflow.name}"
        lines.append(self._draw_content_line(name_line))

        # Description if present
        if workflow.description:
            lines.append(self._draw_content_line(workflow.description))

        return lines

    def _draw_inputs(self, inputs: dict[str, InputDefinition]) -> list[str]:
        """Draw input parameters section.

        Args:
            inputs: Dictionary of input definitions.

        Returns:
            List of input section lines.

        """
        lines: list[str] = []

        # Section divider
        lines.append(self._draw_divider())

        # Inputs header
        lines.append(self._draw_content_line("Inputs:"))

        # Each input
        for name, definition in inputs.items():
            input_str = self._format_input(name, definition)
            lines.append(self._draw_content_line(f"  {input_str}"))

        return lines

    def _draw_steps(self, steps: list[StepRecordUnion]) -> list[str]:
        """Draw steps with arrows and annotations.

        Args:
            steps: List of step definitions.

        Returns:
            List of step section lines.

        """
        lines: list[str] = []

        # Section divider (if we have inputs, otherwise just mark steps section)
        lines.append(self._draw_divider())
        lines.append(self._draw_content_line("Steps:"))
        lines.append(self._draw_content_line(""))

        # Draw each step
        for index, step in enumerate(steps, start=1):
            step_lines = self._draw_step(step, index)
            lines.extend(step_lines)

            # Add arrow to next step (if not last)
            if index < len(steps):
                lines.append(self._draw_content_line("   ↓"))

        return lines

    def _draw_step(self, step: StepRecordUnion, index: int) -> list[str]:
        """Draw a single step with type annotation.

        Args:
            step: Step definition.
            index: Step number (1-based).

        Returns:
            List of lines for this step.

        """
        lines: list[str] = []

        # Determine step type label
        type_label = self._get_type_label(step)

        # Main step line
        main_line = f"{index}. [{type_label}] {step.name}"
        lines.append(self._draw_content_line(main_line))

        # Add when clause if present
        if step.when:
            when_line = f"   └─ when: {step.when}"
            lines.append(self._draw_content_line(when_line))

        # Handle step-specific rendering
        if isinstance(step, ValidateStepRecord):
            lines.extend(self._draw_validate_details(step, index))
        elif isinstance(step, BranchStepRecord):
            lines.extend(self._draw_branch_details(step, index))
        elif isinstance(step, LoopStepRecord):
            lines.extend(self._draw_parallel_details(step, index))

        return lines

    def _draw_validate_details(
        self,
        step: ValidateStepRecord,
        index: int,
    ) -> list[str]:
        """Draw validate step details (stages, retry, on_failure).

        Args:
            step: Validate step definition.
            index: Step number for substep labeling.

        Returns:
            List of detail lines.

        """
        lines: list[str] = []

        # Show stages if it's a list
        if isinstance(step.stages, list):
            stages_str = ", ".join(step.stages)
            lines.append(self._draw_content_line(f"   ├─ stages: {stages_str}"))

        # Show retry count
        if step.retry > 0:
            lines.append(self._draw_content_line(f"   ├─ retry: {step.retry}"))

        # Show on_failure step if present
        if step.on_failure:
            on_fail_type = self._get_type_label(step.on_failure)
            on_fail_name = step.on_failure.name
            on_fail_line = f"   ├─ on_fail → {index}a. [{on_fail_type}] {on_fail_name}"
            lines.append(self._draw_content_line(on_fail_line))
            # Show retry loop
            retry_line = f"   │            └─ retry → {index}."
            lines.append(self._draw_content_line(retry_line))
            # Show on_pass path
            lines.append(self._draw_content_line("   └─ on_pass ↓"))
        elif step.retry > 0 or isinstance(step.stages, list):
            # Close the tree if we showed stages/retry but no on_failure
            lines.append(self._draw_content_line("   └─ on_pass ↓"))

        return lines

    def _draw_branch_details(self, step: BranchStepRecord, index: int) -> list[str]:
        """Draw branch step options.

        Args:
            step: Branch step definition.
            index: Step number for substep labeling.

        Returns:
            List of detail lines.

        """
        lines: list[str] = []

        for opt_index, option in enumerate(step.options):
            substep_type = self._get_type_label(option.step)
            substep_name = option.step.name
            # Show condition and substep
            lines.append(self._draw_content_line(f"   ├─ when: {option.when}"))
            substep_line = (
                f"   │  └─ {index}{chr(97 + opt_index)}. "
                f"[{substep_type}] {substep_name}"
            )
            lines.append(
                self._draw_content_line(substep_line),
            )

        return lines

    def _draw_parallel_details(
        self,
        step: LoopStepRecord,
        index: int,
    ) -> list[str]:
        """Draw parallel substeps.

        Args:
            step: Parallel step definition.
            index: Step number for substep labeling.

        Returns:
            List of detail lines.

        """
        lines: list[str] = []

        for substep_index, substep in enumerate(step.steps):
            substep_type = self._get_type_label(substep)
            connector = "├─" if substep_index < len(step.steps) - 1 else "└─"
            substep_line = (
                f"   {connector} {index}{chr(97 + substep_index)}. "
                f"[{substep_type}] {substep.name}"
            )
            lines.append(self._draw_content_line(substep_line))

        return lines

    def _get_type_label(self, step: StepRecordUnion) -> str:
        """Get type label for a step.

        Args:
            step: Step definition.

        Returns:
            Type label string (e.g., "python", "agent").

        """
        return step.type.value

    def _format_input(self, name: str, definition: InputDefinition) -> str:
        """Format input parameter for display.

        Args:
            name: Input parameter name.
            definition: Input definition.

        Returns:
            Formatted input string.

        """
        type_str = definition.type.value
        if definition.required:
            return f"{name} ({type_str}, required)"
        return f"{name} ({type_str}, default: {definition.default})"

    def _draw_top_border(self) -> str:
        """Draw top border of box.

        Returns:
            Top border line.

        """
        return "┌" + "─" * (self.width - BORDER_CORNERS_WIDTH) + "┐"

    def _draw_bottom_border(self) -> str:
        """Draw bottom border of box.

        Returns:
            Bottom border line.

        """
        return "└" + "─" * (self.width - BORDER_CORNERS_WIDTH) + "┘"

    def _draw_divider(self) -> str:
        """Draw section divider.

        Returns:
            Divider line.

        """
        return "├" + "─" * (self.width - BORDER_CORNERS_WIDTH) + "┤"

    def _draw_content_line(self, content: str) -> str:
        """Draw a content line within the box.

        Args:
            content: Content to display (without box borders).

        Returns:
            Line with box borders and padding.

        """
        # Calculate available width for content
        available_width = self.width - TOTAL_PADDING_WIDTH  # Account for "│ " and " │"

        # Truncate if too long using textwrap for Unicode-safe truncation
        if len(content) > available_width:
            import textwrap

            content = textwrap.shorten(
                content, width=available_width, placeholder="..."
            )

        # Pad to width
        padded = content.ljust(available_width)

        return f"│ {padded} │"
