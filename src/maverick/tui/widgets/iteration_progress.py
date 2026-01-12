"""IterationProgress widget for displaying loop iteration progress.

This widget displays loop iteration progress with status icons, indentation for
nested loops, and duration display for completed iterations.

Features:
- Status icons for all 6 IterationStatus values
  (pending, running, completed, failed, skipped, cancelled)
- Nested loop indentation (2 spaces per nesting level, up to 3 levels)
- Collapsed indicator for nesting levels 4+ with expandable toggle
- Duration display for completed/failed iterations (e.g., "(1500ms)")
- Empty state indicator when no iterations present
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Static

from maverick.tui.models.enums import IterationStatus
from maverick.tui.models.widget_state import LoopIterationState

# Status icons for each iteration status
# Based on quickstart.md specification
STATUS_ICONS: dict[IterationStatus, str] = {
    IterationStatus.PENDING: "\u25cb",  # ○ Open circle
    IterationStatus.RUNNING: "\u25cf",  # ● Filled circle
    IterationStatus.COMPLETED: "\u2713",  # ✓ Checkmark
    IterationStatus.FAILED: "\u2717",  # ✗ X mark
    IterationStatus.SKIPPED: "\u2298",  # ⊘ Circle with slash
    IterationStatus.CANCELLED: "\u2297",  # ⊗ Circle with X
}

# Expand/collapse icons
EXPAND_ICON = "\u25b6"  # ▶ Right-pointing triangle
COLLAPSE_ICON = "\u25bc"  # ▼ Down-pointing triangle


class IterationProgress(Widget):
    """Widget displaying loop iteration progress.

    Displays a list of iterations with status icons, labels, and durations.
    Supports nested loops with indentation (up to 3 levels visible).
    Nesting levels 4+ show a collapsed indicator with expandable toggle.

    Attributes:
        _state: Current LoopIterationState containing all iteration data.

    Class Attributes:
        MAX_VISIBLE_NESTING: Maximum nesting level to show full detail (0-3).
            Levels beyond this show a collapsed indicator.
    """

    MAX_VISIBLE_NESTING = 3  # Show full detail up to nesting level 3 (0, 1, 2, 3)

    DEFAULT_CSS = """
    IterationProgress {
        height: auto;
        min-height: 1;
    }
    """

    class ToggleExpanded(Message):
        """Message emitted when user toggles expand/collapse state.

        Attributes:
            step_name: Name of the loop step being toggled.
            expanded: New expanded state.
        """

        def __init__(self, step_name: str, expanded: bool) -> None:
            """Initialize ToggleExpanded message.

            Args:
                step_name: Name of the loop step being toggled.
                expanded: New expanded state.
            """
            super().__init__()
            self.step_name = step_name
            self.expanded = expanded

    def __init__(
        self,
        state: LoopIterationState,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Initialize IterationProgress widget.

        Args:
            state: Initial loop iteration state.
            name: Widget name.
            id: Widget ID.
            classes: CSS classes.
        """
        super().__init__(name=name, id=id, classes=classes)
        self._state = state

    def compose(self) -> ComposeResult:
        """Compose the widget's child widgets.

        Yields:
            Static widgets for each iteration or empty state indicator.
            For nesting levels > MAX_VISIBLE_NESTING, yields a collapsed indicator.
        """
        # Check if we're beyond max visible nesting level
        if self._state.nesting_level > self.MAX_VISIBLE_NESTING:
            yield from self._compose_collapsed()
            return

        # Check if explicitly collapsed
        if not self._state.expanded and self._state.iterations:
            yield from self._compose_collapsed()
            return

        with Vertical():
            # Handle empty state
            if not self._state.iterations:
                yield Static("No iterations", classes="iteration iteration-empty")
                return

            # Render each iteration
            for item in self._state.iterations:
                # Calculate indentation based on nesting level (2 spaces per level)
                # Capped at MAX_VISIBLE_NESTING to prevent excessive indentation
                indent_level = min(self._state.nesting_level, self.MAX_VISIBLE_NESTING)
                indent = "  " * indent_level

                # Get status icon
                icon = STATUS_ICONS.get(item.status, "\u25cb")  # Default to open circle

                # Build duration suffix if present
                duration = f" ({item.duration_ms}ms)" if item.duration_ms else ""

                # Compose the full display text
                display_text = f"{indent}{icon} {item.display_text}{duration}"

                # Yield Static with iteration-specific CSS class
                yield Static(
                    display_text,
                    classes=f"iteration iteration-{item.status.value}",
                )

    def _compose_collapsed(self) -> ComposeResult:
        """Compose the collapsed state indicator.

        Yields:
            Static widget showing collapsed indicator with expand toggle.
        """
        # Calculate indentation for the collapsed indicator
        # Use MAX_VISIBLE_NESTING as the cap for visual consistency
        indent_level = min(self._state.nesting_level, self.MAX_VISIBLE_NESTING)
        indent = "  " * indent_level

        # Build collapsed text with iteration count
        iteration_count = len(self._state.iterations)
        if iteration_count == 1:
            iterations_text = "1 iteration"
        else:
            iterations_text = f"{iteration_count} iterations"

        # Use expand icon since content is collapsed
        collapsed_text = (
            f"{indent}{EXPAND_ICON} ... {self._state.step_name} ({iterations_text})"
        )

        yield Static(
            collapsed_text,
            classes="iteration iteration-collapsed",
            id=f"collapsed-{self._state.step_name}",
        )

    def on_click(self) -> None:
        """Handle click events to toggle expand/collapse state.

        Only responds to clicks when in collapsed state or for deeply nested loops.
        Emits ToggleExpanded message for parent to handle state update.
        """
        # Toggle expand state if collapsed or if beyond max visible nesting
        if (
            not self._state.expanded
            or self._state.nesting_level > self.MAX_VISIBLE_NESTING
        ):
            # Emit message for parent to handle state update
            self.post_message(
                self.ToggleExpanded(
                    step_name=self._state.step_name,
                    expanded=True,
                )
            )

    def toggle_expanded(self) -> None:
        """Toggle the expanded state of the widget.

        This updates the internal state's expanded flag and triggers recompose.
        For deeply nested loops (> MAX_VISIBLE_NESTING), this allows showing
        the full detail temporarily.
        """
        self._state.expanded = not self._state.expanded
        self.refresh(recompose=True)
        # Emit message for parent to track state
        self.post_message(
            self.ToggleExpanded(
                step_name=self._state.step_name,
                expanded=self._state.expanded,
            )
        )

    def update_state(self, state: LoopIterationState) -> None:
        """Update the widget with new state.

        This replaces the internal state and triggers a full recompose
        to reflect the updated iterations.

        Args:
            state: New loop iteration state.
        """
        self._state = state
        self.refresh(recompose=True)

    @property
    def is_collapsed(self) -> bool:
        """Check if the widget is currently showing collapsed state.

        Returns:
            True if collapsed (not expanded or beyond max nesting level).
        """
        return (
            not self._state.expanded
            or self._state.nesting_level > self.MAX_VISIBLE_NESTING
        )
